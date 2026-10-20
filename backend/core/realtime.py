"""Authenticated Review realtime ASR transport; no legacy app dependency.

A browser websocket sends the opaque session cookie and Origin, so the HTTP
session expiry and disabled-user checks are reused without a CSRF header. Every
stream is bound to the owning Collection and Card at connect time.
"""

import asyncio
import contextlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core import auth
from core.config import get_settings
from core.db import get_engine
from core.errors import DomainError
from core.integrations.realtime_asr import DashScopeRealtimeASRBridge
from core.integrations.realtime_session import (
    RealtimeSessionError,
    get_store,
)
from core.models import Card, CardTemplate

router = APIRouter(prefix="/api/v1/review/realtime")


def dashscope_enabled():
    return get_settings().realtime_asr_provider.strip().lower() == "dashscope"


async def send_error(websocket, code, message, retryable):
    await websocket.send_json(
        {"type": "error", "code": code, "message": message, "retryable": retryable}
    )


async def forward_events(websocket, session_id, event_queue):
    store = get_store()
    while True:
        event = await event_queue.get()
        kind = event.get("type")
        if kind == "__internal.connection.open":
            continue
        if kind == "__internal.connection.close":
            reason = event.get("reason") or "DashScope realtime connection closed"
            session = store.get_session(session_id)
            if session and session.status != "ready":
                store.mark_session_failed(session_id, reason)
                await send_error(websocket, "REALTIME_SESSION_FAILED", reason, True)
            break
        if kind != "__internal.dashscope.event":
            continue
        payload = event.get("message") or {}
        message_type = payload.get("type")
        if message_type == "conversation.item.input_audio_transcription.text":
            text = str(payload.get("text") or "").strip()
            if text:
                store.update_partial_text(session_id, text)
                await websocket.send_json({"type": "transcript.partial", "text": text})
            await websocket.send_json(payload)
            continue
        if message_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(payload.get("transcript") or "").strip()
            try:
                store.mark_ready(session_id, transcript)
                await websocket.send_json({"type": "transcript.final", "text": transcript})
            except RealtimeSessionError as exc:
                store.mark_session_failed(session_id, exc.message)
                await send_error(websocket, exc.code, exc.message, exc.retryable)
            await websocket.send_json(payload)
            continue
        if message_type == "error":
            detail = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            message = str(
                detail.get("message") or payload.get("message") or "Realtime error"
            )
            store.mark_session_failed(session_id, message)
            await send_error(
                websocket,
                str(detail.get("code") or "REALTIME_SESSION_FAILED"),
                message,
                bool(detail.get("retryable", True)),
            )
            await websocket.send_json(payload)
            continue
        await websocket.send_json(payload)


