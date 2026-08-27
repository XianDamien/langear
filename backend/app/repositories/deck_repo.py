"""Deck repository for database operations."""

from sqlalchemy.orm import Session, aliased

from app.models.deck import Deck


class DeckRepository:
    """Repository for Deck model operations."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get_all_sources(self) -> list[Deck]:
        """Get all top-level sources.

        Returns:
            List of Deck objects with type='source'
        """
        return (
            self.db.query(Deck)
            .filter(Deck.type == "source", Deck.parent_id.is_(None))
            .order_by(Deck.level_index)
            .all()
        )

    def get_sources_by_ids(self, deck_ids: list[int]) -> list[Deck]:
        """Get source decks by IDs."""
        if not deck_ids:
            return []
        return (
            self.db.query(Deck)
            .filter(
                Deck.id.in_(deck_ids),
                Deck.type == "source",
                Deck.parent_id.is_(None),
            )
            .order_by(Deck.level_index, Deck.id)
            .all()
        )

    def get_children(self, parent_id: int) -> list[Deck]:
        """Get all children of a deck.

        Args:
            parent_id: Parent deck ID

        Returns:
            List of child Deck objects ordered by level_index
        """
        return (
            self.db.query(Deck)
            .filter(Deck.parent_id == parent_id)
            .order_by(Deck.level_index)
            .all()
        )

    def get_by_id(self, deck_id: int) -> Deck | None:
        """Get deck by ID.

        Args:
            deck_id: Deck ID

        Returns:
            Deck object or None if not found
        """
        return self.db.query(Deck).filter(Deck.id == deck_id).first()

    def get_lesson_ids_for_sources(self, source_ids: list[int]) -> list[int]:
        """Get all lesson IDs that belong to the provided source scope."""
        if not source_ids:
            return []

        source = aliased(Deck)
        unit = aliased(Deck)
        lesson = aliased(Deck)

        rows = (
            self.db.query(lesson.id)
            .join(unit, lesson.parent_id == unit.id)
            .join(source, unit.parent_id == source.id)
            .filter(
                source.id.in_(source_ids),
                source.type == "source",
                unit.type == "unit",
                lesson.type == "lesson",
            )
            .order_by(source.level_index, unit.level_index, lesson.level_index, lesson.id)
            .all()
        )
        return [row[0] for row in rows]

    def get_source_id_for_lesson(self, lesson_id: int) -> int | None:
        """Resolve the source deck ID for a lesson."""
        source = aliased(Deck)
        unit = aliased(Deck)
        lesson = aliased(Deck)

        row = (
            self.db.query(source.id)
            .join(unit, unit.parent_id == source.id)
            .join(lesson, lesson.parent_id == unit.id)
            .filter(
                lesson.id == lesson_id,
                source.type == "source",
                unit.type == "unit",
                lesson.type == "lesson",
            )
            .first()
        )
        return row[0] if row else None

    def create(
        self,
        title: str,
        type: str,
        parent_id: int | None = None,
        level_index: int = 0,
    ) -> Deck:
        """Create a new deck.

        Args:
            title: Deck title
            type: Deck type (source/unit/lesson)
            parent_id: Parent deck ID (None for sources)
            level_index: Sort order within parent

        Returns:
            Created Deck object
        """
        deck = Deck(
            title=title,
            type=type,
            parent_id=parent_id,
            level_index=level_index,
        )
        self.db.add(deck)
        self.db.flush()
        return deck
