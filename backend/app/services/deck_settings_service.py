"""Personal settings for a selected course; public deck content stays shared."""

from sqlalchemy.orm import Session

from app.models.deck import Deck
from app.models.user import User
from app.repositories.settings_repo import SettingsRepository
from app.services.my_courses_service import MyCoursesService
from app.services.settings_service import SettingsService

SCHEDULING_KEYS = {"desired_retention", "learning_steps", "relearning_steps", "maximum_interval"}
DECK_SETTING_KEYS = SCHEDULING_KEYS | {"daily_new_limit", "daily_review_limit"}


class DeckSettingsService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsRepository(db)

    @staticmethod
    def key(user_id: int, deck_id: int) -> str:
        return f"deck_settings:{user_id}:{deck_id}"

    def _deck_chain(self, deck_id: int) -> list[Deck]:
        deck = self.db.get(Deck, deck_id)
        if deck is None:
            raise LookupError("Course not found")
        chain = [deck]
        while deck.parent_id is not None:
            deck = self.db.get(Deck, deck.parent_id)
            if deck is None or any(item.id == deck.id for item in chain):
                break
            chain.append(deck)
        return chain

    def _require_selected(self, user_id: int, deck_id: int) -> Deck:
        if self.db.get(User, user_id) is None:
            raise PermissionError("User no longer exists")
        deck = self._deck_chain(deck_id)[0]
        selected = MyCoursesService(self.db).get_lesson_ids(user_id)
        if not any(deck_id in {parent.id for parent in self._deck_chain(lesson_id)} for lesson_id in selected):
            raise LookupError("Course is not in your courses")
        return deck

    def _defaults(self, user_id: int) -> dict:
        personal = SettingsService(self.db).get_settings(user_id)
        return {
            **{key: personal[key] for key in SCHEDULING_KEYS},
            "daily_new_limit": self.settings.get("daily_new_limit") if self.settings.get("daily_new_limit") is not None else 20,
            "daily_review_limit": self.settings.get("daily_review_limit") if self.settings.get("daily_review_limit") is not None else 100,
        }

    def resolve(self, user_id: int, deck_id: int) -> tuple[dict, int | None]:
        """Nearest explicit course settings win; children inherit their parent."""
        defaults = self._defaults(user_id)
        for deck in self._deck_chain(deck_id):
            overrides = self.settings.get(self.key(user_id, deck.id))
            if overrides is not None:
                return {**defaults, **overrides}, deck.id
        return defaults, None

    def get(self, user_id: int, deck_id: int) -> dict:
        deck = self._require_selected(user_id, deck_id)
        values, inherited_from = self.resolve(user_id, deck_id)
        return {**values, "deck_id": deck_id, "deck_title": deck.title, "inherited_from": inherited_from}

    def update(self, user_id: int, deck_id: int, updates: dict) -> dict:
        if set(updates) - DECK_SETTING_KEYS:
            raise ValueError("Unsupported course settings")
        for key in {"daily_new_limit", "daily_review_limit"} & updates.keys():
            if type(updates[key]) is not int or not 0 <= updates[key] <= 10000:
                raise ValueError(f"{key} must be an integer between 0 and 10000")
        if "desired_retention" in updates:
            value = updates["desired_retention"]
            if type(value) not in {int, float} or not 0 < value < 1:
                raise ValueError("desired_retention must be between 0 and 1")
        for key in {"learning_steps", "relearning_steps"} & updates.keys():
            values = updates[key]
            if not isinstance(values, list) or any(type(v) is not int or v <= 0 for v in values):
                raise ValueError(f"{key} must contain positive integers")
        if "maximum_interval" in updates:
            value = updates["maximum_interval"]
            if type(value) is not int or not 0 < value <= 36500:
                raise ValueError("maximum_interval must be between 1 and 36500")
        try:
            # Lock the account even on a first save to serialize JSON inserts.
            if self.db.query(User.id).filter(User.id == user_id).with_for_update().first() is None:
                raise PermissionError("User no longer exists")
            deck = self._require_selected(user_id, deck_id)
            current, _ = self.resolve(user_id, deck_id)
            values = {**current, **updates}
            self.settings.set(self.key(user_id, deck_id), values)
            title = deck.title
            self.db.commit()
            return {**values, "deck_id": deck_id, "deck_title": title, "inherited_from": deck_id}
        except Exception:
            self.db.rollback()
            raise

    def lesson_scope(self, user_id: int, deck_id: int) -> list[int]:
        """Share a quota only among lessons inheriting this exact config."""
        result = []
        for lesson in self.db.query(Deck).filter(Deck.type == "lesson"):
            for parent in self._deck_chain(lesson.id):
                if parent.id == deck_id:
                    result.append(lesson.id)
                    break
                if self.settings.get(self.key(user_id, parent.id)) is not None:
                    break
        return result
