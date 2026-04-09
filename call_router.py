"""
Call Router
POST /api/initiate-call        — streams prompt generation, then fires Vapi call
POST /api/prepare-browser-bot  — prepares browser-session assistant config
POST /api/webhook/vapi         — receives Vapi call lifecycle events
POST /webhook/vapi/server      — public server-url webhook endpoint for ngrok/Vapi
GET  /api/sessions             — list logged sessions
GET  /api/sessions/{id}        — session details + transcript
POST /api/sessions/{id}/bind-call — attach browser call_id to a session
"""

import json
import logging
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from time import monotonic
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from config import settings
from gpt_ws import stream_prompt_generation
from session_store import SessionRecord, session_store
from vapi_service import (
    build_assistant_overrides,
    create_outbound_call,
    fetch_call_details,
    update_assistant_webhook,
)
from web_search_service import WebSearchError, run_web_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
public_router = APIRouter()
RATE_LIMIT_WINDOW_SECONDS = 60.0
_REQUEST_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
DEFAULT_SERVER_MESSAGES = [
    "conversation-update",
    "model-output",
    "status-update",
    'transcript[transcriptType="final"]',
    "speech-update",
    "end-of-call-report",
    "tool-calls",
]
NGROK_LOCAL_API_URL = "http://127.0.0.1:4040/api/tunnels"
_MODEL_OUTPUT_ACCUM: dict[tuple[str, str], str] = {}
_MODEL_OUTPUT_LAST_PERSISTED: dict[tuple[str, str], str] = {}
_VAPI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
VAPI_CACHE_TTL = 15.0

# ── Request / Response models ─────────────────────────────────────────────────

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class PromptGenerationRequest(BaseModel):
    industry: str = Field(..., min_length=2, max_length=100, description="Industry sector")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    use_case: str = Field(..., min_length=2, max_length=100, description="Purpose of the call")
    persona: str = Field(..., min_length=5, max_length=300, description="Agent personality and tone")
    guardrails: str = Field(..., min_length=5, max_length=500, description="Rules the agent must follow")
    agent_name: str = Field(default="Aisha", min_length=1, max_length=50, description="Name of the AI agent")
    voice_gender: str = Field(default="female", description="Gender of the voice agent (male/female)")

    @field_validator("industry", "company", "use_case", "persona", "guardrails")
    @classmethod
    def sanitise_input(cls, v: str) -> str:
        # Strip characters that could cause prompt injection.
        return v.replace("```", "").replace("{{", "").replace("}}", "").strip()


class InitiateCallRequest(PromptGenerationRequest):
    phone_number: str = Field(..., description="E.164 format phone number, e.g. +919876543210")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.replace(" ", "").replace("-", "")
        if not PHONE_PATTERN.match(cleaned):
            raise ValueError("Phone number must be in E.164 format, e.g. +919876543210")
        return cleaned


class PrepareBrowserBotRequest(PromptGenerationRequest):
    """Request to generate a browser-session bot config."""


class PrepareBrowserBotResponse(BaseModel):
    session_id: str
    system_prompt: str
    first_message: str
    assistant_id: str
    assistant_overrides: dict[str, Any]


class BindCallRequest(BaseModel):
    call_id: str = Field(..., min_length=2, max_length=120)


class AppendSessionEventRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=40)
    text: str = Field(..., min_length=1, max_length=4000)
    source: str = Field(default="frontend_browser", min_length=2, max_length=60)
    event_type: str = Field(default="message", min_length=2, max_length=60)
    metadata: dict[str, Any] | None = None


class ConfigureWebhookRequest(BaseModel):
    public_base_url: str | None = Field(
        default=None,
        description="Optional public base URL (e.g. https://xxxx.ngrok-free.app).",
    )
    assistant_id: str | None = Field(
        default=None,
        description="Optional assistant id. Falls back to VAPI_ASSISTANT_ID.",
    )
    server_messages: list[str] | None = Field(
        default=None,
        description="Optional override for assistant serverMessages.",
    )


