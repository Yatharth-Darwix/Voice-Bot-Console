"""
OpenAI Realtime WebSocket Service
Connects to OpenAI Realtime API to stream-generate Vapi system prompts.
"""

import asyncio
import json
import logging
import socket
from typing import Any, AsyncGenerator

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config import settings
from meta_prompt import build_greeting_prompt, build_meta_prompt

logger = logging.getLogger(__name__)

REALTIME_URL = (
    "wss://api.openai.com/v1/realtime"
    "?model=gpt-realtime"
)

WS_HEADERS = {
    "Authorization": f"Bearer {settings.openai_api_key}",
}

PROMPT_TIMEOUT_SECONDS = 90
FIRST_TOKEN_TIMEOUT_SECONDS = 20


async def stream_prompt_generation(
    industry: str,
    company: str,
    use_case: str,
    persona: str,
    guardrails: str,
    agent_name: str,
    agent_gender: str,
    customer_name: str,
    customer_gender: str,
    call_flow: str = "",
    query_handling: str = "",
) -> AsyncGenerator[str, None]:
    """
    Connects to OpenAI Realtime WebSocket, streams system prompt tokens
    back as SSE-formatted chunks, then triggers a Vapi call.

    Yields SSE strings: data: {...}\n\n
    """
    full_prompt: list[str] = []
    first_message: str = ""

    try:
        await _ensure_dns_resolution("api.openai.com", timeout=8.0)

        async with websockets.connect(
            REALTIME_URL,
            extra_headers=WS_HEADERS,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:

            logger.info("GPT Realtime WebSocket connected")

            # ── Wait for session.created ──────────────────────────────────
            await _wait_for_event(ws, "session.created", timeout=10)

            # ── Configure session (text only, no audio) ───────────────────
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "output_modalities": ["text"],
                    "instructions": (
                        "You are a world-class AI voice agent prompt engineer. "
                        "Output ONLY the system prompt text. "
                        "No preamble. No explanation. No markdown. No code fences."
                    ),
                    "max_output_tokens": 2500,
                },
            }))

            # ── Send meta-prompt as user message ──────────────────────────
            meta_prompt_text = build_meta_prompt(
                industry=industry,
                company=company,
                use_case=use_case,
                persona=persona,
                guardrails=guardrails,
                agent_name=agent_name,
                agent_gender=agent_gender,
                customer_name=customer_name,
                customer_gender=customer_gender,
                call_flow=call_flow,
                query_handling=query_handling,
            )

            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": meta_prompt_text}],
                },
            }))

            await ws.send(json.dumps({
                "type": "response.create",
                "response": {"output_modalities": ["text"]},
            }))

            logger.info("Streaming system prompt generation...")

            # ── Stream response tokens ─────────────────────────────────────
            async for raw in _stream_response(ws):
                full_prompt.append(raw)
                yield f"data: {json.dumps({'token': raw, 'phase': 'system_prompt'})}\n\n"

            system_prompt = "".join(full_prompt)
            logger.info("System prompt complete (%d chars)", len(system_prompt))

            # ── Generate firstMessage (same session, new turn) ────────────
            yield f"data: {json.dumps({'phase': 'greeting', 'status': 'generating'})}\n\n"

            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": build_greeting_prompt(
                        company=company,
                        use_case=use_case,
                        persona=persona,
                        agent_name=agent_name,
                        agent_gender=agent_gender,
                        customer_name=customer_name,
                        customer_gender=customer_gender,
                    )}],
                },
            }))

            await ws.send(json.dumps({
                "type": "response.create",
                "response": {"output_modalities": ["text"]},
            }))

            greeting_parts: list[str] = []
            async for raw in _stream_response(ws):
                greeting_parts.append(raw)

            first_message = "".join(greeting_parts).strip().strip('"')
            logger.info("First message generated: %s", first_message[:80])

        # ── Emit final payload ────────────────────────────────────────────
        yield f"data: {json.dumps({
            'done': True,
            'system_prompt': system_prompt,
            'first_message': first_message,
        })}\n\n"

    except asyncio.TimeoutError:
        logger.error("GPT WebSocket timed out after %ds", PROMPT_TIMEOUT_SECONDS)
        yield f"data: {json.dumps({'error': 'OpenAI Realtime timed out. Check internet/DNS and retry.'})}\n\n"

    except socket.gaierror as exc:
        logger.error("DNS resolution failed for OpenAI Realtime: %s", exc)
        yield f"data: {json.dumps({'error': 'DNS lookup failed for api.openai.com. Check network/DNS settings.'})}\n\n"

    except (ConnectionClosed, WebSocketException) as exc:
        logger.error("WebSocket error: %s", exc)
        yield f"data: {json.dumps({'error': f'WebSocket connection failed: {exc}'})}\n\n"

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Unexpected error in GPT WS stream")
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"


