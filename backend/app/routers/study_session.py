"""Study-session router for scheduled learning entrypoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import get_current_user_id
from app.services.study_session_service import StudySessionService

router = APIRouter(prefix="/api/v1/study", tags=["Study"])


def _parse_source_scope(value: str | None) -> list[int] | None:
    """Parse a comma-separated source scope query parameter."""
    if value is None:
        return None

    raw_parts = [part.strip() for part in value.split(",")]
    if not raw_parts or any(not part for part in raw_parts):
        raise ValueError("source_scope must be a comma-separated list of source deck ids")

    try:
        return [int(part) for part in raw_parts]
    except ValueError as exc:
        raise ValueError("source_scope must contain only integer source deck ids") from exc


@router.get("/session")
def get_study_session(
    source_scope: str | None = None,
    lesson_id: int | None = None,
    user_deck_id: int | None = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Return the scheduled study session for the current Beijing business day.

    Response cards keep public native FSRS card_state values:
    learning | review | relearning

    Each card also includes:
    - is_new_card: whether the card still belongs to the derived initial-card bucket
    - due_at: server_time for new cards, native SRS due for others
    - last_review_at: null for new cards, last completed review time otherwise
    """
    request_id = str(uuid.uuid4())

    try:
        if lesson_id is not None and user_deck_id is not None:
            raise ValueError("lesson_id and user_deck_id cannot be combined")

        scope_ids = _parse_source_scope(source_scope)
        session_data = StudySessionService(db).get_session(
            user_id=user_id,
            source_scope=scope_ids,
            lesson_id=lesson_id,
            user_deck_id=user_deck_id,
        )
        return {
            "request_id": request_id,
            "data": session_data,
        }
    except LookupError as exc:
        error_code = "USER_DECK_NOT_FOUND" if "User deck" in str(exc) else "LESSON_NOT_FOUND"
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": error_code,
                    "message": str(exc),
                },
            },
        )
    except ValueError as exc:
        error_code = "INVALID_SOURCE_SCOPE" if "source_scope" in str(exc) else "INVALID_REQUEST"
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": error_code,
                    "message": str(exc),
                },
            },
        )
