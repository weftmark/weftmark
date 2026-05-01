# WeftMark — Claude Code Instructions

## Project overview

WeftMark is a multi-user web platform for managing weaving (loom) projects. All projects are private by default. Users can self-register via Clerk but are blocked until an admin approves them.

- Requirements: `docs/requirements/` (start with `docs/requirements/README.md`)
- WIF 1.1 spec: `docs/standard/standard-wif1-1.txt`
- Sample WIF files: `docs/samples/`

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + React Router |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | PostgreSQL (Neon managed in prod, local container in dev) |
| Task queue | Celery + Redis |
| Auth | Clerk (OIDC). Backend reads `Authorization: Bearer` header — NOT cookies. |
| Deployment | Docker + Docker Compose, monorepo |

## Auth

Backend reads `Authorization: Bearer` header. All API modules must use `client.ts`'s `configureApiClient(getToken)` path; never raw `fetch()` without a Bearer header.

Binary/image endpoints (photos, drawdown, preview) use the `AuthedImage` component (fetch → blob URL) — `<img src>` can't carry Bearer headers. File downloads use `downloadAuthed()`.

## Infrastructure

- **Domain/DNS/SSL:** Cloudflare (registrar + proxy). Origin CA cert with Full (strict) mode. No Certbot needed.
- **Object storage:** Cloudflare R2 (S3-compatible; use `STORAGE_BACKEND=s3` / boto3; zero egress fees)
- **Reverse proxy:** nginx with CrowdSec bouncer → containers
- **Database:** PostgreSQL. Production uses a managed DSN — set `POSTGRES_DSN` in `.env`; individual `POSTGRES_*` vars are ignored when DSN is set. Dev uses a local Postgres container.
- **Container registry:** `ghcr.io/weftmark/weftmark-backend` and `ghcr.io/weftmark/weftmark-frontend`
- **Source:** `https://github.com/weftmark/weftmark` (org: `weftmark`, owner: `gx1400`)
- **Email:** `admin@weftmark.com` / `feedback@weftmark.com` for SMTP config

## Git workflow

Three tiers: `main` (production-ready), `dev` (integration), working branches (`feature/*`, `fix/*`).

### Normal path (feature or fix)

- Branch from `dev`: `git checkout dev && git checkout -b feature/<name>` or `fix/<name>`
- PR targets `dev` — always pass `--base dev` to `gh pr create`
- Never commit directly to `main` or `dev`

### Hotfix path

- `hotfix/*` branches from `main` and targets `main` directly
- `check-merge-source.yml` enforces that only `dev` and `hotfix/*` may open PRs to `main`
- After merging to `main`, backport the fix to `dev` as a follow-up PR

**Merge gate — feature/fix → dev:** unit tests written, pytest passes, tsc clean, golden path verified in browser, no regressions.

**Merge gate — dev → main:** all feature gates plus full smoke-test (auth login, core CRUD, activities), pytest passes, no known open bugs.

**When to suggest a commit:** After each feature passes end-to-end testing and pytest. Don't commit speculatively mid-feature.

## CI/CD

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `ci-feature.yml` | push to `feature/*`, `fix/*` | lint + typecheck (fast feedback) |
| `ci-hotfix.yml` | push to `hotfix/*` | full suite (lint, typecheck, pytest, migration, dep audit, docker build) |
| `ci-dev-pr.yml` | PR to `dev` | full suite — this is the gate; tests don't re-run after merge |
| `ci-dev-push.yml` | push to `dev` | SBOM update + semver version bump (bot commits, skipped if actor is bot) |
| `ci-main-pr.yml` | PR to `main` | lint, typecheck, dep audit, docker build; **no file writes allowed** |
| `ci-main-push.yml` | push to `main` | promote version tag, SBOM artifacts, publish versioned + `:latest` images |
| `check-merge-source.yml` | PR to `main` | enforces source must be `dev` or `hotfix/*` |
| `publish-dev.yml` | manual dispatch | publishes `:dev` + `:{version}-dev` images to ghcr.io |

After every push, check CI status proactively: `gh run list --repo weftmark/weftmark --limit 3`. If failed, pull logs with `gh run view <id> --log-failed` and surface errors immediately.

Bot actor: `weftmark-bot[bot]`. Post-merge jobs use `if: github.actor != 'weftmark-bot[bot]'` to prevent infinite re-triggering. Bot commits use `[skip actions]` in the message.

Append `[skip ci]` to commit messages for documentation-only changes (`.md` files, comments) to avoid unnecessary CI runs.

## Development rules

### Pull before starting work

Always `git pull origin <branch>` at the start of every session. The CI bot commits version bumps directly to branches — skip this and pushes will conflict on `VERSION` / `frontend/package.json`.

### Rebuild both services together

Always rebuild frontend AND backend together. Never rebuild just one.

```bash
docker compose -f docker-compose.build.yml --env-file .env.local stop frontend backend worker
docker compose -f docker-compose.build.yml --env-file .env.local build frontend backend
docker compose -f docker-compose.build.yml --env-file .env.local up -d frontend backend worker
```

The running `frontend-1` container is nginx-only — no `node`, `npm`, or build tools inside it. Never run `docker compose exec frontend npm ...`.

### Test-first development

Before implementing any new feature: write tests first, run them (confirm fail), implement until they pass. Commit feature + tests together.

- Backend tests: `backend/tests/` mirroring `app/` structure (e.g. `app/services/foo.py` → `tests/services/test_foo.py`)
- After each feature, update `docs/testing.md` (coverage %, gap table, history row)

### Environment files on package install

When any package is installed (pip, npm, conda), regenerate in the same commit:
- `environment.yml` — `conda run -n weaving_site conda env export --no-builds > environment.yml`
- `.nvmrc` — `node --version` (only when Node version changes)

### Single bash commands

Issue each command as a separate tool call — never chain with `&&` or `;`. Allows per-command session approval.

## PR workflow

1. Claude implements the feature and opens the PR (`gh pr create --base dev`)
2. The developer reviews on GitHub and works through the test plan
3. The developer merges

Claude's role ends at opening the PR. Never run `gh pr merge`.

### PR scope

One PR = one topic (one feature, one fix, one refactor). If a fix is discovered incidentally, note it and handle it in a separate PR.

## Collaboration style

- Ask questions one at a time — single most important question, wait for the answer
- Give clear recommendations with reasoning, not balanced option lists
- Deferred/phase 2 features go in `docs/requirements/phase2.md`

## Allowed bash patterns (add to .claude/settings.json if permission prompts become disruptive)

```
Bash(docker compose *)
Bash(docker cp *)
Bash(conda run *)
Bash(git add *)
Bash(git commit *)
Bash(git push *)
Bash(git pull *)
Bash(git fetch *)
Bash(git checkout *)
Bash(git stash *)
Bash(npx tsc *)
Bash(npm run *)
Bash(gh run *)
Bash(gh pr *)
Bash(curl -s http://localhost:*)
Bash(python -c ' *)
```
