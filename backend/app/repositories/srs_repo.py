"""SRS repository for database operations."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.fsrs_review_log import FSRSReviewLog
from app.models.user_card_srs import UserCardSRS
from app.utils.timezone import storage_now, to_storage_local

VALID_SRS_STATES = {"learning", "review", "relearning"}


class SRSRepository:
    """Repository for UserCardSRS model operations."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get_by_card_id(self, card_id: int) -> UserCardSRS | None:
        """Get SRS state for a card.

        Args:
            card_id: Card ID

        Returns:
            UserCardSRS object or None if not exists
        """
        return (
            self.db.query(UserCardSRS)
            .filter(UserCardSRS.card_id == card_id)
            .first()
        )

    def upsert(
        self,
        card_id: int,
        state: str,
        step: int | None,
        stability: float | None,
        difficulty: float | None,
        due: datetime,
        last_review: datetime | None,
    ) -> UserCardSRS:
        """Create or update a native FSRS card snapshot."""
        if state not in VALID_SRS_STATES:
            raise ValueError(f"Unsupported native FSRS state: {state}")

        normalized_step = None if state == "review" else (0 if step is None else step)
        storage_due = to_storage_local(due, self.db)
        storage_last_review = (
            to_storage_local(last_review, self.db)
            if last_review is not None
            else None
        )

        srs = self.get_by_card_id(card_id)

        if srs is None:
            srs = UserCardSRS(
                card_id=card_id,
                state=state,
                step=normalized_step,
                stability=stability,
                difficulty=difficulty,
                due=storage_due,
                last_review=storage_last_review,
            )
            self.db.add(srs)
        else:
            srs.state = state
            srs.step = normalized_step
            srs.stability = stability
            srs.difficulty = difficulty
            srs.due = storage_due
            srs.last_review = storage_last_review

        self.db.flush()
        return srs

    def create_review_log(
        self,
        card_id: int,
        rating: int,
        review_datetime: datetime,
        review_duration: int | None = None,
    ) -> FSRSReviewLog:
        """Persist a native FSRS review-log row."""
        if rating not in {1, 2, 3, 4}:
            raise ValueError(f"Unsupported native FSRS rating: {rating}")

        review_log = FSRSReviewLog(
            card_id=card_id,
            rating=rating,
            review_datetime=to_storage_local(review_datetime, self.db),
            review_duration=review_duration,
        )
        self.db.add(review_log)
        self.db.flush()
        return review_log

    @staticmethod
    def is_new_bucket(srs: UserCardSRS | None) -> bool:
        """Whether a card still belongs to the business new-card bucket."""
        return srs is None or srs.last_review is None

    def derive_card_state(self, srs: UserCardSRS | None) -> str:
        """Return the API-facing native FSRS state without overloading `new`."""
        if srs is None or srs.last_review is None:
            return "learning"
        return srs.state

    def count_due_by_lesson(self, lesson_id: int) -> int:
        """Count cards due for review in a lesson.

        Args:
            lesson_id: Lesson deck ID

        Returns:
            Number of cards due for review
        """
        return self.count_due_cards(lesson_ids=[lesson_id])

    def get_due_cards(
        self,
        lesson_ids: list[int] | None = None,
        states: list[str] | None = None,
        limit: int | None = None,
        as_of=None,
    ) -> list[tuple["Card", UserCardSRS]]:
        """Get due non-new cards joined with their card records."""
        from app.models.card import Card

        now = to_storage_local(as_of, self.db) if as_of is not None else storage_now(self.db)
        query = (
            self.db.query(Card, UserCardSRS)
            .join(UserCardSRS, UserCardSRS.card_id == Card.id)
            .filter(
                UserCardSRS.due <= now,
                UserCardSRS.last_review.isnot(None),
            )
            .order_by(UserCardSRS.due, Card.deck_id, Card.card_index, Card.id)
        )

        if lesson_ids is not None:
            if not lesson_ids:
                return []
            query = query.filter(Card.deck_id.in_(lesson_ids))

        if states is not None:
            if not states:
                return []
            query = query.filter(UserCardSRS.state.in_(states))

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def count_due_cards(
        self,
        lesson_ids: list[int] | None = None,
        states: list[str] | None = None,
        as_of=None,
    ) -> int:
        """Count due cards while excluding pure-new states."""
        from app.models.card import Card

        now = to_storage_local(as_of, self.db) if as_of is not None else storage_now(self.db)
        query = (
            self.db.query(UserCardSRS)
            .join(Card, Card.id == UserCardSRS.card_id)
            .filter(
                UserCardSRS.due <= now,
                UserCardSRS.last_review.isnot(None),
            )
        )

        if lesson_ids is not None:
            if not lesson_ids:
                return 0
            query = query.filter(Card.deck_id.in_(lesson_ids))

        if states is not None:
            if not states:
                return 0
            query = query.filter(UserCardSRS.state.in_(states))

        return query.count()

    def count_completed_by_lesson(self, lesson_id: int) -> int:
        """Count cards that have been reviewed at least once.

        Args:
            lesson_id: Lesson deck ID

        Returns:
            Number of cards with SRS state (reviewed at least once)
        """
        from app.models.card import Card

        return (
            self.db.query(UserCardSRS)
            .join(Card, Card.id == UserCardSRS.card_id)
            .filter(
                Card.deck_id == lesson_id,
                UserCardSRS.last_review.isnot(None),
            )
            .count()
        )

    def get_reviewed_cards(
        self,
        lesson_ids: list[int] | None = None,
        states: list[str] | None = None,
        exclude_card_ids: list[int] | None = None,
        limit: int | None = None,
        as_of=None,
    ) -> list[tuple["Card", UserCardSRS]]:
        """Get reviewed cards that are scheduled in the future.

        These cards are not due yet, but lesson-scoped study pages still need
        them so a refresh does not make already-reviewed cards disappear.
        """
        from app.models.card import Card

        now = to_storage_local(as_of, self.db) if as_of is not None else storage_now(self.db)
        query = (
            self.db.query(Card, UserCardSRS)
            .join(UserCardSRS, UserCardSRS.card_id == Card.id)
            .filter(
                UserCardSRS.due > now,
                UserCardSRS.last_review.isnot(None),
            )
            .order_by(UserCardSRS.due, Card.deck_id, Card.card_index, Card.id)
        )

        if lesson_ids is not None:
            if not lesson_ids:
                return []
            query = query.filter(Card.deck_id.in_(lesson_ids))

        if states is not None:
            if not states:
                return []
            query = query.filter(UserCardSRS.state.in_(states))

        if exclude_card_ids:
            query = query.filter(~Card.id.in_(exclude_card_ids))

        if limit is not None:
            query = query.limit(limit)

        return query.all()
