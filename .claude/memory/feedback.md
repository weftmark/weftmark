# Collaboration Feedback

## Ask questions one at a time

**Rule:** When gathering requirements or clarifying features, ask one question at a time — not a list.

**Why:** The user wants to answer each question fully and elaborate with context. A list of questions short-circuits that.

**How to apply:** In any requirements or design discussion, pick the single most important open question and ask only that. Wait for the answer before asking the next.

## Recommendations over options when asked

**Rule:** When the user asks "what do you recommend?" or "talk me through the options," give a clear recommendation with reasoning, not a balanced list with no conclusion.

**Why:** The user wants to make a decision, not read a comparison table. They can redirect if they disagree.

**How to apply:** Lead with the recommendation, then explain why. Note the tradeoff briefly. Don't hedge.

## Document deferred features explicitly

**Rule:** When the user says something is a future/phase 2 feature, record it in `docs/requirements/phase2.md` with enough context to implement it later (what, why deferred, any architectural constraints).

**How to apply:** Any time a feature is deferred, add it to phase2.md before moving on.

## Git workflow and branching

**Rule:** Use a three-tier Git workflow: `main` (production-ready), `dev` (integration), `feature/*` (one branch per feature branched from dev).

**Branch rules:**

- Always branch new features from `dev`, not `main`
- Feature branches named `feature/<short-descriptor>`
- Features merge into `dev` after passing their merge gate
- `dev` merges into `main` only after a full smoke-test pass
- Never commit directly to `main`

**Unit test requirement:** Every new feature must include unit tests covering its service/business logic. Tests live in `backend/tests/` mirroring the `app/` structure. Write tests as part of the feature, not as an afterthought.

