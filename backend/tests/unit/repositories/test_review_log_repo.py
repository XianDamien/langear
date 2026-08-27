"""
Unit tests for ReviewLogRepository.

Tests review log repository operations including:
- Creating review logs
- Getting logs by ID
- Updating log status
- Getting single feedbacks by lesson
- Getting summaries by lesson
- Counting reviews by date
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.repositories.review_log_repo import ReviewLogRepository
from app.utils.timezone import storage_now
from app.models.deck import Deck
from app.models.card import Card
from app.models.review_log import ReviewLog


@pytest.mark.unit
class TestReviewLogRepository:
    """Test ReviewLogRepository operations."""

    def test_create_single_review_log(self, test_db: Session):
        """Test creating a single-card review log."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.commit()

        # Create review log
        feedback = {
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent"
        }

        log = repo.create(
            deck_id=lesson.id,
            result_type="single",
            ai_feedback_json=feedback,
            card_id=card.id,
            rating="good"
        )

        assert log.id is not None
        assert log.card_id == card.id
        assert log.deck_id == lesson.id
        assert log.rating == "good"
        assert log.result_type == "single"
        assert log.ai_feedback_json == feedback
        assert log.status == "processing"  # Default status

    def test_create_summary_review_log(self, test_db: Session):
        """Test creating a lesson summary review log."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        # Create summary log
        summary = {
            "overall_performance": "Good progress",
            "strengths": ["Pronunciation", "Fluency"],
            "areas_for_improvement": ["Completeness"]
        }

        log = repo.create(
            deck_id=lesson.id,
            result_type="summary",
            ai_feedback_json=summary,
            card_id=None,
            rating=None
        )

        assert log.id is not None
        assert log.card_id is None
        assert log.deck_id == lesson.id
        assert log.rating is None
        assert log.result_type == "summary"
        assert log.ai_feedback_json == summary

    def test_create_review_log_with_empty_feedback(self, test_db: Session):
        """Test creating a review log with empty feedback (processing state)."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.commit()

        # Create log with empty feedback
        log = repo.create(
            deck_id=lesson.id,
            result_type="single",
            ai_feedback_json={},
            card_id=card.id,
            rating="good"
        )

        assert log.ai_feedback_json == {}
        assert log.status == "processing"

    def test_get_by_id_found(self, test_db: Session):
        """Test getting a review log by ID when it exists."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.flush()

        # Create review log
        log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json={"test": "data"}
        )
        test_db.add(log)
        test_db.commit()

        # Get by ID
        result = repo.get_by_id(log.id)

        assert result is not None
        assert result.id == log.id
        assert result.card_id == card.id

    def test_get_by_id_not_found(self, test_db: Session):
        """Test getting a review log by ID when it doesn't exist."""
        repo = ReviewLogRepository(test_db)

        result = repo.get_by_id(99999)

        assert result is None

    def test_update_status_to_completed(self, test_db: Session):
        """Test updating review log status from processing to completed."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.flush()

        # Create log in processing state
        log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json={},
            status="processing"
        )
        test_db.add(log)
        test_db.commit()

        # Update to completed with feedback
        feedback = {
            "pronunciation": "Excellent",
            "completeness": "Complete",
            "fluency": "Very fluent"
        }

        updated_log = repo.update_status(
            log_id=log.id,
            status="completed",
            ai_feedback_json=feedback
        )

        assert updated_log is not None
        assert updated_log.status == "completed"
        assert updated_log.ai_feedback_json == feedback
        assert updated_log.error_code is None
        assert updated_log.error_message is None

    def test_update_status_to_failed(self, test_db: Session):
        """Test updating review log status from processing to failed."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.flush()

        # Create log in processing state
        log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json={},
            status="processing"
        )
        test_db.add(log)
        test_db.commit()

        # Update to failed with error details
        updated_log = repo.update_status(
            log_id=log.id,
            status="failed",
            error_code="ASR_ERROR",
            error_message="ASR service unavailable"
        )

        assert updated_log is not None
        assert updated_log.status == "failed"
        assert updated_log.error_code == "ASR_ERROR"
        assert updated_log.error_message == "ASR service unavailable"

    def test_update_status_not_found(self, test_db: Session):
        """Test updating status of non-existent review log."""
        repo = ReviewLogRepository(test_db)

        result = repo.update_status(
            log_id=99999,
            status="completed"
        )

        assert result is None

    def test_update_status_partial_update(self, test_db: Session):
        """Test that update_status only updates provided fields."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Test", back_text="测试")
        test_db.add(card)
        test_db.flush()

        # Create log with initial feedback
        initial_feedback = {"initial": "data"}
        log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json=initial_feedback,
            status="processing"
        )
        test_db.add(log)
        test_db.commit()

        # Update only status, not feedback
        updated_log = repo.update_status(
            log_id=log.id,
            status="completed"
        )

        assert updated_log.status == "completed"
        assert updated_log.ai_feedback_json == initial_feedback  # Unchanged

    def test_get_single_feedbacks_by_lesson_empty(self, test_db: Session):
        """Test getting single feedbacks when lesson has no reviews."""
        repo = ReviewLogRepository(test_db)

        # Create lesson without reviews
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        feedbacks = repo.get_single_feedbacks_by_lesson(lesson.id)

        assert feedbacks == []

    def test_get_single_feedbacks_by_lesson_with_feedbacks(self, test_db: Session):
        """Test getting single feedbacks when lesson has reviews."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create cards
        card1 = Card(deck_id=lesson.id, card_index=0, front_text="Card 1")
        card2 = Card(deck_id=lesson.id, card_index=1, front_text="Card 2")
        test_db.add_all([card1, card2])
        test_db.flush()

        # Create single review logs
        feedback1 = {"pronunciation": "Good", "rating": "A"}
        feedback2 = {"pronunciation": "Excellent", "rating": "A+"}

        log1 = ReviewLog(
            card_id=card1.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json=feedback1,
            status="completed"
        )
        log2 = ReviewLog(
            card_id=card2.id,
            deck_id=lesson.id,
            rating="easy",
            result_type="single",
            ai_feedback_json=feedback2,
            status="completed"
        )
        test_db.add_all([log1, log2])
        test_db.commit()

        # Get feedbacks
        feedbacks = repo.get_single_feedbacks_by_lesson(lesson.id)

        assert len(feedbacks) == 2
        assert feedback1 in feedbacks
        assert feedback2 in feedbacks

    def test_get_single_feedbacks_excludes_summaries(self, test_db: Session):
        """Test that get_single_feedbacks_by_lesson excludes summary logs."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Card 1")
        test_db.add(card)
        test_db.flush()

        # Create single log
        single_log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json={"type": "single"},
            status="completed"
        )

        # Create summary log
        summary_log = ReviewLog(
            card_id=None,
            deck_id=lesson.id,
            rating=None,
            result_type="summary",
            ai_feedback_json={"type": "summary"},
            status="completed"
        )

        test_db.add_all([single_log, summary_log])
        test_db.commit()

        # Get feedbacks
        feedbacks = repo.get_single_feedbacks_by_lesson(lesson.id)

        assert len(feedbacks) == 1
        assert feedbacks[0]["type"] == "single"

    def test_get_summary_by_lesson_not_found(self, test_db: Session):
        """Test getting summary when it doesn't exist."""
        repo = ReviewLogRepository(test_db)

        # Create lesson without summary
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        summary = repo.get_summary_by_lesson(lesson.id)

        assert summary is None

    def test_get_summary_by_lesson_found(self, test_db: Session):
        """Test getting summary when it exists."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create summary log
        summary_data = {
            "overall_performance": "Excellent",
            "completion_rate": "100%"
        }

        log = ReviewLog(
            card_id=None,
            deck_id=lesson.id,
            rating=None,
            result_type="summary",
            ai_feedback_json=summary_data,
            status="completed"
        )
        test_db.add(log)
        test_db.commit()

        # Get summary
        summary = repo.get_summary_by_lesson(lesson.id)

        assert summary is not None
        assert summary.result_type == "summary"
        assert summary.ai_feedback_json == summary_data

    def test_get_summary_by_lesson_only_gets_summary(self, test_db: Session):
        """Test that get_summary_by_lesson only returns summary, not single logs."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(deck_id=lesson.id, card_index=0, front_text="Card 1")
        test_db.add(card)
        test_db.flush()

        # Create single log
        single_log = ReviewLog(
            card_id=card.id,
            deck_id=lesson.id,
            rating="good",
            result_type="single",
            ai_feedback_json={},
            status="completed"
        )
        test_db.add(single_log)
        test_db.commit()

        # Get summary (should be None)
        summary = repo.get_summary_by_lesson(lesson.id)

        assert summary is None

    def test_count_reviews_by_date_empty(self, test_db: Session):
        """Test counting reviews when no reviews exist for the date."""
        repo = ReviewLogRepository(test_db)

        today = storage_now()
        count = repo.count_reviews_by_date(today)

        assert count == 0

    def test_count_reviews_by_date_with_reviews(self, test_db: Session):
        """Test counting reviews for a specific date."""
        repo = ReviewLogRepository(test_db)

        # Create lesson and cards
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create reviews for today
        today = storage_now().replace(hour=12, minute=0, second=0, microsecond=0)

        for i in range(5):
            card = Card(deck_id=lesson.id, card_index=i, front_text=f"Card {i}")
            test_db.add(card)
            test_db.flush()

            log = ReviewLog(
                card_id=card.id,
                deck_id=lesson.id,
                rating="good",
                result_type="single",
                ai_feedback_json={},
                status="completed",
                created_at=today
            )
            test_db.add(log)

        test_db.commit()

        # Count reviews for today
        count = repo.count_reviews_by_date(today)

        assert count == 5

    def test_count_reviews_by_date_excludes_other_dates(self, test_db: Session):
        """Test that count_reviews_by_date only counts reviews from the specified date."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        today = storage_now().replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        # Create reviews for today
        for i in range(3):
            card = Card(deck_id=lesson.id, card_index=i, front_text=f"Today {i}")
            test_db.add(card)
            test_db.flush()

            log = ReviewLog(
                card_id=card.id,
                deck_id=lesson.id,
                rating="good",
                result_type="single",
                ai_feedback_json={},
                created_at=today
            )
            test_db.add(log)

        # Create reviews for yesterday
        for i in range(5):
            card = Card(deck_id=lesson.id, card_index=i + 10, front_text=f"Yesterday {i}")
            test_db.add(card)
            test_db.flush()

            log = ReviewLog(
                card_id=card.id,
                deck_id=lesson.id,
                rating="good",
                result_type="single",
                ai_feedback_json={},
                created_at=yesterday
            )
            test_db.add(log)

        test_db.commit()

        # Count should only include today's reviews
        assert repo.count_reviews_by_date(today) == 3
        assert repo.count_reviews_by_date(yesterday) == 5

    def test_count_reviews_by_date_excludes_summaries(self, test_db: Session):
        """Test that count_reviews_by_date only counts single reviews, not summaries."""
        repo = ReviewLogRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        today = storage_now()

        # Create single reviews
        for i in range(3):
            card = Card(deck_id=lesson.id, card_index=i, front_text=f"Card {i}")
            test_db.add(card)
            test_db.flush()

            log = ReviewLog(
                card_id=card.id,
                deck_id=lesson.id,
                rating="good",
                result_type="single",
                ai_feedback_json={}
            )
            test_db.add(log)

        # Create summary
        summary = ReviewLog(
            card_id=None,
            deck_id=lesson.id,
            rating=None,
            result_type="summary",
            ai_feedback_json={}
        )
        test_db.add(summary)

        test_db.commit()

        # Count should only include single reviews
        count = repo.count_reviews_by_date(today)

        assert count == 3

    def test_list_single_submissions_orders_newest_first(self, test_db: Session):
        """Test listing single-card submissions ordered by creation time desc."""
        repo = ReviewLogRepository(test_db)

        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        first_card = Card(deck_id=lesson.id, card_index=0, front_text="First", back_text="一")
        second_card = Card(deck_id=lesson.id, card_index=1, front_text="Second", back_text="二")
        test_db.add_all([first_card, second_card])
        test_db.flush()

        older = ReviewLog(
            card_id=first_card.id,
            deck_id=lesson.id,
            rating=None,
            result_type="single",
            ai_feedback_json={},
            status="processing",
            created_at=storage_now() - timedelta(minutes=5),
        )
        newer = ReviewLog(
            card_id=second_card.id,
            deck_id=lesson.id,
            rating=None,
            result_type="single",
            ai_feedback_json={},
            status="failed",
            created_at=storage_now(),
        )
        summary = ReviewLog(
            card_id=None,
            deck_id=lesson.id,
            rating=None,
            result_type="summary",
            ai_feedback_json={},
            status="completed",
        )
        test_db.add_all([older, newer, summary])
        test_db.commit()

        results = repo.list_single_submissions(lesson_id=lesson.id)
        assert [log.id for log in results] == [newer.id, older.id]

    def test_list_single_submissions_supports_card_filter(self, test_db: Session):
        """Test listing single-card submissions by lesson and card."""
        repo = ReviewLogRepository(test_db)

        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        first_card = Card(deck_id=lesson.id, card_index=0, front_text="First", back_text="一")
        second_card = Card(deck_id=lesson.id, card_index=1, front_text="Second", back_text="二")
        test_db.add_all([first_card, second_card])
        test_db.flush()

        first_log = ReviewLog(
            card_id=first_card.id,
            deck_id=lesson.id,
            rating=None,
            result_type="single",
            ai_feedback_json={},
            status="processing",
        )
        second_log = ReviewLog(
            card_id=second_card.id,
            deck_id=lesson.id,
            rating=None,
            result_type="single",
            ai_feedback_json={},
            status="completed",
        )
        test_db.add_all([first_log, second_log])
        test_db.commit()

        results = repo.list_single_submissions(lesson_id=lesson.id, card_id=first_card.id)
        assert [log.id for log in results] == [first_log.id]
