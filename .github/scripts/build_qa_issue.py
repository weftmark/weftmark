"""Generate a QA issue body for a dev build.

Reads VERSION and REPO from environment variables set by the workflow.
Writes the issue body to qa_issue_body.md in the current directory.
"""

import json
import os
import re
import subprocess

version = os.environ["VERSION"]
repo = os.environ["REPO"]
current_tag = f"v{version}-dev"

# All dev tags sorted oldest to newest
tags = subprocess.run(
    ["git", "tag", "--list", "v*-dev", "--sort=version:refname"],
    capture_output=True,
    text=True,
).stdout.strip().splitlines()
tags = [t for t in tags if t]

prev_tag = None
for i, tag in enumerate(tags):
    if tag == current_tag and i > 0:
        prev_tag = tags[i - 1]
        break

# Merge commits in range
if prev_tag:
    log = subprocess.run(
        ["git", "log", f"{prev_tag}..HEAD", "--merges", "--pretty=format:%s"],
        capture_output=True,
        text=True,
    ).stdout
else:
    log = subprocess.run(
        ["git", "log", "--merges", "--pretty=format:%s", "--max-count=40"],
        capture_output=True,
        text=True,
    ).stdout

pr_numbers = re.findall(r"#(\d+)", log)
seen: set[str] = set()
unique_prs: list[str] = []
for p in pr_numbers:
    if p not in seen:
        seen.add(p)
        unique_prs.append(p)

sections = []
for pr_num in unique_prs:
    result = subprocess.run(
        ["gh", "pr", "view", pr_num, "--json", "title,body", "--repo", repo],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        continue
    pr = json.loads(result.stdout)
    title = pr.get("title", f"PR #{pr_num}")
    body = pr.get("body") or ""
    m = re.search(r"## Test plan\n(.*?)(?=\n## |\Z)", body, re.DOTALL | re.IGNORECASE)
    plan = m.group(1).strip() if m else "_No test plan specified._"
    sections.append(f"### #{pr_num} — {title}\n\n{plan}")

range_label = f"`{prev_tag}..HEAD`" if prev_tag else "_(no previous dev tag)_"
pr_block = "\n\n---\n\n".join(sections) if sections else "_No merged PRs found in range._"

issue_body = f"""## Dev build v{version}

**Images**
- `ghcr.io/weftmark/weftmark-backend:{version}-dev`
- `ghcr.io/weftmark/weftmark-frontend:{version}-dev`

**Range:** {range_label}

---

{pr_block}

---

_Close this issue when all items above are validated on `dev.weftmark.com`._"""

with open("qa_issue_body.md", "w") as f:
    f.write(issue_body)

print(f"QA issue body written ({len(sections)} PR(s) included)")
