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
            {'english': 'a red apple', 'meaning_zh': '一个红苹果', 'source': source}]}


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
    body = {'deck_id': account['deck_id'], 'review_queue_id': q, 'entry_key': str(uuid4()), 'attempt_ids': [f['attempt']['id']]}
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


def test_availability_requires_planner_and_voice_credentials(client, account, dialogue, monkeypatch):
    monkeypatch.delenv('CORE_DIALOGUE_AGENT_TOKEN', raising=False)
    monkeypatch.delenv('CORE_DIALOGUE_API_KEY', raising=False)
    get_settings.cache_clear()
    assert client.get('/api/v1/dialogue/availability').json() == {'enabled': False}
    monkeypatch.setenv('CORE_DIALOGUE_AGENT_TOKEN', 'planner-token-' + 'x' * 32)
    monkeypatch.setenv('CORE_DIALOGUE_API_KEY', 'voice-provider-key')
    get_settings.cache_clear()
    assert client.get('/api/v1/dialogue/availability').json() == {'enabled': True}


def test_dialogue_requires_current_completed_round_and_grounded_expressions(client, account, dialogue, monkeypatch):
    from core import dialogue as module
    forged_round = {**dialogue, 'entry_key': str(uuid4()), 'review_queue_id': str(uuid4())}
    assert client.post('/api/v1/dialogue/sessions', json=forged_round).status_code == 409
    original = module.planner
    def invented_expression(kind, context):
        value = original(kind, context)
        value['target_expressions'][0]['english'] = 'a spaceship'
        return value
    monkeypatch.setattr(module, 'planner', invented_expression)
    forged_text = {**dialogue, 'entry_key': str(uuid4())}
    assert client.post('/api/v1/dialogue/sessions', json=forged_text).status_code == 502


def test_new_round_cannot_reuse_historical_ratings_or_start_with_available_cards(client, account, dialogue):
    q = queue(client, account)
    entry = {**dialogue, 'review_queue_id': q}
    response = client.post('/api/v1/dialogue/sessions', json=entry)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'DIALOGUE_ROUND_EVIDENCE_MISMATCH'
    make_note(client, account, fields={'word': 'pear', 'meaning': '梨'})
    entry['review_queue_id'] = queue(client, account)
    response = client.post('/api/v1/dialogue/sessions', json=entry)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'DIALOGUE_ROUND_INCOMPLETE'


class FakeOmni:
    def __init__(self, finish=False, interrupt=False, spoken_finish=False):
        self.events = asyncio.Queue(); self.count = 0; self.inputs = 0
        self.finish, self.interrupt = finish, interrupt
        self.spoken_finish = spoken_finish
        self.sent = []
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
        self.sent.append(value)
        if value['type'] == 'session.update':
            if 'turn_detection' in value['session']:
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
                if self.spoken_finish:
                    self.events.put_nowait({'type': 'response.audio_transcript.delta', 'delta': 'You asked politely. Well done! Goodbye.'})
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


@pytest.mark.parametrize('phase', ['responding', 'transcribing'])
def test_finish_waits_for_inflight_work_then_requests_distinct_closing(client, account, dialogue, monkeypatch, phase):
    import json
    from core import dialogue_voice

    class InflightOmni(FakeOmni):
        waiting = False

        async def send(self, raw):
            value = json.loads(raw)
            if value['type'] == 'response.create' and self.count == 0 and phase == 'responding':
                self.sent.append(value)
                self.count += 1
                self.waiting = True
                self.events.put_nowait({'type': 'response.audio_transcript.delta', 'delta': 'Tell me what happened.'})
            elif value['type'] == 'input_audio_buffer.commit' and phase == 'transcribing':
                self.sent.append(value)
                self.inputs += 1
                self.waiting = True
            elif value['type'] == 'input_audio_buffer.clear' and self.waiting:
                self.sent.append(value)
                self.waiting = False
                if phase == 'responding':
                    self.events.put_nowait({'type': 'response.done', 'response': {'id': 'inflight', 'status': 'completed', 'output': []}})
                else:
                    self.events.put_nowait({'type': 'conversation.item.input_audio_transcription.completed',
                        'item_id': 'inflight-input', 'transcript': 'I asked for an apple.'})
            elif value['type'] == 'response.create' and 'learner chose to stop' in value['response']['instructions']:
                self.sent.append(value)
                self.count += 1
                self.events.put_nowait({'type': 'response.audio_transcript.delta', 'delta': 'Thank you for practising. Goodbye.'})
                self.events.put_nowait({'type': 'response.done', 'response': {'id': 'closing', 'status': 'completed', 'output': []}})
            else:
                await super().send(raw)

    provider = InflightOmni()
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: provider)
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        if phase == 'responding':
            receive(ws, 'message_delta')
        else:
            receive(ws, 'ready')
            speech(ws)
        ws.send_json({'type': 'end'})
        assert receive(ws, 'ended')['reason'] == 'user_ended'
    saved = client.get(path).json()
    assert saved['turns'][-1]['text'] == 'Thank you for practising. Goodbye.'
    assert saved['user_turns'] == (1 if phase == 'transcribing' else 0)
    assert sum(e['type'] == 'response.create' for e in provider.sent) == 2


