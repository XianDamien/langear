from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.models import Attempt, Card, Collection, MediaAsset


def note(client, account, fields=None, kind="sentence", **extra):
    response = client.post(
        "/api/v1/notes",
        json={
            "note_type_key": kind,
            "fields": fields
            or {"english": "I came home late.", "chinese": "我回家晚了。"},
            "deck_id": account["deck_id"],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def asset(engine, collection_id, kind="audio"):
    with Session(engine) as db, db.begin():
        row = MediaAsset(
            collection_id=UUID(collection_id),
            object_key="test/" + str(uuid4()),
            kind=kind,
        )
        db.add(row)
        db.flush()
        return str(row.id)


def add_attempt(engine, item, collection_id):
    card = item["cards"][0]
    with Session(engine) as db, db.begin():
        row = Attempt(
            collection_id=UUID(collection_id),
            card_id=UUID(card["id"]),
            note_id=UUID(item["id"]),
            card_template_id=db.get(Card, UUID(card["id"])).card_template_id,
            note_snapshot=deepcopy(item["fields"]),
            front_snapshot=deepcopy(card["front"]),
            back_snapshot=deepcopy(card["back"]),
            answer_snapshot=deepcopy(card["answer"]),
            input_type="text",
            input_snapshot={"text": "My answer."},
        )
        db.add(row)
        db.flush()
        return row.id


def delete(client, kind, resource_id):
    preview = client.post(f"/api/v1/{kind}/{resource_id}/delete/preview")
    assert preview.status_code == 200, preview.text
    result = client.post(
        f"/api/v1/{kind}/{resource_id}/delete",
        json={"confirmation_token": preview.json()["confirmation_token"]},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_five_templates_dynamic_rendering_and_independent_cards(
    client, account, engine
):
    audio = asset(engine, account["collection"]["id"])
    sentence = note(
        client,
        account,
        {
            "english": "I came home late.",
            "chinese": "我回家晚了。",
            "reference_audio": audio,
        },
    )
    vocabulary = note(
        client, account, {"word": "apple", "meaning": "苹果"}, kind="vocabulary"
    )
    assert len(sentence["cards"]) == 3
    assert len(vocabulary["cards"]) == 2
    assert len({c["id"] for c in sentence["cards"] + vocabulary["cards"]}) == 5
    assert (
        len({c["new_position"] for c in sentence["cards"] + vocabulary["cards"]}) == 5
    )
    for card in sentence["cards"]:
        assert UUID(card["id"]).version == 7
        assert card["queue"] == "new" and card["fsrs_state"] is None
        if card["card_template_key"] == "sentence_translation":
            assert card["front"] == {"chinese": "我回家晚了。"}
            assert card["input_requirement"] == {"type": "text", "required": True}
        else:
            assert card["front"] == {"reference_audio": audio}
            assert "english" not in card["front"]
        assert "note" not in card["back"]
    assert [c["input_requirement"] for c in vocabulary["cards"]] == [
        {"type": "none", "required": False}
    ] * 2
    assert vocabulary["cards"][0]["front"] == {"word": "apple"}
    assert vocabulary["cards"][1]["front"] == {"meaning": "苹果"}


def test_missing_fields_reported_and_generation_is_idempotent(client, account, engine):
    item = note(client, account, {"english": "Hello."})
    assert item["cards"] == [] and len(item["skipped_templates"]) == 3
    audio = asset(engine, account["collection"]["id"])
    response = client.put(
        f"/api/v1/notes/{item['id']}",
        json={"revision": 1, "fields": {"english": "Hello.", "reference_audio": audio}},
    )
    assert response.status_code == 200
    assert response.json()["cards"] == []
    one = client.post(
        f"/api/v1/notes/{item['id']}/generate-cards",
        json={"deck_id": account["deck_id"]},
    ).json()
    two = client.post(
        f"/api/v1/notes/{item['id']}/generate-cards",
        json={"deck_id": account["deck_id"]},
    ).json()
    assert len(one["cards_created"]) == 2 and two["cards_created"] == []
    assert [c["id"] for c in one["cards"]] == [c["id"] for c in two["cards"]]


def test_revision_conflict_preserves_identity_and_attempt_snapshot(
    client, account, engine
):
    item = note(client, account)
    attempt_id = add_attempt(engine, item, account["collection"]["id"])
    body = {
        "revision": 1,
        "fields": {"english": "A revised sentence.", "chinese": "新句子。"},
        "tags": ["a", "a", " b "],
    }
    updated = client.put(f"/api/v1/notes/{item['id']}", json=body)
    assert updated.status_code == 200, updated.text
    value = updated.json()
    assert (
        value["id"] == item["id"]
        and value["guid"] == item["guid"]
        and value["revision"] == 2
    )
    assert value["cards"][0]["id"] == item["cards"][0]["id"]
    assert value["cards"][0]["back"]["english"] == "A revised sentence."
    assert value["tags"] == ["a", "b"]
    stale = client.put(f"/api/v1/notes/{item['id']}", json=body)
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["current_revision"] == 2
    with Session(engine) as db:
        assert db.get(Attempt, attempt_id).back_snapshot == item["cards"][0]["back"]
    invalid = client.put(
        f"/api/v1/notes/{item['id']}", json={"revision": 2, "fields": {"english": " "}}
    )
    assert invalid.status_code == 422
    assert client.get(f"/api/v1/notes/{item['id']}").json()["revision"] == 2


def test_concurrent_edit_one_winner(client, account):
    item = note(client, account)
    body = {"revision": 1, "fields": {"english": "Edited.", "chinese": "编辑。"}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.put(f"/api/v1/notes/{item['id']}", json=body), range(2)
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]


def test_concurrent_generation_no_duplicate_cards_or_positions(client, account):
    item = note(client, account)
    delete(client, "cards", item["cards"][0]["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    f"/api/v1/notes/{item['id']}/generate-cards",
                    json={"deck_id": account["deck_id"]},
                ),
                range(2),
            )
        )
    assert all(r.status_code == 200 for r in results)
    assert sorted(len(r.json()["cards_created"]) for r in results) == [0, 1]


def test_delete_card_keeps_note_siblings_and_regenerates_fresh_state(
    client, account, engine
):
    item = note(
        client, account, {"word": "apple", "meaning": "苹果"}, kind="vocabulary"
    )
    attempt_id = add_attempt(engine, item, account["collection"]["id"])
    deleted_id = item["cards"][0]["id"]
    delete(client, "cards", deleted_id)
    remaining = client.get(f"/api/v1/notes/{item['id']}").json()
    assert len(remaining["cards"]) == 1
    assert remaining["cards"][0]["id"] == item["cards"][1]["id"]
    with Session(engine) as db:
        assert db.get(Attempt, attempt_id) is None
    result = client.post(
        f"/api/v1/notes/{item['id']}/generate-cards",
        json={"deck_id": account["deck_id"]},
    ).json()
    assert (
        len(result["cards_created"]) == 1 and result["cards_created"][0] != deleted_id
    )
    for card in result["cards"]:
        delete(client, "cards", card["id"])
    assert client.get(f"/api/v1/notes/{item['id']}").json()["cards"] == []


def test_stale_deletion_preview_rejected_on_edit_or_new_attempt(
    client, account, engine
):
    item = note(client, account)
    preview = client.post(f"/api/v1/notes/{item['id']}/delete/preview").json()
    add_attempt(engine, item, account["collection"]["id"])
    result = client.post(
        f"/api/v1/notes/{item['id']}/delete",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    assert (
        result.status_code == 409
        and result.json()["error"]["code"] == "DELETION_IMPACT_CHANGED"
    )
    preview = client.post(f"/api/v1/notes/{item['id']}/delete/preview").json()
    client.put(
        f"/api/v1/notes/{item['id']}",
        json={"revision": 1, "fields": {"english": "Changed."}},
    )
    result = client.post(
        f"/api/v1/notes/{item['id']}/delete",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    assert result.status_code == 409
    assert client.get(f"/api/v1/notes/{item['id']}").status_code == 200


def test_deletion_token_is_bound_to_operation_and_resource(client, account):
    first, second = note(client, account), note(client, account)
    preview = client.post(f"/api/v1/notes/{first['id']}/delete/preview").json()
    for resource in [second["id"], first["cards"][0]["id"]]:
        kind = "notes" if resource == second["id"] else "cards"
        assert (
            client.post(
                f"/api/v1/{kind}/{resource}/delete",
                json={"confirmation_token": preview["confirmation_token"]},
            ).status_code
            == 409
        )
    assert (
        client.post(
            f"/api/v1/notes/{first['id']}/delete",
            json={"confirmation_token": "forged.token"},
        ).status_code
        == 409
    )


def test_type_switch_requires_mapping_and_replaces_cards_attempts(
    client, account, engine
):
    audio = asset(engine, account["collection"]["id"])
    item = note(
        client,
        account,
        {"word": "Hello.", "meaning": "你好。", "reference_audio": audio},
        kind="vocabulary",
        tags=["keep"],
    )
    attempt_id = add_attempt(engine, item, account["collection"]["id"])
    preview = client.post(
        f"/api/v1/notes/{item['id']}/change-type/preview",
        json={"target_note_type_key": "sentence"},
    ).json()
    assert (
        preview["impact"]["cards_deleted"] == 2
        and preview["impact"]["attempts_deleted"] == 1
    )
    body = {
        "revision": 1,
        "target_note_type_key": "sentence",
        "confirmation_token": preview["confirmation_token"],
        "field_mapping": {},
    }
    assert (
        client.post(f"/api/v1/notes/{item['id']}/change-type", json=body).status_code
        == 422
    )
    body["field_mapping"] = preview["suggested_field_mapping"]
    result = client.post(f"/api/v1/notes/{item['id']}/change-type", json=body)
    assert result.status_code == 200, result.text
    changed = result.json()
    assert (
        changed["id"] == item["id"]
        and changed["guid"] == item["guid"]
        and changed["tags"] == ["keep"]
    )
    assert changed["revision"] == 2 and len(changed["cards"]) == 3
    assert not set(c["id"] for c in item["cards"]) & set(
        c["id"] for c in changed["cards"]
    )
    assert all(c["fsrs_state"] is None and c["reps"] == 0 for c in changed["cards"])
    with Session(engine) as db:
        assert db.get(Attempt, attempt_id) is None
    assert (
        client.post(f"/api/v1/notes/{item['id']}/change-type", json=body).status_code
        == 409
    )


def test_type_mapping_invalid_and_multideck_requires_destination(client, account):
    item = note(
        client, account, {"word": "Hello.", "meaning": "你好。"}, kind="vocabulary"
    )
    other = client.post("/api/v1/decks", json={"name": "Another"}).json()
    assert (
        client.put(
            f"/api/v1/cards/{item['cards'][0]['id']}/deck",
            json={"deck_id": other["id"]},
        ).status_code
        == 200
    )
    preview = client.post(
        f"/api/v1/notes/{item['id']}/change-type/preview",
        json={"target_note_type_key": "sentence"},
    ).json()
    body = {
        "revision": 1,
        "target_note_type_key": "sentence",
        "confirmation_token": preview["confirmation_token"],
        "field_mapping": preview["suggested_field_mapping"],
    }
    response = client.post(f"/api/v1/notes/{item['id']}/change-type", json=body)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "TARGET_DECK_REQUIRED"
    )
    body["deck_id"] = account["deck_id"]
    body["field_mapping"]["reference_audio"] = "word"
    assert (
        client.post(f"/api/v1/notes/{item['id']}/change-type", json=body).status_code
        == 422
    )
    body["field_mapping"]["reference_audio"] = None
    body["field_mapping"]["english"] = None
    assert (
        client.post(f"/api/v1/notes/{item['id']}/change-type", json=body).status_code
        == 422
    )
    body["field_values"] = {"english": "Explicit replacement."}
    assert (
        client.post(f"/api/v1/notes/{item['id']}/change-type", json=body).status_code
        == 200
    )


def test_cross_collection_all_read_and_write_paths_return_404(client, account):
    item = note(client, account)
    old_deck, card_id = account["deck_id"], item["cards"][0]["id"]
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "a strong test password"},
    ).json()
    client.headers["X-CSRF-Token"] = other["csrf_token"]
    own_deck = client.get("/api/v1/decks").json()["decks"][0]["id"]
    cases = [
        ("get", f"/api/v1/notes/{item['id']}", None),
        ("get", f"/api/v1/cards/{card_id}", None),
        ("get", f"/api/v1/cards?deck_id={old_deck}", None),
        (
            "put",
            f"/api/v1/notes/{item['id']}",
            {"revision": 1, "fields": {"english": "Attack"}},
        ),
        ("post", f"/api/v1/notes/{item['id']}/generate-cards", {"deck_id": own_deck}),
        ("post", f"/api/v1/cards/{card_id}/delete/preview", None),
        (
            "post",
            f"/api/v1/notes/{item['id']}/change-type/preview",
            {"target_note_type_key": "vocabulary"},
        ),
        ("post", "/api/v1/decks", {"name": "child", "parent_id": old_deck}),
        ("put", f"/api/v1/cards/{card_id}/deck", {"deck_id": own_deck}),
    ]
    for method, path, body in cases:
        response = client.request(method.upper(), path, json=body)
        assert response.status_code == 404, (method, path, response.text)
    assert client.get("/api/v1/notes").json()["notes"] == []


def test_deck_cycles_names_subtree_delete_and_mixed_note_cards(client, account):
    parent = client.post("/api/v1/decks", json={"name": "Parent"}).json()
    child = client.post(
        "/api/v1/decks", json={"name": "Child", "parent_id": parent["id"]}
    ).json()
    assert client.post("/api/v1/decks", json={"name": "Parent"}).status_code == 409
    assert (
        client.post(
            "/api/v1/decks", json={"name": "Child", "parent_id": parent["id"]}
        ).status_code
        == 409
    )
    cycle = client.put(
        f"/api/v1/decks/{parent['id']}",
        json={"name": "Parent", "parent_id": child["id"]},
    )
    assert (
        cycle.status_code == 422
        and cycle.json()["error"]["code"] == "DECK_HIERARCHY_CYCLE"
    )
    item = note(
        client,
        {**account, "deck_id": child["id"]},
        {"word": "hello", "meaning": "你好"},
        kind="vocabulary",
    )
    client.put(
        f"/api/v1/cards/{item['cards'][0]['id']}/deck",
        json={"deck_id": account["deck_id"]},
    )
    result = delete(client, "decks", parent["id"])
    assert (
        result["impact"]["decks_deleted"] == 2
        and result["impact"]["cards_deleted"] == 1
    )
    assert len(client.get(f"/api/v1/notes/{item['id']}").json()["cards"]) == 1


def test_media_ownership_reference_cleanup_and_shared_library(client, account, engine):
    own_id = account["collection"]["id"]
    unused = asset(engine, own_id)
    audio = asset(engine, own_id)
    item = note(client, account, {"english": "Hello.", "reference_audio": audio})
    with Session(engine) as db, db.begin():
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        shared = MediaAsset(
            collection_id=library.id,
            collection_kind="library",
            kind="audio",
            scope="library_shared",
            object_key="library/shared.wav",
        )
        db.add(shared)
        db.flush()
        shared_id = str(shared.id)
    second = note(client, account, {"english": "Hi.", "reference_audio": shared_id})
    delete(client, "notes", item["id"])
    delete(client, "notes", second["id"])
    with Session(engine) as db:
        assert db.get(MediaAsset, UUID(audio)).lifecycle == "pending_delete"
        assert db.get(MediaAsset, UUID(unused)).lifecycle == "ready"
        assert db.get(MediaAsset, UUID(shared_id)).lifecycle == "ready"
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "another@example.com", "password": "a strong test password"},
    ).json()
    client.headers["X-CSRF-Token"] = other["csrf_token"]
    other_deck = client.get("/api/v1/decks").json()["decks"][0]["id"]
    response = client.post(
        "/api/v1/notes",
        json={
            "note_type_key": "sentence",
            "deck_id": other_deck,
            "fields": {"english": "Hi", "reference_audio": unused},
        },
    )
    assert response.status_code == 404


