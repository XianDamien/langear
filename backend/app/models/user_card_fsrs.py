"""Current FSRS snapshot for a user-card pair."""

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class UserCardFSRS(Base):
    """Per-user current FSRS state for a card."""

    __tablename__ = "user_card_fsrs"
    __table_args__ = (
        CheckConstraint(
            "state in ('learning', 'review', 'relearning')",
            name="ck_user_card_fsrs_state",
        ),
        Index("ix_user_card_fsrs_card_id", "card_id"),
        Index("ix_user_card_fsrs_due", "due"),
        Index("ix_user_card_fsrs_user_id", "user_id"),
        Index("ix_user_card_fsrs_user_id_state_due", "user_id", "state", "due"),
    )

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    card_id = Column(Integer, ForeignKey("cards.id"), primary_key=True)
    state = Column(String(20), nullable=False)
    step = Column(Integer, nullable=True)
    stability = Column(Float, nullable=True)
    difficulty = Column(Float, nullable=True)
    due = Column(DateTime, nullable=False, default=storage_now)
    last_review = Column(DateTime, nullable=True)
    last_rating = Column(String(20), nullable=True)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    user = relationship("User", back_populates="card_fsrs")
    card = relationship("Card", back_populates="user_fsrs_states")
