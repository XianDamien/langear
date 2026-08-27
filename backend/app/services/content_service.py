"""Content service for deck tree and card queries."""

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.oss_adapter import OSSAdapter
from app.repositories.card_repo import CardRepository
from app.repositories.deck_repo import DeckRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.srs_repo import SRSRepository
from app.utils.timezone import app_now, to_app_timezone


class ContentService:
    """Service for querying educational content (decks and cards)."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.deck_repo = DeckRepository(db)
        self.card_repo = CardRepository(db)
        self.srs_repo = SRSRepository(db)
        self.review_log_repo = ReviewLogRepository(db)
        self.oss_adapter = OSSAdapter()

    def _build_lesson_node(self, lesson_id: int, lesson_title: str) -> dict[str, Any]:
        total_cards = self.card_repo.count_by_lesson(lesson_id)
        completed_cards = self.srs_repo.count_completed_by_lesson(lesson_id)
        due_cards = self.srs_repo.count_due_by_lesson(lesson_id)
        new_cards = max(0, total_cards - completed_cards)

        return {
            "id": lesson_id,
            "title": lesson_title,
            "total_cards": total_cards,
            "completed_cards": completed_cards,
            "due_cards": due_cards,
            "new_cards": new_cards,
        }

    def _build_unit_node(self, unit_id: int, unit_title: str) -> dict[str, Any]:
        lessons = self.deck_repo.get_children(unit_id)
        lesson_nodes = [
            self._build_lesson_node(lesson.id, lesson.title)
            for lesson in lessons
        ]

        return {
            "id": unit_id,
            "title": unit_title,
            "lessons": lesson_nodes,
        }

    def _safe_signed_audio_url(self, audio_path: str | None) -> str | None:
        if not audio_path:
            return None

        try:
            return self.oss_adapter.generate_signed_url(audio_path, expires=7200)
        except Exception:
            return None

    def _get_lesson_srs_map(self, lesson_id: int) -> dict[int, Any]:
        """Get lesson SRS rows keyed by card_id."""
        from app.models.card import Card
        from app.models.user_card_srs import UserCardSRS

        rows = (
            self.db.query(UserCardSRS)
            .join(Card, Card.id == UserCardSRS.card_id)
            .filter(Card.deck_id == lesson_id)
            .all()
        )
        return {row.card_id: row for row in rows}

    def get_deck_tree(self) -> dict[str, Any]:
        """Get the complete deck tree: sources -> units -> lessons.

        Returns:
            Dictionary with:
            - sources: List of source decks with nested units and lessons
                Each lesson includes: total_cards, completed_cards, due_cards, new_cards

        Example:
            {
                "sources": [
                    {
                        "id": 1,
                        "title": "New Concept English Book 2",
                        "units": [
                            {
                                "id": 11,
                                "title": "Unit 1",
                                "lessons": [
                                    {
                                        "id": 111,
                                        "title": "Lesson 1",
                                        "total_cards": 24,
                                        "completed_cards": 8,
                                        "due_cards": 5,
                                        "new_cards": 16
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        """
        sources = self.deck_repo.get_all_sources()

        result_sources = []
        for source in sources:
            units = self.deck_repo.get_children(source.id)
            unit_nodes = [
                self._build_unit_node(unit.id, unit.title)
                for unit in units
            ]

            result_sources.append(
                {
                    "id": source.id,
                    "title": source.title,
                    "units": unit_nodes,
                }
            )

        return {"sources": result_sources}

    def get_lesson_cards(self, lesson_id: int) -> dict[str, Any]:
        """Get all cards in a lesson (ordered by card_index).

        Args:
            lesson_id: Lesson deck ID

        Returns:
            Dictionary with:
            - lesson_id: Lesson ID
            - cards: List of card objects with id, card_index, front_text, back_text, audio_path

        Raises:
            ValueError: If lesson not found
        """
        # Verify lesson exists
        lesson = self.deck_repo.get_by_id(lesson_id)
        if not lesson or lesson.type != "lesson":
            raise ValueError(f"Lesson {lesson_id} not found")

        # Get all cards ordered by card_index
        cards = self.card_repo.get_by_lesson(lesson_id)
        srs_map = self._get_lesson_srs_map(lesson_id)
        server_time = app_now(self.db)

        # Get latest user recording OSS paths per card
        oss_paths = self.review_log_repo.get_latest_oss_paths_by_lesson(lesson_id)

        result_cards = []
        for card in cards:
            srs = srs_map.get(card.id)
            card_state = self.srs_repo.derive_card_state(srs)
            is_new_card = self.srs_repo.is_new_bucket(srs)
            due_at = server_time if is_new_card else to_app_timezone(srs.due, self.db)
            last_review_at = (
                None
                if srs is None or srs.last_review is None
                else to_app_timezone(srs.last_review, self.db)
            )
            result_cards.append(
                {
                    "id": card.id,
                    "card_index": card.card_index,
                    "front_text": card.front_text,
                    "back_text": card.back_text,
                    "audio_path": self._safe_signed_audio_url(card.audio_path),
                    "oss_audio_path": oss_paths.get(card.id),
                    "card_state": card_state,
                    "is_new_card": is_new_card,
                    "due_at": due_at.isoformat(),
                    "last_review_at": None if last_review_at is None else last_review_at.isoformat(),
                }
            )

        return {
            "lesson_id": lesson_id,
            "cards": result_cards,
        }
