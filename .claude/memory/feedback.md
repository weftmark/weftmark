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

## All memories live in the repo

**Rule:** All project memories must be saved in `.claude/memory/` inside the repo (`d:/repos/weaving_site/.claude/memory/`), not in `~/.claude/projects/`.

**Why:** The user wants memories version-controlled with the project so they travel with the repo and are visible in git history.

**How to apply:** Write memory files to `d:/repos/weaving_site/.claude/memory/` and update `MEMORY.md` there. Never write project memories to the home-dir path.
