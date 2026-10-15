"""Service layer for user-owned study decks."""

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.user_deck_repo import UserDeckRepository
from app.utils.timezone import storage_now


class UserDeckService:
    """Import and list user study decks."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.user_deck_repo = UserDeckRepository(db)

    def import_deck(self, user_id: int, origin_deck_id: int) -> dict[str, Any]:
        """Import a public source/unit/lesson deck into a user's study space."""
        self.user_deck_repo.ensure_user(user_id)

        origin_deck = self.user_deck_repo.get_origin_deck(origin_deck_id)
        if origin_deck is None:
            raise ValueError(f"Deck {origin_deck_id} does not exist")

        existing = self.user_deck_repo.get_by_user_origin(user_id, origin_deck_id)
        if existing is not None:
            return self.user_deck_repo.summarize(existing, storage_now())

        cards = self.user_deck_repo.get_cards_for_origin(origin_deck)
        if not cards:
            raise ValueError(f"Deck {origin_deck_id} has no cards to import")

        user_deck = self.user_deck_repo.create_import(user_id, origin_deck, cards)
        self.db.commit()
        self.db.refresh(user_deck)
        return self.user_deck_repo.summarize(user_deck, storage_now())

    def list_decks(self, user_id: int) -> list[dict[str, Any]]:
        """List imported decks with current user learning counts."""
        self.user_deck_repo.ensure_user(user_id)
        user_decks = self.user_deck_repo.list_for_user(user_id)
        as_of = storage_now()
        return [
            self.user_deck_repo.summarize(user_deck, as_of)
            for user_deck in user_decks
        ]