def test_library_and_system_notetypes_are_read_only(client, account):
    types = client.get("/api/v1/note-types").json()["note_types"]
    assert len(types) == 2 and sum(len(t["card_templates"]) for t in types) == 5
    assert all(t["read_only"] for t in types)
    library = client.get("/api/v1/library").json()
    assert library["read_only"] and library["id"] != account["collection"]["id"]
    assert client.post("/api/v1/note-types", json={"key": "custom"}).status_code == 405
    assert (
        client.post(
            "/api/v1/decks", json={"name": "forged", "collection_id": library["id"]}
        ).status_code
        == 422
    )


def test_expired_confirmation_and_stale_type_preview(client, account, monkeypatch):
    item = note(
        client, account, {"word": "hello", "meaning": "你好"}, kind="vocabulary"
    )
    preview = client.post(f"/api/v1/notes/{item['id']}/delete/preview").json()
    from core import confirmation

    original = confirmation.time.time
    with monkeypatch.context() as patch:
        patch.setattr(confirmation.time, "time", lambda: original() + 601)
        response = client.post(
            f"/api/v1/notes/{item['id']}/delete",
            json={"confirmation_token": preview["confirmation_token"]},
        )
        assert response.status_code == 409
    preview = client.post(
        f"/api/v1/notes/{item['id']}/change-type/preview",
        json={"target_note_type_key": "sentence"},
    ).json()
    client.put(
        f"/api/v1/notes/{item['id']}",
        json={"revision": 1, "fields": {"word": "changed", "meaning": "修改"}},
    )
    response = client.post(
        f"/api/v1/notes/{item['id']}/change-type",
        json={
            "revision": 2,
            "target_note_type_key": "sentence",
            "field_mapping": preview["suggested_field_mapping"],
            "confirmation_token": preview["confirmation_token"],
        },
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "NOTETYPE_CHANGE_CONFLICT"
    )


