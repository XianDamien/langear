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
            self.user_deck_repo.activate_existing(existing, origin_deck)
            cards = self.user_deck_repo.get_cards_for_origin(origin_deck)
            if not cards:
                raise ValueError(f"Deck {origin_deck_id} has no cards to import")
            self.user_deck_repo.supplement_memberships(existing, cards)
            self.db.commit()
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
        user_decks = self.user_deck_repo.list_for_user(user_id, active_only=True)
        as_of = storage_now()
        return [
            self.user_deck_repo.summarize(user_deck, as_of)
            for user_deck in user_decks
        ]

    def sync_selection(
        self,
        user_id: int,
        origin_deck_ids: list[int],
    ) -> dict[str, Any]:
        """Synchronize the final active user deck selection using soft delete."""
        self.user_deck_repo.ensure_user(user_id)

        normalized_ids: list[int] = []
        seen: set[int] = set()
        for origin_deck_id in origin_deck_ids:
            if origin_deck_id in seen:
                continue
            seen.add(origin_deck_id)
            normalized_ids.append(origin_deck_id)

        origin_decks = self.user_deck_repo.get_origin_decks_by_ids(normalized_ids)
        origin_decks_by_id = {deck.id: deck for deck in origin_decks}
        missing_ids = [
            origin_deck_id
            for origin_deck_id in normalized_ids
            if origin_deck_id not in origin_decks_by_id
        ]
        if missing_ids:
            raise ValueError(
                f"Unknown origin_deck_ids: {', '.join(str(origin_id) for origin_id in missing_ids)}"
            )

        for origin_deck_id in normalized_ids:
            origin_deck = origin_decks_by_id[origin_deck_id]
            cards = self.user_deck_repo.get_cards_for_origin(origin_deck)
            if not cards:
                raise ValueError(f"Deck {origin_deck_id} has no cards to import")

            existing = self.user_deck_repo.get_by_user_origin(user_id, origin_deck_id)
            if existing is None:
                existing = self.user_deck_repo.create_import(user_id, origin_deck, cards)
            else:
                self.user_deck_repo.activate_existing(existing, origin_deck)
                self.user_deck_repo.supplement_memberships(existing, cards)

        self.user_deck_repo.deactivate_missing(user_id, set(normalized_ids))
        self.db.commit()

        return {
            "origin_deck_ids": normalized_ids,
            "user_decks": self.list_decks(user_id),
        }
