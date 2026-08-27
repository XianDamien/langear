"""User model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class User(Base):
    """User account model (MVP: single admin user with ID=1)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    password_hash = Column(String(255), nullable=True)
    invitation_code_id = Column(Integer, ForeignKey("invitation_codes.id"), nullable=True)
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    invitation_code = relationship("InvitationCode", back_populates="users")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    user_decks = relationship("UserDeck", back_populates="user")
    card_fsrs = relationship("UserCardFSRS", back_populates="user")
    review_logs = relationship("ReviewLog", back_populates="user")
