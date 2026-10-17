"""Per-user lesson selection, independent of imported decks and study history."""

from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.deck import Deck
from app.models.user import User
from app.repositories.settings_repo import SettingsRepository


class MyCoursesService:
    """Store the legacy course picker in the existing JSON settings table."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsRepository(db)

    @staticmethod
    def _key(user_id: int) -> str:
        return f"my_courses:{user_id}:lesson_ids"

    def _require_user(self, user_id: int, *, for_update: bool = False) -> None:
        query = self.db.query(User.id).filter(User.id == user_id)
        if for_update:
            # Serialize replacements for this user, including the first insert
            # when there is no settings row to lock yet.
            query = query.with_for_update()
        if query.first() is None:
            raise LookupError("User no longer exists")

    def _existing_lesson_ids(self, lesson_ids: list[int]) -> list[int]:
        if not lesson_ids:
            return []
        return [
            lesson_id
            for (lesson_id,) in self.db.query(Deck.id)
            .filter(Deck.type == "lesson", Deck.id.in_(lesson_ids))
            .order_by(Deck.id)
            .all()
        ]

    def get_lesson_ids(self, user_id: int) -> list[int]:
        self._require_user(user_id)
        selected = self.settings.get(self._key(user_id)) or []
        # Removed content must not leave unresolvable IDs in the course tree.
        return self._existing_lesson_ids(selected)

    def replace_lesson_ids(self, user_id: int, lesson_ids: list[int]) -> list[int]:
        try:
            self._require_user(user_id, for_update=True)
            selected = sorted(set(lesson_ids))
            # Deck IDs use SQL INTEGER; reject out-of-range IDs before binding
            # them to PostgreSQL, which would otherwise return a server error.
            if any(lesson_id > 2**31 - 1 for lesson_id in selected):
                raise ValueError("Lesson IDs must refer to existing lessons")
            existing = self._existing_lesson_ids(selected)
            if existing != selected:
                invalid = sorted(set(selected) - set(existing))
                raise ValueError(f"Unknown or non-lesson IDs: {invalid}")
            self.settings.set(self._key(user_id), selected)
            self.db.commit()
            return selected
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def card_key(user_id: int, lesson_id: int) -> str:
        return f"my_courses:{user_id}:lesson:{lesson_id}:card_ids"

    def get_card_ids(self, user_id: int, lesson_id: int) -> list[int] | None:
        self._require_user(user_id)
        if lesson_id > 2**31 - 1 or not self._existing_lesson_ids([lesson_id]):
            raise ValueError("Lesson not found")
        # None follows all original cards, including future additions. [] is an
        # explicitly empty scope; it must never fall back to the whole lesson.
        return self.settings.get(self.card_key(user_id, lesson_id))

    def replace_card_ids(self, user_id: int, lesson_id: int, card_ids: list[int] | None) -> dict:
        try:
            self._require_user(user_id, for_update=True)
            self.get_card_ids(user_id, lesson_id)
            selected = sorted(set(card_ids)) if card_ids is not None else None
            if selected is not None:
                if any(card_id > 2**31 - 1 for card_id in selected):
                    raise ValueError("Invalid card IDs")
                existing = {
                    row[0] for row in self.db.query(Card.id).filter(Card.deck_id == lesson_id, Card.id.in_(selected)).all()
                }
                if existing != set(selected):
                    raise ValueError("Cards must belong to the selected lesson")
            self.settings.set(self.card_key(user_id, lesson_id), selected)
            lessons = set(self.get_lesson_ids(user_id))
            if selected == []:
                lessons.discard(lesson_id)
            else:
                lessons.add(lesson_id)
            self.settings.set(self._key(user_id), sorted(lessons))
            self.db.commit()
            return {"card_ids": selected, "lesson_ids": sorted(lessons)}
        except Exception:
            self.db.rollback()
            raise
