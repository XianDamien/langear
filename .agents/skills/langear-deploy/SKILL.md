---
name: langear-deploy
description: Deploy, sync, verify, or roll back LanGear across local, staging, and production. Use this skill whenever the user mentions LanGear deployment, staging, release, 发布, 上线, 同步到 staging, 热加载, hot reload, GitHub Actions, CI/CD, GHCR, 镜像拉取, 生产审批, manage.py, release.override.yml, staging backend, review worker, or asks which commit, image, model, prompt, or database revision is actually running. Also use it after merging feature work when the question is how to get the change onto staging or production.
---

# LanGear Deployment

LanGear has three layers that are easy to confuse:

1. **Git checkout** — what the repository working tree contains.
2. **Runtime mode** — whether the running containers use a fixed release image or the mounted source with hot reload.
3. **Database revision** — the Alembic version in the live database.

Syncing source does **not** change a running release. Always identify which layer you are changing before running a command.

## Default release path: GitHub Actions + GHCR

```text
Push dev/staging
  -> GitHub Actions: release-tool tests, isolated PostgreSQL integration tests,
     frontend unit tests, typecheck and build
  -> Build matching backend/frontend images once; push to GHCR
  -> Store a small schema-3 manifest with Git SHA, image digests and image IDs
  -> Actions connects to staging over SSH
  -> Staging pulls images by digest, switches API/worker/frontend, checks health
  -> Actual staging acceptance + explicit production release request
  -> GitHub production Environment required reviewer approval
  -> Production pulls the same accepted digests; no rebuild
```

The Mac only pushes code or requests workflows. Do not download/save/load/upload
application image archives or route application artifacts through the Mac for new
releases. Actions sends only small release metadata and versioned deployment tools
over SSH; application bytes travel directly from GHCR to the target host.
The frontend image supplies static files to the existing host Nginx/TLS setup;
it is extracted without running its image or replacing the host proxy contract.

| Trigger | Tests | Publish images | Deploy staging |
|---|---|---|---|
| PR | Yes | No | No |
| Push `dev/staging` | Yes | Yes | Yes, if still the branch head |
| Push `main` | Yes | Yes | No |
| Manual `operation=release` | Yes | Yes | Only on `dev/staging`, if still the branch head |
| Manual `operation=promote` | Reuses successful build | No rebuild | Rechecks current staging, then awaits production approval |

The default contract is `runtime=core-v1` with `api_base_url=/api/v1`.
The optional `core` contract requires `/api/content/v1`. Keep the pair consistent.
Schema-2 tar bundles remain supported for historical compatibility, not as the
normal release path.

## Environment map

| Environment | Access | Code root | Runtime | Database |
|---|---|---|---|---|
| Local | this Mac | current repo | `backend` on `127.0.0.1:8004`, Vite on `3002` | `langear_local` on local PostgreSQL |
| Staging | `ssh zhaohui-staging-server` | `/home/kemove/langear/dev/repo` | `/home/kemove/langear/dev/compose/docker-compose.yml` | `langear_staging` on `langear-lan3132-test-postgres`; `langear_legacy_snapshot` is only the old legacy copy |
| Production | `ssh langear-prod` | `/srv/langear/prod/repo` | `/srv/langear/prod/compose/docker-compose.yml` | legacy `langear` on `langear-prod-postgres` |

- Staging preview: `https://8.159.139.145:7145` (self-signed certificate).
- Staging backend is bound to `127.0.0.1:8004`; the preview Nginx proxies to it.
- Active staging DB is `langear_staging` on `langear-lan3132-test-postgres`. The compose
  PostgreSQL container `langear-staging-dev-postgres` holds `langear_legacy_snapshot` and
  is not on the active request path.
- Production backend is bound to `127.0.0.1:8000` and still runs the legacy
  `app.main:app` against `langear` at revision `a8f2d4c6e9b1`.
- For backend/database/container diagnosis, use the project-level `langear-debugger`
  skill.
- Do not use `dev.langear.cn` as the active staging entry; its DNS points at a different legacy frontend.

## Non-negotiable rules

- Develop in local task worktrees. Use staging for runtime verification and release acceptance; do not default to editing application code in the staging checkout.
- Only one task may use the shared staging runtime at a time. A push to `dev/staging` can switch it from source hot reload to a fixed release; check runtime ownership before pushing. Actions staging deploy/acceptance jobs share `langear-staging-runtime`; manual sessions must also coordinate with those jobs.
- Before syncing local work to staging, inspect **both** checkouts for branch, commit, staged changes, and unstaged changes. Preserve unrelated remote work; do not overwrite it or pull it into the local task.
- Never print secrets from `env/backend.env`, `env/review.env`, `backend/.env*`, database dumps, or FRP tokens.
- Do not run destructive database resets, refreshes, or production changes without explicit scope.
- Production deployment, production rollback, and production database changes always require explicit authorization, even if staging was already approved. Never approve or bypass the GitHub production Environment gate on the user's behalf without explicit release authorization.

