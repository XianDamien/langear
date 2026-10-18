"""Authenticated Review transport for the existing Qwen realtime bridge."""
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket
from sqlalchemy.orm import Session

from core import auth
from core.db import get_engine
from core.errors import DomainError
from core.models import Card, CardTemplate

router = APIRouter(prefix="/api/v1/review/realtime")


@router.websocket("/asr/ws")
async def realtime_asr(websocket: WebSocket, card_id: UUID):
    # A browser websocket sends the opaque session cookie and Origin. Reuse the
    # HTTP session expiry/disabled-user checks without requiring a CSRF header.
    scope = {**websocket.scope, "type": "http", "method": "GET"}
    request = Request(scope)
    try:
        auth.require_origin(request)
        with Session(get_engine()) as db, db.begin():
            collection = auth.identity(request, db)
            card = db.get(Card, card_id)
            template = db.get(CardTemplate, card.card_template_id) if card else None
            if card is None or card.collection_id != collection.id or template.key != "sentence_retelling":
                raise DomainError(404, "NOT_FOUND", "Card not found.")
            collection_id = collection.id
    except DomainError:
        await websocket.close(code=1008)
        return
    # No legacy database access: only its provider bridge and transient stream
    # store are reused. Namespaced UUID integers bind each stream to its owner.
    from app.routers.realtime import realtime_asr_ws
    await realtime_asr_ws(websocket, lesson_id=collection_id.int, card_id=card_id.int)


def transcript_for(session_id, collection_id, card_id):
    from app.services.realtime_session_service import get_realtime_session_store
    session = get_realtime_session_store().get_session(session_id)
    # Streams are transient. A recovered upload survives an API restart/TTL
    # expiry and can be transcribed from its authorized recording by the outbox.
    if session is None:
        return None
    if session.lesson_id != collection_id.int or session.card_id != card_id.int:
        raise DomainError(422, "REALTIME_TRANSCRIPT_NOT_READY", "The recording transcript is not ready.")
    if session.status != "ready" or not session.final_text.strip():
        return None
    return {"text": session.final_text, "timestamps": []}
