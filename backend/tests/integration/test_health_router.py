"""
Integration tests for health check endpoint.

Tests the /health endpoint which provides service health status.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHealthRouter:
    """Test suite for health check API endpoint."""

    def test_health_check_success(self, client: TestClient):
        """Test GET /health returns successful health status."""
        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data

    def test_health_check_status_healthy(self, client: TestClient):
        """Test GET /health returns 'healthy' status."""
        # Act
        response = client.get("/health")

        # Assert
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_check_includes_timestamp(self, client: TestClient):
        """Test GET /health includes valid ISO timestamp."""
        # Act
        response = client.get("/health")

        # Assert
        data = response.json()
        assert "timestamp" in data

        timestamp = datetime.fromisoformat(data["timestamp"])
        assert timestamp is not None

    def test_health_check_timestamp_format(self, client: TestClient):
        """Test GET /health timestamp uses business timezone ISO 8601 offset."""
        # Act
        response = client.get("/health")

        # Assert
        data = response.json()
        assert datetime.fromisoformat(data["timestamp"]).utcoffset() == timedelta(hours=8)

    def test_health_check_no_request_id(self, client: TestClient):
        """Test GET /health does not include request_id (unlike other endpoints)."""
        # Act
        response = client.get("/health")

        # Assert
        data = response.json()
        assert "request_id" not in data

    def test_health_check_no_authentication(self, client: TestClient):
        """Test GET /health works without authentication."""
        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200

    def test_health_check_response_structure(self, client: TestClient):
        """Test GET /health returns exactly the expected fields."""
        # Act
        response = client.get("/health")

        # Assert
        data = response.json()
        assert set(data.keys()) == {"status", "timestamp"}

    def test_health_check_multiple_calls(self, client: TestClient):
        """Test GET /health returns consistent results on multiple calls."""
        # Act
        response1 = client.get("/health")
        response2 = client.get("/health")

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        assert data1["status"] == "healthy"
        assert data2["status"] == "healthy"
