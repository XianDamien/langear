"""Repository for per-user FSRS snapshots."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user_card_fsrs import UserCardFSRS
from app.utils.timezone import to_storage_local

VALID_SRS_STATES = {"learning", "review", "relearning"}


class UserCardFSRSRepository:
    """CRUD helpers for user-specific FSRS state."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get_by_user_card(self, user_id: int, card_id: int) -> UserCardFSRS | None:
        """Return a per-user FSRS snapshot for a card."""
        return (
            self.db.query(UserCardFSRS)
            .filter(
                UserCardFSRS.user_id == user_id,
                UserCardFSRS.card_id == card_id,
            )
            .first()
        )

    def upsert(
        self,
        user_id: int,
        card_id: int,
        state: str,
        step: int | None,
        stability: float | None,
        difficulty: float | None,
        due: datetime,
        last_review: datetime | None,
        last_rating: str | None,
    ) -> UserCardFSRS:
        """Create or update a per-user FSRS snapshot."""
        if state not in VALID_SRS_STATES:
            raise ValueError(f"Unsupported user FSRS state: {state}")

        normalized_step = None if state == "review" else (0 if step is None else step)
        storage_due = to_storage_local(due, self.db)
        storage_last_review = (
            to_storage_local(last_review, self.db)
            if last_review is not None
            else None
        )

        fsrs = self.get_by_user_card(user_id, card_id)
        if fsrs is None:
            fsrs = UserCardFSRS(
                user_id=user_id,
                card_id=card_id,
                state=state,
                step=normalized_step,
                stability=stability,
                difficulty=difficulty,
                due=storage_due,
                last_review=storage_last_review,
                last_rating=last_rating,
            )
            self.db.add(fsrs)
        else:
            fsrs.state = state
            fsrs.step = normalized_step
            fsrs.stability = stability
            fsrs.difficulty = difficulty
            fsrs.due = storage_due
            fsrs.last_review = storage_last_review
            fsrs.last_rating = last_rating

        self.db.flush()
        return fsrs
