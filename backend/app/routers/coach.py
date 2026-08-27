"""Coach router for lesson Q&A chat."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.coach import CoachChatRequest
from app.services.coach_service import CoachService

router = APIRouter(prefix="/api/v1/coach", tags=["Coach"])


@router.post("/chat")
async def coach_chat(
    request: CoachChatRequest,
    db: Session = Depends(get_db),
):
    """Stream lesson-scoped Q&A responses as NDJSON events."""
    request_id = str(uuid.uuid4())
    service = CoachService(db)
    try:
        prepared = service.prepare_chat(
            user_id=request.user_id,
            lesson_id=request.lesson_id,
            message=request.message,
            thread_id=request.thread_id,
            card_id=request.card_id,
        )
    except ValueError as exc:
        error_message = str(exc)
        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=404,
                detail={
                    "request_id": request_id,
                    "error": {"code": "RESOURCE_NOT_FOUND", "message": error_message},
                },
            )
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {"code": "INVALID_REQUEST", "message": error_message},
            },
        )

    async def event_stream():
        try:
            async for event in service.stream_prepared_chat(prepared):
                yield json.dumps(
                    {"request_id": request_id, **event},
                    ensure_ascii=False,
                ) + "\n"
        except Exception as exc:  # pragma: no cover - fallback for stream runtime failures
            yield json.dumps(
                {
                    "request_id": request_id,
                    "type": "error",
                    "error": {
                        "code": "COACH_RUNTIME_ERROR",
                        "message": str(exc),
                    },
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/threads/{thread_id}")
def get_coach_thread(
    thread_id: str,
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    """Get metadata for one coach thread."""
    request_id = str(uuid.uuid4())
    service = CoachService(db)
    thread = service.get_thread(user_id=user_id, thread_id=thread_id)
    if thread is None:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "THREAD_NOT_FOUND",
                    "message": f"Coach thread {thread_id} not found",
                },
            },
        )

    return {
        "request_id": request_id,
        "data": thread,
    }


@router.get("/threads/{thread_id}/messages")
def get_coach_thread_messages(
    thread_id: str,
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    """Get deduplicated message history for one coach thread."""
    request_id = str(uuid.uuid4())
    service = CoachService(db)
    try:
        messages = service.get_thread_messages(user_id=user_id, thread_id=thread_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "THREAD_NOT_FOUND",
                    "message": str(exc),
                },
            },
        )

    return {
        "request_id": request_id,
        "data": messages,
    }
