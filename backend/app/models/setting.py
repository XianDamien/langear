"""System settings model."""

from sqlalchemy import Column, DateTime, JSON, String

from app.database import Base
from app.utils.timezone import storage_now


class Setting(Base):
    """System configuration settings.

    Uses key-value store pattern with JSON for complex values.
    """

    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)
