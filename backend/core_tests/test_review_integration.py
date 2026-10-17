from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session
from core.models import MediaAsset
from core_tests.test_review import make_note, queue, next_card, flip, rate


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


def test_rating_exposes_waiting_and_undo_status(client, account):
    make_note(client, account)
    q = queue(client, account)
    assert next_card(client, q)['can_undo'] is False
    flipped = flip(client, q, next_card(client, q)).json()
    assert rate(client, q, flipped, 'again').status_code == 200
    result = next_card(client, q)
    assert result['empty_reason'] == 'waiting'
    assert result['next_due_at']
    assert result['can_undo'] is True


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
