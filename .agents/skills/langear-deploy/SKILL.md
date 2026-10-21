---
name: langear-deploy
description: Deploy, sync, verify, or roll back LanGear across local, staging, and production. Use this skill whenever the user mentions LanGear deployment, staging, release, 发布, 上线, 同步到 staging, 热加载, hot reload, manage.py, release.override.yml, staging backend, review worker, or asks which commit, image, model, prompt, or database revision is actually running. Also use it after merging feature work when the question is how to get the change onto staging or production.
---

# LanGear Deployment

LanGear has three layers that are easy to confuse:

1. **Git checkout** — what the repository working tree contains.
2. **Runtime mode** — whether the running containers use a fixed release image or the mounted source with hot reload.
3. **Database revision** — the Alembic version in the live database.

Syncing source does **not** change a running release. Always identify which layer you are changing before running a command.

## Environment map

| Environment | Access | Code root | Runtime | Database |
|---|---|---|---|---|
| Local | this Mac | current repo | `backend` on `127.0.0.1:8000`, Vite on `3002` | local PostgreSQL, commonly `lan30_local` |
| Staging | `ssh zhaohui-staging-server` | `/home/kemove/langear/dev/repo` | `/home/kemove/langear/dev/compose/docker-compose.yml` | independent staging PostgreSQL |
| Production | `ssh langear-prod` | `/srv/langear/prod/repo` | `/srv/langear/prod/compose/docker-compose.yml` | production PostgreSQL |

- Staging preview: `https://8.159.139.145:7145` (self-signed certificate).
- Staging backend is bound to `127.0.0.1:8004`; the preview Nginx proxies to it.
- Production backend is bound to `127.0.0.1:8000`.
- Do not use `dev.langear.cn` as the active staging entry; its DNS points at a different legacy frontend.

## Non-negotiable rules

- Develop in local task worktrees. Use staging for runtime verification and release acceptance; do not default to editing application code in the staging checkout.
- Only one task may use the shared staging runtime at a time.
- Before syncing local work to staging, inspect **both** checkouts for branch, commit, staged changes, and unstaged changes. Preserve unrelated remote work; do not overwrite it or pull it into the local task.
- Never print secrets from `env/backend.env`, `env/review.env`, `backend/.env*`, database dumps, or FRP tokens.
- Do not run destructive database resets, refreshes, or production changes without explicit scope.
- Production deployment, production rollback, and production database changes always require explicit authorization, even if staging was already approved.

## 1. Local development

Default local shape:

```text
Browser http://localhost:3002
  -> local Vite proxy
  -> http://127.0.0.1:8000/api/...
  -> local backend
  -> local PostgreSQL
```

Start or restart the local backend from the repo:

```bash
cd backend
CORE_DATABASE_URL='postgresql+psycopg://damien@127.0.0.1:5432/lan30_local' \
CORE_ALLOWED_ORIGINS='["http://localhost:3002","http://127.0.0.1:3002"]' \
.venv/bin/uvicorn core.core_only:app \
  --host 127.0.0.1 --port 8000 --log-level info \
  --env-file .env.development.local
```

`--env-file` does not override variables already present in the process environment, so the inline `CORE_DATABASE_URL` wins. The env file supplies API keys, OSS keys, and the default model.

Start the frontend:

```bash
cd frontend && pnpm dev
```

Vite is fixed to `3002`. The default proxy target is the staging preview unless `VITE_DEV_PROXY_TARGET` overrides it. Check the running process before assuming which backend the page uses:

```bash
ps eww -p $(lsof -nP -iTCP:3002 -sTCP:LISTEN -t | head -1) \
  | tr ' ' '\n' | grep '^VITE_DEV_PROXY_TARGET='
```

### Env-file precedence can silently change the model

`backend/.env` and `backend/.env.development.local` are not interchangeable. In this repo the former has historically pointed at SQLite and a different Gemini model, while the latter is the local development config. Before trusting a rerun or benchmark, inspect the **running process**, not just the file you intended to load:

```bash
ps eww -p $(lsof -nP -iTCP:8000 -sTCP:LISTEN -t | head -1) \
  | tr ' ' '\n' | grep -E '^(CORE_DATABASE_URL|GEMINI_MODEL_ID|AI_FEEDBACK_PROVIDER|AI_FEEDBACK_PROMPT_VERSION)=' \
  | sed -E 's#(://[^:]+:)[^@]+@#\1***@#'
```

