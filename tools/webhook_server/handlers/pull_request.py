"""Handler for Gitea pull_request events."""

import logging

from claude_runner import run_claude
from gitea import post_issue_comment

log = logging.getLogger(__name__)

REVIEW_PROMPT = """\
You are an automated code reviewer for the weaving_site repository.

A pull request was just opened:

PR #{number}: {title}
From: {head} → {base}
Author: {author}

Description:
{body}

Your task:
1. Fetch the diff using the Gitea API: GET {diff_url}
2. Review the changes for: correctness, test coverage, potential bugs, \
and consistency with the existing codebase style.
3. Post your review as a comment on PR #{number} using the Gitea issues API \
(PRs use the same comment endpoint as issues).

Be concise. Lead with a one-line verdict (Looks good / Needs changes / Questions). \
Note specific concerns with file+line references where possible. \
Do not approve or request changes via the review API — comment only.

Gitea base URL: {gitea_base_url}
Repo: {gitea_repo}
"""

MERGE_PROMPT = """\
Pull request #{number} "{title}" was {action} on {repo}.
Merged by: {merger}

Post a brief comment on issue #{number} acknowledging the merge and noting \
any follow-up steps visible from the PR title/description (e.g. "version bump \
will land on dev shortly via CI").

PR description:
{body}

Gitea base URL: {gitea_base_url}
Repo: {gitea_repo}
"""


async def handle(payload: dict) -> None:
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    number = pr.get("number")
    title = pr.get("title", "")
    author = pr.get("user", {}).get("login", "unknown")

    if author == "claude_vscode":
        log.info("pull_request #%s by claude_vscode — skipped", number)
        return

    log.info("pull_request action=%s #%s '%s' by %s", action, number, title, author)

    from config import settings

    if action == "opened":
        prompt = REVIEW_PROMPT.format(
            number=number,
            title=title,
            head=pr.get("head", {}).get("label", ""),
            base=pr.get("base", {}).get("label", ""),
            author=author,
            body=(pr.get("body") or "").strip()[:800],
            diff_url=f"{settings.gitea_base_url}/api/v1/repos/{settings.gitea_repo}/pulls/{number}.diff",
            gitea_base_url=settings.gitea_base_url,
            gitea_repo=settings.gitea_repo,
        )
        response = await run_claude(prompt, allowed_tools="Bash,Read,Glob,Grep")
        log.info("PR review posted for #%s (%d chars)", number, len(response))

    elif action in ("closed",) and pr.get("merged"):
        merger = pr.get("merged_by", {}).get("login", "unknown")
        prompt = MERGE_PROMPT.format(
            number=number,
            title=title,
            action="merged",
            repo=settings.gitea_repo,
            merger=merger,
            body=(pr.get("body") or "").strip()[:400],
            gitea_base_url=settings.gitea_base_url,
            gitea_repo=settings.gitea_repo,
        )
        response = await run_claude(prompt, allowed_tools="Bash,Read,Glob,Grep")
        log.info("PR merge comment posted for #%s (%d chars)", number, len(response))

    else:
        log.info("pull_request action=%s — no handler", action)
