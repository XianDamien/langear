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


@pytest.mark.parametrize('user_id', [None, 1, 2])
def test_tree_query_count_does_not_grow_per_lesson(test_db, sample_deck_tree, user_id):
    from sqlalchemy import event
    from app.models import Card, Deck

    unit_id = sample_deck_tree['unit'].id
    for i in range(12):
        lesson = Deck(title=f'Lesson {i+2}', type='lesson', parent_id=unit_id, level_index=i+1)
        test_db.add(lesson)
        test_db.flush()
        test_db.add(Card(deck_id=lesson.id, card_index=0, front_text='Example'))
    test_db.flush()
    statements = []
    def count_queries(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    connection = test_db.connection()
    event.listen(connection, 'before_cursor_execute', count_queries)
    try:
        tree = ContentService(test_db, user_id=user_id).get_deck_tree()
    finally:
        event.remove(connection, 'before_cursor_execute', count_queries)
    assert len(tree['sources'][0]['units'][0]['lessons']) == 13
    assert len(statements) <= 4, f'{len(statements)} SQL queries for 13 lessons'


@pytest.mark.parametrize('legacy_days,personal_days,legacy_due,personal_due,expected_due', [
    (1, 2, 2, -1, 0),
    (3, 1, -1, 2, 0),
    (1, None, -1, 2, 1),
    (2, 2, 2, -1, 1),
    (None, 1, -1, 2, 0),
])
def test_tree_keeps_effective_personal_progress(test_db, sample_deck_tree, legacy_days, personal_days, legacy_due, personal_due, expected_due):
    from datetime import timedelta
    from app.models import User, UserCardSRS
    from app.models.user_card_fsrs import UserCardFSRS
    from app.utils.timezone import storage_now

    now = storage_now()
    test_db.add(User(id=1, username='original'))
    test_db.add(User(id=2, username='other'))
    card_id = sample_deck_tree['cards'][0].id
    legacy = test_db.get(UserCardSRS, card_id)
    legacy.last_review = None if legacy_days is None else now-timedelta(days=legacy_days)
    legacy.due = now+timedelta(days=legacy_due)
    test_db.add(UserCardFSRS(user_id=1, card_id=card_id, state='review', due=now+timedelta(days=personal_due), last_review=None if personal_days is None else now-timedelta(days=personal_days)))
    test_db.flush()
    own = ContentService(test_db, user_id=1).get_deck_tree()['sources'][0]['units'][0]['lessons'][0]
    other = ContentService(test_db, user_id=2).get_deck_tree()['sources'][0]['units'][0]['lessons'][0]
    assert (own['total_cards'], own['completed_cards'], own['new_cards'], own['due_cards']) == (5, 1, 4, expected_due)
    assert (other['completed_cards'], other['new_cards'], other['due_cards']) == (0, 5, 0)
