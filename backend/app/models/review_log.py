"""Review log model for study submissions and AI feedback."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class ReviewLog(Base):
    """Submission log for training attempts and AI feedback.

    During the migration window we keep legacy `status` / `rating` columns for
    backward compatibility, while the new runtime writes `ai_status` /
    `submitted_rating`.
    """

    __tablename__ = "review_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1, index=True)
    user_deck_id = Column(Integer, ForeignKey("user_decks.id"), nullable=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=True, index=True)  # NULL for summary
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)  # Lesson ID
    rating = Column(String(20), nullable=True)  # again/hard/good/easy (NULL for summary)
    result_type = Column(String(20), nullable=False, index=True)  # single/summary
    ai_feedback_json = Column(JSON, nullable=True)  # May remain NULL until AI finishes
    ai_status = Column(String(20), default="processing", nullable=False, index=True)
    submitted_rating = Column(String(20), nullable=True)
    rated_at = Column(DateTime, nullable=True)

    # Asynchronous processing status
    status = Column(
        String(20), default="processing", nullable=False, index=True
    )  # processing/completed/failed
    error_code = Column(String(50), nullable=True)  # Error code if failed
    error_message = Column(Text, nullable=True)  # Error message if failed

    created_at = Column(DateTime, default=storage_now, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="review_logs")
    user_deck = relationship("UserDeck", back_populates="review_logs")
    card = relationship("Card", back_populates="review_logs")
    deck = relationship("Deck", back_populates="review_logs")
