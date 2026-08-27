"""
Unit tests for DashboardService.

Tests business logic for statistics and analytics.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.services.dashboard_service import DashboardService
from app.models import Deck, Card, ReviewLog
from tests.test_data.seed_data import create_test_settings
from app.utils.timezone import storage_now


def _create_lesson_and_card(db: Session) -> tuple[Deck, Card]:
    """Create a minimal lesson + card pair for testing."""
    lesson = Deck(title="Test Lesson", type="lesson", level_index=0)
    db.add(lesson)
    db.flush()

    card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试", audio_path="test.wav")
    db.add(card)
    db.flush()

    return lesson, card


def _add_review(db: Session, card: Card, lesson: Deck, created_at: datetime = None):
    """Add a single completed review log."""
    db.add(ReviewLog(
        card_id=card.id,
        deck_id=lesson.id,
        rating="good",
        result_type="single",
        ai_feedback_json={},
        status="completed",
        created_at=created_at or storage_now()
    ))


@pytest.mark.unit
class TestDashboardService:
    """Test DashboardService business logic."""

    def test_get_dashboard_stats_empty(self, test_db: Session):
        """Test getting dashboard stats with no data."""
        create_test_settings(test_db)

        result = DashboardService(test_db).get_dashboard_stats()

        assert result["today"]["new_limit"] == 20
        assert result["today"]["review_limit"] == 50
        assert result["today"]["completed"] == 0
        assert result["streak_days"] == 0
        assert len(result["heatmap"]) == 90

    def test_get_dashboard_stats_with_reviews(self, test_db: Session):
        """Test dashboard stats with review data."""
        create_test_settings(test_db)
        lesson, card = _create_lesson_and_card(test_db)

        # 3 reviews today, 2 yesterday
        for _ in range(3):
            _add_review(test_db, card, lesson)
        yesterday = storage_now() - timedelta(days=1)
        for _ in range(2):
            _add_review(test_db, card, lesson, created_at=yesterday)
        test_db.commit()

        result = DashboardService(test_db).get_dashboard_stats()

        assert result["today"]["completed"] == 3
        assert result["streak_days"] == 2
        assert result["heatmap"][-1]["count"] == 3

    def test_calculate_streak_consecutive_days(self, test_db: Session):
        """Test streak calculation with consecutive days."""
        lesson, card = _create_lesson_and_card(test_db)

        for days_ago in range(5):
            _add_review(test_db, card, lesson, created_at=storage_now() - timedelta(days=days_ago))
        test_db.commit()

        assert DashboardService(test_db).get_dashboard_stats()["streak_days"] == 5

    def test_calculate_streak_broken(self, test_db: Session):
        """Test streak calculation with broken streak (gap of 2 days)."""
        lesson, card = _create_lesson_and_card(test_db)

        _add_review(test_db, card, lesson)  # today
        _add_review(test_db, card, lesson, created_at=storage_now() - timedelta(days=3))  # 3 days ago
        test_db.commit()

        assert DashboardService(test_db).get_dashboard_stats()["streak_days"] == 1

    def test_heatmap_format(self, test_db: Session):
        """Test heatmap data format and ordering."""
        create_test_settings(test_db)

        heatmap = DashboardService(test_db).get_dashboard_stats()["heatmap"]

        assert len(heatmap) == 90

        # Chronological order (oldest first)
        dates = [entry["date"] for entry in heatmap]
        assert dates == sorted(dates)

        for entry in heatmap:
            assert isinstance(entry["date"], str)
            assert isinstance(entry["count"], int)
