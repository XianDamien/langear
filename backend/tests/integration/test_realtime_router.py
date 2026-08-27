"""Integration tests for realtime ASR router."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.realtime_session_service import get_realtime_session_store


def _receive_until_type(ws, expected_type: str, max_reads: int = 6):
    for _ in range(max_reads):
        message = ws.receive_json()
        if message.get("type") == expected_type:
            return message
    raise AssertionError(f"Did not receive expected message type: {expected_type}")


@pytest.mark.integration
class TestRealtimeRouter:
    def test_realtime_ws_success_and_session_query(self, client: TestClient):
        """WS should emit session.created/partial/final and session query should return ready."""
        settings.realtime_asr_provider = "mock"
        store = get_realtime_session_store()
        store.clear()

        with client.websocket_connect("/api/v1/realtime/asr/ws?lesson_id=101&card_id=202") as ws:
            created_message = ws.receive_json()
            assert created_message["type"] == "session.created"
            session_id = created_message["realtime_session_id"]

            ws.send_json({"type": "session.start"})
            ws.send_json(
                {
                    "type": "audio.append",
                    "chunk_base64": base64.b64encode(b"audio-1").decode("utf-8"),
                    "seq": 1,
                    "ts_ms": 120,
                }
            )
            partial_message = _receive_until_type(ws, "transcript.partial")
            assert partial_message["type"] == "transcript.partial"
            assert partial_message["text"]

            ws.send_json({"type": "audio.commit"})
            final_message = _receive_until_type(ws, "transcript.final")
            assert final_message["type"] == "transcript.final"
            assert final_message["text"]
            completed_message = _receive_until_type(
                ws, "conversation.item.input_audio_transcription.completed"
            )
            assert completed_message["type"] == "conversation.item.input_audio_transcription.completed"
            assert completed_message["transcript"]

            query_resp = client.get(f"/api/v1/realtime/asr/sessions/{session_id}")
            assert query_resp.status_code == 200
            payload = query_resp.json()["data"]
            assert payload["status"] == "ready"
            assert payload["final_text"]

            ws.send_json({"type": "session.end"})
            closed_message = _receive_until_type(ws, "session.closed")
            assert closed_message["type"] == "session.closed"

    def test_realtime_ws_commit_without_audio_returns_error(self, client: TestClient):
        """Commit without appended audio should return REALTIME_SESSION_FAILED."""
        settings.realtime_asr_provider = "mock"
        store = get_realtime_session_store()
        store.clear()

        with client.websocket_connect("/api/v1/realtime/asr/ws?lesson_id=9&card_id=99") as ws:
            created_message = ws.receive_json()
            assert created_message["type"] == "session.created"
            ws.send_json({"type": "audio.commit"})
            error_message = ws.receive_json()
            assert error_message["type"] == "error"
            assert error_message["code"] == "REALTIME_SESSION_FAILED"

    def test_get_realtime_session_not_found(self, client: TestClient):
        """Session query should return 404 for unknown session id."""
        settings.realtime_asr_provider = "mock"
        store = get_realtime_session_store()
        store.clear()

        resp = client.get("/api/v1/realtime/asr/sessions/not-exists")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "REALTIME_SESSION_NOT_FOUND"
