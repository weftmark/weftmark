"""Handler for Gitea issue_comment events."""

import logging

from claude_runner import run_claude
from gitea import post_issue_comment

log = logging.getLogger(__name__)

PROMPT_TEMPLATE = """\
You are acting as an automated assistant for the weaving_site Gitea repository.

A comment was posted on issue #{issue_number} ("{issue_title}") by {commenter}.

Comment:
{comment_body}

Issue description:
{issue_body}

Read the comment carefully and respond helpfully. If the comment is a question, answer it. \
If it is a task or request, carry it out and summarise what you did. \
Post your response as a follow-up comment on the same issue — use the post_issue_comment \
tool by writing your response and the issue number clearly in your reply. \
Keep your response concise and on-topic for the issue.

Issue number: {issue_number}
Repository path: {repo_path}
"""


async def handle(payload: dict) -> None:
    action = payload.get("action")
    if action not in ("created",):
        log.info("issue_comment action=%s — skipped", action)
        return

    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    commenter = comment.get("user", {}).get("login", "unknown")

    # Ignore comments from ourselves to avoid reply loops
    if commenter == "claude_vscode":
        log.info("Ignoring comment from claude_vscode to avoid loop")
        return

    issue_number = issue.get("number")
    issue_title = issue.get("title", "")
    issue_body = (issue.get("body") or "").strip()
    comment_body = (comment.get("body") or "").strip()

    log.info("issue_comment created on #%s by %s", issue_number, commenter)

    from config import settings
    prompt = PROMPT_TEMPLATE.format(
        issue_number=issue_number,
        issue_title=issue_title,
        commenter=commenter,
        comment_body=comment_body,
        issue_body=issue_body[:1000],
        repo_path=settings.repo_path,
    )

    response = await run_claude(prompt, allowed_tools="Bash,Read,Glob,Grep")
    log.info("claude response (%d chars)", len(response))

    await post_issue_comment(issue_number, response)
    log.info("posted response to issue #%s", issue_number)
