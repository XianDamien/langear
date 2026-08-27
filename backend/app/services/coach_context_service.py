"""Context assembly service for the coach agent."""

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.card_repo import CardRepository
from app.repositories.deck_repo import DeckRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.srs_repo import SRSRepository
from app.utils.timezone import from_storage_local


class CoachContextService:
    """Builds card-, lesson-, and feedback-level context for coach prompts."""

    def __init__(self, db: Session):
        self.db = db
        self.card_repo = CardRepository(db)
        self.deck_repo = DeckRepository(db)
        self.review_log_repo = ReviewLogRepository(db)
        self.srs_repo = SRSRepository(db)

    def _serialize_submission(self, submission) -> dict[str, Any]:
        feedback_json = submission.ai_feedback_json or {}
        transcription = feedback_json.get("transcription") or {}
        feedback = feedback_json.get("feedback") or {}
        return {
            "review_log_id": submission.id,
            "submission_id": submission.id,
            "card_id": submission.card_id,
            "lesson_id": submission.deck_id,
            "status": submission.status,
            "created_at": from_storage_local(submission.created_at, self.db).isoformat(),
            "transcription": transcription,
            "feedback": feedback,
            "oss_audio_path": feedback_json.get("oss_path"),
            "user_transcription_text": transcription.get("text"),
        }

    def _serialize_card(self, card) -> dict[str, Any]:
        return {
            "id": card.id,
            "lesson_id": card.deck_id,
            "card_index": card.card_index,
            "front_text": card.front_text,
            "back_text": card.back_text,
            "audio_path": card.audio_path,
        }

    def _get_lesson(self, lesson_id: int):
        lesson = self.deck_repo.get_by_id(lesson_id)
        if lesson is None or not lesson.is_lesson:
            raise ValueError(f"Lesson {lesson_id} not found")
        return lesson

    def get_current_card_context(
        self,
        user_id: int,
        lesson_id: int,
        card_id: int | None = None,
    ) -> dict[str, Any]:
        """Return the strongest current-card context available for a lesson."""
        lesson = self._get_lesson(lesson_id)

        resolved_card_id = card_id
        if resolved_card_id is None:
            recent_submissions = self.review_log_repo.list_single_submissions(
                user_id=user_id,
                lesson_id=lesson_id,
            )
            if recent_submissions and recent_submissions[0].card_id is not None:
                resolved_card_id = recent_submissions[0].card_id

        card = None
        submissions = []
        if resolved_card_id is not None:
            card = self.card_repo.get_by_id(resolved_card_id)
            if card is None or card.deck_id != lesson_id:
                raise ValueError(f"Card {resolved_card_id} does not belong to lesson {lesson_id}")
            submissions = self.review_log_repo.list_single_submissions(
                user_id=user_id,
                lesson_id=lesson_id,
                card_id=resolved_card_id,
            )

        latest_submission = submissions[0] if submissions else None
        return {
            "lesson": {
                "id": lesson.id,
                "title": lesson.title,
                "source_id": self.deck_repo.get_source_id_for_lesson(lesson.id),
            },
            "card": self._serialize_card(card) if card is not None else None,
            "latest_feedback": self._serialize_submission(latest_submission)
            if latest_submission is not None
            else None,
            "recent_feedbacks": [
                self._serialize_submission(submission) for submission in submissions[:3]
            ],
        }

    def get_lesson_feedback_history(
        self,
        user_id: int,
        lesson_id: int,
        card_id: int | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent lesson feedback history with card metadata."""
        self._get_lesson(lesson_id)
        submissions = self.review_log_repo.list_single_submissions(
            user_id=user_id,
            lesson_id=lesson_id,
            card_id=card_id,
        )[:limit]

        cards_by_id: dict[int, Any] = {}
        result: list[dict[str, Any]] = []
        for submission in submissions:
            item = self._serialize_submission(submission)
            if submission.card_id is not None:
                card = cards_by_id.get(submission.card_id)
                if card is None:
                    card = self.card_repo.get_by_id(submission.card_id)
                    cards_by_id[submission.card_id] = card
                if card is not None:
                    item["card"] = self._serialize_card(card)
            result.append(item)

        return result

    def get_lesson_fsrs_overview(self, user_id: int, lesson_id: int) -> dict[str, Any]:
        """Return a compact lesson-level FSRS overview."""
        _ = user_id
        self._get_lesson(lesson_id)
        total_cards = self.card_repo.count_by_lesson(lesson_id)
        completed_cards = self.srs_repo.count_completed_by_lesson(lesson_id)
        due_cards = self.srs_repo.count_due_by_lesson(lesson_id)
        return {
            "lesson_id": lesson_id,
            "total_cards": total_cards,
            "completed_cards": completed_cards,
            "due_cards": due_cards,
            "new_cards": max(total_cards - completed_cards, 0),
        }

    def get_lesson_progress(self, user_id: int, lesson_id: int) -> dict[str, Any]:
        """Return lesson progress derived from card and FSRS state."""
        overview = self.get_lesson_fsrs_overview(user_id=user_id, lesson_id=lesson_id)
        total_cards = overview["total_cards"] or 0
        completed_cards = overview["completed_cards"] or 0
        return {
            **overview,
            "completion_ratio": 0 if total_cards == 0 else completed_cards / total_cards,
        }

    def get_user_global_patterns(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Return a placeholder user-level pattern list.

        Existing lesson feedback data is not yet partitioned by user in the current
        backend model, so this method intentionally returns a conservative empty
        result until the multi-user learning data refactor lands.
        """
        _ = user_id, limit
        return []
