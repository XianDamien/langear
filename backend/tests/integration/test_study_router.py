"""Integration tests for study submissions API.

Tests:
- POST /api/v1/study/submissions (create async feedback job)
- GET /api/v1/study/submissions/{id} (poll result)
- POST /api/v1/study/submissions/{id}/rating (submit FSRS rating)
"""

import base64
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.review_log import ReviewLog
from app.models.user_card_fsrs import UserCardFSRS
from app.models.user_card_srs import UserCardSRS
from app.services.realtime_session_service import get_realtime_session_store
from app.utils.timezone import storage_now


def _make_ready_realtime_session(lesson_id: int, card_id: int) -> str:
    store = get_realtime_session_store()
    session = store.create_session(
        lesson_id=lesson_id,
        card_id=card_id,
        model="qwen3-asr-flash-realtime",
    )
    sample_chunk = base64.b64encode(b"fake-audio-bytes").decode("utf-8")
    store.append_audio_chunk(session.id, sample_chunk)
    store.commit_session(session.id)
    return session.id


@pytest.mark.integration
class TestStudyRouter:
    def test_submit_submission_requires_realtime_session_id(
        self,
        client: TestClient,
        sample_deck_tree,
        monkeypatch,
    ):
        """POST /study/submissions should reject requests without realtime_session_id."""

        # Avoid launching a real background thread in tests.
        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id

        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
            },
        )

        assert resp.status_code == 422

    def test_submit_submission_realtime_not_ready(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        """POST /study/submissions should block when realtime session is not ready."""

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        session = store.create_session(
            lesson_id=lesson_id,
            card_id=card_id,
            model="qwen3-asr-flash-realtime",
        )

        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": session.id,
            },
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "REALTIME_TRANSCRIPT_NOT_READY"
        assert test_db.query(ReviewLog).count() == 0

    def test_submit_submission_realtime_failed(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        """POST /study/submissions should block when realtime session failed."""

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        session = store.create_session(
            lesson_id=lesson_id,
            card_id=card_id,
            model="qwen3-asr-flash-realtime",
        )
        store.mark_session_failed(session.id, "manual failure")

        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": session.id,
            },
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "REALTIME_SESSION_FAILED"
        assert test_db.query(ReviewLog).count() == 0

    def test_submit_submission_without_rating_success(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        all_adapters_mocked,
        monkeypatch,
    ):
        """POST /study/submissions should accept payload without rating."""

        # Avoid launching a real background thread in tests.
        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)

        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "request_id" in body
        assert body["data"]["status"] == "processing"
        submission_id = body["data"]["submission_id"]
        assert isinstance(submission_id, int)

        review_log = test_db.query(ReviewLog).filter(ReviewLog.id == submission_id).first()
        assert review_log is not None
        assert review_log.status == "processing"
        assert review_log.result_type == "single"
        assert review_log.deck_id == lesson_id
        assert review_log.card_id == card_id
        assert review_log.ai_feedback_json["study_session"]["quota_bucket"] == "new"
        assert review_log.ai_feedback_json["study_session"]["scheduled_state"] == "learning"

    def test_submit_submission_accepts_configured_test_prefix(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        """POST /study/submissions should accept the configured recordings prefix."""

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)
        monkeypatch.setattr("app.services.review_service.settings.oss_recordings_prefix", "test/recordings")

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)

        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "test/recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        submission_id = body["data"]["submission_id"]
        review_log = test_db.query(ReviewLog).filter(ReviewLog.id == submission_id).first()
        assert review_log is not None
        assert review_log.status == "processing"

    def test_submit_submission_uses_review_bucket_for_reviewed_card(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        all_adapters_mocked,
        monkeypatch,
    ):
        """POST /study/submissions should derive review bucket from native SRS."""

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        srs = test_db.query(UserCardSRS).filter(UserCardSRS.card_id == card_id).one()
        srs.state = "review"
        srs.step = None
        srs.stability = 3.0
        srs.difficulty = 4.0
        srs.due = storage_now() - timedelta(hours=1)
        srs.last_review = storage_now() - timedelta(days=1)
        test_db.commit()

        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)
        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )

        assert resp.status_code == 200
        submission_id = resp.json()["data"]["submission_id"]
        review_log = test_db.query(ReviewLog).filter(ReviewLog.id == submission_id).one()
        assert review_log.ai_feedback_json["study_session"]["quota_bucket"] == "review"
        assert review_log.ai_feedback_json["study_session"]["scheduled_state"] == "review"

    def test_submit_submission_with_user_deck_persists_user_deck_id(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        monkeypatch,
    ):
        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        selection = client.put(
            "/api/v1/user-decks/selection",
            json={"origin_deck_ids": [lesson_id]},
        )
        assert selection.status_code == 200
        user_deck_id = selection.json()["data"]["user_decks"][0]["id"]

        now = storage_now()
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=card_id,
                state="review",
                step=None,
                due=now - timedelta(minutes=10),
                last_review=now - timedelta(days=1),
            )
        )
        test_db.commit()

        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)
        resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "user_deck_id": user_deck_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )

        assert resp.status_code == 200
        submission_id = resp.json()["data"]["submission_id"]
        review_log = test_db.query(ReviewLog).filter(ReviewLog.id == submission_id).one()
        assert review_log.user_deck_id == user_deck_id
        assert review_log.deck_id == lesson_id
        assert review_log.ai_feedback_json["study_session"]["quota_bucket"] == "review"

    def test_submit_rating_updates_srs(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        all_adapters_mocked,
        monkeypatch,
    ):
        """POST /study/submissions/{id}/rating should update SRS and rating."""

        # Avoid launching a real background thread in tests.
        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)

        create_resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )
        assert create_resp.status_code == 200
        submission_id = create_resp.json()["data"]["submission_id"]

        rate_resp = client.post(
            f"/api/v1/study/submissions/{submission_id}/rating",
            json={"rating": "good"},
        )
        assert rate_resp.status_code == 200
        data = rate_resp.json()["data"]
        assert data["submission_id"] == submission_id
        assert data["rating"] == "good"
        assert data["srs"]["state"] in {"learning", "review", "relearning"}
        assert data["srs"]["state"] != "new"
        assert "srs" in data
        assert "due" in data["srs"]
        assert data["srs"]["due_at"] == data["srs"]["due"]

    def test_submit_numeric_rating_updates_srs(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
        all_adapters_mocked,
        monkeypatch,
    ):
        """POST /study/submissions/{id}/rating should accept FSRS numeric ratings."""

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                return None

        monkeypatch.setattr("app.services.review_service.threading.Thread", _FakeThread)

        store = get_realtime_session_store()
        store.clear()

        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id
        realtime_session_id = _make_ready_realtime_session(lesson_id, card_id)

        create_resp = client.post(
            "/api/v1/study/submissions",
            json={
                "lesson_id": lesson_id,
                "card_id": card_id,
                "oss_audio_path": "recordings/20260209/test.webm",
                "realtime_session_id": realtime_session_id,
            },
        )
        assert create_resp.status_code == 200
        submission_id = create_resp.json()["data"]["submission_id"]

        rate_resp = client.post(
            f"/api/v1/study/submissions/{submission_id}/rating",
            json={"rating": 3},
        )
        assert rate_resp.status_code == 200
        data = rate_resp.json()["data"]
        assert data["submission_id"] == submission_id
        assert data["rating"] == "good"
        assert data["rating_label"] == "good"
        assert "srs" in data
        assert data["srs"]["state"] in {"learning", "review", "relearning"}
        assert data["srs"]["due_at"] == data["srs"]["due"]

    def test_get_submission_completed_includes_issues(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/submissions/{id} should include feedback.issues field."""
        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id

        review_log = ReviewLog(
            card_id=card_id,
            deck_id=lesson_id,
            rating=None,
            result_type="single",
            status="completed",
            ai_feedback_json={
                "transcription": {
                    "text": "Last week I went to the theatre.",
                    "timestamps": [],
                },
                "feedback": {
                    "pronunciation": "Good",
                    "completeness": "Complete",
                    "fluency": "Fluent",
                    "suggestions": [],
                    "issues": [
                        {"problem": "Missing ending sound", "timestamp": 0.9}
                    ],
                },
                "oss_path": "recordings/20260319/test.webm",
            },
        )
        test_db.add(review_log)
        test_db.commit()
        test_db.refresh(review_log)

        resp = client.get(f"/api/v1/study/submissions/{review_log.id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert "issues" in data["feedback"]
        assert data["feedback"]["issues"][0]["timestamp"] == 0.9

    def test_get_submission_completed_returns_native_srs_state(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/submissions/{id} should never expose derived new as srs.state."""
        lesson_id = sample_deck_tree["lesson"].id
        card_id = sample_deck_tree["cards"][0].id

        srs = test_db.query(UserCardSRS).filter(UserCardSRS.card_id == card_id).one()
        srs.state = "review"
        srs.step = None
        srs.stability = 4.0
        srs.difficulty = 3.5
        srs.due = storage_now() + timedelta(days=2)
        srs.last_review = storage_now() - timedelta(hours=6)

        review_log = ReviewLog(
            card_id=card_id,
            deck_id=lesson_id,
            rating="good",
            result_type="single",
            status="completed",
            ai_feedback_json={
                "transcription": {"text": "done", "timestamps": []},
                "feedback": {"issues": [], "suggestions": []},
                "oss_path": "recordings/20260319/test.webm",
            },
        )
        test_db.add(review_log)
        test_db.commit()
        test_db.refresh(review_log)

        resp = client.get(f"/api/v1/study/submissions/{review_log.id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["srs"]["state"] in {"learning", "review", "relearning"}
        assert data["srs"]["state"] != "new"

    def test_list_submissions_returns_processing_failed_and_completed(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/submissions should return mixed statuses for a lesson."""
        lesson_id = sample_deck_tree["lesson"].id
        card_one_id = sample_deck_tree["cards"][0].id
        card_two_id = sample_deck_tree["cards"][1].id

        logs = [
            ReviewLog(
                card_id=card_one_id,
                deck_id=lesson_id,
                rating=None,
                result_type="single",
                status="processing",
                ai_feedback_json={},
            ),
            ReviewLog(
                card_id=card_one_id,
                deck_id=lesson_id,
                rating=None,
                result_type="single",
                status="failed",
                error_code="REALTIME_SESSION_FAILED",
                error_message="Realtime session failed",
                ai_feedback_json={},
            ),
            ReviewLog(
                card_id=card_two_id,
                deck_id=lesson_id,
                rating=None,
                result_type="single",
                status="completed",
                ai_feedback_json={
                    "transcription": {
                        "text": "Completed transcript",
                        "timestamps": [],
                    },
                    "feedback": {
                        "pronunciation": "Good",
                        "completeness": "Complete",
                        "fluency": "Fluent",
                        "suggestions": [],
                        "issues": [],
                    },
                    "oss_path": "recordings/20260319/completed.webm",
                },
            ),
        ]
        test_db.add_all(logs)
        test_db.commit()

        resp = client.get(f"/api/v1/study/submissions?lesson_id={lesson_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert [item["status"] for item in data] == ["completed", "failed", "processing"]
        assert data[0]["transcription"]["text"] == "Completed transcript"
        assert data[0]["feedback"]["pronunciation"] == "Good"
        assert data[1]["error_code"] == "REALTIME_SESSION_FAILED"
        assert data[2]["submission_id"] == logs[0].id

    def test_list_submissions_filters_by_card_id(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/submissions should support card_id filtering."""
        lesson_id = sample_deck_tree["lesson"].id
        card_one_id = sample_deck_tree["cards"][0].id
        card_two_id = sample_deck_tree["cards"][1].id

        test_db.add_all(
            [
                ReviewLog(
                    card_id=card_one_id,
                    deck_id=lesson_id,
                    rating=None,
                    result_type="single",
                    status="failed",
                    error_code="AI_FEEDBACK_FAILED",
                    error_message="bad output",
                    ai_feedback_json={},
                ),
                ReviewLog(
                    card_id=card_two_id,
                    deck_id=lesson_id,
                    rating=None,
                    result_type="single",
                    status="completed",
                    ai_feedback_json={
                        "transcription": {"text": "other card", "timestamps": []},
                        "feedback": {
                            "pronunciation": "Good",
                            "completeness": "Complete",
                            "fluency": "Fluent",
                            "suggestions": [],
                            "issues": [],
                        },
                        "oss_path": "recordings/20260319/other.webm",
                    },
                ),
            ]
        )
        test_db.commit()

        resp = client.get(
            f"/api/v1/study/submissions?lesson_id={lesson_id}&card_id={card_one_id}"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["card_id"] == card_one_id
        assert data[0]["status"] == "failed"
