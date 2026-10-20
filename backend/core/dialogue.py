"""Authorized, read-only practice tools and independent Dialogue persistence."""
import json
import re
from datetime import timedelta
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from core import auth
from core.config import get_settings
from core.db import get_db
from core.errors import DomainError, missing
from core.models import Attempt, Card, Deck, DialogueReview, DialogueSession, DialogueTurn
from core.repository import ContentRepository
from core.dialogue_schemas import DialogueCreate, Scenario, Review, Translation
from core.review import QUEUES, RUNTIME_LOCK, ReviewService

router = APIRouter(prefix='/api/v1/dialogue')

# One voice connection may run this long before the teacher closes the conversation.
SESSION_SECONDS = 600


def enabled():
    config = get_settings()
    if not config.dialogue_enabled:
        raise DomainError(503, 'DIALOGUE_UNAVAILABLE', 'Dialogue is not configured.')
    return config


def planner(kind, context):
    config = enabled()
    if not config.dialogue_agent_token:
        raise DomainError(503, 'DIALOGUE_UNAVAILABLE', 'Dialogue is not configured.')
    try:
        response = httpx.post(config.dialogue_agent_url.rstrip('/') + '/' + kind,
            headers={'Authorization': 'Bearer ' + config.dialogue_agent_token.get_secret_value()},
            json=context, timeout=60)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise DomainError(502, 'DIALOGUE_AGENT_FAILED', 'Please retry preparing the dialogue.') from None


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
            'transcription': a.asr_result, 'feedback': a.ai_feedback, 'feedback_status': a.ai_status,
            'rating': a.rating}
        # Audio object keys and signed URLs are not required by the planning model.
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


def validate_scenario(value, context):
    try:
        scenario = Scenario.model_validate(value).model_dump(mode='json')
        valid = {(s['attempt_id'], s['card_id']): s for s in context['sources']}
        stop_words = {'about', 'after', 'again', 'also', 'and', 'are', 'but', 'for', 'from', 'have', 'how', 'into', 'please', 'that', 'the', 'their', 'there', 'this', 'what', 'when', 'where', 'which', 'with', 'would', 'you', 'your'}
        for expression in scenario['target_expressions']:
            source = valid.get((expression['source']['attempt_id'], expression['source']['card_id']))
            if source is None:
                raise ValueError('Unknown source')
            source_text = json.dumps([value for key in ('note', 'answer') for value in source[key].values()], ensure_ascii=False).lower()
            terms = {term.rstrip('s') for term in re.findall(r'[a-z]{3,}', expression['english'].lower()) if term not in stop_words}
            source_terms = {term.rstrip('s') for term in re.findall(r'[a-z]{3,}', source_text)}
            if not terms or not terms.intersection(source_terms):
                raise ValueError('Expression is not grounded in its source')
        ids = [g['id'] for g in scenario['goals']]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate goal')
        return scenario
    except (ValidationError, ValueError, TypeError):
        raise DomainError(502, 'DIALOGUE_AGENT_FAILED', 'Scenario evidence is invalid. Please retry.') from None


def session_data(db, session):
    turns = list(db.scalars(select(DialogueTurn).where(DialogueTurn.session_id == session.id,
        DialogueTurn.collection_id == session.collection_id).order_by(DialogueTurn.created_at, DialogueTurn.id)))
    review = db.scalar(select(DialogueReview).where(DialogueReview.session_id == session.id,
        DialogueReview.collection_id == session.collection_id))
    return {'id': str(session.id), 'deck_id': str(session.deck_id), 'scenario': session.scenario,
        'status': session.status, 'finish_reason': session.finish_reason, 'user_turns': session.user_turns,
        'time_limit_seconds': SESSION_SECONDS,
        'turns': [{'id': str(t.id), 'role': t.role, 'text': t.text, 'translation_zh': t.translation_zh} for t in turns],
        'review': review.result if review else None}


def service(collection=Depends(auth.identity), db=Depends(get_db, scope='function')):
    return db, collection, ContentRepository(db, collection)


@router.get('/availability')
def availability(context=Depends(service)):
    config = get_settings()
    return {'enabled': bool(config.dialogue_enabled and config.dialogue_agent_token and config.dialogue_api_key)}


@router.post('/sessions', status_code=201)
def create_session(body: DialogueCreate, context=Depends(service)):
    enabled()
    db, collection, repo = context
    existing = db.scalar(select(DialogueSession).where(DialogueSession.collection_id == collection.id,
        DialogueSession.entry_key == body.entry_key))
    if existing:
        if existing.deck_id != body.deck_id or set(existing.context['practice_attempt_ids']) != set(map(str, body.attempt_ids)):
            raise DomainError(409, 'DIALOGUE_ENTRY_CONFLICT', 'This entry belongs to another practice round.')
        return session_data(db, existing)
    bound = practice_context(db, collection, body.deck_id, body.review_queue_id, body.attempt_ids)
    scenario = validate_scenario(planner('scenario', bound), bound)
    statement = insert(DialogueSession).values(collection_id=collection.id, entry_key=body.entry_key,
        deck_id=body.deck_id, context=bound, scenario=scenario).on_conflict_do_nothing(index_elements=['collection_id','entry_key'])
    db.execute(statement)
    existing = db.scalar(select(DialogueSession).where(DialogueSession.collection_id == collection.id,
        DialogueSession.entry_key == body.entry_key))
    if existing.deck_id != body.deck_id or set(existing.context['practice_attempt_ids']) != set(map(str, body.attempt_ids)):
        raise DomainError(409, 'DIALOGUE_ENTRY_CONFLICT', 'This entry belongs to another practice round.')
    return session_data(db, existing)


