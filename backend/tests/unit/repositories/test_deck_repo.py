"""
Unit tests for DeckRepository.

Tests deck repository operations including:
- Getting all sources
- Getting children of a deck
- Getting deck by ID
- Creating new decks
- Hierarchy validation
"""

import pytest
from sqlalchemy.orm import Session
from app.repositories.deck_repo import DeckRepository
from app.models.deck import Deck


@pytest.mark.unit
class TestDeckRepository:
    """Test DeckRepository operations."""

    def test_get_all_sources_empty(self, test_db: Session):
        """Test getting all sources when database is empty."""
        repo = DeckRepository(test_db)
        sources = repo.get_all_sources()

        assert sources == []

    def test_get_all_sources_single(self, test_db: Session):
        """Test getting a single source deck."""
        repo = DeckRepository(test_db)

        # Create a source deck
        source = Deck(title="NCE Book 1", type="source", level_index=0)
        test_db.add(source)
        test_db.commit()

        # Get all sources
        sources = repo.get_all_sources()

        assert len(sources) == 1
        assert sources[0].title == "NCE Book 1"
        assert sources[0].type == "source"
        assert sources[0].parent_id is None

    def test_get_all_sources_multiple_ordered(self, test_db: Session):
        """Test getting multiple sources ordered by level_index."""
        repo = DeckRepository(test_db)

        # Create sources out of order
        source2 = Deck(title="NCE Book 2", type="source", level_index=2)
        source0 = Deck(title="NCE Book 1", type="source", level_index=0)
        source1 = Deck(title="Practice", type="source", level_index=1)

        test_db.add_all([source2, source0, source1])
        test_db.commit()

        # Get all sources
        sources = repo.get_all_sources()

        assert len(sources) == 3
        assert sources[0].title == "NCE Book 1"
        assert sources[1].title == "Practice"
        assert sources[2].title == "NCE Book 2"

    def test_get_all_sources_excludes_non_sources(self, test_db: Session):
        """Test that get_all_sources only returns source type decks."""
        repo = DeckRepository(test_db)

        # Create source and unit
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        unit = Deck(title="Unit", type="unit", level_index=0, parent_id=source.id)
        test_db.add(unit)
        test_db.commit()

        # Get all sources
        sources = repo.get_all_sources()

        assert len(sources) == 1
        assert sources[0].type == "source"

    def test_get_children_empty(self, test_db: Session):
        """Test getting children when parent has no children."""
        repo = DeckRepository(test_db)

        # Create source without children
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.commit()

        children = repo.get_children(source.id)

        assert children == []

    def test_get_children_single(self, test_db: Session):
        """Test getting single child of a parent."""
        repo = DeckRepository(test_db)

        # Create source and unit
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        unit = Deck(title="Unit 1", type="unit", level_index=0, parent_id=source.id)
        test_db.add(unit)
        test_db.commit()

        children = repo.get_children(source.id)

        assert len(children) == 1
        assert children[0].title == "Unit 1"
        assert children[0].parent_id == source.id

    def test_get_children_multiple_ordered(self, test_db: Session):
        """Test getting multiple children ordered by level_index."""
        repo = DeckRepository(test_db)

        # Create source
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        # Create units out of order
        unit2 = Deck(title="Unit 3", type="unit", level_index=2, parent_id=source.id)
        unit0 = Deck(title="Unit 1", type="unit", level_index=0, parent_id=source.id)
        unit1 = Deck(title="Unit 2", type="unit", level_index=1, parent_id=source.id)

        test_db.add_all([unit2, unit0, unit1])
        test_db.commit()

        children = repo.get_children(source.id)

        assert len(children) == 3
        assert children[0].title == "Unit 1"
        assert children[1].title == "Unit 2"
        assert children[2].title == "Unit 3"

    def test_get_children_only_direct_children(self, test_db: Session):
        """Test that get_children only returns direct children, not grandchildren."""
        repo = DeckRepository(test_db)

        # Create source -> unit -> lesson hierarchy
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        unit = Deck(title="Unit 1", type="unit", level_index=0, parent_id=source.id)
        test_db.add(unit)
        test_db.flush()

        lesson = Deck(title="Lesson 1", type="lesson", level_index=0, parent_id=unit.id)
        test_db.add(lesson)
        test_db.commit()

        # Get children of source
        children = repo.get_children(source.id)

        assert len(children) == 1
        assert children[0].title == "Unit 1"
        assert children[0].type == "unit"

    def test_get_by_id_found(self, test_db: Session):
        """Test getting a deck by ID when it exists."""
        repo = DeckRepository(test_db)

        # Create deck
        deck = Deck(title="Test Deck", type="source", level_index=0)
        test_db.add(deck)
        test_db.commit()

        # Get by ID
        result = repo.get_by_id(deck.id)

        assert result is not None
        assert result.id == deck.id
        assert result.title == "Test Deck"

    def test_get_by_id_not_found(self, test_db: Session):
        """Test getting a deck by ID when it doesn't exist."""
        repo = DeckRepository(test_db)

        # Try to get non-existent deck
        result = repo.get_by_id(99999)

        assert result is None

    def test_create_source_deck(self, test_db: Session):
        """Test creating a source deck."""
        repo = DeckRepository(test_db)

        deck = repo.create(
            title="New Concept English Book 1",
            type="source",
            parent_id=None,
            level_index=0
        )

        assert deck.id is not None
        assert deck.title == "New Concept English Book 1"
        assert deck.type == "source"
        assert deck.parent_id is None
        assert deck.level_index == 0
        assert deck.created_at is not None

    def test_create_unit_deck(self, test_db: Session):
        """Test creating a unit deck with parent."""
        repo = DeckRepository(test_db)

        # Create parent source
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        # Create unit
        unit = repo.create(
            title="Unit 1",
            type="unit",
            parent_id=source.id,
            level_index=0
        )

        assert unit.id is not None
        assert unit.title == "Unit 1"
        assert unit.type == "unit"
        assert unit.parent_id == source.id
        assert unit.level_index == 0

    def test_create_lesson_deck(self, test_db: Session):
        """Test creating a lesson deck."""
        repo = DeckRepository(test_db)

        # Create source and unit
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        unit = Deck(title="Unit 1", type="unit", level_index=0, parent_id=source.id)
        test_db.add(unit)
        test_db.flush()

        # Create lesson
        lesson = repo.create(
            title="Lesson 1",
            type="lesson",
            parent_id=unit.id,
            level_index=0
        )

        assert lesson.id is not None
        assert lesson.title == "Lesson 1"
        assert lesson.type == "lesson"
        assert lesson.parent_id == unit.id

    def test_create_multiple_siblings(self, test_db: Session):
        """Test creating multiple decks at the same level."""
        repo = DeckRepository(test_db)

        # Create parent
        source = Deck(title="Source", type="source", level_index=0)
        test_db.add(source)
        test_db.flush()

        # Create multiple units
        unit1 = repo.create("Unit 1", "unit", source.id, 0)
        unit2 = repo.create("Unit 2", "unit", source.id, 1)
        unit3 = repo.create("Unit 3", "unit", source.id, 2)

        # Verify all created
        children = repo.get_children(source.id)
        assert len(children) == 3
        assert children[0].title == "Unit 1"
        assert children[1].title == "Unit 2"
        assert children[2].title == "Unit 3"

    def test_full_hierarchy(self, test_db: Session):
        """Test creating and querying a complete 3-level hierarchy."""
        repo = DeckRepository(test_db)

        # Create source
        source = repo.create("NCE Book 1", "source", None, 0)

        # Create unit
        unit = repo.create("Unit 1", "unit", source.id, 0)

        # Create lesson
        lesson = repo.create("Lesson 1", "lesson", unit.id, 0)

        # Verify hierarchy
        assert source.parent_id is None
        assert unit.parent_id == source.id
        assert lesson.parent_id == unit.id

        # Verify queries
        sources = repo.get_all_sources()
        assert len(sources) == 1

        units = repo.get_children(source.id)
        assert len(units) == 1

        lessons = repo.get_children(unit.id)
        assert len(lessons) == 1
