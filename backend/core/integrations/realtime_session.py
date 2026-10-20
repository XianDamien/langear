"""In-memory realtime ASR session state with TTL cleanup.

The store is transient: only a stream that is still alive in this process can
be queried. Durable transcripts are persisted on the Attempt snapshot instead.
"""

import base64
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class RealtimeSession:
    id: str
    deck_id: uuid.UUID
    card_id: uuid.UUID
    owner: int
    model: str
    status: str = "collecting"
    partial_text: str = ""
    final_text: str = ""
    error: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    chunk_count: int = 0
    total_audio_bytes: int = 0

    def to_api_dict(self) -> dict:
        return {
            "id": self.id,
            "deck_id": str(self.deck_id),
            "card_id": str(self.card_id),
            "model": self.model,
            "status": self.status,
            "partial_text": self.partial_text,
            "final_text": self.final_text,
            "error": self.error,
            "updated_at": self.updated_at.isoformat(),
        }


class RealtimeSessionError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


class RealtimeSessionStore:
    """Thread-safe store; every stream is bound to one Collection and Card."""

    def __init__(self, ttl_minutes: int = 15):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, RealtimeSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now():
        return datetime.now(UTC)

    def create_session(self, deck_id, card_id, owner, model) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            session = RealtimeSession(
                id=str(uuid.uuid4()),
                deck_id=deck_id,
                card_id=card_id,
                owner=owner,
                model=model,
                updated_at=self._now(),
            )
            self._sessions[session.id] = session
            return session

    def get_session(self, session_id: str) -> RealtimeSession | None:
        with self._lock:
            self._cleanup_expired_locked()
            return self._sessions.get(session_id)

    def owned_session(self, session_id: str, owner: int) -> RealtimeSession | None:
        session = self.get_session(session_id)
        return session if session is not None and session.owner == owner else None

    def append_audio_chunk(self, session_id: str, chunk_base64: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            session = self._session(session_id)
            if session.status in {"ready", "failed"}:
                raise RealtimeSessionError(
                    "REALTIME_SESSION_FAILED",
                    "This realtime session is already closed",
                    retryable=False,
                )
            try:
                audio = base64.b64decode(chunk_base64, validate=True)
            except Exception:
                raise RealtimeSessionError(
                    "REALTIME_SESSION_FAILED", "Invalid audio chunk", retryable=False
                ) from None
            session.chunk_count += 1
            session.total_audio_bytes += len(audio)
            return self._mark_collecting_locked(session)

    def commit_session(self, session_id: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            session = self._session(session_id)
            if session.chunk_count <= 0 or session.total_audio_bytes <= 0:
                session.status, session.error = "failed", "No realtime audio received"
                session.updated_at = self._now()
                raise RealtimeSessionError(
                    "REALTIME_SESSION_FAILED", "No realtime audio received", retryable=True
                )
            self._mark_finalizing_locked(session)
            return self._mark_ready_locked(
                session,
                session.partial_text.strip()
                or f"实时转写完成（共 {session.chunk_count} 段音频）",
            )

    def mark_collecting(self, session_id: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            return self._mark_collecting_locked(self._session(session_id))

    def update_partial_text(self, session_id: str, text: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            session = self._mark_collecting_locked(self._session(session_id))
            session.partial_text = text.strip()
            session.updated_at = self._now()
            return session

    def mark_finalizing(self, session_id: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            return self._mark_finalizing_locked(self._session(session_id))

    def mark_ready(self, session_id: str, final_text: str) -> RealtimeSession:
        with self._lock:
            self._cleanup_expired_locked()
            return self._mark_ready_locked(self._session(session_id), final_text)

    def close_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.updated_at = self._now()

    def mark_session_failed(self, session_id: str, error: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.status != "ready":
                session.status, session.error = "failed", error
                session.updated_at = self._now()

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _session(self, session_id) -> RealtimeSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise RealtimeSessionError(
                "REALTIME_SESSION_NOT_FOUND",
                "Realtime session not found or expired",
                retryable=True,
            )
        return session

    def _cleanup_expired_locked(self) -> None:
        now = self._now()
        for session_id in [
            key
            for key, session in self._sessions.items()
            if now - session.updated_at > self._ttl
        ]:
            self._sessions.pop(session_id, None)

    def _mark_collecting_locked(self, session: RealtimeSession) -> RealtimeSession:
        session.status, session.updated_at = "collecting", self._now()
        return session

    def _mark_finalizing_locked(self, session: RealtimeSession) -> RealtimeSession:
        session.status, session.updated_at = "finalizing", self._now()
        return session

    def _mark_ready_locked(
        self, session: RealtimeSession, final_text: str
    ) -> RealtimeSession:
        normalized = final_text.strip()
        if not normalized:
            raise RealtimeSessionError(
                "REALTIME_TRANSCRIPT_NOT_READY",
                "Realtime final transcript is empty",
                retryable=True,
            )
        session.final_text, session.status, session.error = (
            normalized,
            "ready",
            None,
        )
        session.updated_at = self._now()
        return session


_store = RealtimeSessionStore()


def get_store() -> RealtimeSessionStore:
    return _store
