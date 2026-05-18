"""Tests for app.services.github_discussions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_discussions import (
    _graphql,
    _type_label,
    build_discussion_body,
    build_discussion_title,
    create_discussion,
    get_repo_and_category_id,
)

# ---------------------------------------------------------------------------
# _type_label — pure dict lookup
# ---------------------------------------------------------------------------


class TestTypeLabel:
    def test_feedback(self):
        assert _type_label("feedback") == "Feedback"

    def test_feature_request(self):
        assert _type_label("feature_request") == "Feature Request"

    def test_bug_report(self):
        assert _type_label("bug_report") == "Bug Report"

    def test_unknown_falls_back_to_title_case(self):
        assert _type_label("my_custom_type") == "My Custom Type"

    def test_unknown_single_word(self):
        assert _type_label("general") == "General"


# ---------------------------------------------------------------------------
# build_discussion_title — pure string builder
# ---------------------------------------------------------------------------


class TestBuildDiscussionTitle:
    def test_with_subject(self):
        result = build_discussion_title("feedback", "My bug")
        assert result == "[Feedback] My bug"

    def test_without_subject(self):
        result = build_discussion_title("feedback", None)
        assert result == "[Feedback] User submission"

    def test_whitespace_only_subject(self):
        result = build_discussion_title("bug_report", "   ")
        assert result == "[Bug Report] User submission"

    def test_subject_is_stripped(self):
        result = build_discussion_title("feature_request", "  My idea  ")
        assert result == "[Feature Request] My idea"

    def test_empty_string_subject(self):
        result = build_discussion_title("feedback", "")
        assert result == "[Feedback] User submission"


# ---------------------------------------------------------------------------
# build_discussion_body — pure markdown builder
# ---------------------------------------------------------------------------


class TestBuildDiscussionBody:
    def test_minimal_body_included(self):
        result = build_discussion_body("feedback", None, "Hello world", None, False)
        assert "Hello world" in result

    def test_no_diagnostics_skips_section(self):
        result = build_discussion_body("feedback", None, "Hello", None, False)
        assert "Diagnostics" not in result

    def test_with_environment_diagnostic(self):
        diag = {"environment": "production"}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "Diagnostics" in result
        assert "production" in result

    def test_with_app_version_diagnostic(self):
        diag = {"app_version": "1.2.3"}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "1.2.3" in result

    def test_non_anonymous_includes_page_url(self):
        diag = {"page_url": "/projects/abc", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "/projects/abc" in result

    def test_non_anonymous_includes_project_id(self):
        diag = {"project_id": "proj-123", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "proj-123" in result

    def test_non_anonymous_includes_draft_id(self):
        diag = {"draft_id": "draft-456", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "draft-456" in result

    def test_anonymous_omits_page_url(self):
        diag = {"page_url": "/projects/secret-uuid", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, True)
        assert "/projects/secret-uuid" not in result

    def test_anonymous_omits_project_id(self):
        diag = {"project_id": "proj-secret", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, True)
        assert "proj-secret" not in result

    def test_anonymous_omits_draft_id(self):
        diag = {"draft_id": "draft-secret", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, True)
        assert "draft-secret" not in result

    def test_anonymous_includes_user_agent(self):
        diag = {"user_agent": "Mozilla/5.0", "environment": "prod"}
        result = build_discussion_body("feedback", None, "Hello", diag, True)
        assert "Mozilla/5.0" in result

    def test_anonymous_appends_anonymously_note(self):
        result = build_discussion_body("feedback", None, "Hello", None, True)
        assert "anonymously" in result

    def test_non_anonymous_no_anonymously_note(self):
        result = build_discussion_body("feedback", None, "Hello", None, False)
        assert "anonymously" not in result

    def test_note_always_appended(self):
        result = build_discussion_body("feedback", None, "Hello", None, False)
        assert "hobby project" in result

    def test_empty_diagnostics_dict_skips_section(self):
        result = build_discussion_body("feedback", None, "Hello", {}, False)
        assert "Diagnostics" not in result

    def test_diagnostics_with_only_falsy_values_skips_section(self):
        diag = {"environment": "", "app_version": None}
        result = build_discussion_body("feedback", None, "Hello", diag, False)
        assert "Diagnostics" not in result


# ---------------------------------------------------------------------------
# _graphql — async HTTP call
# ---------------------------------------------------------------------------


def _mock_httpx_client(json_response: dict):
    """Return (mock_cls, mock_response) for patching httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = json_response

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_cls, mock_client_instance


