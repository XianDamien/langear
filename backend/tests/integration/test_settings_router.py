"""Integration tests for user-level settings API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_data.seed_data import create_test_user_settings


@pytest.mark.integration
class TestSettingsRouter:
    """Test suite for `/api/v1/settings`."""

    def test_get_settings_success(self, client: TestClient, test_db: Session):
        response = client.get("/api/v1/settings")

        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload["request_id"], str)
        assert payload["data"] == {
            "desired_retention": 0.9,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [],
        }

    def test_get_settings_with_existing_user_settings(
        self,
        client: TestClient,
        test_db: Session,
        sample_user_settings,
    ):
        response = client.get("/api/v1/settings")

        assert response.status_code == 200
        assert response.json()["data"] == {
            "desired_retention": 0.9,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [1, 2],
        }

    def test_put_settings_updates_multiple_fields(self, client: TestClient, test_db: Session):
        response = client.put(
            "/api/v1/settings",
            json={
                "desired_retention": 0.88,
                "learning_steps": [15, 1440],
                "relearning_steps": [15],
                "maximum_interval": 999,
                "default_source_scope": [2, 3],
            },
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "desired_retention": 0.88,
            "learning_steps": [15, 1440],
            "relearning_steps": [15],
            "maximum_interval": 999,
            "default_source_scope": [2, 3],
        }

    def test_put_settings_partial_update_preserves_existing_values(
        self,
        client: TestClient,
        test_db: Session,
    ):
        create_test_user_settings(test_db)

        response = client.put(
            "/api/v1/settings",
            json={"desired_retention": 0.86},
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "desired_retention": 0.86,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [1, 2],
        }

    def test_put_settings_persists_changes(self, client: TestClient, test_db: Session):
        response = client.put(
            "/api/v1/settings",
            json={"default_source_scope": [7]},
        )
        assert response.status_code == 200

        follow_up = client.get("/api/v1/settings")
        assert follow_up.status_code == 200
        assert follow_up.json()["data"]["default_source_scope"] == [7]

    def test_put_settings_invalid_key_returns_400(self, client: TestClient, test_db: Session):
        response = client.put(
            "/api/v1/settings",
            json={"daily_new_limit": 10},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"]["code"] == "INVALID_SETTINGS"
        assert "Invalid settings keys" in detail["error"]["message"]

    def test_put_settings_invalid_desired_retention_returns_400(
        self,
        client: TestClient,
        test_db: Session,
    ):
        response = client.put(
            "/api/v1/settings",
            json={"desired_retention": 1},
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error"]["code"] == "INVALID_SETTINGS"

    def test_put_settings_invalid_step_shape_validation(self, client: TestClient, test_db: Session):
        response = client.put(
            "/api/v1/settings",
            json={"learning_steps": "15,1440"},
        )

        assert response.status_code in [400, 422]

    def test_put_settings_invalid_source_scope_members(self, client: TestClient, test_db: Session):
        response = client.put(
            "/api/v1/settings",
            json={"default_source_scope": [1, -2]},
        )

        assert response.status_code == 400
        assert "positive integers only" in response.json()["detail"]["error"]["message"]

    def test_put_settings_empty_payload_returns_current_state(
        self,
        client: TestClient,
        test_db: Session,
    ):
        create_test_user_settings(test_db)

        response = client.put("/api/v1/settings", json={})

        assert response.status_code == 200
        assert response.json()["data"] == {
            "desired_retention": 0.9,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [1, 2],
        }
