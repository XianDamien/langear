"""User-owned study deck instances."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class UserDeck(Base):
    """Imported study scope for a specific user."""

    __tablename__ = "user_decks"
    __table_args__ = (
        UniqueConstraint("user_id", "origin_deck_id", name="uq_user_decks_user_origin"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    origin_deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False)
    title_snapshot = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    user = relationship("User", back_populates="user_decks")
    origin_deck = relationship("Deck", back_populates="user_decks")
    deck_cards = relationship("UserDeckCard", back_populates="user_deck")
    review_logs = relationship("ReviewLog", back_populates="user_deck")
