"""Review transactions publish disposable runtime changes only after DB commit."""

from copy import deepcopy
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from core import auth
from core.db import get_engine
from core.models import Collection
from core.review import QUEUES, RUNTIME_LOCK, ReviewService
from core.review_schemas import Flip, QueueCreate, Rate, ScheduleAction, SchedulingPatch

router = APIRouter(prefix="/api/v1")
Identity = Annotated[Collection, Depends(auth.identity)]
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


def transact(collection, operation, *args):
    # Acquire/use/release in the same sync endpoint thread. A yielding dependency
    # may be resumed on a different thread and cannot own a threading.RLock.
    with RUNTIME_LOCK:
        before = deepcopy(QUEUES.get(collection.id))
        try:
            with Session(get_engine(), expire_on_commit=False) as db, db.begin():
                result = getattr(ReviewService(db, collection), operation)(*args)
            return result
        except BaseException:
            if before is None:
                QUEUES.pop(collection.id, None)
            else:
                QUEUES[collection.id] = before
            raise


@router.post("/review/queues")
def create_queue(body: QueueCreate, collection: Identity):
    return transact(collection, "build", body)


@router.get("/review/queues/{queue_id}/next")
def next_card(queue_id: UUID, collection: Identity):
    return transact(collection, "next", queue_id)


@router.post("/review/queues/{queue_id}/flip")
def flip(
    queue_id: UUID,
    body: Flip,
    key: IdempotencyKey,
    collection: Identity,
):
    return transact(collection, "flip", queue_id, body, key)


@router.put("/review/queues/{queue_id}/attempts/{attempt_id}/rating")
def rate(
    queue_id: UUID,
    attempt_id: UUID,
    body: Rate,
    key: IdempotencyKey,
    collection: Identity,
):
    return transact(collection, "rate", queue_id, attempt_id, body, key)


@router.post("/review/queues/{queue_id}/undo")
def undo(queue_id: UUID, collection: Identity):
    return transact(collection, "undo", queue_id)


@router.get("/attempts/{attempt_id}")
def attempt(attempt_id: UUID, collection: Identity):
    return transact(collection, "get_attempt", attempt_id)


@router.post("/cards/{card_id}/schedule")
def change_schedule(card_id: UUID, body: ScheduleAction, collection: Identity):
    return transact(collection, "change_schedule", card_id, body)


@router.get("/decks/{deck_id}/scheduling")
def scheduling(deck_id: UUID, collection: Identity):
    return transact(collection, "get_settings", deck_id)


@router.patch("/decks/{deck_id}/scheduling")
def update_scheduling(deck_id: UUID, body: SchedulingPatch, collection: Identity):
    return transact(collection, "update_settings", deck_id, body)
