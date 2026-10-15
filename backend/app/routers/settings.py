"""Settings router for system configuration."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import require_current_user_id
from app.services.settings_service import SettingsService
from app.services.deck_settings_service import DeckSettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


class SettingsUpdateRequest(BaseModel):
    """Request model for updating settings."""

    model_config = ConfigDict(extra="allow", strict=True)

    desired_retention: float | None = None
    learning_steps: list[int] | None = None
    relearning_steps: list[int] | None = None
    maximum_interval: int | None = None
    default_source_scope: list[int] | None = None


@router.get("")
def get_settings(
    deck_id: int | None = Query(None, gt=0, le=2147483647),
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """Get current user's learning settings."""
    request_id = str(uuid.uuid4())

    if deck_id is not None:
        try:
            return {"request_id": request_id, "data": DeckSettingsService(db).get(user_id, deck_id)}
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    settings_service = SettingsService(db)
    settings = settings_service.get_settings(user_id)

    return {
        "request_id": request_id,
        "data": settings,
    }


@router.put("")
def update_settings(
    request: SettingsUpdateRequest,
    deck_id: int | None = Query(None, gt=0, le=2147483647),
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """Update current user's learning settings."""
    request_id = str(uuid.uuid4())

    try:
        # Convert request to dict, excluding None values
        updates = {
            k: v for k, v in request.model_dump().items() if v is not None
        }

        if deck_id is not None:
            updated_settings = DeckSettingsService(db).update(user_id, deck_id, updates)
        else:
            updated_settings = SettingsService(db).update_settings(user_id, updates)

        return {
            "request_id": request_id,
            "data": updated_settings,
        }

    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "INVALID_SETTINGS",
                    "message": str(e),
                },
            },
        )
