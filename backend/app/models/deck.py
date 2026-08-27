"""Deck model for source/unit/lesson hierarchy."""
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now

DeckType = Literal["source", "unit", "lesson"]


class Deck(Base):
    """Deck model representing source/unit/lesson hierarchy.

    Types:
    - source: Top level (e.g., "New Concept English Book 2")
    - unit: Middle level (e.g., "Unit 1")
    - lesson: Bottom level (e.g., "Lesson 1")
    """

    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    type = Column(String(20), nullable=False, index=True)  # source/unit/lesson
    parent_id = Column(Integer, ForeignKey("decks.id"), nullable=True, index=True)
    level_index = Column(Integer, nullable=False, default=0)  # Sort order within parent
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    # Relationships
    parent = relationship("Deck", remote_side=[id], backref="children")
    cards = relationship("Card", back_populates="deck")
    user_decks = relationship("UserDeck", back_populates="origin_deck")
    review_logs = relationship("ReviewLog", back_populates="deck")

    @property
    def is_source(self) -> bool:
        return self.type == "source"

    @property
    def is_unit(self) -> bool:
        return self.type == "unit"

    @property
    def is_lesson(self) -> bool:
        return self.type == "lesson"