@pytest.mark.parametrize("delete_original", [False, True])
def test_filtered_card_delete_and_original_deck_delete_preserve_ownership(
    client, account, engine, delete_original
):
    from core.models import Deck

    item = note(client, account)
    card_id = item["cards"][0]["id"]
    with Session(engine) as db, db.begin():
        deck = Deck(
            collection_id=UUID(account["collection"]["id"]),
            kind="filtered",
            name="Temporary",
        )
        db.add(deck)
        db.flush()
        filtered_id = str(deck.id)
        card = db.get(Card, UUID(card_id))
        card.original_deck_id, card.deck_id, card.deck_kind = (
            card.deck_id,
            deck.id,
            "filtered",
        )
        original_position = card.new_position
    assert (
        client.put(
            f"/api/v1/cards/{card_id}/deck", json={"deck_id": account["deck_id"]}
        ).status_code
        == 422
    )
    if delete_original:
        deleted = delete(client, "decks", account["deck_id"])
        assert deleted["impact"]["cards_deleted"] == 1
        assert client.get(f"/api/v1/cards/{card_id}").status_code == 404
        assert client.get(f"/api/v1/decks/{filtered_id}").status_code == 200
    else:
        deleted = delete(client, "decks", filtered_id)
        assert (
            deleted["impact"]["cards_deleted"] == 0
            and deleted["impact"]["cards_returned"] == 1
        )
        current = client.get(f"/api/v1/cards/{card_id}").json()
        assert (
            current["deck_id"] == account["deck_id"]
            and current["new_position"] == original_position
        )
    assert client.get(f"/api/v1/notes/{item['id']}").status_code == 200


