"""Handler for Gitea workflow_run events.

This replaces the Monitor-based CI polling pattern. Gitea fires this event
the instant a run completes, so the webhook server knows about CI results
immediately rather than on the next poll interval.

On completion the handler posts a formatted comment to the relevant open PR
(if one exists for that branch) so the active Claude Code session can see the
result without polling the Gitea API at all.
"""

import logging

import httpx

log = logging.getLogger(__name__)


async def _find_open_pr(branch: str, base_url: str, repo: str, token: str) -> int | None:
    """Return the PR number for an open PR from this branch, or None."""
    url = f"{base_url}/api/v1/repos/{repo}/pulls"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"token {token}"},
            params={"state": "open", "limit": 50},
        )
    if resp.status_code != 200:
        return None
    for pr in resp.json():
        if pr.get("head", {}).get("ref") == branch:
            return pr["number"]
    return None


async def _post_comment(issue_number: int, body: str, base_url: str, repo: str, token: str) -> None:
    url = f"{base_url}/api/v1/repos/{repo}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
            json={"body": body},
        )
        resp.raise_for_status()


async def _get_failed_jobs(run_id: int, base_url: str, repo: str, token: str) -> list[dict]:
    """Fetch job details for a failed run."""
    url = f"{base_url}/api/v1/repos/{repo}/actions/runs/{run_id}/jobs"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"token {token}"})
    if resp.status_code != 200:
        return []
    jobs = resp.json().get("workflow_jobs", [])
    return [j for j in jobs if j.get("conclusion") == "failure"]


async def handle(payload: dict) -> None:
    action = payload.get("action")
    if action != "completed":
        log.info("workflow_run action=%s — skipped", action)
        return

    run = payload.get("workflow_run", {})
    run_id = run.get("id")
    branch = run.get("head_branch", "")
    conclusion = run.get("conclusion", "")
    run_name = run.get("display_title") or run.get("name", "CI")
    run_url = run.get("html_url", "")

    log.info("workflow_run #%s completed: %s on %s", run_id, conclusion, branch)

    from config import settings

    icon = "✅" if conclusion == "success" else "❌" if conclusion == "failure" else "⚠️"

    if conclusion == "success":
        # For dev/main pushes, note that a version bump may have landed
        bump_note = ""
        if branch in ("dev", "main"):
            bump_note = "\n\nVersion bump commit will land shortly — run `git pull origin {branch}` to pick it up.".format(
                branch=branch
            )

        comment = (
            f"{icon} **CI run #{run_id} passed** on `{branch}`{bump_note}\n\n"
            f"[View run]({run_url})"
        )
    else:
        failed_jobs = await _get_failed_jobs(run_id, settings.gitea_base_url, settings.gitea_repo, settings.gitea_token)
        job_details = ""
        if failed_jobs:
            names = ", ".join(f"`{j['name']}`" for j in failed_jobs)
            job_details = f"\n\nFailed jobs: {names}"

        comment = (
            f"{icon} **CI run #{run_id} {conclusion}** on `{branch}`{job_details}\n\n"
            f"[View run]({run_url})"
        )

    # Post to the open PR for this branch if one exists
    pr_number = await _find_open_pr(branch, settings.gitea_base_url, settings.gitea_repo, settings.gitea_token)
    if pr_number:
        await _post_comment(pr_number, comment, settings.gitea_base_url, settings.gitea_repo, settings.gitea_token)
        log.info("workflow_run result posted to PR #%s", pr_number)
    else:
        log.info("workflow_run on %s — no open PR found, result logged only: %s", branch, conclusion)
