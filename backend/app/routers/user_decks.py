"""User deck router for personal study scopes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import get_current_user_id
from app.services.user_deck_service import UserDeckService

router = APIRouter(prefix="/api/v1/user-decks", tags=["User Decks"])


class UserDeckImportRequest(BaseModel):
    """Request payload for importing a public deck into personal study."""

    model_config = ConfigDict(extra="forbid")

    origin_deck_id: int


class UserDeckSelectionRequest(BaseModel):
    """Request payload for final user deck selection sync."""

    model_config = ConfigDict(extra="forbid")

    origin_deck_ids: list[int]


@router.post("/import")
def import_user_deck(
    request: UserDeckImportRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Import a public deck scope into the current user's study space."""
    request_id = str(uuid.uuid4())
    try:
        user_deck = UserDeckService(db).import_deck(
            user_id=user_id,
            origin_deck_id=request.origin_deck_id,
        )
        return {
            "request_id": request_id,
            "data": user_deck,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "USER_DECK_IMPORT_FAILED",
                    "message": str(exc),
                },
            },
        )


@router.get("")
def list_user_decks(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """List the current user's imported study decks."""
    request_id = str(uuid.uuid4())
    user_decks = UserDeckService(db).list_decks(user_id)
    return {
        "request_id": request_id,
        "data": {
            "user_decks": user_decks,
        },
    }


@router.put("/selection")
def sync_user_deck_selection(
    request: UserDeckSelectionRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Replace the current user's active public-deck selection."""
    request_id = str(uuid.uuid4())
    try:
        data = UserDeckService(db).sync_selection(
            user_id=user_id,
            origin_deck_ids=request.origin_deck_ids,
        )
        return {
            "request_id": request_id,
            "data": data,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "USER_DECK_SELECTION_INVALID",
                    "message": str(exc),
                },
            },
        )
