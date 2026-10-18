from uuid import UUID, uuid4
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from core.config import get_settings
from core.models import Attempt, Deck, MediaAsset, ProcessingOutbox, utcnow
from core import processing
from core_tests.test_review import make_note, queue, next_card, flip, rate


def recording(engine, account, ready=False):
    with Session(engine) as db, db.begin():
        asset = MediaAsset(collection_id=UUID(account["collection"]["id"]), object_key=f"{uuid4()}.webm", kind="audio", lifecycle="ready" if ready else "temporary", uploaded_at=utcnow())
        db.add(asset)
        db.flush()
        return str(asset.id)


def test_legacy_entry_uses_current_collection_and_configured_source(client, account, engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "legacy_import_source", "fixture")
    with Session(engine) as db, db.begin():
        db.get(Deck, UUID(account["deck_id"])).deck_guid = "legacy:fixture:deck:42"
    assert client.get("/api/v1/review/legacy-lessons/42").json() == {"deck_id": account["deck_id"]}
    assert client.get("/api/v1/review/legacy-lessons/43").status_code == 404
    assert client.get("/api/v1/review/legacy-lessons/0").status_code == 422
    monkeypatch.setattr(get_settings(), "legacy_import_source", "other-source")
    assert client.get("/api/v1/review/legacy-lessons/42").status_code == 404
    monkeypatch.setattr(get_settings(), "legacy_import_source", "fixture")
    client.post("/api/v1/auth/register", json={"email": "second@example.com", "password": "a strong second password"})
    assert client.get("/api/v1/review/legacy-lessons/42").status_code == 404


def test_processing_retains_input_and_transcript_through_rating_and_undo(client, account, engine, monkeypatch):
    asset = recording(engine, account)
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "audio", "temporary_media_asset_id": asset}).json()
    assert rate(client, q, original, "easy").status_code == 200
    monkeypatch.setattr(processing, "sign_media", lambda key: "https://test/" + key)
    monkeypatch.setattr(processing, "transcribe", lambda _: {"text": "Qwen transcript", "timestamps": []})
    provider = Mock()
    provider.generate_single_feedback.return_value = {"pronunciation": "清晰", "issues": [], "transcription_text": "another model transcript"}
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    assert processing.process_one(engine)
    assert processing.process_one(engine)
    assert not processing.process_one(engine)
    saved = client.get(f"/api/v1/attempts/{original['attempt']['id']}").json()
    assert saved["asr_result"]["text"] == "Qwen transcript"
    assert saved["ai_feedback"]["pronunciation"] == "清晰"
    assert saved["rating"] == "easy"
    assert saved["input_snapshot"] == original["attempt"]["input_snapshot"]
    restored = client.post(f"/api/v1/review/queues/{q}/undo").json()
    assert restored["attempt"]["asr_result"] == saved["asr_result"]
    assert restored["attempt"]["ai_feedback"] == saved["ai_feedback"]
    assert rate(client, q, restored, "good").status_code == 200
    assert provider.generate_single_feedback.call_count == 1


def test_translation_processing_uses_snapshots_and_failure_does_not_block_rating(client, account, engine, monkeypatch):
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "text", "text": "  Hi  "}).json()
    provider = Mock()
    provider.generate_translation_feedback.side_effect = RuntimeError("secret provider body")
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    assert processing.process_one(engine)
    provider.generate_translation_feedback.assert_called_once_with("你好", "Hello", "  Hi  ")
    saved = client.get(f"/api/v1/attempts/{original['attempt']['id']}").json()
    assert saved["ai_status"] == "failed"
    assert "secret" not in str(saved)
    assert rate(client, q, original, "easy").status_code == 200
    assert not processing.process_one(engine)


def test_worker_rolls_back_abandoned_job_for_restart(client, account, engine, monkeypatch):
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "text", "text": "Hi"}).json()
    provider = Mock()
    provider.generate_translation_feedback.side_effect = KeyboardInterrupt
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    with pytest.raises(KeyboardInterrupt):
        processing.process_one(engine)
    with Session(engine) as db:
        assert db.scalar(select(ProcessingOutbox)).status == "pending"
    provider.generate_translation_feedback.side_effect = None
    provider.generate_translation_feedback.return_value = {"summary": "正确"}
    assert processing.process_one(engine)
    assert client.get(f"/api/v1/attempts/{original['attempt']['id']}").json()["ai_status"] == "succeeded"


