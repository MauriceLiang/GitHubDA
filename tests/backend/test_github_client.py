import httpx
import pytest

from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GITHUB_API, GitHubClient, PageObservation, parse_repository_input


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


def test_secondary_rate_limit_403_is_mapped_without_retry():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(403, headers={"Retry-After": "9"}, json={"message": "You have exceeded a secondary rate limit."})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    with pytest.raises(AppError) as error:
        client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert error.value.status_code == 429
    assert error.value.details["retry_after_seconds"] == 9
    assert len(calls) == 1


def test_non_rate_limit_403_is_not_reported_as_rate_limit():
    def respond(_request):
        return httpx.Response(403, json={"message": "Resource not accessible by integration"})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    with pytest.raises(AppError) as error:
        client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert error.value.status_code == 502
    assert error.value.code == "GITHUB_UPSTREAM_ERROR"
    assert error.value.details["http_status"] == 403


def test_upstream_5xx_retries_three_times_then_maps_to_502():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503, json={"message": "temporarily unavailable"})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    with pytest.raises(AppError) as error:
        client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert error.value.status_code == 502
    assert error.value.details["http_status"] == 503
    assert len(calls) == 3


def test_timeout_maps_to_504_without_retry():
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    with pytest.raises(AppError) as error:
        client.search_repositories("requests", None, None, "best_match", "desc", 1, 20)
    assert error.value.status_code == 504
    assert error.value.code == "GITHUB_TIMEOUT"
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


def test_detailed_pagination_reports_each_validated_page():
    calls = []

    def respond(request):
        page = int(request.url.params.get("page", "1"))
        calls.append(page)
        headers = {}
        if page < 3:
            headers["Link"] = f'<{GITHUB_API}/repos/a/b/issues?page={page + 1}>; rel="next"'
        return httpx.Response(200, headers=headers, json=[{"id": page * 10}, {"id": page * 10 + 1}])

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    observations: list[PageObservation] = []
    result = client.list_paginated_detailed("/repos/a/b/issues", on_page=observations.append)

    assert calls == [1, 2, 3]
    assert result.complete is True
    assert result.pages_fetched == 3
    assert result.observed_items == 6
    assert result.http_calls == 3
    assert [item.pages_fetched for item in observations] == [1, 2, 3]
    assert [item.observed_items for item in observations] == [2, 4, 6]
    assert [item.has_next for item in observations] == [True, True, False]


def test_detailed_pagination_retains_successful_pages_before_timeout():
    calls = []

    def respond(request):
        page = int(request.url.params.get("page", "1"))
        calls.append(page)
        if page == 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            headers={"Link": f'<{GITHUB_API}/repos/a/b/issues?page={page + 1}>; rel="next"'},
            json=[{"id": page}, {"id": page + 10}],
        )

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))
    result = client.list_paginated_detailed("/repos/a/b/issues")

    assert calls == [1, 2, 3]
    assert result.items == [{"id": 1}, {"id": 11}, {"id": 2}, {"id": 12}]
    assert len(result.raw_pages) == 2
    assert result.pages_fetched == 2
    assert result.observed_items == 4
    assert result.complete is False
    assert result.has_next is True
    assert result.error_code == "GITHUB_TIMEOUT"
    assert result.timeout_count == 1
    assert result.http_calls == 3


def test_detailed_pagination_does_not_swallow_progress_callback_errors():
    def respond(_request):
        return httpx.Response(200, json=[{"id": 1}])

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))

    with pytest.raises(RuntimeError, match="progress store unavailable"):
        client.list_paginated_detailed(
            "/repos/a/b/issues",
            on_page=lambda _observation: (_ for _ in ()).throw(RuntimeError("progress store unavailable")),
        )


def test_legacy_pagination_preserves_app_error_contract_after_detailed_failure():
    def respond(_request):
        return httpx.Response(429, headers={"Retry-After": "11"}, json={"message": "limited"})

    client = GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(respond)))

    with pytest.raises(AppError) as error:
        client.list_paginated("/repos/a/b/issues")

    assert error.value.status_code == 429
    assert error.value.code == "GITHUB_RATE_LIMITED"
    assert error.value.details["retry_after_seconds"] == 11
