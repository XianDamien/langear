"""Study-session scheduling service."""

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.oss_adapter import OSSAdapter
from app.repositories.card_repo import CardRepository
from app.repositories.deck_repo import DeckRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.srs_repo import SRSRepository
from app.utils.timezone import app_now, to_app_timezone, to_storage_local
from app.models.card import Card
from app.repositories.personal_srs_repo import PersonalSRSRepository
from app.services.deck_settings_service import DeckSettingsService


class StudySessionService:
    """Build a scheduled study session from FSRS state and quota rules."""

    def __init__(self, db: Session):
        """Initialize service dependencies."""
        self.db = db
        self.card_repo = CardRepository(db)
        self.deck_repo = DeckRepository(db)
        self.review_log_repo = ReviewLogRepository(db)
        self.settings_repo = SettingsRepository(db)
        self.srs_repo = SRSRepository(db)
        self.oss_adapter = OSSAdapter()

    def get_session(
        self,
        source_scope: list[int] | None = None,
        lesson_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Build the current study session payload."""
        if user_id is not None and lesson_id is not None:
            return self._get_personal_lesson_session(user_id, lesson_id)
        server_time = app_now(self.db)
        business_date = server_time.date()
        as_of = to_storage_local(server_time, self.db)

        effective_scope = self._resolve_effective_scope(source_scope)
        lesson_ids = self._resolve_lesson_ids(effective_scope, lesson_id)

        settings = self.settings_repo.get_all()
        daily_new_limit = settings.get("daily_new_limit", 20)
        daily_review_limit = settings.get("daily_review_limit", 100)

        quota_usage = self.review_log_repo.count_quota_usage_by_date(business_date)
        new_remaining = max(0, daily_new_limit - quota_usage["new"])
        review_remaining = max(0, daily_review_limit - quota_usage["review"])

        due_learning = self.srs_repo.get_due_cards(
            lesson_ids=lesson_ids,
            states=["learning", "relearning"],
            limit=review_remaining,
            as_of=as_of,
        )
        review_slots_left = max(0, review_remaining - len(due_learning))
        due_review = self.srs_repo.get_due_cards(
            lesson_ids=lesson_ids,
            states=["review"],
            limit=review_slots_left,
            as_of=as_of,
        )
        new_cards = self._get_new_cards(
            lesson_ids=lesson_ids,
            limit=new_remaining,
        )
        reviewed_cards = self._get_reviewed_cards(
            lesson_id=lesson_id,
            lesson_ids=lesson_ids,
            active_cards=[*due_learning, *due_review, *new_cards],
            as_of=as_of,
        )

        due_count = self.srs_repo.count_due_cards(lesson_ids=lesson_ids, as_of=as_of)
        latest_oss_paths = self.review_log_repo.get_latest_oss_paths_by_lesson_ids(lesson_ids)

        cards = [
            *[
                self._serialize_card(card, srs, latest_oss_paths.get(card.id), server_time)
                for card, srs in due_learning
            ],
            *[
                self._serialize_card(card, srs, latest_oss_paths.get(card.id), server_time)
                for card, srs in due_review
            ],
            *[
                self._serialize_card(card, srs, latest_oss_paths.get(card.id), server_time)
                for card, srs in new_cards
            ],
            *[
                self._serialize_card(card, srs, latest_oss_paths.get(card.id), server_time)
                for card, srs in reviewed_cards
            ],
        ]

        lesson_name = None
        if lesson_id is not None:
            lesson = self.deck_repo.get_by_id(lesson_id)
            lesson_name = lesson.title if lesson is not None else None

        return {
            "server_time": server_time.isoformat(),
            "session_date": business_date.isoformat(),
            "scope": {
                "source_ids": effective_scope,
                "lesson_id": lesson_id,
            },
            "quota": {
                "daily_new_limit": daily_new_limit,
                "daily_review_limit": daily_review_limit,
                "new_remaining": new_remaining,
                "review_remaining": review_remaining,
            },
            "summary": {
                "new_remaining": new_remaining,
                "review_remaining": review_remaining,
                "due_count": due_count,
            },
            "cards": cards,
            "lesson_name": lesson_name,
        }

    def _get_personal_lesson_session(self, user_id: int, lesson_id: int) -> dict[str, Any]:
        settings_service = DeckSettingsService(self.db)
        settings_service.get(user_id, lesson_id)
        lesson = self.deck_repo.get_by_id(lesson_id)
        if lesson is None or lesson.type != "lesson":
            raise LookupError("Lesson not found")
        configuration, inherited_from = settings_service.resolve(user_id, lesson_id)
        server_time = app_now(self.db)
        as_of = to_storage_local(server_time, self.db)
        quota_lessons = settings_service.lesson_scope(user_id, inherited_from or lesson_id)
        usage = self.review_log_repo.count_quota_usage_by_date(
            server_time.date(), user_id=user_id, lesson_ids=quota_lessons,
        )
        new_remaining = max(0, configuration["daily_new_limit"] - usage["new"])
        review_remaining = max(0, configuration["daily_review_limit"] - usage["review"])
        from app.services.my_courses_service import MyCoursesService
        selected = MyCoursesService(self.db).get_card_ids(user_id, lesson_id)
        query = self.db.query(Card).filter(Card.deck_id == lesson_id)
        if selected is not None:
            query = query.filter(Card.id.in_(selected))
        cards = query.order_by(Card.card_index, Card.id).all()
        states = PersonalSRSRepository(self.db).for_cards(user_id, [card.id for card in cards])
        rows = [(card, states.get(card.id)) for card in cards]
        new = [(card, srs) for card, srs in rows if srs is None or srs.last_review is None]
        due = [(card, srs) for card, srs in rows if srs is not None and srs.last_review is not None and srs.due <= as_of]
        due.sort(key=lambda item: (item[1].state == "review", item[1].due, item[0].id))
        reviewed = [(card, srs) for card, srs in rows if srs is not None and srs.last_review is not None and srs.due > as_of]
        paths = self.review_log_repo.get_latest_oss_paths_by_lesson_ids([lesson_id], user_id=user_id)
        return {
            "server_time": server_time.isoformat(), "session_date": server_time.date().isoformat(),
            "scope": {"source_ids": [self.deck_repo.get_source_id_for_lesson(lesson_id)], "lesson_id": lesson_id},
            "quota": {"daily_new_limit": configuration["daily_new_limit"], "daily_review_limit": configuration["daily_review_limit"], "new_remaining": new_remaining, "review_remaining": review_remaining},
            "summary": {"new_remaining": new_remaining, "review_remaining": review_remaining, "due_count": len(due)},
            "cards": [self._serialize_card(card, srs, paths.get(card.id), server_time) for card, srs in [*due[:review_remaining], *new[:new_remaining], *reviewed]],
            "lesson_name": lesson.title,
        }

    def _resolve_effective_scope(self, requested_scope: list[int] | None) -> list[int]:
        """Resolve effective source scope using request, settings, then all sources."""
        if requested_scope is not None:
            source_ids = self._validated_source_ids(requested_scope)
            if len(source_ids) != len(set(requested_scope)):
                raise ValueError("Invalid source_scope: one or more source decks do not exist")
            return source_ids

        settings = self.settings_repo.get_all()
        default_scope = settings.get("default_source_scope")
        if isinstance(default_scope, list) and default_scope:
            source_ids = self._validated_source_ids(default_scope)
            if source_ids:
                return source_ids

        return [source.id for source in self.deck_repo.get_all_sources()]

    def _validated_source_ids(self, scope_ids: list[int]) -> list[int]:
        """Return de-duplicated valid source IDs preserving request order."""
        deduped_ids: list[int] = []
        seen: set[int] = set()
        for deck_id in scope_ids:
            if deck_id not in seen:
                seen.add(deck_id)
                deduped_ids.append(deck_id)

        valid_sources = self.deck_repo.get_sources_by_ids(deduped_ids)
        valid_source_ids = {source.id for source in valid_sources}
        return [deck_id for deck_id in deduped_ids if deck_id in valid_source_ids]

    def _resolve_lesson_ids(self, source_ids: list[int], lesson_id: int | None) -> list[int]:
        """Resolve lesson IDs from scope and optional lesson restriction."""
        if lesson_id is not None:
            lesson = self.deck_repo.get_by_id(lesson_id)
            if lesson is None or lesson.type != "lesson":
                raise LookupError(f"Lesson {lesson_id} not found")

            lesson_source_id = self.deck_repo.get_source_id_for_lesson(lesson_id)
            if lesson_source_id is None or lesson_source_id not in source_ids:
                return []
            return [lesson_id]

        return self.deck_repo.get_lesson_ids_for_sources(source_ids)

    def _safe_signed_audio_url(self, audio_path: str | None) -> str | None:
        """Sign reference audio URLs without failing the whole session response."""
        if not audio_path:
            return None
        try:
            return self.oss_adapter.generate_signed_url(audio_path, expires=7200)
        except Exception:
            return None

    def _get_new_cards(
        self,
        lesson_ids: list[int],
        limit: int,
    ) -> list[tuple[Any, Any]]:
        """Get cards that remain in the derived new bucket."""
        if not lesson_ids or limit <= 0:
            return []

        return self.card_repo.get_new_cards(
            lesson_ids=lesson_ids,
            limit=limit,
        )

    def _get_reviewed_cards(
        self,
        lesson_id: int | None,
        lesson_ids: list[int],
        active_cards: list[tuple[Any, Any]],
        as_of: Any,
    ) -> list[tuple[Any, Any]]:
        """Keep reviewed lesson cards visible after refresh.

        Global study sessions should continue to show only today's queue. The
        lesson-scoped page is different: users expect the deck view to retain
        cards they just reviewed even after FSRS schedules them into the future.
        """
        if lesson_id is None or not lesson_ids:
            return []

        active_card_ids = [card.id for card, _ in active_cards]
        return self.srs_repo.get_reviewed_cards(
            lesson_ids=lesson_ids,
            exclude_card_ids=active_card_ids,
            as_of=as_of,
        )

    def _serialize_card(
        self,
        card: Any,
        srs: Any,
        latest_oss_path: str | None,
        server_time: Any,
    ) -> dict[str, Any]:
        """Serialize a card row for the study session response."""
        card_state = self.srs_repo.derive_card_state(srs)
        is_new_card = self.srs_repo.is_new_bucket(srs)
        due_at = server_time if is_new_card else to_app_timezone(srs.due, self.db)
        last_review_at = (
            None
            if srs is None or srs.last_review is None
            else to_app_timezone(srs.last_review, self.db)
        )

        return {
            "id": card.id,
            "lesson_id": card.deck_id,
            "card_index": card.card_index,
            "front_text": card.front_text,
            "back_text": card.back_text,
            "audio_path": self._safe_signed_audio_url(card.audio_path),
            "oss_audio_path": latest_oss_path,
            "card_state": card_state,
            "is_new_card": is_new_card,
            "due_at": due_at.isoformat(),
            "last_review_at": None if last_review_at is None else last_review_at.isoformat(),
        }
