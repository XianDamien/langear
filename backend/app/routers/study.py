"""Study router for training submissions and results."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import get_current_user_id
from app.services.review_service import ReviewService

router = APIRouter(prefix="/api/v1/study", tags=["Study"])
logger = logging.getLogger(__name__)


class SubmissionRequest(BaseModel):
    """Request model for submitting a card review."""

    lesson_id: int
    card_id: int
    oss_audio_path: str
    realtime_session_id: str
    user_deck_id: int | None = None


class RatingRequest(BaseModel):
    """Request model for submitting a rating for an existing submission."""

    rating: int | str


RATING_LABEL_MAP = {
    1: "again",
    2: "hard",
    3: "good",
    4: "easy",
}


def _normalize_rating(rating: int | str) -> str:
    """Normalize legacy string and FSRS numeric ratings to labels."""
    if isinstance(rating, int):
        normalized = RATING_LABEL_MAP.get(rating)
        if normalized is None:
            raise ValueError("Invalid rating. Must be one of: 1, 2, 3, 4")
        return normalized

    normalized = rating.strip().lower()
    if normalized in RATING_LABEL_MAP.values():
        return normalized

    if normalized.isdigit():
        return _normalize_rating(int(normalized))

    raise ValueError("Invalid rating. Must be one of: again, hard, good, easy")


@router.post("/submissions")
def submit_review(
    request: SubmissionRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Submit a card feedback job (asynchronous - returns immediately).

    Frontend flow:
    1. Upload audio to OSS using STS credentials
    2. Call this endpoint with OSS path
    3. Poll /submissions/{id} for result

    Args:
        request: Submission request with lesson_id, card_id, oss_audio_path

    Returns:
        Response with submission ID:
        - request_id: Unique request ID
        - data:
            - submission_id: ID for polling results
            - status: "processing"

    Raises:
        400: If invalid OSS path
        404: If card not found or invalid lesson
    """
    request_id = str(uuid.uuid4())

    try:
        review_service = ReviewService(db)
        result = review_service.submit_card_review(
            user_id=user_id,
            lesson_id=request.lesson_id,
            card_id=request.card_id,
            oss_audio_path=request.oss_audio_path,
            realtime_session_id=request.realtime_session_id,
            user_deck_id=request.user_deck_id,
            request_id=request_id,
        )

        return {
            "request_id": request_id,
            "data": result,
        }

    except ValueError as e:
        error_message = str(e)

        # Determine error code
        if "oss" in error_message.lower():
            error_code = "INVALID_OSS_PATH"
        elif "REALTIME_SESSION_NOT_FOUND" in error_message:
            error_code = "REALTIME_SESSION_NOT_FOUND"
        elif "REALTIME_TRANSCRIPT_NOT_READY" in error_message:
            error_code = "REALTIME_TRANSCRIPT_NOT_READY"
        elif "REALTIME_SESSION_FAILED" in error_message:
            error_code = "REALTIME_SESSION_FAILED"
        elif "not found" in error_message.lower():
            error_code = "CARD_NOT_FOUND"
        else:
            error_code = "INVALID_REQUEST"

        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
            },
        )


@router.post("/submissions/{submission_id}/rating")
def submit_rating(
    submission_id: int,
    request: RatingRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Submit rating for a submission.

    Rating is decoupled from AI feedback generation. Submissions can be created
    without rating to start ASR+LLM evaluation immediately.

    Response contract:
    - data.srs.state only returns native FSRS states:
      learning | review | relearning
    """
    request_id = str(uuid.uuid4())

    try:
        review_service = ReviewService(db)
        result = review_service.submit_submission_rating(
            submission_id=submission_id,
            rating=_normalize_rating(request.rating),
            user_id=user_id,
        )
        return {
            "request_id": request_id,
            "data": result,
        }

    except ValueError as e:
        error_message = str(e)
        if "rating" in error_message.lower():
            error_code = "INVALID_RATING"
        elif "not found" in error_message.lower():
            error_code = "SUBMISSION_NOT_FOUND"
        elif "failed" in error_message.lower():
            error_code = "SUBMISSION_FAILED"
        else:
            error_code = "INVALID_REQUEST"

        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
            },
        )


@router.get("/submissions")
def get_submission_history(
    lesson_id: int | None = Query(default=None),
    user_deck_id: int | None = Query(default=None),
    card_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """List recent submissions for a lesson/card."""
    request_id = str(uuid.uuid4())
    if lesson_id is None and user_deck_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "lesson_id or user_deck_id is required",
                },
            },
        )
    if lesson_id is not None and user_deck_id is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "lesson_id and user_deck_id cannot be combined",
                },
            },
        )
    review_service = ReviewService(db)
    result = review_service.list_submissions(
        user_id=user_id,
        lesson_id=lesson_id,
        user_deck_id=user_deck_id,
        card_id=card_id,
    )
    logger.info(
        "Listed %s submissions for lesson=%s user_deck=%s card=%s request_id=%s",
        len(result),
        lesson_id,
        user_deck_id,
        card_id,
        request_id,
    )
    return {
        "request_id": request_id,
        "data": result,
    }


@router.get("/submissions/{submission_id}")
def get_submission_result(
    submission_id: int,
    db: Session = Depends(get_db),
):
    """Poll for submission result (for frontend polling).

    Frontend should poll this endpoint every 1-2 seconds after submission.
    Recommended timeout: 30 seconds (stop polling but don't block user).

    Args:
        submission_id: Submission ID from submit_review

    Returns:
        Response with submission status and results:
        - request_id: Unique request ID
        - data:
            - submission_id: Submission ID
            - status: "processing" | "completed" | "failed"
            - [if completed]: transcription, feedback, srs
            - [if completed and srs present]: srs.state only returns
              learning | review | relearning
            - [if failed]: error_code, error_message

    Raises:
        404: If submission not found
    """
    request_id = str(uuid.uuid4())

    try:
        review_service = ReviewService(db)
        result = review_service.get_submission_result(submission_id)

        return {
            "request_id": request_id,
            "data": result,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "SUBMISSION_NOT_FOUND",
                    "message": str(e),
                },
            },
        )
