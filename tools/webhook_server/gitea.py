"""Gitea API helpers for posting responses back."""

import httpx

from config import settings


async def post_issue_comment(issue_number: int, body: str) -> None:
    url = f"{settings.gitea_base_url}/api/v1/repos/{settings.gitea_repo}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"token {settings.gitea_token}", "Content-Type": "application/json"},
            json={"body": body},
        )
        resp.raise_for_status()
