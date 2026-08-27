# LanGear Product Architecture Baseline

Status: shared understanding, 2026-08-23

This document turns the product decisions from the architecture discussion into an implementation boundary. It is a design baseline, not a migration plan for the current schema; the current database is disposable because it has no user records.

## Product direction

LanGear is an online, Anki-like speaking practice system. Its durable learning unit is the Card, and its durable content unit is the Note. There is no permanent course-completion state: a Card is new, learning, due, suspended, or buried according to its scheduler.

The first executable slice is:

1. Multi-user account and Collection isolation.
2. Hierarchical Decks with dynamic Note-to-Card rendering.
3. Vocabulary and Sentence system NoteTypes.
4. FSRS scheduling, runtime review queues, sibling burying, and Filtered Decks.
5. Attempt snapshots with independent ASR, AI feedback, and learner Rating flows.
6. System Library copy import and LanGear JSON/ZIP import.

Deferred: teacher workflows, assignments, custom templates, automatic Library sync, APKG, offline mode, RLS, Dialogue Sessions, and open-ended Q&A.

## Domain shape

```text
User
└── Collection (one per user)
    ├── Deck tree
    │   └── Card
    │       ├── Note
    │       ├── Card Template
    │       ├── FSRS state
    │       └── Attempt history
    └── private MediaAsset

System Library Collection (one, read-only)
└── Deck tree → Notes → shared reference MediaAssets
```

Note is not assigned to a Deck. Creating a Note receives a target Standard Deck and places all generated Cards there. Cards can later move independently and may mix NoteTypes. A Note can remain without Cards; the user explicitly generates missing Cards when needed.

## Initial NoteTypes

### Vocabulary

Fields: `word`, `meaning`, `phonetic`, `note`, `reference_audio`, `image`.

Templates: English-to-Chinese and Chinese-to-English.

### Sentence NoteType

Fields: `english`, `chinese`, `note`, `reference_audio`.

Sentence is the shared content type, not a fourth practice mode. One Sentence Note may generate Retelling, Translation, and Dictation Cards with independent Deck and FSRS state. Retelling requires `english + reference_audio`; its front is audio-only, it requires a learner recording, and its back shows reference audio, English, Chinese, optional Attempt AI feedback, and notes. Translation requires `english + chinese`; its front is Chinese-only, it requires an English text answer, and its back shows English, Chinese, optional reference audio, optional Attempt AI feedback, and notes. Dictation requires `english + reference_audio`; its front is audio-only, it requires English text, and its back shows English, Chinese, deterministic writing feedback, an optional empty AI-feedback slot, and notes. Dictation does not invoke AI in v1. Both Vocabulary templates allow direct reveal and Rating without submitted input.

Retelling and Translation use separate evaluators, prompts, and mode-specific result schemas. They share only a stable AI Feedback response envelope. Each result records its `feedback_kind`, prompt, model, and schema versions so the two evaluation paths can evolve independently.

All active templates generate persistent Cards by default. Template and field changes are controlled structural operations; ordinary Note field edits are direct edits protected by optimistic locking. A NoteType change uses an Anki-style, user-confirmed old-field-to-new-field mapping. It preserves Note identity/guid but replaces Cards, Attempts, and FSRS state; Card Templates and scheduling state are not mapped.

## Review flow

```text
Start runtime queue
→ render current Note + Card Template
→ optional temporary recordings
→ flip Card
→ create Attempt + applicable Outbox tasks in one transaction
→ Rating API may immediately update Attempt + Card FSRS
→ ASR and AI tasks independently update the same Attempt
→ take next runtime Card ID
```

Pre-flip recordings are temporary OSS objects. Only the recording submitted on flip becomes a permanent Attempt asset. AI and ASR do not choose the learner Rating. A Rating is written once; repeated requests are idempotent. The current Anki-style undo is runtime-only and covers the latest review operation when the same review service still owns the context.

Filtered Decks store at most two `search_terms`, each with a structured filter, limit, and sort order. Structured filters support Deck subtree, tags any/all, NoteType, Card Template, and Card state; arbitrary Anki query strings are not accepted. Version 1 supports only `added`, `retrievability_ascending`, and `retrievability_descending`. `added` uses the Card's initial creation order. Retrievability is calculated from current FSRS state at rebuild time; Cards without a memory state follow stateful Cards and use `added` as their stable fallback order.

A rebuild evaluates terms in order and creates an ordered runtime Card ID queue in memory or Redis. The main order stays stable for that build, while intraday learning Cards may be reinserted by `due_at`. No filtered position is written to a Card; loss of the runtime queue or an explicit rebuild recalculates it.

Version 1 Filtered Decks always reschedule Cards. There is no `reschedule=false` preview mode or `preview_repeat` queue. Card types follow Anki's `new`, `learning`, `review`, and `relearning` phases; queues are separately modeled as `new`, `learning`, `day_learning`, `review`, `suspended`, `buried_sibling`, and `buried_user`. The default learning and relearning steps are each a single 15-minute step, desired retention is `0.90`, and the maximum review interval is `36500` days. Card responses expose backend-computed Again/Hard/Good/Easy interval previews; the backend revalidates and applies the selected Rating.

Standard Deck advanced settings retain Anki-style New gather, New sort, New/Review order, Interday Learning/Review order, and Review sort controls. LanGear defaults are `random_cards`, `order_gathered`, `after_reviews`, `before_reviews`, and `retrievability_descending`. Decks may override these controls together with new/review limits, desired retention, and sibling burying; unset values inherit from the nearest ancestor and then the Collection default. Display-order changes rebuild runtime queues without rewriting Card due or FSRS state.

## Schema sketch

The exact SQLAlchemy models and indexes belong in implementation work. The durable table boundaries are:

```text
users
collections
decks(parent_id, kind, filter_config_json, scheduling_config)
note_types
note_type_fields
card_templates
notes(guid, fields_json, tags, revision)
cards(note_id, deck_id, card_template_id, type, queue, due_at, due_day, fsrs_state_json, original_deck_id)
card_review_attempts(card_id, note_id, snapshots, audio_asset_id, ASR fields, feedback fields, rating)
media_assets(scope, collection_id, object_key, lifecycle)
task_outbox(task_type, aggregate_id, status, retry metadata)
```

All user-owned core tables carry `collection_id`; composite foreign keys prevent cross-Collection relationships. `Note.guid` is unique within a Collection and is used for idempotent imports. `Attempt` snapshots are immutable after creation; only independent processing results and Rating fields are filled later.

## Operational baseline

- PostgreSQL in development, staging, and production; no SQLite-driven schema design.
- UUIDv7 generated by the application for core entity IDs.
- Celery + Redis for ASR and AI tasks; PostgreSQL is the business source of truth.
- Transactional Outbox for Attempt-to-task publication; delivery is at least once and workers are idempotent.
- Production migrations run as explicit release jobs, not on every process start.
- `main` deploys to staging; production deploys the same verified commit/tag.
- Staging and production use separate PostgreSQL databases, Redis, workers, and OSS namespaces.
- PostgreSQL backups include full backups and WAL/PITR; target RPO is at most 24 hours and RTO at most 4 hours.

## Product deletion rules

All destructive actions require explicit confirmation. There is no recycle bin in the first version. Media objects use immutable OSS keys and are cleaned asynchronously after the database no longer references them; temporary uploads have a shorter TTL.
