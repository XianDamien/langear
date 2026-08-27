"""Stable card membership for a user deck."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class UserDeckCard(Base):
    """Association row for cards imported into a user deck."""

    __tablename__ = "user_deck_cards"
    __table_args__ = (
        UniqueConstraint("user_deck_id", "new_position", name="uq_user_deck_cards_position"),
    )

    user_deck_id = Column(Integer, ForeignKey("user_decks.id"), primary_key=True)
    card_id = Column(Integer, ForeignKey("cards.id"), primary_key=True)
    new_position = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=storage_now, nullable=False)

    user_deck = relationship("UserDeck", back_populates="deck_cards")
    card = relationship("Card", back_populates="user_deck_memberships")
