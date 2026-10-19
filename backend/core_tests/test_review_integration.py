from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.models import Card, MediaAsset
from core.review import ReviewService
from core.scheduling import study_day
from core_tests.test_review import make_note, queue, next_card, flip, rate


@pytest.fixture
def learning_time(monkeypatch):
    now = datetime(2026, 10, 17, 6, tzinfo=UTC)
    original = ReviewService.__init__

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.now = now
        self.day = study_day(now, self.collection.timezone)

    monkeypatch.setattr(ReviewService, '__init__', initialize)
    return now


def test_card_picker_selection_invalidates_queue(client, account):
    first = make_note(client, account)
    make_note(client, account)
    selected = client.get('/api/v1/cards').json()['cards'][0]['id']
    q = queue(client, account)
    assert next_card(client, q)['new_remaining'] == 2
    path = f"/api/v1/decks/{account['deck_id']}/study-selection"
    assert client.put(path, json={'card_ids': [selected]}).status_code == 200
    assert client.get(f'/api/v1/review/queues/{q}/next').json()['error']['code'] == 'QUEUE_EXPIRED'
    q = queue(client, account)
    assert next_card(client, q)['new_remaining'] == 1
    assert next_card(client, q)['card']['id'] == selected
    client.put(path, json={'card_ids': []})
    q = queue(client, account)
    assert next_card(client, q)['empty_reason'] == 'no_cards'
    client.put(path, json={'card_ids': None})
    assert next_card(client, queue(client, account))['new_remaining'] == 2


def test_again_continues_learning_without_changing_due_time(client, account, engine, learning_time):
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    assert current['can_undo'] is False
    flipped = flip(client, q, current).json()
    assert rate(client, q, flipped, 'again').status_code == 200
    result = next_card(client, q)
    assert result['card'] is not None
    assert result['card']['id'] == current['card']['id']
    assert result['review_token'] != current['review_token']
    assert 'attempt' not in result and 'back' not in result['card']
    assert result['empty_reason'] is None
    assert result['learning_remaining'] == 1
    assert result['can_undo'] is True
    assert result == next_card(client, q)
    with Session(engine) as db:
        due = db.get(Card, UUID(current['card']['id'])).due_at
        assert due == learning_time + timedelta(minutes=15)
    assert datetime.fromisoformat(result['next_due_at']) == due
    # Rebuilding the disposable queue retains early learning eligibility.
    rebuilt = next_card(client, queue(client, account))
    assert rebuilt['card']['id'] == current['card']['id']
    repeated = flip(client, rebuilt['queue_id'], rebuilt).json()
    assert repeated['attempt']['id'] != flipped['attempt']['id']
    assert rate(client, rebuilt['queue_id'], repeated, 'easy').status_code == 200
    assert next_card(client, rebuilt['queue_id'])['card'] is None


@pytest.mark.parametrize('regular_queue', ['new', 'review'])
def test_learning_ahead_follows_available_regular_work(client, account, engine, learning_time, regular_queue):
    make_note(client, account)
    make_note(client, account)
    with Session(engine) as db, db.begin():
        first, second = list(db.scalars(select(Card).order_by(Card.new_position)))
        first_id, second_id = str(first.id), str(second.id)
        first.type = first.queue = 'learning'
        first.new_position = None
        first.due_at = learning_time + timedelta(minutes=15)
        first.due_day = None
        if regular_queue == 'review':
            second.type = second.queue = 'review'
            second.new_position = None
            second.due_day = study_day(learning_time, 'Asia/Shanghai')
    q = queue(client, account)
    result = next_card(client, q)
    assert result['card']['id'] == second_id
    assert result['learning_remaining'] == 1
    # When ordinary work is no longer available, use the learning-ahead card.
    with Session(engine) as db, db.begin():
        db.get(Card, UUID(second_id)).queue = 'suspended'
    assert next_card(client, q)['card']['id'] == first_id


