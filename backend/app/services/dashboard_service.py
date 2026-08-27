"""Dashboard service for statistics and analytics."""

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.review_log_repo import ReviewLogRepository
from app.repositories.settings_repo import SettingsRepository
from app.utils.timezone import app_now


class DashboardService:
    """Service for dashboard statistics and study analytics."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.review_log_repo = ReviewLogRepository(db)
        self.settings_repo = SettingsRepository(db)

    def get_dashboard_stats(self) -> dict[str, Any]:
        """Get dashboard statistics.

        Returns:
            Dictionary with:
            - today: Today's study limits and completed count
            - streak_days: Consecutive study days
            - heatmap: Study activity heatmap (last 90 days)

        Example:
            {
                "today": {
                    "new_limit": 20,
                    "review_limit": 100,
                    "completed": 36
                },
                "streak_days": 7,
                "heatmap": [
                    {"date": "2026-02-05", "count": 18},
                    {"date": "2026-02-06", "count": 24},
                    ...
                ]
            }
        """
        # Get settings
        settings = self.settings_repo.get_all()
        daily_new_limit = settings.get("daily_new_limit", 20)
        daily_review_limit = settings.get("daily_review_limit", 100)

        # Get today's completed reviews
        today = app_now(self.db)
        today_completed = self.review_log_repo.count_reviews_by_date(today)

        # Calculate streak days (simplified - count consecutive days with reviews)
        streak_days = self._calculate_streak()

        # Generate heatmap for last 90 days
        heatmap = self._generate_heatmap(days=90)

        return {
            "today": {
                "new_limit": daily_new_limit,
                "review_limit": daily_review_limit,
                "completed": today_completed,
            },
            "streak_days": streak_days,
            "heatmap": heatmap,
        }

    def _calculate_streak(self) -> int:
        """Calculate consecutive study days ending today.

        Returns:
            Number of consecutive days with at least one review
        """
        streak = 0
        current_date = app_now(self.db)

        while True:
            count = self.review_log_repo.count_reviews_by_date(current_date)
            if count == 0:
                break
            streak += 1
            current_date -= timedelta(days=1)

            # Limit streak calculation to 365 days
            if streak >= 365:
                break

        return streak

    def _generate_heatmap(self, days: int = 90) -> list[dict[str, Any]]:
        """Generate study activity heatmap.

        Args:
            days: Number of days to include (default: 90)

        Returns:
            List of {date: str, count: int} objects
        """
        heatmap = []
        current_date = app_now(self.db)

        for i in range(days):
            date = current_date - timedelta(days=i)
            count = self.review_log_repo.count_reviews_by_date(date)

            heatmap.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "count": count,
                }
            )

        # Return in chronological order (oldest first)
        return list(reversed(heatmap))
