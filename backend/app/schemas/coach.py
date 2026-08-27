"""Pydantic schemas for coach agent APIs."""

from typing import Any

from pydantic import BaseModel, Field


class CoachChatRequest(BaseModel):
    """Request body for the Q&A coach chat endpoint."""

    user_id: int = Field(..., ge=1)
    lesson_id: int = Field(..., ge=1)
    message: str = Field(..., min_length=1)
    thread_id: str | None = None
    card_id: int | None = Field(default=None, ge=1)


class CoachThreadResponse(BaseModel):
    """Thread metadata returned by coach endpoints."""

    thread_id: str
    user_id: int
    lesson_id: int | None = None
    card_id: int | None = None
    last_update_time: float | None = None
    message_count: int = 0


class CoachMessageResponse(BaseModel):
    """Single thread message returned by coach endpoints."""

    author: str
    content: str
    timestamp: float | None = None
    invocation_id: str | None = None


class CoachCitation(BaseModel):
    """Citation payload returned alongside coach answers."""

    source_type: str
    lesson_id: int | None = None
    card_id: int | None = None
    review_log_id: int | None = None
    submission_id: int | None = None
    doc_path: str | None = None
    chunk_id: str | None = None
    title: str | None = None
    url: str | None = None
    excerpt: str | None = None
    score: float | None = None


class CoachJumpTarget(BaseModel):
    """Structured jump target for frontend navigation."""

    target_type: str
    lesson_id: int | None = None
    card_id: int | None = None
    review_log_id: int | None = None
    submission_id: int | None = None
    label: str | None = None


class CoachPreparedChat(BaseModel):
    """Prepared context bundle used internally before streaming."""

    user_id: int
    lesson_id: int
    card_id: int | None = None
    thread_id: str | None = None
    prompt: str
    citations: list[dict[str, Any]]
    jump_targets: list[dict[str, Any]]
    resource_links: list[dict[str, Any]]

