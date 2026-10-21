from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from core.models import Collection, Deck


VALUES = {
    "daily_new_limit": 7, "daily_review_limit": 45,
    "desired_retention": 0.92, "maximum_interval": 36500,
    "learning_steps": [15], "relearning_steps": [15],
}

SOURCE_ORDER = {
    "new_card_gather_order": "lowest_position",
    "new_card_sort_order": "order_gathered",
}


def test_new_card_order_defaults_to_source_order(client, account):
    parent = account["deck_id"]
    child = client.post("/api/v1/decks", json={"name": "Child", "parent_id": parent}).json()["id"]
    for deck_id in (parent, child):
        data = client.get(f"/api/v1/decks/{deck_id}/settings").json()
        assert {key: data[key] for key in SOURCE_ORDER} == SOURCE_ORDER
        assert data["new_card_order_overrides"] == dict.fromkeys(SOURCE_ORDER)


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
    assert saved["scheduling_enabled"] is True
    assert client.get(f"/api/v1/decks/{child}/settings").json()["daily_new_limit"] == 7
    assert client.get(f"/api/v1/decks/{sibling}/settings").json()["daily_new_limit"] == 9999
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
    {"new_card_gather_order": "invalid"}, {"new_card_sort_order": "random_cards"},
    {"new_card_gather_order": 3},
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


def test_new_card_order_preserves_custom_and_restores_inheritance(client, account):
    parent = account['deck_id']
    child = client.post('/api/v1/decks', json={'name': 'Lesson', 'parent_id': parent}).json()['id']
    parent_path = f'/api/v1/decks/{parent}/settings'
    child_path = f'/api/v1/decks/{child}/settings'
    source = {'new_card_gather_order': 'lowest_position', 'new_card_sort_order': 'order_gathered'}
    assert client.put(parent_path, json={**VALUES, **source}).status_code == 200
    inherited = client.get(child_path).json()
    assert all(inherited[key] == value for key, value in source.items())
    assert inherited['new_card_order_overrides'] == dict.fromkeys(source)
    custom = {'new_card_gather_order': 'highest_position', 'new_card_sort_order': 'template'}
    assert client.put(child_path, json={**VALUES, **custom}).status_code == 200
    # Older clients and saves of unrelated settings must leave order untouched.
    saved = client.put(child_path, json=VALUES).json()
    assert saved['new_card_order_overrides'] == custom
    assert client.get(parent_path).json()['new_card_order_overrides'] == source
    restored = client.put(child_path, json={**VALUES, **dict.fromkeys(source)}).json()
    assert restored['new_card_order_overrides'] == dict.fromkeys(source)
    assert all(restored[key] == value for key, value in source.items())


def test_settings_order_rebuilds_queue_without_changing_card_schedules(client, account, engine):
    from sqlalchemy import select
    from core.models import Card
    from core_tests.test_review import make_note, queue, next_card

    for word in ['first', 'second', 'third']:
        make_note(client, account, {'word': word, 'meaning': '词'})
    path = f"/api/v1/decks/{account['deck_id']}/settings"
    with Session(engine) as db:
        cards = list(db.scalars(select(Card).order_by(Card.new_position)))
        first, last = str(cards[0].id), str(cards[-1].id)
        before = [(c.id, c.new_position, c.reps, c.fsrs_state, c.due_at, c.schedule_revision) for c in cards]
    assert client.put(path, json={**VALUES, 'new_card_gather_order': 'highest_position', 'new_card_sort_order': 'order_gathered'}).status_code == 200
    old_queue = queue(client, account)
    assert next_card(client, old_queue)['card']['id'] == last
    assert client.put(path, json={**VALUES, 'new_card_gather_order': 'lowest_position', 'new_card_sort_order': 'order_gathered'}).status_code == 200
    expired = client.get(f'/api/v1/review/queues/{old_queue}/next')
    assert expired.status_code == 409
    assert expired.json()['error']['code'] == 'QUEUE_EXPIRED'
    assert next_card(client, queue(client, account))['card']['id'] == first
    with Session(engine) as db:
        cards = list(db.scalars(select(Card).order_by(Card.new_position)))
        assert [(c.id, c.new_position, c.reps, c.fsrs_state, c.due_at, c.schedule_revision) for c in cards] == before
