# Attempt as the practice fact

Status: accepted

An Attempt is created when a learner flips a Card, after any pre-flip recordings have remained temporary. It stores immutable input, Note-field, rendered-prompt, answer, and media snapshots. ASR, AI feedback, and learner Rating are independent updates to the same Attempt: Rating is synchronous and advances FSRS; ASR and AI run asynchronously and never choose a Rating. A failed ASR or AI task does not block Rating.

Celery and Redis execute the asynchronous work. A PostgreSQL `task_outbox` row is created in the same transaction as the Attempt for each independent task, giving reliable at-least-once delivery. Workers must be idempotent by Attempt ID. Attempt data, rather than Celery result data, is the business record.
