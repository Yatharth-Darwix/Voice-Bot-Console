"""Call orchestration service functions."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from gpt_ws import stream_prompt_generation
from session_store import session_store
from vapi_service import create_outbound_call


async def collect_prompt_bundle(body: Any) -> tuple[str, str]:
    """Collect final prompt outputs from the SSE-style generator."""
    system_prompt: str = ""
    first_message: str = ""

    async for chunk in stream_prompt_generation(
        industry=body.industry,
        company=body.company,
        use_case=body.use_case,
        persona=body.persona,
        guardrails=body.guardrails,
        agent_name=body.agent_name,
        agent_gender=body.voice_gender,
        start_language=body.start_language,
        customer_name=body.customer_name,
        customer_gender=body.customer_gender,
        call_flow=body.call_flow,
        query_handling=body.query_handling,
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


async def pipeline_stream(
    *,
    body: Any,
    session_id: str,
    auto_configure_webhook: Callable[[], Awaitable[tuple[str | None, str | None]]],
    resolve_voice_id: Callable[[str], str | None],
    logger: logging.Logger,
) -> AsyncGenerator[str, None]:
    """Orchestrate GPT streaming and outbound call creation."""
    system_prompt: str = ""
    first_message: str = ""

    try:
        yield (
            f"data: {json.dumps({'phase': 'session', 'session_id': session_id, 'status': 'created'})}\\n\\n"
        )

        webhook_url, webhook_error = await auto_configure_webhook()
        if webhook_url:
            yield (
                "data: "
                + json.dumps(
                    {
                        "phase": "webhook",
                        "status": "synced",
                        "webhook_url": webhook_url,
                        "session_id": session_id,
                    }
                )
                + "\\n\\n"
            )
        elif webhook_error:
            yield (
                "data: "
                + json.dumps(
                    {
                        "phase": "webhook",
                        "status": "sync_failed",
                        "detail": webhook_error,
                        "session_id": session_id,
                    }
                )
                + "\\n\\n"
            )

        async for chunk in stream_prompt_generation(
            industry=body.industry,
            company=body.company,
            use_case=body.use_case,
            persona=body.persona,
            guardrails=body.guardrails,
            agent_name=body.agent_name,
            agent_gender=body.voice_gender,
            start_language=body.start_language,
            customer_name=body.customer_name,
            customer_gender=body.customer_gender,
            call_flow=body.call_flow,
            query_handling=body.query_handling,
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
            yield f"data: {json.dumps({'error': 'No system prompt generated', 'session_id': session_id})}\\n\\n"
            return

        session_store.attach_prompt(session_id, system_prompt, first_message)
        session_store.set_status(session_id, "prompt_ready")

        yield f"data: {json.dumps({'phase': 'vapi', 'status': 'dialing', 'session_id': session_id})}\\n\\n"

        call_result = await create_outbound_call(
            phone_number=body.phone_number,
            system_prompt=system_prompt,
            first_message=first_message,
            voice_id=resolve_voice_id(body.voice_gender),
            speaking_speed=body.speaking_speed,
            metadata={"session_id": session_id},
        )

        session_store.bind_call(session_id, call_result["call_id"])
        session_store.set_status(session_id, "dialing")

        yield (
            f"data: {json.dumps({'phase': 'call_live', 'call_id': call_result['call_id'], 'status': 'dialing', 'session_id': session_id})}\\n\\n"
        )

    except RuntimeError as exc:
        session_store.set_status(session_id, "failed")
        logger.error("Pipeline error: %s", exc)
        yield f"data: {json.dumps({'error': str(exc), 'session_id': session_id})}\\n\\n"
