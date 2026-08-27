"""User-level FSRS settings."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class UserSettings(Base):
    """Per-user learning settings for FSRS scheduling."""

    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    desired_retention = Column(Float, nullable=False, default=0.9)
    learning_steps_json = Column(JSON, nullable=False, default=lambda: [15])
    relearning_steps_json = Column(JSON, nullable=False, default=lambda: [15])
    maximum_interval = Column(Integer, nullable=False, default=36500)
    default_source_scope_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    user = relationship("User", back_populates="settings")
