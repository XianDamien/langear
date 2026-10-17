from uuid import UUID
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from core.models import Card, MediaAsset, Note


@pytest.mark.parametrize(
    "key,kind",
    [
        ("vocabulary_english_to_chinese", "vocabulary"),
        ("vocabulary_chinese_to_english", "vocabulary"),
        ("sentence_retelling", "sentence"),
        ("sentence_translation", "sentence"),
        ("sentence_dictation", "sentence"),
    ],
)
def test_only_selected_template_is_created_and_persists(
    client, account, engine, key, kind
):
    with Session(engine) as db, db.begin():
        asset = MediaAsset(
            collection_id=UUID(account["collection"]["id"]),
            object_key="test/audio.mp3",
            kind="audio",
        )
        db.add(asset)
        db.flush()
        audio = str(asset.id)
    fields = (
        {"word": "hello", "meaning": "你好", "reference_audio": audio}
        if kind == "vocabulary"
        else {"english": "Hello.", "chinese": "你好。", "reference_audio": audio}
    )
    response = client.post(
        "/api/v1/notes",
        json={
            "deck_id": account["deck_id"],
            "note_type_key": kind,
            "card_template_key": key,
            "fields": fields,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["cards_created"]) == 1
    assert [card["card_template_key"] for card in body["cards"]] == [key]
    assert body["skipped_templates"] == []
    assert [
        card["card_template_key"]
        for card in client.get("/api/v1/cards").json()["cards"]
    ] == [key]
    # An ordinary note edit must not create the unselected siblings.
    response = client.put(
        "/api/v1/notes/" + body["id"], json={"revision": 1, "fields": fields}
    )
    assert response.status_code == 200
    assert len(response.json()["cards"]) == 1


@pytest.mark.parametrize(
    "key,fields",
    [
        ("sentence_dictation", {"english": "Hello."}),
        ("sentence_translation", {"english": "Hello."}),
        ("vocabulary_english_to_chinese", {"english": "Hello.", "chinese": "你好"}),
        ("unknown", {"english": "Hello.", "chinese": "你好"}),
    ],
)
def test_invalid_selection_or_missing_required_fields_rolls_back(
    client, account, engine, key, fields
):
    response = client.post(
        "/api/v1/notes",
        json={
            "deck_id": account["deck_id"],
            "note_type_key": "sentence",
            "card_template_key": key,
            "fields": fields,
        },
    )
    assert response.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Note)) == 0
        assert db.scalar(select(func.count()).select_from(Card)) == 0
