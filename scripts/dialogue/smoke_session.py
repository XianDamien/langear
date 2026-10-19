"""Real pi + realtime acceptance against an isolated dev backend.

Creates its own synthetic account and cards through public APIs. Never truncates data.
Run inside langear-dialogue-backend, with --pcm pointing to a synthetic English recap.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
from uuid6 import uuid7
import httpx
from websockets.asyncio.client import connect

ORIGIN = 'http://localhost:3108'


async def smoke(pcm):
    client = httpx.Client(base_url='http://127.0.0.1:8000/api/v1', headers={'Origin': ORIGIN}, timeout=70)
    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code < 400, (path, response.status_code, response.text[:500])
        return response.json()
    identity = request('POST', '/auth/register', json={'email': 'teacher-smoke-' + str(uuid7()) + '@example.com', 'password': 'isolated teacher smoke password'})
    client.headers['X-CSRF-Token'] = identity['csrf_token']
    cookie = '; '.join(k + '=' + v for k, v in client.cookies.items())
    client.headers['Cookie'] = cookie
    deck = request('GET', '/decks')['decks'][0]['id']
    material = [
        ('I went to the theatre last week. I could not hear the actors.', '我上周去了剧院。我听不清演员的台词。'),
        ('The people behind me were talking loudly. Could you speak quietly, please?', '我后面的人说话很大声。能请你小声一点吗？'),
    ]
    for english, chinese in material:
        request('POST', '/notes', json={'note_type_key': 'sentence', 'card_template_key': 'sentence_translation',
            'fields': {'english': english, 'chinese': chinese}, 'deck_id': deck})
    queue = request('POST', '/review/queues', json={'scope': {'deck_id': deck, 'card_template_keys': ['sentence_translation']}})['queue_id']
    attempt_ids = []
    while True:
        current = request('GET', '/review/queues/' + queue + '/next')
        if not current['card']:
            break
        flipped = request('POST', '/review/queues/' + queue + '/flip', headers={'Idempotency-Key': str(uuid7())},
            json={'card_id': current['card']['id'], 'review_token': current['review_token'],
                'input': {'type': 'text', 'text': 'I went to theatre. People was talking loud.'}})
        attempt_id = flipped['attempt']['id']
        request('PUT', '/review/queues/' + queue + '/attempts/' + attempt_id + '/rating', headers={'Idempotency-Key': str(uuid7())},
            json={'rating': 'easy', 'card_schedule_revision': flipped['card_schedule_revision']})
        attempt_ids.append(attempt_id)
    before = [request('GET', '/attempts/' + attempt) for attempt in attempt_ids]
    session = request('POST', '/dialogue/sessions', json={'deck_id': deck, 'review_queue_id': queue,
        'entry_key': str(uuid7()), 'attempt_ids': attempt_ids})
    path = '/dialogue/sessions/' + session['id']
    print(json.dumps({'session_id': session['id'], 'scenario': session['scenario'], 'practised_attempts': len(attempt_ids)}, ensure_ascii=False), flush=True)
    audio_bytes, saved = 0, []
    async with connect('ws://127.0.0.1:8000/api/v1' + path + '/ws', origin=ORIGIN,
            additional_headers={'Cookie': cookie}, max_size=4 * 1024 * 1024) as ws:
        async def until_ready():
            nonlocal audio_bytes
            for _ in range(3000):
                event = json.loads(await asyncio.wait_for(ws.recv(), 70))
                kind = event.get('type')
                if kind == 'error':
                    raise RuntimeError(event)
                if kind == 'audio':
                    audio_bytes += len(base64.b64decode(event['data']))
                if kind == 'turn':
                    saved.append(event['turn'])
                    print(json.dumps(event['turn'], ensure_ascii=False), flush=True)
                if kind in ('ready', 'ended'):
                    return kind
            raise RuntimeError('Too many provider events')
        assert await until_ready() == 'ready'
        opening = saved[-1]['text']
        assert '?' in opening and any(word in opening.lower() for word in ('practis', 'practic', 'recap', 'summari', 'theatre', 'learn', 'review'))
        await ws.send(json.dumps({'type': 'audio_begin'}))
        raw = Path(pcm).read_bytes()
        for offset in range(0, len(raw), 3200):
            await ws.send(json.dumps({'type': 'audio', 'data': base64.b64encode(raw[offset:offset + 3200]).decode()}))
        await ws.send(json.dumps({'type': 'commit'}))
        state = await until_ready()
        assert any(t['role'] == 'user' for t in saved)
        for text in ["Yes, I'm ready. Let's try the theatre scene.",
                "Hello. The people behind me are talking loudly, and I can't hear the actors. Could you help me, please?",
                "Could you ask them to speak quietly, please? If it stays noisy, could we move to quieter seats?",
                "That sounds good. Thank you for your help."]:
            if state == 'ended':
                break
            await ws.send(json.dumps({'type': 'text', 'text': text}))
            state = await until_ready()
        if state != 'ended':
            await ws.send(json.dumps({'type': 'end'}))
            assert await until_ready() == 'ended'
    final = request('GET', path)
    assert final['status'] == 'finished' and final['user_turns'] >= 2 and audio_bytes > 0
    turn = next(t for t in final['turns'] if t['role'] == 'assistant')
    translation = request('POST', path + '/turns/' + turn['id'] + '/translation')
    assert translation.get('chinese')
    # Exercise optional pi evidence review without making it part of normal dialogue completion.
    reviewed = request('POST', path + '/review')
    assert reviewed['review'].get('summary_en')
    after = [request('GET', '/attempts/' + attempt) for attempt in attempt_ids]
    assert before == after, 'Dialogue changed existing practice records'
    from sqlalchemy.orm import Session
    from core.db import get_engine
    from core.models import DialogueSession
    from uuid import UUID
    with Session(get_engine()) as db:
        context = db.get(DialogueSession, UUID(session['id'])).context
        assert set(context['practice_attempt_ids']) == set(attempt_ids)
        assert len(context['sources']) == len(attempt_ids)
        assert all(source['input']['text'] == 'I went to theatre. People was talking loud.' for source in context['sources'])
        context_report = [{key: source.get(key) for key in ('attempt_id', 'card_id', 'note', 'input', 'feedback_status', 'rating')} for source in context['sources']]
    print(json.dumps({'result': 'passed', 'context': context_report, 'finish_reason': final['finish_reason'],
        'user_turns': final['user_turns'], 'output_audio_bytes': audio_bytes, 'translation': translation,
        'takeaway': reviewed['review']['summary_en'], 'practice_unchanged': before == after}, ensure_ascii=False, indent=2), flush=True)
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pcm', required=True)
    asyncio.run(smoke(parser.parse_args().pcm))
