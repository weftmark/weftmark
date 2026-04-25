#!/usr/bin/env python
"""
SessionStart hook — injects two blocks of context at the start of every session:

1. Open 'process' label issues: workflow directives and instructions from gx1400.
   These take precedence over default behaviour — always read and apply them.

2. The current in-progress issue + its last 10 comments, so Claude knows exactly
   what task is active and what has been discussed.

Gitea unreachable → exits 0 silently (hook must not block the session).
"""
import json
import sys
import urllib.request


def load_token(path=".env.local"):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("GITEA_TOKEN_ISSUES="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def gitea_get(path, token):
    url = f"http://10.10.10.90:3000/api/v1{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def main():
    token = load_token()
    if not token:
        sys.exit(0)

    issues = gitea_get(
        "/repos/gx1400/weaving_site/issues?state=open&type=issues&limit=50", token
    )
    if not issues:
        sys.exit(0)

    lines = []

    # --- 1. Open process issues (workflow directives) ---
    process_issues = [
        i for i in issues if any(l["name"] == "process" for l in i["labels"])
    ]
    if process_issues:
        lines += ["## Workflow directives (process issues — apply these)", ""]
        for pi in process_issues:
            labels = " ".join(l["name"] for l in pi["labels"])
            lines += [f"### #{pi['number']} [{labels}] {pi['title']}", ""]
            body = (pi.get("body") or "").strip()
            if body:
                lines += [body, ""]
            comments = gitea_get(
                f"/repos/gx1400/weaving_site/issues/{pi['number']}/comments", token
            ) or []
            if comments:
                recent = comments[-5:]
                for c in recent:
                    lines += [f"**{c['user']['login']} ({c['updated_at'][:10]}):**",
                               c["body"].strip(), ""]

    # --- 2. Active in-progress issue + comments ---
    in_progress = [
        i for i in issues if any(l["name"] == "in-progress" for l in i["labels"])
    ]
    if in_progress:
        issue = in_progress[0]
        number = issue["number"]
        title = issue["title"]
        labels = " ".join(l["name"] for l in issue["labels"])
        body = (issue.get("body") or "").strip()

        comments = gitea_get(
            f"/repos/gx1400/weaving_site/issues/{number}/comments", token
        ) or []

        lines += [f"## Active issue: #{number} [{labels}] {title}", ""]
        if body:
            lines += [body, ""]
        if comments:
            recent = comments[-10:]
            lines.append(f"### Recent comments ({len(recent)} of {len(comments)})")
            lines.append("")
            for c in recent:
                user = c["user"]["login"]
                date = c["updated_at"][:10]
                lines += [f"**{user}** ({date}):", c["body"].strip(), ""]

    if not lines:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines)
        }
    }))


main()
