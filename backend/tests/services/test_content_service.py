"""
Unit tests for ContentService.

Tests business logic for deck tree and card queries.
"""

import pytest
from sqlalchemy.orm import Session
from app.services.content_service import ContentService


@pytest.mark.unit
class TestContentService:
    """Test ContentService business logic."""

    def test_get_deck_tree_empty(self, test_db: Session):
        """Test getting deck tree with no data."""
        service = ContentService(test_db)
        result = service.get_deck_tree()

        assert "sources" in result
        assert result["sources"] == []

    def test_get_deck_tree_complete(self, test_db: Session, sample_deck_tree):
        """Test getting complete deck tree with all 3 levels."""
        service = ContentService(test_db)
        result = service.get_deck_tree()

        # Verify structure
        assert "sources" in result
        assert len(result["sources"]) == 1

        source = result["sources"][0]
        assert source["id"] == sample_deck_tree["source"].id
        assert source["title"] == "New Concept English Book 2"
        assert "units" in source
        assert len(source["units"]) == 1

        unit = source["units"][0]
        assert unit["id"] == sample_deck_tree["unit"].id
        assert unit["title"] == "Unit 1: Getting Started"
        assert "lessons" in unit
        assert len(unit["lessons"]) == 1

        lesson = unit["lessons"][0]
        assert lesson["id"] == sample_deck_tree["lesson"].id
        assert lesson["title"] == "Lesson 1: A Private Conversation"
        assert lesson["total_cards"] == 5
        assert lesson["completed_cards"] == 0  # Initial SRS snapshots have no reviews yet
        assert lesson["new_cards"] == 5
        assert lesson["due_cards"] >= 0  # Due count varies based on timing

    def test_get_lesson_cards_success(self, test_db: Session, sample_deck_tree):
        """Test getting cards for a valid lesson."""
        service = ContentService(test_db)
        lesson_id = sample_deck_tree["lesson"].id

        result = service.get_lesson_cards(lesson_id)

        assert result["lesson_id"] == lesson_id
        assert "cards" in result
        assert len(result["cards"]) == 5

        # Verify cards are ordered by card_index
        for i, card in enumerate(result["cards"]):
            assert card["card_index"] == i
            assert "id" in card
            assert "front_text" in card
            assert "back_text" in card
            assert "audio_path" in card

        # Verify first card content
        first_card = result["cards"][0]
        assert first_card["front_text"] == "Last week I went to the theatre."
        assert first_card["back_text"] == "上周我去了剧院。"

    def test_get_lesson_cards_not_found(self, test_db: Session):
        """Test getting cards for nonexistent lesson."""
        service = ContentService(test_db)

        with pytest.raises(ValueError, match="Lesson 99999 not found"):
            service.get_lesson_cards(99999)

    def test_get_lesson_cards_wrong_type(self, test_db: Session, sample_deck_tree):
        """Test getting cards for a unit (not a lesson)."""
        service = ContentService(test_db)
        unit_id = sample_deck_tree["unit"].id  # This is a unit, not lesson

        with pytest.raises(ValueError, match=f"Lesson {unit_id} not found"):
            service.get_lesson_cards(unit_id)

    def test_get_lesson_cards_empty_lesson(self, test_db: Session):
        """Test getting cards for a lesson with no cards."""
        from app.models import Deck

        # Create empty lesson
        lesson = Deck(title="Empty Lesson", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        service = ContentService(test_db)
        result = service.get_lesson_cards(lesson.id)

        assert result["lesson_id"] == lesson.id
        assert result["cards"] == []