class ConfigureWebhookResponse(BaseModel):
    assistant_id: str
    webhook_url: str
    server_messages: list[str]


class SessionSummaryResponse(BaseModel):
    session_id: str
    mode: str
    status: str
    call_id: str | None
    industry: str
    company: str
    use_case: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummaryResponse]


class SessionMessage(BaseModel):
    at: str
    role: str
    text: str
    source: str
    event_type: str
    metadata: dict[str, Any] | None = None


class SessionDetailResponse(SessionSummaryResponse):
    persona: str
    guardrails: str
    system_prompt: str
    first_message: str
    messages: list[SessionMessage]
    vapi_fetch_error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_voice_id_for_gender(gender: str) -> str | None:
    """Map gender choice to ElevenLabs voice ID from environment."""
    g = gender.lower().strip()
    if g == "male":
        return settings.elevenlabs_voice_id_male
    if g == "female":
        return settings.elevenlabs_voice_id_female
    return None


def _enforce_rate_limit(request: Request) -> None:
    """Simple in-memory per-IP rate limiter."""
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    bucket = _REQUEST_BUCKETS[client_ip]

    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry shortly.")

    bucket.append(now)


def _to_summary(session: SessionRecord) -> SessionSummaryResponse:
    return SessionSummaryResponse(
        session_id=session.session_id,
        mode=session.mode,
        status=session.status,
        call_id=session.call_id,
        industry=session.industry,
        company=session.company,
        use_case=session.use_case,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(raw: Any) -> str:
    if raw is None:
        return _now_iso()

    if isinstance(raw, (int, float)):
        epoch = float(raw)
        if epoch > 10_000_000_000:
            epoch = epoch / 1000.0
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

    value = str(raw).strip()
    if not value:
        return _now_iso()

    if value.isdigit():
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch = epoch / 1000.0
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return _now_iso()


def _normalize_public_base_url(url: str) -> str:
    return url.strip().rstrip("/")


async def _detect_ngrok_public_url() -> str:
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(NGROK_LOCAL_API_URL)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not query local ngrok API at http://127.0.0.1:4040/api/tunnels. "
                    "Start ngrok or provide public_base_url."
                ),
            ) from exc

    tunnels = payload.get("tunnels")
    if not isinstance(tunnels, list):
        raise HTTPException(
            status_code=400,
            detail="ngrok API did not return tunnel list. Provide public_base_url explicitly.",
        )

    https_tunnel: str | None = None
    http_tunnel: str | None = None
    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = tunnel.get("public_url")
        if not isinstance(public_url, str) or not public_url:
            continue
        if public_url.startswith("https://") and not https_tunnel:
            https_tunnel = public_url
        if public_url.startswith("http://") and not http_tunnel:
            http_tunnel = public_url

    selected = https_tunnel or http_tunnel
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="No ngrok public tunnel found. Start ngrok or provide public_base_url.",
        )

    return _normalize_public_base_url(selected)


async def _configure_webhook_from_base_url(public_base_url: str) -> str:
    assistant_id = (settings.vapi_assistant_id or "").strip()
    if not assistant_id:
        raise RuntimeError("Missing assistant id. Set VAPI_ASSISTANT_ID.")

    webhook_url = f"{_normalize_public_base_url(public_base_url)}/webhook/vapi/server"
    await update_assistant_webhook(
        assistant_id=assistant_id,
        server_url=webhook_url,
        server_messages=DEFAULT_SERVER_MESSAGES,
    )
    return webhook_url


async def _auto_configure_webhook_from_env() -> tuple[str | None, str | None]:
    public_base_url = (settings.vapi_server_public_base_url or "").strip()
    if not public_base_url:
        return None, None

    try:
        webhook_url = await _configure_webhook_from_base_url(public_base_url)
        return webhook_url, None
    except RuntimeError as exc:
        logger.error("Auto webhook sync failed: %s", exc)
        return None, str(exc)