def test_spoken_natural_closing_with_finish_tool_is_not_repeated(client, account, dialogue, monkeypatch):
    from core import dialogue_voice
    provider = FakeOmni(finish=True, spoken_finish=True)
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: provider)
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        receive(ws, 'ready')
        speech(ws)
        assert receive(ws, 'ended')['reason'] == 'task_completed'
    assert provider.count == 2
    assert client.get(path).json()['turns'][-1]['text'] == 'You asked politely. Well done! Goodbye.'


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


def test_context_uses_owned_attempt_snapshots_with_input_feedback_and_bounded_realtime_payload(client, account, dialogue, engine, monkeypatch):
    from copy import deepcopy
    from uuid import UUID
    from sqlalchemy.orm import Session
    from core.models import Attempt
    from core import dialogue as module
    from core.dialogue_prompt import voice_practice
    with Session(engine) as db, db.begin():
        attempt = db.get(Attempt, UUID(dialogue['attempt_ids'][0]))
        attempt.input_snapshot = {'type': 'text', 'text': 'I want apple.'}
        attempt.asr_result = {'text': 'I want apple.'}
        attempt.ai_feedback = {'correction': 'I would like an apple, please.', 'details': {'article': 'Use an before apple.'}}
        attempt.ai_status = 'succeeded'
    captured = {}
    original = module.planner
    def capture(kind, context):
        captured.update(context)
        return original(kind, context)
    monkeypatch.setattr(module, 'planner', capture)
    result = create(client, dialogue)
    source = captured['sources'][0]
    assert source['input']['text'] == source['transcription']['text'] == 'I want apple.'
    assert source['note']['word'] == 'apple'
    assert source['feedback']['details']['article'] == 'Use an before apple.'
    assert source['rating'] == 'easy'
    assert 'temporary_media_asset_id' not in source['input']
    realtime = voice_practice(captured, result['scenario'])
    assert realtime['sources'][0]['feedback'] == source['feedback']
    # Exercise actual long-context selection while preserving source evidence and original storage.
    large = deepcopy(captured)
    large['sources'] += [{**deepcopy(source), 'attempt_id': str(uuid4()), 'note': {'english': 'x' * 40000}} for _ in range(39)]
    bounded = voice_practice(large, result['scenario'])
    import json
    assert len(json.dumps(bounded, ensure_ascii=False)) < 28000
    assert source['attempt_id'] in [s['attempt_id'] for s in bounded['sources']]
    assert bounded['omitted_count'] > 0
    assert large['sources'][1]['note']['english'] == 'x' * 40000


def test_realtime_receives_lesson_context_and_start_click_is_not_a_learner_answer(client, account, dialogue, monkeypatch):
    from core import dialogue_voice
    provider = FakeOmni()
    monkeypatch.setattr(dialogue_voice, 'provider_connection', lambda: provider)
    session = create(client, dialogue)
    path = '/api/v1/dialogue/sessions/' + session['id']
    with client.websocket_connect('wss://testserver' + path + '/ws') as ws:
        receive(ws, 'ready')
        ws.send_json({'type': 'text', 'text': 'I practised buying an apple.'})
        assert receive(ws, 'turn')['turn']['text'] == 'I practised buying an apple.'
        receive(ws, 'ready')
        ws.send_json({'type': 'end'})
        assert receive(ws, 'ended')['reason'] == 'user_ended'
    prompt = next(e['session']['instructions'] for e in provider.sent if e['type'] == 'session.update')
    assert 'brief recap' in prompt and 'apple' in prompt and 'feedback_status' in prompt
    saved = client.get(path).json()
    assert saved['user_turns'] == 1
    assert [t['text'] for t in saved['turns'] if t['role'] == 'user'] == ['I practised buying an apple.']
    assert any(e['type'] == 'conversation.item.create' and 'Start my English' in str(e) for e in provider.sent)


def test_translation_only_reads_an_owned_saved_turn(client, account, dialogue, monkeypatch, engine):
    from uuid import UUID
    from core import dialogue as module, dialogue_voice
    from sqlalchemy.orm import Session
    from core.models import DialogueSession
    session = create(client, dialogue)
    with Session(engine) as db:
        owner = db.get(DialogueSession, UUID(session['id'])).collection_id
    token, _, _ = dialogue_voice.claim(owner, UUID(session['id']))
    turn, _ = dialogue_voice.save_turn(owner, UUID(session['id']), token, 'teacher-translate', 'assistant', 'Could you speak quietly, please?')
    def translate(kind, context):
        assert kind == 'translation' and context == {'text': turn['text']}
        return {'chinese': '能请你小声一点吗？'}
    monkeypatch.setattr(module, 'planner', translate)
    path = '/api/v1/dialogue/sessions/' + session['id'] + '/turns/' + turn['id'] + '/translation'
    assert client.post(path).json() == {'chinese': '能请你小声一点吗？'}
    assert client.post(path.replace(turn['id'], str(uuid4()))).status_code == 404
    with TestClient(app, base_url='https://testserver', headers={'Origin': 'http://localhost:3002'}) as other:
        identity = other.post('/api/v1/auth/register', json={'email': 'translator@example.com', 'password': 'another strong password'}).json()
        other.headers['X-CSRF-Token'] = identity['csrf_token']
        assert other.post(path).status_code == 404