@router.get('/sessions')
def list_sessions(context=Depends(service)):
    """Collection-scoped dialogue history; never exposes another learner's turns."""
    db, collection, _ = context
    rows = db.execute(
        select(DialogueSession, Deck.name)
        .join(Deck, Deck.id == DialogueSession.deck_id)
        .where(DialogueSession.collection_id == collection.id)
        .order_by(DialogueSession.created_at.desc(), DialogueSession.id.desc())
    ).all()
    reviewed = set(
        db.scalars(
            select(DialogueReview.session_id).where(
                DialogueReview.collection_id == collection.id
            )
        )
    )
    return {
        'sessions': [
            {
                'id': str(session.id),
                'deck_id': str(session.deck_id),
                'deck_name': deck_name,
                'title': (session.scenario or {}).get('title'),
                'status': session.status,
                'user_turns': session.user_turns,
                'created_at': session.created_at.isoformat(),
                'has_review': session.id in reviewed,
            }
            for session, deck_name in rows
        ]
    }


@router.delete('/sessions/{session_id}', status_code=204)
def delete_session(session_id: UUID, context=Depends(service)):
    db, collection, repo = context
    session = repo.get(DialogueSession, session_id)
    db.execute(
        delete(DialogueReview).where(
            DialogueReview.collection_id == collection.id,
            DialogueReview.session_id == session.id,
        )
    )
    db.execute(
        delete(DialogueTurn).where(
            DialogueTurn.collection_id == collection.id,
            DialogueTurn.session_id == session.id,
        )
    )
    db.delete(session)
    db.flush()


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


def validate_review(value, session, turns):
    try:
        review = Review.model_validate(value).model_dump(mode='json')
        user_turns = {t['id']: t['text'] for t in turns if t['role'] == 'user'}
        goals = [g['id'] for g in session.scenario['goals']]
        if sorted(g['goal_id'] for g in review['goals']) != sorted(goals):
            raise ValueError('Invalid goals')
        for goal in review['goals']:
            if not set(goal['evidence_turn_ids']) <= user_turns.keys() or (goal['completed'] and not goal['evidence_turn_ids']):
                raise ValueError('Invalid goal evidence')
        for expression in review['used_expressions']:
            if not set(expression['evidence_turn_ids']) <= user_turns.keys():
                raise ValueError('Invalid expression evidence')
            # Only credit an expression present in a learner turn; normalize punctuation and whitespace.
            normalize = lambda text: ' '.join(''.join(c.lower() if c.isalnum() else ' ' for c in text).split())
            if not any(normalize(expression['english']) in normalize(user_turns[t]) for t in expression['evidence_turn_ids']):
                raise ValueError('Expression was not used')
        valid = {(s['attempt_id'], s['card_id']) for s in session.context['sources']}
        if any((p['source']['attempt_id'], p['source']['card_id']) not in valid for p in review['practice_points']):
            raise ValueError('Invalid advice source')
        return review
    except (ValidationError, ValueError, TypeError):
        raise DomainError(502, 'DIALOGUE_AGENT_FAILED', 'Review evidence is invalid. Please retry.') from None


@router.post('/sessions/{session_id}/review')
def create_review(session_id: UUID, context=Depends(service)):
    db, collection, repo = context
    session = repo.get(DialogueSession, session_id)
    if session.status != 'finished':
        raise DomainError(409, 'DIALOGUE_NOT_FINISHED', 'Finish the dialogue before reviewing it.')
    data = session_data(db, session)
    if data['review'] is None:
        result = validate_review(planner('review', {'practice': session.context, 'scenario': session.scenario,
            'turns': data['turns'], 'finish_reason': session.finish_reason}), session, data['turns'])
        db.execute(insert(DialogueReview).values(collection_id=collection.id, session_id=session.id, result=result)
            .on_conflict_do_nothing(index_elements=['session_id']))
    return session_data(db, session)


@router.post('/sessions/{session_id}/turns/{turn_id}/translation')
def translate_turn(session_id: UUID, turn_id: UUID, context=Depends(service)):
    db, collection, repo = context
    repo.get(DialogueSession, session_id)
    turn = repo.get(DialogueTurn, turn_id)
    if turn.session_id != session_id:
        missing()
    # Pre-generated Chinese makes this a cache read; the planner only runs once per turn.
    if turn.translation_zh:
        return {'chinese': turn.translation_zh}
    try:
        # The client selects an owned saved turn, never arbitrary model input or another user's text.
        translation = Translation.model_validate(planner('translation', {'text': turn.text}))
    except ValidationError:
        raise DomainError(502, 'DIALOGUE_AGENT_FAILED', 'Translation is unavailable. Please retry.') from None
    turn.translation_zh = translation.chinese
    return translation.model_dump()
