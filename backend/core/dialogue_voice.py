"""Authenticated Manual-mode Qwen-Omni bridge; the browser never receives provider keys."""
import asyncio
import base64
import binascii
import json
import logging
import re
import time
from datetime import timedelta
from urllib.parse import urlencode
from uuid import UUID
from uuid6 import uuid7
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect
from core import auth
from core.config import get_settings
from core.db import get_engine
from core import dialogue as dialogue_api
from core.dialogue import SESSION_SECONDS, enabled, session_data
from core.dialogue_prompt import instructions, voice_practice
from core.dialogue_schemas import Translation
from core.errors import DomainError
from core.models import DialogueSession, DialogueTurn, utcnow
from core.repository import ContentRepository

router = APIRouter(prefix='/api/v1/dialogue')
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 16000 * 2 * 29


def provider_connection():
    config = enabled()
    if not config.dialogue_api_key:
        raise DomainError(503, 'DIALOGUE_UNAVAILABLE', 'Voice dialogue is not configured.')
    url = config.dialogue_ws_url + ('&' if '?' in config.dialogue_ws_url else '?') + urlencode({'model': config.dialogue_model})
    # Unlike httpx, websockets also reads OS-level proxy settings. A system SOCKS
    # proxy without python-socks installed would fail here instead of connecting.
    return connect(url, additional_headers={'Authorization': 'Bearer ' + config.dialogue_api_key.get_secret_value()},
        open_timeout=15, max_size=4 * 1024 * 1024, ping_interval=20, ping_timeout=20, proxy=None)


def claim(collection_id, session_id):
    token = uuid7()
    with Session(get_engine()) as db, db.begin():
        session = db.scalar(select(DialogueSession).where(DialogueSession.id == session_id,
            DialogueSession.collection_id == collection_id).with_for_update())
        if not session or session.status == 'finished':
            raise DomainError(409, 'DIALOGUE_FINISHED', 'Dialogue has already ended.')
        if session.connection_id and session.lease_until and session.lease_until > utcnow():
            raise DomainError(409, 'DIALOGUE_BUSY', 'Dialogue is open in another connection.')
        session.connection_id, session.lease_until, session.status = token, utcnow() + timedelta(seconds=60), 'active'
        data = session_data(db, session)
        practice = voice_practice(session.context, session.scenario)
    return token, data, practice


def update_lease(collection_id, session_id, token):
    with Session(get_engine()) as db, db.begin():
        result = db.execute(update(DialogueSession).where(DialogueSession.id == session_id,
            DialogueSession.collection_id == collection_id, DialogueSession.connection_id == token,
            DialogueSession.status == 'active').values(lease_until=utcnow() + timedelta(seconds=60)))
        if not result.rowcount:
            raise DomainError(409, 'DIALOGUE_BUSY', 'Dialogue connection is no longer active.')


def save_turn(collection_id, session_id, token, item_id, role, text):
    if not text.strip() or len(text) > 16000 or not item_id or len(item_id) > 200:
        raise DomainError(502, 'DIALOGUE_TRANSCRIPT_FAILED', 'A complete transcript was not received.')
    with Session(get_engine()) as db, db.begin():
        session = db.scalar(select(DialogueSession).where(DialogueSession.id == session_id,
            DialogueSession.collection_id == collection_id, DialogueSession.connection_id == token).with_for_update())
        if not session or session.status != 'active':
            raise DomainError(409, 'DIALOGUE_FINISHED', 'Dialogue has ended.')
        old = db.scalar(select(DialogueTurn).where(DialogueTurn.session_id == session.id,
            DialogueTurn.provider_item_id == item_id, DialogueTurn.role == role))
        if old:
            return {'id': str(old.id), 'role': old.role, 'text': old.text}, session.user_turns
        if role == 'user':
            session.user_turns += 1
        turn = DialogueTurn(collection_id=collection_id, session_id=session_id,
            provider_item_id=item_id, role=role, text=text.strip())
        db.add(turn); db.flush()
        return {'id': str(turn.id), 'role': role, 'text': turn.text}, session.user_turns


def prefetch_translation(collection_id, session_id, turn_id, text):
    """Generate Chinese right after a teacher turn so a later click never waits.

    Failures are ignored on purpose: the translation endpoint still generates on demand.
    """
    try:
        chinese = Translation.model_validate(dialogue_api.planner('translation', {'text': text})).chinese
        with Session(get_engine()) as db, db.begin():
            db.execute(update(DialogueTurn).where(DialogueTurn.id == UUID(str(turn_id)),
                DialogueTurn.collection_id == collection_id, DialogueTurn.session_id == session_id,
                DialogueTurn.translation_zh.is_(None)).values(translation_zh=chinese))
    except Exception:
        return


