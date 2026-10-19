"""Transactional review application service and disposable, single-process queues.

Persistent learning facts live in Card/Attempt, not in the runtime queue. Collection
row locks serialize all writes across workers; a missing local queue must rebuild.
"""

import json
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from hashlib import sha256
from threading import RLock
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from uuid6 import uuid7

from core.content import ContentService, present
from core.errors import DomainError
from core.models import (
    Attempt,
    Card,
    CardTemplate,
    Deck,
    MediaAsset,
    Note,
    ProcessingOutbox,
    ReviewReceipt,
)
from core.scheduling import (
    DEFAULT_SCHEDULING,
    SCHEDULE_FIELDS,
    ancestry,
    day_start,
    effective,
    options,
    ordered,
    restored_queue,
    schedule,
    study_day,
)


@dataclass
class RuntimeQueue:
    id: UUID
    scope: dict
    order: list
    day: int
    config_stamp: str
    expires_at: datetime
    started_at: datetime | None = None
    current: UUID | None = None
    token: UUID | None = None
    undo: dict | None = None


QUEUES = {}
RUNTIME_LOCK = RLock()
# Like Anki's default: use imminent learning cards once ordinary work runs out.
LEARN_AHEAD = timedelta(minutes=20)


def conflict(code, message="Review state changed; rebuild or reload the current card."):
    raise DomainError(409, code, message)


def dictation(expected, actual):
    def normalize(value):
        return unicodedata.normalize(
            "NFKC", value.replace("\r\n", "\n").replace("\r", "\n")
        ).translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))

    expected, actual = normalize(expected), normalize(actual)
    differences = []
    for op, a, b, c, d in SequenceMatcher(
        None, expected, actual, autojunk=False
    ).get_opcodes():
        if op == "equal":
            continue
        left, right = expected[a:b], actual[c:d]
        category = (
            "capitalization"
            if left and right and left.lower() == right.lower()
            else "spacing"
            if all(ch.isspace() for ch in left + right)
            else "punctuation"
            if all(unicodedata.category(ch).startswith("P") for ch in left + right)
            else "word"
        )
        differences.append(
            {
                "category": category,
                "expected": left,
                "actual": right,
                "expected_range": {"start": a, "end": b},
                "actual_range": {"start": c, "end": d},
            }
        )
    return {
        "kind": "dictation_text_diff",
        "evaluator_version": "1",
        "exact_match": expected == actual,
        "normalized_expected": expected,
        "normalized_actual": actual,
        "differences": differences,
    }