### `A trusted Origin is required` on localhost

The core backend checks the `Origin` header. If the local Vite page gets `403 ORIGIN_FORBIDDEN`, add both local origins to `CORE_ALLOWED_ORIGINS`, then restart the backend:

```text
http://localhost:3002
http://127.0.0.1:3002
```

Verify without changing data: a request with the trusted origin should get past the origin check (for example `401` on login with a bad password), while the same request without an origin should still return `403`.

## 2. Merge work into `dev/staging`

The main development branch is `dev/staging`. First check whether the feature is already merged — a merge commit may already exist even when the feature branch still exists:

```bash
git fetch origin dev/staging
git merge-base --is-ancestor <feature-sha> dev/staging && echo merged || echo not-merged
git log --oneline dev/staging..<feature-branch>
```

If there are commits not in `dev/staging`, merge them locally and test before pushing. Do not create merge commits on someone else's behalf without checking the worktree state.

Push the local branch:

```bash
git push origin dev/staging
```

### Sync the staging checkout without GitHub SSH access

The staging server has **no GitHub SSH authorization**. Its checkout cannot pull from GitHub. Use the Mac as the transport:

```bash
# 1. Confirm local is strictly ahead of the staging checkout.
git fetch staging-dev dev/staging
git merge-base --is-ancestor staging-dev/dev/staging dev/staging \
  && echo "fast-forward possible" || echo "STOP: staging has commits not in local"

# 2. Push to a temporary ref; do not push to the checked-out dev/staging branch.
git push staging-dev dev/staging:refs/heads/sync/dev-staging-<short-sha>

# 3. Fast-forward the staging working tree, then delete the temp ref.
ssh zhaohui-staging-server 'cd /home/kemove/langear/dev/repo && \
  git merge --ff-only refs/heads/sync/dev-staging-<short-sha> && \
  git branch -D sync/dev-staging-<short-sha> && \
  git log -1 --oneline && git status -sb'
```

If the staging checkout is not clean, or contains commits not in local, stop and reconcile before merging. Never force-push or reset the staging checkout to “fix” divergence.

## 3. Staging runtime modes

Inspect the authoritative state first:

```bash
python3 scripts/release/manage.py status staging
cat /home/kemove/langear/dev/releases/current.json   # on the staging server
```

`releases/current.json` is authoritative. Do not infer the running version from `git log` alone.

### Release mode

A fixed release uses `compose/release.override.yml` and an immutable image. Signatures:

- `current.json` has `"mode": "release"`.
- Container command has no `--reload`.
- Code lives under `/app`; `repo/backend` is **not** mounted.
- Frontend static is a specific release directory.

Deploy a successful CI bundle:

```bash
# CI must have produced the artifact for this SHA.
python3 scripts/release/manage.py stage --run <RUN_ID>
```

`stage` downloads the paired frontend/backend artifact, verifies it, uploads it to staging, switches both halves, and waits for health checks. It pauses backend source hot reload.

After acceptance:

```bash
python3 scripts/release/manage.py approve --checks '<what you actually tested and observed>'
```

Only record checks that were actually performed. Do not describe untested recording, ASR, or feedback flows as accepted.

### Dev hot-reload mode

Use this when you need the current checkout's backend code on staging:

```bash
python3 scripts/release/manage.py dev
```

What it does:

- Stops the review worker before replacing the backend.
- Rewrites `compose/release.override.yml` to keep the previous image's Python environment but run from `/workspace/backend` with `--reload`.
- Mounts `repo/backend` into both backend and review worker.
- Recreates the web container so Nginx re-resolves the backend.
- Leaves the frontend static at the last preview build.

This is the right mode for testing backend prompt, API, worker, ASR, and grading changes. It is **not** a frontend deployment. For frontend iteration, run local Vite (`pnpm dev`) against the staging API, or build a new release.

Verify that the source is actually mounted and the new code is loaded:

```bash
ssh zhaohui-staging-server '
  docker inspect langear-staging-dev-backend --format "cmd={{.Config.Cmd}}";
  docker inspect langear-staging-dev-backend --format "{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}";
  docker exec langear-staging-dev-backend \
    grep -m1 "<a distinctive line from the changed file>" \
    /workspace/backend/<path-to-file>
'
```

