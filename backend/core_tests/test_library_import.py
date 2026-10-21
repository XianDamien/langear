"""Shared Library import: subtree copying, idempotency, conflicts and deletion."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import (
    Card,
    CardTemplate,
    Collection,
    Deck,
    MediaAsset,
    MediaReference,
    Note,
    NoteType,
)
from core_tests.test_review import flip, make_note, next_card, queue, rate


def library(db):
    return db.scalar(select(Collection).where(Collection.kind == "library"))


def add_deck(db, shared, name, parent=None, guid=None):
    deck = Deck(
        collection_id=shared.id,
        name=name,
        parent_id=parent.id if parent is not None else None,
        deck_guid=guid or str(uuid4()),
    )
    db.add(deck)
    db.flush()
    return deck


def add_note(db, shared, fields, note_type_key="sentence", guid=None):
    note_type_id = db.scalar(select(NoteType.id).where(NoteType.key == note_type_key))
    note = Note(
        collection_id=shared.id,
        note_type_id=note_type_id,
        fields=fields,
        guid=guid or str(uuid4()),
        source_metadata={"kind": "card", "source": "fixture", "legacy_id": "shared"},
    )
    db.add(note)
    db.flush()
    return note


def add_card(db, shared, note, deck, template_key, position=1):
    template = db.scalar(
        select(CardTemplate).where(
            CardTemplate.note_type_id == note.note_type_id,
            CardTemplate.key == template_key,
        )
    )
    card = Card(
        collection_id=shared.id,
        note_id=note.id,
        note_type_id=note.note_type_id,
        card_template_id=template.id,
        template_ord=template.ord,
        deck_id=deck.id,
        new_position=position,
    )
    db.add(card)
    db.flush()
    return card


def imported_tree(client):
    return client.get("/api/v1/decks/tree").json()["tree"]


def find_node(nodes, name):
    for node in nodes:
        if node["name"] == name:
            return node
        found = find_node(node["children"], name)
        if found:
            return found
    return None


def test_import_copies_every_card_even_when_fields_do_not_satisfy_a_template(
    client, account, engine
):
    """A shared card is copied verbatim; generation rules never drop it."""
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:root")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:lesson")
        note = add_note(db, shared, {"english": "Hello."}, guid="lib:note")
        add_card(db, shared, note, child, "sentence_translation", 1)
        add_card(db, shared, note, root, "sentence_retelling", 2)
        root_id = root.id

    response = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"]["notes"] == 1
    assert body["created"]["cards"] == 2

    tree = imported_tree(client)
    imported_root = find_node(tree, "Shared course")
    imported_child = find_node(imported_root["children"], "Lesson")
    assert imported_child["stats"]["total_cards"] == 1
    assert imported_root["stats"]["total_cards"] == 2

    root_cards = client.get(
        "/api/v1/cards", params={"deck_id": imported_root["id"]}
    ).json()["cards"]
    child_cards = client.get(
        "/api/v1/cards", params={"deck_id": imported_child["id"]}
    ).json()["cards"]
    assert [card["card_template_key"] for card in root_cards] == ["sentence_retelling"]
    assert [card["card_template_key"] for card in child_cards] == ["sentence_translation"]
    # The translation template needs `chinese`, which the shared note lacks;
    # the card is still copied but reported as not renderable.
    translation = child_cards[0]
    assert translation["renderable"] is False
    assert translation["missing_fields"] == ["chinese"]


def test_import_links_shared_media_and_keeps_it_after_copy_deletion(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Audio course", guid="lib:audio")
        audio = MediaAsset(
            collection_id=shared.id,
            collection_kind="library",
            scope="library_shared",
            object_key="library/" + str(uuid4()),
            kind="audio",
        )
        db.add(audio)
        db.flush()
        note = add_note(
            db,
            shared,
            {"english": "Listen.", "reference_audio": str(audio.id)},
            guid="lib:audio-note",
        )
        add_card(db, shared, note, deck, "sentence_retelling")
        deck_id, audio_id, note_guid = deck.id, audio.id, note.guid

    preview = client.get(f"/api/v1/library/decks/{deck_id}/cards")
    assert preview.status_code == 200, preview.text
    assert preview.json()["total"] == 1

    imported = client.post(f"/api/v1/library/decks/{deck_id}/import")
    assert imported.status_code == 200, imported.text
    copied_deck = imported.json()["deck_id"]
    notes = client.get("/api/v1/notes").json()["notes"]
    copied_note = next(note for note in notes if note["guid"] == note_guid)
    assert copied_note["fields"]["reference_audio"] == str(audio_id)
    with Session(engine) as db:
        reference = db.scalar(
            select(MediaReference).where(MediaReference.note_id == copied_note["id"])
        )
        assert reference is not None
        assert reference.media_collection_id == library(db).id
        assert reference.media_scope == "library_shared"

    deletion = client.post(f"/api/v1/decks/{copied_deck}/delete/preview").json()
    assert deletion["impact"]["media_references_deleted"] == 1
    client.post(
        f"/api/v1/decks/{copied_deck}/delete",
        json={"confirmation_token": deletion["confirmation_token"]},
    )
    with Session(engine) as db:
        # Shared media is never owned by the learner Collection.
        assert db.get(MediaAsset, audio_id).lifecycle == "ready"


def test_import_child_then_parent_converges_on_one_tree(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:parent")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:child")
        note = add_note(db, shared, {"english": "One."}, guid="lib:one")
        add_card(db, shared, note, child, "sentence_translation")
        root_guid, child_guid = root.deck_guid, child.deck_guid
        root_id, child_id = root.id, child.id

    first = client.post(f"/api/v1/library/decks/{child_id}/import")
    assert first.status_code == 200, first.text
    standalone = first.json()["deck_id"]
    tree = imported_tree(client)
    assert find_node(tree, "Lesson")["id"] == standalone
    assert find_node(tree, "Shared course") is None

    second = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert second.status_code == 200, second.text
    assert second.json()["created"]["decks"] == 1
    tree = imported_tree(client)
    parents = [node for node in tree if node["id"] == second.json()["deck_id"]]
    assert parents and parents[0]["name"] == "Shared course"
    assert [child["name"] for child in parents[0]["children"]] == ["Lesson"]
    moved = parents[0]["children"][0]
    assert moved["id"] == standalone
    assert moved["deck_guid"] == child_guid
    assert moved["stats"]["total_cards"] == 1

    third = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert third.status_code == 200, third.text
    assert third.json()["created"] == {"decks": 0, "notes": 0, "cards": 0}
    assert third.json()["existing"] == {"decks": 2, "notes": 1, "cards": 1}
    user_decks = client.get("/api/v1/decks").json()["decks"]
    matching = [row for row in user_decks if row["deck_guid"] in {root_guid, child_guid}]
    assert len(matching) == 2


def test_reimport_keeps_learner_moved_decks_without_creating_a_cycle(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:moved-root")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:moved-child")
        source_root_id = root.id

    imported = client.post(f"/api/v1/library/decks/{source_root_id}/import").json()
    root_id, child_id = imported["deck_ids"]
    assert client.put(f"/api/v1/decks/{child_id}", json={"name": "Lesson"}).status_code == 200
    assert client.put(
        f"/api/v1/decks/{root_id}", json={"name": "Shared course", "parent_id": child_id}
    ).status_code == 200

    response = client.post(f"/api/v1/library/decks/{source_root_id}/import")
    assert response.status_code == 200, response.text
    tree = imported_tree(client)
    assert find_node(tree, "Lesson")["id"] == child_id
    assert find_node(tree, "Lesson")["children"][0]["id"] == root_id
    assert client.get(f"/api/v1/decks/{child_id}").json()["parent_id"] is None


def test_reimport_after_note_type_change_reports_skip(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:type-deck")
        note = add_note(db, shared, {"english": "Hello.", "chinese": "你好。"}, guid="lib:type-note")
        add_card(db, shared, note, deck, "sentence_translation")
        source_deck_id = deck.id

    assert client.post(f"/api/v1/library/decks/{source_deck_id}/import").status_code == 200
    copied_note = next(row for row in client.get("/api/v1/notes").json()["notes"] if row["guid"] == "lib:type-note")
    preview = client.post(
        f"/api/v1/notes/{copied_note['id']}/change-type/preview",
        json={"target_note_type_key": "vocabulary"},
    ).json()
    changed = client.post(
        f"/api/v1/notes/{copied_note['id']}/change-type",
        json={
            "revision": copied_note["revision"],
            "target_note_type_key": "vocabulary",
            "confirmation_token": preview["confirmation_token"],
            "field_mapping": preview["suggested_field_mapping"],
            "field_values": {"word": "Hello", "meaning": "你好"},
        },
    )
    assert changed.status_code == 200, changed.text

    response = client.post(f"/api/v1/library/decks/{source_deck_id}/import")
    assert response.status_code == 200, response.text
    assert response.json()["created"]["cards"] == 0
    assert response.json()["skipped_cards"][0]["reason"] == "NOTE_TYPE_CHANGED"


def test_deletion_preview_expires_when_library_note_text_changes(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:preview-note-deck")
        note = add_note(db, shared, {"english": "Before."}, guid="lib:preview-note")
        add_card(db, shared, note, deck, "sentence_translation")
        source_deck_id = deck.id

    copied_deck_id = client.post(f"/api/v1/library/decks/{source_deck_id}/import").json()["deck_id"]
    copied_note = next(row for row in client.get("/api/v1/notes").json()["notes"] if row["guid"] == "lib:preview-note")
    preview = client.post(f"/api/v1/decks/{copied_deck_id}/delete/preview").json()
    edited = client.put(
        f"/api/v1/notes/{copied_note['id']}",
        json={"revision": copied_note["revision"], "fields": {"english": "After."}},
    )
    assert edited.status_code == 200, edited.text
    response = client.post(
        f"/api/v1/decks/{copied_deck_id}/delete",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "DELETION_IMPACT_CHANGED"
    assert client.get(f"/api/v1/notes/{copied_note['id']}").status_code == 200


def test_reimport_preserves_learner_edits_and_only_appends_missing_content(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:edit-root")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:edit-child")
        note = add_note(
            db,
            shared,
            {"english": "Original.", "chinese": "原始。"},
            guid="lib:edit-note",
        )
        add_card(db, shared, note, child, "sentence_translation")
        root_id, child_id = root.id, child.id

    imported = client.post(f"/api/v1/library/decks/{root_id}/import").json()
    imported_root = imported["deck_id"]
    imported_child = imported["deck_ids"][1]
    renamed = client.put(
        f"/api/v1/decks/{imported_root}", json={"name": "My shared course"}
    )
    assert renamed.status_code == 200, renamed.text
    copied_notes = client.get("/api/v1/notes").json()["notes"]
    copied_note = next(
        note for note in copied_notes if note["guid"] == "lib:edit-note"
    )
    edited = client.put(
        f"/api/v1/notes/{copied_note['id']}",
        json={
            "revision": copied_note["revision"],
            "fields": {"english": "My wording.", "chinese": "我的措辞。"},
        },
    )
    assert edited.status_code == 200, edited.text
    q = queue(client, account, imported_child)
    flipped = flip(
        client, q, next_card(client, q), {"type": "text", "text": "My wording."}
    ).json()
    assert rate(client, q, flipped, "good").status_code == 200
    cards = client.get(
        "/api/v1/cards", params={"deck_id": imported_child}
    ).json()["cards"]
    rated = cards[0]
    assert rated["reps"] == 1

    with Session(engine) as db, db.begin():
        shared = library(db)
        child = db.get(Deck, child_id)
        note = add_note(db, shared, {"english": "New."}, guid="lib:new-note")
        add_card(db, shared, note, child, "sentence_translation")

    again = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert again.status_code == 200, again.text
    assert again.json()["created"]["cards"] == 1
    assert again.json()["created"]["notes"] == 1
    tree = imported_tree(client)
    assert find_node(tree, "My shared course")["id"] == imported_root
    assert find_node(tree, "Shared course") is None
    notes = client.get("/api/v1/notes").json()["notes"]
    kept = next(note for note in notes if note["guid"] == "lib:edit-note")
    assert kept["fields"]["english"] == "My wording."
    cards = client.get(
        "/api/v1/cards", params={"deck_id": imported_child}
    ).json()["cards"]
    assert len(cards) == 2
    assert next(card for card in cards if card["id"] == rated["id"])["reps"] == 1


def test_reimport_does_not_move_a_card_the_learner_relocated(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:move-root")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:move-child")
        note = add_note(db, shared, {"english": "Move me."}, guid="lib:move-note")
        add_card(db, shared, note, child, "sentence_translation")
        root_id = root.id

    imported = client.post(f"/api/v1/library/decks/{root_id}/import").json()
    imported_child = imported["deck_ids"][1]
    card = client.get(
        "/api/v1/cards", params={"deck_id": imported_child}
    ).json()["cards"][0]
    destination = client.post("/api/v1/decks", json={"name": "Personal"}).json()["id"]
    moved = client.put(f"/api/v1/cards/{card['id']}/deck", json={"deck_id": destination})
    assert moved.status_code == 200, moved.text

    again = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert again.status_code == 200, again.text
    assert again.json()["created"]["cards"] == 0
    skipped = again.json()["skipped_cards"]
    assert len(skipped) == 1
    assert skipped[0]["card_template_key"] == "sentence_translation"
    assert skipped[0]["reason"] == "CARD_ALREADY_IN_ANOTHER_DECK"
    assert skipped[0]["deck_id"] == destination
    assert client.get(f"/api/v1/cards/{card['id']}").json()["deck_id"] == destination


def test_import_rejects_rows_with_matching_guid_from_another_source(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:collision-deck")
        root_id = deck.id
    with Session(engine) as db, db.begin():
        user_deck = Deck(
            collection_id=UUID(account["collection"]["id"]),
            name="Personal",
            deck_guid="lib:collision-deck",
        )
        db.add(user_deck)
    response = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "LIBRARY_IMPORT_CONFLICT"


def test_import_rejects_note_guid_collision_with_user_content(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:note-collision")
        note = add_note(db, shared, {"english": "Shared."}, guid="lib:same-note")
        add_card(db, shared, note, deck, "sentence_translation")
        root_id = deck.id
    created = client.post(
        "/api/v1/notes",
        json={
            "deck_id": account["deck_id"],
            "note_type_key": "sentence",
            "guid": "lib:same-note",
            "fields": {"english": "Mine."},
        },
    )
    assert created.status_code == 201, created.text
    response = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "LIBRARY_IMPORT_CONFLICT"


def test_import_reports_a_name_conflict_instead_of_overwriting(
    client, account, engine
):
    existing = client.post("/api/v1/decks", json={"name": "Shared course"})
    assert existing.status_code == 201, existing.text
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:name-conflict")
        root_id = deck.id
    response = client.post(f"/api/v1/library/decks/{root_id}/import")
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "LIBRARY_IMPORT_CONFLICT"
    assert error["details"]["deck_name"] == "Shared course"


def test_delete_scope_only_removes_unreferenced_library_notes(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:scope-root")
        first = add_deck(db, shared, "Lesson A", parent=root, guid="lib:scope-a")
        second = add_deck(db, shared, "Lesson B", parent=root, guid="lib:scope-b")
        note = add_note(
            db,
            shared,
            {"word": "apple", "meaning": "苹果"},
            note_type_key="vocabulary",
            guid="lib:scope-note",
        )
        add_card(db, shared, note, first, "vocabulary_english_to_chinese")
        add_card(db, shared, note, second, "vocabulary_chinese_to_english")
        root_id = root.id

    imported = client.post(f"/api/v1/library/decks/{root_id}/import").json()
    imported_root, lesson_a, lesson_b = imported["deck_ids"]
    user_note = make_note(client, account, {"word": "mine", "meaning": "我的"}, deck_id=lesson_a)

    one_side = client.post(f"/api/v1/decks/{lesson_a}/delete/preview").json()
    assert one_side["impact"]["notes_deleted"] == 0
    deleted = client.post(
        f"/api/v1/decks/{lesson_a}/delete",
        json={"confirmation_token": one_side["confirmation_token"]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["impact"]["cards_deleted"] == 2
    assert client.get(f"/api/v1/notes/{user_note['id']}").status_code == 200
    remaining = client.get(
        "/api/v1/cards", params={"deck_id": lesson_b}
    ).json()["cards"]
    assert len(remaining) == 1

    whole = client.post(f"/api/v1/decks/{imported_root}/delete/preview").json()
    assert whole["impact"]["notes_deleted"] == 1
    result = client.post(
        f"/api/v1/decks/{imported_root}/delete",
        json={"confirmation_token": whole["confirmation_token"]},
    )
    assert result.status_code == 200, result.text
    with Session(engine) as db:
        shared_id = library(db).id
        copied = db.scalar(
            select(Note).where(
                Note.guid == "lib:scope-note", Note.collection_id != shared_id
            )
        )
        assert copied is None
        # The Library original is untouched by a learner copy deletion.
        original = db.scalar(
            select(Note).where(
                Note.guid == "lib:scope-note", Note.collection_id == shared_id
            )
        )
        assert original is not None
        assert db.get(Note, UUID(user_note["id"])) is not None


def test_deletion_preview_token_invalidates_when_import_adds_a_card(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Shared course", guid="lib:stale")
        note = add_note(db, shared, {"english": "First."}, guid="lib:stale-one")
        add_card(db, shared, note, deck, "sentence_translation")
        deck_id = deck.id

    imported = client.post(f"/api/v1/library/decks/{deck_id}/import").json()["deck_id"]
    preview = client.post(f"/api/v1/decks/{imported}/delete/preview").json()
    with Session(engine) as db, db.begin():
        shared = library(db)
        source_deck = db.scalar(select(Deck).where(Deck.deck_guid == "lib:stale"))
        note = add_note(db, shared, {"english": "Second."}, guid="lib:stale-two")
        add_card(db, shared, note, source_deck, "sentence_translation")
    assert client.post(f"/api/v1/library/decks/{deck_id}/import").status_code == 200
    stale = client.post(
        f"/api/v1/decks/{imported}/delete",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "DELETION_IMPACT_CHANGED"
    refreshed = client.post(f"/api/v1/decks/{imported}/delete/preview").json()
    assert refreshed["impact"]["cards_deleted"] == 2
    assert client.post(
        f"/api/v1/decks/{imported}/delete",
        json={"confirmation_token": refreshed["confirmation_token"]},
    ).status_code == 200


def test_library_cards_api_pages_and_can_include_the_subtree(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course", guid="lib:page-root")
        child = add_deck(db, shared, "Lesson", parent=root, guid="lib:page-child")
        for index in range(3):
            note = add_note(
                db, shared, {"english": f"Sentence {index}."}, guid=f"lib:page-{index}"
            )
            add_card(db, shared, note, child, "sentence_translation", index + 1)
        root_id, child_id = root.id, child.id

    page = client.get(
        f"/api/v1/library/decks/{child_id}/cards", params={"limit": 2, "offset": 0}
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3
    assert len(body["cards"]) == 2
    assert body["scope"] == "deck"
    second = client.get(
        f"/api/v1/library/decks/{child_id}/cards", params={"limit": 2, "offset": 2}
    ).json()
    assert len(second["cards"]) == 1
    assert {card["id"] for card in body["cards"]}.isdisjoint(
        {card["id"] for card in second["cards"]}
    )
    subtree = client.get(
        f"/api/v1/library/decks/{root_id}/cards",
        params={"include_descendants": True},
    ).json()
    assert subtree["total"] == 3
    assert subtree["scope"] == "subtree"
    assert client.get(
        f"/api/v1/library/decks/{root_id}/cards"
    ).json()["total"] == 0


def test_library_tree_reports_content_counts_without_schedule_stats(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Shared course")
        first = add_deck(db, shared, "Lesson A", parent=root)
        second = add_deck(db, shared, "Lesson B", parent=root)
        note = add_note(
            db, shared, {"word": "apple", "meaning": "苹果"}, note_type_key="vocabulary"
        )
        add_card(db, shared, note, first, "vocabulary_english_to_chinese")
        add_card(db, shared, note, second, "vocabulary_chinese_to_english")

    response = client.get("/api/v1/library/decks/tree")
    assert response.status_code == 200, response.text
    parent = find_node(response.json()["tree"], "Shared course")
    assert parent["stats"] == {"total_cards": 2, "note_count": 1}
    assert [child["stats"] for child in parent["children"]] == [
        {"total_cards": 1, "note_count": 1},
        {"total_cards": 1, "note_count": 1},
    ]


def test_library_import_rejects_a_filtered_deck_source(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        filtered = Deck(
            collection_id=shared.id, name="Temporary", kind="filtered", scheduling_config={}
        )
        db.add(filtered)
        db.flush()
        filtered_id = filtered.id
    response = client.post(f"/api/v1/library/decks/{filtered_id}/import")
    assert response.status_code == 404, response.text


def test_import_selection_copies_all_cards_but_limits_study_scope(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Selectable course", guid="lib:selectable")
        first = add_note(db, shared, {"english": "First."}, guid="lib:first")
        second = add_note(db, shared, {"english": "Second."}, guid="lib:second")
        add_card(db, shared, first, deck, "sentence_translation", 1)
        add_card(db, shared, second, deck, "sentence_translation", 2)
        deck_id = deck.id

    response = client.post(
        f"/api/v1/library/decks/{deck_id}/import",
        json={"note_guids": ["lib:first"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    copied = body["deck_id"]
    assert body["selection"] == {"note_guids": ["lib:first"], "cards": 1}

    # The whole lesson is copied so the learner keeps the course structure...
    all_cards = client.get("/api/v1/cards", params={"deck_id": copied}).json()["cards"]
    assert len(all_cards) == 2
    # ...while only the selected sentence enters the study queue.
    study = client.get(
        "/api/v1/cards", params={"deck_id": copied, "study_only": True}
    ).json()["cards"]
    assert [card["note_guid"] for card in study] == ["lib:first"]
    selection = client.get(
        f"/api/v1/library/decks/{deck_id}/selection"
    ).json()
    assert selection == {"note_guids": ["lib:first"], "joined": True}

    # Re-importing without a selection body keeps the learner's scope.
    kept = client.post(f"/api/v1/library/decks/{deck_id}/import")
    assert kept.status_code == 200, kept.text
    assert client.get(f"/api/v1/library/decks/{deck_id}/selection").json()[
        "note_guids"
    ] == ["lib:first"]

    # A different subset replaces the previous scope without duplicating cards.
    updated = client.post(
        f"/api/v1/library/decks/{deck_id}/import",
        json={"note_guids": ["lib:second"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["created"]["cards"] == 0
    assert client.get(f"/api/v1/library/decks/{deck_id}/selection").json()[
        "note_guids"
    ] == ["lib:second"]

    # Explicitly importing the whole course clears the subset and restores all cards.
    whole = client.post(
        f"/api/v1/library/decks/{deck_id}/import",
        json={"note_guids": None},
    )
    assert whole.status_code == 200, whole.text
    assert whole.json()["selection"]["note_guids"] is None
    assert client.get(f"/api/v1/library/decks/{deck_id}/selection").json()[
        "note_guids"
    ] is None
    study = client.get(
        "/api/v1/cards", params={"deck_id": copied, "study_only": True}
    ).json()["cards"]
    assert len(study) == 2


def test_import_selection_rejects_notes_outside_the_deck(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        deck = add_deck(db, shared, "Selectable course", guid="lib:selectable")
        other = add_deck(db, shared, "Other course", guid="lib:other")
        note = add_note(db, shared, {"english": "Outside."}, guid="lib:outside")
        add_card(db, shared, note, other, "sentence_translation", 1)
        deck_id = deck.id

    response = client.post(
        f"/api/v1/library/decks/{deck_id}/import",
        json={"note_guids": ["lib:outside"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "STUDY_SELECTION_INVALID"


def test_import_adopts_legacy_deck_and_note_identity(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        source = add_deck(db, shared, "Legacy course", guid="lib:legacy")
        source_note = add_note(
            db, shared, {"english": "Legacy.", "chinese": "旧。"}, guid="lib:legacy-note"
        )
        add_card(db, shared, source_note, source, "sentence_translation")

        user = db.get(Collection, UUID(account["collection"]["id"]))
        note_type_id = source_note.note_type_id
        template = db.scalar(
            select(CardTemplate).where(CardTemplate.key == "sentence_translation")
        )
        legacy_deck = Deck(
            collection_id=user.id,
            name="Legacy course",
            deck_guid="lib:legacy",
            imported=True,
            in_my_courses=False,
            source_metadata={"kind": "deck", "source": "legacy-fixture"},
        )
        db.add(legacy_deck)
        db.flush()
        legacy_note = Note(
            collection_id=user.id,
            note_type_id=note_type_id,
            fields={"english": "Legacy.", "chinese": "旧。"},
            guid="lib:legacy-note",
            imported=True,
            source_metadata={"kind": "card", "source": "legacy-fixture"},
        )
        db.add(legacy_note)
        db.flush()
        db.add(
            Card(
                collection_id=user.id,
                note_id=legacy_note.id,
                note_type_id=note_type_id,
                card_template_id=template.id,
                template_ord=template.ord,
                deck_id=legacy_deck.id,
                new_position=1,
            )
        )
        source_id, legacy_deck_id = source.id, legacy_deck.id

    response = client.post(f"/api/v1/library/decks/{source_id}/import")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == {"decks": 0, "notes": 0, "cards": 0}
    assert body["existing"] == {"decks": 1, "notes": 1, "cards": 1}

    with Session(engine) as db:
        deck = db.get(Deck, legacy_deck_id)
        note = db.scalar(
            select(Note).where(
                Note.guid == "lib:legacy-note",
                Note.collection_id == UUID(account["collection"]["id"]),
            )
        )
        assert deck.in_my_courses is True
        assert deck.source_metadata["source"] == "library"
        assert deck.source_metadata["legacy_source"] == "legacy-fixture"
        assert note.source_metadata["source"] == "library"
        assert note.source_metadata["legacy_source"] == "legacy-fixture"

    # The Library now shows the adopted copy as joined instead of "加入".
    node = find_node(
        client.get("/api/v1/library/decks/tree").json()["tree"], "Legacy course"
    )
    assert node["in_my_courses"] is True


def test_import_still_rejects_an_user_authored_identity(client, account, engine):
    with Session(engine) as db, db.begin():
        shared = library(db)
        source = add_deck(db, shared, "User course", guid="lib:user-owned")
        user = db.get(Collection, UUID(account["collection"]["id"]))
        db.add(
            Deck(
                collection_id=user.id,
                name="My own course",
                deck_guid="lib:user-owned",
                imported=False,
                source_metadata={"kind": "deck"},
            )
        )
        source_id = source.id

    response = client.post(f"/api/v1/library/decks/{source_id}/import")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "LIBRARY_IMPORT_CONFLICT"


def test_parent_selection_is_distributed_across_child_decks(
    client, account, engine
):
    with Session(engine) as db, db.begin():
        shared = library(db)
        root = add_deck(db, shared, "Book", guid="lib:book")
        first = add_deck(db, shared, "Lesson A", parent=root, guid="lib:a")
        second = add_deck(db, shared, "Lesson B", parent=root, guid="lib:b")
        first_note = add_note(db, shared, {"english": "A."}, guid="lib:a-note")
        second_note = add_note(db, shared, {"english": "B."}, guid="lib:b-note")
        add_card(db, shared, first_note, first, "sentence_translation", 1)
        add_card(db, shared, second_note, second, "sentence_translation", 2)
        root_id = root.id

    imported = client.post(
        f"/api/v1/library/decks/{root_id}/import",
        json={"note_guids": ["lib:a-note"]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["selection"] == {
        "note_guids": ["lib:a-note"],
        "cards": 1,
    }
    tree = imported_tree(client)
    imported_root = find_node(tree, "Book")
    imported_a = find_node(imported_root["children"], "Lesson A")
    imported_b = find_node(imported_root["children"], "Lesson B")
    assert imported_root["in_my_courses"] is True
    assert imported_a["in_my_courses"] is True
    assert imported_b["in_my_courses"] is False
    assert [
        card["note_guid"]
        for card in client.get(
            "/api/v1/cards", params={"deck_id": imported_a["id"], "study_only": True}
        ).json()["cards"]
    ] == ["lib:a-note"]
    assert client.get(
        "/api/v1/cards", params={"deck_id": imported_b["id"], "study_only": True}
    ).json()["cards"] == []
    assert client.get(
        f"/api/v1/library/decks/{root_id}/selection"
    ).json()["note_guids"] == ["lib:a-note"]

    switched = client.post(
        f"/api/v1/library/decks/{root_id}/import",
        json={"note_guids": ["lib:b-note"]},
    )
    assert switched.status_code == 200, switched.text
    assert client.get(
        f"/api/v1/library/decks/{root_id}/selection"
    ).json()["note_guids"] == ["lib:b-note"]
    assert client.get(
        "/api/v1/cards", params={"deck_id": imported_a["id"], "study_only": True}
    ).json()["cards"] == []
    assert [
        card["note_guid"]
        for card in client.get(
            "/api/v1/cards", params={"deck_id": imported_b["id"], "study_only": True}
        ).json()["cards"]
    ] == ["lib:b-note"]
