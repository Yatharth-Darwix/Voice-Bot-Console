"""In-memory session store for dashboard observability (v1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SessionRecord:
    session_id: str
    mode: str
    industry: str
    company: str
    use_case: str
    persona: str
    guardrails: str
    status: str
    call_id: str | None = None
    system_prompt: str = ""
    first_message: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    transcript_events: list[dict[str, Any]] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = _now_iso()


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._call_to_session: dict[str, str] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        mode: str,
        industry: str,
        company: str,
        use_case: str,
        persona: str,
        guardrails: str,
        status: str,
    ) -> SessionRecord:
        with self._lock:
            session = SessionRecord(
                session_id=str(uuid4()),
                mode=mode,
                industry=industry,
                company=company,
                use_case=use_case,
                persona=persona,
                guardrails=guardrails,
                status=status,
            )
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self) -> list[SessionRecord]:
        with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda session: session.updated_at,
                reverse=True,
            )

    def set_status(self, session_id: str, status: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session.status = status
            session.touch()

    def attach_prompt(self, session_id: str, system_prompt: str, first_message: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session.system_prompt = system_prompt
            session.first_message = first_message
            session.touch()

    def bind_call(self, session_id: str, call_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session.call_id = call_id
            session.touch()
            self._call_to_session[call_id] = session_id

    def session_id_for_call(self, call_id: str) -> str | None:
        with self._lock:
            return self._call_to_session.get(call_id)

    def append_transcript_event(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        source: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session.transcript_events.append(
                {
                    "at": _now_iso(),
                    "role": role,
                    "text": text,
                    "source": source,
                    "event_type": event_type,
                    "metadata": metadata,
                }
            )
            session.touch()


session_store = SessionStore()