**Merge gate — feature/* → dev:** unit tests written, pytest passes, tsc clean, golden path verified in browser, no regressions.

**Merge gate — dev → main:** all feature gates plus full smoke-test (auth login, core CRUD, activities), pytest passes across full suite, no known open bugs.

**When to suggest a commit:** After each feature passes end-to-end testing and pytest. Don't commit speculatively mid-feature.

**Why:** Unit tests catch regressions before they reach dev or main. main should always be releasable.

**How to apply:** Start every new feature with `git checkout dev && git checkout -b feature/<name>`. Write tests alongside the feature code. Run pytest before offering to merge.

## Always pull dev before starting work

**Rule:** Always run `git pull origin dev` (or the relevant branch) at the start of every session before making changes or pushing. Then rebuild and restart both frontend and backend.

**Why:** The CI runner commits version bumps directly to the branch after each successful push. If you don't pull first, pushes will be rejected or cause merge conflicts on `VERSION` and `frontend/package.json`.

**How to apply:** At the start of every session:

```bash
git pull origin dev
docker compose build frontend backend && docker compose up -d frontend backend
```

Check whether the runner action has completed before pulling if the session starts immediately after a push.

## Skip CI for documentation-only commits

**Rule:** Append `[skip ci]` to commit messages for documentation-only or non-functional changes.

**Why:** CI runs (and version bumps) are wasteful for changes that don't affect code behavior — e.g. STATUS.md updates, README edits, comment-only changes.

**How to apply:** Any commit that touches only documentation files (STATUS.md, README.md, *.md, comments) should include `[skip ci]` in the message. Example: `docs: update STATUS.md [skip ci]`

## Update STATUS.md and commit after each completed task

**Rule:** After completing each task:

1. Update STATUS.md — mark the task done, refresh the Next 10 Planned Tasks list
2. Commit STATUS.md with `[skip ci]` since it's a docs-only change
3. Pause to invite the user to confirm or clarify requirements for upcoming work

**Why:** Keeps project status accurate after each milestone without triggering CI. User wants to validate requirements incrementally rather than building ahead of a misunderstood spec.

**How to apply:** Every time a task is marked completed, immediately update and commit STATUS.md. Then signal it's a good checkpoint to review scope before proceeding.

## Regenerate environment lock files on package install

**Rule:** Any time a new package is installed (pip, npm, or conda), regenerate all three environment files and include them in the same commit as the dependency change.

Files to regenerate:

- `environment.yml` — `conda env export --no-builds` from the `weaving_site` conda env
- `backend/requirements-lock.txt` — `pip freeze` from the `weaving_site` conda env
- `.nvmrc` — `node --version` (only changes when Node version changes)

**Why:** User wants lock files kept in sync with the actual installed state so the repo can be reproduced exactly.

**How to apply:** After any `pip install`, `npm install`, or `conda install`, run the three export commands and stage the updated files alongside the dependency change before committing.

## Test-first development process

**Rule:** Before implementing any new feature, scope and write tests first. Run them to confirm they fail, then implement the feature until tests pass. Commit feature + tests together.

**Why:** User explicitly requested test-first development as a process requirement.

**How to apply:**

- Write tests in `tests/routers/` or `tests/models/` before writing the feature code
- After each feature, update `docs/testing.md` (coverage %, gap table, history row) and the coverage line near the top of `STATUS.md`
- Review existing tests for correctness and applicability after each change — remove stale tests
- Suggest coverage reassessment at natural breakpoints: after a router reaches ≥80%, before Phase 2, after a major refactor
- Coverage tracking file is `docs/testing.md`

## Proactively check CI status after pushes

**Rule:** After every push to Gitea, query the Actions API to check whether the triggered run passed or failed. If it failed, pull the job-level details and surface the error without being asked.

**Why:** User monitors CI manually and wants Claude to do that legwork — spotting failures and pulling failure details proactively rather than waiting to be asked.

**How to apply:**

- After pushing, poll `GET /api/v1/repos/gx1400/weaving_site/actions/runs?limit=3` until the new run appears as `completed`
- If `conclusion == "failure"`, fetch job details: `GET /api/v1/repos/gx1400/weaving_site/actions/runs/{run_id}/jobs`
- Read-only token is `GITEA_TOKEN_RO` in `.env.local`; read-write token is `GITEA_TOKEN_RW` — use RW for creating PRs and any write operations
- Gitea API base is `http://10.10.10.90:3000`
- When the user shows a failure traceback, use the same API to identify which job/step failed and pull context

## Creating a PR via the Gitea API

**Rule:** Always use this exact pattern. Do not deviate — previous variations caused silent failures or connection errors.

**Why:** `--data-raw` produces empty responses; port 3001 is refused; packages like `jq` or `gh` are not guaranteed to be in PATH on Windows.

**How to apply — exact working command:**

```bash
GITEA_TOKEN=$(grep GITEA_TOKEN_RW .env.local | cut -d= -f2 | tr -d '[:space:]')
curl -s -X POST "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/pulls" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"<title>\",\"head\":\"dev\",\"base\":\"main\",\"body\":\"<body with \\n for newlines>\"}" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('html_url') or json.dumps(d,indent=2))"
```

**Critical rules:**
- Use `-d` not `--data-raw` — `--data-raw` causes empty body and no response
- Port is **3000**, not 3001
- Escape newlines as `\\n` inside the `-d` JSON string (single-quoted heredocs don't work reliably on Windows bash)
- Parse response with inline `python -c` — Python via conda is always available; `jq` and `gh` are not
- Token extraction: `grep GITEA_TOKEN_RW .env.local | cut -d= -f2 | tr -d '[:space:]'`
- For CI status checks use `GITEA_TOKEN_RO` (read-only is sufficient)

## Rebuilding the frontend

**Rule:** The running `frontend-1` container is nginx-only — it has no `node`, `npm`, or build tools. Never run `docker compose exec frontend npm ...`.

**Why:** The frontend uses a multi-stage Dockerfile: Node builds in stage 1, the output is copied into an nginx image for stage 2. The running container is stage 2 only.

**How to apply — exact workflow:**

```bash
# Build new image (runs tsc + vite build inside Docker)
docker compose build frontend

# Restart container with new image
docker compose up -d frontend
```

If the build fails, the full error is in the `docker compose build` output — read it before retrying. Common causes: TypeScript errors, unused variables (TS6133), missing imports.

## All memories live in the repo

**Rule:** All project memories must be saved in `.claude/memory/` inside the repo (`d:/repos/weaving_site/.claude/memory/`), not in `~/.claude/projects/`.

**Why:** The user wants memories version-controlled with the project so they travel with the repo and are visible in git history.

**How to apply:** Write memory files to `d:/repos/weaving_site/.claude/memory/` and update `MEMORY.md` there. Never write project memories to the home-dir path.
