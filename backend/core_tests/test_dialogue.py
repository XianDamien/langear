"""Dialogue HTTP/WebSocket contract; external model traffic is replaced at its transport boundary."""
import asyncio
import base64
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from core.main import app
from core.config import get_settings
from core_tests.test_review import make_note, queue, next_card, flip, rate


def scenario(context):
    s = context['sources'][0]
    source = {'card_id': s['card_id'], 'attempt_id': s['attempt_id']}
    return {'title': 'At the fruit shop', 'setup_zh': '买一些水果并询价。', 'learner_role': 'Customer', 'agent_role': 'Shopkeeper',
        'goals': [{'id': 'buy', 'description_zh': '买一个苹果'}],
        'target_expressions': [{'english': 'an apple', 'meaning_zh': '一个苹果', 'source': source},
            {'english': 'please', 'meaning_zh': '请', 'source': source}]}


@pytest.fixture
def dialogue(monkeypatch, client, account):
    monkeypatch.setenv('CORE_DIALOGUE_ENABLED', 'true'); get_settings.cache_clear()
    from core import dialogue as module
    def model(kind, context):
        if kind == 'scenario': return scenario(context)
        users = [t['id'] for t in context['turns'] if t['role'] == 'user']
        return {'summary_zh': '已完成购买。' if users else '本次提前结束，尚未开始任务。',
            'goals': [{'goal_id': 'buy', 'completed': bool(users), 'evidence_turn_ids': users[:1]}],
            'used_expressions': [{'english': 'an apple', 'evidence_turn_ids': users[:1]}] if users else [], 'practice_points': []}
    monkeypatch.setattr(module, 'planner', model)
    make_note(client, account)
    q = queue(client, account)
    f = flip(client, q, next_card(client, q)).json()
    assert rate(client, q, f, 'easy').status_code == 200
    body = {'deck_id': account['deck_id'], 'entry_key': str(uuid4()), 'attempt_ids': [f['attempt']['id']]}
    yield body
    get_settings.cache_clear()


