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
from app.utils.timezone import storage_now


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

    def get_origin_decks_by_ids(self, origin_deck_ids: list[int]) -> list[Deck]:
        """Return public decks for the provided ids."""
        if not origin_deck_ids:
            return []

        return (
            self.db.query(Deck)
            .filter(Deck.id.in_(origin_deck_ids))
            .all()
        )

    def get_by_user_origin(
        self,
        user_id: int,
        origin_deck_id: int,
        include_inactive: bool = True,
    ) -> UserDeck | None:
        """Return an imported user deck for a public origin deck."""
        query = (
            self.db.query(UserDeck)
            .filter(
                UserDeck.user_id == user_id,
                UserDeck.origin_deck_id == origin_deck_id,
            )
        )
        if not include_inactive:
            query = query.filter(UserDeck.status == "active")
        return query.first()

    def get_active_by_id(self, user_id: int, user_deck_id: int) -> UserDeck | None:
        """Return an active user deck by id for the current user."""
        return (
            self.db.query(UserDeck)
            .filter(
                UserDeck.id == user_deck_id,
                UserDeck.user_id == user_id,
                UserDeck.status == "active",
            )
            .first()
        )

    def list_for_user(self, user_id: int, active_only: bool = True) -> list[UserDeck]:
        """List imported user decks in stable creation order."""
        query = (
            self.db.query(UserDeck)
            .filter(UserDeck.user_id == user_id)
        )
        if active_only:
            query = query.filter(UserDeck.status == "active")
        return query.order_by(UserDeck.created_at, UserDeck.id).all()

    def get_lesson_ids_for_origin(self, origin_deck: Deck) -> list[int]:
        """Return ordered lesson ids covered by a source, unit, or lesson deck."""
        if origin_deck.type == "lesson":
            return [origin_deck.id]

        if origin_deck.type == "unit":
            return [
                deck_id
                for (deck_id,) in (
                    self.db.query(Deck.id)
                    .filter(Deck.parent_id == origin_deck.id, Deck.type == "lesson")
                    .order_by(Deck.level_index, Deck.id)
                    .all()
                )
            ]

        if origin_deck.type == "source":
            unit = aliased(Deck)
            lesson = aliased(Deck)
            return [
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

        return []

    def get_cards_for_lesson_ids(self, lesson_ids: list[int]) -> list[Card]:
        """Return cards for ordered lesson ids while preserving lesson order."""
        if not lesson_ids:
            return []

        lesson_order = {lesson_id: index for index, lesson_id in enumerate(lesson_ids)}
        cards = (
            self.db.query(Card)
            .filter(Card.deck_id.in_(lesson_ids))
            .all()
        )
        return sorted(
            cards,
            key=lambda card: (
                lesson_order.get(card.deck_id, len(lesson_ids)),
                card.card_index,
                card.id,
            ),
        )

    def get_cards_for_origin(self, origin_deck: Deck) -> list[Card]:
        """Return cards covered by a source, unit, or lesson deck."""
        lesson_ids = self.get_lesson_ids_for_origin(origin_deck)
        return self.get_cards_for_lesson_ids(lesson_ids)

    def create_import(self, user_id: int, origin_deck: Deck, cards: list[Card]) -> UserDeck:
        """Create a user deck and stable card membership rows."""
        user_deck = UserDeck(
            user_id=user_id,
            origin_deck_id=origin_deck.id,
            scope_type=origin_deck.type,
            title_snapshot=origin_deck.title,
            status="active",
        )
        self.db.add(user_deck)
        self.db.flush()

        self.supplement_memberships(user_deck, cards)
        return user_deck

    def activate_existing(self, user_deck: UserDeck, origin_deck: Deck) -> UserDeck:
        """Reactivate an existing user deck with refreshed public metadata."""
        user_deck.status = "active"
        user_deck.scope_type = origin_deck.type
        user_deck.title_snapshot = origin_deck.title
        user_deck.updated_at = storage_now(self.db)
        self.db.flush()
        return user_deck

    def deactivate_missing(self, user_id: int, keep_origin_ids: set[int]) -> None:
        """Soft-delete active user decks not included in the final selection."""
        query = (
            self.db.query(UserDeck)
            .filter(
                UserDeck.user_id == user_id,
                UserDeck.status == "active",
            )
        )
        if keep_origin_ids:
            query = query.filter(~UserDeck.origin_deck_id.in_(keep_origin_ids))

        now = storage_now(self.db)
        for user_deck in query.all():
            user_deck.status = "inactive"
            user_deck.updated_at = now

        self.db.flush()

    def supplement_memberships(self, user_deck: UserDeck, cards: list[Card]) -> None:
        """Append missing user deck memberships while keeping historical positions."""
        existing_memberships = (
            self.db.query(UserDeckCard)
            .filter(UserDeckCard.user_deck_id == user_deck.id)
            .order_by(UserDeckCard.new_position, UserDeckCard.card_id)
            .all()
        )
        existing_card_ids = {membership.card_id for membership in existing_memberships}
        next_position = (
            max((membership.new_position for membership in existing_memberships), default=0)
        )

        for card in cards:
            if card.id in existing_card_ids:
                continue

            next_position += 1
            self.db.add(
                UserDeckCard(
                    user_deck_id=user_deck.id,
                    card_id=card.id,
                    new_position=next_position,
                )
            )

        self.db.flush()

    def has_card_membership(self, user_deck_id: int, card_id: int) -> bool:
        """Whether a card belongs to a user deck."""
        return (
            self.db.query(UserDeckCard)
            .filter(
                UserDeckCard.user_deck_id == user_deck_id,
                UserDeckCard.card_id == card_id,
            )
            .first()
            is not None
        )

    def list_cards_with_fsrs(
        self,
        user_id: int,
        user_deck_id: int,
    ) -> list[tuple[UserDeckCard, Card, UserCardFSRS | None]]:
        """Return ordered user deck cards with optional per-user FSRS snapshots."""
        fsrs_join = and_(
            UserCardFSRS.user_id == user_id,
            UserCardFSRS.card_id == UserDeckCard.card_id,
        )
        return (
            self.db.query(UserDeckCard, Card, UserCardFSRS)
            .join(Card, Card.id == UserDeckCard.card_id)
            .outerjoin(UserCardFSRS, fsrs_join)
            .filter(UserDeckCard.user_deck_id == user_deck_id)
            .order_by(UserDeckCard.new_position, UserDeckCard.card_id)
            .all()
        )

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
            "origin_deck_id": user_deck.origin_deck_id,
            "title": user_deck.title_snapshot,
            "scope_type": user_deck.scope_type,
            "total_count": total_count,
            "new_count": new_count,
            "learning_count": learning_count,
            "review_count": review_count,
        }