def test_learning_ahead_orders_by_due_and_respects_window(client, account, engine, learning_time):
    for _ in range(4):
        make_note(client, account)
    with Session(engine) as db, db.begin():
        cards = list(db.scalars(select(Card).order_by(Card.new_position)))
        ids = [str(card.id) for card in cards]
        for card, minutes in zip(cards[:3], [20, 5, 21]):
            card.type = card.queue = 'learning'
            card.new_position = None
            card.due_at = learning_time + timedelta(minutes=minutes)
            card.due_day = None
        cards[3].type = 'learning'
        cards[3].new_position = None
        cards[3].queue = 'day_learning'
        cards[3].due_day = study_day(learning_time, 'Asia/Shanghai') + 1
    q = queue(client, account)
    result = next_card(client, q)
    assert result['card']['id'] == ids[1]
    assert result['learning_remaining'] == 2
    for card_id, expected in [(ids[1], ids[0]), (ids[0], None)]:
        with Session(engine) as db, db.begin():
            db.get(Card, UUID(card_id)).queue = 'suspended'
        result = next_card(client, q)
        assert (result['card']['id'] if result['card'] else None) == expected
    assert result['empty_reason'] == 'waiting'
    assert result['learning_remaining'] == 0
    assert datetime.fromisoformat(result['next_due_at']) == learning_time + timedelta(minutes=21)


def test_upload_verification_ownership_claim_and_recovery(client, account, engine, monkeypatch):
    monkeypatch.setattr('core.uploads.upload_grant', lambda asset: {'media_asset_id': str(asset.id), 'upload_url': 'https://oss.invalid/upload', 'headers': {}})
    calls = []
    monkeypatch.setattr('core.uploads.verify_audio', lambda asset: calls.append(asset.object_key))
    grant = client.post('/api/v1/media-assets/audio-uploads', json={'content_type': 'audio/webm', 'size_bytes': 16})
    assert grant.status_code == 201, grant.text
    media = grant.json()['media_asset_id']
    with Session(engine) as db, db.begin():
        reference = MediaAsset(collection_id=UUID(account['collection']['id']), object_key='reference.mp3', kind='audio')
        db.add(reference)
        db.flush()
        ref = str(reference.id)
    make_note(client, account, {'english': 'Hello.', 'reference_audio': ref}, 'sentence_retelling')
    q = queue(client, account)
    current = next_card(client, q)
    payload = {'type': 'audio', 'temporary_media_asset_id': media}
    assert flip(client, q, current, payload).json()['error']['code'] == 'MEDIA_NOT_UPLOADED'
    path = f'/api/v1/media-assets/{media}/confirm-upload'
    assert client.post(path).status_code == 200
    assert client.post(path).status_code == 200
    assert len(calls) == 1
    flipped = flip(client, q, current, payload).json()
    assert flipped['attempt']['media_asset_id'] == media
    assert client.post(path).status_code == 409
    assert client.get(f'/api/v1/media-assets/{media}/url').status_code == 503  # no OSS test credentials
    response = client.post('/api/v1/auth/register', json={'email': 'other@example.com', 'password': 'a strong test password'})
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    assert client.post(path).status_code == 404
    assert client.get(f'/api/v1/attempts/{flipped["attempt"]["id"]}').status_code == 404


def test_simple_settings_reject_ignored_collection_values(client, account):
    path = f"/api/v1/decks/{account['deck_id']}/settings"
    current = client.get(path).json()
    values = {key: current[key] for key in ('daily_new_limit','daily_review_limit','desired_retention','maximum_interval','learning_steps','relearning_steps')}
    assert current['scheduling_enabled'] is True
    assert client.put(path, json={**values, 'learning_steps': [1]}).json()['error']['code'] == 'COLLECTION_SETTING_ONLY'
    assert client.get(path).json() == current


