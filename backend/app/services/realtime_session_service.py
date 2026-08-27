"""In-memory realtime ASR session management with TTL cleanup."""

from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.utils.timezone import app_now, to_app_timezone


@dataclass(slots=True)
class RealtimeSession:
    """Realtime ASR session state."""

    id: str
    lesson_id: int
    card_id: int
    model: str
    status: str = "collecting"  # collecting/finalizing/ready/failed
    partial_text: str = ""
    final_text: str = ""
    error: str | None = None
    updated_at: datetime = field(default_factory=app_now)
    chunk_count: int = 0
    total_audio_bytes: int = 0

    def to_api_dict(self) -> dict[str, str | int | None]:
        """Serialize session state for API responses."""
        return {
            "id": self.id,
            "lesson_id": self.lesson_id,
            "card_id": self.card_id,
            "model": self.model,
            "status": self.status,
            "partial_text": self.partial_text,
            "final_text": self.final_text,
            "error": self.error,
            "updated_at": to_app_timezone(self.updated_at).isoformat(),
        }


class RealtimeSessionError(Exception):
    """Realtime session operation error."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class RealtimeSessionStore:
    """Thread-safe in-memory realtime ASR session store with TTL cleanup."""

    def __init__(self, ttl_minutes: int = 15):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, RealtimeSession] = {}
        self._lock = threading.Lock()

    def create_session(self, lesson_id: int, card_id: int, model: str) -> RealtimeSession:
        """Create a realtime session."""
        with self._lock:
            self._cleanup_expired_locked()
            session_id = str(uuid.uuid4())
            session = RealtimeSession(
                id=session_id,
                lesson_id=lesson_id,
                card_id=card_id,
                model=model,
                updated_at=app_now(),
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> RealtimeSession | None:
        """Get session by id."""
        with self._lock:
            self._cleanup_expired_locked()
            return self._sessions.get(session_id)

    def append_audio_chunk(
        self,
        session_id: str,
        chunk_base64: str,
    ) -> RealtimeSession:
        """Append an audio chunk and emit a lightweight partial transcript."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )

            if session.status in {"ready", "failed"}:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_FAILED",
                    message=f"Realtime session {session_id} is already closed",
                    retryable=False,
                )

            try:
                audio_bytes = base64.b64decode(chunk_base64, validate=True)
            except Exception as exc:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_FAILED",
                    message=f"Invalid audio chunk payload: {exc}",
                    retryable=False,
                ) from exc

            session.chunk_count += 1
            session.total_audio_bytes += len(audio_bytes)
            session = self._mark_collecting_locked(session)
            session.partial_text = f"识别中（已接收 {session.chunk_count} 段）"
            return session

    def commit_session(self, session_id: str) -> RealtimeSession:
        """Finalize realtime transcript after recording stops."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )

            if session.chunk_count <= 0 or session.total_audio_bytes <= 0:
                session.status = "failed"
                session.error = "No realtime audio received"
                session.updated_at = app_now()
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_FAILED",
                    message="No realtime audio received",
                    retryable=True,
                )

            session = self._mark_finalizing_locked(session)

            # Keep first version deterministic for tests and frontend gating.
            final_text = (
                session.partial_text.strip()
                or f"实时转写完成（共 {session.chunk_count} 段音频）"
            )
            return self._mark_ready_locked(session, final_text)

    def mark_collecting(self, session_id: str) -> RealtimeSession:
        """Mark session collecting audio."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )
            return self._mark_collecting_locked(session)

    def update_partial_text(self, session_id: str, text: str) -> RealtimeSession:
        """Update partial transcript text."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )
            session = self._mark_collecting_locked(session)
            session.partial_text = text.strip()
            session.updated_at = app_now()
            return session

    def mark_finalizing(self, session_id: str) -> RealtimeSession:
        """Mark session finalizing."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )
            return self._mark_finalizing_locked(session)

    def mark_ready(self, session_id: str, final_text: str) -> RealtimeSession:
        """Mark session ready with final transcript text."""
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise RealtimeSessionError(
                    code="REALTIME_SESSION_NOT_FOUND",
                    message=f"Realtime session {session_id} not found",
                    retryable=True,
                )
            return self._mark_ready_locked(session, final_text)

    def close_session(self, session_id: str) -> None:
        """Mark a session as closed and keep state until TTL cleanup."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session.updated_at = app_now()

    def mark_session_failed(self, session_id: str, error: str) -> None:
        """Mark a session failed."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if session.status != "ready":
                session.status = "failed"
                session.error = error
                session.updated_at = app_now()

    def clear(self) -> None:
        """Clear all sessions (used by tests)."""
        with self._lock:
            self._sessions.clear()

    def _cleanup_expired_locked(self) -> None:
        now = app_now()
        to_delete = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.updated_at > self._ttl
        ]
        for session_id in to_delete:
            self._sessions.pop(session_id, None)

    def _mark_collecting_locked(self, session: RealtimeSession) -> RealtimeSession:
        session.status = "collecting"
        session.updated_at = app_now()
        return session

    def _mark_finalizing_locked(self, session: RealtimeSession) -> RealtimeSession:
        session.status = "finalizing"
        session.updated_at = app_now()
        return session

    def _mark_ready_locked(self, session: RealtimeSession, final_text: str) -> RealtimeSession:
        normalized = final_text.strip()
        if not normalized:
            raise RealtimeSessionError(
                code="REALTIME_TRANSCRIPT_NOT_READY",
                message="Realtime final transcript is empty",
                retryable=True,
            )
        session.final_text = normalized
        session.status = "ready"
        session.error = None
        session.updated_at = app_now()
        return session


_realtime_session_store = RealtimeSessionStore()


def get_realtime_session_store() -> RealtimeSessionStore:
    """Return process-level singleton realtime session store."""
    return _realtime_session_store
