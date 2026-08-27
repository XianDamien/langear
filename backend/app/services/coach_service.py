"""Service layer for the lesson Q&A coach."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.coach import CoachPreparedChat
from app.services.coach_context_service import CoachContextService
from app.services.coach_kb_service import CoachKnowledgeBaseService
from app.services.coach_runtime import get_coach_runtime


PRONUNCIATION_VIDEO_URL = (
    "https://www.bilibili.com/video/BV1Y4411M7Ac/"
    "?spm_id_from=333.337.search-card.all.click&vd_source=ed38c8a108bdf614c79b6ca89e859e4a"
)


class CoachService:
    """Coordinates business context, retrieval, and ADK chat execution."""

    def __init__(self, db: Session):
        self.db = db
        self.context_service = CoachContextService(db)
        self.kb_service = CoachKnowledgeBaseService()
        self.runtime = get_coach_runtime()

    @staticmethod
    def _collect_issue_tags(current_card_context: dict[str, Any]) -> list[str]:
        latest_feedback = (current_card_context.get("latest_feedback") or {}).get("feedback") or {}
        tags: list[str] = []
        for issue in latest_feedback.get("issues", []):
            for key in ("problem", "suggestion", "target_word", "ipa"):
                value = issue.get(key)
                if isinstance(value, str) and value.strip():
                    tags.append(value.strip())
        return tags

    @staticmethod
    def _is_pronunciation_question(
        *,
        user_message: str,
        current_card_context: dict[str, Any],
        lesson_feedback_history: list[dict[str, Any]],
    ) -> bool:
        message = user_message.lower()
        keywords = ("pronunciation", "发音", "音标", "读音", "连读", "重音", "intonation")
        if any(keyword in message for keyword in keywords):
            return True

        def has_pronunciation_issue(feedback: dict[str, Any]) -> bool:
            issue_text = " ".join(
                issue.get("problem", "")
                for issue in feedback.get("issues", [])
                if isinstance(issue, dict)
            ).lower()
            return any(keyword in issue_text for keyword in keywords)

        latest_feedback = (current_card_context.get("latest_feedback") or {}).get("feedback") or {}
        if has_pronunciation_issue(latest_feedback):
            return True

        return any(
            has_pronunciation_issue(item.get("feedback") or {})
            for item in lesson_feedback_history
        )

    @staticmethod
    def _build_resource_links(
        *,
        user_message: str,
        current_card_context: dict[str, Any],
        lesson_feedback_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not CoachService._is_pronunciation_question(
            user_message=user_message,
            current_card_context=current_card_context,
            lesson_feedback_history=lesson_feedback_history,
        ):
            return []

        return [
            {
                "source_type": "external_resource",
                "url": PRONUNCIATION_VIDEO_URL,
                "reason": "当前问题涉及发音/读音类改进，补充固定跟练视频作为后续练习资源。",
                "target_problem": "pronunciation",
            }
        ]

    @staticmethod
    def _build_jump_targets(
        *,
        current_card_context: dict[str, Any],
        lesson_feedback_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        card = current_card_context.get("card")
        latest_feedback = current_card_context.get("latest_feedback")
        if card and latest_feedback:
            targets.append(
                {
                    "target_type": "card_feedback",
                    "lesson_id": card["lesson_id"],
                    "card_id": card["id"],
                    "review_log_id": latest_feedback["review_log_id"],
                    "submission_id": latest_feedback["submission_id"],
                    "label": f"卡片 {card['card_index']} 最近一次反馈",
                }
            )

        for item in lesson_feedback_history[:3]:
            if item.get("card") is None:
                continue
            targets.append(
                {
                    "target_type": "card_feedback",
                    "lesson_id": item["lesson_id"],
                    "card_id": item["card"]["id"],
                    "review_log_id": item["review_log_id"],
                    "submission_id": item["submission_id"],
                    "label": f"卡片 {item['card']['card_index']} 历史反馈",
                }
            )

        return targets

    @staticmethod
    def _build_citations(
        *,
        current_card_context: dict[str, Any],
        lesson_feedback_history: list[dict[str, Any]],
        kb_hits: list[dict[str, Any]],
        resource_links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        latest_feedback = current_card_context.get("latest_feedback")
        card = current_card_context.get("card")
        if latest_feedback and card:
            citations.append(
                {
                    "source_type": "card_feedback",
                    "lesson_id": card["lesson_id"],
                    "card_id": card["id"],
                    "review_log_id": latest_feedback["review_log_id"],
                    "submission_id": latest_feedback["submission_id"],
                    "excerpt": latest_feedback.get("user_transcription_text"),
                }
            )

        for item in lesson_feedback_history[:3]:
            card = item.get("card")
            citations.append(
                {
                    "source_type": "card_feedback",
                    "lesson_id": item["lesson_id"],
                    "card_id": card["id"] if card else item.get("card_id"),
                    "review_log_id": item["review_log_id"],
                    "submission_id": item["submission_id"],
                    "excerpt": (item.get("transcription") or {}).get("text"),
                }
            )

        citations.extend(kb_hits)
        citations.extend(resource_links)
        return citations

    def prepare_chat(
        self,
        *,
        user_id: int,
        lesson_id: int,
        message: str,
        thread_id: str | None,
        card_id: int | None,
    ) -> CoachPreparedChat:
        """Prepare all context before entering the streaming runtime."""
        current_card_context = self.context_service.get_current_card_context(
            user_id=user_id,
            lesson_id=lesson_id,
            card_id=card_id,
        )
        lesson_feedback_history = self.context_service.get_lesson_feedback_history(
            user_id=user_id,
            lesson_id=lesson_id,
            card_id=card_id,
            limit=settings.coach_history_limit,
        )
        lesson_fsrs_overview = self.context_service.get_lesson_fsrs_overview(
            user_id=user_id,
            lesson_id=lesson_id,
        )
        lesson_progress = self.context_service.get_lesson_progress(
            user_id=user_id,
            lesson_id=lesson_id,
        )
        query = self.kb_service.build_query(
            user_message=message,
            current_card_context=current_card_context,
            lesson_feedback_history=lesson_feedback_history,
        )
        kb_hits = self.kb_service.search(
            query=query,
            tags=self._collect_issue_tags(current_card_context),
            top_k=settings.coach_kb_top_k,
        )
        resource_links = self._build_resource_links(
            user_message=message,
            current_card_context=current_card_context,
            lesson_feedback_history=lesson_feedback_history,
        )
        citations = self._build_citations(
            current_card_context=current_card_context,
            lesson_feedback_history=lesson_feedback_history,
            kb_hits=kb_hits,
            resource_links=resource_links,
        )
        jump_targets = self._build_jump_targets(
            current_card_context=current_card_context,
            lesson_feedback_history=lesson_feedback_history,
        )

        prompt_payload = {
            "user_question": message,
            "current_card_context": current_card_context,
            "lesson_feedback_history": lesson_feedback_history,
            "lesson_fsrs_overview": lesson_fsrs_overview,
            "lesson_progress": lesson_progress,
            "knowledge_hits": kb_hits,
            "resource_links": resource_links,
        }
        prompt = (
            "请基于下面的 lesson 学习上下文，用中文回答用户问题。"
            "回答要优先使用当前卡片、当前 lesson 反馈和知识库片段，避免空泛建议。"
            "\n\n上下文 JSON：\n"
            f"{json.dumps(prompt_payload, ensure_ascii=False)}"
        )

        return CoachPreparedChat(
            user_id=user_id,
            lesson_id=lesson_id,
            card_id=card_id or (current_card_context.get("card") or {}).get("id"),
            thread_id=thread_id,
            prompt=prompt,
            citations=citations,
            jump_targets=jump_targets,
            resource_links=resource_links,
        )

    async def stream_prepared_chat(
        self,
        prepared: CoachPreparedChat,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat deltas, then send structured metadata."""
        resolved_thread_id: str | None = prepared.thread_id
        async for event in self.runtime.stream_chat(
            user_id=prepared.user_id,
            lesson_id=prepared.lesson_id,
            card_id=prepared.card_id,
            thread_id=prepared.thread_id,
            prompt=prepared.prompt,
        ):
            if event["type"] == "message_delta":
                resolved_thread_id = event["thread_id"]
            yield event

        yield {
            "type": "citations",
            "thread_id": resolved_thread_id,
            "items": prepared.citations,
        }
        yield {
            "type": "jump_targets",
            "thread_id": resolved_thread_id,
            "items": prepared.jump_targets,
        }
        yield {
            "type": "resource_links",
            "thread_id": resolved_thread_id,
            "items": prepared.resource_links,
        }
        yield {
            "type": "done",
            "thread_id": resolved_thread_id,
        }

    def get_thread(self, *, user_id: int, thread_id: str) -> dict[str, Any] | None:
        summary = self.runtime.get_thread(user_id=user_id, thread_id=thread_id)
        if summary is None:
            return None
        return {
            "thread_id": summary.thread_id,
            "user_id": summary.user_id,
            "lesson_id": summary.lesson_id,
            "card_id": summary.card_id,
            "last_update_time": summary.last_update_time,
            "message_count": summary.message_count,
        }

    def get_thread_messages(self, *, user_id: int, thread_id: str) -> list[dict[str, Any]]:
        return self.runtime.get_thread_messages(user_id=user_id, thread_id=thread_id)
