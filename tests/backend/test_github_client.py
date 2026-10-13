import httpx
import pytest

from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GITHUB_API, GitHubClient, parse_repository_input


@pytest.mark.parametrize("value", ["https://github.com.evil.test/owner/repo", "https://user@github.com/owner/repo", "https://github.com:8443/owner/repo", "https://github.com/owner/repo/issues"])
def test_resolve_rejects_non_repository_urls(value):
    with pytest.raises(AppError) as error:
        parse_repository_input(value)
    assert error.value.code == "INVALID_REPOSITORY_URL"


def test_github_rate_limit_is_mapped_without_retry():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "17"}, json={"message": "limited"})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    with pytest.raises(AppError) as error:
        client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert error.value.status_code == 429
    assert error.value.details["retry_after_seconds"] == 17
    assert len(calls) == 1


def test_client_sends_versioned_json_headers():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"items": [], "total_count": 0, "incomplete_results": False})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert seen[0].headers["Accept"] == "application/vnd.github+json"
    assert seen[0].headers["X-GitHub-Api-Version"] == "2026-03-10"


def test_deep_pagination_reports_truncated_coverage(monkeypatch):
    monkeypatch.setattr("backend.app.integrations.github.client.get_settings", lambda: type("Settings", (), {"github_token": None, "github_timeout_seconds": 1, "github_max_pages": 1})())
    responses = 0

    def respond(request):
        nonlocal responses
        responses += 1
        return httpx.Response(200, headers={"Link": '<https://api.github.com/repos/a/b/commits?page=2>; rel="next"'}, json=[{"sha": "one"}])

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    rows, complete, _raw = client.list_paginated("/repos/a/b/commits")
    assert rows == [{"sha": "one"}]
    assert complete is False
    assert responses == 1