def test_removed_media_stays_live_while_other_note_references_it(
    client, account, engine
):
    audio = asset(engine, account["collection"]["id"])
    first = note(client, account, {"english": "Hello.", "reference_audio": audio})
    second = note(client, account, {"english": "Again.", "reference_audio": audio})
    delete(client, "notes", first["id"])
    with Session(engine) as db:
        assert db.get(MediaAsset, UUID(audio)).lifecycle == "ready"
    assert (
        client.put(
            f"/api/v1/notes/{second['id']}",
            json={"revision": 1, "fields": {"english": "Again."}},
        ).status_code
        == 200
    )
    with Session(engine) as db:
        assert db.get(MediaAsset, UUID(audio)).lifecycle == "pending_delete"


def test_same_source_field_can_map_twice_without_copying_unmapped_fields(
    client, account
):
    item = note(
        client,
        account,
        {"word": "Hello", "meaning": "你好", "phonetic": "unused"},
        kind="vocabulary",
    )
    preview = client.post(
        f"/api/v1/notes/{item['id']}/change-type/preview",
        json={"target_note_type_key": "sentence"},
    ).json()
    response = client.post(
        f"/api/v1/notes/{item['id']}/change-type",
        json={
            "revision": 1,
            "target_note_type_key": "sentence",
            "confirmation_token": preview["confirmation_token"],
            "field_mapping": {
                "english": "word",
                "chinese": "word",
                "note": None,
                "reference_audio": None,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["fields"] == {"english": "Hello", "chinese": "Hello"}


def test_media_picker_lists_only_ready_owned_and_library_assets(
    client, account, engine
):
    own = asset(engine, account["collection"]["id"])
    with Session(engine) as db, db.begin():
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        shared = MediaAsset(
            collection_id=library.id,
            collection_kind="library",
            kind="audio",
            scope="library_shared",
            object_key="library/shared.wav",
        )
        temporary = MediaAsset(
            collection_id=UUID(account["collection"]["id"]),
            kind="audio",
            lifecycle="temporary",
            object_key="private/temp.wav",
        )
        db.add_all([shared, temporary])
        db.flush()
        shared_id = str(shared.id)
    listed = client.get("/api/v1/media-assets").json()["media_assets"]
    assert {row["id"] for row in listed} == {own, shared_id}
    assert all(set(row) == {"id", "kind", "name"} for row in listed)
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "picker@example.com", "password": "a strong test password"},
    ).json()
    client.headers["X-CSRF-Token"] = other["csrf_token"]
    listed = client.get("/api/v1/media-assets").json()["media_assets"]
    assert [row["id"] for row in listed] == [shared_id]
