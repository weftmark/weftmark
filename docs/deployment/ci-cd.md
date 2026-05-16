# WeftMark — CI/CD Pipeline Reference

Complete reference for all GitHub Actions workflows: triggers, jobs, and purpose.

---

## Overview

| Workflow | File | Trigger | Purpose |
| --- | --- | --- | --- |
| Feature CI | `ci-feature.yml` | push `feature/*`, `fix/*` | Lint + typecheck |
| Dev PR gate | `ci-dev-pr.yml` | PR to `dev` | Full suite — the merge gate |
| Dev push | `ci-dev-push.yml` | push to `dev` | SBOM update + version bump |
| Hotfix CI | `ci-hotfix.yml` | push `hotfix/*` | Full suite + dep audit + docker build |
| Main PR gate | `ci-main-pr.yml` | PR to `main` | Lint, typecheck, dep audit, docker build |
| Main push | `ci-main-push.yml` | push to `main` | Tag release + SBOM update |
| Merge source check | `check-merge-source.yml` | PR to `main` | Enforces source must be `dev` or `hotfix/*` |
| Publish dev | `publish-dev.yml` | Manual dispatch | Build + push `:dev` image → Komodo deploy |
| EULA sync | `sync-eula.yml` | Manual dispatch | Export EULA content and open a sync PR |
| Main→dev sync | `sync-main-to-dev.yml` | push to `main` | Open PR to backport main changes to dev |
| Issue triage | `triage.yml` | issue opened | Apply `needs-triage` label automatically |

---

## Bot Actor

Bot commits and automated PRs are authored by `weftmark-bot[bot]`. Jobs that must not re-run after bot commits guard with:

```yaml
if: github.actor != 'weftmark-bot[bot]'
```

**Do not use `[skip actions]`** — that token suppresses CI on the PR target branch, breaking the merge gate.

---

## Workflow Details

### `ci-feature.yml` — Feature / Fix Branch CI

**Trigger:** push to `feature/*` or `fix/*`

**Jobs:**

| Job | What it does |
| --- | --- |
| `lint-backend` | `ruff check` + `ruff format --check` |
| `lint-frontend` | `npm run lint` (ESLint) |
| `typecheck-frontend` | `tsc -b --noEmit` |

Failures here block the developer early — before opening a PR. Does not run pytest (that lives in the PR gate).

---

### `ci-dev-pr.yml` — Dev PR Gate (Merge Gate)

**Trigger:** pull request targeting `dev`

This is the primary merge gate. All jobs must pass before merging to `dev`.

**Jobs:**

| Job | What it does |
| --- | --- |
| `lint-backend` | `ruff check` + `ruff format --check` |
| `lint-frontend` | `npm run lint` |
| `typecheck-frontend` | `tsc -b --noEmit` |
| `test-backend` | `pytest` against a real PostgreSQL instance (spun up as a service) |
| `migration-check` | `alembic upgrade head` on a clean database — verifies migrations run clean |
| `dep-audit-backend` | `pip-audit` — known CVEs in Python dependencies |
| `dep-audit-frontend` | `npm audit` — known CVEs in npm dependencies |

Tests do not re-run after the merge commit — the PR gate result is the authoritative signal.

---

### `ci-dev-push.yml` — Dev Branch Post-Merge

**Trigger:** push to `dev` (fires after every merge, excluding bot commits)

**Jobs:**

| Job | What it does |
| --- | --- |
| `sbom-backend` | Detects `requirements.txt` changes; regenerates backend SBOM and license manifest; commits via bot |
| `sbom-frontend` | Detects `package.json` / `package-lock.json` changes; regenerates frontend SBOM; commits via bot |
| `version-bump` | Increments `VERSION` and `frontend/package.json` patch version; commits via bot |

Bot commits from this workflow are the reason you must `git pull origin dev` before starting any new work — the VERSION file will conflict otherwise.

---

### `ci-hotfix.yml` — Hotfix Branch CI

**Trigger:** push to `hotfix/*`

Runs the full suite (same as `ci-dev-pr.yml`) plus a Docker build validation. Hotfixes bypass the dev branch and go directly to `main`, so the CI gate here must be equivalent to the dev PR gate.

**Jobs:** lint-backend, lint-frontend, typecheck-frontend, test-backend, migration-check, dep-audit-backend, dep-audit-frontend, docker-build.

---

### `ci-main-pr.yml` — Main PR Gate

**Trigger:** pull request targeting `main`

No file writes are permitted in this workflow (guarded by a separate scan job). Source must come from `dev` or `hotfix/*` (enforced by `check-merge-source.yml`).

**Jobs:**

