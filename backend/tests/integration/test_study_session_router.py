"""Integration tests for the study-session API."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Card, Deck, ReviewLog, Setting, UserCardFSRS, UserCardSRS
from app.utils.timezone import storage_now


def _create_scoped_source(
    db: Session,
    title: str,
    source_index: int,
    lesson_index: int,
    state: str = "review",
) -> dict[str, Deck | Card]:
    source = Deck(title=title, type="source", level_index=source_index)
    db.add(source)
    db.flush()

    unit = Deck(title=f"{title} Unit", type="unit", level_index=0, parent_id=source.id)
    db.add(unit)
    db.flush()

    lesson = Deck(title=f"{title} Lesson", type="lesson", level_index=lesson_index, parent_id=unit.id)
    db.add(lesson)
    db.flush()

    card = Card(
        deck_id=lesson.id,
        card_index=0,
        front_text=f"{title} sentence",
        back_text=f"{title} 翻译",
        audio_path=f"audio/{title}.wav",
    )
    db.add(card)
    db.flush()

    db.add(
        UserCardSRS(
            card_id=card.id,
            state=state,
            step=0 if state in {"learning", "relearning"} else None,
            stability=None if state == "learning" else 3.0,
            difficulty=None if state == "learning" else 4.0,
            due=storage_now() - timedelta(hours=1),
            last_review=None if state == "learning" else storage_now() - timedelta(days=1),
        )
    )
    db.commit()

    return {"source": source, "lesson": lesson, "card": card}


@pytest.mark.integration
class TestStudySessionRouter:
    def test_get_study_session_by_user_deck_returns_only_active_user_deck_cards(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        lesson = sample_deck_tree["lesson"]
        cards = sample_deck_tree["cards"]

        selection = client.put(
            "/api/v1/user-decks/selection",
            json={"origin_deck_ids": [lesson.id]},
        )
        assert selection.status_code == 200
        user_deck_id = selection.json()["data"]["user_decks"][0]["id"]

        now = storage_now()
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=cards[0].id,
                state="learning",
                step=0,
                due=now - timedelta(minutes=30),
                last_review=now - timedelta(hours=1),
            )
        )
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=cards[1].id,
                state="review",
                step=None,
                due=now - timedelta(minutes=5),
                last_review=now - timedelta(days=1),
            )
        )
        test_db.commit()

        response = client.get(f"/api/v1/study/session?user_deck_id={user_deck_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["scope"]["user_deck_id"] == user_deck_id
        assert data["scope"]["lesson_id"] is None
        assert len(data["cards"]) == 5
        assert [card["id"] for card in data["cards"][:2]] == [cards[0].id, cards[1].id]
        assert data["cards"][0]["card_state"] == "learning"
        assert data["cards"][1]["card_state"] == "review"

    def test_get_study_session_uses_beijing_timezone_offset(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/session should serialize timestamps with fixed +08:00 offset."""
        lesson = sample_deck_tree["lesson"]
        srs_rows = test_db.query(UserCardSRS).order_by(UserCardSRS.card_id).all()
        srs_rows[0].state = "review"
        srs_rows[0].step = None
        srs_rows[0].stability = 3.5
        srs_rows[0].difficulty = 4.0
        srs_rows[0].due = storage_now() - timedelta(minutes=30)
        srs_rows[0].last_review = storage_now() - timedelta(hours=4)
        test_db.commit()

        response = client.get(f"/api/v1/study/session?lesson_id={lesson.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert datetime.fromisoformat(data["server_time"]).utcoffset() == timedelta(hours=8)
        assert all(
            datetime.fromisoformat(card["due_at"]).utcoffset() == timedelta(hours=8)
            for card in data["cards"]
        )

    def test_get_study_session_prioritizes_due_review_then_new(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """GET /study/session should order learning -> review -> new and use +08:00 times."""
        lesson = sample_deck_tree["lesson"]
        cards = sample_deck_tree["cards"]

        test_db.add_all(
            [
                Setting(key="daily_new_limit", value=2),
                Setting(key="daily_review_limit", value=3),
            ]
        )

        srs_rows = test_db.query(UserCardSRS).order_by(UserCardSRS.card_id).all()
        srs_rows[0].state = "learning"
        srs_rows[0].step = 1
        srs_rows[0].due = storage_now() - timedelta(hours=2)
        srs_rows[0].last_review = storage_now() - timedelta(hours=3)
        srs_rows[1].state = "review"
        srs_rows[1].step = None
        srs_rows[1].stability = 3.5
        srs_rows[1].difficulty = 4.0
        srs_rows[1].due = storage_now() - timedelta(hours=1)
        srs_rows[1].last_review = storage_now() - timedelta(days=1)
        srs_rows[2].state = "review"
        srs_rows[2].step = None
        srs_rows[2].stability = 3.5
        srs_rows[2].difficulty = 4.0
        srs_rows[2].due = storage_now() + timedelta(days=1)
        srs_rows[2].last_review = storage_now() - timedelta(days=1)
        srs_rows[3].state = "review"
        srs_rows[3].step = None
        srs_rows[3].stability = 5.0
        srs_rows[3].difficulty = 3.5
        srs_rows[3].due = storage_now() - timedelta(days=2)
        srs_rows[3].last_review = None

        test_db.add(
            ReviewLog(
                card_id=cards[0].id,
                deck_id=lesson.id,
                rating="good",
                result_type="single",
                status="completed",
                ai_feedback_json={"oss_path": "recordings/20260321/example.webm"},
            )
        )
        test_db.commit()

        response = client.get(f"/api/v1/study/session?lesson_id={lesson.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["summary"]["due_count"] == 2
        assert [card["card_state"] for card in data["cards"]] == [
            "learning",
            "review",
            "learning",
            "learning",
            "review",
        ]
        assert [card["is_new_card"] for card in data["cards"]] == [False, False, True, True, False]
        assert data["cards"][0]["last_review_at"] is not None
        assert data["cards"][1]["last_review_at"] is not None
        assert data["cards"][2]["last_review_at"] is None
        assert data["cards"][3]["last_review_at"] is None
        assert data["cards"][2]["id"] == cards[3].id
        assert data["cards"][2]["card_state"] == "learning"
        assert data["cards"][4]["id"] == cards[2].id
        assert data["cards"][0]["oss_audio_path"] == "recordings/20260321/example.webm"
        assert datetime.fromisoformat(data["server_time"]).utcoffset() == timedelta(hours=8)
        assert all(
            datetime.fromisoformat(card["due_at"]).utcoffset() == timedelta(hours=8)
            for card in data["cards"]
        )
        assert all(
            card["last_review_at"] is None
            or datetime.fromisoformat(card["last_review_at"]).utcoffset() == timedelta(hours=8)
            for card in data["cards"]
        )

    def test_get_study_session_does_not_schedule_cards_missing_srs_snapshot(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """Cards without an SRS row must not be treated as new cards."""
        from app.models import UserCardSRS

        lesson = sample_deck_tree["lesson"]
        cards = sample_deck_tree["cards"]

        test_db.add_all(
            [
                Setting(key="daily_new_limit", value=10),
                Setting(key="daily_review_limit", value=0),
            ]
        )

        missing_srs = test_db.query(UserCardSRS).filter(UserCardSRS.card_id == cards[0].id).one()
        test_db.delete(missing_srs)
        test_db.commit()

        response = client.get(f"/api/v1/study/session?lesson_id={lesson.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        returned_ids = [card["id"] for card in data["cards"]]
        assert cards[0].id not in returned_ids
        assert len(returned_ids) == 4

    def test_get_study_session_lesson_scope_keeps_reviewed_future_cards_visible(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """Lesson refresh should keep already-reviewed, not-due cards in the list."""
        lesson = sample_deck_tree["lesson"]
        cards = sample_deck_tree["cards"]

        test_db.add_all(
            [
                Setting(key="daily_new_limit", value=1),
                Setting(key="daily_review_limit", value=1),
            ]
        )

        srs_rows = test_db.query(UserCardSRS).order_by(UserCardSRS.card_id).all()
        srs_rows[0].state = "review"
        srs_rows[0].step = None
        srs_rows[0].stability = 4.5
        srs_rows[0].difficulty = 3.8
        srs_rows[0].due = storage_now() + timedelta(days=3)
        srs_rows[0].last_review = storage_now() - timedelta(hours=1)

        srs_rows[1].state = "review"
        srs_rows[1].step = None
        srs_rows[1].stability = 4.0
        srs_rows[1].difficulty = 4.1
        srs_rows[1].due = storage_now() - timedelta(minutes=30)
        srs_rows[1].last_review = storage_now() - timedelta(days=1)

        srs_rows[2].state = "review"
        srs_rows[2].step = None
        srs_rows[2].stability = 5.0
        srs_rows[2].difficulty = 3.5
        srs_rows[2].due = storage_now() + timedelta(days=5)
        srs_rows[2].last_review = None

        srs_rows[3].state = "relearning"
        srs_rows[3].step = 1
        srs_rows[3].stability = 2.0
        srs_rows[3].difficulty = 5.5
        srs_rows[3].due = storage_now() + timedelta(hours=6)
        srs_rows[3].last_review = storage_now() - timedelta(hours=2)
        test_db.commit()

        response = client.get(f"/api/v1/study/session?lesson_id={lesson.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        returned_ids = [card["id"] for card in data["cards"]]
        assert returned_ids == [cards[1].id, cards[2].id, cards[3].id, cards[0].id]
        assert data["cards"][0]["last_review_at"] is not None
        assert data["cards"][1]["is_new_card"] is True
        assert data["cards"][2]["card_state"] == "relearning"
        assert data["cards"][3]["card_state"] == "review"
        assert data["cards"][3]["last_review_at"] is not None

        scoped_response = client.get("/api/v1/study/session")
        assert scoped_response.status_code == 200
        scoped_ids = [card["id"] for card in scoped_response.json()["data"]["cards"]]
        assert cards[0].id not in scoped_ids
        assert cards[3].id not in scoped_ids

    def test_get_study_session_source_scope_overrides_settings(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """Request source_scope should beat default_source_scope settings."""
        source1 = sample_deck_tree["source"]
        source2_tree = _create_scoped_source(test_db, "Source 2", 1, 0)

        test_db.add(Setting(key="default_source_scope", value=[source2_tree["source"].id]))
        test_db.commit()

        response = client.get(f"/api/v1/study/session?source_scope={source1.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["scope"]["source_ids"] == [source1.id]
        assert all(card["lesson_id"] == sample_deck_tree["lesson"].id for card in data["cards"])

    def test_get_study_session_uses_default_source_scope_when_request_missing(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        """Settings default_source_scope should apply when request scope is absent."""
        _ = sample_deck_tree
        source2_tree = _create_scoped_source(test_db, "Scoped Source", 1, 0)

        test_db.add_all(
            [
                Setting(key="daily_new_limit", value=0),
                Setting(key="daily_review_limit", value=5),
                Setting(key="default_source_scope", value=[source2_tree["source"].id]),
            ]
        )
        test_db.commit()

        response = client.get("/api/v1/study/session")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["scope"]["source_ids"] == [source2_tree["source"].id]
        assert [card["lesson_id"] for card in data["cards"]] == [source2_tree["lesson"].id]

    def test_get_study_session_rejects_invalid_source_scope(
        self,
        client: TestClient,
        sample_deck_tree,
    ):
        """Invalid source_scope values should return a structured 400."""
        _ = sample_deck_tree

        response = client.get("/api/v1/study/session?source_scope=1,abc")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"]["code"] == "INVALID_SOURCE_SCOPE"
