# Direct Qwen voice dialogue

The Python backend assembles a fixed scenario from the authenticated learner's rated Attempt snapshots and sends bounded lesson context directly to Qwen-Omni-Realtime. Creating or finishing a Dialogue Session makes no separate model request. There is no pi service or Chinese recap step.

## Isolated development

`compose.yml` runs only PostgreSQL and the backend. Set `DIALOGUE_RUNTIME_DIR` to a private directory containing `postgres.env` and `core.env`, and select the staging dependency baseline with `DEV_BASE_IMAGE`. Keep the backend database URL pointed at this isolated PostgreSQL service. Apply `alembic -c alembic-core.ini upgrade head` before using the API. The voice settings are listed in `backend/.env.dialogue.example`; provider keys never go to the browser.

Frontend verification: `pnpm test`, `pnpm typecheck` and `pnpm lint` in `frontend/`. Backend integration tests use a disposable PostgreSQL database named `lan30_test_*` via `CORE_TEST_DATABASE_URL`; do not run truncating fixtures on preview, staging or production databases.

## Protocol

- `GET /api/v1/dialogue/availability`: enabled only when the feature and Qwen voice key are configured.
- `POST /api/v1/dialogue/sessions`: `{deck_id, review_queue_id, entry_key, attempt_ids}`. Requires the current exhausted Review queue and the exact rated Attempt set for this round. Assembles the scenario locally and persists its context.
- `GET /api/v1/dialogue/sessions/{id}`: fixed scenario, state and saved complete turns. No review field.
- `WS .../{id}/ws`: normal session cookie and trusted Origin required. Client sends `audio_begin`, PCM16 mono 16kHz `audio` chunks, `commit` or `end`; server sends `connected`, `message_delta`, PCM16 mono 24kHz `audio`, saved `turn`, `ready`, `ended` or sanitized `error` events.
- `POST .../{id}/finish`: ends a disconnected session without calling a model. The former `/review` endpoint is removed.

Eight learner turns and a 90-second recording limit are enforced by the server. A connection lease prevents concurrent sessions and expires after a process crash. Reconnection restores complete turns; partial replies are never persisted. Raw dialogue audio is streamed but not stored.

Existing `dialogue_reviews` storage is retained for compatibility with earlier previews; this version never reads or writes it. Dialogue never changes Attempts, ratings, processing or Card scheduling. Production rollout remains a separate operation.
