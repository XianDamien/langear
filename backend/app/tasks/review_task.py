"""Background task for processing review submissions asynchronously."""

import logging
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.adapters.ai_feedback_adapter import create_ai_feedback_provider
from app.adapters.oss_adapter import OSSAdapter
from app.database import SessionLocal
from app.exceptions import AIFeedbackError
from app.repositories.card_repo import CardRepository
from app.repositories.review_log_repo import ReviewLogRepository
from app.services.submission_trace import log_submission_trace

logger = logging.getLogger(__name__)


def _resolve_audio_url(
    oss_adapter: OSSAdapter,
    audio_path: str,
    expires: int = 3600,
) -> str:
    """Resolve an audio path to a usable URL."""
    if not audio_path or not isinstance(audio_path, str):
        raise ValueError("Audio path is empty")

    normalized = audio_path.strip()
    if normalized.startswith(("http://", "https://")):
        return normalized

    if normalized.startswith("oss://"):
        parsed = urlparse(normalized)
        object_name = parsed.path.lstrip("/")
        if not object_name:
            raise ValueError(f"Invalid OSS URL: {audio_path}")
        return oss_adapter.generate_signed_url(object_name, expires=expires)

    return oss_adapter.generate_signed_url(normalized, expires=expires)


def process_review_task(
    submission_id: int,
    card_id: int,
    lesson_id: int,
    oss_audio_path: str,
    realtime_session_id: str,
    realtime_final_text: str,
    request_id: str | None = None,
) -> None:
    """Process a single review submission asynchronously.

    This function runs in a background thread and handles:
    1. Resolving user/reference audio URLs
    2. Keeping realtime ASR final transcript as a submission precondition
    3. Gemini dual-audio feedback generation
    4. Database updates (review_log)

    Args:
        submission_id: Review log ID (submission ID)
        card_id: Card ID being reviewed
        lesson_id: Lesson deck ID
        oss_audio_path: OSS path to user's audio recording
        realtime_session_id: Realtime ASR session id
        realtime_final_text: Realtime ASR final transcript text used only for readiness validation

    Returns:
        None (updates database directly)
    """
    db: Session = SessionLocal()

    try:
        log_submission_trace(
            logger,
            "task_started",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            status="processing",
        )

        # Initialize adapters and repositories
        oss_adapter = OSSAdapter()
        card_repo = CardRepository(db)
        review_log_repo = ReviewLogRepository(db)

        # Step 1: Resolve user audio URL
        logger.info(f"Resolving user audio URL for submission {submission_id}")
        try:
            user_audio_url = _resolve_audio_url(
                oss_adapter=oss_adapter,
                audio_path=oss_audio_path,
                expires=3600,
            )
        except Exception as e:
            logger.error(f"Failed to resolve user audio for submission {submission_id}: {e}")
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="USER_AUDIO_ACCESS_FAILED",
                error_message=str(e),
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="USER_AUDIO_ACCESS_FAILED",
                error_message=str(e),
            )
            return

        log_submission_trace(
            logger,
            "user_audio_resolved",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            status="processing",
        )

        # Step 2: Get card and resolve reference audio URL
        card = card_repo.get_by_id(card_id)
        if not card:
            logger.error(f"Card {card_id} not found for submission {submission_id}")
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="CARD_NOT_FOUND",
                error_message=f"Card {card_id} not found",
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="CARD_NOT_FOUND",
                error_message=f"Card {card_id} not found",
            )
            return

        reference_audio_path = card.audio_path
        if not reference_audio_path:
            logger.error(f"Reference audio missing for card {card_id}")
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="REFERENCE_AUDIO_NOT_FOUND",
                error_message=f"Card {card_id} has no reference audio path",
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="REFERENCE_AUDIO_NOT_FOUND",
                error_message=f"Card {card_id} has no reference audio path",
            )
            return

        try:
            reference_audio_url = _resolve_audio_url(
                oss_adapter=oss_adapter,
                audio_path=reference_audio_path,
                expires=3600,
            )
        except Exception as e:
            logger.error(f"Failed to resolve reference audio for card {card_id}: {e}")
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="REFERENCE_AUDIO_NOT_FOUND",
                error_message=str(e),
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="REFERENCE_AUDIO_NOT_FOUND",
                error_message=str(e),
            )
            return

        log_submission_trace(
            logger,
            "reference_audio_resolved",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            status="processing",
        )

        # Step 3: Realtime transcript remains a submission safeguard, but the
        # displayed transcription now comes from Gemini.
        if not realtime_final_text.strip():
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="REALTIME_TRANSCRIPT_NOT_READY",
                error_message="Realtime final transcript is empty",
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="REALTIME_TRANSCRIPT_NOT_READY",
                error_message="Realtime final transcript is empty",
            )
            return

        # Step 4: AI feedback with dual-audio input
        logger.info(f"Generating AI feedback for submission {submission_id}")
        try:
            ai_provider = create_ai_feedback_provider()
            feedback = ai_provider.generate_single_feedback(
                front_text=card.front_text,
                user_audio_url=user_audio_url,
                reference_audio_url=reference_audio_url,
            )
        except AIFeedbackError as e:
            logger.error(f"AI feedback failed for submission {submission_id}: {str(e)}")
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="AI_FEEDBACK_FAILED",
                error_message=str(e),
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="warning",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="AI_FEEDBACK_FAILED",
                error_message=str(e),
            )
            return

        transcription_text = feedback.pop("transcription_text")

        review_log = review_log_repo.get_by_id(submission_id)
        study_session_meta: dict[str, Any] | None = None
        if review_log and isinstance(review_log.ai_feedback_json, dict):
            metadata = review_log.ai_feedback_json.get("study_session")
            if isinstance(metadata, dict):
                study_session_meta = metadata

        # Step 5: Update review_log with completed status
        logger.info(f"Finalizing submission {submission_id}")
        ai_feedback_json: dict[str, Any] = {
            "transcription": {
                "text": transcription_text,
                "timestamps": [],
            },
            "feedback": feedback,
            "oss_path": oss_audio_path,
            "realtime_session_id": realtime_session_id,
            "reference_audio_path": reference_audio_path,
        }
        if study_session_meta is not None:
            ai_feedback_json["study_session"] = study_session_meta

        review_log_repo.update_status(
            log_id=submission_id,
            status="completed",
            ai_feedback_json=ai_feedback_json,
        )

        # Commit all changes
        db.commit()
        log_submission_trace(
            logger,
            "task_completed",
            request_id=request_id,
            submission_id=submission_id,
            lesson_id=lesson_id,
            card_id=card_id,
            realtime_session_id=realtime_session_id,
            oss_audio_path=oss_audio_path,
            status="completed",
        )

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in submission {submission_id}: {str(e)}", exc_info=True)
        try:
            review_log_repo = ReviewLogRepository(db)
            review_log_repo.update_status(
                log_id=submission_id,
                status="failed",
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )
            db.commit()
            log_submission_trace(
                logger,
                "task_failed",
                level="error",
                request_id=request_id,
                submission_id=submission_id,
                lesson_id=lesson_id,
                card_id=card_id,
                realtime_session_id=realtime_session_id,
                oss_audio_path=oss_audio_path,
                status="failed",
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )
        except Exception as commit_error:
            logger.error(f"Failed to update error status: {str(commit_error)}")
            db.rollback()

    finally:
        db.close()
