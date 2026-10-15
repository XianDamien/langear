"""Repository operations for user-owned study decks."""

from datetime import datetime

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, aliased

from app.models.card import Card
from app.models.deck import Deck
from app.models.user import User
from app.models.user_card_fsrs import UserCardFSRS
from app.models.user_deck import UserDeck
from app.models.user_deck_card import UserDeckCard


class UserDeckRepository:
    """Repository for user deck import and summary queries."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def ensure_user(self, user_id: int) -> User:
        """Return an existing user or create the MVP default user row."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if user is not None:
            return user

        user = User(id=user_id, username=f"user-{user_id}")
        self.db.add(user)
        self.db.flush()
        return user

    def get_origin_deck(self, origin_deck_id: int) -> Deck | None:
        """Return the public source/unit/lesson deck by id."""
        return self.db.query(Deck).filter(Deck.id == origin_deck_id).first()

    def get_by_user_origin(self, user_id: int, origin_deck_id: int) -> UserDeck | None:
        """Return an imported user deck for a public origin deck."""
        return (
            self.db.query(UserDeck)
            .filter(
                UserDeck.user_id == user_id,
                UserDeck.origin_deck_id == origin_deck_id,
            )
            .first()
        )

    def list_for_user(self, user_id: int) -> list[UserDeck]:
        """List imported user decks in stable creation order."""
        return (
            self.db.query(UserDeck)
            .filter(UserDeck.user_id == user_id)
            .order_by(UserDeck.created_at, UserDeck.id)
            .all()
        )

    def get_cards_for_origin(self, origin_deck: Deck) -> list[Card]:
        """Return cards covered by a source, unit, or lesson deck."""
        if origin_deck.type == "lesson":
            lesson_ids = [origin_deck.id]
        elif origin_deck.type == "unit":
            lesson_ids = [
                deck_id
                for (deck_id,) in (
                    self.db.query(Deck.id)
                    .filter(Deck.parent_id == origin_deck.id, Deck.type == "lesson")
                    .order_by(Deck.level_index, Deck.id)
                    .all()
                )
            ]
        elif origin_deck.type == "source":
            unit = aliased(Deck)
            lesson = aliased(Deck)
            lesson_ids = [
                deck_id
                for (deck_id,) in (
                    self.db.query(lesson.id)
                    .join(unit, lesson.parent_id == unit.id)
                    .filter(
                        unit.parent_id == origin_deck.id,
                        unit.type == "unit",
                        lesson.type == "lesson",
                    )
                    .order_by(unit.level_index, lesson.level_index, lesson.id)
                    .all()
                )
            ]
        else:
            return []

        if not lesson_ids:
            return []

        return (
            self.db.query(Card)
            .join(Deck, Deck.id == Card.deck_id)
            .filter(Card.deck_id.in_(lesson_ids))
            .order_by(Deck.level_index, Card.deck_id, Card.card_index, Card.id)
            .all()
        )

    def create_import(self, user_id: int, origin_deck: Deck, cards: list[Card]) -> UserDeck:
        """Create a user deck and stable card membership rows."""
        user_deck = UserDeck(
            user_id=user_id,
            origin_deck_id=origin_deck.id,
            scope_type=origin_deck.type,
            title_snapshot=origin_deck.title,
        )
        self.db.add(user_deck)
        self.db.flush()

        for index, card in enumerate(cards, start=1):
            self.db.add(
                UserDeckCard(
                    user_deck_id=user_deck.id,
                    card_id=card.id,
                    new_position=index,
                )
            )

        self.db.flush()
        return user_deck

    def summarize(self, user_deck: UserDeck, as_of: datetime) -> dict[str, int | str]:
        """Return counts for a single user deck."""
        total_count = (
            self.db.query(func.count(UserDeckCard.card_id))
            .filter(UserDeckCard.user_deck_id == user_deck.id)
            .scalar()
            or 0
        )

        fsrs_join = and_(
            UserCardFSRS.user_id == user_deck.user_id,
            UserCardFSRS.card_id == UserDeckCard.card_id,
        )

        new_count = (
            self.db.query(func.count(UserDeckCard.card_id))
            .outerjoin(UserCardFSRS, fsrs_join)
            .filter(
                UserDeckCard.user_deck_id == user_deck.id,
                UserCardFSRS.card_id.is_(None),
            )
            .scalar()
            or 0
        )

        learning_count = (
            self.db.query(func.count(UserDeckCard.card_id))
            .join(UserCardFSRS, fsrs_join)
            .filter(
                UserDeckCard.user_deck_id == user_deck.id,
                UserCardFSRS.state.in_(["learning", "relearning"]),
            )
            .scalar()
            or 0
        )

        review_count = (
            self.db.query(func.count(UserDeckCard.card_id))
            .join(UserCardFSRS, fsrs_join)
            .filter(
                UserDeckCard.user_deck_id == user_deck.id,
                UserCardFSRS.state == "review",
                UserCardFSRS.due <= as_of,
            )
            .scalar()
            or 0
        )

        return {
            "id": user_deck.id,
            "title": user_deck.title_snapshot,
            "scope_type": user_deck.scope_type,
            "total_count": total_count,
            "new_count": new_count,
            "learning_count": learning_count,
            "review_count": review_count,
        }
