"""Personal course settings must affect scheduling without changing other users."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models import Card, FSRSReviewLog, ReviewLog, Setting, UserCardFSRS, UserCardSRS
from app.services.deck_settings_service import DeckSettingsService
from app.utils.timezone import storage_now
from tests.integration.test_my_courses_router import (
    auth, courses_engine, courses_sessions, courses_client,
)


def select_courses(client, user_id=1):
    response = client.put('/api/v1/my-courses/lessons', headers=auth(user_id), json={"lesson_ids": [103, 104]})
    assert response.status_code == 200


def get_settings(client, deck_id=103, user_id=1):
    response = client.get(f'/api/v1/settings?deck_id={deck_id}', headers=auth(user_id))
    assert response.status_code == 200, response.text
    return response.json()['data']


def save(client, deck_id=103, user_id=1, **values):
    response = client.put(f'/api/v1/settings?deck_id={deck_id}', headers=auth(user_id), json=values)
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_scoped_settings_persist_and_isolate_user_deck_and_defaults(courses_client):
    for user in (1, 2):
        select_courses(courses_client, user)
    original = get_settings(courses_client)
    save(courses_client, daily_new_limit=3, daily_review_limit=7, desired_retention=0.95, learning_steps=[3, 20], relearning_steps=[8], maximum_interval=90)
    updated = get_settings(courses_client)
    assert updated['daily_new_limit'] == 3
    assert updated['desired_retention'] == 0.95
    assert updated['learning_steps'] == [3, 20]
    assert get_settings(courses_client, 104)['daily_new_limit'] == original['daily_new_limit']
    assert get_settings(courses_client, user_id=2)['daily_new_limit'] == original['daily_new_limit']
    assert courses_client.get('/api/v1/settings', headers=auth()).json()['data']['desired_retention'] == 0.9


def test_settings_inherit_parent_until_child_is_saved(courses_client):
    select_courses(courses_client)
    save(courses_client, deck_id=101, daily_new_limit=4)
    assert get_settings(courses_client)['daily_new_limit'] == 4
    save(courses_client, deck_id=103, daily_new_limit=2)
    save(courses_client, deck_id=101, daily_new_limit=6)
    assert get_settings(courses_client, 103)['daily_new_limit'] == 2
    assert get_settings(courses_client, 104)['daily_new_limit'] == 6


@pytest.mark.parametrize('method', ['get', 'put'])
def test_course_settings_require_authentication_and_selected_course(courses_client, method):
    kwargs = {'json': {'daily_new_limit': 4}} if method == 'put' else {}
    assert courses_client.request(method, '/api/v1/settings?deck_id=103', **kwargs).status_code == 401
    assert courses_client.request(method, '/api/v1/settings?deck_id=103', headers=auth(), **kwargs).status_code == 404
    assert courses_client.request(method, '/api/v1/settings?deck_id=103', headers=auth(999), **kwargs).status_code == 401


@pytest.mark.parametrize('updates', [
    {'daily_new_limit': -1}, {'daily_review_limit': 10001}, {'daily_new_limit': True},
    {'daily_new_limit': '3'}, {'desired_retention': 1}, {'learning_steps': [-1]},
    {'maximum_interval': 0}, {'default_source_scope': [101]}, {'user_id': 2},
    {'learning_steps': [True]}, {'maximum_interval': True}, {'desired_retention': True},
])
def test_invalid_settings_are_atomic(courses_client, updates):
    select_courses(courses_client)
    save(courses_client, daily_new_limit=3)
    response = courses_client.put('/api/v1/settings?deck_id=103', headers=auth(), json=updates)
    assert response.status_code in (400, 422)
    assert get_settings(courses_client)['daily_new_limit'] == 3


def test_personal_queue_reads_own_limits_and_own_usage(courses_client, courses_sessions):
    for user in (1, 2):
        select_courses(courses_client, user)
    with courses_sessions.begin() as db:
        db.add_all([Card(id=i, deck_id=103, card_index=i, front_text='Example') for i in range(201, 205)])
        db.flush()
        db.add(ReviewLog(user_id=2, card_id=201, deck_id=103, result_type='single', status='completed', ai_feedback_json={'study_session': {'quota_bucket': 'new'}}))
    save(courses_client, daily_new_limit=2)
    response = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth())
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['quota']['new_remaining'] == 2
    assert len(data['cards']) == 2
    save(courses_client, daily_new_limit=0)
    assert courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth()).json()['data']['cards'] == []
    assert len(courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth(2)).json()['data']['cards']) == 4


def test_parent_course_daily_quota_is_shared_by_its_lessons(courses_client, courses_sessions):
    select_courses(courses_client)
    save(courses_client, deck_id=101, daily_new_limit=2)
    with courses_sessions.begin() as db:
        db.add_all([Card(id=201, deck_id=103, card_index=0, front_text='One'), Card(id=202, deck_id=104, card_index=0, front_text='Two')])
        db.flush()
        db.add(ReviewLog(user_id=1, card_id=202, deck_id=104, result_type='single', status='completed', ai_feedback_json={'study_session': {'quota_bucket': 'new'}}))
    response = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth())
    assert response.status_code == 200, response.text
    assert response.json()['data']['quota']['new_remaining'] == 1
    save(courses_client, deck_id=104, daily_new_limit=3)
    response = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth())
    assert response.json()['data']['quota']['new_remaining'] == 2


def test_rating_uses_personal_fsrs_steps_and_keeps_other_user_unchanged(courses_client, courses_sessions):
    for user in (1, 2):
        select_courses(courses_client, user)
    save(courses_client, learning_steps=[3], maximum_interval=30)
    with courses_sessions.begin() as db:
        db.add(Card(id=201, deck_id=103, card_index=0, front_text='Example'))
        db.flush()
        db.add(ReviewLog(id=401, user_id=1, card_id=201, deck_id=103, result_type='single', status='completed'))
        db.add(UserCardFSRS(user_id=2, card_id=201, state='review', stability=8, due=storage_now()+timedelta(days=5), last_review=storage_now()))
    assert courses_client.post('/api/v1/study/submissions/401/rating', headers=auth(2), json={'rating':'again'}).status_code == 400
    response = courses_client.post('/api/v1/study/submissions/401/rating', headers=auth(), json={'rating':'again'})
    assert response.status_code == 200, response.text
    with courses_sessions() as db:
        own = db.get(UserCardFSRS, (1, 201))
        assert (own.due-own.last_review).total_seconds() == 180
        assert db.get(UserCardFSRS, (2, 201)).stability == 8
        assert db.get(UserCardSRS, 201) is None
        assert db.query(FSRSReviewLog).filter_by(card_id=201).count() == 1
    own_result = courses_client.get('/api/v1/study/submissions/401', headers=auth())
    assert own_result.status_code == 200
    assert own_result.json()['data']['srs']['state'] == 'learning'
    queue = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth()).json()['data']
    assert queue['cards'][0]['is_new_card'] is False
    assert queue['cards'][0]['last_review_at'] is not None
    own_tree = courses_client.get('/api/v1/decks/tree', headers=auth()).json()['data']
    other_tree = courses_client.get('/api/v1/decks/tree', headers=auth(2)).json()['data']
    assert own_tree['sources'][0]['units'][0]['lessons'][0]['completed_cards'] == 1
    assert other_tree['sources'][0]['units'][0]['lessons'][0]['completed_cards'] == 1
    assert courses_client.get('/api/v1/study/submissions/401', headers=auth(2)).status_code == 404
    assert courses_client.get('/api/v1/study/submissions?lesson_id=103', headers=auth(2)).json()['data'] == []


@pytest.mark.parametrize('has_stale_personal', [False, True])
def test_legacy_progress_belongs_only_to_original_user(courses_client, courses_sessions, has_stale_personal):
    for user in (1, 2):
        select_courses(courses_client, user)
    now = storage_now()
    with courses_sessions.begin() as db:
        db.add(Card(id=201, deck_id=103, card_index=0, front_text='Legacy'))
        db.flush()
        db.add(UserCardSRS(card_id=201, state='review', stability=12, difficulty=5, due=now+timedelta(days=5), last_review=now-timedelta(days=1)))
        if has_stale_personal:
            db.add(UserCardFSRS(user_id=1, card_id=201, state='learning', stability=1, due=now-timedelta(days=2), last_review=now-timedelta(days=3)))
        db.add(ReviewLog(id=401, user_id=1, card_id=201, deck_id=103, result_type='single', status='completed'))
    old_queue = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth()).json()['data']
    assert old_queue['cards'][0]['is_new_card'] is False
    assert old_queue['cards'][0]['card_state'] == 'review'
    other_queue = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth(2)).json()['data']
    assert other_queue['cards'][0]['is_new_card'] is True
    other_tree = courses_client.get('/api/v1/decks/tree', headers=auth(2)).json()['data']
    assert other_tree['sources'][0]['units'][0]['lessons'][0]['completed_cards'] == 0
    cards = courses_client.get('/api/v1/decks/103/cards', headers=auth()).json()['data']['cards']
    assert cards[0]['is_new_card'] is False
    save(courses_client, learning_steps=[3])
    response = courses_client.post('/api/v1/study/submissions/401/rating', headers=auth(), json={'rating': 'good'})
    assert response.status_code == 200, response.text
    assert response.json()['data']['srs']['state'] == 'review'
    with courses_sessions() as db:
        assert db.get(UserCardFSRS, (1, 201)).last_review > now
        assert db.get(UserCardSRS, 201).last_review == now-timedelta(days=1)
        assert db.get(UserCardFSRS, (2, 201)) is None


def test_submission_uses_authenticated_user_and_personal_quota(courses_client, courses_sessions, monkeypatch):
    select_courses(courses_client, 2)
    with courses_sessions.begin() as db:
        db.add(Card(id=201, deck_id=103, card_index=0, front_text='Example'))
    ready = SimpleNamespace(lesson_id=103, card_id=201, status='ready', final_text='An example.')
    monkeypatch.setattr('app.services.review_service.get_realtime_session_store', lambda: SimpleNamespace(get_session=lambda _: ready))
    monkeypatch.setattr('app.services.review_service.threading', SimpleNamespace(Thread=Mock(return_value=Mock())))
    response = courses_client.post('/api/v1/study/submissions', headers=auth(2), json={
        'lesson_id': 103, 'card_id': 201, 'oss_audio_path': 'recordings/test.webm', 'realtime_session_id': 'test-ready',
    })
    assert response.status_code == 200, response.text
    submission_id = response.json()['data']['submission_id']
    with courses_sessions() as db:
        record = db.get(ReviewLog, submission_id)
        assert record.user_id == 2
        assert record.ai_feedback_json['study_session']['quota_bucket'] == 'new'
    assert courses_client.get(f'/api/v1/study/submissions/{submission_id}', headers=auth()).status_code == 404
    queue = courses_client.get('/api/v1/study/session?lesson_id=103', headers=auth(2)).json()['data']
    assert queue['quota']['new_remaining'] == 19
