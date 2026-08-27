"""Card repository for database operations."""

from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.user_card_srs import UserCardSRS


class CardRepository:
    """Repository for Card model operations."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get_by_id(self, card_id: int) -> Card | None:
        """Get card by ID.

        Args:
            card_id: Card ID

        Returns:
            Card object or None if not found
        """
        return self.db.query(Card).filter(Card.id == card_id).first()

    def get_by_lesson(self, lesson_id: int) -> list[Card]:
        """Get all cards in a lesson.

        Args:
            lesson_id: Lesson deck ID

        Returns:
            List of Card objects ordered by card_index
        """
        return (
            self.db.query(Card)
            .filter(Card.deck_id == lesson_id)
            .order_by(Card.card_index)
            .all()
        )

    def create(
        self,
        deck_id: int,
        card_index: int,
        front_text: str,
        back_text: str | None = None,
        audio_path: str | None = None,
    ) -> Card:
        """Create a new card.

        Args:
            deck_id: Lesson deck ID
            card_index: Card order within lesson
            front_text: English text
            back_text: Chinese translation (optional)
            audio_path: OSS URL for audio (optional)

        Returns:
            Created Card object
        """
        card = Card(
            deck_id=deck_id,
            card_index=card_index,
            front_text=front_text,
            back_text=back_text,
            audio_path=audio_path,
        )
        self.db.add(card)
        self.db.flush()
        return card

    def count_by_lesson(self, lesson_id: int) -> int:
        """Count total cards in a lesson.

        Args:
            lesson_id: Lesson deck ID

        Returns:
            Total number of cards
        """
        return self.db.query(Card).filter(Card.deck_id == lesson_id).count()

    def get_new_cards(
        self,
        lesson_ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[tuple[Card, UserCardSRS | None]]:
        """Get cards that are still in the new bucket."""
        query = (
            self.db.query(Card, UserCardSRS)
            .join(UserCardSRS, UserCardSRS.card_id == Card.id)
            .filter(UserCardSRS.last_review.is_(None))
            .order_by(Card.deck_id, Card.card_index, Card.id)
        )

        if lesson_ids is not None:
            if not lesson_ids:
                return []
            query = query.filter(Card.deck_id.in_(lesson_ids))

        if limit is not None:
            query = query.limit(limit)

        return query.all()
