"""Unit tests for the native-FSRS SRS repository."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.deck import Deck
from app.models.user_card_srs import UserCardSRS
from app.repositories.srs_repo import SRSRepository
from app.utils.timezone import storage_now


def _create_card(test_db: Session, lesson_title: str = "Lesson 1", card_index: int = 0) -> Card:
    lesson = Deck(title=lesson_title, type="lesson", level_index=0)
    test_db.add(lesson)
    test_db.flush()

    card = Card(deck_id=lesson.id, card_index=card_index, front_text="Test", back_text="测试")
    test_db.add(card)
    test_db.flush()
    return card


def _create_srs(
    test_db: Session,
    card_id: int,
    *,
    state: str = "learning",
    step: int | None = 0,
    stability: float | None = None,
    difficulty: float | None = None,
    due: datetime | None = None,
    last_review: datetime | None = None,
) -> UserCardSRS:
    srs = UserCardSRS(
        card_id=card_id,
        state=state,
        step=step,
        stability=stability,
        difficulty=difficulty,
        due=due or storage_now(),
        last_review=last_review,
    )
    test_db.add(srs)
    test_db.flush()
    return srs


@pytest.mark.unit
class TestSRSRepository:
    def test_get_by_card_id_not_found(self, test_db: Session):
        repo = SRSRepository(test_db)
        assert repo.get_by_card_id(99999) is None

    def test_get_by_card_id_returns_initial_snapshot(self, test_db: Session):
        repo = SRSRepository(test_db)
        card = _create_card(test_db)
        _create_srs(test_db, card.id, state="learning", step=0, last_review=None)
        test_db.commit()

        result = repo.get_by_card_id(card.id)

        assert result is not None
        assert result.card_id == card.id
        assert result.state == "learning"
        assert result.step == 0
        assert result.last_review is None
        assert repo.derive_card_state(result) == "learning"
        assert repo.is_new_bucket(result) is True

    def test_upsert_insert_initial_snapshot(self, test_db: Session):
        repo = SRSRepository(test_db)
        card = _create_card(test_db)
        due_time = storage_now() + timedelta(days=1)

        srs = repo.upsert(
            card_id=card.id,
            state="learning",
            step=0,
            stability=None,
            difficulty=None,
            due=due_time,
            last_review=None,
        )

        assert srs.state == "learning"
        assert srs.step == 0
        assert srs.stability is None
        assert srs.difficulty is None
        assert srs.last_review is None
        assert repo.derive_card_state(srs) == "learning"
        assert repo.is_new_bucket(srs) is True

    def test_upsert_update_existing_snapshot(self, test_db: Session):
        repo = SRSRepository(test_db)
        card = _create_card(test_db)
        _create_srs(test_db, card.id, state="learning", step=0, last_review=None)
        test_db.commit()

        review_time = storage_now()
        due_time = review_time + timedelta(days=7)
        updated = repo.upsert(
            card_id=card.id,
            state="review",
            step=None,
            stability=7.0,
            difficulty=4.0,
            due=due_time,
            last_review=review_time,
        )

        assert updated.state == "review"
        assert updated.step is None
        assert updated.stability == 7.0
        assert updated.difficulty == 4.0
        assert updated.last_review == review_time
        assert repo.derive_card_state(updated) == "review"
        assert repo.is_new_bucket(updated) is False

    def test_upsert_rejects_invalid_persisted_state(self, test_db: Session):
        repo = SRSRepository(test_db)
        card = _create_card(test_db)

        with pytest.raises(ValueError, match="Unsupported native FSRS state"):
            repo.upsert(
                card_id=card.id,
                state="invalid",
                step=0,
                stability=None,
                difficulty=None,
                due=storage_now(),
                last_review=None,
            )

    def test_create_review_log(self, test_db: Session):
        repo = SRSRepository(test_db)
        card = _create_card(test_db)
        review_time = storage_now()

        review_log = repo.create_review_log(
            card_id=card.id,
            rating=3,
            review_datetime=review_time,
            review_duration=1800,
        )

        assert review_log.card_id == card.id
        assert review_log.rating == 3
        assert review_log.review_datetime == review_time
        assert review_log.review_duration == 1800

    def test_get_due_cards_excludes_initial_bucket(self, test_db: Session):
        repo = SRSRepository(test_db)
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        new_card = Card(deck_id=lesson.id, card_index=0, front_text="new", back_text="新")
        review_card = Card(deck_id=lesson.id, card_index=1, front_text="review", back_text="复习")
        test_db.add_all([new_card, review_card])
        test_db.flush()

        _create_srs(
            test_db,
            new_card.id,
            state="learning",
            step=0,
            due=storage_now() - timedelta(hours=1),
            last_review=None,
        )
        _create_srs(
            test_db,
            review_card.id,
            state="review",
            step=None,
            stability=5.0,
            difficulty=4.0,
            due=storage_now() - timedelta(hours=1),
            last_review=storage_now() - timedelta(days=1),
        )
        test_db.commit()

        due_cards = repo.get_due_cards(lesson_ids=[lesson.id])

        assert len(due_cards) == 1
        assert due_cards[0][0].id == review_card.id

    def test_count_due_by_lesson_only_counts_reviewed_rows(self, test_db: Session):
        repo = SRSRepository(test_db)
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        due_review = Card(deck_id=lesson.id, card_index=0, front_text="a", back_text="a")
        future_review = Card(deck_id=lesson.id, card_index=1, front_text="b", back_text="b")
        initial_card = Card(deck_id=lesson.id, card_index=2, front_text="c", back_text="c")
        test_db.add_all([due_review, future_review, initial_card])
        test_db.flush()

        _create_srs(
            test_db,
            due_review.id,
            state="review",
            step=None,
            stability=5.0,
            difficulty=4.0,
            due=storage_now() - timedelta(hours=1),
            last_review=storage_now() - timedelta(days=1),
        )
        _create_srs(
            test_db,
            future_review.id,
            state="review",
            step=None,
            stability=5.0,
            difficulty=4.0,
            due=storage_now() + timedelta(days=1),
            last_review=storage_now() - timedelta(days=1),
        )
        _create_srs(
            test_db,
            initial_card.id,
            state="learning",
            step=0,
            due=storage_now() - timedelta(hours=1),
            last_review=None,
        )
        test_db.commit()

        assert repo.count_due_by_lesson(lesson.id) == 1

    def test_count_completed_by_lesson_excludes_initial_bucket(self, test_db: Session):
        repo = SRSRepository(test_db)
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        initial_card = Card(deck_id=lesson.id, card_index=0, front_text="a", back_text="a")
        reviewed_card = Card(deck_id=lesson.id, card_index=1, front_text="b", back_text="b")
        test_db.add_all([initial_card, reviewed_card])
        test_db.flush()

        _create_srs(
            test_db,
            initial_card.id,
            state="learning",
            step=0,
            due=storage_now(),
            last_review=None,
        )
        _create_srs(
            test_db,
            reviewed_card.id,
            state="review",
            step=None,
            stability=4.0,
            difficulty=5.0,
            due=storage_now(),
            last_review=storage_now() - timedelta(days=1),
        )
        test_db.commit()

        assert repo.count_completed_by_lesson(lesson.id) == 1

    def test_get_reviewed_cards_returns_only_future_reviewed_rows(self, test_db: Session):
        repo = SRSRepository(test_db)
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        future_review = Card(deck_id=lesson.id, card_index=0, front_text="a", back_text="a")
        due_review = Card(deck_id=lesson.id, card_index=1, front_text="b", back_text="b")
        initial_card = Card(deck_id=lesson.id, card_index=2, front_text="c", back_text="c")
        test_db.add_all([future_review, due_review, initial_card])
        test_db.flush()

        _create_srs(
            test_db,
            future_review.id,
            state="review",
            step=None,
            stability=4.0,
            difficulty=5.0,
            due=storage_now() + timedelta(days=1),
            last_review=storage_now() - timedelta(days=1),
        )
        _create_srs(
            test_db,
            due_review.id,
            state="review",
            step=None,
            stability=4.0,
            difficulty=5.0,
            due=storage_now() - timedelta(hours=1),
            last_review=storage_now() - timedelta(days=1),
        )
        _create_srs(
            test_db,
            initial_card.id,
            state="learning",
            step=0,
            due=storage_now() + timedelta(days=2),
            last_review=None,
        )
        test_db.commit()

        reviewed_cards = repo.get_reviewed_cards(lesson_ids=[lesson.id])

        assert [card.id for card, _ in reviewed_cards] == [future_review.id]
