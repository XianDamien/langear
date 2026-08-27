"""ADK-backed runtime wrapper for the coach agent."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, AsyncGenerator
import uuid

from app.config import settings


COACH_SYSTEM_INSTRUCTION = """
You are LanGear's lesson coach.

Your job is to answer based on the supplied lesson context, card context,
recent feedback history, FSRS overview, and internal knowledge-base snippets.

Rules:
- Prefer the provided lesson and card context over general language knowledge.
- When explaining, be concrete and tie the answer back to the user's latest
  transcription, current feedback, or lesson history.
- If the context does not support a claim, say so plainly instead of guessing.
- Keep the answer focused on helping the learner improve their English speaking.
- Do not invent extra sources beyond the provided context.
""".strip()


@dataclass
class CoachThreadSummary:
    thread_id: str
    user_id: int
    lesson_id: int | None
    card_id: int | None
    last_update_time: float | None
    message_count: int


class CoachAgentRuntime:
    """Persistent ADK runtime for the lesson Q&A coach."""

    def __init__(self) -> None:
        session_db_path = Path(settings.coach_session_db_path)
        session_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_db_path = session_db_path
        self._session_service = self._create_session_service()

    @staticmethod
    def _import_adk():
        try:
            from google.adk.agents import LlmAgent
            from google.adk.runners import Runner
            from google.adk.sessions.sqlite_session_service import SqliteSessionService
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Coach agent runtime requires google-adk to be installed"
            ) from exc
        return LlmAgent, Runner, SqliteSessionService, types

    def _create_session_service(self):
        _, _, SqliteSessionService, _ = self._import_adk()
        return SqliteSessionService(str(self._session_db_path))

    def _build_agent(self):
        LlmAgent, _, _, _ = self._import_adk()
        api_key = settings.coach_agent_api_key or settings.gemini_api_key
        if api_key:
            os.environ.setdefault("GOOGLE_API_KEY", api_key)
        return LlmAgent(
            name="langear_lesson_coach",
            model=settings.coach_agent_model_id or settings.gemini_model_id,
            instruction=COACH_SYSTEM_INSTRUCTION,
        )

    def _extract_event_text(self, event) -> str:
        content = getattr(event, "content", None)
        if content is None:
            return ""
        parts = getattr(content, "parts", None) or []
        texts = [part.text for part in parts if getattr(part, "text", None)]
        return "".join(texts).strip()

    @staticmethod
    def _normalize_message_text(*, author: str, text: str) -> str:
        if author == "user" and "\n\n上下文 JSON：" in text:
            return text.split("\n\n上下文 JSON：", 1)[0].strip()
        return text

    def _get_or_create_session(
        self,
        *,
        user_id: int,
        lesson_id: int,
        card_id: int | None,
        thread_id: str | None,
    ):
        app_name = settings.coach_agent_app_name
        normalized_user_id = str(user_id)

        if thread_id:
            session = self._session_service.get_session(
                app_name=app_name,
                user_id=normalized_user_id,
                session_id=thread_id,
            )
            if session is None:
                raise ValueError(f"Coach thread {thread_id} not found")

            stored_lesson_id = session.state.get("lesson_id")
            if stored_lesson_id is not None and stored_lesson_id != lesson_id:
                raise ValueError(
                    f"Coach thread {thread_id} belongs to lesson {stored_lesson_id}, not lesson {lesson_id}"
                )
            return session

        return self._session_service.create_session(
            app_name=app_name,
            user_id=normalized_user_id,
            session_id=str(uuid.uuid4()),
            state={
                "lesson_id": lesson_id,
                "card_id": card_id,
            },
        )

    def get_thread(self, *, user_id: int, thread_id: str) -> CoachThreadSummary | None:
        session = self._session_service.get_session(
            app_name=settings.coach_agent_app_name,
            user_id=str(user_id),
            session_id=thread_id,
        )
        if session is None:
            return None

        return CoachThreadSummary(
            thread_id=session.id,
            user_id=int(session.user_id),
            lesson_id=session.state.get("lesson_id"),
            card_id=session.state.get("card_id"),
            last_update_time=session.last_update_time,
            message_count=len(session.events),
        )

    def get_thread_messages(self, *, user_id: int, thread_id: str) -> list[dict[str, Any]]:
        session = self._session_service.get_session(
            app_name=settings.coach_agent_app_name,
            user_id=str(user_id),
            session_id=thread_id,
        )
        if session is None:
            raise ValueError(f"Coach thread {thread_id} not found")

        messages: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for event in session.events:
            if getattr(event, "partial", False):
                continue
            text = self._extract_event_text(event)
            if not text:
                continue
            text = self._normalize_message_text(author=event.author, text=text)
            pair = (event.author, text)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            messages.append(
                {
                    "author": event.author,
                    "content": text,
                    "timestamp": getattr(event, "timestamp", None),
                    "invocation_id": getattr(event, "invocation_id", None),
                }
            )
        return messages

    async def stream_chat(
        self,
        *,
        user_id: int,
        lesson_id: int,
        card_id: int | None,
        thread_id: str | None,
        prompt: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        _, Runner, _, types = self._import_adk()
        session = self._get_or_create_session(
            user_id=user_id,
            lesson_id=lesson_id,
            card_id=card_id,
            thread_id=thread_id,
        )
        runner = Runner(
            app_name=settings.coach_agent_app_name,
            agent=self._build_agent(),
            session_service=self._session_service,
        )

        previous_text = ""
        content = types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )
        async for event in runner.run_async(
            user_id=str(user_id),
            session_id=session.id,
            new_message=content,
        ):
            if getattr(event, "author", "") == "user":
                continue

            text = self._extract_event_text(event)
            if not text:
                continue

            delta = text[len(previous_text):] if text.startswith(previous_text) else text
            previous_text = text
            if delta:
                yield {
                    "type": "message_delta",
                    "thread_id": session.id,
                    "delta": delta,
                }


_runtime_singleton: CoachAgentRuntime | None = None


def get_coach_runtime() -> CoachAgentRuntime:
    """Return a singleton runtime instance for coach chat."""
    global _runtime_singleton
    if _runtime_singleton is None:
        _runtime_singleton = CoachAgentRuntime()
    return _runtime_singleton