## 1. Local development

Default local shape:

```text
Browser http://localhost:3002
  -> local Vite proxy
  -> http://127.0.0.1:8004/api/...
  -> local backend
  -> local PostgreSQL
```

Start or restart the local backend from the repo:

```bash
cd backend
secret=$(awk -F= '/^CORE_CONFIRMATION_SECRET=/{sub(/^CORE_CONFIRMATION_SECRET=/,""); print}' .env.development.local | tr -d '"' | head -1)
CORE_DATABASE_URL='postgresql+psycopg://damien@127.0.0.1:5432/langear_local' \
CORE_CONFIRMATION_SECRET="$secret" \
CORE_COOKIE_SECURE=false \
.venv/bin/uvicorn core.main:app \
  --host 127.0.0.1 --port 8004 --reload --log-level info \
  --env-file .env
```

`--env-file` does not override variables already present in the process environment, so the inline `CORE_DATABASE_URL` wins. The env file supplies API keys, OSS keys, and the default model. `CORE_CONFIRMATION_SECRET` is required and must be at least 32 characters; load it from `.env.development.local` without printing it.

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

After checking that staging is available, push the local branch; this starts CI and automatic staging deployment:

```bash
git push origin dev/staging
```

Watch the automatic run and confirm the deployed SHA rather than manually
syncing source or running `manage.py stage` after every push:

```bash
gh run list --workflow frontend-dev-deploy.yml --branch dev/staging --limit 5
gh run watch <RUN_ID> --exit-status
python3 scripts/release/manage.py status staging
```

A successful build alone is insufficient: inspect `deploy-staging`. Superseded
builds can succeed while their deployment step is skipped. A running release
does not update the server Git checkout, and checkout drift is not a reason to
copy source into a fixed release.

### Optional source sync for explicit dev hot reload

Use this only when the task needs the server checkout mounted as source. Normal
Actions releases need no source sync and no GitHub SSH authorization on staging.
The staging checkout currently cannot pull from GitHub over SSH; for this dev-only
path, use the Mac to transport commits:

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

New pushes to `dev/staging` deploy automatically after CI succeeds. Inspect the
Actions run and `current.json`; do not perform another Mac-mediated deployment.

To build manually from the current remote development branch:

```bash
gh workflow run frontend-dev-deploy.yml --ref dev/staging -f operation=release
gh run list --workflow frontend-dev-deploy.yml --branch dev/staging --limit 5
```

For a transient deployment failure, inspect the failed job and rerun just
`deploy-staging` in Actions (or `gh run rerun <RUN_ID> --job <JOB_ID>`), reusing
its existing manifest and image digests. Avoid rebuilding an already accepted
SHA: an existing release directory refuses changed manifests or tooling.
Rerunning an exact already-running release verifies health and identity without
recreating containers. The branch-head guard still skips superseded releases.

`manage.py stage --run <RUN_ID>` is a compatibility entry point: for a schema-3
registry release it downloads the small manifest and asks Actions to rerun
`deploy-staging`. Its current metadata guard requires the original run to have
succeeded; use the Actions failed-job rerun for a failed overall run. Schema-2
historical bundles retain the old archive transfer behavior.

Only record acceptance checks actually performed. Healthy containers and CI do
not establish that login, recording, ASR or feedback have passed user-flow
acceptance. The promotion workflow records checks after verifying the running
staging release; `manage.py approve --checks '<actual checks>'` remains available
for explicitly recording local acceptance evidence.

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

Use a new `dev/staging` push/manual release run, or rerun the current branch head's `deploy-staging` job with its existing manifest. `manage.py dev` only restores backend source hot reload; it does not restore release mode. Automatic deployment switches both frontend and backend and pauses hot reload.

## 4. Production release

Production reuses the exact staging image digests. Do not rebuild from a floating
branch, deploy frontend separately, or copy dev data to production.

After actual staging acceptance and an explicit production release request:

```bash
gh workflow run frontend-dev-deploy.yml --ref dev/staging \
  -f operation=promote \
  -f run_id=<SUCCESSFUL_RELEASE_RUN_ID> \
  -f 'checks=<actual completed acceptance steps and observed results>'
```

This dispatch reuses `.github/workflows/promote-release.yml` and performs:

