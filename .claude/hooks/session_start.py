#!/usr/bin/env python
"""
SessionStart hook — injects the current in-progress Gitea issue + recent
comments into Claude's context so every session starts aware of active work.
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
        "/repos/gx1400/weaving_site/issues?state=open&type=issues&limit=30", token
    )
    if not issues:
        sys.exit(0)

    in_progress = [
        i for i in issues if any(l["name"] == "in-progress" for l in i["labels"])
    ]
    if not in_progress:
        sys.exit(0)

    issue = in_progress[0]
    number = issue["number"]
    title = issue["title"]
    labels = " ".join(l["name"] for l in issue["labels"])
    body = (issue.get("body") or "").strip()

    comments = gitea_get(
        f"/repos/gx1400/weaving_site/issues/{number}/comments", token
    ) or []

    lines = [f"## Active issue: #{number} [{labels}] {title}", ""]
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

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines)
        }
    }))


main()
