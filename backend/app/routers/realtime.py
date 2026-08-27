"""Realtime ASR router (WS + session status query)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.adapters.realtime_asr_adapter import DashScopeRealtimeASRBridge
from app.config import settings
from app.services.realtime_session_service import (
    RealtimeSessionError,
    get_realtime_session_store,
)

router = APIRouter(prefix="/api/v1/realtime", tags=["Realtime ASR"])


def _is_dashscope_provider() -> bool:
    return settings.realtime_asr_provider.strip().lower() == "dashscope"


async def _send_error(
    websocket: WebSocket,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    await websocket.send_json(
        {
            "type": "error",
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    )


async def _forward_dashscope_events(
    websocket: WebSocket,
    session_id: str,
    event_queue: asyncio.Queue[dict[str, Any]],
) -> None:
    """Forward DashScope callback events to frontend and update session store."""
    store = get_realtime_session_store()
    while True:
        wrapped_event = await event_queue.get()
        event_type = wrapped_event.get("type")

        if event_type == "__internal.connection.open":
            continue

        if event_type == "__internal.connection.close":
            reason = wrapped_event.get("reason") or "DashScope realtime connection closed"
            session = store.get_session(session_id)
            if session and session.status != "ready":
                store.mark_session_failed(session_id, reason)
                await _send_error(
                    websocket,
                    code="REALTIME_SESSION_FAILED",
                    message=reason,
                    retryable=True,
                )
            break

        if event_type != "__internal.dashscope.event":
            continue

        payload = wrapped_event.get("message") or {}
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
                await _send_error(
                    websocket,
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                )
            await websocket.send_json(payload)
            continue

        if message_type == "error":
            error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = str(error_payload.get("code") or "REALTIME_SESSION_FAILED")
            message = str(error_payload.get("message") or payload.get("message") or "Realtime error")
            retryable = bool(error_payload.get("retryable", True))
            store.mark_session_failed(session_id, message)
            await _send_error(websocket, code=code, message=message, retryable=retryable)
            await websocket.send_json(payload)
            continue

        # Keep passthrough for optional debug/observability on frontend.
        await websocket.send_json(payload)


@router.websocket("/asr/ws")
async def realtime_asr_ws(
    websocket: WebSocket,
    lesson_id: int = Query(...),
    card_id: int = Query(...),
):
    """Realtime ASR websocket endpoint."""
    await websocket.accept()

    store = get_realtime_session_store()
    session = store.create_session(
        lesson_id=lesson_id,
        card_id=card_id,
        model=settings.realtime_asr_model,
    )
    session_id = session.id

    await websocket.send_json(
        {
            "type": "session.created",
            "session": {
                "id": session_id,
                "model": settings.realtime_asr_model,
            },
            "realtime_session_id": session_id,
        }
    )

    bridge: DashScopeRealtimeASRBridge | None = None
    dashscope_forward_task: asyncio.Task[None] | None = None

    if _is_dashscope_provider():
        bridge = DashScopeRealtimeASRBridge(
            api_key=settings.dashscope_api_key,
            model=settings.realtime_asr_model,
            language=settings.realtime_asr_language,
            ws_base_url=settings.realtime_asr_ws_base_url,
        )
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        try:
            await asyncio.to_thread(bridge.connect, asyncio.get_running_loop(), event_queue)
            dashscope_forward_task = asyncio.create_task(
                _forward_dashscope_events(
                    websocket=websocket,
                    session_id=session_id,
                    event_queue=event_queue,
                )
            )
        except Exception as exc:
            error_message = f"Failed to connect DashScope realtime ASR: {exc}"
            store.mark_session_failed(session_id, error_message)
            await _send_error(
                websocket,
                code="REALTIME_SESSION_FAILED",
                message=error_message,
                retryable=True,
            )
            await websocket.close()
            return

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type in {"session.start", "session.update"}:
                continue

            if message_type in {"audio.append", "input_audio_buffer.append"}:
                audio_base64 = message.get("chunk_base64") or message.get("audio") or ""
                if not audio_base64:
                    await _send_error(
                        websocket,
                        code="REALTIME_SESSION_FAILED",
                        message="Missing audio chunk in append message",
                        retryable=True,
                    )
                    continue

                if bridge:
                    try:
                        store.mark_collecting(session_id)
                        await asyncio.to_thread(bridge.append_audio, str(audio_base64))
                    except Exception as exc:
                        message_text = f"Failed to append realtime audio: {exc}"
                        store.mark_session_failed(session_id, message_text)
                        await _send_error(
                            websocket,
                            code="REALTIME_SESSION_FAILED",
                            message=message_text,
                            retryable=True,
                        )
                    continue

                # Mock provider fallback for local testing.
                try:
                    updated = store.append_audio_chunk(
                        session_id=session_id,
                        chunk_base64=str(audio_base64),
                    )
                    await websocket.send_json({"type": "transcript.partial", "text": updated.partial_text})
                    await websocket.send_json(
                        {
                            "type": "conversation.item.input_audio_transcription.text",
                            "text": updated.partial_text,
                        }
                    )
                except RealtimeSessionError as exc:
                    await _send_error(
                        websocket,
                        code=exc.code,
                        message=exc.message,
                        retryable=exc.retryable,
                    )
                continue

            if message_type in {"audio.commit", "input_audio_buffer.commit"}:
                if bridge:
                    try:
                        store.mark_finalizing(session_id)
                        await asyncio.to_thread(bridge.commit)
                    except Exception as exc:
                        message_text = f"Failed to commit realtime audio: {exc}"
                        store.mark_session_failed(session_id, message_text)
                        await _send_error(
                            websocket,
                            code="REALTIME_SESSION_FAILED",
                            message=message_text,
                            retryable=True,
                        )
                    continue

                # Mock provider fallback for local testing.
                try:
                    updated = store.commit_session(session_id)
                    await websocket.send_json({"type": "transcript.final", "text": updated.final_text})
                    await websocket.send_json(
                        {
                            "type": "conversation.item.input_audio_transcription.completed",
                            "transcript": updated.final_text,
                        }
                    )
                except RealtimeSessionError as exc:
                    await _send_error(
                        websocket,
                        code=exc.code,
                        message=exc.message,
                        retryable=exc.retryable,
                    )
                continue

            if message_type == "session.end":
                store.close_session(session_id)
                if bridge:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(bridge.close)
                await websocket.send_json({"type": "session.closed"})
                await websocket.close()
                break

            await _send_error(
                websocket,
                code="REALTIME_SESSION_FAILED",
                message=f"Unsupported event type: {message_type}",
                retryable=False,
            )

    except WebSocketDisconnect:
        store.mark_session_failed(session_id, "Connection closed before transcript was finalized")

    finally:
        if bridge:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(bridge.close)
        if dashscope_forward_task:
            dashscope_forward_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dashscope_forward_task


@router.get("/asr/sessions/{realtime_session_id}")
def get_realtime_session(realtime_session_id: str):
    """Query realtime ASR session state."""
    request_id = str(uuid.uuid4())
    store = get_realtime_session_store()
    session = store.get_session(realtime_session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "REALTIME_SESSION_NOT_FOUND",
                    "message": f"Realtime session {realtime_session_id} not found",
                },
            },
        )

    return {
        "request_id": request_id,
        "data": session.to_api_dict(),
    }