class ReviewService(ContentService):
    def __init__(self, db, collection):
        super().__init__(db, collection)
        self.collection = self.repo.lock()
        self.now = datetime.now(UTC)
        self.day = study_day(self.now, self.collection.timezone)
        self.decks = {
            d.id: d
            for d in db.scalars(select(Deck).where(Deck.collection_id == collection.id))
        }

    def config(self, card):
        return effective(
            self.collection, card.original_deck_id or card.deck_id, self.decks
        )

    def stamp(self):
        return sha256(
            repr(
                (
                    self.collection.timezone,
                    self.collection.scheduling_config,
                    sorted(
                        (str(d.id), str(d.parent_id), d.in_my_courses, d.scheduling_config)
                        for d in self.decks.values()
                    ),
                )
            ).encode()
        ).hexdigest()

    def queue(self, queue_id):
        q = QUEUES.get(self.collection.id)
        if (
            q is None
            or q.id != queue_id
            or q.expires_at <= self.now
            or q.day != self.day
            or q.config_stamp != self.stamp()
        ):
            conflict("QUEUE_EXPIRED")
        return q

    def restore_buried(self):
        for card in self.db.scalars(
            select(Card)
            .where(
                Card.collection_id == self.collection.id,
                Card.queue.in_(["buried_sibling", "buried_user"]),
                Card.buried_on_day < self.day,
            )
            .with_for_update()
        ):
            card.queue, card.buried_on_day = restored_queue(card), None
            card.schedule_revision += 1
        self.db.flush()

    def pending(self):
        return self.db.scalar(
            select(Attempt).where(
                Attempt.collection_id == self.collection.id, Attempt.rating.is_(None)
            )
        )

    def pending_for(self, scope):
        attempt = self.pending()
        if attempt is None:
            return None
        card = self.repo.get(Card, attempt.card_id)
        template = self.db.get(CardTemplate, card.card_template_id)
        ids = (
            self.repo.descendants(scope["deck_id"])
            if scope["include_descendants"] else [scope["deck_id"]]
        )
        templates = scope.get("card_template_keys")
        imported = scope.get("exclude_imported") and self.repo.get(
            Note, card.note_id
        ).guid.startswith("legacy:")
        if card.deck_id not in ids or (templates and template.key not in templates) or imported:
            raise DomainError(
                409, "PENDING_REVIEW_OUTSIDE_SCOPE",
                "Finish the saved answer in its own deck and practice type.",
                {
                    "deck_id": str(card.deck_id),
                    "deck_name": " / ".join(
                        self.decks[key].name
                        for key in reversed(ancestry(card.deck_id, self.decks))
                    ),
                    "card_template_key": template.key,
                },
            )
        return attempt

    def in_scope(self, scope):
        root = self.repo.get(Deck, scope["deck_id"])
        ids = (
            self.repo.descendants(root.id)
            if scope["include_descendants"]
            else [root.id]
        )
        query = select(Card).where(
            Card.collection_id == self.collection.id, Card.deck_id.in_(ids)
        )
        if scope.get("exclude_imported"):
            query = query.join(Note, Card.note_id == Note.id).where(~Note.guid.startswith("legacy:"))
        if scope.get("card_template_keys"):
            query = query.join(
                CardTemplate, Card.card_template_id == CardTemplate.id
            ).where(CardTemplate.key.in_(scope["card_template_keys"]))
        cards = list(self.db.scalars(query))
        # Match the existing Card Picker: None means all, [] means no cards.
        return [card for card in cards if self.card_selected(card)]

    def card_selected(self, card):
        selected = self.decks[card.deck_id].scheduling_config.get("study_card_ids")
        return selected is None or str(card.id) in selected


    def build(self, body):
        self.restore_buried()
        scope = body.scope.model_dump()
        root = self.repo.get(Deck, scope["deck_id"])
        if root.kind == "filtered":
            raise DomainError(
                422,
                "FILTERED_DECK_NOT_READY",
                "Build Filtered Deck membership and order through the Filtered Deck service first.",
            )
        attempt = self.pending_for(scope)
        config = effective(self.collection, root.id, self.decks)
        cards = self.in_scope(scope)
        order = ordered(cards, self.collection, config, self.now, self.decks)
        q = RuntimeQueue(
            uuid7(),
            scope,
            [c.id for c in order],
            self.day,
            self.stamp(),
            self.now + timedelta(hours=2),
            started_at=self.now,
        )
        if attempt:
            q.current, q.token = attempt.card_id, attempt.review_token
        QUEUES[self.collection.id] = q
        return {
            "queue_id": q.id,
            "scope": q.scope,
            **self.counts(q),
            "current": self.next(q.id) if attempt else None,
        }

    def quota_path(self, deck_id):
        return [None] + (ancestry(deck_id, self.decks) if deck_id in self.decks else [])

    def consume(self, usage, deck_id, kind):
        if kind not in ("new", "review"):
            return
        for key in self.quota_path(deck_id):
            counts = usage.setdefault(key, {"new": 0, "review": 0})
            counts["review"] += 1
            counts["new"] += int(kind == "new")

    def usage(self):
        usage = {}
        for attempt in self.db.scalars(
            select(Attempt).where(
                Attempt.collection_id == self.collection.id,
                Attempt.rating.is_not(None),
                Attempt.rated_at >= day_start(self.day, self.collection.timezone),
            )
        ):
            self.consume(usage, attempt.quota_deck_id, attempt.quota_kind)
        return usage

    def capacity(self, card, usage):
        kind = card.queue
        if kind not in ("new", "review"):
            return True
        config = {**DEFAULT_SCHEDULING, **self.collection.scheduling_config}
        for key in self.quota_path(card.original_deck_id or card.deck_id):
            limits = (
                config
                if key is None
                else {
                    **config,
                    **{
                        k: v
                        for k, v in self.decks[key].scheduling_config.items()
                        if v is not None
                    },
                }
            )
            counts = usage.get(key, {"new": 0, "review": 0})
            if counts["review"] >= limits["review_limit"] or (
                kind == "new" and counts["new"] >= limits["new_limit"]
            ):
                return False
        return True

    def eligible(self, q, *, scoped_cards=None, usage=None, renderable_ids=None):
        cards = self.in_scope(q.scope) if scoped_cards is None else scoped_cards
        def can_render(card):
            return self.render(card)["renderable"] if renderable_ids is None else card.id in renderable_ids
        available = {
            c.id: c
            for c in cards
            if c.queue == "new"
            or c.queue == "learning"
            and c.due_at <= self.now
            or c.queue in ("review", "day_learning")
            and c.due_day <= self.day
        }
        fresh = ordered(
            list(available.values()),
            self.collection,
            effective(self.collection, q.scope["deck_id"], self.decks),
            self.now,
            self.decks,
        )
        order = (
            [c.id for c in fresh if c.queue == "learning"]
            + q.order
            + [c.id for c in fresh if c.id not in q.order]
        )
        if q.current in order:
            order = [q.current] + [i for i in order if i != q.current]
        seen = set()
        result = []
        usage = self.usage() if usage is None else deepcopy(usage)
        for card_id in order:
            if card_id not in seen and card_id in available:
                seen.add(card_id)
                card = available[card_id]
                if self.capacity(card, usage) and can_render(card):
                    result.append(card)
                    self.consume(
                        usage, card.original_deck_id or card.deck_id, card.queue
                    )
        # Keep the stored FSRS due time. Early learning is a queue policy, and
        # must never jump ahead of due cards or available new/review work.
        ahead = sorted(
            (c for c in cards if c.queue == "learning"
             and self.now < c.due_at <= self.now + LEARN_AHEAD),
            key=lambda c: (c.due_at, c.id),
        )
        result.extend(c for c in ahead if can_render(c))
        return result

    def counts(self, q, *, scoped_cards=None, usage=None, renderable_ids=None):
        all_cards = self.in_scope(q.scope) if scoped_cards is None else scoped_cards
        cards = self.eligible(q, scoped_cards=all_cards, usage=usage, renderable_ids=renderable_ids)
        future = [c.due_at for c in all_cards if c.queue == "learning" and c.due_at > self.now]
        return {
            "can_undo": bool(q.undo and not self.pending()),
            "next_due_at": min(future) if future else None,
            "empty_reason": None if cards else "no_cards" if not all_cards else "waiting" if future else "done_today",
            "new_remaining": sum(c.queue == "new" for c in cards),
            "review_remaining": sum(c.queue == "review" for c in cards),
            "learning_remaining": sum(
                c.queue in ("learning", "day_learning") for c in cards
            ),
        }

    def next(self, queue_id):
        q = self.queue(queue_id)
        pending = self.pending_for(q.scope)
        if pending:
            q.current, q.token = pending.card_id, pending.review_token
            card = self.repo.get(Card, pending.card_id)
            front = self.front(card)
            front["front"] = pending.front_snapshot
            return {
                "queue_id": q.id,
                "review_token": q.token,
                "card": front,
                **self.flipped(pending),
                **self.counts(q),
            }
        candidates = self.eligible(q)
        if q.current not in [c.id for c in candidates]:
            q.current = candidates[0].id if candidates else None
            q.token = uuid7() if candidates else None
        card = self.repo.get(Card, q.current) if q.current else None
        return {
            "queue_id": q.id,
            "review_token": q.token,
            "card": self.front(card) if card else None,
            **self.counts(q),
        }

    def front(self, card):
        data = self.render(card)
        return {
            key: data[key]
            for key in (
                "id",
                "note_id",
                "deck_id",
                "card_template_key",
                "card_schedule_revision",
                "front",
                "input_requirement",
            )
        }

    def attempt_data(self, attempt):
        return {
            key: getattr(attempt, key)
            for key in (
                "id",
                "card_id",
                "review_token",
                "note_snapshot",
                "front_snapshot",
                "back_snapshot",
                "answer_snapshot",
                "input_snapshot",
                "input_type",
                "media_asset_id",
                "rating",
                "rated_at",
                "asr_status",
                "asr_result",
                "ai_status",
                "ai_feedback",
                "deterministic_result",
                "card_schedule_revision",
                "previous_interval_days",
                "scheduled_interval_days",
                "review_kind",
                "fsrs_algorithm_version",
                "fsrs_config_version",
            )
        }

    def replay(self, key, operation, body):
        if key.version != 7:
            raise DomainError(
                422, "INVALID_IDEMPOTENCY_KEY", "Use a UUIDv7 Idempotency-Key."
            )
        fingerprint = sha256(
            json.dumps(
                jsonable_encoder(body), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        receipt = self.db.scalar(
            select(ReviewReceipt).where(
                ReviewReceipt.collection_id == self.collection.id,
                ReviewReceipt.key == key,
            )
        )
        if receipt and (
            receipt.operation != operation or receipt.payload_hash != fingerprint
        ):
            conflict("IDEMPOTENCY_KEY_REUSED")
        return receipt.response if receipt else None, fingerprint

    def receipt(self, key, operation, fingerprint, response):
        response = jsonable_encoder(response)
        self.db.add(
            ReviewReceipt(
                collection_id=self.collection.id,
                key=key,
                operation=operation,
                payload_hash=fingerprint,
                response=response,
            )
        )
        self.db.flush()
        return response

    def flip(self, queue_id, body, key):
        q = self.queue(queue_id)
        operation = "flip"
        replay, fingerprint = self.replay(key, operation, body.model_dump(exclude_none=True))
        if replay is not None:
            return replay
        attempt = self.db.scalar(
            select(Attempt).where(
                Attempt.collection_id == self.collection.id,
                Attempt.review_token == body.review_token,
            )
        )
        if attempt:
            if (
                attempt.card_id != body.card_id
                or attempt.input_snapshot != jsonable_encoder(body.input, exclude_none=True)
            ):
                conflict("REVIEW_TOKEN_REUSED")
            response = self.flipped(attempt)
        else:
            self.next(queue_id)
            if self.pending() or (q.current, q.token) != (
                body.card_id,
                body.review_token,
            ):
                conflict("REVIEW_TOKEN_INVALID")
            card = self.lock_card(body.card_id)
            rendered = self.render(card)
            if body.input.type != rendered["input_requirement"]["type"]:
                raise DomainError(
                    422, "INPUT_REQUIRED", "Input does not match the Card Template."
                )
            media = None
            transcription = None
            if body.input.type == "audio":
                media = self.repo.get(MediaAsset, body.input.temporary_media_asset_id)
                if (
                    media.scope != "private"
                    or media.kind != "audio"
                    or media.lifecycle != "temporary"
                ):
                    conflict("MEDIA_ALREADY_CLAIMED")
                if media.uploaded_at is None:
                    conflict("MEDIA_NOT_UPLOADED")
                if body.input.realtime_session_id:
                    from core.realtime import transcript_for
                    transcription = transcript_for(body.input.realtime_session_id, self.collection.id, card.id)
                media.lifecycle = "ready"
            note = self.repo.get(Note, card.note_id)
            template = self.db.get(CardTemplate, card.card_template_id)
            attempt = Attempt(
                collection_id=self.collection.id,
                card_id=card.id,
                note_id=card.note_id,
                card_template_id=card.card_template_id,
                review_token=body.review_token,
                note_snapshot=deepcopy(note.fields),
                front_snapshot=rendered["front"],
                back_snapshot=rendered["back"],
                answer_snapshot=rendered["answer"],
                input_type=body.input.type,
                input_snapshot=jsonable_encoder(body.input, exclude_none=True),
                media_asset_id=media.id if media else None,
                card_schedule_revision=card.schedule_revision,
                quota_kind=card.queue if card.queue in ("new", "review") else None,
                quota_deck_id=card.original_deck_id or card.deck_id,
                asr_status="succeeded" if transcription else "pending" if media else "skipped",
                asr_result=transcription,
                ai_status="pending"
                if template.key in ("sentence_retelling", "sentence_translation")
                else "skipped",
                deterministic_result=dictation(note.fields["english"], body.input.text)
                if template.key == "sentence_dictation"
                else None,
            )
            self.db.add(attempt)
            self.db.flush()
            for kind in ("asr", "ai"):
                if getattr(attempt, kind + "_status") == "pending":
                    self.db.add(
                        ProcessingOutbox(
                            collection_id=self.collection.id,
                            attempt_id=attempt.id,
                            kind=kind,
                        )
                    )
            response = self.flipped(attempt)
        return self.receipt(key, operation, fingerprint, response)

    def flipped(self, attempt):
        card = self.repo.get(Card, attempt.card_id)
        return {
            "attempt": self.attempt_data(attempt),
            "card_schedule_revision": card.schedule_revision,
            "rating_options": options(
                card, self.now, self.collection, self.config(card)
            ),
        }

    def lock_card(self, card_id):
        self.repo.get(Card, card_id)
        return self.db.scalar(
            select(Card)
            .where(Card.collection_id == self.collection.id, Card.id == card_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def rate(self, queue_id, attempt_id, body, key):
        q = self.queue(queue_id)
        operation = "rating:" + str(attempt_id)
        replay, fingerprint = self.replay(key, operation, body.model_dump())
        if replay is not None:
            return replay
        attempt = self.repo.get(Attempt, attempt_id)
        if attempt.rating:
            if attempt.rating != body.rating:
                conflict("RATING_ALREADY_SET")
            return self.receipt(key, operation, fingerprint, attempt.rating_result)
        if q.current != attempt.card_id or q.token != attempt.review_token:
            conflict("REVIEW_TOKEN_INVALID")
        card = self.lock_card(attempt.card_id)
        if card.schedule_revision != body.card_schedule_revision or card.queue in (
            "suspended",
            "buried_user",
            "buried_sibling",
        ):
            conflict("CARD_SCHEDULE_CONFLICT")
        if not self.capacity(card, self.usage()):
            conflict("DAILY_LIMIT_REACHED")
        before = {name: deepcopy(getattr(card, name)) for name in SCHEDULE_FIELDS}
        changed = []
        config = self.config(card)
        state = schedule(card, body.rating, self.now, self.collection, config)
        for name, value in state.items():
            setattr(card, name, value)
        card.schedule_revision += 1
        if config["sibling_burying"]:
            for sibling in self.db.scalars(
                select(Card)
                .where(
                    Card.collection_id == self.collection.id,
                    Card.note_id == card.note_id,
                    Card.id != card.id,
                    Card.queue.in_(["new", "review", "day_learning"]),
                )
                .with_for_update()
            ):
                changed.append(
                    (
                        sibling.id,
                        sibling.queue,
                        sibling.buried_on_day,
                        sibling.schedule_revision + 1,
                    )
                )
                sibling.queue, sibling.buried_on_day = "buried_sibling", self.day
                sibling.schedule_revision += 1
        attempt.previous_interval_days = before["interval_days"]
        attempt.scheduled_interval_days = state["interval_days"]
        attempt.review_kind = before["type"]
        attempt.fsrs_algorithm_version = state["fsrs_state"]["fsrs_algorithm_version"]
        attempt.fsrs_config_version = state["fsrs_state"]["fsrs_config_version"]
        attempt.rating, attempt.rated_at = body.rating, self.now
        response = {
            "attempt_id": attempt.id,
            "rating": attempt.rating,
            "rated_at": attempt.rated_at,
            "card": {
                **state,
                "id": card.id,
                "card_schedule_revision": card.schedule_revision,
            },
        }
        attempt.rating_result = jsonable_encoder(response)
        q.undo = {
            "attempt_id": attempt.id,
            "card_id": card.id,
            "before": before,
            "revision": card.schedule_revision,
            "siblings": changed,
            "order": list(q.order),
        }
        q.order = [i for i in q.order if i != card.id]
        q.current, q.token = None, None
        return self.receipt(key, operation, fingerprint, response)

    def undo(self, queue_id, key=None):
        q = self.queue(queue_id)
        if key:
            replay, fingerprint = self.replay(key, "undo", {"queue_id": queue_id})
            if replay is not None:
                return replay
        if not q.undo or self.pending():
            conflict("UNDO_NOT_AVAILABLE")
        context = q.undo
        card = self.lock_card(context["card_id"])
        if card.schedule_revision != context["revision"]:
            conflict("UNDO_NOT_AVAILABLE")
        siblings = [self.lock_card(row[0]) for row in context["siblings"]]
        if any(
            c.schedule_revision != row[3]
            for c, row in zip(siblings, context["siblings"])
        ):
            conflict("UNDO_NOT_AVAILABLE")
        for field, value in context["before"].items():
            setattr(card, field, value)
        card.schedule_revision += 1
        for sibling, row in zip(siblings, context["siblings"]):
            sibling.queue, sibling.buried_on_day = row[1:3]
            sibling.schedule_revision += 1
        attempt = self.repo.get(Attempt, context["attempt_id"])
        attempt.rating = attempt.rated_at = attempt.rating_result = None
        attempt.card_schedule_revision = card.schedule_revision
        for name in (
            "previous_interval_days",
            "scheduled_interval_days",
            "review_kind",
            "fsrs_algorithm_version",
            "fsrs_config_version",
        ):
            setattr(attempt, name, None)
        for receipt in self.db.scalars(
            select(ReviewReceipt).where(
                ReviewReceipt.collection_id == self.collection.id,
                ReviewReceipt.operation == "rating:" + str(attempt.id),
            )
        ):
            receipt.response = {**receipt.response, "superseded": True}
        q.order, q.current, q.token, q.undo = (
            context["order"],
            card.id,
            attempt.review_token,
            None,
        )
        self.db.flush()
        response = self.flipped(attempt)
        return self.receipt(key, "undo", fingerprint, response) if key else response

    def change_schedule(self, card_id, body):
        card = self.lock_card(card_id)
        if card.schedule_revision != body.card_schedule_revision:
            conflict("CARD_SCHEDULE_CONFLICT")
        if body.action == "suspend":
            card.queue, card.buried_on_day = "suspended", None
        elif body.action == "bury":
            if card.queue == "suspended":
                conflict("CARD_SCHEDULE_CONFLICT")
            card.queue, card.buried_on_day = "buried_user", self.day
        else:
            allowed = (
                ["suspended"]
                if body.action == "unsuspend"
                else ["buried_user", "buried_sibling"]
            )
            if card.queue not in allowed:
                conflict("CARD_SCHEDULE_CONFLICT")
            card.queue, card.buried_on_day = restored_queue(card), None
        card.schedule_revision += 1
        QUEUES.pop(self.collection.id, None)
        return self.render(card)

    def get_attempt(self, attempt_id):
        return self.attempt_data(self.repo.get(Attempt, attempt_id))

    def get_settings(self, deck_id):
        deck = self.repo.standard_deck(deck_id)
        return {
            "overrides": deck.scheduling_config,
            "effective": effective(self.collection, deck_id, self.decks),
        }

    def update_settings(self, deck_id, body):
        deck = self.repo.standard_deck(deck_id)
        values = {**deck.scheduling_config, **body.overrides}
        deck.scheduling_config = {
            key: value for key, value in values.items() if value is not None
        }
        QUEUES.pop(self.collection.id, None)
        return self.get_settings(deck_id)

    def deck_counts(self):
        self.restore_buried()
        cards_by_deck = {deck.id: [] for deck in self.decks.values() if deck.kind == "standard"}
        renderable_ids = set()
        # One snapshot for every deck. Keep queue ordering, quotas, selection and
        # learning-ahead rules in the same eligibility code used by real review.
        rows = self.db.execute(
            select(Card, Note.fields, CardTemplate.required_fields)
            .join(Note, Card.note_id == Note.id)
            .join(CardTemplate, Card.card_template_id == CardTemplate.id)
            .where(Card.collection_id == self.collection.id,
                   Card.deck_id.in_(cards_by_deck), ~Note.guid.startswith("legacy:"))
        )
        for card, fields, required in rows:
            if self.card_selected(card):
                cards_by_deck[card.deck_id].append(card)
                if all(present(fields.get(key)) for key in required):
                    renderable_ids.add(card.id)
        usage, stamp = self.usage(), self.stamp()
        result = {}
        for deck_id, cards in cards_by_deck.items():
            q = RuntimeQueue(uuid7(), {"deck_id": deck_id, "include_descendants": False, "exclude_imported": True}, [], self.day, stamp, self.now + timedelta(hours=2))
            result[str(deck_id)] = self.counts(q, scoped_cards=cards, usage=usage, renderable_ids=renderable_ids)
        return {"decks": result}

    def paused_cards(self, deck_id):
        self.restore_buried()
        cards = self.in_scope({"deck_id": deck_id, "include_descendants": True})
        return {"cards": [{**self.front(card), "queue": card.queue}
                          for card in cards if card.queue in ("suspended", "buried_user", "buried_sibling")]}
