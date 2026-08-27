"""Review service for training submissions and results."""

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.fsrs_adapter import FSRSAdapter
from app.config import settings
from app.repositories.card_repo import CardRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.srs_repo import SRSRepository
from app.repositories.user_card_fsrs_repo import UserCardFSRSRepository
from app.repositories.user_deck_repo import UserDeckRepository
from app.services.realtime_session_service import get_realtime_session_store
from app.services.submission_trace import log_submission_trace
from app.tasks.review_task import process_review_task
from app.utils.timezone import from_storage_local, storage_now

logger = logging.getLogger(__name__)
NATIVE_SRS_STATES = {"learning", "review", "relearning"}


class ReviewService:
    """Service for handling review submissions and results.

    Manages asynchronous training flow:
    1. Submit review (immediate return with submission_id)
    2. Background processing (ASR + AI + FSRS)
    3. Poll for results
    """

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.card_repo = CardRepository(db)
        self.review_log_repo = ReviewLogRepository(db)
        self.srs_repo = SRSRepository(db)
        self.user_card_fsrs_repo = UserCardFSRSRepository(db)
        self.user_deck_repo = UserDeckRepository(db)
        self.fsrs_adapter = FSRSAdapter()
        self.realtime_store = get_realtime_session_store()

    def _serialize_native_srs(self, srs: Any) -> dict[str, Any] | None:
        """Serialize native SRS data while hiding the derived new bucket."""
        if srs is None or srs.state not in NATIVE_SRS_STATES:
            return None

        due_at = from_storage_local(srs.due, self.db).isoformat()
        return {
            "state": srs.state,
            "difficulty": srs.difficulty,
            "stability": srs.stability,
            "due": due_at,
            "due_at": due_at,
        }

    def submit_card_review(
        self,
        user_id: int,
        lesson_id: int,
        card_id: int,
        oss_audio_path: str,
        realtime_session_id: str,
        user_deck_id: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit a card feedback request (synchronous part).

        Creates a review_log record with status='processing' and
        launches a background task for asynchronous processing.

        Args:
            lesson_id: Lesson deck ID
            card_id: Card ID being reviewed
            oss_audio_path: OSS path to user's audio recording

        Returns:
            Dictionary with:
            - submission_id: Review log ID for polling
            - status: "processing"

        Raises:
            ValueError: If request validation fails
        """
        log_submission_trace(
            logger,
            "submit_received",
            request_id=request_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
        )

        def raise_validation_error(error_message: str) -> None:
            error_code = error_message.split(":", 1)[0]
            log_submission_trace(
                logger,
                "submit_validation_failed",
                level="warning",
                request_id=request_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                error_code=error_code,
                error_message=error_message,
                review_log_committed=False,
            )
            raise ValueError(error_message)

        # Validate card and lesson
        card = self.card_repo.get_by_id(card_id)
        if not card:
            raise_validation_error(f"Card {card_id} not found")

        if card.deck_id != lesson_id:
            raise_validation_error(f"Card {card_id} does not belong to lesson {lesson_id}")

        if user_deck_id is not None:
            user_deck = self.user_deck_repo.get_active_by_id(user_id, user_deck_id)
            if user_deck is None:
                raise_validation_error(f"USER_DECK_NOT_FOUND: {user_deck_id}")
            if not self.user_deck_repo.has_card_membership(user_deck_id, card_id):
                raise_validation_error(
                    f"USER_DECK_CARD_MISMATCH: card {card_id} does not belong to user deck {user_deck_id}"
                )

        # Validate OSS path format
        expected_prefix = (
            f"{(settings.oss_recordings_prefix or 'recordings').strip().strip('/') or 'recordings'}/"
        )
        if not oss_audio_path.startswith(expected_prefix):
            raise_validation_error(
                f"Invalid OSS path. Must start with '{expected_prefix}'"
            )

        # Validate realtime session
        realtime_session = self.realtime_store.get_session(realtime_session_id)
        if not realtime_session:
            raise_validation_error(f"REALTIME_SESSION_NOT_FOUND: {realtime_session_id}")

        if realtime_session.lesson_id != lesson_id or realtime_session.card_id != card_id:
            raise_validation_error(
                "REALTIME_SESSION_NOT_FOUND: session does not match lesson/card context"
            )

        if realtime_session.status == "failed":
            message = realtime_session.error or "Realtime session failed"
            raise_validation_error(f"REALTIME_SESSION_FAILED: {message}")

        if realtime_session.status != "ready" or not realtime_session.final_text.strip():
            raise_validation_error(
                "REALTIME_TRANSCRIPT_NOT_READY: realtime final transcript is not ready"
            )

        if user_deck_id is not None:
            current_srs = self.user_card_fsrs_repo.get_by_user_card(user_id, card_id)
            card_state = self._derive_user_fsrs_state(current_srs)
            quota_bucket = "new" if self._is_user_new_bucket(current_srs) else "review"
        else:
            current_srs = self.srs_repo.get_by_card_id(card_id)
            card_state = self.srs_repo.derive_card_state(current_srs)
            quota_bucket = "new" if self.srs_repo.is_new_bucket(current_srs) else "review"

        # Create review_log with status='processing'
        log_submission_trace(
            logger,
            "review_log_create_started",
            request_id=request_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            review_log_committed=False,
        )
        review_log = self.review_log_repo.create(
            user_id=user_id,
            user_deck_id=user_deck_id,
            card_id=card_id,
            deck_id=lesson_id,
            rating=None,
            result_type="single",
            ai_feedback_json={
                "study_session": {
                    "quota_bucket": quota_bucket,
                    "scheduled_state": card_state,
                }
            },
        )

        # Commit to get the log ID
        self.db.commit()

        submission_id = review_log.id
        log_submission_trace(
            logger,
            "review_log_created",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            review_log_committed=True,
            status="processing",
        )

        # Launch background task
        task_thread = threading.Thread(
            target=process_review_task,
            args=(
                submission_id,
                card_id,
                lesson_id,
                oss_audio_path,
                realtime_session_id,
                realtime_session.final_text.strip(),
                request_id,
            ),
            daemon=True,
        )
        task_thread.start()
        log_submission_trace(
            logger,
            "background_task_started",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            status="processing",
        )

        return {
            "submission_id": submission_id,
            "status": "processing",
        }

    def submit_submission_rating(
        self,
        submission_id: int,
        rating: str,
        user_id: int,
    ) -> dict[str, Any]:
        """Submit rating for a previously created submission.

        Rating is decoupled from AI feedback generation. It only drives
        FSRS scheduling updates and learning statistics.

        Args:
            submission_id: Review log ID returned from submit_card_review
            rating: User rating (again/hard/good/easy)

        Returns:
            Dictionary with updated rating and SRS state.

        Raises:
            ValueError: If submission not found, invalid rating, or submission failed.
        """
        valid_ratings = ["again", "hard", "good", "easy"]
        if rating not in valid_ratings:
            raise ValueError(f"Invalid rating. Must be one of: {valid_ratings}")

        review_log = self.review_log_repo.get_by_id(submission_id)
        if not review_log:
            raise ValueError(f"Submission {submission_id} not found")
        if review_log.user_id != user_id:
            raise ValueError(f"Submission {submission_id} not found")

        if review_log.status == "failed":
            raise ValueError(f"Submission {submission_id} failed")

        if review_log.card_id is None:
            raise ValueError("Cannot submit rating for summary submission")

        current_srs = self.srs_repo.get_by_card_id(review_log.card_id)
        current_user_srs = self.user_card_fsrs_repo.get_by_user_card(user_id, review_log.card_id)
        new_srs_data = self.fsrs_adapter.schedule_card(
            current_user_srs or current_srs,
            rating,
            card_id=review_log.card_id,
        )

        srs = self.srs_repo.upsert(
            card_id=review_log.card_id,
            state=new_srs_data["state"],
            step=new_srs_data["step"],
            stability=new_srs_data["stability"],
            difficulty=new_srs_data["difficulty"],
            due=new_srs_data["due"],
            last_review=new_srs_data["last_review"],
        )
        self.srs_repo.create_review_log(
            card_id=review_log.card_id,
            rating=new_srs_data["review_log"]["rating"],
            review_datetime=new_srs_data["review_log"]["review_datetime"],
            review_duration=new_srs_data["review_log"]["review_duration"],
        )
        self.user_card_fsrs_repo.upsert(
            user_id=user_id,
            card_id=review_log.card_id,
            state=new_srs_data["state"],
            step=new_srs_data["step"],
            stability=new_srs_data["stability"],
            difficulty=new_srs_data["difficulty"],
            due=new_srs_data["due"],
            last_review=new_srs_data["last_review"],
            last_rating=rating,
        )

        review_log.rating = rating
        review_log.submitted_rating = rating
        review_log.rated_at = storage_now(self.db)
        self.db.commit()

        result = {
            "submission_id": submission_id,
            "rating": rating,
            "rating_label": rating,
        }
        native_srs = self._serialize_native_srs(srs)
        if native_srs is not None:
            result["srs"] = native_srs
        return result

    def get_submission_result(self, submission_id: int) -> dict[str, Any]:
        """Get submission result (for polling).

        Args:
            submission_id: Review log ID from submit_card_review

        Returns:
            Dictionary with status and result data:
            - If processing: {submission_id, status: "processing"}
            - If failed: {submission_id, status: "failed", error_code, error_message}
            - If completed: {submission_id, status: "completed", transcription, feedback, srs}

        Raises:
            ValueError: If submission not found
        """
        review_log = self.review_log_repo.get_by_id(submission_id)
        if not review_log:
            raise ValueError(f"Submission {submission_id} not found")

        # Processing status
        if review_log.status == "processing":
            return {
                "submission_id": submission_id,
                "status": "processing",
            }

        # Failed status
        if review_log.status == "failed":
            return {
                "submission_id": submission_id,
                "status": "failed",
                "error_code": review_log.error_code,
                "error_message": review_log.error_message,
            }

        # Completed status
        if review_log.status == "completed":
            result = {
                "submission_id": submission_id,
                "status": "completed",
                "result_type": "single",
            }

            # Add transcription and feedback from ai_feedback_json
            if review_log.ai_feedback_json:
                result["transcription"] = review_log.ai_feedback_json.get("transcription", {})
                result["feedback"] = review_log.ai_feedback_json.get("feedback", {})
                result["oss_audio_path"] = review_log.ai_feedback_json.get("oss_path")

            # SRS is only returned after rating is submitted (decoupled flow)
            if review_log.rating and review_log.card_id is not None:
                srs = (
                    self.user_card_fsrs_repo.get_by_user_card(review_log.user_id, review_log.card_id)
                    or self.srs_repo.get_by_card_id(review_log.card_id)
                )
                native_srs = self._serialize_native_srs(srs)
                if native_srs is not None:
                    result["srs"] = native_srs

            return result

        # Unknown status (should not happen)
        return {
            "submission_id": submission_id,
            "status": review_log.status,
        }

    def list_submissions(
        self,
        user_id: int,
        lesson_id: int | None = None,
        user_deck_id: int | None = None,
        card_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List submission history for a lesson or user deck."""
        submissions = self.review_log_repo.list_single_submissions(
            user_id=user_id,
            lesson_id=lesson_id,
            user_deck_id=user_deck_id,
            card_id=card_id,
        )
        result: list[dict[str, Any]] = []
        for submission in submissions:
            feedback_json = submission.ai_feedback_json or {}
            result.append(
                {
                    "submission_id": submission.id,
                    "card_id": submission.card_id,
                    "lesson_id": submission.deck_id,
                    "user_deck_id": submission.user_deck_id,
                    "status": submission.status,
                    "error_code": submission.error_code,
                    "error_message": submission.error_message,
                    "created_at": from_storage_local(submission.created_at, self.db).isoformat(),
                    "oss_audio_path": feedback_json.get("oss_path"),
                    "transcription": feedback_json.get("transcription"),
                    "feedback": feedback_json.get("feedback"),
                }
            )

        return result

    @staticmethod
    def _is_user_new_bucket(srs: Any) -> bool:
        """Whether a per-user FSRS row is still in the business new bucket."""
        return srs is None or srs.last_review is None

    def _derive_user_fsrs_state(self, srs: Any) -> str:
        """Return API-facing state for per-user FSRS rows without exposing synthetic new."""
        if self._is_user_new_bucket(srs):
            return "learning"
        return srs.state