def _normalize_vapi_messages(call_payload: dict[str, Any]) -> list[SessionMessage]:
    """Extract transcript-like messages from Vapi call payload."""
    raw_messages: Any = None
    artifact = call_payload.get("artifact")
    if isinstance(artifact, dict):
        artifact_transcript = artifact.get("transcript")
        if isinstance(artifact_transcript, list):
            raw_messages = artifact_transcript
        elif isinstance(artifact.get("messages"), list):
            raw_messages = artifact.get("messages")

    if not isinstance(raw_messages, list):
        if isinstance(call_payload.get("transcript"), list):
            raw_messages = call_payload.get("transcript")
        elif isinstance(call_payload.get("messages"), list):
            raw_messages = call_payload.get("messages")

    if not isinstance(raw_messages, list):
        return []

    normalized: list[SessionMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue

        role = _normalize_role(item.get("role") or item.get("speaker"))
        if role not in {"assistant", "user"}:
            continue
        timestamp = _normalize_timestamp(item.get("time") or item.get("timestamp") or item.get("createdAt"))

        text = _extract_text_from_record(item)

        if not text:
            continue

        normalized.append(
            SessionMessage(
                at=timestamp,
                role=role,
                text=text,
                source=str(item.get("source") or "vapi_call_fetch"),
                event_type=str(item.get("type") or "message"),
                metadata=item,
            )
        )

    return normalized


def _normalize_role(raw_role: Any) -> str:
    role = str(raw_role or "").strip().lower()
    if role in {"assistant", "agent", "bot", "ai"}:
        return "assistant"
    if role in {"user", "customer", "client", "caller", "human"}:
        return "user"
    if role == "system":
        return "event"
    return role or "event"


def _extract_text_from_record(item: dict[str, Any]) -> str:
    def _read_list_content(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        parts: list[str] = []
        for chunk in value:
            if isinstance(chunk, str):
                if chunk.strip():
                    parts.append(chunk.strip())
            elif isinstance(chunk, dict):
                chunk_text = str(
                    chunk.get("text")
                    or chunk.get("content")
                    or chunk.get("output_text")
                    or chunk.get("value")
                    or ""
                ).strip()
                if chunk_text:
                    parts.append(chunk_text)
        return " ".join(parts).strip()

    value = item.get("message")
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    elif isinstance(value, list):
        list_text = _read_list_content(value)
        if list_text:
            return list_text
    elif isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            content_text = _read_list_content(content)
            if content_text:
                return content_text
        fallback = str(value.get("text") or "").strip()
        if fallback:
            return fallback

    transcript = item.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()

    content = item.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        content_text = _read_list_content(content)
        if content_text:
            return content_text

    output = item.get("output")
    if isinstance(output, str) and output.strip():
        return output.strip()
    if isinstance(output, dict):
        output_text = str(output.get("text") or output.get("content") or "").strip()
        if output_text:
            return output_text

    return ""


def _event_text_from_message(message: dict[str, Any], event_type: str) -> str:
    if event_type == "status-update":
        status = str(message.get("status") or "unknown")
        ended_reason = str(message.get("endedReason") or "").strip()
        if ended_reason:
            return f"Status changed to {status} ({ended_reason})"
        return f"Status changed to {status}"

    if event_type == "speech-update":
        role = str(message.get("role") or "assistant")
        status = str(message.get("status") or "unknown")
        return f"{role} speech {status}"

    if event_type in {"hang", "call-ended"}:
        ended_reason = str(message.get("endedReason") or "unknown")
        return f"Call ended ({ended_reason})"

    if event_type == "end-of-call-report":
        report = message.get("analysis") or message.get("report") or {}
        if isinstance(report, dict):
            summary = str(report.get("summary") or "").strip()
            if summary:
                return f"End-of-call report: {summary}"
        return "End-of-call report received"

    if event_type == "assistant.started":
        return "Assistant connected"

    return f"Event received: {event_type}"


def _extract_call_id(message: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    call = message.get("call")
    if isinstance(call, dict):
        value = call.get("id")
        if isinstance(value, str) and value:
            return value

    value = message.get("callId")
    if isinstance(value, str) and value:
        return value

    if isinstance(payload, dict):
        payload_call = payload.get("call")
        if isinstance(payload_call, dict):
            value = payload_call.get("id")
            if isinstance(value, str) and value:
                return value

        value = payload.get("callId")
        if isinstance(value, str) and value:
            return value

    return None


def _append_if_new(
    *,
    session_id: str,
    role: str,
    text: str,
    source: str,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    cleaned = text.strip()
    if not cleaned:
        return

    session = session_store.get(session_id)
    if session and session.transcript_events:
        last = session.transcript_events[-1]
        if (
            str(last.get("role") or "") == role
            and str(last.get("text") or "") == cleaned
            and str(last.get("event_type") or "") == event_type
        ):
            return

    session_store.append_transcript_event(
        session_id=session_id,
        role=role,
        text=cleaned,
        source=source,
        event_type=event_type,
        metadata=metadata,
    )


def _clear_model_output_state(session_id: str) -> None:
    for key in list(_MODEL_OUTPUT_ACCUM.keys()):
        if key[0] == session_id:
            _MODEL_OUTPUT_ACCUM.pop(key, None)
            _MODEL_OUTPUT_LAST_PERSISTED.pop(key, None)


def _extract_session_hint(message: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("session_id") or metadata.get("sessionId")
        if isinstance(value, str) and value:
            return value

    call = message.get("call")
    if isinstance(call, dict):
        metadata = call.get("metadata")
        if isinstance(metadata, dict):
            value = metadata.get("session_id") or metadata.get("sessionId")
            if isinstance(value, str) and value:
                return value

    if isinstance(payload, dict):
        payload_metadata = payload.get("metadata")
        if isinstance(payload_metadata, dict):
            value = payload_metadata.get("session_id") or payload_metadata.get("sessionId")
            if isinstance(value, str) and value:
                return value

        payload_call = payload.get("call")
        if isinstance(payload_call, dict):
            payload_call_metadata = payload_call.get("metadata")
            if isinstance(payload_call_metadata, dict):
                value = payload_call_metadata.get("session_id") or payload_call_metadata.get("sessionId")
                if isinstance(value, str) and value:
                    return value

    return None


def _extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw = message.get("toolCallList")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    fallback = message.get("toolCalls")
    if isinstance(fallback, list):
        return [item for item in fallback if isinstance(item, dict)]

    return []


async def _handle_tool_calls(message: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    tool_calls = _extract_tool_calls(message)

    if not tool_calls:
        return {
            "results": [],
            "error": "No toolCallList found in tool-calls message",
        }

    for call in tool_calls:
        tool_call_id = str(call.get("id") or "")
        function_block = call.get("function")
        if not isinstance(function_block, dict):
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": "unknown",
                    "error": "Missing function payload",
                }
            )
            continue

        function_name = str(function_block.get("name") or "unknown")
        raw_arguments = function_block.get("arguments")
        parsed_args: dict[str, Any] = {}

        if isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                maybe_args = json.loads(raw_arguments)
                if isinstance(maybe_args, dict):
                    parsed_args = maybe_args
            except json.JSONDecodeError:
                parsed_args = {}
        elif isinstance(raw_arguments, dict):
            parsed_args = raw_arguments

        if function_name != "web_search":
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": f"Unsupported tool '{function_name}'",
                }
            )
            continue

        query = str(parsed_args.get("query") or parsed_args.get("q") or "").strip()
        max_results = parsed_args.get("max_results", 3)

        try:
            max_results_int = int(max_results)
        except (TypeError, ValueError):
            max_results_int = 3

        if not query:
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": "Missing 'query' argument",
                }
            )
            continue

        try:
            result_text = await run_web_search(query=query, max_results=max_results_int)
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "result": result_text.replace("\n", " ").strip(),
                }
            )
        except WebSearchError as exc:
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": str(exc),
                }
            )

    return {"results": results}


