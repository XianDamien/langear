"""Authorized, read-only practice tools and independent Dialogue persistence."""
import json
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from core import auth
from core.config import get_settings
from core.db import get_db
from core.errors import DomainError, missing
from core.models import Attempt, Card, Deck, DialogueSession, DialogueTurn
from core.repository import ContentRepository
from core.dialogue_schemas import DialogueCreate, Scenario
from core.review import QUEUES, RUNTIME_LOCK, ReviewService

router = APIRouter(prefix='/api/v1/dialogue')


def enabled():
    config = get_settings()
    if not config.dialogue_enabled:
        raise DomainError(503, 'DIALOGUE_UNAVAILABLE', 'Dialogue is not configured.')
    return config


def practice_context(db, collection, deck_id, queue_id, attempt_ids):
    """The caller's Collection is injected by auth, never a model argument."""
    repo = ContentRepository(db, collection)
    deck = repo.get(Deck, deck_id)
    ids = set(attempt_ids)
    if len(ids) != len(attempt_ids):
        raise DomainError(422, 'DIALOGUE_ATTEMPTS_INVALID', 'Practice evidence contains duplicates.')
    submitted_attempts = list(db.scalars(select(Attempt).where(
        Attempt.collection_id == collection.id,
        Attempt.id.in_(ids),
        Attempt.rating.is_not(None),
    )))
    if len(submitted_attempts) != len(ids):
        missing()
    with RUNTIME_LOCK:
        queue = QUEUES.get(collection.id)
        if not queue or queue.id != queue_id or queue.scope['deck_id'] != deck.id:
            raise DomainError(409, 'DIALOGUE_ROUND_EXPIRED', 'The practice round has expired. Please refresh the lesson.')
        if ReviewService(db, collection).next(queue_id)['card'] is not None:
            raise DomainError(409, 'DIALOGUE_ROUND_INCOMPLETE', 'Finish the available cards before starting the dialogue.')
        round_started_at = queue.started_at or queue.expires_at - timedelta(hours=2)
        round_attempts = list(db.scalars(select(Attempt).where(
            Attempt.collection_id == collection.id,
            Attempt.rated_at >= round_started_at,
            Attempt.rating.is_not(None),
        ).order_by(Attempt.rated_at, Attempt.id)))
        round_ids = {attempt.id for attempt in round_attempts}
        if not ids or ids != round_ids:
            raise DomainError(409, 'DIALOGUE_ROUND_EVIDENCE_MISMATCH', 'Refresh the lesson to prepare this practice round.')
        attempts = round_attempts
    deck_ids = repo.descendants(deck.id)
    # Validate membership with current owned Cards; content itself uses immutable Attempt snapshots.
    cards = {c.id for c in db.scalars(select(Card).where(Card.collection_id == collection.id, Card.deck_id.in_(deck_ids)))}
    if any(a.card_id not in cards for a in attempts):
        missing()
    # Cap prompt size without mutating original feedback or grading data.
    sources = []
    for a in attempts[-40:]:
        data = {'source_type': 'card_feedback', 'deck_id': str(deck.id), 'card_id': str(a.card_id), 'attempt_id': str(a.id),
            'note': a.note_snapshot, 'answer': a.answer_snapshot, 'input': a.input_snapshot,
            'transcription': a.asr_result, 'feedback': a.ai_feedback, 'feedback_status': a.ai_status}
        # Audio object keys and signed URLs are not required by the voice model.
        for key in ('note', 'answer', 'input'):
            data[key] = {k: v[:6000] for k, v in data[key].items() if isinstance(v, str) and k not in ('reference_audio', 'image', 'media_asset_id', 'temporary_media_asset_id', 'realtime_session_id')}
        for key in ('feedback', 'transcription'):
            if len(json.dumps(data[key], ensure_ascii=False)) > 12000:
                data[key] = {'omitted': True, 'reason': 'context_budget'}
        sources.append(data)
    while len(json.dumps(sources, ensure_ascii=False)) > 120000 and len(sources) > 1:
        sources.pop(0)
    return {'deck_id': str(deck.id), 'deck_name': deck.name, 'sources': sources,
            'practice_attempt_ids': sorted(map(str, ids)), 'omitted_count': len(attempts) - len(sources)}


