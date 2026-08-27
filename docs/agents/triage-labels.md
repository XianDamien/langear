# Triage Labels

Use the following default triage label vocabulary:

- `needs-triage`: maintainer needs to evaluate
- `needs-info`: waiting on reporter
- `ready-for-agent`: fully specified and ready for an agent to execute
- `ready-for-human`: needs human implementation
- `wontfix`: will not be actioned

## Refactor Ownership Note

When triaging the Anki-style architecture refactor:

- Product/AI owner: product contracts, NoteType/CardTemplate behavior, AI schemas and prompts, evaluation datasets, and learner-facing frontend flows.
- Feng: backend foundations and infrastructure, including PostgreSQL/Alembic, authentication and Collection isolation, FSRS scheduling, Attempt/Media/Outbox/Celery reliability, deployment, observability, backup, and migration work.
- Shared: freeze API and state-machine contracts before parallel implementation; product semantics are led by the Product/AI owner, while Feng validates data constraints and operational feasibility.
