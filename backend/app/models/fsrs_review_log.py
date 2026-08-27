"""Native FSRS review history aligned with py-fsrs ReviewLog."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class FSRSReviewLog(Base):
    """Per-review FSRS history entry."""

    __tablename__ = "fsrs_review_log"
    __table_args__ = (
        CheckConstraint(
            "rating in (1, 2, 3, 4)",
            name="ck_fsrs_review_log_rating",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    review_datetime = Column(DateTime, nullable=False, index=True)
    review_duration = Column(Integer, nullable=True)

    card = relationship("Card", back_populates="fsrs_review_logs")
