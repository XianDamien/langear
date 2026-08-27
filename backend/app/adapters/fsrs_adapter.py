"""Native FSRS adapter aligned with the upstream py-fsrs contract."""

from datetime import datetime
from typing import Any

from fsrs import Card as FSRSCard
from fsrs import Rating, ReviewLog as FSRSReviewLog, Scheduler, State

from app.exceptions import InvalidRatingError, SRSUpdateError
from app.models.user_card_srs import UserCardSRS
from app.utils.timezone import app_now, from_storage_local, to_utc


STATE_TO_STRING = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}
STRING_TO_STATE = {value: key for key, value in STATE_TO_STRING.items()}


class FSRSAdapter:
    """Bridge between persisted SQL rows and native py-fsrs objects."""

    def __init__(self):
        """Initialize FSRS scheduler with default parameters."""
        self.scheduler = Scheduler()

    def rating_from_string(self, rating_str: str) -> Rating:
        """Convert rating string to FSRS Rating enum.

        Args:
            rating_str: One of 'again', 'hard', 'good', 'easy'

        Returns:
            FSRS Rating enum value

        Raises:
            InvalidRatingError: If rating string is invalid
        """
        mapping = {
            "again": Rating.Again,
            "hard": Rating.Hard,
            "good": Rating.Good,
            "easy": Rating.Easy,
        }
        if rating_str not in mapping:
            raise InvalidRatingError()
        return mapping[rating_str]

    def state_to_string(self, state: State) -> str:
        """Convert FSRS State enum to the persisted string value."""
        return STATE_TO_STRING[state]

    def string_to_state(self, state_str: str) -> State:
        """Convert persisted state string to FSRS State enum."""
        try:
            return STRING_TO_STATE[state_str]
        except KeyError as exc:
            raise SRSUpdateError(f"Unsupported FSRS state: {state_str}") from exc

    def to_fsrs_card(
        self,
        current_srs: UserCardSRS | None,
        *,
        card_id: int | None = None,
    ) -> FSRSCard:
        """Convert a stored `user_card_srs` row to a native FSRS Card."""
        if current_srs is None:
            if card_id is None:
                raise SRSUpdateError("card_id is required when scheduling a card without SRS row")
            return FSRSCard(card_id=card_id)

        return FSRSCard(
            card_id=current_srs.card_id,
            state=self.string_to_state(current_srs.state),
            step=current_srs.step,
            stability=current_srs.stability,
            difficulty=current_srs.difficulty,
            due=to_utc(current_srs.due),
            last_review=to_utc(current_srs.last_review) if current_srs.last_review is not None else None,
        )

    def serialize_card(self, card: FSRSCard) -> dict[str, Any]:
        """Serialize a native FSRS Card for persistence."""
        return {
            "card_id": card.card_id,
            "state": self.state_to_string(card.state),
            "step": card.step,
            "stability": card.stability,
            "difficulty": card.difficulty,
            "due": to_utc(card.due),
            "last_review": to_utc(card.last_review) if card.last_review is not None else None,
        }

    def serialize_review_log(self, review_log: FSRSReviewLog) -> dict[str, Any]:
        """Serialize a native FSRS ReviewLog for persistence."""
        return {
            "card_id": review_log.card_id,
            "rating": int(review_log.rating),
            "review_datetime": to_utc(review_log.review_datetime),
            "review_duration": review_log.review_duration,
        }

    def schedule_card(
        self,
        current_srs: UserCardSRS | None,
        rating_str: str,
        *,
        card_id: int | None = None,
        review_datetime: datetime | None = None,
        review_duration: int | None = None,
    ) -> dict[str, Any]:
        """Review a card through native py-fsrs and return card + review-log payloads."""
        try:
            rating = self.rating_from_string(rating_str)
            review_at = to_utc(app_now()) if review_datetime is None else to_utc(review_datetime)
            fsrs_card = self.to_fsrs_card(current_srs, card_id=card_id)
            updated_card, review_log = self.scheduler.review_card(
                fsrs_card,
                rating,
                review_datetime=review_at,
                review_duration=review_duration,
            )

            result = self.serialize_card(updated_card)
            result["review_log"] = self.serialize_review_log(review_log)
            return result
        except InvalidRatingError:
            raise
        except Exception as exc:
            raise SRSUpdateError(f"FSRS scheduling failed: {exc}") from exc
