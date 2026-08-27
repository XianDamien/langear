"""Card model for individual sentences."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class Card(Base):
    """Card model representing individual sentences/questions.

    Each card belongs to a lesson (deck with type='lesson').
    """

    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)
    card_index = Column(Integer, nullable=False)  # Order within lesson
    front_text = Column(Text, nullable=False)  # English text
    back_text = Column(Text, nullable=True)  # Chinese translation (optional)
    audio_path = Column(String(500), nullable=True)  # OSS URL for original audio
    created_at = Column(DateTime, default=storage_now, nullable=False)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    # Relationships
    deck = relationship("Deck", back_populates="cards")
    srs_state = relationship("UserCardSRS", back_populates="card", uselist=False)
    user_fsrs_states = relationship("UserCardFSRS", back_populates="card")
    user_deck_memberships = relationship("UserDeckCard", back_populates="card")
    fsrs_review_logs = relationship("FSRSReviewLog", back_populates="card")
    review_logs = relationship("ReviewLog", back_populates="card")