| Job | What it does |
| --- | --- |
| `check-write-commands` | Scans `ci-main-push.yml` for forbidden file-write commands |
| `lint-backend` | `ruff check` + `ruff format --check` |
| `lint-frontend` | `npm run lint` |
| `typecheck-frontend` | `tsc -b --noEmit` |
| `dep-audit-backend` | `pip-audit` |
| `dep-audit-frontend` | `npm audit` |
| `docker-build` | Full `docker compose build` validation (no push) |

pytest is intentionally omitted — it already ran in `ci-dev-pr.yml` or `ci-hotfix.yml`. Running it again on `main` would add minutes with no new signal.

---

### `check-merge-source.yml` — Merge Source Enforcement

**Trigger:** pull request targeting `main`

Fails if the source branch is anything other than `dev` or `hotfix/*`. Prevents feature branches from being merged directly to production.

---

### `ci-main-push.yml` — Main Post-Merge

**Trigger:** push to `main` (fires after merge, excluding bot commits)

**Jobs:**

| Job | What it does |
| --- | --- |
| `tag-release` | Creates an annotated git tag `v{VERSION}` via GitHub API (idempotent; produces a verified tag) |
| `sbom-backend` | Regenerates backend SBOM on package changes; bot commits |
| `sbom-frontend` | Regenerates frontend SBOM on package changes; bot commits |

---

### `publish-dev.yml` — Publish Dev Images

**Trigger:** manual workflow dispatch (from GitHub Actions → publish-dev.yml → Run workflow)

**Jobs:**

| Job | What it does |
| --- | --- |
| `build-push-backend` | Builds backend Docker image, pushes `ghcr.io/weftmark/weftmark-backend:{version}-dev` and `:dev` |
| `build-push-frontend` | Builds frontend Docker image, pushes `ghcr.io/weftmark/weftmark-frontend:{version}-dev` and `:dev` |
| `create-qa-issue` | Opens a GitHub issue with a QA checklist for the dev deployment |

After publish completes, trigger the Komodo deploy webhook to pull the new `:dev` image to `dev.weftmark.com`.

---

### `sync-main-to-dev.yml` — Backport Sync

**Trigger:** push to `main`

If `main` has commits not present in `dev` (e.g., a hotfix merge or bot tag commit), this workflow opens a backport PR from `main` → `dev` automatically.

---

### `sync-eula.yml` — EULA Content Sync

**Trigger:** manual workflow dispatch

Exports the current EULA markdown content, commits it to a branch, and opens a PR. Used when the EULA text changes independently of a feature.

---

### `triage.yml` — Issue Auto-Labeling

**Trigger:** issue opened

Applies the `needs-triage` label to every newly opened issue automatically, so nothing falls through without review.

---

## Image Tags

| Git event | Backend image tag | Frontend image tag | Destination |
| --- | --- | --- | --- |
| Manual (`publish-dev.yml`) | `:dev`, `:{version}-dev` | `:dev`, `:{version}-dev` | `dev.weftmark.com` via Komodo |
| Manual (`publish-staging`) | `:staging`, `:{version}-rc` | `:staging`, `:{version}-rc` | `staging.weftmark.com` via Komodo |
| Push to `main` (via Komodo) | `:latest`, `:{version}` | `:latest`, `:{version}` | `weftmark.com` via Komodo |

Registry: `ghcr.io/weftmark/weftmark-backend` and `ghcr.io/weftmark/weftmark-frontend`

---

## Branch → CI Flow

```
feature/* or fix/*
    push → ci-feature.yml (lint + typecheck)
    PR to dev → ci-dev-pr.yml (full gate)
    merge → ci-dev-push.yml (SBOM + version bump)
    manual → publish-dev.yml (image build + deploy)

hotfix/*
    push → ci-hotfix.yml (full gate + docker build)
    PR to main → ci-main-pr.yml + check-merge-source.yml
    merge → ci-main-push.yml (tag + SBOM)
              sync-main-to-dev.yml (backport PR)

dev → main
    PR → ci-main-pr.yml + check-merge-source.yml
    merge → ci-main-push.yml (tag + SBOM)
              sync-main-to-dev.yml
```

---

## Secrets Required

| Secret | Used by | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | All workflows | Default GitHub token (auto-provided) |
| `BOT_APP_ID` + `BOT_APP_PRIVATE_KEY` | Bot-commit workflows | Generate bot tokens to bypass branch protection |
| `GHCR_PAT` | `publish-dev.yml` | Push images to ghcr.io |
| `POSTGRES_PASSWORD` | `ci-dev-pr.yml`, `ci-hotfix.yml` | Run pytest against a real database |

---

## Merge Gates Summary

| Gate | Where | Required to pass |
| --- | --- | --- |
| Feature → dev | `ci-dev-pr.yml` | lint, typecheck, pytest, migration, dep audit |
| Hotfix → main | `ci-hotfix.yml` + `ci-main-pr.yml` | full suite + docker build |
| Dev → main | `ci-main-pr.yml` + `check-merge-source.yml` | lint, typecheck, dep audit, docker build, source check |