def release(collection_id, session_id, token, reason=None):
    with Session(get_engine()) as db, db.begin():
        db.execute(update(DialogueSession).where(DialogueSession.id == session_id,
            DialogueSession.collection_id == collection_id, DialogueSession.connection_id == token).values(
                connection_id=None, lease_until=None, status='finished' if reason else 'interrupted', finish_reason=reason))


async def bridge(browser, provider, collection_id, session_id, token, data, practice):
    config = get_settings()
    recording = pending_input = responding = False
    audio_bytes = 0
    assistant_text = ''
    user_turns = data['user_turns']
    ending = None
    turn_deadline = time.monotonic() + 45
    ready = False
    completed = False
    closing_requested = False
    prompt = instructions(data['scenario'], practice)

    async def send(value):
        await provider.send(json.dumps(value))

    async def respond(extra=None):
        nonlocal responding, assistant_text, turn_deadline
        turn_deadline = time.monotonic() + 60
        responding, assistant_text = True, ''
        await send({'type': 'response.create', 'response': {'instructions': prompt + ('\n' + extra if extra else '')}})

    async def request_closing():
        nonlocal closing_requested
        closing_requested = True
        await send({'type': 'session.update', 'session': {'tools': []}})
        # Control input represents the explicit Finish click, never a learner answer.
        await send({'type': 'conversation.item.create', 'item': {'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': 'I would like to finish this practice now. Please give me a brief teacher closing, without another question.'}]}})
        await respond('The learner chose to stop. Give a brief teacher closing based only on what they actually said. Do not ask another question or call a tool.')

    async def from_browser():
        nonlocal recording, pending_input, audio_bytes, completed, turn_deadline, user_turns, ending
        while True:
            message = await browser.receive_json()
            kind = message.get('type')
            if kind == 'end':
                if ending:
                    continue
                ending = 'user_ended'
                recording = False
                await send({'type': 'input_audio_buffer.clear'})
                if responding:
                    # Do not manufacture a partial turn or overlap two provider responses.
                    continue
                if not pending_input:
                    await request_closing()
            elif kind in ('audio_begin', 'text'):
                if not ready or responding or pending_input or recording or ending:
                    raise DomainError(409, 'DIALOGUE_NOT_READY', 'Wait for the agent to finish.')
                if kind == 'text':
                    text = message.get('text')
                    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                        raise DomainError(422, 'DIALOGUE_TEXT_INVALID', 'Use a short English reply.')
                    item_id = 'text-' + str(uuid7())
                    turn, user_turns = save_turn(collection_id, session_id, token, item_id, 'user', text)
                    await send({'type': 'conversation.item.create', 'item': {'id': item_id, 'type': 'message',
                        'role': 'user', 'content': [{'type': 'input_text', 'text': text.strip()}]}})
                    await browser.send_json({'type': 'turn', 'turn': turn, 'user_turns': user_turns})
                    await respond('This is the last turn. Give a brief, honest teacher closing without another question.' if ending else None)
                else:
                    recording, audio_bytes = True, 0
                    await send({'type': 'input_audio_buffer.clear'})
            elif kind == 'audio':
                if not recording or not isinstance(message.get('data'), str) or len(message['data']) > 65536:
                    raise DomainError(422, 'DIALOGUE_AUDIO_INVALID', 'Audio format is invalid.')
                try:
                    chunk = base64.b64decode(message['data'], validate=True)
                except (ValueError, binascii.Error):
                    raise DomainError(422, 'DIALOGUE_AUDIO_INVALID', 'Audio format is invalid.') from None
                audio_bytes += len(chunk)
                if len(chunk) % 2 or audio_bytes > MAX_AUDIO_BYTES:
                    raise DomainError(422, 'DIALOGUE_AUDIO_LIMIT', 'Please keep each turn under 30 seconds.')
                await send({'type': 'input_audio_buffer.append', 'audio': message['data']})
            elif kind == 'commit':
                if not recording or audio_bytes < 3200:
                    recording, pending_input = False, False
                    turn_deadline = None
                    await browser.send_json({'type': 'ready', 'user_turns': user_turns})
                    await browser.send_json({'type': 'notice', 'text': '没有听清，请再说一次。'})
                    continue
                recording, pending_input = False, True
                turn_deadline = time.monotonic() + 45
                await send({'type': 'input_audio_buffer.commit'})
            else:
                raise DomainError(422, 'DIALOGUE_EVENT_INVALID', 'Unsupported dialogue event.')

    async def from_provider():
        nonlocal ready, recording, pending_input, responding, assistant_text, user_turns, ending, completed, turn_deadline
        async for raw in provider:
            event = json.loads(raw)
            kind = event.get('type', '')
            if kind == 'session.created':
                await send({'type': 'session.update', 'session': {
                    'modalities': ['text', 'audio'], 'turn_detection': None,
                    'audio': {'input': {'format': {'type': 'pcm', 'sample_rate': 16000}},
                              'output': {'voice': config.dialogue_voice, 'format': {'type': 'pcm', 'sample_rate': 24000}}},
                    'input_audio_transcription': {'model': config.dialogue_asr_model},
                    'instructions': prompt,
                    'tools': [{'type': 'function', 'name': 'finish_scenario',
                        'description': 'Call after roleplay and a brief teacher closing, only when every communicative goal has been achieved. A recap or teacher example does not count.',
                        'parameters': {'type': 'object', 'properties': {'goal_ids': {'type': 'array', 'items': {'type': 'string'}}},
                            'required': ['goal_ids'], 'additionalProperties': False}}],
                }})
            elif kind == 'session.updated' and not ready:
                ready = True
                # Some realtime models require a user item before the first response. This is the
                # explicit Start click, not a learner answer; never persist/count it as a turn.
                await send({'type': 'conversation.item.create', 'item': {'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'Start my English practice conversation using the supplied lesson evidence. Ask me for a brief recap first; do not invent my recap.'}]}})
                for turn in data['turns']:
                    content_type = 'input_text' if turn['role'] == 'user' else 'output_text'
                    await send({'type': 'conversation.item.create', 'item': {'type': 'message', 'role': turn['role'],
                        'content': [{'type': content_type, 'text': turn['text']}]}})
                await browser.send_json({'type': 'connected', 'session': data, 'output_sample_rate': 24000})
                if not data['turns']:
                    await respond()
                elif ending:
                    await respond('This is the final turn. Give a brief teacher closing in English without another question.')
                elif data['turns'][-1]['role'] == 'user':
                    await respond('Continue from the saved conversation. The previous teacher response was interrupted; do not restart the introduction.')
                else:
                    turn_deadline = None
                    await browser.send_json({'type': 'ready', 'user_turns': user_turns})
            elif kind in ('conversation.item.input_audio_transcription.delta',
                          'conversation.item.input_audio_transcription.text'):
                if not (recording or pending_input):
                    continue
                # Committed prefix plus the in-flight suffix form the live transcript.
                partial = (str(event.get('text') or '') + str(event.get('stash') or '')).strip()
                if partial:
                    await browser.send_json({'type': 'transcript_partial', 'text': partial})
            elif kind == 'conversation.item.input_audio_transcription.completed':
                if not pending_input:
                    continue
                transcript = re.sub(r'\s*。\s*$', '', str(event.get('transcript') or '')).strip()
                pending_input, turn_deadline = False, None
                if not transcript:
                    await browser.send_json({'type': 'ready', 'user_turns': user_turns})
                    await browser.send_json({'type': 'notice', 'text': '没有听清，请再说一次。'})
                    continue
                turn, user_turns = save_turn(collection_id, session_id, token, event.get('item_id'), 'user', transcript)
                await browser.send_json({'type': 'turn', 'turn': turn, 'user_turns': user_turns})
                if ending in ('user_ended', 'time_limit'):
                    await request_closing()
                else:
                    await respond('This is the final turn. Give a brief, honest teacher closing in English without another question.' if ending else None)
            elif kind in ('response.audio.delta', 'response.output_audio.delta'):
                await browser.send_json({'type': 'audio', 'data': event['delta']})
            elif kind in ('response.audio_transcript.delta', 'response.output_audio_transcript.delta', 'response.text.delta'):
                assistant_text += event.get('delta', '')
                await browser.send_json({'type': 'message_delta', 'text': event.get('delta', '')})
            elif kind == 'response.function_call_arguments.done':
                try:
                    args = json.loads(event.get('arguments', '{}'))
                    goal_ids = {g['id'] for g in data['scenario']['goals']}
                    valid = event.get('name') == 'finish_scenario' and set(args.get('goal_ids', [])) == goal_ids and user_turns > 0
                except (TypeError, ValueError):
                    valid = False
                if valid:
                    ending = ending or 'task_completed'
                await send({'type': 'conversation.item.create', 'item': {'type': 'function_call_output',
                    'call_id': event['call_id'], 'output': json.dumps({'accepted': valid})}})
            elif kind == 'response.done':
                response = event.get('response', {})
                if response.get('status') != 'completed':
                    raise DomainError(502, 'DIALOGUE_RESPONSE_FAILED', 'The voice response was interrupted. Please reconnect.')
                has_spoken_reply = bool(assistant_text.strip())
                if has_spoken_reply:
                    item_id = response.get('id')
                    turn, _ = save_turn(collection_id, session_id, token, item_id, 'assistant', assistant_text)
                    await browser.send_json({'type': 'turn', 'turn': turn, 'user_turns': user_turns})
                    # Warm the Chinese translation off the critical path so a click is instant.
                    asyncio.create_task(asyncio.to_thread(
                        prefetch_translation, collection_id, session_id, turn['id'], turn['text']))
                    assistant_text = ''
                if ending in ('user_ended', 'time_limit') and not closing_requested:
                    await request_closing()
                elif any(i.get('type') == 'function_call' for i in response.get('output', [])) and not (ending and has_spoken_reply):
                    await respond('Close briefly as the teacher in English without another question. Do not call finish_scenario again.' if ending else 'Continue the conversation naturally; the communicative task is not yet finished.')
                elif ending:
                    completed = True
                    release(collection_id, session_id, token, ending)
                    await browser.send_json({'type': 'ended', 'reason': ending})
                    return
                else:
                    responding = False
                    turn_deadline = None
                    await browser.send_json({'type': 'ready', 'user_turns': user_turns})
            elif kind == 'error' or kind.endswith('transcription.failed'):
                detail = event.get('error') if isinstance(event.get('error'), dict) else {}
                message = str(detail.get('message') or event.get('message') or '')
                lowered = message.lower()
                too_long = 'exceeded maximum duration' in lowered
                if (kind.endswith('transcription.failed') or 'buffer too small' in lowered
                        or 'no audio' in lowered or 'no speech' in lowered or too_long):
                    recording, pending_input, responding = False, False, False
                    turn_deadline = None
                    if too_long:
                        await send({'type': 'input_audio_buffer.clear'})
                    await browser.send_json({'type': 'ready', 'user_turns': user_turns})
                    await browser.send_json({'type': 'notice', 'text': '单次录音不能超过 30 秒，请说完后稍作停顿再提交。'
                        if too_long else '没有听清，请再说一次。'})
                    continue
                logger.warning('Dialogue provider error type=%s message=%s', detail.get('type'), message[:300])
                raise DomainError(502, 'DIALOGUE_PROVIDER_FAILED', 'Voice dialogue is unavailable. Please reconnect.')
        if not completed:
            raise DomainError(502, 'DIALOGUE_PROVIDER_FAILED', 'The voice connection closed. Please reconnect.')

    async def heartbeat():
        while True:
            await asyncio.sleep(10)
            if turn_deadline is not None and time.monotonic() > turn_deadline:
                raise DomainError(504, 'DIALOGUE_RESPONSE_TIMEOUT', 'The voice response timed out. Please reconnect.')
            update_lease(collection_id, session_id, token)

    async def stop_at_time_limit():
        """Close the conversation gracefully once the session budget is spent."""
        nonlocal ending
        await asyncio.sleep(SESSION_SECONDS)
        if ending or completed:
            return
        ending = 'time_limit'
        await send({'type': 'input_audio_buffer.clear'})
        if not (responding or pending_input):
            await request_closing()
        # Stay alive until the bridge ends so the closing response can complete.
        await asyncio.Event().wait()

    tasks = [asyncio.create_task(fn()) for fn in (from_browser, from_provider, heartbeat, stop_at_time_limit)]
    try:
        done, _ = await asyncio.wait(tasks, timeout=900, return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise DomainError(408, 'DIALOGUE_TIMEOUT', 'Dialogue timed out. Please reconnect.')
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if not completed:
            release(collection_id, session_id, token)


@router.websocket('/sessions/{session_id}/ws')
async def voice_session(browser: WebSocket, session_id: UUID):
    token = collection_id = None
    accepted = False
    try:
        enabled()
        request = Request({**browser.scope, 'type': 'http', 'method': 'GET'})
        auth.require_origin(request)
        with Session(get_engine()) as db, db.begin():
            collection = auth.identity(request, db)
            ContentRepository(db, collection).get(DialogueSession, session_id)
            collection_id = collection.id
        await browser.accept()
        accepted = True
        token, data, practice = claim(collection_id, session_id)
        async with provider_connection() as provider:
            await bridge(browser, provider, collection_id, session_id, token, data, practice)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else 'DIALOGUE_CONNECTION_FAILED'
        logger.exception('Dialogue voice session failed: session=%s code=%s', session_id, code)
        message = ('语音服务暂时不可用，请稍后重新连接。' if code == 'DIALOGUE_PROVIDER_FAILED'
            else '语音连接失败，请检查网络或代理后重新连接。' if code == 'DIALOGUE_CONNECTION_FAILED'
            else '语音对话未完成，请重新连接。')
        try:
            await browser.send_json({'type': 'error', 'code': code, 'message': message})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if token:
            # bridge releases its own lease; this only catches handshake failures.
            release(collection_id, session_id, token)
        try:
            await browser.close(code=1000 if accepted else 1008)
        except (RuntimeError, WebSocketDisconnect):
            pass
