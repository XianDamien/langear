"""Unit tests for the native-FSRS adapter."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fsrs import Rating, State

from app.adapters.fsrs_adapter import FSRSAdapter
from app.exceptions import InvalidRatingError, SRSUpdateError
from app.models.user_card_srs import UserCardSRS
from app.utils.timezone import storage_now


def _mock_review_output(
    *,
    state: State,
    due: datetime,
    step: int | None,
    stability: float | None,
    difficulty: float | None,
    last_review: datetime,
    rating: Rating,
    card_id: int = 1,
):
    card = Mock()
    card.card_id = card_id
    card.state = state
    card.step = step
    card.stability = stability
    card.difficulty = difficulty
    card.due = due
    card.last_review = last_review

    review_log = Mock()
    review_log.card_id = card_id
    review_log.rating = rating
    review_log.review_datetime = last_review
    review_log.review_duration = 1200
    return card, review_log


@pytest.mark.unit
class TestFSRSAdapter:
    @pytest.fixture
    def fsrs_adapter(self):
        return FSRSAdapter()

    def test_rating_from_string(self, fsrs_adapter):
        assert fsrs_adapter.rating_from_string("again") == Rating.Again
        assert fsrs_adapter.rating_from_string("hard") == Rating.Hard
        assert fsrs_adapter.rating_from_string("good") == Rating.Good
        assert fsrs_adapter.rating_from_string("easy") == Rating.Easy

    def test_rating_from_string_invalid(self, fsrs_adapter):
        with pytest.raises(InvalidRatingError):
            fsrs_adapter.rating_from_string("invalid")

    def test_state_conversion_roundtrip(self, fsrs_adapter):
        for state in [State.Learning, State.Review, State.Relearning]:
            state_str = fsrs_adapter.state_to_string(state)
            assert fsrs_adapter.string_to_state(state_str) == state

    def test_to_fsrs_card_requires_card_id_for_missing_srs(self, fsrs_adapter):
        with pytest.raises(SRSUpdateError, match="card_id is required"):
            fsrs_adapter.to_fsrs_card(None)

    def test_to_fsrs_card_maps_native_snapshot(self, fsrs_adapter):
        current_srs = Mock(spec=UserCardSRS)
        current_srs.card_id = 7
        current_srs.state = "review"
        current_srs.step = None
        current_srs.stability = 10.0
        current_srs.difficulty = 4.8
        current_srs.due = datetime(2026, 3, 22, 10, 0, 0)
        current_srs.last_review = datetime(2026, 3, 21, 10, 0, 0)

        fsrs_card = fsrs_adapter.to_fsrs_card(current_srs)

        assert fsrs_card.card_id == 7
        assert fsrs_card.state == State.Review
        assert fsrs_card.step is None
        assert fsrs_card.stability == 10.0
        assert fsrs_card.difficulty == 4.8
        assert fsrs_card.due.tzinfo == timezone.utc
        assert fsrs_card.last_review.tzinfo == timezone.utc

    def test_schedule_card_new_bucket_returns_native_card_and_review_log(self, fsrs_adapter):
        now = datetime.now(timezone.utc)
        updated_card, review_log = _mock_review_output(
            state=State.Learning,
            due=now + timedelta(minutes=1),
            step=1,
            stability=1.2,
            difficulty=5.5,
            last_review=now,
            rating=Rating.Good,
            card_id=42,
        )

        with patch.object(fsrs_adapter.scheduler, "review_card", return_value=(updated_card, review_log)):
            result = fsrs_adapter.schedule_card(None, "good", card_id=42)

        assert result["state"] == "learning"
        assert result["step"] == 1
        assert result["stability"] == 1.2
        assert result["difficulty"] == 5.5
        assert result["last_review"] == now
        assert result["review_log"]["card_id"] == 42
        assert result["review_log"]["rating"] == 3

    def test_schedule_card_existing_review_card(self, fsrs_adapter):
        now = datetime.now(timezone.utc)
        current_srs = Mock(spec=UserCardSRS)
        current_srs.card_id = 9
        current_srs.state = "review"
        current_srs.step = None
        current_srs.stability = 10.0
        current_srs.difficulty = 5.0
        current_srs.due = (now - timedelta(days=1)).replace(tzinfo=None)
        current_srs.last_review = (now - timedelta(days=5)).replace(tzinfo=None)

        updated_card, review_log = _mock_review_output(
            state=State.Review,
            due=now + timedelta(days=10),
            step=None,
            stability=15.0,
            difficulty=4.5,
            last_review=now,
            rating=Rating.Good,
            card_id=9,
        )

        with patch.object(fsrs_adapter.scheduler, "review_card", return_value=(updated_card, review_log)) as patched:
            result = fsrs_adapter.schedule_card(current_srs, "good")

        patched.assert_called_once()
        scheduled_card = patched.call_args.args[0]
        assert scheduled_card.state == State.Review
        assert scheduled_card.card_id == 9
        assert result["state"] == "review"
        assert result["step"] is None
        assert result["due"] == now + timedelta(days=10)

    def test_schedule_card_relearning_transition(self, fsrs_adapter):
        now = datetime.now(timezone.utc)
        current_srs = Mock(spec=UserCardSRS)
        current_srs.card_id = 5
        current_srs.state = "review"
        current_srs.step = None
        current_srs.stability = 12.0
        current_srs.difficulty = 5.0
        current_srs.due = (now - timedelta(days=1)).replace(tzinfo=None)
        current_srs.last_review = (now - timedelta(days=6)).replace(tzinfo=None)

        updated_card, review_log = _mock_review_output(
            state=State.Relearning,
            due=now + timedelta(minutes=10),
            step=0,
            stability=2.0,
            difficulty=6.0,
            last_review=now,
            rating=Rating.Again,
            card_id=5,
        )

        with patch.object(fsrs_adapter.scheduler, "review_card", return_value=(updated_card, review_log)):
            result = fsrs_adapter.schedule_card(current_srs, "again")

        assert result["state"] == "relearning"
        assert result["step"] == 0
        assert result["review_log"]["rating"] == 1

    def test_schedule_card_preserves_utc_due_and_last_review(self, fsrs_adapter):
        now = datetime.now(timezone.utc)
        updated_card, review_log = _mock_review_output(
            state=State.Review,
            due=now + timedelta(days=3),
            step=None,
            stability=8.5,
            difficulty=4.2,
            last_review=now,
            rating=Rating.Good,
            card_id=3,
        )

        with patch.object(fsrs_adapter.scheduler, "review_card", return_value=(updated_card, review_log)):
            result = fsrs_adapter.schedule_card(None, "good", card_id=3)

        assert result["due"].tzinfo == timezone.utc
        assert result["last_review"].tzinfo == timezone.utc
        assert result["review_log"]["review_datetime"].tzinfo == timezone.utc

    def test_schedule_card_invalid_rating_propagates(self, fsrs_adapter):
        with pytest.raises(InvalidRatingError):
            fsrs_adapter.schedule_card(None, "bad-rating", card_id=1)

    def test_schedule_card_wraps_scheduler_errors(self, fsrs_adapter):
        current_srs = Mock(spec=UserCardSRS)
        current_srs.card_id = 1
        current_srs.state = "review"
        current_srs.step = None
        current_srs.stability = 10.0
        current_srs.difficulty = 5.0
        current_srs.due = storage_now()
        current_srs.last_review = storage_now()

        with patch.object(fsrs_adapter.scheduler, "review_card", side_effect=Exception("boom")):
            with pytest.raises(SRSUpdateError, match="FSRS scheduling failed: boom"):
                fsrs_adapter.schedule_card(current_srs, "good")
