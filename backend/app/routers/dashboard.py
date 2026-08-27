"""Dashboard router for statistics and analytics."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db)):
    """Get dashboard statistics.

    Returns:
        Response with dashboard data:
        - request_id: Unique request ID
        - data:
            - today: Today's limits and completed count
            - streak_days: Consecutive study days
            - heatmap: Study activity heatmap (last 90 days)

    Example response:
        {
            "request_id": "...",
            "data": {
                "today": {
                    "new_limit": 20,
                    "review_limit": 100,
                    "completed": 36
                },
                "streak_days": 7,
                "heatmap": [...]
            }
        }
    """
    request_id = str(uuid.uuid4())

    dashboard_service = DashboardService(db)
    stats = dashboard_service.get_dashboard_stats()

    return {
        "request_id": request_id,
        "data": stats,
    }