# ── Private helpers ────────────────────────────────────────────────────────────

async def _wait_for_event(
    ws: Any,
    event_type: str,
    timeout: float = 10.0,
) -> dict:
    """Wait for a specific event type from the WebSocket."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timed out waiting for event: {event_type}")

        raw_msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = json.loads(raw_msg)

        if event.get("type") == event_type:
            return event
        if event.get("type") == "error":
            raise RuntimeError(f"OpenAI error: {event.get('error', {}).get('message')}")


async def _stream_response(
    ws: Any,
) -> AsyncGenerator[str, None]:
    """
    Yield text delta tokens from a response.text.delta stream.
    Returns when response.done is received.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PROMPT_TIMEOUT_SECONDS

    collected_parts: list[str] = []
    saw_delta = False
    first_token_deadline = loop.time() + FIRST_TOKEN_TIMEOUT_SECONDS

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError("Timed out waiting for Realtime response")

        raw_msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = json.loads(raw_msg)
        etype = event.get("type", "")

        if etype in {"response.text.delta", "response.output_text.delta"}:
            delta = event.get("delta", "")
            if delta:
                saw_delta = True
                collected_parts.append(delta)
                yield delta
        elif etype == "response.content_part.added":
            part = event.get("part", {})
            text = _extract_text_from_part(part)
            if text and not saw_delta:
                collected_parts.append(text)
                yield text
        elif etype == "response.done":
            response = event.get("response", {})
            status = response.get("status")

            if status and status != "completed":
                reason = _extract_response_error(response)
                raise RuntimeError(f"OpenAI Realtime response failed ({status}): {reason}")

            if not collected_parts:
                fallback_text = _extract_text_from_response(response)
                if fallback_text:
                    yield fallback_text
            return
        elif etype == "error":
            raise RuntimeError(
                f"OpenAI Realtime error: {event.get('error', {}).get('message', 'unknown')}"
            )

        if not saw_delta and loop.time() > first_token_deadline:
            raise asyncio.TimeoutError(
                "No token received from OpenAI Realtime. Possible network or DNS issue."
            )


async def _ensure_dns_resolution(hostname: str, timeout: float) -> None:
    """Fail fast when DNS resolution is unavailable."""
    loop = asyncio.get_running_loop()
    await asyncio.wait_for(loop.getaddrinfo(hostname, 443), timeout=timeout)


def _extract_response_error(response: dict) -> str:
    status_details = response.get("status_details", {})
    error = status_details.get("error", {})
    return error.get("message") or status_details.get("reason") or "unknown reason"


def _extract_text_from_part(part: dict) -> str:
    if not isinstance(part, dict):
        return ""

    part_type = part.get("type")
    if part_type in {"output_text", "text", "input_text"}:
        return str(part.get("text", "")).strip()
    if part_type == "message":
        return _extract_text_from_response({"output": [part]})
    return ""


def _extract_text_from_response(response: dict) -> str:
    outputs = response.get("output", [])
    texts: list[str] = []

    for output in outputs:
        content = output.get("content", [])
        for part in content:
            text = _extract_text_from_part(part)
            if text:
                texts.append(text)

    return "".join(texts)
