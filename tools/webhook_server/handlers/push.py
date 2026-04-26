"""Handler for Gitea push events."""

import logging

log = logging.getLogger(__name__)


async def handle(payload: dict) -> None:
    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/")
    pusher = payload.get("pusher", {}).get("login", "unknown")
    commits = payload.get("commits", [])
    repo = payload.get("repository", {}).get("full_name", "")

    # Skip CI-generated version bump commits to avoid noise
    for commit in commits:
        msg = commit.get("message", "")
        if "[skip ci]" in msg and "bump version" in msg.lower():
            log.info("push to %s — version bump commit, skipping", branch)
            return

    log.info(
        "push to %s by %s — %d commit(s): %s",
        branch,
        pusher,
        len(commits),
        "; ".join(c.get("message", "").splitlines()[0][:60] for c in commits[:3]),
    )
