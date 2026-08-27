"""Study-session scheduling service."""

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.oss_adapter import OSSAdapter
from app.repositories.card_repo import CardRepository
from app.repositories.deck_repo import DeckRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.srs_repo import SRSRepository
from app.repositories.user_deck_repo import UserDeckRepository
from app.utils.timezone import app_now, to_app_timezone, to_storage_local


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
        self.user_deck_repo = UserDeckRepository(db)
        self.oss_adapter = OSSAdapter()

    def get_session(
        self,
        user_id: int,
        source_scope: list[int] | None = None,
        lesson_id: int | None = None,
        user_deck_id: int | None = None,
    ) -> dict[str, Any]:
        """Build the current study session payload."""
        if lesson_id is not None and user_deck_id is not None:
            raise ValueError("lesson_id and user_deck_id cannot be combined")

        server_time = app_now(self.db)
        business_date = server_time.date()
        as_of = to_storage_local(server_time, self.db)
        quota_usage = self.review_log_repo.count_quota_usage_by_date(
            business_date,
            user_id=user_id,
        )

        settings = self.settings_repo.get_all()
        daily_new_limit = settings.get("daily_new_limit", 20)
        daily_review_limit = settings.get("daily_review_limit", 100)
        new_remaining = max(0, daily_new_limit - quota_usage["new"])
        review_remaining = max(0, daily_review_limit - quota_usage["review"])

        if user_deck_id is not None:
            return self._get_user_deck_session(
                user_id=user_id,
                user_deck_id=user_deck_id,
                server_time=server_time,
                as_of=as_of,
                daily_new_limit=daily_new_limit,
                daily_review_limit=daily_review_limit,
                new_remaining=new_remaining,
                review_remaining=review_remaining,
            )

        effective_scope = self._resolve_effective_scope(source_scope)
        lesson_ids = self._resolve_lesson_ids(effective_scope, lesson_id)

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
        latest_oss_paths = self.review_log_repo.get_latest_oss_paths_by_lesson_ids(
            lesson_ids,
            user_id=user_id,
        )

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
                "user_deck_id": None,
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

    def _get_user_deck_session(
        self,
        user_id: int,
        user_deck_id: int,
        server_time: Any,
        as_of: Any,
        daily_new_limit: int,
        daily_review_limit: int,
        new_remaining: int,
        review_remaining: int,
    ) -> dict[str, Any]:
        """Build a session for a user-owned active study deck."""
        user_deck = self.user_deck_repo.get_active_by_id(user_id, user_deck_id)
        if user_deck is None:
            raise LookupError(f"User deck {user_deck_id} not found")

        deck_rows = self.user_deck_repo.list_cards_with_fsrs(user_id, user_deck_id)
        due_learning_all = [
            (card, fsrs)
            for _, card, fsrs in deck_rows
            if self._is_due_non_new(fsrs, as_of) and fsrs.state in {"learning", "relearning"}
        ]
        due_learning = due_learning_all[:review_remaining]
        review_slots_left = max(0, review_remaining - len(due_learning))

        due_review_all = [
            (card, fsrs)
            for _, card, fsrs in deck_rows
            if self._is_due_non_new(fsrs, as_of) and fsrs.state == "review"
        ]
        due_review = due_review_all[:review_slots_left]
        active_card_ids = {card.id for card, _ in [*due_learning, *due_review]}

        new_cards_all = [
            (card, fsrs)
            for _, card, fsrs in deck_rows
            if self._is_new_bucket(fsrs)
            and card.id not in active_card_ids
        ]
        new_cards = new_cards_all[:new_remaining]
        active_card_ids.update(card.id for card, _ in new_cards)

        reviewed_cards = [
            (card, fsrs)
            for _, card, fsrs in deck_rows
            if fsrs is not None
            and fsrs.last_review is not None
            and fsrs.due > as_of
            and card.id not in active_card_ids
        ]

        due_count = sum(
            1
            for _, _, fsrs in deck_rows
            if self._is_due_non_new(fsrs, as_of)
        )
        latest_oss_paths = self.review_log_repo.get_latest_oss_paths_by_card_ids(
            [card.id for _, card, _ in deck_rows],
            user_id=user_id,
            user_deck_id=user_deck_id,
        )

        cards = [
            *[
                self._serialize_card(card, fsrs, latest_oss_paths.get(card.id), server_time)
                for card, fsrs in due_learning
            ],
            *[
                self._serialize_card(card, fsrs, latest_oss_paths.get(card.id), server_time)
                for card, fsrs in due_review
            ],
            *[
                self._serialize_card(card, fsrs, latest_oss_paths.get(card.id), server_time)
                for card, fsrs in new_cards
            ],
            *[
                self._serialize_card(card, fsrs, latest_oss_paths.get(card.id), server_time)
                for card, fsrs in reviewed_cards
            ],
        ]

        return {
            "server_time": server_time.isoformat(),
            "session_date": server_time.date().isoformat(),
            "scope": {
                "source_ids": [],
                "lesson_id": None,
                "user_deck_id": user_deck_id,
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
            "lesson_name": user_deck.title_snapshot,
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

    @staticmethod
    def _is_new_bucket(srs: Any) -> bool:
        """Whether a card is still new for the active session mode."""
        return srs is None or srs.last_review is None

    def _derive_card_state(self, srs: Any) -> str:
        """Return the API-facing native FSRS state without exposing a synthetic new state."""
        if self._is_new_bucket(srs):
            return "learning"
        return srs.state

    def _is_due_non_new(self, srs: Any, as_of: Any) -> bool:
        """Whether a non-new card is due at the provided timestamp."""
        return (
            srs is not None
            and srs.last_review is not None
            and srs.due <= as_of
        )

    def _serialize_card(
        self,
        card: Any,
        srs: Any,
        latest_oss_path: str | None,
        server_time: Any,
    ) -> dict[str, Any]:
        """Serialize a card row for the study session response."""
        card_state = self._derive_card_state(srs)
        is_new_card = self._is_new_bucket(srs)
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
