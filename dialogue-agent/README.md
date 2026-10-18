# LanGear Dialogue Agent

This private Node service uses the pi agent core from the reviewed local pi package version (`0.85.1`). Python authenticates the learner, scopes practice evidence to their Collection, and validates all source and turn citations. The model sees only the bound context through `get_practice_context`; it has no database or shell tools. A schema-validated `submit_result` ends the bounded planning/review loop.

The confirmed product scope lives in `docs/plans/2026-10-18-dialogue-agent.md` and Linear LAN-21. pi prepares one immutable scenario and reviews the completed transcript. Qwen-Omni-Realtime performs the actual English roleplay and audio generation through the Python WebSocket gateway. Dialogue never writes Attempts, ratings, or Card scheduling.

## Development

Use Node >=22.19.0. Install with `pnpm install --frozen-lockfile`, then provide the variables in `.env.example` through your process environment and run `pnpm start`. The service defaults to loopback; bind `HOST=0.0.0.0` only inside its private container network. The Python environment variables are documented in `backend/.env.dialogue.example`. Configure the Omni WebSocket host and planner HTTP host for the same authorized region/workspace; they are independently configurable. Provider keys stay on the server.

`pnpm typecheck`, `pnpm lint`, and `pnpm test` validate the Node service. Frontend checks run in `frontend/` using `pnpm typecheck`, `pnpm lint`, and `pnpm test`. Backend integration tests require a disposable PostgreSQL database named `lan30_test_*` through `CORE_TEST_DATABASE_URL`; never point them at preview, staging, or production data.

`scripts/dialogue/compose.yml` is a standalone development stack with its own PostgreSQL volume and localhost backend port. Provide private `postgres.env`, `core.env` and `agent.env` files under `DIALOGUE_RUNTIME_DIR`, plus the explicitly selected `DEV_BASE_IMAGE`. The backend URL must target this stack's `postgres`, and the agent URL must be `http://agent:8111`. Create/seed or import data into this isolated database explicitly, then run `alembic -c alembic-core.ini upgrade head` before starting the API. Schema revision `lan21_0008` adds only independent Dialogue tables. Production deployment and migration are separate operations.

## Protocol and recovery

- `POST /api/v1/dialogue/sessions`: `{deck_id, review_queue_id, entry_key, attempt_ids}`; the backend verifies the active Review queue is exhausted and that the rated Attempts exactly match this round before preparing a scenario. Duplicate keys with different round evidence return 409.
- `GET /api/v1/dialogue/sessions/{id}`: persisted scenario, complete turns and optional review.
- `WS /api/v1/dialogue/sessions/{id}/ws`: requires the normal session cookie and trusted Origin. Browser sends `audio_begin`, PCM16 mono 16kHz `audio` chunks, `commit`, or `end`. Server sends `connected`, `message_delta`, PCM16 mono 24kHz `audio`, persisted `turn`, `ready`, `ended`, or sanitized `error` events.
- `POST .../{id}/finish`: explicitly ends a disconnected session. `POST .../{id}/review` generates/returns its Chinese review, with validated learner-turn and original Attempt evidence.

The server enforces eight learner turns and a 90-second input limit. A lease prevents simultaneous voice connections; after a process crash it expires within 60 seconds. Disconnecting releases the microphone in the browser and marks the server session interrupted. Reconnecting restores complete text turns, with no automatic retransmission of partially submitted audio. Incomplete assistant responses are not persisted. Text context, ASR text and existing feedback are bounded before planning; no long-term memory is generated. Raw dialogue audio is streamed but not stored in this version.

The bridge waits for the input transcription before requesting the next response. It supplies explicit response instructions even for the opening turn, as required by Qwen-Omni. `finish_scenario` signals goal completion; the Chinese review separately checks actual learner evidence. It must not infer pronunciation from text.
