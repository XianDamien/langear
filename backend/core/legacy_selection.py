"""Translate legacy lesson/card IDs at the API boundary, using only owned imported content."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path
from pydantic import Field
from sqlalchemy import select
from core import auth
from core.config import get_settings
from core.content import ContentService
from core.db import get_db
from core.errors import DomainError
from core.models import Card, Deck, Note
from core.schemas import Body

router = APIRouter(prefix="/api/v1/review/legacy-lessons")


def service(collection=Depends(auth.identity), db=Depends(get_db, scope="function")):
    return ContentService(db, collection)


def lesson(service, lesson_id):
    source = get_settings().legacy_import_source
    deck = service.db.scalar(select(Deck).where(
        Deck.collection_id == service.collection.id,
        Deck.deck_guid == f"legacy:{source}:deck:{lesson_id}",
    )) if source else None
    if deck is None:
        raise DomainError(404, "LEGACY_LESSON_NOT_IMPORTED", "This lesson has not been migrated.")
    return deck


def selected_ids(service, deck):
    selected = deck.scheduling_config.get("study_card_ids")
    if selected is None:
        return None
    return sorted(set(int(guid.rsplit(":", 1)[1]) for guid in service.db.scalars(
        select(Note.guid).join(Card, Card.note_id == Note.id).where(
            Card.collection_id == service.collection.id, Card.deck_id == deck.id,
            Card.id.in_(selected), Note.guid.startswith(f"legacy:{get_settings().legacy_import_source}:card:"),
        )
    )))


class LegacySelection(Body):
    card_ids: list[Annotated[int, Field(gt=0, le=2147483647, strict=True)]] | None


@router.get("/{lesson_id}/study-selection")
def get_selection(lesson_id: int = Path(gt=0), svc=Depends(service)):
    return {"card_ids": selected_ids(svc, lesson(svc, lesson_id))}


@router.put("/{lesson_id}/study-selection")
def put_selection(body: LegacySelection, lesson_id: int = Path(gt=0), svc=Depends(service)):
    svc.repo.lock()
    deck = lesson(svc, lesson_id)
    source = get_settings().legacy_import_source
    selected = sorted(set(body.card_ids)) if body.card_ids is not None else None
    ids = None
    if selected is not None:
        rows = list(svc.db.execute(select(Card.id, Note.guid).join(Note, Card.note_id == Note.id).where(
            Card.collection_id == svc.collection.id, Card.deck_id == deck.id,
            Note.guid.in_([f"legacy:{source}:card:{value}" for value in selected]),
        )))
        if {int(guid.rsplit(":", 1)[1]) for _, guid in rows} != set(selected):
            raise DomainError(422, "INVALID_LEGACY_CARDS", "Cards must belong to this imported lesson.")
        ids = sorted(str(card_id) for card_id, _ in rows)
    deck.scheduling_config = {**deck.scheduling_config, "study_card_ids": ids, "legacy_selection_user_updated": True}
    deck.in_my_courses = selected != []
    svc.db.flush()
    lessons = sorted(int(row.deck_guid.rsplit(":", 1)[1]) for row in svc.db.scalars(
        select(Deck).where(Deck.collection_id == svc.collection.id, Deck.in_my_courses.is_(True),
                           Deck.deck_guid.startswith(f"legacy:{source}:deck:"))
    ))
    return {"card_ids": selected, "lesson_ids": lessons}


class LegacyLessons(Body):
    lesson_ids: list[Annotated[int, Field(gt=0, le=2147483647, strict=True)]]


def owned_lessons(svc):
    source = get_settings().legacy_import_source
    if not source:
        return {}
    rows = svc.db.scalars(select(Deck).where(
        Deck.collection_id == svc.collection.id, Deck.deck_guid.startswith(f"legacy:{source}:deck:"),
        select(Card.id).where(Card.deck_id == Deck.id).exists(),
    ))
    return {int(row.deck_guid.rsplit(":", 1)[1]): row for row in rows}


@router.get("")
def get_lessons(svc=Depends(service)):
    return {"lesson_ids": sorted(key for key, deck in owned_lessons(svc).items() if deck.in_my_courses)}


@router.put("")
def put_lessons(body: LegacyLessons, svc=Depends(service)):
    svc.repo.lock()
    decks = owned_lessons(svc)
    selected = set(body.lesson_ids)
    if selected - decks.keys():
        raise DomainError(422, "INVALID_LEGACY_LESSONS", "Select imported lessons in your Collection.")
    for key, deck in decks.items():
        deck.in_my_courses = key in selected
        deck.scheduling_config = {**deck.scheduling_config, 'legacy_selection_user_updated': True}
    svc.db.flush()
    return {"lesson_ids": sorted(selected)}
