"""Invitation code model."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class InvitationCode(Base):
    """Registration invitation code for private beta users."""

    __tablename__ = "invitation_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    note = Column(String(255), nullable=True)
    max_uses = Column(Integer, default=1, nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    disabled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    users = relationship("User", back_populates="invitation_code")
