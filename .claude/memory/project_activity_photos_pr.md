---
name: Activity photos PR status
description: State of feature/activity-photos branch and open investigation into full-suite test failures
type: project
---

## PR #59 MERGED: feature/activity-photos → dev

**Branch:** `feature/activity-photos`  
**Last commit:** 5d2247a — "test: add photo tests for feature #34 (storage, resize, router)"  
**CI:** Run 91 passed (SHA 5d2247a3, conclusion: success)  
**Issue:** #34 pinned as active

## What was shipped in this branch

- `POST/GET/DELETE /{activity_id}/photos` endpoints
- `_resize_to_jpeg()` — Pillow resize to 2048px max, JPEG encode 85%
- Frontend: photos collapsible section, auto-expands when photos exist
- `AbandonedDrawdownView`: full design with desaturation overlay at abandon %, amber banner
- Bug fixes: setQueryData updater fn (multi-upload), photos merge pattern (step/jump/rename cache)
- 26 new tests: TestActivityPhoto (storage), TestResizeToJpeg (unit), TestActivityPhotos (15 router integration)
- Coverage: 70% (up from 67%)

## Open investigation: local full-suite failures

When we ran `conda run -n weaving_site python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -20` (task bzegrd28f), the output showed:

```
12 failed, 210 passed, 1 skipped, 1 warning, 87 errors in 583.69s
```

Failing tests:
- `test_looms.py::TestUpdateLoom` (4 tests errored)
- `test_looms.py::TestDeleteLoom` (4 tests errored)
- `test_projects.py::TestGetDrawdown` (9 tests errored)

**Key finding:** Both failing tests pass when run in isolation. This is a pre-existing DB isolation issue — likely async teardown race conditions where FK violations occur mid-truncate.

**Evidence these are NOT caused by our changes:**
- CI run 91 passed on the pushed commit
- We did not touch test_looms.py, test_projects.py, looms router, or projects router
- Tests pass in isolation

**Next step when resuming:**
Run the failing groups together to confirm they're flaky:
```bash
conda run -n weaving_site python -m pytest backend/tests/routers/test_looms.py::TestUpdateLoom backend/tests/routers/test_looms.py::TestDeleteLoom backend/tests/routers/test_projects.py::TestGetDrawdown -v --tb=short
```
If they pass: failures are non-deterministic, PR is good to merge.  
If they fail: investigate the error message — likely a FK violation in DB teardown, which is a pre-existing conftest issue.

**Why:** User needed to shut down before this investigation completed.  
**How to apply:** Resume by running the targeted test command above. If clean, merge PR #59 into dev.