If the file is missing, you are still in release mode or the checkout was not synced.

### Switch back to release mode

Run a new `stage` with a CI artifact. `manage.py dev` does not restore release mode by itself, and stopping containers is not a deployment.

## 4. Production release

Production reuses the exact staging artifacts. Do not rebuild from a floating branch, do not deploy frontend separately, and do not copy dev data to production.

```bash
# 1. Plan only; does not modify production.
python3 scripts/release/manage.py promote --sha <FULL_SHA>

# 2. Only after explicit production authorization:
python3 scripts/release/manage.py promote --sha <FULL_SHA> --execute
```

Preconditions:

- Staging approval exists for exactly that SHA.
- Artifact hashes, image ID, and database revision still match the approval record.
- The SHA is a full 40-character Git SHA.

Production deployment does not switch the source checkout. Runtime records and image IDs are authoritative, not `git HEAD`.

## 5. Rollback

```bash
python3 scripts/release/manage.py rollback staging
python3 scripts/release/manage.py rollback prod           # plan only
python3 scripts/release/manage.py rollback prod --execute # requires authorization
```

Rollback restores the previous frontend and backend. It does not migrate or downgrade the database. If the schema changed, the script refuses the application rollback; prepare a separate database recovery plan.

## 6. Database migrations

Migration heads must equal the live database revision. Deploy scripts never migrate automatically.

Check before a release or after syncing a large batch:

```bash
# Live revision recorded in the release state
python3 scripts/release/manage.py status staging

# Code head inside the staging backend container
ssh zhaohui-staging-server '
  docker exec -w /workspace/backend langear-staging-dev-backend \
    alembic -c alembic-core.ini heads
'
```

If the code head is ahead of the live revision, do not treat the deployment as ready. Prepare a backup, migration, and recovery plan as a separate authorized step. For a local check, run the isolated test script rather than pytest against a real database:

```bash
cd backend && uv run bash ../scripts/release/test-core.sh -q
```

## 7. Verification checklist

After any sync or mode switch:

- [ ] `GET /health` returns `{"status":"healthy","service":"collection-core"}` on the target backend.
- [ ] Staging preview `/health` returns healthy.
- [ ] The container command and mounts match the intended mode (`/app` without `--reload` for release; `/workspace/backend` with `--reload` for dev).
- [ ] The changed file inside the container contains the expected content.
- [ ] The review worker is healthy, not just the API.
- [ ] The database revision matches the code head.
- [ ] The frontend static SHA matches the intended release when testing UI.
- [ ] The AI provider/model in the runtime is the one you expect; do not assume Gemini.
- [ ] Local `3002` requests pass the origin check (or return `403` deliberately when testing the guard).

## 8. Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `A trusted Origin is required` | `CORE_ALLOWED_ORIGINS` lacks the browser origin | Add `http://localhost:3002` / `http://127.0.0.1:3002`, restart backend |
| Source synced but behavior unchanged | Runtime is a fixed release image | `manage.py dev` for backend testing, or `stage --run` for a full release |
| New prompt not used in staging | Backend/worker still run the image; or only one container was restarted | Check mounts and the file inside **both** backend and worker |
| Wrong model in a rerun | The script loaded a different env file or inherited a stale process env | Inspect the running process env; do not assume the file you intended won |
| `git push staging-dev dev/staging` refused | Staging branch is checked out | Push to a temp ref and `git merge --ff-only` on the server |
| Staging cannot fetch from GitHub | No GitHub SSH auth on staging | Transport commits from the Mac via `staging-dev` |
| Release aborts on schema mismatch | Code Alembic head ≠ live DB revision | Stop; prepare a migration/recovery plan |
| Staging preview UI is stale | `manage.py dev` keeps the last static frontend | Use local Vite, or deploy a new release bundle |

## Key files

- `AGENTS.md` — repository rules and environment routing.
- `docs/operations/dev-prod-workflow.md` — current dev/staging/prod workflow.
- `scripts/release/manage.py` — Mac entry point for stage/approve/promote/rollback/dev.
- `scripts/release/host.py` — server-side deployment, overlay, health, and rollback logic.
- `.github/workflows/frontend-dev-deploy.yml` — CI that tests and packages the paired release.
- `compose/docker-compose.yml` and `compose/release.override.yml` on the staging/prod host — source-mount vs fixed-image runtime contract.
