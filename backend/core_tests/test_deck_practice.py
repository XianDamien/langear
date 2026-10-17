from uuid import UUID
from sqlalchemy.orm import Session
from core.models import MediaAsset


def test_membership_persists_is_idempotent_and_does_not_change_cards(client, account):
    deck_id = account["deck_id"]
    path = f"/api/v1/decks/{deck_id}/membership"
    assert client.get(f"/api/v1/decks/{deck_id}").json()["in_my_courses"] is False
    for _ in range(2):
        assert client.put(path, json={"joined": True}).json()["in_my_courses"] is True
    assert client.get("/api/v1/decks").json()["decks"][0]["in_my_courses"] is True
    assert client.put(path, json={"joined": False}).json()["in_my_courses"] is False
    assert client.get(f"/api/v1/decks/{deck_id}").status_code == 200
    assert client.get("/api/v1/cards").json()["cards"] == []
    client.headers.pop("X-CSRF-Token")
    assert client.put(path, json={"joined": True}).status_code == 403


def test_membership_and_private_media_are_collection_scoped(client, account, engine, monkeypatch):
    with Session(engine) as db, db.begin():
        asset = MediaAsset(collection_id=UUID(account["collection"]["id"]), object_key="fixture/audio.mp3", kind="audio")
        db.add(asset)
        db.flush()
        asset_id = str(asset.id)
    calls = []
    monkeypatch.setattr("core.media.sign_media", lambda key: calls.append(key) or "https://media.example/audio")
    path = f"/api/v1/media-assets/{asset_id}/url"
    assert client.get(path).json()["url"] == "https://media.example/audio"
    assert calls == ["fixture/audio.mp3"]
    response = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "another strong password"})
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.put(f"/api/v1/decks/{account['deck_id']}/membership", json={"joined": True}).status_code == 404
    assert client.get(path).status_code == 404
    assert calls == ["fixture/audio.mp3"]
    assert all(not d["in_my_courses"] for d in client.get("/api/v1/decks").json()["decks"])