def build_scenario(context):
    """Assemble a stable roleplay locally from owned card snapshots; no model request."""
    expressions = []
    seen = set()
    for source in reversed(context['sources']):
        note = source['note']
        english = (note.get('english') or note.get('word') or source['answer'].get('english') or '').strip()
        if not english or english in seen:
            continue
        seen.add(english)
        expressions.append({'english': english[:2000],
            'meaning_zh': (note.get('chinese') or note.get('meaning') or '')[:2000],
            'source': {'attempt_id': source['attempt_id'], 'card_id': source['card_id']}})
        if len(expressions) == 3:
            break
    return Scenario(title=f"{context['deck_name'][:1800]} · 情景对话",
        setup_zh='你正在和一位英语朋友聊天。围绕刚练过的内容分享想法，并试着用上学到的表达。',
        learner_role='Yourself', agent_role='An English-speaking friend',
        goals=[{'id': 'use_material', 'description_zh': '用刚练过的内容表达想法，并回应朋友的问题。'}],
        target_expressions=expressions).model_dump(mode='json')


def session_data(db, session):
    turns = list(db.scalars(select(DialogueTurn).where(DialogueTurn.session_id == session.id,
        DialogueTurn.collection_id == session.collection_id).order_by(DialogueTurn.created_at, DialogueTurn.id)))
    return {'id': str(session.id), 'deck_id': str(session.deck_id), 'scenario': session.scenario,
        'status': session.status, 'finish_reason': session.finish_reason, 'user_turns': session.user_turns,
        'max_user_turns': 8, 'turns': [{'id': str(t.id), 'role': t.role, 'text': t.text} for t in turns]}


def service(collection=Depends(auth.identity), db=Depends(get_db, scope='function')):
    return db, collection, ContentRepository(db, collection)


@router.get('/availability')
def availability(context=Depends(service)):
    config = get_settings()
    return {'enabled': bool(config.dialogue_enabled and config.dialogue_api_key)}


@router.post('/sessions', status_code=201)
def create_session(body: DialogueCreate, context=Depends(service)):
    if not enabled().dialogue_api_key:
        raise DomainError(503, 'DIALOGUE_UNAVAILABLE', 'Voice dialogue is not configured.')
    db, collection, repo = context
    existing = db.scalar(select(DialogueSession).where(DialogueSession.collection_id == collection.id,
        DialogueSession.entry_key == body.entry_key))
    if existing:
        if existing.deck_id != body.deck_id or set(existing.context['practice_attempt_ids']) != set(map(str, body.attempt_ids)):
            raise DomainError(409, 'DIALOGUE_ENTRY_CONFLICT', 'This entry belongs to another practice round.')
        return session_data(db, existing)
    bound = practice_context(db, collection, body.deck_id, body.review_queue_id, body.attempt_ids)
    scenario = build_scenario(bound)
    statement = insert(DialogueSession).values(collection_id=collection.id, entry_key=body.entry_key,
        deck_id=body.deck_id, context=bound, scenario=scenario).on_conflict_do_nothing(index_elements=['collection_id','entry_key'])
    db.execute(statement)
    existing = db.scalar(select(DialogueSession).where(DialogueSession.collection_id == collection.id,
        DialogueSession.entry_key == body.entry_key))
    if existing.deck_id != body.deck_id or set(existing.context['practice_attempt_ids']) != set(map(str, body.attempt_ids)):
        raise DomainError(409, 'DIALOGUE_ENTRY_CONFLICT', 'This entry belongs to another practice round.')
    return session_data(db, existing)


@router.get('/sessions/{session_id}')
def get_session(session_id: UUID, context=Depends(service)):
    db, _, repo = context
    return session_data(db, repo.get(DialogueSession, session_id))


@router.post('/sessions/{session_id}/finish')
def finish_session(session_id: UUID, context=Depends(service)):
    db, _, repo = context
    session = repo.get(DialogueSession, session_id)
    if session.status == 'active':
        raise DomainError(409, 'DIALOGUE_ACTIVE', 'End the voice connection first.')
    if session.status != 'finished':
        session.status, session.finish_reason = 'finished', 'user_ended'
    return session_data(db, session)