1. Require a successful push/manual release build from `dev/staging` or `main`.
   Use the original build run ID that contains `langear-release-<SHA>`, not a
   previous promotion run ID.
2. Download only that run's manifest and check out its exact SHA for the tools.
3. Verify that staging is still running that immutable SHA, API/worker image
   IDs match, frontend SHA is correct, and database revision is unchanged.
4. Record the supplied real acceptance evidence and retain the exact manifest
   plus approval as `accepted-release-<SHA>`.
5. Wait at the `production` GitHub Environment required-reviewer gate.
6. After authorized human approval, production pulls the accepted digests and
   applies health checks and schema guards. Production jobs share
   `langear-production-runtime`.

The reusable workflow also exposes a direct `workflow_dispatch` entry point when
available in GitHub. The existing `frontend-dev-deploy.yml` promotion dispatch
above works with the current development branch workflow.

### GitHub configuration and credentials

Both `staging` and `production` Environments use `DEPLOY_HOST`, `DEPLOY_PORT`,
`DEPLOY_USER`, `DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS` secrets. Dedicated CI
keys and trusted host keys are provisioned; never upload a personal SSH key or
disable host-key verification. Branch policies allow `dev/staging` and `main`.
Production requires reviewer `XianDamien`; recheck the Environment protection
rules before relying on that gate. The old repository `DEV_DEPLOY_*` secrets are
not used by this pipeline.

CI uses `GITHUB_TOKEN` with package write permission to publish; deployment jobs
have package read permission. The host receives the short-lived token over stdin
and uses a temporary Docker auth directory, removed when the command finishes.
Do not print credentials, persist that token, or store it in command arguments.

### First production rollout is still a separate migration task

