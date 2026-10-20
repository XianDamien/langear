"""Translate legacy lesson/card IDs at the API boundary, using only owned imported content.

This is a temporary compatibility surface. It is the only place that resolves
legacy integers, and it does so through the provenance written by the importer
(`Deck.source_metadata` / `Note.source_metadata`), never by parsing GUIDs.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import Field
from sqlalchemy import select

from core import auth
from core.content import ContentService
from core.db import get_db
from core.errors import DomainError
from core.models import Card, Deck, Note
from core.schemas import Body

router = APIRouter(prefix="/api/v1/review/legacy-lessons")


def service(collection=Depends(auth.identity), db=Depends(get_db, scope="function")):
    return ContentService(db, collection)


def lesson(service, lesson_id):
    deck = service.db.scalar(
        select(Deck).where(
            Deck.collection_id == service.collection.id,
            Deck.imported.is_(True),
            Deck.source_metadata["legacy_id"].astext == str(lesson_id),
        )
    )
    if deck is None:
        raise DomainError(
            404, "LEGACY_LESSON_NOT_IMPORTED", "This lesson has not been migrated."
        )
    return deck


def selected_ids(service, deck):
    selected = deck.scheduling_config.get("study_card_ids")
    if selected is None:
        return None
    values = service.db.scalars(
        select(Note.source_metadata["legacy_id"].astext)
        .join(Card, Card.note_id == Note.id)
        .where(
            Card.collection_id == service.collection.id,
            Card.deck_id == deck.id,
            Card.id.in_(selected),
            Note.imported.is_(True),
        )
    )
    return sorted({int(value) for value in values if value and value.isdigit()})


class LegacySelection(Body):
    card_ids: list[Annotated[int, Field(gt=0, le=2147483647, strict=True)]] | None


@router.get("/{lesson_id}/study-selection")
def get_selection(lesson_id: int = Path(gt=0), svc=Depends(service)):
    return {"card_ids": selected_ids(svc, lesson(svc, lesson_id))}


@router.put("/{lesson_id}/study-selection")
def put_selection(body: LegacySelection, lesson_id: int = Path(gt=0), svc=Depends(service)):
    svc.repo.lock()
    deck = lesson(svc, lesson_id)
    selected = sorted(set(body.card_ids)) if body.card_ids is not None else None
    ids = None
    if selected is not None:
        rows = list(
            svc.db.execute(
                select(Card.id, Note.source_metadata["legacy_id"].astext)
                .join(Note, Card.note_id == Note.id)
                .where(
                    Card.collection_id == svc.collection.id,
                    Card.deck_id == deck.id,
                    Note.imported.is_(True),
                    Note.source_metadata["legacy_id"].astext.in_(
                        [str(value) for value in selected]
                    ),
                )
            )
        )
        if {int(legacy_id) for _, legacy_id in rows if legacy_id} != set(selected):
            raise DomainError(
                422, "INVALID_LEGACY_CARDS", "Cards must belong to this imported lesson."
            )
        ids = sorted(str(card_id) for card_id, _ in rows)
    deck.scheduling_config = {
        **deck.scheduling_config,
        "study_card_ids": ids,
        "legacy_selection_user_updated": True,
    }
    deck.in_my_courses = selected != []
    svc.db.flush()
    lessons = sorted(
        int(row.source_metadata["legacy_id"])
        for row in imported_decks(svc)
        if row.in_my_courses and row.source_metadata.get("legacy_id")
    )
    return {"card_ids": selected, "lesson_ids": lessons}


class LegacyLessons(Body):
    lesson_ids: list[Annotated[int, Field(gt=0, le=2147483647, strict=True)]]


def imported_decks(svc):
    return svc.db.scalars(
        select(Deck).where(
            Deck.collection_id == svc.collection.id, Deck.imported.is_(True)
        )
    )


def owned_lessons(svc):
    """Imported Lessons that still own at least one Card."""
    return {
        int(row.source_metadata["legacy_id"]): row
        for row in imported_decks(svc)
        if row.source_metadata.get("legacy_id")
        and svc.db.scalar(select(Card.id).where(Card.deck_id == row.id).limit(1))
        is not None
    }


@router.get("")
def get_lessons(svc=Depends(service)):
    return {
        "lesson_ids": sorted(key for key, deck in owned_lessons(svc).items() if deck.in_my_courses)
    }


@router.put("")
def put_lessons(body: LegacyLessons, svc=Depends(service)):
    svc.repo.lock()
    decks = owned_lessons(svc)
    selected = set(body.lesson_ids)
    if selected - decks.keys():
        raise DomainError(
            422, "INVALID_LEGACY_LESSONS", "Select imported lessons in your Collection."
        )
    for key, deck in decks.items():
        deck.in_my_courses = key in selected
        deck.scheduling_config = {
            **deck.scheduling_config,
            "legacy_selection_user_updated": True,
        }
    svc.db.flush()
    return {"lesson_ids": sorted(selected)}