def create(client, body):
    response = client.post('/api/v1/dialogue/sessions', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_authorized_context_idempotency_and_no_scheduling_side_effects(client, account, dialogue):
    session = create(client, dialogue)
    assert session['scenario']['target_expressions'][0]['source']['attempt_id'] == dialogue['attempt_ids'][0]
    assert create(client, dialogue)['id'] == session['id']
    attempt = client.get('/api/v1/attempts/' + dialogue['attempt_ids'][0]).json()
    assert attempt['rating'] == 'easy'
    path = '/api/v1/dialogue/sessions/' + session['id']
    assert client.get(path).json()['turns'] == []
    assert client.post(path + '/review').status_code == 409
    assert client.post(path + '/finish').json()['finish_reason'] == 'user_ended'
    review = client.post(path + '/review').json()['review']
    assert review['goals'][0]['completed'] is False
    assert client.post(path + '/review').json()['review'] == review
    assert client.get('/api/v1/attempts/' + dialogue['attempt_ids'][0]).json() == attempt


def test_other_collection_cannot_read_use_or_connect_to_dialogue(client, account, dialogue):
    session = create(client, dialogue)
    with TestClient(app, base_url='https://testserver', headers={'Origin': 'http://localhost:3002'}) as other:
        identity = other.post('/api/v1/auth/register', json={'email': 'other@example.com', 'password': 'another strong password'}).json()
        other.headers['X-CSRF-Token'] = identity['csrf_token']
        assert other.get('/api/v1/dialogue/sessions/' + session['id']).status_code == 404
        assert other.post('/api/v1/dialogue/sessions', json=dialogue).status_code == 404
        assert other.post('/api/v1/dialogue/sessions/' + session['id'] + '/finish').status_code == 404
        with pytest.raises(WebSocketDisconnect):
            with other.websocket_connect('wss://testserver/api/v1/dialogue/sessions/' + session['id'] + '/ws'): pass
    forged = {**dialogue, 'entry_key': str(uuid4()), 'attempt_ids': [str(uuid4())]}
    assert client.post('/api/v1/dialogue/sessions', json=forged).status_code == 404
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/dialogue/sessions', json=dialogue).status_code == 403
    client.headers['X-CSRF-Token'] = csrf


def test_planner_cannot_invent_source_or_claim_agent_expression(client, account, dialogue, monkeypatch):
    from core import dialogue as module
    original = module.planner
    def forged(kind, context):
        value = original(kind, context)
        value['target_expressions'][0]['source']['attempt_id'] = str(uuid4())
        return value
    monkeypatch.setattr(module, 'planner', forged)
    assert client.post('/api/v1/dialogue/sessions', json=dialogue).status_code == 502


class FakeOmni:
    def __init__(self, finish=False, interrupt=False):
        self.events = asyncio.Queue(); self.count = 0; self.inputs = 0
        self.finish, self.interrupt = finish, interrupt
    async def __aenter__(self):
        self.events.put_nowait({'type': 'session.created'}); return self
    async def __aexit__(self, *args): pass
    def __aiter__(self): return self
    async def __anext__(self):
        import json
        return json.dumps(await self.events.get())
    async def send(self, raw):
        import json
        value = json.loads(raw)
        if value['type'] == 'session.update':
            assert value['session']['turn_detection'] is None
            self.events.put_nowait({'type': 'session.updated'})
        elif value['type'] == 'input_audio_buffer.commit':
            self.inputs += 1
            self.events.put_nowait({'type': 'conversation.item.input_audio_transcription.completed',
                'item_id': 'user-' + str(self.inputs), 'transcript': 'An apple, please.'})
        elif value['type'] == 'response.create':
            assert value['response']['instructions']
            self.count += 1
            if self.finish and self.inputs and self.count == 2:
                self.events.put_nowait({'type': 'response.function_call_arguments.done', 'name': 'finish_scenario',
                    'arguments': '{"goal_ids":["buy"]}', 'call_id': 'finish-1'})
                self.events.put_nowait({'type': 'response.done', 'response': {'id': 'resp-2', 'status': 'completed', 'output': [{'type': 'function_call'}]}})
            else:
                self.events.put_nowait({'type': 'response.audio_transcript.delta', 'delta': 'Hello! What would you like?'})
                self.events.put_nowait({'type': 'response.done', 'response': {'id': 'resp-' + str(self.count), 'status': 'failed' if self.interrupt else 'completed', 'output': []}})


def receive(ws, kind):
    for _ in range(30):
        event = ws.receive_json()
        if event['type'] == 'error': raise AssertionError(event)
        if event['type'] == kind: return event
    raise AssertionError('Expected ' + kind)


def speech(ws):
    ws.send_json({'type': 'audio_begin'})
    ws.send_json({'type': 'audio', 'data': base64.b64encode(b'\x00\x01' * 3200).decode()})
    ws.send_json({'type': 'commit'})


@pytest.mark.parametrize('goal_done', [False, True])
def test_manual_voice_persists_turns_and_finishes_on_goal_or_eight_turns(client, account, dialogue, monkeypatch, goal_done):
    from core import dialogue_voice
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: FakeOmni(finish=goal_done))
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        assert receive(ws, 'connected')['session']['id'] == session['id']
        receive(ws, 'ready')
        for index in range(1 if goal_done else 8):
            speech(ws)
            assert receive(ws, 'turn')['turn']['role'] == 'user'
            if index < (0 if goal_done else 7): receive(ws, 'ready')
        assert receive(ws, 'ended')['reason'] == ('task_completed' if goal_done else 'turn_limit')
    saved = client.get(path).json()
    assert saved['status'] == 'finished'
    assert saved['user_turns'] == (1 if goal_done else 8)
    assert len([t for t in saved['turns'] if t['role'] == 'user']) == saved['user_turns']
    reviewed = client.post(path + '/review')
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['review']['used_expressions'][0]['english'] == 'an apple'


def test_interrupted_agent_output_is_not_saved_and_can_reconnect(client, account, dialogue, monkeypatch):
    from core import dialogue_voice
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: FakeOmni(interrupt=True))
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        assert ws.receive_json()['type'] == 'connected'
        while ws.receive_json()['type'] != 'error': pass
    saved = client.get(path).json()
    assert saved['status'] == 'interrupted' and saved['turns'] == []
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: FakeOmni())
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        receive(ws, 'ready')
        ws.send_json({'type': 'end'})
        assert receive(ws, 'ended')['reason'] == 'user_ended'
    assert client.get(path).json()['status'] == 'finished'


def test_review_rejects_agent_only_evidence_and_concurrent_voice_is_exclusive(client, account, dialogue, monkeypatch):
    from core import dialogue_voice, dialogue as module
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: FakeOmni())
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as first:
        receive(first, 'ready')
        with client.websocket_connect('wss://testserver' + path + '/ws') as second:
            assert second.receive_json()['code'] == 'DIALOGUE_BUSY'
        speech(first); receive(first, 'ready')
        first.send_json({'type': 'end'}); receive(first, 'ended')
    turns = client.get(path).json()['turns']
    agent_id = next(t['id'] for t in turns if t['role'] == 'assistant')
    original = module.planner
    def wrong_evidence(kind, context):
        value = original(kind, context)
        value['goals'][0]['evidence_turn_ids'] = [agent_id]
        return value
    monkeypatch.setattr(module, 'planner', wrong_evidence)
    assert client.post(path + '/review').status_code == 502
    assert client.get(path).json()['review'] is None
    monkeypatch.setattr(module, 'planner', original)
    assert client.post(path + '/review').status_code == 200
