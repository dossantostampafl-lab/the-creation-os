from __future__ import annotations

import httpx
import pytest

from app.automation.connectors.github import GITHUB_API_BASE, GitHubConnector
from app.automation.contracts import ConnectorRequest, ConnectorStatus
from app.automation.registry import default_registry


def github_request(capability: str, payload: dict, timeout_seconds: float = 1.0) -> ConnectorRequest:
    return ConnectorRequest(
        connector_id="github",
        capability=capability,
        payload=payload,
        timeout_seconds=timeout_seconds,
        idempotency_key=f"{capability}-key",
        correlation_id="correlation-1",
    )


def github_connector(handler) -> GitHubConnector:
    return GitHubConnector(
        token="ghp_secret",
        allowed_repositories={"openai/example"},
        allowed_organizations={"openai"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_github_connector_lists_authorized_repositories_without_exposing_token():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(f"{GITHUB_API_BASE}/repos/openai/example")
        assert request.headers["authorization"] == "Bearer ghp_secret"
        return httpx.Response(
            200,
            json={"id": 1, "full_name": "openai/example", "private": True, "html_url": "https://github.com/openai/example", "default_branch": "main"},
        )

    connector = github_connector(handler)
    result = await connector.execute(github_request("list_authorized_repositories", {}))

    assert result.status == ConnectorStatus.SUCCEEDED
    assert result.output["repositories"][0]["full_name"] == "openai/example"
    assert "ghp_secret" not in str(result.output)
    await connector._client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_github_connector_lists_issues_pull_requests_and_workflows():
    seen_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "number": 7, "title": "issue", "state": "open", "html_url": "issue-url"},
                    {"id": 2, "number": 8, "title": "pr-as-issue", "pull_request": {}, "state": "open"},
                ],
            )
        if request.url.path.endswith("/pulls"):
            return httpx.Response(200, json=[{"id": 3, "number": 9, "title": "pr", "state": "open", "draft": False, "html_url": "pr-url"}])
        return httpx.Response(200, json={"workflow_runs": [{"id": 4, "name": "ci", "status": "completed", "conclusion": "success", "html_url": "run-url"}]})

    connector = github_connector(handler)
    issues = await connector.execute(github_request("list_issues", {"owner": "openai", "repo": "example", "state": "open"}))
    pulls = await connector.execute(github_request("list_pull_requests", {"owner": "openai", "repo": "example", "state": "open"}))
    runs = await connector.execute(github_request("list_workflow_runs", {"owner": "openai", "repo": "example"}))

    assert issues.output["issues"] == [{"id": 1, "number": 7, "title": "issue", "state": "open", "html_url": "issue-url", "created_at": None, "updated_at": None}]
    assert pulls.output["pull_requests"][0]["number"] == 9
    assert runs.output["workflow_runs"][0]["conclusion"] == "success"
    assert seen_paths == ["/repos/openai/example/issues", "/repos/openai/example/pulls", "/repos/openai/example/actions/runs"]
    await connector._client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_github_connector_creates_issue_and_adds_comment_only_on_authorized_repo():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer ghp_secret"
        if request.url.path.endswith("/issues"):
            assert request.read()
            return httpx.Response(201, json={"id": 10, "number": 3, "title": "new", "state": "open", "html_url": "issue-url"})
        return httpx.Response(201, json={"id": 11, "html_url": "comment-url", "created_at": "2026-07-15T00:00:00Z"})

    connector = github_connector(handler)
    issue = await connector.execute(github_request("create_issue", {"owner": "openai", "repo": "example", "title": "new", "body": "body"}))
    comment = await connector.execute(github_request("add_issue_comment", {"owner": "openai", "repo": "example", "issue_number": 3, "body": "comment"}))

    assert issue.status == ConnectorStatus.SUCCEEDED
    assert issue.output["issue"]["number"] == 3
    assert comment.output["comment"]["html_url"] == "comment-url"
    assert "ghp_secret" not in str(issue.output)
    await connector._client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_github_connector_rejects_unauthorized_repository_and_destructive_capability():
    connector = github_connector(lambda request: httpx.Response(200, json={}))

    with pytest.raises(Exception, match="not authorized"):
        await connector.execute(github_request("list_issues", {"owner": "openai", "repo": "blocked"}))
    with pytest.raises(Exception, match="Unsupported GitHub capability"):
        await connector.execute(github_request("merge_pull_request", {"owner": "openai", "repo": "example"}))

    await connector._client.aclose()  # type: ignore[union-attr]


def test_default_registry_exposes_github_without_requiring_token_in_capability_list(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    capabilities = default_registry().list_capabilities()

    assert "github" in capabilities
    assert {capability.name for capability in capabilities["github"]} == {
        "list_authorized_repositories",
        "list_issues",
        "list_pull_requests",
        "create_issue",
        "add_issue_comment",
        "list_workflow_runs",
    }
