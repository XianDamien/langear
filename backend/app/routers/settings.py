"""Settings router for system configuration."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import get_current_user_id
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


class SettingsUpdateRequest(BaseModel):
    """Request model for updating settings."""

    model_config = ConfigDict(extra="allow")

    desired_retention: float | None = None
    learning_steps: list[int] | None = None
    relearning_steps: list[int] | None = None
    maximum_interval: int | None = None
    default_source_scope: list[int] | None = None


@router.get("")
def get_settings(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get current user's learning settings."""
    request_id = str(uuid.uuid4())

    settings_service = SettingsService(db)
    settings = settings_service.get_settings(user_id)

    return {
        "request_id": request_id,
        "data": settings,
    }


@router.put("")
def update_settings(
    request: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update current user's learning settings."""
    request_id = str(uuid.uuid4())

    try:
        # Convert request to dict, excluding None values
        updates = {
            k: v for k, v in request.model_dump().items() if v is not None
        }

        settings_service = SettingsService(db)
        updated_settings = settings_service.update_settings(user_id, updates)

        return {
            "request_id": request_id,
            "data": updated_settings,
        }

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
