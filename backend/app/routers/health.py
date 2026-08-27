"""Health check router."""

from fastapi import APIRouter

from app.utils.timezone import app_now

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Health check endpoint.

    Returns:
        Service status and timestamp
    """
    return {
        "status": "healthy",
        "timestamp": app_now().isoformat(),
    }
