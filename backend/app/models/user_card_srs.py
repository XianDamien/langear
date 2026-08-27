"""User card SRS snapshot aligned with native FSRS Card fields."""

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.timezone import storage_now


class UserCardSRS(Base):
    """Native FSRS card snapshot for each card.

    `new` is not persisted in `state`; the initial/new bucket is derived by
    `last_review IS NULL`.
    """

    __tablename__ = "user_card_srs"
    __table_args__ = (
        CheckConstraint(
            "state in ('learning', 'review', 'relearning')",
            name="ck_user_card_srs_state",
        ),
    )

    card_id = Column(Integer, ForeignKey("cards.id"), primary_key=True)
    state = Column(String(20), nullable=False, default="learning")
    step = Column(Integer, nullable=True)
    stability = Column(Float, nullable=True)
    difficulty = Column(Float, nullable=True)
    due = Column(DateTime, nullable=False, default=storage_now)
    last_review = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=storage_now, onupdate=storage_now, nullable=False)

    # Relationships
    card = relationship("Card", back_populates="srs_state")

    @property
    def is_initial(self) -> bool:
        """Whether the row still represents an initial/new-bucket card."""
        return self.last_review is None
