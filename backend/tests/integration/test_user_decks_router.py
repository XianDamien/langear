"""Integration tests for user deck endpoints."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user_card_fsrs import UserCardFSRS
from app.utils.timezone import storage_now


@pytest.mark.integration
class TestUserDecksRouter:
    """Test user deck import and listing endpoints."""

    def test_import_lesson_creates_user_deck(
        self,
        client: TestClient,
        sample_deck_tree,
    ):
        lesson = sample_deck_tree["lesson"]

        response = client.post(
            "/api/v1/user-decks/import",
            json={"origin_deck_id": lesson.id},
        )

        assert response.status_code == 200
        payload = response.json()
        data = payload["data"]
        assert data["title"] == lesson.title
        assert data["scope_type"] == "lesson"
        assert data["total_count"] == 5
        assert data["new_count"] == 5
        assert data["learning_count"] == 0
        assert data["review_count"] == 0

    def test_import_is_idempotent(
        self,
        client: TestClient,
        sample_deck_tree,
    ):
        lesson = sample_deck_tree["lesson"]

        first = client.post(
            "/api/v1/user-decks/import",
            json={"origin_deck_id": lesson.id},
        )
        second = client.post(
            "/api/v1/user-decks/import",
            json={"origin_deck_id": lesson.id},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

    def test_list_user_decks_with_user_fsrs_counts(
        self,
        client: TestClient,
        test_db: Session,
        sample_deck_tree,
    ):
        lesson = sample_deck_tree["lesson"]
        cards = sample_deck_tree["cards"]

        import_response = client.post(
            "/api/v1/user-decks/import",
            json={"origin_deck_id": lesson.id},
        )
        assert import_response.status_code == 200

        now = storage_now()
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=cards[0].id,
                state="learning",
                step=0,
                due=now,
            )
        )
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=cards[1].id,
                state="review",
                step=None,
                due=now - timedelta(minutes=1),
            )
        )
        test_db.add(
            UserCardFSRS(
                user_id=1,
                card_id=cards[2].id,
                state="review",
                step=None,
                due=now + timedelta(days=1),
            )
        )
        test_db.commit()

        response = client.get("/api/v1/user-decks")

        assert response.status_code == 200
        user_decks = response.json()["data"]["user_decks"]
        assert len(user_decks) == 1
        assert user_decks[0]["total_count"] == 5
        assert user_decks[0]["new_count"] == 2
        assert user_decks[0]["learning_count"] == 1
        assert user_decks[0]["review_count"] == 1

    def test_import_missing_deck_returns_404(self, client: TestClient):
        response = client.post(
            "/api/v1/user-decks/import",
            json={"origin_deck_id": 999999},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["error"]["code"] == "USER_DECK_IMPORT_FAILED"