class TestGraphql:
    @pytest.mark.asyncio
    async def test_returns_data_on_success(self):
        mock_cls, _ = _mock_httpx_client({"data": {"result": "ok"}})
        with patch("httpx.AsyncClient", mock_cls):
            result = await _graphql("token", "query {}", {})
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_raises_on_errors_key(self):
        mock_cls, _ = _mock_httpx_client({"errors": [{"message": "bad query"}]})
        with patch("httpx.AsyncClient", mock_cls):
            with pytest.raises(RuntimeError, match="GraphQL errors"):
                await _graphql("token", "query {}", {})

    @pytest.mark.asyncio
    async def test_passes_bearer_header(self):
        mock_cls, mock_client = _mock_httpx_client({"data": {}})
        with patch("httpx.AsyncClient", mock_cls):
            await _graphql("my-token", "query {}", {})

        call_kwargs = mock_client.post.call_args[1]
        assert "Bearer my-token" in call_kwargs["headers"]["Authorization"]

    @pytest.mark.asyncio
    async def test_posts_query_and_variables(self):
        mock_cls, mock_client = _mock_httpx_client({"data": {}})
        variables = {"owner": "acme", "name": "repo"}
        with patch("httpx.AsyncClient", mock_cls):
            await _graphql("token", "query Q($owner: String!) {}", variables)

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["variables"] == variables


# ---------------------------------------------------------------------------
# get_repo_and_category_id — wraps _graphql
# ---------------------------------------------------------------------------


def _graphql_mock(repo_id: str, categories: list[dict]):
    return AsyncMock(
        return_value={
            "repository": {
                "id": repo_id,
                "discussionCategories": {"nodes": categories},
            }
        }
    )


class TestGetRepoAndCategoryId:
    @pytest.mark.asyncio
    async def test_returns_preferred_category(self):
        categories = [{"id": "C_1", "name": "Feedback"}, {"id": "C_2", "name": "General"}]
        with patch("app.services.github_discussions._graphql", _graphql_mock("R_abc", categories)):
            repo_id, cat_id = await get_repo_and_category_id("token", "owner/repo", "feedback")
        assert repo_id == "R_abc"
        assert cat_id == "C_1"

    @pytest.mark.asyncio
    async def test_falls_back_to_general_when_preferred_missing(self):
        categories = [{"id": "C_gen", "name": "General"}, {"id": "C_qa", "name": "Q&A"}]
        with patch("app.services.github_discussions._graphql", _graphql_mock("R_x", categories)):
            _, cat_id = await get_repo_and_category_id("token", "owner/repo", "feature_request")
        assert cat_id == "C_gen"

    @pytest.mark.asyncio
    async def test_uses_first_category_as_last_resort(self):
        categories = [{"id": "C_first", "name": "Unrelated"}]
        with patch("app.services.github_discussions._graphql", _graphql_mock("R_y", categories)):
            _, cat_id = await get_repo_and_category_id("token", "owner/repo", "feedback")
        assert cat_id == "C_first"

    @pytest.mark.asyncio
    async def test_raises_when_no_categories(self):
        with patch("app.services.github_discussions._graphql", _graphql_mock("R_z", [])):
            with pytest.raises(RuntimeError, match="No Discussion categories"):
                await get_repo_and_category_id("token", "owner/repo", "feedback")

    @pytest.mark.asyncio
    async def test_case_insensitive_category_match(self):
        categories = [{"id": "C_fb", "name": "feedback"}]
        with patch("app.services.github_discussions._graphql", _graphql_mock("R_ci", categories)):
            _, cat_id = await get_repo_and_category_id("token", "owner/repo", "feedback")
        assert cat_id == "C_fb"


# ---------------------------------------------------------------------------
# create_discussion — wraps get_repo_and_category_id + _graphql
# ---------------------------------------------------------------------------


class TestCreateDiscussion:
    @pytest.mark.asyncio
    async def test_returns_discussion_url(self):
        expected_url = "https://github.com/owner/repo/discussions/42"

        with patch(
            "app.services.github_discussions.get_repo_and_category_id",
            new=AsyncMock(return_value=("R_repo", "C_cat")),
        ):
            mock_data = {"createDiscussion": {"discussion": {"url": expected_url}}}
            with patch(
                "app.services.github_discussions._graphql",
                new=AsyncMock(return_value=mock_data),
            ):
                url = await create_discussion("token", "owner/repo", "feedback", "My title", "My body")

        assert url == expected_url

    @pytest.mark.asyncio
    async def test_passes_title_and_body_to_mutation(self):
        with patch(
            "app.services.github_discussions.get_repo_and_category_id",
            new=AsyncMock(return_value=("R_r", "C_c")),
        ):
            mock_graphql = AsyncMock(return_value={"createDiscussion": {"discussion": {"url": "https://example.com"}}})
            with patch("app.services.github_discussions._graphql", new=mock_graphql):
                await create_discussion("token", "owner/repo", "feedback", "Test title", "Test body")

        call_args = mock_graphql.call_args
        variables = call_args[0][2]
        assert variables["input"]["title"] == "Test title"
        assert variables["input"]["body"] == "Test body"
