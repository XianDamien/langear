"""Deck hierarchy, statistics and My Courses membership."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Collection, Deck, Note
from core_tests.test_review import flip, make_note, next_card, queue, rate


def test_deck_list_includes_hierarchy_membership_and_statistics(client, account):
    root = account["deck_id"]
    child = client.post("/api/v1/decks", json={"name": "Lesson", "parent_id": root}).json()["id"]
    make_note(client, account)
    make_note(client, account, {"word": "pear", "meaning": "梨"}, deck_id=child)
    client.put(f"/api/v1/decks/{child}/membership", json={"joined": True})
    rows = client.get("/api/v1/decks").json()["decks"]
    by_id = {row["id"]: row for row in rows}
    assert by_id[child]["parent_id"] == root
    assert by_id[child]["depth"] == 1
    assert by_id[root]["depth"] == 0
    assert by_id[root]["stats"]["total_cards"] == 2
    assert by_id[child]["stats"]["total_cards"] == 1
    assert by_id[child]["in_my_courses"] is True
    assert by_id[root]["in_my_courses"] is False
    assert by_id[root]["path"] == [root]
    assert by_id[child]["path"] == [root, child]


def test_deck_tree_reports_subtree_statistics_and_membership(client, account):
    root = account["deck_id"]
    child = client.post("/api/v1/decks", json={"name": "Lesson", "parent_id": root}).json()["id"]
    root_card = make_note(client, account)["cards"][0]["id"]
    child_card = make_note(client, account, deck_id=child)["cards"][0]["id"]
    tree = client.get("/api/v1/decks/tree")
    assert tree.status_code == 200, tree.text
    nodes = tree.json()["tree"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["id"] == root
    assert node["stats"]["total_cards"] == 2
    assert node["stats"]["new_cards"] == 2
    assert node["stats"]["completed_cards"] == 0
    assert [item["id"] for item in node["children"]] == [child]
    assert node["children"][0]["stats"]["total_cards"] == 1
    assert node["children"][0]["parent_id"] == root
    flat = {row["id"]: row for row in tree.json()["decks"]}
    assert flat[root]["stats"]["total_cards"] == 2
    assert flat[child]["stats"]["total_cards"] == 1
    assert all(row["in_my_courses"] is False for row in flat.values())
    _ = (root_card, child_card)


def test_deck_statistics_count_due_and_completed_cards(client, account):
    make_note(client, account)
    make_note(client, account, {"word": "pear", "meaning": "梨"})
    q = queue(client, account)
    flipped = flip(client, q, next_card(client, q)).json()
    assert rate(client, q, flipped, "good").status_code == 200
    stats = client.get("/api/v1/decks/" + account["deck_id"]).json()
    _ = stats
    tree = client.get("/api/v1/decks/tree").json()["tree"][0]["stats"]
    assert tree["total_cards"] == 2
    assert tree["completed_cards"] == 1
    assert tree["due_cards"] == tree["new_cards"] + tree["learning_cards"] + tree["review_cards"]


def test_my_courses_lists_only_joined_decks_with_statistics(client, account):
    joined = account["deck_id"]
    other = client.post("/api/v1/decks", json={"name": "NotJoined"}).json()["id"]
    make_note(client, account)
    make_note(client, account, deck_id=other)
    assert client.get("/api/v1/my-courses").json()["decks"] == []
    assert client.put(f"/api/v1/decks/{joined}/membership", json={"joined": True}).status_code == 200
    rows = client.get("/api/v1/my-courses").json()["decks"]
    assert [row["id"] for row in rows] == [joined]
    assert rows[0]["stats"]["total_cards"] == 1
    assert client.put(f"/api/v1/decks/{joined}/membership", json={"joined": False}).status_code == 200
    assert client.get("/api/v1/my-courses").json()["decks"] == []


def test_deck_tree_and_my_courses_are_collection_isolated(client, account):
    from fastapi.testclient import TestClient
    from core.main import app

    make_note(client, account)
    client.put(f"/api/v1/decks/{account['deck_id']}/membership", json={"joined": True})
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "http://localhost:3002"}
    ) as other:
        identity = other.post(
            "/api/v1/auth/register",
            json={"email": "courses@example.com", "password": "another strong password"},
        ).json()
        other.headers["X-CSRF-Token"] = identity["csrf_token"]
        assert other.get("/api/v1/my-courses").json()["decks"] == []
        theirs = other.get("/api/v1/decks/tree").json()["tree"]
        assert len(theirs) == 1
        assert theirs[0]["stats"]["total_cards"] == 0
        assert other.put(
            f"/api/v1/decks/{account['deck_id']}/membership", json={"joined": True}
        ).status_code == 404


def test_imported_flag_is_not_set_by_client_supplied_guids(client, account, engine):
    note = make_note(client, account)
    asset = note["id"]
    with Session(engine) as db, db.begin():
        stored = db.get(Note, UUID(asset))
        assert stored.imported is False
        stored.imported = True
    cards = client.get(
        "/api/v1/cards", params={"exclude_imported": True}
    ).json()["cards"]
    assert cards == []
    with Session(engine) as db:
        assert db.get(Note, UUID(asset)).imported is True
        deck = db.scalar(
            Deck.__table__.select().where(Deck.collection_id == UUID(account["collection"]["id"]))
        )
        assert deck is not None


def test_migration_backfills_source_metadata_for_pre_existing_legacy_rows(engine):
    """Rows imported before lan33_0011 must stay findable through provenance."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from core.content import ContentService
    from core.legacy_selection import lesson

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic-core.ini"))
    command.downgrade(config, "lan21_0010")
    with engine.begin() as connection:
        collection_id = connection.scalar(
            text("SELECT id FROM collections WHERE kind = 'library'")
        )
        note_type_id = connection.scalar(
            text("SELECT id FROM note_types WHERE key = 'sentence'")
        )
        connection.execute(
            text(
                "INSERT INTO decks (id, collection_id, name, deck_guid, kind, parent_kind,"
                " in_my_courses, scheduling_config, created_at, updated_at)"
                " VALUES (gen_random_uuid(), :c, 'Old lesson', 'legacy:fixture:deck:7',"
                " 'standard', 'standard', false, '{}', now(), now())"
            ),
            {"c": collection_id},
        )
        connection.execute(
            text(
                "INSERT INTO notes (id, collection_id, guid, note_type_id, fields, tags,"
                " revision, created_at, updated_at)"
                " VALUES (gen_random_uuid(), :c, 'legacy:fixture:card:9', :nt,"
                " '{\"english\": \"Old sentence.\"}', '[]', 1, now(), now())"
            ),
            {"c": collection_id, "nt": note_type_id},
        )
    command.upgrade(config, "head")
    with Session(engine) as db:
        collection = db.get(Collection, collection_id)
        deck = db.scalar(select(Deck).where(Deck.deck_guid == "legacy:fixture:deck:7"))
        note = db.scalar(select(Note).where(Note.guid == "legacy:fixture:card:9"))
        assert deck.imported is True
        assert note.imported is True
        assert deck.source_metadata == {
            "kind": "deck",
            "source": "fixture",
            "legacy_id": "7",
        }
        assert note.source_metadata == {
            "kind": "card",
            "source": "fixture",
            "legacy_id": "9",
        }
        # The runtime lookup the legacy bridge uses must resolve the row.
        assert lesson(ContentService(db, collection), 7).id == deck.id
