# LanGear Agent Guide

LanGear is an AI-assisted English retelling training app.

## Subagent Constraint

- Spawn subagents only when their output will materially affect the task
- After spawning a subagent, do not finish or close out the task before its result returns and is evaluated, unless the user explicitly cancels the work
- Do not create subagents just for appearance of parallelism
- If a subagent is no longer needed, cancel or close it explicitly instead of letting it run pointlessly and waste tokens

## Worktree Documentation Policy

- In feature worktrees, keep changes code-scoped unless the user explicitly asks for documentation edits
- Do not update project `README.md`, `PRD.md`, or `PRD_BASELINE.md` as part of routine worktree implementation, because those edits create avoidable merge conflicts
- Defer documentation rewrites until the related functionality is complete and merged, then update docs once in a final pass
- When documentation is intentionally deferred under this rule, say so explicitly in the final response

## Commit Message Policy

- Future commit messages should use concise Chinese descriptions by default
- The title should include the main change points
- Only commit task-related files unless explicitly asked otherwise

## Quickfire Backend Routing

- In AI-Mark / Quickfire tasks, do not assume the backend code lives in the current frontend workspace by default
- When the user mentions backend debugging, server logs, upload tracing, ASR results, grading results, batch data, OSS audio, NocoDB records, validation failures, or other production/backend investigation topics, use the `quickfire-server-debug` skill first
- Skill path: `/Users/damien/.codex/skills/quickfire-server-debug/SKILL.md`

## Repo Layout

```text
frontend/
  src/
  tests/
  e2e/

backend/
  app/
  migrations/
  tests/
  scripts/

docs/
scripts/
skills/
```

## Run Commands

- Frontend dev: `cd frontend && pnpm dev` (default port `3002`)
- Frontend E2E: `cd frontend && pnpm test:e2e`
- Backend dev: `cd backend && uv run uvicorn app.main:app --reload` (default port `8000`)
- Backend tests: `cd backend && uv run pytest`

## Server Access

- Production server SSH alias: `ssh langear-prod`
- Remote deployment root: `/srv/langear`
- Production backend compose files: `/srv/langear/docker-compose.yml` + `/srv/langear/docker-compose.server.yml`
- Test backend compose file: `/srv/langear/docker-compose.test.yml`

## Environment Rules

- Frontend env lives in `frontend/.env`
- Backend env lives in `backend/.env`
- Do not rely on repo root `.env` for backend runtime
- Do not hardcode API keys

## Integration Rules

- ASR must use `qwen3-asr-flash`
- Gemini must use the official `google-genai` SDK path only
- Do not use Gemini relay
- Do not add Gemini runtime fallback branches
- Backend Gemini config should come from `backend/.env`
- OSS user audio and reference audio are handled by backend adapters

## Working Rules

- Prefer minimal, task-scoped changes
- Do not mix unrelated dirty files into a commit
- Add or update tests when behavior changes
- Prefer reading existing code before changing architecture
- `CLAUDE.md` is a symlink to `AGENTS.md`; treat `AGENTS.md` as the single source of truth

## Agent skills

### Issue tracker

LanGear issues are tracked in Linear via the `managing-langear` workflow, not GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default triage label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Use a single-context layout rooted at the repository root. See `docs/agents/domain.md`.

### Product language

- Treat `CONTEXT.md` as the canonical glossary for learner-facing agent terminology
- Use `Study Session` for retelling practice and card-level feedback
- Use `Dialogue Session` for post-lesson scenario dialogue practice; do not treat it as a `Study Session`
- In the first version, the default `Dialogue Entry Point` is the explicit button shown after all cards in a lesson are completed

### Learner agents

- Build learner-facing agents in this priority order:
  - `P0`: shared foundations — multi-user context, business tools, card/lesson context assembly, Markdown RAG, citations/jump targets
  - `P1`: Q&A / summary agent — lesson/card answering, lesson summary, fixed pronunciation follow-up resource
  - `P2`: dialogue agent — end-to-end scenario conversation after lesson completion
  - `P3`: unified card system + AI card mutations
- Keep `P0` and `P1` as the first executable slice unless the user explicitly reprioritizes
- The Q&A agent must answer from current card context, current lesson feedback history, and internal knowledge-base snippets before relying on general model priors
- External follow-up resources are currently restricted to the single approved Bilibili pronunciation link recorded in `docs/plans/2026-05-01-adk-coach-agent-todo.md`

### Tech stack skills

When working in this repo, prefer these local Codex skills under `~/.codex/skills`:

- `~/.codex/skills/vue/SKILL.md`
- `~/.codex/skills/nuxt/SKILL.md`
- `~/.codex/skills/pinia/SKILL.md`
- `~/.codex/skills/vite/SKILL.md`
- `~/.codex/skills/vitepress/SKILL.md`
- `~/.codex/skills/vitest/SKILL.md`
- `~/.codex/skills/unocss/SKILL.md`
- `~/.codex/skills/pnpm/SKILL.md`

## Documentation Files

- `README.md` is the primary entry for run commands, environment setup, and current developer workflow
- `PRD_BASELINE.md` is the fast alignment baseline for current product and integration behavior
- `PRD.md` is the detailed product and implementation source document
- `docs/prd_versions/README.md` defines the PRD versioning and mirror workflow
- `docs/standards/worktree-dev-delivery.md` defines the worktree delivery and merge workflow

## Key Files

- `AGENTS.md`
- `README.md`
- `PRD.md`
- `PRD_BASELINE.md`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `backend/pyproject.toml`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/adapters/asr_adapter.py`
- `backend/app/adapters/gemini_adapter.py`
- `scripts/prd_version_manager.py`
