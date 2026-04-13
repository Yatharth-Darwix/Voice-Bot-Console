"""Small reusable helpers for API router modules."""

from __future__ import annotations

from collections import deque
from time import monotonic
from typing import Any

from fastapi import HTTPException, Request


def get_voice_id_for_gender(
    gender: str,
    *,
    male_voice_id: str | None,
    female_voice_id: str | None,
) -> str | None:
    normalized = gender.lower().strip()
    if normalized == "male":
        return male_voice_id
    if normalized == "female":
        return female_voice_id
    return None


def enforce_rate_limit(
    *,
    request: Request,
    request_buckets: dict[str, deque[float]],
    window_seconds: float,
    rate_limit_per_minute: int,
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    bucket = request_buckets[client_ip]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry shortly.")

    bucket.append(now)


def extract_call_id(message: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
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
