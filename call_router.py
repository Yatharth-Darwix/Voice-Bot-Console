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

import logging
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas import (
    AppendSessionEventRequest,
    BindCallRequest,
    ConfigureWebhookRequest,
    ConfigureWebhookResponse,
    InitiateCallRequest,
    PrepareBrowserBotRequest,
    PrepareBrowserBotResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionMessage,
    SessionSummaryResponse,
)
from app.services.call_service import collect_prompt_bundle, pipeline_stream
from app.services.session_service import enrich_messages_with_vapi, to_summary_dict
from app.services.webhook_config_service import (
    auto_configure_webhook_from_env,
    configure_webhook_from_base_url,
    detect_ngrok_public_url,
    normalize_public_base_url,
)
from app.services.webhook_service import process_vapi_server_message
from app.services.webhook_state_service import (
    clear_model_output_state as clear_model_output_state_impl,
)
from app.services.webhook_state_service import (
    persist_server_message as persist_server_message_impl,
)
from app.services.webhook_state_service import (
    resolve_session_id as resolve_session_id_impl,
)
from app.utils.message_normalizers import normalize_vapi_message_dicts
from app.utils.router_helpers import enforce_rate_limit, extract_call_id, get_voice_id_for_gender
from config import settings
from session_store import session_store
from vapi_service import (
    build_assistant_overrides,
    fetch_call_details,
    update_assistant_webhook,
)

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


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _auto_configure_webhook_from_env() -> tuple[str | None, str | None]:
    return await auto_configure_webhook_from_env(
        env_public_base_url=settings.vapi_server_public_base_url,
        assistant_id=settings.vapi_assistant_id,
        server_messages=DEFAULT_SERVER_MESSAGES,
        update_assistant_webhook=update_assistant_webhook,
        logger=logger,
    )


def _normalize_vapi_messages(call_payload: dict[str, Any]) -> list[SessionMessage]:
    return [SessionMessage(**item) for item in normalize_vapi_message_dicts(call_payload)]


def _clear_model_output_state(session_id: str) -> None:
    clear_model_output_state_impl(
        session_id=session_id,
        model_output_accum=_MODEL_OUTPUT_ACCUM,
        model_output_last_persisted=_MODEL_OUTPUT_LAST_PERSISTED,
    )


def _resolve_session_id(
    message: dict[str, Any],
    payload: dict[str, Any] | None,
    call_id: str | None,
) -> str | None:
    return resolve_session_id_impl(
        session_store=session_store,
        message=message,
        payload=payload,
        call_id=call_id,
    )


def _persist_server_message(session_id: str, event_type: str, message: dict[str, Any], source: str) -> None:
    from app.utils.message_normalizers import (
        event_text_from_message,
        extract_text_from_record,
        normalize_role,
    )

    persist_server_message_impl(
        session_store=session_store,
        session_id=session_id,
        event_type=event_type,
        message=message,
        source=source,
        model_output_accum=_MODEL_OUTPUT_ACCUM,
        model_output_last_persisted=_MODEL_OUTPUT_LAST_PERSISTED,
        normalize_role=normalize_role,
        extract_text_from_record=extract_text_from_record,
        event_text_from_message=event_text_from_message,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/initiate-call")
async def initiate_call(body: InitiateCallRequest, request: Request):
    """
    Full phone pipeline:
    1. Stream prompt generation from OpenAI Realtime WebSocket (SSE)
    2. Once done, fire Vapi outbound call
    3. Return call_id in final SSE event
    """
    enforce_rate_limit(
        request=request,
        request_buckets=_REQUEST_BUCKETS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        rate_limit_per_minute=settings.rate_limit_per_minute,
    )

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
        pipeline_stream(
            body=body,
            session_id=session.session_id,
            auto_configure_webhook=_auto_configure_webhook_from_env,
            resolve_voice_id=lambda gender: get_voice_id_for_gender(
                gender,
                male_voice_id=settings.elevenlabs_voice_id_male,
                female_voice_id=settings.elevenlabs_voice_id_female,
            ),
            logger=logger,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/prepare-browser-bot", response_model=PrepareBrowserBotResponse)
async def prepare_browser_bot(body: PrepareBrowserBotRequest, request: Request):
    """
    Generates dynamic assistant config for in-browser Vapi sessions.
    Keeps phone-call flow unchanged.
    """
    enforce_rate_limit(
        request=request,
        request_buckets=_REQUEST_BUCKETS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        rate_limit_per_minute=settings.rate_limit_per_minute,
    )

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
        system_prompt, first_message = await collect_prompt_bundle(body)
        assistant_overrides = build_assistant_overrides(
            system_prompt=system_prompt,
            first_message=first_message,
            voice_id=get_voice_id_for_gender(
                body.voice_gender,
                male_voice_id=settings.elevenlabs_voice_id_male,
                female_voice_id=settings.elevenlabs_voice_id_female,
            ),
            speaking_speed=body.speaking_speed,
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
    enforce_rate_limit(
        request=request,
        request_buckets=_REQUEST_BUCKETS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        rate_limit_per_minute=settings.rate_limit_per_minute,
    )

    assistant_id = (body.assistant_id or settings.vapi_assistant_id or "").strip()
    if not assistant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing assistant id. Set VAPI_ASSISTANT_ID or provide assistant_id.",
        )

    if body.public_base_url and body.public_base_url.strip():
        public_base_url = normalize_public_base_url(body.public_base_url)
    elif settings.vapi_server_public_base_url and settings.vapi_server_public_base_url.strip():
        public_base_url = normalize_public_base_url(settings.vapi_server_public_base_url)
    else:
        public_base_url = await detect_ngrok_public_url(NGROK_LOCAL_API_URL)

    server_messages = body.server_messages or DEFAULT_SERVER_MESSAGES

    try:
        webhook_url = await configure_webhook_from_base_url(
            public_base_url=public_base_url,
            assistant_id=assistant_id,
            server_messages=server_messages,
            update_assistant_webhook=update_assistant_webhook,
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
    sessions = [SessionSummaryResponse(**to_summary_dict(session)) for session in session_store.list()]
    return SessionListResponse(sessions=sessions)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = [SessionMessage(**event) for event in session.transcript_events]
    messages, vapi_fetch_error = await enrich_messages_with_vapi(
        session=session,
        messages=messages,
        fetch_call_details=fetch_call_details,
        normalize_vapi_messages=_normalize_vapi_messages,
    )

    summary = SessionSummaryResponse(**to_summary_dict(session))
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


@router.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    try:
        payload = await request.json()
        return await process_vapi_server_message(
            payload=payload,
            source="api_webhook",
            logger=logger,
            session_store=session_store,
            extract_call_id=extract_call_id,
            resolve_session_id=_resolve_session_id,
            persist_server_message=_persist_server_message,
            clear_model_output_state=_clear_model_output_state,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc


@public_router.post("/webhook/vapi/server")
@public_router.post("/webhook/vapi/server/")
async def vapi_server_webhook(request: Request):
    try:
        payload = await request.json()
        return await process_vapi_server_message(
            payload=payload,
            source="server_url_webhook",
            logger=logger,
            session_store=session_store,
            extract_call_id=extract_call_id,
            resolve_session_id=_resolve_session_id,
            persist_server_message=_persist_server_message,
            clear_model_output_state=_clear_model_output_state,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Server URL webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid server webhook payload") from exc
