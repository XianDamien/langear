"""Settings service for per-user learning configuration."""

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.user_settings_repo import UserSettingsRepository

VALID_SETTING_KEYS = {
    "desired_retention",
    "learning_steps",
    "relearning_steps",
    "maximum_interval",
    "default_source_scope",
}


class SettingsService:
    """Service for managing user learning settings."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.settings_repo = UserSettingsRepository(db)

    def get_settings(self, user_id: int) -> dict[str, Any]:
        """Get user-level FSRS settings."""
        settings = self.settings_repo.get_or_create(user_id)
        return self._serialize_settings(settings)

    def update_settings(self, user_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Update user-level FSRS settings."""
        invalid_keys = set(updates.keys()) - VALID_SETTING_KEYS
        if invalid_keys:
            raise ValueError(f"Invalid settings keys: {invalid_keys}")

        if "desired_retention" in updates:
            retention = updates["desired_retention"]
            if not isinstance(retention, (int, float)) or retention <= 0 or retention >= 1:
                raise ValueError("desired_retention must be a number between 0 and 1")

        if "learning_steps" in updates:
            self._validate_step_list("learning_steps", updates["learning_steps"])

        if "relearning_steps" in updates:
            self._validate_step_list("relearning_steps", updates["relearning_steps"])

        if "maximum_interval" in updates:
            if (
                not isinstance(updates["maximum_interval"], int)
                or updates["maximum_interval"] <= 0
            ):
                raise ValueError("maximum_interval must be a positive integer")

        if "default_source_scope" in updates:
            if not isinstance(updates["default_source_scope"], list):
                raise ValueError("default_source_scope must be a list")
            if any(not isinstance(item, int) or item <= 0 for item in updates["default_source_scope"]):
                raise ValueError("default_source_scope must contain positive integers only")

        settings = self.settings_repo.get_or_create(user_id)
        if "desired_retention" in updates:
            settings.desired_retention = float(updates["desired_retention"])
        if "learning_steps" in updates:
            settings.learning_steps_json = updates["learning_steps"]
        if "relearning_steps" in updates:
            settings.relearning_steps_json = updates["relearning_steps"]
        if "maximum_interval" in updates:
            settings.maximum_interval = updates["maximum_interval"]
        if "default_source_scope" in updates:
            settings.default_source_scope_json = updates["default_source_scope"]

        self.db.commit()
        self.db.refresh(settings)

        return self._serialize_settings(settings)

    @staticmethod
    def _validate_step_list(field_name: str, steps: Any) -> None:
        """Validate intraday step list values in minutes."""
        if not isinstance(steps, list):
            raise ValueError(f"{field_name} must be a list")
        if any(not isinstance(step, int) or step <= 0 for step in steps):
            raise ValueError(f"{field_name} must contain positive integers only")

    @staticmethod
    def _serialize_settings(settings) -> dict[str, Any]:
        """Convert ORM settings row to API response payload."""
        return {
            "desired_retention": settings.desired_retention,
            "learning_steps": settings.learning_steps_json or [],
            "relearning_steps": settings.relearning_steps_json or [],
            "maximum_interval": settings.maximum_interval,
            "default_source_scope": settings.default_source_scope_json or [],
        }
