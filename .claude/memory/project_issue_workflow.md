---
name: Gitea issue tracking workflow
description: Active workflow for tracking planned tasks as Gitea issues; query at session start instead of reading STATUS.md
type: project
---

# Gitea Issue Tracking Workflow

Planned work is tracked as [Gitea issues](http://10.10.10.90:3000/gx1400/weaving_site/issues). Migration from STATUS.md is complete as of 2026-04-25.

**Why:** STATUS.md task lists are static and require manual editing. Gitea issues are filterable, labelable, and linkable to PRs. Claude can read/write them programmatically.

**How to apply:** At the start of each session, query open issues (see below) to understand current priorities. Do NOT read STATUS.md for the task list — it only contains a link to Gitea now.

---

## Label taxonomy

| Label | ID | Color | Purpose |
| --- | --- | --- | --- |
| `P1` | 1 | red `#d73a4a` | Critical — ships in current session |
| `P2` | 2 | orange `#e4751f` | High — next up |
| `P3` | 3 | yellow `#f9d0c4` | Medium — planned |
| `P4` | 4 | light gray `#e4e669` | Low — someday |
| `feature` | 5 | blue `#0075ca` | New user-facing capability |
| `bug` | 6 | red `#d73a4a` | Something broken |
| `test` | 7 | green `#2ea44f` | Coverage gap or test-only work |
| `refactor` | 8 | purple `#6f42c1` | Internal cleanup, no UX change |
| `blocker` | 9 | dark red `#b60205` | Blocks another issue |
| `infra` | 10 | gray `#e4e4e4` | CI, Docker, tooling, dependencies |
| `phase-2` | 11 | light blue `#bfdadc` | Deferred — not this cycle |
| `in-progress` | 13 | teal `#00aabb` | Actively being worked on right now |

The `in-progress` label is a single-issue tracker: remove it from the old issue and add it to the new one when retargeting work.

---

## How Claude queries issues at session start

```bash
GITEA_TOKEN=$(grep GITEA_TOKEN_ISSUES .env.local | cut -d= -f2 | tr -d '[:space:]')
# Show open non-phase-2 issues ordered by label priority
curl -s "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues?state=open&type=issues&limit=30" \
  -H "Authorization: token $GITEA_TOKEN" \
  | python -c "import sys,json; issues=json.load(sys.stdin); [print(f'#{i[\"number\"]} [{\" \".join(l[\"name\"] for l in i[\"labels\"])}] {i[\"title\"]}') for i in issues if not any(l[\"name\"]==\"phase-2\" for l in i[\"labels\"])]"
```

## How Claude moves the in-progress label

```bash
GITEA_TOKEN=$(grep GITEA_TOKEN_ISSUES .env.local | cut -d= -f2 | tr -d '[:space:]')
OLD=<old_issue_number>
NEW=<new_issue_number>
# Remove from old
curl -s -X DELETE "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues/$OLD/labels/13" \
  -H "Authorization: token $GITEA_TOKEN"
# Add to new
curl -s -X POST "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues/$NEW/labels" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"labels\":[13]}"
```

## How Claude creates an issue

```bash
curl -s -X POST "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"<title>\",\"body\":\"<body>\",\"labels\":[<label_id_list>]}" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('html_url') or json.dumps(d,indent=2))"
```

## How Claude closes an issue

```bash
curl -s -X PATCH "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues/<number>" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"state\":\"closed\"}"
```
