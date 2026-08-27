"""Background task processing for LanGear."""

from app.tasks.review_task import process_review_task

__all__ = ["process_review_task"]
