"""Session query and message-merging service functions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

_VAPI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
VAPI_CACHE_TTL = 15.0


def to_summary_dict(session: Any) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "mode": session.mode,
        "status": session.status,
        "call_id": session.call_id,
        "industry": session.industry,
        "company": session.company,
        "use_case": session.use_case,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _message_key(message: Any) -> tuple[str, str, str, str]:
    return (
        str(getattr(message, "at", "")),
        str(getattr(message, "role", "")),
        str(getattr(message, "text", "")),
        str(getattr(message, "event_type", "")),
    )


async def enrich_messages_with_vapi(
    *,
    session: Any,
    messages: list[Any],
    fetch_call_details: Callable[[str], Awaitable[dict[str, Any]]],
    normalize_vapi_messages: Callable[[dict[str, Any]], list[Any]],
) -> tuple[list[Any], str | None]:
    vapi_fetch_error: str | None = None

    if not session.call_id:
        return sorted(messages, key=lambda item: str(getattr(item, "at", ""))), vapi_fetch_error

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
        fetched_messages = normalize_vapi_messages(call_payload)
        if fetched_messages:
            existing_keys = {_message_key(msg) for msg in messages}
            for fetched in fetched_messages:
                key = _message_key(fetched)
                if key in existing_keys:
                    continue
                messages.append(fetched)
                existing_keys.add(key)

    return sorted(messages, key=lambda item: str(getattr(item, "at", ""))), vapi_fetch_error
