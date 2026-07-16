from __future__ import annotations

import os
import re
from typing import Any

import httpx

from app.automation.contracts import ConnectorCapability, ConnectorRejected, ConnectorRequest, ConnectorResult, ConnectorStatus

GITHUB_API_BASE = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubConnector:
    connector_id = "github"

    def __init__(
        self,
        *,
        token: str | None = None,
        allowed_repositories: set[str] | None = None,
        allowed_organizations: set[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.allowed_repositories = {
            item.lower()
            for item in (allowed_repositories if allowed_repositories is not None else self._csv_env("GITHUB_ALLOWED_REPOSITORIES", REPOSITORY_PATTERN))
        }
        self.allowed_organizations = {
            item.lower()
            for item in (allowed_organizations if allowed_organizations is not None else self._csv_env("GITHUB_ALLOWED_ORGANIZATIONS", OWNER_PATTERN))
        }
        self._client = client

    def capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability("list_authorized_repositories", "List GitHub repositories authorized for this connector.", {}),
            ConnectorCapability("list_issues", "List issues for an authorized GitHub repository.", self._repo_schema()),
            ConnectorCapability("list_pull_requests", "List pull requests for an authorized GitHub repository.", self._repo_schema()),
            ConnectorCapability(
                "create_issue",
                "Create a non-destructive issue in an authorized GitHub repository.",
                {"type": "object", "required": ["owner", "repo", "title"], "properties": {"owner": {}, "repo": {}, "title": {}, "body": {}, "labels": {}}},
            ),
            ConnectorCapability(
                "add_issue_comment",
                "Add a comment to an existing GitHub issue in an authorized repository.",
                {"type": "object", "required": ["owner", "repo", "issue_number", "body"], "properties": {"owner": {}, "repo": {}, "issue_number": {}, "body": {}}},
            ),
            ConnectorCapability("list_workflow_runs", "List workflow run status for an authorized GitHub repository.", self._repo_schema()),
        ]

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if not self.token:
            raise ConnectorRejected("GitHub token is not configured")
        try:
            if request.capability == "list_authorized_repositories":
                return await self._list_authorized_repositories(request)
            if request.capability == "list_issues":
                return await self._list_issues(request)
            if request.capability == "list_pull_requests":
                return await self._list_pull_requests(request)
            if request.capability == "create_issue":
                return await self._create_issue(request)
            if request.capability == "add_issue_comment":
                return await self._add_issue_comment(request)
            if request.capability == "list_workflow_runs":
                return await self._list_workflow_runs(request)
            raise ConnectorRejected("Unsupported GitHub capability")
        except httpx.TimeoutException as exc:
            return ConnectorResult(status=ConnectorStatus.TIMEOUT, error_code="github_timeout", error_message=exc.__class__.__name__)
        except httpx.HTTPStatusError as exc:
            return ConnectorResult(
                status=ConnectorStatus.FAILED,
                error_code="github_http_error",
                error_message=f"GitHub API returned {exc.response.status_code}",
                output={"status_code": exc.response.status_code},
            )
        except httpx.HTTPError as exc:
            return ConnectorResult(status=ConnectorStatus.FAILED, error_code="github_http_error", error_message=exc.__class__.__name__)

    async def _list_authorized_repositories(self, request: ConnectorRequest) -> ConnectorResult:
        repositories = []
        for full_name in sorted(self.allowed_repositories):
            owner, repo = full_name.split("/", 1)
            response = await self._request(request, "GET", f"/repos/{owner}/{repo}")
            repositories.append(self._repository_summary(response.json()))
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"repositories": repositories})

    async def _list_issues(self, request: ConnectorRequest) -> ConnectorResult:
        owner, repo = self._authorized_repo_from_payload(request.payload)
        params = {"state": self._state(request.payload), "per_page": self._per_page(request.payload)}
        response = await self._request(request, "GET", f"/repos/{owner}/{repo}/issues", params=params)
        issues = [self._issue_summary(item) for item in response.json() if "pull_request" not in item]
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"repository": f"{owner}/{repo}", "issues": issues})

    async def _list_pull_requests(self, request: ConnectorRequest) -> ConnectorResult:
        owner, repo = self._authorized_repo_from_payload(request.payload)
        params = {"state": self._state(request.payload), "per_page": self._per_page(request.payload)}
        response = await self._request(request, "GET", f"/repos/{owner}/{repo}/pulls", params=params)
        pulls = [self._pull_request_summary(item) for item in response.json()]
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"repository": f"{owner}/{repo}", "pull_requests": pulls})

    async def _create_issue(self, request: ConnectorRequest) -> ConnectorResult:
        owner, repo = self._authorized_repo_from_payload(request.payload)
        title = self._required_text(request.payload, "title", 256)
        body = self._optional_text(request.payload, "body", 65536)
        labels = request.payload.get("labels", [])
        if not isinstance(labels, list) or not all(isinstance(item, str) and len(item) <= 128 for item in labels):
            raise ConnectorRejected("GitHub labels must be a list of strings")
        response = await self._request(
            request,
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json_payload={"title": title, "body": body, "labels": labels},
        )
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"repository": f"{owner}/{repo}", "issue": self._issue_summary(response.json())})

    async def _add_issue_comment(self, request: ConnectorRequest) -> ConnectorResult:
        owner, repo = self._authorized_repo_from_payload(request.payload)
        issue_number = request.payload.get("issue_number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ConnectorRejected("GitHub issue_number must be a positive integer")
        body = self._required_text(request.payload, "body", 65536)
        response = await self._request(
            request,
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json_payload={"body": body},
        )
        item = response.json()
        return ConnectorResult(
            status=ConnectorStatus.SUCCEEDED,
            output={"repository": f"{owner}/{repo}", "comment": {"id": item.get("id"), "html_url": item.get("html_url"), "created_at": item.get("created_at")}},
        )

    async def _list_workflow_runs(self, request: ConnectorRequest) -> ConnectorResult:
        owner, repo = self._authorized_repo_from_payload(request.payload)
        params: dict[str, Any] = {"per_page": self._per_page(request.payload)}
        if request.payload.get("branch"):
            params["branch"] = self._required_text(request.payload, "branch", 255)
        if request.payload.get("status"):
            params["status"] = self._required_text(request.payload, "status", 64)
        response = await self._request(request, "GET", f"/repos/{owner}/{repo}/actions/runs", params=params)
        runs = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "html_url": item.get("html_url"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
            for item in response.json().get("workflow_runs", [])
        ]
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"repository": f"{owner}/{repo}", "workflow_runs": runs})

    async def _request(
        self,
        request: ConnectorRequest,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{GITHUB_API_BASE}{path}"
        client = self._client or httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(request.timeout_seconds))
        close_client = self._client is None
        try:
            response = await client.request(method, url, params=params, json=json_payload, headers=self._headers())
            response.raise_for_status()
            return response
        finally:
            if close_client:
                await client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "the-creation-os-automation-sdk",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _authorized_repo_from_payload(self, payload: dict[str, Any]) -> tuple[str, str]:
        owner = self._required_text(payload, "owner", 100)
        repo = self._required_text(payload, "repo", 100)
        full_name = f"{owner}/{repo}".lower()
        if not OWNER_PATTERN.fullmatch(owner) or not OWNER_PATTERN.fullmatch(repo):
            raise ConnectorRejected("GitHub repository identifier is invalid")
        if full_name not in self.allowed_repositories:
            raise ConnectorRejected("GitHub repository is not authorized")
        if self.allowed_organizations and owner.lower() not in self.allowed_organizations:
            raise ConnectorRejected("GitHub organization is not authorized")
        return owner, repo

    def _required_text(self, payload: dict[str, Any], key: str, max_length: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ConnectorRejected(f"GitHub field {key} is required")
        return value.strip()

    def _optional_text(self, payload: dict[str, Any], key: str, max_length: int) -> str:
        value = payload.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str) or len(value) > max_length:
            raise ConnectorRejected(f"GitHub field {key} is invalid")
        return value

    def _state(self, payload: dict[str, Any]) -> str:
        state = str(payload.get("state", "open"))
        if state not in {"open", "closed", "all"}:
            raise ConnectorRejected("GitHub state filter is invalid")
        return state

    def _per_page(self, payload: dict[str, Any]) -> int:
        value = payload.get("per_page", 30)
        if not isinstance(value, int) or value < 1 or value > 100:
            raise ConnectorRejected("GitHub per_page must be between 1 and 100")
        return value

    def _repository_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "full_name": item.get("full_name"),
            "private": item.get("private"),
            "html_url": item.get("html_url"),
            "default_branch": item.get("default_branch"),
        }

    def _issue_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "html_url": item.get("html_url"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def _pull_request_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "draft": item.get("draft"),
            "html_url": item.get("html_url"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def _repo_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["owner", "repo"],
            "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string"}, "per_page": {"type": "integer"}},
        }

    def _csv_env(self, name: str, pattern: re.Pattern[str]) -> set[str]:
        return {item.strip() for item in os.getenv(name, "").split(",") if item.strip() and pattern.fullmatch(item.strip())}
