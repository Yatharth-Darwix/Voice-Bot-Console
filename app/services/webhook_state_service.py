"""State-handling helpers for webhook event persistence and session resolution."""

from __future__ import annotations

from typing import Any


def append_if_new(
    *,
    session_store: Any,
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


def clear_model_output_state(
    *,
    session_id: str,
    model_output_accum: dict[tuple[str, str], str],
    model_output_last_persisted: dict[tuple[str, str], str],
) -> None:
    for key in list(model_output_accum.keys()):
        if key[0] == session_id:
            model_output_accum.pop(key, None)
            model_output_last_persisted.pop(key, None)


def extract_session_hint(message: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
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


def resolve_session_id(
    *,
    session_store: Any,
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

    session_hint = extract_session_hint(message, payload)
    if session_hint and session_store.get(session_hint):
        if call_id:
            session_store.bind_call(session_hint, call_id)
        return session_hint

    return None


def persist_server_message(
    *,
    session_store: Any,
    session_id: str,
    event_type: str,
    message: dict[str, Any],
    source: str,
    model_output_accum: dict[tuple[str, str], str],
    model_output_last_persisted: dict[tuple[str, str], str],
    normalize_role: Any,
    extract_text_from_record: Any,
    event_text_from_message: Any,
) -> None:
    transcript = str(message.get("transcript") or "").strip()
    transcript_type = str(message.get("transcriptType") or "").strip().lower()
    is_transcript_event = event_type == "transcript" or event_type.startswith("transcript[")

    if transcript and (is_transcript_event or transcript_type):
        if not transcript_type or transcript_type == "final":
            append_if_new(
                session_store=session_store,
                session_id=session_id,
                role=normalize_role(message.get("role") or "event"),
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
                latest_text = extract_text_from_record(latest)
                if latest_text:
                    append_if_new(
                        session_store=session_store,
                        session_id=session_id,
                        role=normalize_role(latest.get("role")),
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
                merged = f"{model_output_accum.get(key, '')}{token}"
                model_output_accum[key] = merged
                previous_persisted = model_output_last_persisted.get(key, "")
                should_persist = token.endswith((".", "!", "?", ",")) or len(merged) - len(
                    previous_persisted
                ) >= 28
                if should_persist:
                    model_output_last_persisted[key] = merged
                    append_if_new(
                        session_store=session_store,
                        session_id=session_id,
                        role="assistant",
                        text=merged.strip(),
                        source=source,
                        event_type="model-output",
                        metadata=message,
                    )
                    session_store.set_status(session_id, "in_progress")
                return

            append_if_new(
                session_store=session_store,
                session_id=session_id,
                role="assistant",
                text=token.strip(),
                source=source,
                event_type="model-output",
                metadata=message,
            )
            session_store.set_status(session_id, "in_progress")
            return

    event_text = event_text_from_message(message, event_type)
    append_if_new(
        session_store=session_store,
        session_id=session_id,
        role="event",
        text=event_text,
        source=source,
        event_type=event_type,
        metadata=message,
    )
