from uuid import UUID, uuid4
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from core.models import Card, CardTemplate, MediaAsset, ProcessingOutbox, utcnow
from core import processing
from core_tests.test_review import make_note, queue, next_card, flip, rate


def recording(engine, account, ready=False):
    with Session(engine) as db, db.begin():
        asset = MediaAsset(collection_id=UUID(account["collection"]["id"]), object_key=f"{uuid4()}.webm", kind="audio", lifecycle="ready" if ready else "temporary", uploaded_at=utcnow())
        db.add(asset)
        db.flush()
        return str(asset.id)


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
    assert saved["ai_status"] == "pending"
    from datetime import UTC, datetime, timedelta
    for _ in range(2):
        with Session(engine) as db, db.begin():
            db.scalar(select(ProcessingOutbox)).next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        assert processing.process_one(engine)
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
    from core.integrations.realtime_session import get_store

    store = get_store()
    store.clear()
    owner = UUID(account["collection"]["id"]).int
    asset = recording(engine, account)
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    current = next_card(client, q)
    foreign = store.create_session(deck_id=UUID(account["deck_id"]), card_id=uuid4(), owner=owner, model="test")
    store.mark_ready(foreign.id, "Hello")
    data = {"type": "audio", "temporary_media_asset_id": asset, "realtime_session_id": foreign.id}
    assert flip(client, q, current, data).status_code == 422
    stream = store.create_session(
        deck_id=UUID(account["deck_id"]),
        card_id=UUID(current["card"]["id"]),
        owner=owner,
        model="test",
    )
    store.mark_ready(stream.id, "Hello")
    saved = flip(
        client, q, current, {**data, "realtime_session_id": stream.id}
    ).json()
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
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "realtime_asr_provider", "mock")
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    card = next_card(client, queue(client, account))["card"]["id"]
    url = f"/api/v1/review/realtime/asr/ws?card_id={card}"
    with client.websocket_connect("wss://testserver" + url, headers={"Origin": "http://localhost:3002"}) as socket:
        created = socket.receive_json()
        assert created["type"] == "session.created"
        assert created["realtime_session_id"]
        socket.send_json({"type": "audio.append", "chunk_base64": "aGVsbG8="})
        assert socket.receive_json()["type"] == "transcript.partial"
        assert socket.receive_json()["type"] == "conversation.item.input_audio_transcription.text"
        socket.send_json({"type": "audio.commit"})
        seen = set()
        while "transcript.final" not in seen:
            seen.add(socket.receive_json()["type"])
        socket.send_json({"type": "session.end"})
        types = set()
        while "session.closed" not in types:
            types.add(socket.receive_json()["type"])
    client.post("/api/v1/auth/register", json={"email": "foreign@example.com", "password": "a strong other password"})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("wss://testserver" + url, headers={"Origin": "http://localhost:3002"}):
            pass


def test_expired_realtime_stream_recovers_from_the_owned_audio(client, account, engine, monkeypatch):
    from core.integrations.realtime_session import get_store

    get_store().clear()
    asset = recording(engine, account)
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    saved = flip(client, q, next_card(client, q), {"type": "audio", "temporary_media_asset_id": asset, "realtime_session_id": "expired-stream"})
    assert saved.status_code == 200
    assert saved.json()["attempt"]["asr_status"] == "pending"
    assert saved.json()["attempt"]["media_asset_id"] == asset
    with Session(engine) as db:
        assert {job.kind for job in db.scalars(select(ProcessingOutbox))} == {"asr", "ai"}


def test_sentence_template_scope_filters_cards_counts_and_learning_ahead(client, account, engine):
    reference = recording(engine, account, ready=True)
    for template in ("sentence_retelling", "sentence_translation", "sentence_dictation"):
        make_note(client, account, {"english": "Hello", "chinese": "你好", "reference_audio": reference}, template)
    from datetime import UTC, datetime, timedelta
    with Session(engine) as db, db.begin():
        card = db.scalar(select(Card).join(CardTemplate, Card.card_template_id == CardTemplate.id).where(CardTemplate.key == "sentence_dictation"))
        card.queue, card.type, card.new_position = "learning", "learning", None
        card.due_at = datetime.now(UTC) + timedelta(minutes=5)
    response = client.post("/api/v1/review/queues", json={"scope": {"deck_id": account["deck_id"], "card_template_keys": ["sentence_retelling"]}})
    assert response.status_code == 200, response.text
    current = next_card(client, response.json()["queue_id"])
    assert current["card"]["card_template_key"] == "sentence_retelling"
    assert current["new_remaining"] == 1 and current["learning_remaining"] == 0
    for value in ([], ["unknown_template"]):
        assert client.post("/api/v1/review/queues", json={"scope": {"deck_id": account["deck_id"], "card_template_keys": value}}).status_code == 422


