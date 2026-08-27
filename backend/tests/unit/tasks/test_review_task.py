"""Unit tests for review background task."""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.exceptions import AIFeedbackError
from app.models.review_log import ReviewLog
from app.tasks.review_task import process_review_task


@pytest.mark.unit
class TestReviewTask:
    def _create_processing_log(self, test_db: Session, card_id: int, lesson_id: int) -> ReviewLog:
        log = ReviewLog(
            card_id=card_id,
            deck_id=lesson_id,
            rating=None,
            result_type="single",
            ai_feedback_json={},
            status="processing",
        )
        test_db.add(log)
        test_db.commit()
        test_db.refresh(log)
        return log

    def test_process_review_task_success(
        self,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        lesson = sample_deck_tree["lesson"]
        card = sample_deck_tree["cards"][0]
        log = self._create_processing_log(test_db, card.id, lesson.id)

        monkeypatch.setattr("app.tasks.review_task.SessionLocal", lambda: test_db)
        monkeypatch.setattr(test_db, "close", lambda: None)
        monkeypatch.setattr(
            "app.adapters.oss_adapter.OSSAdapter.generate_signed_url",
            lambda self, object_name, expires=3600: f"https://signed.example.com/{object_name}",
        )

        mock_provider = Mock()
        mock_provider.generate_single_feedback.return_value = {
            "transcription_text": "Last week I went to the movie theater",
            "pronunciation": "Clear pronunciation.",
            "completeness": "Complete sentence.",
            "fluency": "Fluent speech.",
            "suggestions": [
                {"text": "Stress theatre", "target_word": "theatre", "timestamp": 1.1}
            ],
            "issues": [
                {
                    "problem": "Dropped ending consonant in theatre.",
                    "timestamp": 1.1,
                }
            ],
        }
        monkeypatch.setattr(
            "app.tasks.review_task.create_ai_feedback_provider",
            lambda: mock_provider,
        )

        process_review_task(
            submission_id=log.id,
            card_id=card.id,
            lesson_id=lesson.id,
            oss_audio_path="recordings/20260319/1_1700000000.webm",
            realtime_session_id="session-1",
            realtime_final_text="Last week I went to the theatre",
        )

        updated = test_db.query(ReviewLog).filter(ReviewLog.id == log.id).first()
        assert updated is not None
        assert updated.status == "completed"
        assert updated.ai_feedback_json["feedback"]["issues"][0]["timestamp"] == 1.1
        assert updated.ai_feedback_json["feedback"]["suggestions"][0]["timestamp"] == 1.1
        assert updated.ai_feedback_json["transcription"]["text"] == "Last week I went to the movie theater"
        assert updated.ai_feedback_json["transcription"]["timestamps"] == []
        assert updated.ai_feedback_json["realtime_session_id"] == "session-1"

    def test_process_review_task_reference_audio_missing(
        self,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        lesson = sample_deck_tree["lesson"]
        card = sample_deck_tree["cards"][0]
        card.audio_path = None
        test_db.commit()

        log = self._create_processing_log(test_db, card.id, lesson.id)

        monkeypatch.setattr("app.tasks.review_task.SessionLocal", lambda: test_db)
        monkeypatch.setattr(test_db, "close", lambda: None)
        monkeypatch.setattr(
            "app.adapters.oss_adapter.OSSAdapter.generate_signed_url",
            lambda self, object_name, expires=3600: f"https://signed.example.com/{object_name}",
        )

        process_review_task(
            submission_id=log.id,
            card_id=card.id,
            lesson_id=lesson.id,
            oss_audio_path="recordings/20260319/1_1700000000.webm",
            realtime_session_id="session-2",
            realtime_final_text="Last week I went to the theatre",
        )

        updated = test_db.query(ReviewLog).filter(ReviewLog.id == log.id).first()
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "REFERENCE_AUDIO_NOT_FOUND"

    def test_process_review_task_ai_failure(
        self,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        lesson = sample_deck_tree["lesson"]
        card = sample_deck_tree["cards"][0]
        log = self._create_processing_log(test_db, card.id, lesson.id)

        monkeypatch.setattr("app.tasks.review_task.SessionLocal", lambda: test_db)
        monkeypatch.setattr(test_db, "close", lambda: None)
        monkeypatch.setattr(
            "app.adapters.oss_adapter.OSSAdapter.generate_signed_url",
            lambda self, object_name, expires=3600: f"https://signed.example.com/{object_name}",
        )

        mock_provider = Mock()
        mock_provider.generate_single_feedback.side_effect = AIFeedbackError(
            "invalid model response"
        )
        monkeypatch.setattr(
            "app.tasks.review_task.create_ai_feedback_provider",
            lambda: mock_provider,
        )

        process_review_task(
            submission_id=log.id,
            card_id=card.id,
            lesson_id=lesson.id,
            oss_audio_path="recordings/20260319/1_1700000000.webm",
            realtime_session_id="session-3",
            realtime_final_text="Last week I went to the theatre",
        )

        updated = test_db.query(ReviewLog).filter(ReviewLog.id == log.id).first()
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "AI_FEEDBACK_FAILED"
