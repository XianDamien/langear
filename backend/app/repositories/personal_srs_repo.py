"""Read personal progress with compatibility for the original account.

Migration d3c1b8f4e2a9 assigns legacy snapshots to user 1. Older app
versions continued updating those rows after the one-time backfill.
"""

from sqlalchemy.orm import Session

from app.models.user_card_fsrs import UserCardFSRS
from app.models.user_card_srs import UserCardSRS


class PersonalSRSRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def effective(personal, legacy):
        if legacy is not None and legacy.last_review is not None and (
            personal is None or personal.last_review is None
            or legacy.last_review > personal.last_review
        ):
            return legacy
        return personal

    def get(self, user_id: int, card_id: int):
        personal = self.db.get(UserCardFSRS, (user_id, card_id))
        legacy = self.db.get(UserCardSRS, card_id) if user_id == 1 else None
        return self.effective(personal, legacy)

    def for_cards(self, user_id: int, card_ids: list[int]) -> dict:
        rows = self.db.query(UserCardFSRS).filter(
            UserCardFSRS.user_id == user_id, UserCardFSRS.card_id.in_(card_ids),
        ).all()
        states = {row.card_id: row for row in rows}
        if user_id == 1:
            for legacy in self.db.query(UserCardSRS).filter(UserCardSRS.card_id.in_(card_ids)):
                states[legacy.card_id] = self.effective(states.get(legacy.card_id), legacy)
        return states