def test_pending_other_template_requires_explicit_resume_and_preserves_answer(client, account):
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "text", "text": "My saved translation"}).json()
    blocked = client.post("/api/v1/review/queues", json={"scope": {"deck_id": account["deck_id"], "card_template_keys": ["sentence_retelling"]}})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["card_template_key"] == "sentence_translation"
    assert client.get(f"/api/v1/attempts/{original['attempt']['id']}").json()["input_snapshot"]["text"] == "My saved translation"
    # A rejected scope leaves the previous queue intact.
    assert next_card(client, q)["attempt"]["id"] == original["attempt"]["id"]
    resumed = client.post("/api/v1/review/queues", json={"scope": {"deck_id": account["deck_id"], "card_template_keys": ["sentence_translation"]}})
    assert resumed.status_code == 200
    recovered = next_card(client, resumed.json()["queue_id"])
    assert recovered["attempt"]["id"] == original["attempt"]["id"]
    assert rate(client, resumed.json()["queue_id"], recovered, "easy").status_code == 200
    assert client.post("/api/v1/review/queues", json={"scope": {"deck_id": account["deck_id"], "card_template_keys": ["sentence_retelling"]}}).status_code == 200

def test_worker_retries_with_backoff_then_exposes_manual_retry(client, account, engine, monkeypatch):
    from datetime import UTC, datetime, timedelta
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "text", "text": "Hi"}).json()
    provider = Mock()
    provider.generate_translation_feedback.side_effect = RuntimeError("secret")
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    now = datetime.now(UTC)
    monkeypatch.setattr(processing, "utcnow", lambda: now, raising=False)
    assert processing.process_one(engine)
    path = f"/api/v1/attempts/{original['attempt']['id']}"
    assert client.get(path).json()["ai_status"] == "pending"
    assert not processing.process_one(engine)
    now += timedelta(seconds=5)
    assert processing.process_one(engine)
    assert not processing.process_one(engine)
    now += timedelta(seconds=10)
    assert processing.process_one(engine)
    assert client.get(path).json()["ai_status"] == "failed"
    assert provider.generate_translation_feedback.call_count == 3
    assert rate(client, q, original, "easy").status_code == 200
    retry = client.post(path + "/retry")
    assert retry.status_code == 200, retry.text
    assert retry.json()["ai_status"] == "pending"
    assert retry.json()["rating"] == "easy"
    assert retry.json()["input_snapshot"] == original["attempt"]["input_snapshot"]
    assert client.post(path + "/retry").status_code == 200
    provider.generate_translation_feedback.side_effect = None
    provider.generate_translation_feedback.return_value = {"summary": "正确"}
    assert processing.process_one(engine)
    assert client.get(path).json()["ai_status"] == "succeeded"
    assert not processing.process_one(engine)
    assert "secret" not in str(client.get(path).json())
    client.headers.pop("X-CSRF-Token")
    assert client.post(path + "/retry").status_code == 403
    foreign = client.post("/api/v1/auth/register", json={"email": "foreign-retry@example.com", "password": "a strong other password"})
    client.headers["X-CSRF-Token"] = foreign.json()["csrf_token"]
    assert client.post(path + "/retry").status_code == 404


def test_asr_backoff_blocks_ai_until_transcript_resolves(client, account, engine, monkeypatch):
    from datetime import UTC, datetime, timedelta
    make_note(client, account, {"english": "Hello", "reference_audio": recording(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    original = flip(client, q, next_card(client, q), {"type": "audio", "temporary_media_asset_id": recording(engine, account)}).json()
    monkeypatch.setattr(processing, "sign_media", lambda key: "https://test/" + key)
    transcribe = Mock(side_effect=RuntimeError("unavailable"))
    provider = Mock()
    provider.generate_single_feedback.return_value = {"summary": "正确"}
    monkeypatch.setattr(processing, "transcribe", transcribe)
    monkeypatch.setattr(processing, "feedback_provider", lambda: provider)
    now = datetime.now(UTC)
    monkeypatch.setattr(processing, "utcnow", lambda: now, raising=False)
    assert processing.process_one(engine)
    assert not processing.process_one(engine)
    provider.generate_single_feedback.assert_not_called()
    transcribe.side_effect = None
    transcribe.return_value = {"text": "Qwen transcript"}
    now += timedelta(seconds=5)
    assert processing.process_one(engine)
    assert processing.process_one(engine)
    saved = client.get(f"/api/v1/attempts/{original['attempt']['id']}").json()
    assert saved["asr_status"] == saved["ai_status"] == "succeeded"
    assert saved["asr_result"]["text"] == "Qwen transcript"
