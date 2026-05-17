"""GitHub Discussions GraphQL client for feedback dispatch."""

import logging

import httpx

log = logging.getLogger(__name__)

_GH_GRAPHQL = "https://api.github.com/graphql"

# Mapping from submission_type → preferred Discussion category name.
_CATEGORY_MAP = {
    "feedback": "Feedback",
    "feature_request": "Ideas",
    "bug_report": "Bug Reports",
}

# Fallback order when the preferred category doesn't exist.
_CATEGORY_FALLBACK = ["General", "Q&A"]


async def _graphql(token: str, query: str, variables: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_GH_GRAPHQL, json={"query": query, "variables": variables}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL errors: {data['errors']}")
    return data["data"]


async def get_repo_and_category_id(token: str, repo: str, submission_type: str) -> tuple[str, str]:
    """Return (repositoryId, categoryId) for the given repo and submission type."""
    owner, name = repo.split("/", 1)
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
        discussionCategories(first: 20) {
          nodes { id name }
        }
      }
    }
    """
    data = await _graphql(token, query, {"owner": owner, "name": name})
    repo_id: str = data["repository"]["id"]
    categories: list[dict] = data["repository"]["discussionCategories"]["nodes"]

    preferred = _CATEGORY_MAP.get(submission_type, "Feedback")
    candidates = [preferred, *_CATEGORY_FALLBACK]
    for candidate in candidates:
        for cat in categories:
            if cat["name"].lower() == candidate.lower():
                return repo_id, cat["id"]

    # Last resort: use the first available category
    if categories:
        log.warning("No matching Discussion category for %r — using %r", preferred, categories[0]["name"])
        return repo_id, categories[0]["id"]

    raise RuntimeError(f"No Discussion categories found in repo {repo}")


async def create_discussion(
    token: str,
    repo: str,
    submission_type: str,
    title: str,
    body: str,
) -> str:
    """Create a GitHub Discussion and return its URL."""
    repo_id, category_id = await get_repo_and_category_id(token, repo, submission_type)
    mutation = """
    mutation($input: CreateDiscussionInput!) {
      createDiscussion(input: $input) {
        discussion { url }
      }
    }
    """
    data = await _graphql(
        token,
        mutation,
        {"input": {"repositoryId": repo_id, "categoryId": category_id, "title": title, "body": body}},
    )
    return data["createDiscussion"]["discussion"]["url"]


def _type_label(submission_type: str) -> str:
    return {"feedback": "Feedback", "feature_request": "Feature Request", "bug_report": "Bug Report"}.get(
        submission_type, submission_type.replace("_", " ").title()
    )


def build_discussion_body(
    submission_type: str,
    subject: str | None,
    body: str,
    diagnostics: dict | None,
    is_anonymous: bool,
    user_email: str | None,
) -> str:
    """Build the markdown body for the GitHub Discussion."""
    lines: list[str] = []

    lines.append(body)
    lines.append("")

    diag = diagnostics or {}
    has_diag = any(
        diag.get(k) for k in ("environment", "page_url", "user_agent", "app_version", "project_id", "draft_id")
    )
    if has_diag:
        lines.append("---")
        lines.append("")
        lines.append("**Diagnostics**")
        lines.append("")
        if diag.get("environment"):
            lines.append(f"- **Environment:** {diag['environment']}")
        if diag.get("app_version"):
            lines.append(f"- **App version:** {diag['app_version']}")
        if diag.get("page_url"):
            lines.append(f"- **Page:** `{diag['page_url']}`")
        if diag.get("project_id"):
            lines.append(f"- **Project ID:** `{diag['project_id']}`")
        if diag.get("draft_id"):
            lines.append(f"- **Draft ID:** `{diag['draft_id']}`")
        if diag.get("user_agent"):
            lines.append(f"- **User agent:** `{diag['user_agent']}`")
        lines.append("")

    if not is_anonymous and user_email:
        lines.append(f"*Submitted by: {user_email}*")
    else:
        lines.append("*Submitted anonymously.*")

    lines.append("")
    lines.append(
        "> **Note:** This is a hobby project — responses may be slow. "
        "You're welcome to attach screenshots or additional context directly to this Discussion thread."
    )

    return "\n".join(lines)


def build_discussion_title(submission_type: str, subject: str | None) -> str:
    prefix = _type_label(submission_type)
    if subject and subject.strip():
        return f"[{prefix}] {subject.strip()}"
    return f"[{prefix}] User submission"
