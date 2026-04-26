"""Handler for Gitea issues events (open/close/label/etc)."""

import logging

from claude_runner import run_claude

log = logging.getLogger(__name__)

TRIAGE_PROMPT = """\
You are an automated issue triager for the weaving_site repository.

A new issue was just opened:

Issue #{number}: {title}
Author: {author}

Body:
{body}

Available labels in this repo (use exact names):
  Priority: P1, P2, P3, P4
  Type: feature, bug, docs, process, phase-2
  Status: in-progress

Your tasks:
1. Read the issue carefully.
2. Apply appropriate labels via the Gitea API:
   POST {gitea_base_url}/api/v1/repos/{gitea_repo}/issues/{number}/labels
   Body: {{"labels": [<label_id>, ...]}}
   Use GET {gitea_base_url}/api/v1/repos/{gitea_repo}/labels to look up label IDs first.
3. Post a brief comment on the issue acknowledging it and explaining the labels chosen.
   If it is a feature request, note whether it fits Phase 1 or should be deferred to phase-2.
   If it is a bug, ask for reproduction steps if missing.

Be concise. Do not over-promise delivery timelines.

Gitea base URL: {gitea_base_url}
Repo: {gitea_repo}
Token for API calls (Authorization: token <value>): {gitea_token}
"""


async def handle(payload: dict) -> None:
    action = payload.get("action")
    issue = payload.get("issue", {})
    number = issue.get("number")
    title = issue.get("title", "")
    author = issue.get("user", {}).get("login", "unknown")

    if author == "claude_vscode":
        log.info("issues #%s by claude_vscode — skipped", number)
        return

    log.info("issues action=%s #%s '%s' by %s", action, number, title, author)

    if action != "opened":
        log.info("issues action=%s — no handler", action)
        return

    from config import settings

    prompt = TRIAGE_PROMPT.format(
        number=number,
        title=title,
        author=author,
        body=(issue.get("body") or "").strip()[:1200],
        gitea_base_url=settings.gitea_base_url,
        gitea_repo=settings.gitea_repo,
        gitea_token=settings.gitea_token,
    )
    response = await run_claude(prompt, allowed_tools="Bash,Read,Glob,Grep")
    log.info("issue triage posted for #%s (%d chars)", number, len(response))
