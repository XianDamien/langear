"""Legacy library / my-courses selection endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import require_current_user_id
from app.services.my_courses_service import MyCoursesService

router = APIRouter(prefix="/api/v1/my-courses", tags=["My Courses"])


class MyCourseLessonsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_ids: list[Annotated[int, Field(strict=True, gt=0)]]


@router.get("/lessons")
def get_my_course_lessons(
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """Read selected lessons for the existing authenticated account."""
    try:
        lesson_ids = MyCoursesService(db).get_lesson_ids(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"request_id": str(uuid.uuid4()), "data": {"lesson_ids": lesson_ids}}


@router.put("/lessons")
def update_my_course_lessons(
    request: MyCourseLessonsUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """Replace selection atomically; deselection never deletes study data."""
    request_id = str(uuid.uuid4())
    try:
        lesson_ids = MyCoursesService(db).replace_lesson_ids(user_id, request.lesson_ids)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {"code": "INVALID_LESSON_IDS", "message": str(exc)},
            },
        ) from exc
    return {"request_id": request_id, "data": {"lesson_ids": lesson_ids}}


class MyCourseCardsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_ids: list[Annotated[int, Field(strict=True, gt=0)]] | None


@router.get("/lessons/{lesson_id}/cards")
def get_my_course_cards(
    lesson_id: Annotated[int, Field(gt=0)],
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    try:
        card_ids = MyCoursesService(db).get_card_ids(user_id, lesson_id)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"request_id": str(uuid.uuid4()), "data": {"card_ids": card_ids}}


@router.put("/lessons/{lesson_id}/cards")
def update_my_course_cards(
    lesson_id: Annotated[int, Field(gt=0)],
    request: MyCourseCardsUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    try:
        result = MyCoursesService(db).replace_card_ids(user_id, lesson_id, request.card_ids)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"request_id": str(uuid.uuid4()), "data": result}
