from sqlalchemy.orm import Session
from core.models import Note


def test_selection_preserves_originals_and_filters_review(client, account, engine):
    deck = account["deck_id"]
    first = client.post("/api/v1/notes", json={"note_type_key": "vocabulary", "deck_id": deck, "fields": {"word": "one", "meaning": "一"}})
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/notes", json={"note_type_key": "vocabulary", "deck_id": deck, "fields": {"word": "two", "meaning": "二"}})
    card_id = first.json()["cards"][0]["id"]
    path = f"/api/v1/decks/{deck}/study-selection"
    assert client.get(path).json()["card_ids"] is None
    assert client.put(path, json={"card_ids": [card_id]}).status_code == 200
    assert client.get(path).json()["card_ids"] == [card_id]
    rows = client.get("/api/v1/cards", params={"deck_id": deck, "study_only": True}).json()["cards"]
    assert [row["id"] for row in rows] == [card_id]
    assert len(client.get("/api/v1/cards", params={"deck_id": deck}).json()["cards"]) > 1
    other = client.post("/api/v1/decks", json={"name": "Other"}).json()["id"]
    assert client.put(f"/api/v1/decks/{other}/study-selection", json={"card_ids": [card_id]}).status_code == 400
    assert client.get(f"/api/v1/decks/{other}/study-selection").json()["card_ids"] is None
    assert client.put(path, json={"card_ids": None}).status_code == 200
    assert len(client.get("/api/v1/cards", params={"deck_id": deck, "study_only": True}).json()["cards"]) > 1
    assert client.put(path, json={"card_ids": []}).json()["joined"] is False
    assert client.get("/api/v1/cards", params={"deck_id": deck, "study_only": True}).json()["cards"] == []
    with Session(engine) as db:
        assert len(db.query(Note).all()) == 2
    client.headers.pop("X-CSRF-Token")
    assert client.put(path, json={"card_ids": None}).status_code == 403
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_study_selection_is_scoped_to_the_current_account(client, account):
    deck = account["deck_id"]
    path = f"/api/v1/decks/{deck}/study-selection"
    other = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "another strong password"})
    assert other.status_code == 201, other.text
    client.headers["X-CSRF-Token"] = other.json()["csrf_token"]
    assert client.get(path).status_code == 404
    assert client.put(path, json={"card_ids": None}).status_code == 404
    assert client.get("/api/v1/cards", params={"deck_id": deck, "study_only": True}).status_code == 404
