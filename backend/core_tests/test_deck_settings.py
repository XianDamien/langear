from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from core.models import Collection, Deck


VALUES = {
    "daily_new_limit": 7, "daily_review_limit": 45,
    "desired_retention": 0.92, "maximum_interval": 1200,
    "learning_steps": [1, 15], "relearning_steps": [],
}


def test_settings_persist_inherit_and_preserve_other_preferences(client, account, engine):
    parent = account["deck_id"]
    child = client.post("/api/v1/decks", json={"name": "Child", "parent_id": parent}).json()["id"]
    sibling = client.post("/api/v1/decks", json={"name": "Other"}).json()["id"]
    path = f"/api/v1/decks/{parent}/settings"
    with Session(engine) as db, db.begin():
        row = db.get(Deck, UUID(parent))
        row.scheduling_config = {"sibling_burying": False}
        defaults = dict(db.get(Collection, UUID(account["collection"]["id"])).scheduling_config)
    assert client.put(path, json=VALUES).status_code == 200
    saved = client.get(path).json()
    assert all(saved[key] == value for key, value in VALUES.items())
    assert saved["scheduling_enabled"] is False
    assert client.get(f"/api/v1/decks/{child}/settings").json()["daily_new_limit"] == 7
    assert client.get(f"/api/v1/decks/{sibling}/settings").json()["daily_new_limit"] == 20
    client.put(f"/api/v1/decks/{child}/settings", json={**VALUES, "daily_new_limit": 3})
    assert client.get(path).json()["daily_new_limit"] == 7
    with Session(engine) as db:
        assert db.get(Deck, UUID(parent)).scheduling_config["sibling_burying"] is False
        assert db.get(Collection, UUID(account["collection"]["id"])).scheduling_config == defaults


@pytest.mark.parametrize("patch", [
    {"daily_new_limit": -1}, {"daily_review_limit": 10001},
    {"daily_new_limit": True}, {"desired_retention": 1},
    {"maximum_interval": 36501}, {"learning_steps": [0]},
    {"relearning_steps": [1.5]}, {"unknown": 1},
])
def test_invalid_settings_do_not_write(client, account, patch):
    path = f"/api/v1/decks/{account['deck_id']}/settings"
    before = client.get(path).json()
    assert client.put(path, json={**VALUES, **patch}).status_code == 422
    assert client.get(path).json() == before


def test_settings_require_auth_csrf_and_collection_ownership(client, account):
    path = f"/api/v1/decks/{account['deck_id']}/settings"
    client.headers.pop("X-CSRF-Token")
    assert client.put(path, json=VALUES).status_code == 403
    response = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "another strong password"})
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.get(path).status_code == 404
    assert client.put(path, json=VALUES).status_code == 404
    client.cookies.clear()
    assert client.get(path).status_code == 401