def _resolve_session_id(
    message: dict[str, Any],
    payload: dict[str, Any] | None,
    call_id: str | None,
) -> str | None:
    if call_id:
        mapped = session_store.session_id_for_call(call_id)
        if mapped:
            return mapped

        for candidate in session_store.list():
            if candidate.call_id == call_id:
                return candidate.session_id

        for candidate in session_store.list():
            if candidate.mode == "phone" and not candidate.call_id and candidate.status in {
                "dialing",
                "prompt_ready",
                "generating_prompt",
            }:
                session_store.bind_call(candidate.session_id, call_id)
                return candidate.session_id

    session_hint = _extract_session_hint(message, payload)
    if session_hint and session_store.get(session_hint):
        if call_id:
            session_store.bind_call(session_hint, call_id)
        return session_hint

    return None


def _persist_server_message(session_id: str, event_type: str, message: dict[str, Any], source: str) -> None:
    transcript = str(message.get("transcript") or "").strip()
    transcript_type = str(message.get("transcriptType") or "").strip().lower()
    is_transcript_event = event_type == "transcript" or event_type.startswith("transcript[")

    if transcript and (is_transcript_event or transcript_type):
        if not transcript_type or transcript_type == "final":
            _append_if_new(
                session_id=session_id,
                role=_normalize_role(message.get("role") or "event"),
                text=transcript,
                source=source,
                event_type="transcript",
                metadata=message,
            )
            session_store.set_status(session_id, "in_progress")
        return

    if event_type == "conversation-update":
        history = message.get("messages")
        if isinstance(history, list) and history:
            latest = history[-1]
            if isinstance(latest, dict):
                latest_text = _extract_text_from_record(latest)
                if latest_text:
                    _append_if_new(
                        session_id=session_id,
                        role=_normalize_role(latest.get("role")),
                        text=latest_text,
                        source=source,
                        event_type="conversation-update",
                        metadata=latest,
                    )
                    session_store.set_status(session_id, "in_progress")
                    return

    if event_type == "model-output":
        turn_id = str(message.get("turnId") or "").strip()
        output = message.get("output")
        token = ""
        if isinstance(output, str):
            token = output
        elif isinstance(output, dict):
            token = str(output.get("text") or output.get("content") or "")
        token = token.strip("\n")

        if token:
            if turn_id:
                key = (session_id, turn_id)
                merged = f"{_MODEL_OUTPUT_ACCUM.get(key, '')}{token}"
                _MODEL_OUTPUT_ACCUM[key] = merged
                previous_persisted = _MODEL_OUTPUT_LAST_PERSISTED.get(key, "")
                should_persist = (
                    token.endswith((".", "!", "?", ","))
                    or len(merged) - len(previous_persisted) >= 28
                )
                if should_persist:
                    _MODEL_OUTPUT_LAST_PERSISTED[key] = merged
                    _append_if_new(
                        session_id=session_id,
                        role="assistant",
                        text=merged.strip(),
                        source=source,
                        event_type="model-output",
                        metadata=message,
                    )
                    session_store.set_status(session_id, "in_progress")
                return

            _append_if_new(
                session_id=session_id,
                role="assistant",
                text=token.strip(),
                source=source,
                event_type="model-output",
                metadata=message,
            )
            session_store.set_status(session_id, "in_progress")
            return

    event_text = _event_text_from_message(message, event_type)
    _append_if_new(
        session_id=session_id,
        role="event",
        text=event_text,
        source=source,
        event_type=event_type,
        metadata=message,
    )


