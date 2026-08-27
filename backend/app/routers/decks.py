"""Decks and cards router for content queries."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.content_service import ContentService

router = APIRouter(prefix="/api/v1/decks", tags=["Decks"])


@router.get("/tree")
def get_deck_tree(db: Session = Depends(get_db)):
    """Get complete deck tree (sources -> units -> lessons).

    Returns:
        Response with deck tree:
        - request_id: Unique request ID
        - data:
            - sources: List of source decks with nested units and lessons
            - each lesson includes total_cards/completed_cards/due_cards/new_cards

    Example response:
        {
            "request_id": "...",
            "data": {
                "sources": [
                    {
                        "id": 1,
                        "title": "New Concept English Book 2",
                        "units": [...]
                    }
                ]
            }
        }
    """
    request_id = str(uuid.uuid4())

    content_service = ContentService(db)
    tree = content_service.get_deck_tree()

    return {
        "request_id": request_id,
        "data": tree,
    }


@router.get("/{lesson_id}/cards")
def get_lesson_cards(lesson_id: int, db: Session = Depends(get_db)):
    """Get all cards in a lesson.

    Args:
        lesson_id: Lesson deck ID

    Returns:
        Response with cards:
        - request_id: Unique request ID
        - data:
            - lesson_id: Lesson ID
            - cards: List of card objects with
              card_state/is_new_card/due_at/last_review_at

    Raises:
        404: If lesson not found
    """
    request_id = str(uuid.uuid4())

    try:
        content_service = ContentService(db)
        cards_data = content_service.get_lesson_cards(lesson_id)

        return {
            "request_id": request_id,
            "data": cards_data,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "LESSON_NOT_FOUND",
                    "message": str(e),
                },
            },
        )