As verified on 2026-10-23, staging automatic deployment succeeded at `3f78ae4`
([run 39910399125](https://github.com/XianDamien/langear/actions/runs/39910399125)).
Promotion gate test
[39911047064](https://github.com/XianDamien/langear/actions/runs/39911047064)
reached waiting-for-approval and was cancelled without deploying production.
These are historical verification records; inspect live state for new releases.

Production still runs the legacy `app.main:app`. It lacks
`/srv/langear/prod/env/review.env` and the `langear-prod-review` network needed by
the core-only image/API/worker. Prepare production configuration, independent
core database provisioning/migration, backups, and recovery as a separately
explicitly authorized task. A configured workflow and passing staging do not
mean this first production rollout is ready. Do not bypass the schema checks.

### Compatibility CLI

`manage.py promote --sha <FULL_SHA>` reads an existing staging approval and prints
a plan. With `--execute`, schema-3 releases request the Actions promotion workflow
and still wait for its Environment approval; they do not directly deploy from
the Mac. Prefer the run-ID workflow dispatch above, which selects the original
build unambiguously. Schema-2 historical releases retain direct archive transfer
and require explicit production authorization. Production deployment does not
switch its Git checkout; runtime records and image IDs remain authoritative.

## 5. Rollback

```bash
python3 scripts/release/manage.py rollback staging
python3 scripts/release/manage.py rollback prod           # plan only
python3 scripts/release/manage.py rollback prod --execute # requires authorization
```

Rollback is currently a manual `manage.py`/SSH operation, not an Actions rollback job. Coordinate with in-flight Actions deployments before using it. Rollback restores the previous frontend and backend. It does not migrate or downgrade the database. If the schema changed, the script refuses the application rollback; prepare a separate database recovery plan.

## 6. Database migrations

Migration heads must equal the live database revision. Deploy scripts never migrate automatically.

Check before a release or after syncing a large batch:

```bash
# Live revision recorded in the release state
python3 scripts/release/manage.py status staging

# Code head inside the staging backend container
ssh zhaohui-staging-server '
  docker exec langear-staging-dev-backend \
    alembic -c alembic-core.ini heads
'
```

The command uses the container's configured working directory (`/app` in release
mode; `/workspace/backend` in dev mode). Do not force the dev path in a fixed image.

If the code head is ahead of the live revision, do not treat the deployment as ready. Prepare a backup, migration, and recovery plan as a separate authorized step. For a local check, run the isolated test script rather than pytest against a real database:

```bash
cd backend && uv run bash ../scripts/release/test-core.sh -q
```

## 7. Verification checklist

After an automatic release, explicit source sync, or mode switch:

- [ ] The intended Actions run built successfully and actually completed `deploy-staging` (not a superseded skip).
- [ ] Schema-3 manifest digests, running API/worker image IDs, `current.json`, and frontend `/release.json` agree on the intended release.
- [ ] `GET /health` returns `{"status":"healthy","service":"collection-core"}` on the target backend.
- [ ] Staging preview `/health` returns healthy.
- [ ] The container command and mounts match the intended mode (`/app` without `--reload` for release; `/workspace/backend` with `--reload` for dev).
- [ ] The changed file inside the container contains the expected content.
- [ ] The review worker is healthy, not just the API.
- [ ] The active staging backend resolves to `langear_staging`, not `langear_legacy_snapshot` or a retired test DB.
- [ ] `langear-dialogue-agent` is still running; the main staging backend uses it for dialogue.
- [ ] The database revision matches the code head.
- [ ] The frontend static SHA matches the intended release when testing UI.
- [ ] The AI provider/model in the runtime is the one you expect; do not assume Gemini.
- [ ] Local `3002` requests pass the origin check (or return `403` deliberately when testing the guard).

## 8. Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `A trusted Origin is required` | `CORE_ALLOWED_ORIGINS` lacks the browser origin | Add `http://localhost:3002` / `http://127.0.0.1:3002`, restart backend |
| Source synced but behavior unchanged | Runtime is a fixed release image | Push `dev/staging` for an automatic release; use source sync plus `manage.py dev` only for explicit hot-reload work |
| New prompt not used in staging | Backend/worker still run the image; or only one container was restarted | Check mounts and the file inside **both** backend and worker |
| Wrong model in a rerun | The script loaded a different env file or inherited a stale process env | Inspect the running process env; do not assume the file you intended won |
| `git push staging-dev dev/staging` refused | Staging branch is checked out | Push to a temp ref and `git merge --ff-only` on the server |
| Staging cannot fetch source from GitHub | No GitHub SSH auth on staging | Normal releases pull GHCR images and need no checkout fetch; only explicit dev hot reload needs commit transport via `staging-dev` |
| Release aborts on schema mismatch | Code Alembic head ≠ live DB revision | Stop; prepare a migration/recovery plan |
| Staging preview UI is stale | Dev mode keeps the last static frontend, or an old automatic run was skipped | Use local Vite or inspect the latest `dev/staging` release and served `/release.json` |
| Worker unhealthy but API healthy | Hanging provider call; heartbeat stale | Check `/tmp/langear-review-worker.heartbeat`, restart the worker, then isolate the stuck `processing_outbox` job; see `langear-debugger` |
| Staging DB looks empty or wrong | Connected to `langear_legacy_snapshot` or a retired test DB | Check `CORE_DATABASE_URL` in `env/review.env`; active DB is `langear_staging` |
| CI passed but staging did not change | Only build passed, run was on `main`, or branch-head guard skipped an old SHA | Check event/ref and the actual deployment step; inspect `current.json` |
| `Refusing to overwrite release file` | A rerun rebuilt the same SHA with different image/tooling metadata | Reuse the original manifest/deploy job; publish changed code under a new commit |
| Production job waits indefinitely | Required reviewer gate | Wait for explicit authorized human approval; do not bypass it |
| Registry pull or SSH authentication fails | Missing Environment secrets, package access, connectivity, or host-key mismatch | Check the target Environment, GHCR access and trusted host key; never log credentials |
| Auto deployment interrupts dev hot reload | Both use the same shared staging runtime | Coordinate runtime ownership before push or manual mode switches; Actions concurrency does not reserve human dev sessions |
| First production core rollout fails preflight | Legacy production has no core env/network/schema | Prepare the separately authorized configuration/database migration; do not weaken release guards |

## Key files

- `AGENTS.md` — repository rules and environment routing.
- `docs/operations/dev-prod-workflow.md` — environment background; its older Mac/tar release description predates this Actions migration. For current release commands use this skill and the workflow/scripts.
- `scripts/release/manage.py` — status, explicit dev/rollback/approval operations and compatibility stage/promote commands.
- `scripts/release/host.py` — server-side deployment, overlay, health, and rollback logic.
- `.github/workflows/frontend-dev-deploy.yml` — tests, cached image builds, GHCR publish, automatic staging deployment and promotion dispatch.
- `.github/workflows/promote-release.yml` — exact-build resolution, staging acceptance, production approval gate and same-digest promotion.
- `scripts/release/actions.py` — Actions SSH transport for metadata/tooling and short-lived registry credentials.
- `scripts/release/registry.py` — schema-3 release manifest generation.
- `scripts/release/Dockerfile.frontend` — packages the already-tested frontend dist without a second build.
- `scripts/release/test_registry.py` and `test_release.py` — registry and historical bundle regression checks.
- `compose/docker-compose.yml` and `compose/release.override.yml` on the staging/prod host — source-mount vs fixed-image runtime contract.
- `.agents/skills/langear-debugger/SKILL.md` — current database/container map and backend troubleshooting.
