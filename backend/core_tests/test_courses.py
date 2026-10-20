"""Deck hierarchy, statistics and My Courses membership."""

from uuid import UUID

from sqlalchemy.orm import Session

from core.models import Deck, Note
from core_tests.test_review import flip, make_note, next_card, queue, rate


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
