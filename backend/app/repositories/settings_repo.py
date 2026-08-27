"""Settings repository for database operations."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.setting import Setting


class SettingsRepository:
    """Repository for Setting model operations."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get(self, key: str) -> Any | None:
        """Get setting value by key.

        Args:
            key: Setting key

        Returns:
            Setting value or None if not found
        """
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else None

    def set(self, key: str, value: Any) -> Setting:
        """Set or update setting value.

        Args:
            key: Setting key
            value: Setting value (will be stored as JSON)

        Returns:
            Setting object
        """
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting is None:
            # Create new setting
            setting = Setting(key=key, value=value)
            self.db.add(setting)
        else:
            # Update existing setting
            setting.value = value

        self.db.flush()
        return setting

    def get_all(self) -> dict[str, Any]:
        """Get all settings as a dictionary.

        Returns:
            Dictionary of all settings
        """
        settings = self.db.query(Setting).all()
        return {s.key: s.value for s in settings}