def test_undo_key_replays_and_paused_cards_can_be_restored(client, account):
    from uuid6 import uuid7
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    flipped = flip(client, q, current).json()
    assert rate(client, q, flipped, 'easy').status_code == 200
    key = {'Idempotency-Key': str(uuid7())}
    first = client.post(f'/api/v1/review/queues/{q}/undo', headers=key)
    assert first.status_code == 200, first.text
    assert client.post(f'/api/v1/review/queues/{q}/undo', headers=key).json() == first.json()
    assert rate(client, q, first.json(), 'easy').status_code == 200
    current = client.get(f'/api/v1/cards/{current["card"]["id"]}').json()
    path = f'/api/v1/cards/{current["id"]}/schedule'
    assert client.post(path, json={'action': 'suspend', 'card_schedule_revision': current['card_schedule_revision']}).status_code == 200
    rows = client.get('/api/v1/review/paused-cards', params={'deck_id': account['deck_id']}).json()['cards']
    assert len(rows) == 1 and rows[0]['queue'] == 'suspended'
    assert 'back' not in rows[0]
    assert client.post(path, json={'action': 'unsuspend', 'card_schedule_revision': rows[0]['card_schedule_revision']}).status_code == 200
    assert client.get('/api/v1/review/paused-cards', params={'deck_id': account['deck_id']}).json()['cards'] == []


def test_deck_counts_queries_do_not_grow_per_deck(client, account, engine):
    from sqlalchemy import event

    ids = [account['deck_id']]
    for i in range(12):
        ids.append(client.post('/api/v1/decks', json={'name': f'Deck {i}'}).json()['id'])
    for deck_id in ids:
        make_note(client, account, deck_id=deck_id)
    statements = []
    def count_queries(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', count_queries)
    try:
        response = client.get('/api/v1/review/deck-counts')
    finally:
        event.remove(engine, 'before_cursor_execute', count_queries)
    assert response.status_code == 200, response.text
    counts = response.json()['decks']
    assert all(counts[deck_id]['new_remaining'] == 1 for deck_id in ids)
    assert len(statements) <= 14, f'{len(statements)} SQL queries for 13 decks'


@pytest.mark.parametrize('new_limit', [1, 20])
def test_batched_deck_counts_match_individual_queue_rules(client, account, engine, learning_time, new_limit):
    from core.models import Collection, Deck, Note
    from core.review import RuntimeQueue
    from uuid6 import uuid7

    ids = [account['deck_id']]
    for i in range(4):
        ids.append(client.post('/api/v1/decks', json={'name': f'Counts {i}', 'parent_id': ids[0]}).json()['id'])
    for deck_id in ids:
        for _ in range(2):
            make_note(client, account, deck_id=deck_id)
    with Session(engine) as db, db.begin():
        collection = db.get(Collection, UUID(account['collection']['id']))
        collection.scheduling_config = {**collection.scheduling_config, 'new_limit': new_limit}
        by_deck = {deck_id: list(db.scalars(select(Card).where(Card.deck_id == UUID(deck_id)).order_by(Card.new_position))) for deck_id in ids}
        # Suspended and due-review cards, imminent/future learning, unrenderable
        # notes, imported content and an explicitly empty Card Picker.
        by_deck[ids[1]][0].queue = 'suspended'
        review = by_deck[ids[1]][1]
        review.type = review.queue = 'review'
        review.new_position = None
        review.due_day = study_day(learning_time, collection.timezone)
        for card, minutes in zip(by_deck[ids[2]], [5, 25]):
            card.type = card.queue = 'learning'
            card.new_position = None
            card.due_at = learning_time+timedelta(minutes=minutes)
        db.get(Note, by_deck[ids[3]][0].note_id).fields = {'meaning': '词'}
        db.get(Note, by_deck[ids[3]][1].note_id).guid = 'legacy:count-test:card:1'
        deck = db.get(Deck, UUID(ids[4]))
        deck.scheduling_config = {'study_card_ids': []}
    with Session(engine) as db, db.begin():
        collection = db.get(Collection, UUID(account['collection']['id']))
        service = ReviewService(db, collection)
        expected = {}
        for deck_id in ids:
            q = RuntimeQueue(uuid7(), {'deck_id': UUID(deck_id), 'include_descendants': False, 'exclude_imported': True}, [], service.day, service.stamp(), service.now+timedelta(hours=2))
            expected[deck_id] = service.counts(q)
        assert service.deck_counts()['decks'] == expected
        assert expected[ids[0]]['new_remaining'] == min(new_limit, 2)
        assert expected[ids[2]]['learning_remaining'] == 1
        assert expected[ids[3]]['new_remaining'] == 0
        assert expected[ids[4]]['empty_reason'] == 'no_cards'
