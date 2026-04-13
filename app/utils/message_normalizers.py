"""Normalization helpers for Vapi and webhook message payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_timestamp(raw: Any) -> str:
    if raw is None:
        return now_iso()

    if isinstance(raw, (int, float)):
        epoch = float(raw)
        if epoch > 10_000_000_000:
            epoch = epoch / 1000.0
        return datetime.fromtimestamp(epoch, UTC).isoformat()

    value = str(raw).strip()
    if not value:
        return now_iso()

    if value.isdigit():
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch = epoch / 1000.0
        return datetime.fromtimestamp(epoch, UTC).isoformat()

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return now_iso()


def normalize_role(raw_role: Any) -> str:
    role = str(raw_role or "").strip().lower()
    if role in {"assistant", "agent", "bot", "ai"}:
        return "assistant"
    if role in {"user", "customer", "client", "caller", "human"}:
        return "user"
    if role == "system":
        return "event"
    return role or "event"


def extract_text_from_record(item: dict[str, Any]) -> str:
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


def event_text_from_message(message: dict[str, Any], event_type: str) -> str:
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


def normalize_vapi_message_dicts(call_payload: dict[str, Any]) -> list[dict[str, Any]]:
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

    normalized: list[dict[str, Any]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue

        role = normalize_role(item.get("role") or item.get("speaker"))
        if role not in {"assistant", "user"}:
            continue
        timestamp = normalize_timestamp(item.get("time") or item.get("timestamp") or item.get("createdAt"))

        text = extract_text_from_record(item)

        if not text:
            continue

        normalized.append(
            {
                "at": timestamp,
                "role": role,
                "text": text,
                "source": str(item.get("source") or "vapi_call_fetch"),
                "event_type": str(item.get("type") or "message"),
                "metadata": item,
            }
        )

    return normalized