@router.websocket("/asr/ws")
async def realtime_asr(websocket: WebSocket, card_id: UUID):
    scope = {**websocket.scope, "type": "http", "method": "GET"}
    request = Request(scope)
    try:
        auth.require_origin(request)
        with Session(get_engine()) as db, db.begin():
            collection = auth.identity(request, db)
            card = db.get(Card, card_id)
            template = db.get(CardTemplate, card.card_template_id) if card else None
            if (
                card is None
                or card.collection_id != collection.id
                or template.key != "sentence_retelling"
            ):
                raise DomainError(404, "NOT_FOUND", "Card not found.")
            owner = collection.id.int
            deck_id = card.deck_id
    except DomainError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    settings = get_settings()
    store = get_store()
    session = store.create_session(
        deck_id=deck_id, card_id=card_id, owner=owner, model=settings.realtime_asr_model
    )
    await websocket.send_json(
        {
            "type": "session.created",
            "session": {"id": session.id, "model": settings.realtime_asr_model},
            "realtime_session_id": session.id,
        }
    )

    bridge = None
    forward = None
    if dashscope_enabled():
        if not settings.asr_api_key:
            store.mark_session_failed(session.id, "Realtime ASR is not configured")
            await send_error(
                websocket, "REALTIME_SESSION_FAILED", "Realtime ASR is not configured", True
            )
            await websocket.close()
            return
        bridge = DashScopeRealtimeASRBridge(
            api_key=settings.asr_api_key.get_secret_value(),
            model=settings.realtime_asr_model,
            language=settings.realtime_asr_language,
            ws_base_url=settings.realtime_asr_ws_base_url,
        )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        try:
            await asyncio.to_thread(bridge.connect, asyncio.get_running_loop(), queue)
            forward = asyncio.create_task(forward_events(websocket, session.id, queue))
        except Exception:
            store.mark_session_failed(session.id, "Failed to connect realtime ASR")
            await send_error(
                websocket,
                "REALTIME_SESSION_FAILED",
                "Failed to connect realtime ASR",
                True,
            )
            await websocket.close()
            return

    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind in {"session.start", "session.update"}:
                continue
            if kind in {"audio.append", "input_audio_buffer.append"}:
                chunk = message.get("chunk_base64") or message.get("audio") or ""
                if not chunk:
                    await send_error(
                        websocket,
                        "REALTIME_SESSION_FAILED",
                        "Missing audio chunk in append message",
                        True,
                    )
                    continue
                if bridge:
                    try:
                        store.mark_collecting(session.id)
                        await asyncio.to_thread(bridge.append_audio, str(chunk))
                    except Exception:
                        store.mark_session_failed(
                            session.id, "Failed to append realtime audio"
                        )
                        await send_error(
                            websocket,
                            "REALTIME_SESSION_FAILED",
                            "Failed to append realtime audio",
                            True,
                        )
                    continue
                try:
                    updated = store.append_audio_chunk(session.id, str(chunk))
                    await websocket.send_json(
                        {"type": "transcript.partial", "text": updated.partial_text}
                    )
                    await websocket.send_json(
                        {
                            "type": "conversation.item.input_audio_transcription.text",
                            "text": updated.partial_text,
                        }
                    )
                except RealtimeSessionError as exc:
                    await send_error(websocket, exc.code, exc.message, exc.retryable)
                continue
            if kind in {"audio.commit", "input_audio_buffer.commit"}:
                if bridge:
                    try:
                        store.mark_finalizing(session.id)
                        await asyncio.to_thread(bridge.commit)
                    except Exception:
                        store.mark_session_failed(
                            session.id, "Failed to commit realtime audio"
                        )
                        await send_error(
                            websocket,
                            "REALTIME_SESSION_FAILED",
                            "Failed to commit realtime audio",
                            True,
                        )
                    continue
                try:
                    updated = store.commit_session(session.id)
                    await websocket.send_json(
                        {"type": "transcript.final", "text": updated.final_text}
                    )
                    await websocket.send_json(
                        {
                            "type": "conversation.item.input_audio_transcription.completed",
                            "transcript": updated.final_text,
                        }
                    )
                except RealtimeSessionError as exc:
                    await send_error(websocket, exc.code, exc.message, exc.retryable)
                continue
            if kind == "session.end":
                store.close_session(session.id)
                if bridge:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(bridge.close)
                await websocket.send_json({"type": "session.closed"})
                await websocket.close()
                break
            await send_error(
                websocket,
                "REALTIME_SESSION_FAILED",
                f"Unsupported event type: {kind}",
                False,
            )
    except WebSocketDisconnect:
        store.mark_session_failed(
            session.id, "Connection closed before transcript was finalized"
        )
    finally:
        if bridge:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(bridge.close)
        if forward:
            forward.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forward


def transcript_for(session_id, collection_id, card_id):
    """Read a finalized transcript from this process's live stream, if any."""
    session = get_store().get_session(session_id)
    if session is None:
        return None
    if session.owner != collection_id.int or session.card_id != card_id:
        raise DomainError(
            422,
            "REALTIME_TRANSCRIPT_NOT_READY",
            "The recording transcript is not ready.",
        )
    if session.status != "ready" or not session.final_text.strip():
        return None
    return {"text": session.final_text, "timestamps": []}
