"""User settings repository for per-user learning preferences."""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_settings import UserSettings


class UserSettingsRepository:
    """Repository for UserSettings model operations."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def get_by_user_id(self, user_id: int) -> UserSettings | None:
        """Get user settings for a user."""
        return (
            self.db.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )

    def get_or_create(
        self,
        user_id: int,
        *,
        desired_retention: float = 0.9,
        learning_steps_json: list[int] | None = None,
        relearning_steps_json: list[int] | None = None,
        maximum_interval: int = 36500,
        default_source_scope_json: list[int] | None = None,
    ) -> UserSettings:
        """Return existing user settings or create defaults."""
        settings = self.get_by_user_id(user_id)
        if settings is not None:
            return settings

        user = self.db.query(User).filter(User.id == user_id).first()
        if user is None:
            user = User(id=user_id, username=f"user-{user_id}")
            self.db.add(user)
            self.db.flush()

        settings = UserSettings(
            user_id=user_id,
            desired_retention=desired_retention,
            learning_steps_json=[15] if learning_steps_json is None else learning_steps_json,
            relearning_steps_json=[15]
            if relearning_steps_json is None
            else relearning_steps_json,
            maximum_interval=maximum_interval,
            default_source_scope_json=[]
            if default_source_scope_json is None
            else default_source_scope_json,
        )
        self.db.add(settings)
        self.db.flush()
        return settings