async def _collect_prompt_bundle(body: PromptGenerationRequest) -> tuple[str, str]:
    """Collect final prompt outputs from the SSE-style generator."""
    system_prompt: str = ""
    first_message: str = ""

    async for chunk in stream_prompt_generation(
        industry=body.industry,
        company=body.company,
        use_case=body.use_case,
        persona=body.persona,
        guardrails=body.guardrails,
    ):
        if not chunk.startswith("data: "):
            continue

        try:
            payload = json.loads(chunk[6:])
        except json.JSONDecodeError:
            continue

        if payload.get("error"):
            raise RuntimeError(payload["error"])

        if payload.get("done"):
            system_prompt = payload.get("system_prompt", "")
            first_message = payload.get("first_message", "")

    if not system_prompt:
        raise RuntimeError("No system prompt generated")

    return system_prompt, first_message


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/initiate-call")
async def initiate_call(body: InitiateCallRequest, request: Request):
    """
    Full phone pipeline:
    1. Stream prompt generation from OpenAI Realtime WebSocket (SSE)
    2. Once done, fire Vapi outbound call
    3. Return call_id in final SSE event
    """
    _enforce_rate_limit(request)

    session = session_store.create(
        mode="phone",
        industry=body.industry,
        company=body.company,
        use_case=body.use_case,
        persona=body.persona,
        guardrails=body.guardrails,
        status="generating_prompt",
    )

    return StreamingResponse(
        _pipeline_stream(body, session_id=session.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _pipeline_stream(body: InitiateCallRequest, session_id: str) -> AsyncGenerator[str, None]:
    """Orchestrates GPT WS streaming → Vapi call creation."""
    system_prompt: str = ""
    first_message: str = ""

    try:
        yield f"data: {json.dumps({'phase': 'session', 'session_id': session_id, 'status': 'created'})}\n\n"

        webhook_url, webhook_error = await _auto_configure_webhook_from_env()
        if webhook_url:
            yield f"data: {json.dumps({'phase': 'webhook', 'status': 'synced', 'webhook_url': webhook_url, 'session_id': session_id})}\n\n"
        elif webhook_error:
            yield f"data: {json.dumps({'phase': 'webhook', 'status': 'sync_failed', 'detail': webhook_error, 'session_id': session_id})}\n\n"

        # Phase 1: Stream GPT prompt generation.
        async for chunk in stream_prompt_generation(
            industry=body.industry,
            company=body.company,
            use_case=body.use_case,
            persona=body.persona,
            guardrails=body.guardrails,
            agent_name=body.agent_name,
            agent_gender=body.voice_gender,
        ):
            if chunk.startswith("data: "):
                try:
                    payload = json.loads(chunk[6:])
                    if payload.get("done"):
                        system_prompt = payload.get("system_prompt", "")
                        first_message = payload.get("first_message", "")
                except json.JSONDecodeError:
                    pass
            yield chunk

        if not system_prompt:
            session_store.set_status(session_id, "failed")
            yield f"data: {json.dumps({'error': 'No system prompt generated', 'session_id': session_id})}\n\n"
            return

        session_store.attach_prompt(session_id, system_prompt, first_message)
        session_store.set_status(session_id, "prompt_ready")

        # Phase 2: Fire Vapi call.
        yield f"data: {json.dumps({'phase': 'vapi', 'status': 'dialing', 'session_id': session_id})}\n\n"

        call_result = await create_outbound_call(
            phone_number=body.phone_number,
            system_prompt=system_prompt,
            first_message=first_message,
            voice_id=_get_voice_id_for_gender(body.voice_gender),
            metadata={"session_id": session_id},
        )

        session_store.bind_call(session_id, call_result["call_id"])
        session_store.set_status(session_id, "dialing")

        yield f"data: {json.dumps({'phase': 'call_live', 'call_id': call_result['call_id'], 'status': 'dialing', 'session_id': session_id})}\n\n"

    except RuntimeError as exc:
        session_store.set_status(session_id, "failed")
        logger.error("Pipeline error: %s", exc)
        yield f"data: {json.dumps({'error': str(exc), 'session_id': session_id})}\n\n"


@router.post("/prepare-browser-bot", response_model=PrepareBrowserBotResponse)
async def prepare_browser_bot(body: PrepareBrowserBotRequest, request: Request):
    """
    Generates dynamic assistant config for in-browser Vapi sessions.
    Keeps phone-call flow unchanged.
    """
    _enforce_rate_limit(request)

    if not settings.vapi_assistant_id:
        raise HTTPException(status_code=500, detail="Missing VAPI_ASSISTANT_ID in server environment")

    session = session_store.create(
        mode="browser",
        industry=body.industry,
        company=body.company,
        use_case=body.use_case,
        persona=body.persona,
        guardrails=body.guardrails,
        status="generating_prompt",
    )

    try:
        await _auto_configure_webhook_from_env()
        system_prompt, first_message = await _collect_prompt_bundle(body)
        assistant_overrides = build_assistant_overrides(
            system_prompt=system_prompt,
            first_message=first_message,
            voice_id=_get_voice_id_for_gender(body.voice_gender),
        )

        session_store.attach_prompt(session.session_id, system_prompt, first_message)
        session_store.set_status(session.session_id, "ready_for_browser_talk")

        return PrepareBrowserBotResponse(
            session_id=session.session_id,
            system_prompt=system_prompt,
            first_message=first_message,
            assistant_id=settings.vapi_assistant_id,
            assistant_overrides=assistant_overrides,
        )

    except RuntimeError as exc:
        session_store.set_status(session.session_id, "failed")
        logger.error("Prepare browser bot error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/vapi/configure-webhook", response_model=ConfigureWebhookResponse)
async def configure_vapi_webhook(body: ConfigureWebhookRequest, request: Request):
    """
    Sync assistant server webhook URL + serverMessages.
    If public_base_url is omitted, attempts to discover local ngrok URL automatically.
    """
    _enforce_rate_limit(request)

    assistant_id = (body.assistant_id or settings.vapi_assistant_id or "").strip()
    if not assistant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing assistant id. Set VAPI_ASSISTANT_ID or provide assistant_id.",
        )

    if body.public_base_url and body.public_base_url.strip():
        public_base_url = _normalize_public_base_url(body.public_base_url)
    elif settings.vapi_server_public_base_url and settings.vapi_server_public_base_url.strip():
        public_base_url = _normalize_public_base_url(settings.vapi_server_public_base_url)
    else:
        public_base_url = await _detect_ngrok_public_url()

    webhook_url = f"{public_base_url}/webhook/vapi/server"
    server_messages = body.server_messages or DEFAULT_SERVER_MESSAGES

    try:
        await update_assistant_webhook(
            assistant_id=assistant_id,
            server_url=webhook_url,
            server_messages=server_messages,
        )
    except RuntimeError as exc:
        logger.error("Failed to configure Vapi webhook: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConfigureWebhookResponse(
        assistant_id=assistant_id,
        webhook_url=webhook_url,
        server_messages=server_messages,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    sessions = [_to_summary(session) for session in session_store.list()]
    return SessionListResponse(sessions=sessions)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = [SessionMessage(**event) for event in session.transcript_events]
    vapi_fetch_error: str | None = None

    if session.call_id:
        now = monotonic()
        cached_at, cached_payload = _VAPI_CACHE.get(session.call_id, (0.0, None))

        if cached_payload and (now - cached_at < VAPI_CACHE_TTL):
            call_payload = cached_payload
        else:
            try:
                call_payload = await fetch_call_details(session.call_id)
                _VAPI_CACHE[session.call_id] = (now, call_payload)
            except RuntimeError as exc:
                vapi_fetch_error = str(exc)
                call_payload = cached_payload or {}

        if call_payload:
            fetched_messages = _normalize_vapi_messages(call_payload)
            if fetched_messages:
                existing_keys = {(msg.at, msg.role, msg.text, msg.event_type) for msg in messages}
                for fetched in fetched_messages:
                    key = (fetched.at, fetched.role, fetched.text, fetched.event_type)
                    if key in existing_keys:
                        continue
                    messages.append(fetched)
                    existing_keys.add(key)

    messages = sorted(messages, key=lambda item: item.at)

    summary = _to_summary(session)
    return SessionDetailResponse(
        **summary.model_dump(),
        persona=session.persona,
        guardrails=session.guardrails,
        system_prompt=session.system_prompt,
        first_message=session.first_message,
        messages=messages,
        vapi_fetch_error=vapi_fetch_error,
    )


@router.post("/sessions/{session_id}/bind-call")
async def bind_session_call(session_id: str, body: BindCallRequest):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_store.bind_call(session_id, body.call_id)
    session_store.set_status(session_id, "in_progress")
    return {"ok": True, "session_id": session_id, "call_id": body.call_id}


@router.post("/sessions/{session_id}/events")
async def append_session_event(session_id: str, body: AppendSessionEventRequest):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_store.append_transcript_event(
        session_id=session_id,
        role=body.role,
        text=body.text,
        source=body.source,
        event_type=body.event_type,
        metadata=body.metadata,
    )

    if body.event_type in {"call-start", "call-started", "in-progress", "status-update:in-progress"}:
        session_store.set_status(session_id, "in_progress")
    elif body.event_type in {"call-end", "ended", "hang", "status-update:ended"}:
        session_store.set_status(session_id, "ended")

    return {"ok": True, "session_id": session_id}


async def _process_vapi_server_message(payload: dict[str, Any], source: str) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, dict):
        # Some integrations may send the ServerMessage "message" object directly.
        direct_type = payload.get("type")
        if isinstance(direct_type, str) and direct_type:
            message = payload

    if not isinstance(message, dict):
        raise HTTPException(status_code=400, detail="Invalid payload: missing message object")

    event_type = str(message.get("type") or "unknown")
    call_id = _extract_call_id(message, payload)
    session_id = _resolve_session_id(message, payload, call_id)

    logger.info("Vapi server message: type=%s call_id=%s session_id=%s", event_type, call_id, session_id)

    if event_type == "tool-calls":
        tool_response = await _handle_tool_calls(message)
        if session_id:
            session_store.append_transcript_event(
                session_id=session_id,
                role="event",
                text="Tool call processed",
                source=source,
                event_type="tool-calls",
                metadata=message,
            )
        return tool_response

    if session_id:
        if event_type in {"status-update", "call-started"}:
            status = str(message.get("status") or "").lower()
            if status in {"in-progress", "in_progress"} or event_type == "call-started":
                session_store.set_status(session_id, "in_progress")
            elif status == "ended":
                session_store.set_status(session_id, "ended")
                _clear_model_output_state(session_id)
            else:
                session_store.set_status(session_id, status or "in_progress")

        if event_type in {"call-ended", "hang"}:
            session_store.set_status(session_id, "ended")
            _clear_model_output_state(session_id)

        _persist_server_message(session_id=session_id, event_type=event_type, message=message, source=source)

    return {"received": True, "event_type": event_type, "session_id": session_id, "call_id": call_id}


@router.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    try:
        payload = await request.json()
        return await _process_vapi_server_message(payload=payload, source="api_webhook")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc


@public_router.post("/webhook/vapi/server")
@public_router.post("/webhook/vapi/server/")
async def vapi_server_webhook(request: Request):
    try:
        payload = await request.json()
        return await _process_vapi_server_message(payload=payload, source="server_url_webhook")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Server URL webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid server webhook payload") from exc
