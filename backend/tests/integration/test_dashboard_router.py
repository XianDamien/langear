"""
Integration tests for dashboard API endpoints.

Tests:
- GET /api/v1/dashboard - Dashboard statistics retrieval
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_data.fixtures import sample_multiple_reviews


@pytest.mark.integration
class TestDashboardRouter:
    """Test suite for dashboard API endpoints."""

    def test_get_dashboard_success(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns successful response."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        assert response.status_code == 200

    def test_get_dashboard_response_structure(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns correct response structure."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()
        assert "request_id" in data
        assert "data" in data
        assert isinstance(data["request_id"], str)
        assert isinstance(data["data"], dict)

    def test_get_dashboard_includes_request_id(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard includes valid request_id."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()
        request_id = data["request_id"]
        assert len(request_id) > 0
        # Request ID should be a UUID
        assert "-" in request_id

    def test_get_dashboard_data_structure(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns proper dashboard data structure."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        assert "today" in data
        assert "streak_days" in data
        assert "heatmap" in data

    def test_get_dashboard_today_structure(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns proper 'today' structure."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        today = data["today"]

        assert "new_limit" in today
        assert "review_limit" in today
        assert "completed" in today

        assert isinstance(today["new_limit"], int)
        assert isinstance(today["review_limit"], int)
        assert isinstance(today["completed"], int)

    def test_get_dashboard_default_limits(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns default limits when not configured."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        today = data["today"]

        assert today["new_limit"] == 20  # Default
        assert today["review_limit"] == 100  # Default
        assert today["completed"] == 0  # No reviews

    def test_get_dashboard_with_custom_settings(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard uses custom settings when configured."""
        # Arrange
        from app.models import Setting

        setting1 = Setting(key="daily_new_limit", value=30)
        setting2 = Setting(key="daily_review_limit", value=150)
        test_db.add_all([setting1, setting2])
        test_db.commit()

        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        today = data["today"]

        assert today["new_limit"] == 30
        assert today["review_limit"] == 150

    def test_get_dashboard_streak_days(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns streak_days as integer."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        assert isinstance(data["streak_days"], int)
        assert data["streak_days"] >= 0

    def test_get_dashboard_streak_days_with_reviews(self, client: TestClient, test_db: Session, sample_multiple_reviews):
        """Test GET /api/v1/dashboard calculates streak_days with review history."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        # sample_multiple_reviews creates 7 days of reviews
        assert data["streak_days"] >= 7

    def test_get_dashboard_heatmap_structure(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns proper heatmap structure."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        heatmap = data["heatmap"]

        assert isinstance(heatmap, list)
        assert len(heatmap) == 90  # Last 90 days

        # Verify each entry structure
        for entry in heatmap:
            assert "date" in entry
            assert "count" in entry
            assert isinstance(entry["date"], str)
            assert isinstance(entry["count"], int)
            assert entry["count"] >= 0

    def test_get_dashboard_heatmap_date_format(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard heatmap uses correct date format (YYYY-MM-DD)."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        heatmap = data["heatmap"]

        for entry in heatmap:
            # Verify date format can be parsed
            date_obj = datetime.strptime(entry["date"], "%Y-%m-%d")
            assert date_obj is not None

    def test_get_dashboard_heatmap_chronological_order(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard heatmap returns dates in chronological order."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        heatmap = data["heatmap"]

        dates = [datetime.strptime(entry["date"], "%Y-%m-%d") for entry in heatmap]
        for i in range(len(dates) - 1):
            assert dates[i] < dates[i + 1], "Dates should be in chronological order"

    def test_get_dashboard_heatmap_includes_review_counts(self, client: TestClient, test_db: Session, sample_multiple_reviews):
        """Test GET /api/v1/dashboard heatmap includes actual review counts."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        data = response.json()["data"]
        heatmap = data["heatmap"]

        # sample_multiple_reviews creates 7 reviews over 7 days
        non_zero_counts = [entry for entry in heatmap if entry["count"] > 0]
        assert len(non_zero_counts) >= 7

    def test_get_dashboard_empty_database(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard works with empty database."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["today"]["completed"] == 0
        assert data["streak_days"] == 0

        # All heatmap entries should have 0 count
        heatmap = data["heatmap"]
        for entry in heatmap:
            assert entry["count"] == 0

    def test_get_dashboard_no_query_parameters(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard does not accept query parameters."""
        # Act
        response = client.get("/api/v1/dashboard?limit=30")

        # Assert
        # Should still work, just ignores the parameter
        assert response.status_code == 200

    def test_get_dashboard_multiple_calls_consistency(self, client: TestClient, test_db: Session):
        """Test GET /api/v1/dashboard returns consistent results on multiple calls."""
        # Act
        response1 = client.get("/api/v1/dashboard")
        response2 = client.get("/api/v1/dashboard")

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()["data"]
        data2 = response2.json()["data"]

        # Core statistics should be the same
        assert data1["today"]["new_limit"] == data2["today"]["new_limit"]
        assert data1["today"]["review_limit"] == data2["today"]["review_limit"]
        assert data1["streak_days"] == data2["streak_days"]
        assert len(data1["heatmap"]) == len(data2["heatmap"])

    def test_get_dashboard_complete_response(self, client: TestClient, test_db: Session, sample_multiple_reviews):
        """Test GET /api/v1/dashboard returns complete valid response with all data."""
        # Act
        response = client.get("/api/v1/dashboard")

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert "request_id" in data
        assert "data" in data

        dashboard_data = data["data"]
        assert "today" in dashboard_data
        assert "streak_days" in dashboard_data
        assert "heatmap" in dashboard_data

        # Verify today data
        today = dashboard_data["today"]
        assert today["new_limit"] > 0
        assert today["review_limit"] > 0
        assert today["completed"] >= 0

        # Verify streak
        assert dashboard_data["streak_days"] >= 0

        # Verify heatmap
        assert len(dashboard_data["heatmap"]) == 90