def test_realtime_transcript_is_bound_to_collection_card_and_ready_stream(client, account, engine, monkeypatch):
    # Reuse the production transient store without loading runtime credentials.
    import sys
    from types import SimpleNamespace
    store = Mock()
    session = SimpleNamespace(lesson_id=UUID(account["collection"]["id"]).int, card_id=0, status="ready", final_text="Hello")
    store.get_session.return_value = session
    monkeypatch.setitem(sys.modules, "app.services.realtime_session_service", SimpleNamespace(get_realtime_session_store=lambda: store))
    asset = recording(engine, account)
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    current = next_card(client, q)
    data = {"type": "audio", "temporary_media_asset_id": asset, "realtime_session_id": "stream"}
    assert flip(client, q, current, data).status_code == 422
    session.card_id = UUID(current["card"]["id"]).int
    saved = flip(client, q, current, data).json()
    assert saved["attempt"]["asr_result"]["text"] == "Hello"
    assert saved["attempt"]["asr_status"] == "succeeded"
    with Session(engine) as db:
        assert [job.kind for job in db.scalars(select(ProcessingOutbox))] == ["ai"]


def test_realtime_socket_rejects_foreign_origin_and_foreign_card(client, account):
    make_note(client, account)
    card = next_card(client, queue(client, account))["card"]["id"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/review/realtime/asr/ws?card_id={card}", headers={"Origin": "https://evil.test"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/review/realtime/asr/ws?card_id={card}"):
            pass  # Vocabulary is not a recording template.


def test_worker_skips_a_job_owned_by_another_transaction(client, account, engine, monkeypatch):
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    flip(client, q, next_card(client, q), {"type": "text", "text": "Hi"})
    provider = Mock()
    provider.generate_translation_feedback.return_value = {"summary": "正确"}
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    with Session(engine) as owner, owner.begin():
        owner.scalar(select(ProcessingOutbox).with_for_update())
        assert processing.process_one(engine) is False
    assert processing.process_one(engine) is True
    assert provider.generate_translation_feedback.call_count == 1


def test_review_socket_reuses_bridge_only_after_card_ownership_check(client, account, engine, monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []

    async def bridge(websocket, lesson_id, card_id):
        calls.append((lesson_id, card_id))
        await websocket.accept()
        await websocket.send_json({"type": "session.created"})
        await websocket.close()

    monkeypatch.setitem(sys.modules, "app.routers.realtime", SimpleNamespace(realtime_asr_ws=bridge))
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    card = next_card(client, queue(client, account))["card"]["id"]
    url = f"/api/v1/review/realtime/asr/ws?card_id={card}"
    with client.websocket_connect("wss://testserver" + url, headers={"Origin": "http://localhost:3002"}) as socket:
        assert socket.receive_json()["type"] == "session.created"
    assert calls == [(UUID(account["collection"]["id"]).int, UUID(card).int)]
    client.post("/api/v1/auth/register", json={"email": "foreign@example.com", "password": "a strong other password"})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("wss://testserver" + url, headers={"Origin": "http://localhost:3002"}):
            pass
    assert len(calls) == 1


def test_expired_realtime_stream_recovers_from_the_owned_audio(client, account, engine, monkeypatch):
    import sys
    from types import SimpleNamespace
    store = Mock()
    store.get_session.return_value = None
    monkeypatch.setitem(sys.modules, "app.services.realtime_session_service", SimpleNamespace(get_realtime_session_store=lambda: store))
    asset = recording(engine, account)
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    saved = flip(client, q, next_card(client, q), {"type": "audio", "temporary_media_asset_id": asset, "realtime_session_id": "expired-stream"})
    assert saved.status_code == 200
    assert saved.json()["attempt"]["asr_status"] == "pending"
    assert saved.json()["attempt"]["media_asset_id"] == asset
    with Session(engine) as db:
        assert {job.kind for job in db.scalars(select(ProcessingOutbox))} == {"asr", "ai"}
