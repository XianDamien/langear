"""All content lookups are scoped before any IDs are resolved."""

from sqlalchemy import select
from core.errors import DomainError, missing
from core.models import Collection, Deck


class ContentRepository:
    def __init__(self, db, collection):
        self.db, self.collection = db, collection

    def lock(self):
        collection = self.db.scalar(
            select(Collection)
            .where(Collection.id == self.collection.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if collection.kind != "user":
            raise DomainError(403, "LIBRARY_READ_ONLY", "System Library is read-only.")
        return collection

    def get(self, model, resource_id):
        resource = self.db.scalar(
            select(model).where(
                model.id == resource_id, model.collection_id == self.collection.id
            )
        )
        if resource is None:
            missing()
        return resource

    def standard_deck(self, deck_id):
        deck = self.get(Deck, deck_id)
        if deck.kind != "standard":
            raise DomainError(422, "STANDARD_DECK_REQUIRED", "Choose a Standard Deck.")
        return deck

    def descendants(self, deck_id):
        root = (
            select(Deck.id)
            .where(Deck.collection_id == self.collection.id, Deck.id == deck_id)
            .cte(recursive=True)
        )
        tree = root.union_all(
            select(Deck.id)
            .join(root, Deck.parent_id == root.c.id)
            .where(Deck.collection_id == self.collection.id)
        )
        return list(self.db.scalars(select(tree.c.id)))
