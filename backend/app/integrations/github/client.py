import re
import threading
import time
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError


GITHUB_API = "https://api.github.com"
_rate_lock = threading.Lock()
_request_lock = threading.Lock()
_rate_cache: dict[str, Any] = {"remaining": None, "reset_at": None, "checked_at": None}
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageObservation:
    page_index: int
    pages_fetched: int
    observed_items: int
    page_cap: int | None
    has_next: bool
    duration_ms: float
    records: list[dict[str, Any]] = field(default_factory=list)
    raw_body: str | None = None
    request_url: str | None = None
    next_url: str | None = None
    http_status: int | None = None


@dataclass(frozen=True)
class PaginatedResult:
    items: list[dict[str, Any]]
    raw_pages: list[str]
    complete: bool
    pages_fetched: int
    observed_items: int
    has_next: bool
    error_code: str | None = None
    error_message: str | None = None
    error_status_code: int | None = None
    error_details: dict[str, Any] = field(default_factory=dict)
    http_calls: int = 0
    rate_limited_count: int = 0
    timeout_count: int = 0
    duration_ms: float = 0.0


class GitHubClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        request_id: str | None = None,
        max_pages: int | None = None,
        *,
        unbounded: bool = False,
        on_response: Callable[[httpx.Response], None] | None = None,
    ):
        settings = get_settings()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "RepoVantage/0.1",
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = client or httpx.Client(
            base_url=GITHUB_API,
            headers=headers,
            timeout=settings.github_timeout_seconds,
            follow_redirects=False,
        )
        if client is not None:
            self.client.headers.update(headers)
        self._owns_client = client is None
        self.max_pages = None if unbounded else settings.github_max_pages if max_pages is None else max_pages
        self._on_response = on_response
        self._metrics_lock = threading.Lock()
        self._request_metrics: dict[str, int | float] = {
            "http_calls": 0,
            "rate_limited_count": 0,
            "timeout_count": 0,
            "duration_ms": 0.0,
        }

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _request(self, method: str, path_or_url: str, *, params: dict[str, Any] | None = None, etag: str | None = None) -> httpx.Response:
        with _request_lock:
            return self._request_locked(method, path_or_url, params=params, etag=etag)

    def request_metrics_snapshot(self) -> dict[str, int | float]:
        with self._metrics_lock:
            return dict(self._request_metrics)

    def _record_http_call(self, started_at: float, *, timed_out: bool = False, rate_limited: bool = False) -> None:
        elapsed_ms = max(0.0, (time.monotonic() - started_at) * 1000)
        with self._metrics_lock:
            self._request_metrics["http_calls"] += 1
            self._request_metrics["duration_ms"] += elapsed_ms
            if timed_out:
                self._request_metrics["timeout_count"] += 1
            if rate_limited:
                self._request_metrics["rate_limited_count"] += 1

    def _request_locked(self, method: str, path_or_url: str, *, params: dict[str, Any] | None = None, etag: str | None = None, redirect_depth: int = 0) -> httpx.Response:
        if path_or_url.startswith("http"):
            if not _is_github_api_url(path_or_url):
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效分页地址")
        headers = {"If-None-Match": etag} if etag else None
        for attempt in range(3):
            request_started = time.monotonic()
            try:
                response = self.client.request(method, path_or_url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                self._record_http_call(request_started, timed_out=True)
                raise AppError(504, "GITHUB_TIMEOUT", "GitHub 请求超时") from exc
            except httpx.RequestError as exc:
                self._record_http_call(request_started)
                if attempt < 2:
                    time.sleep(0.15 * (2**attempt))
                    continue
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "无法连接 GitHub") from exc
            limited = is_rate_limited_response(response)
            self._record_http_call(request_started, rate_limited=limited)
            self._cache_rate_limit(response)
            if self._on_response is not None:
                try:
                    self._on_response(response)
                except Exception as exc:
                    logger.warning("Unable to persist GitHub quota observation error_type=%s", type(exc).__name__)
            if limited:
                retry_after = retry_after_seconds(response)
                raise AppError(429, "GITHUB_RATE_LIMITED", "GitHub 请求暂时受限，请稍后重试", {"retry_after_seconds": retry_after})
            if response.status_code == 404:
                raise AppError(404, "REPOSITORY_NOT_FOUND", "仓库不存在或不可公开访问")
            if response.status_code in (401, 422):
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 拒绝了请求或返回了无效请求")
            if response.status_code >= 500 and attempt < 2:
                time.sleep(0.15 * (2**attempt))
                continue
            if response.is_redirect:
                location = response.headers.get("Location")
                redirect_url = urljoin(f"{GITHUB_API}/", location) if location else None
                if method != "GET" or not redirect_url or redirect_depth >= 1 or not _is_github_api_url(redirect_url):
                    raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了不安全或过多的重定向")
                return self._request_locked("GET", redirect_url, redirect_depth=redirect_depth + 1)
            if response.status_code >= 400:
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了上游错误", {"http_status": response.status_code})
            if response.status_code != 304:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了上游错误") from exc
            return response
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 请求失败")

    @staticmethod
    def _cache_rate_limit(response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        with _rate_lock:
            if remaining and remaining.isdigit():
                _rate_cache["remaining"] = int(remaining)
            if reset and reset.isdigit():
                _rate_cache["reset_at"] = datetime.fromtimestamp(int(reset), UTC).isoformat().replace("+00:00", "Z")
            _rate_cache["checked_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def rate_limit_snapshot() -> dict[str, Any]:
        with _rate_lock:
            return dict(_rate_cache)

    def search_repositories(self, q: str, language: str | None, stars_min: int | None, sort: str, order: str, page: int, per_page: int) -> dict[str, Any]:
        terms = [q.strip()]
        if language and language.lower() != "all":
            terms.append(f"language:{language}")
        if stars_min is not None:
            terms.append(f"stars:>={stars_min}")
        params: dict[str, Any] = {"q": " ".join(terms), "page": page, "per_page": per_page}
        if sort != "best_match":
            params.update(sort=sort, order=order)
        payload = _json(self._request("GET", "/search/repositories", params=params))
        if not isinstance(payload, dict) or not isinstance(payload.get("items", []), list):
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 搜索返回了无效数据")
        return {
            "items": payload.get("items", []),
            "total_count": payload.get("total_count", 0),
            "incomplete_results": bool(payload.get("incomplete_results", False)),
        }

    def get_repository(self, full_name: str, etag: str | None = None) -> tuple[dict[str, Any] | None, int, str | None]:
        owner, repo = validate_full_name(full_name)
        response = self._request("GET", f"/repos/{owner}/{repo}", etag=etag)
        payload = None if response.status_code == 304 else _json(response)
        if payload is not None and not isinstance(payload, dict):
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库接口返回了无效数据")
        return (payload, response.status_code, response.headers.get("ETag"))

    def get_repository_by_id(self, repository_id: int, etag: str | None = None) -> tuple[dict[str, Any] | None, int, str | None]:
        response = self._request("GET", f"/repositories/{repository_id}", etag=etag)
        payload = None if response.status_code == 304 else _json(response)
        if payload is not None and not isinstance(payload, dict):
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库接口返回了无效数据")
        return (payload, response.status_code, response.headers.get("ETag"))

    def list_commits(self, full_name: str, since: str, until: str):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/commits", {"since": since, "until": until})

    def list_commits_detailed(self, full_name: str, since: str, until: str, *, on_page: Callable[[PageObservation], None] | None = None, **pagination_options) -> PaginatedResult:
        owner, repo = validate_full_name(full_name)
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/commits", {"since": since, "until": until}, on_page=on_page, **pagination_options)

    def list_issues(self, full_name: str, since: str, state: str = "all"):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/issues", {"state": state, "since": since})

    def list_issues_detailed(self, full_name: str, since: str, state: str = "all", *, on_page: Callable[[PageObservation], None] | None = None, **pagination_options) -> PaginatedResult:
        owner, repo = validate_full_name(full_name)
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/issues", {"state": state, "since": since}, on_page=on_page, **pagination_options)

    def get_issue_detail(self, full_name: str, issue_number: int) -> dict[str, Any]:
        if type(issue_number) is not int or issue_number <= 0:
            raise AppError(400, "INVALID_ISSUE_NUMBER", "Issue 编号无效")
        owner, repo = validate_full_name(full_name)
        payload = _json(self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}"))
        if not isinstance(payload, dict) or payload.get("number") != issue_number or "pull_request" in payload:
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回的 Issue 详情无效")
        return payload

    def list_issue_comments_detailed(self, full_name: str, issue_number: int) -> PaginatedResult:
        if type(issue_number) is not int or issue_number <= 0:
            raise AppError(400, "INVALID_ISSUE_NUMBER", "Issue 编号无效")
        owner, repo = validate_full_name(full_name)
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/issues/{issue_number}/comments", max_pages=1)

    def get_pull_request_detail(self, full_name: str, pull_number: int) -> dict[str, Any]:
        if type(pull_number) is not int or pull_number <= 0:
            raise AppError(400, "INVALID_PULL_REQUEST_NUMBER", "Pull Request 编号无效")
        owner, repo = validate_full_name(full_name)
        payload = _json(self._request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}"))
        if not isinstance(payload, dict) or payload.get("number") != pull_number:
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回的 Pull Request 详情无效")
        return payload

    def list_pull_request_comments_detailed(self, full_name: str, pull_number: int) -> PaginatedResult:
        if type(pull_number) is not int or pull_number <= 0:
            raise AppError(400, "INVALID_PULL_REQUEST_NUMBER", "Pull Request 编号无效")
        owner, repo = validate_full_name(full_name)
        # Pull Request conversation comments use GitHub's Issues comments endpoint.
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/issues/{pull_number}/comments", max_pages=1)

    def list_pulls(self, full_name: str, state: str = "closed"):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/pulls", {"state": state, "sort": "updated", "direction": "desc"})

    def list_pulls_detailed(self, full_name: str, state: str = "closed", *, on_page: Callable[[PageObservation], None] | None = None, **pagination_options) -> PaginatedResult:
        owner, repo = validate_full_name(full_name)
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/pulls", {"state": state, "sort": "updated", "direction": "desc"}, on_page=on_page, **pagination_options)

    def list_releases(self, full_name: str):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/releases", {})

    def list_releases_detailed(self, full_name: str, *, on_page: Callable[[PageObservation], None] | None = None, **pagination_options) -> PaginatedResult:
        owner, repo = validate_full_name(full_name)
        return self.list_paginated_detailed(f"/repos/{owner}/{repo}/releases", {}, on_page=on_page, **pagination_options)

    def list_paginated(self, path: str, params: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], bool, list[str]]:
        result = self.list_paginated_detailed(path, params)
        if result.error_code:
            raise AppError(
                result.error_status_code or 502,
                result.error_code,
                result.error_message or "GitHub 分页请求失败",
                result.error_details,
            )
        return result.items, result.complete, result.raw_pages

    def list_paginated_detailed(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        on_page: Callable[[PageObservation], None] | None = None,
        max_pages: int | None = None,
        resume_url: str | None = None,
        page_offset: int = 0,
        records_offset: int = 0,
        collect_items: bool = True,
        collect_raw_pages: bool = True,
        stop_after_page: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> PaginatedResult:
        rows: list[dict[str, Any]] = []
        archives: list[str] = []
        if page_offset < 0 or records_offset < 0:
            raise ValueError("pagination offsets must be non-negative")
        if resume_url is not None and not _is_github_api_url(resume_url):
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "保存的分页地址无效，不能安全恢复")
        next_url: str | None = resume_url or path
        current_params = {"per_page": 100, **(params or {})}
        page_cap = self.max_pages if max_pages is None else max_pages
        if page_cap is not None and page_cap < 1:
            raise ValueError("max_pages must be positive")
        initial_metrics = self.request_metrics_snapshot()
        started_at = time.monotonic()
        pages_this_call = 0
        observed_this_call = 0
        while page_cap is None or pages_this_call < page_cap:
            page_started = time.monotonic()
            try:
                response = self._request("GET", next_url, params=current_params if pages_this_call == 0 and resume_url is None else None)
                data = _json(response)
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效分页数据")
            except AppError as exc:
                final_metrics = self.request_metrics_snapshot()
                return PaginatedResult(
                    items=rows,
                    raw_pages=archives,
                    complete=False,
                    pages_fetched=pages_this_call,
                    observed_items=observed_this_call,
                    has_next=next_url is not None,
                    error_code=exc.code,
                    error_message=exc.message,
                    error_status_code=exc.status_code,
                    error_details=dict(exc.details),
                    http_calls=int(final_metrics["http_calls"] - initial_metrics["http_calls"]),
                    rate_limited_count=int(final_metrics["rate_limited_count"] - initial_metrics["rate_limited_count"]),
                    timeout_count=int(final_metrics["timeout_count"] - initial_metrics["timeout_count"]),
                    duration_ms=max(0.0, (time.monotonic() - started_at) * 1000),
                )
            link = response.links.get("next")
            page_next_url = link["url"] if link else None
            if page_next_url is not None and not _is_github_api_url(page_next_url):
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效分页地址")
            if collect_items:
                rows.extend(data)
            if collect_raw_pages:
                archives.append(response.text)
            pages_this_call += 1
            observed_this_call += len(data)
            next_url = page_next_url
            current_params = {}
            if on_page is not None:
                on_page(PageObservation(
                    page_index=page_offset + pages_this_call,
                    pages_fetched=page_offset + pages_this_call,
                    observed_items=records_offset + observed_this_call,
                    page_cap=page_cap,
                    has_next=next_url is not None,
                    duration_ms=max(0.0, (time.monotonic() - page_started) * 1000),
                    records=data,
                    raw_body=response.text,
                    request_url=str(response.request.url),
                    next_url=next_url,
                    http_status=response.status_code,
                ))
            if stop_after_page is not None and stop_after_page(data):
                next_url = None
            if next_url is None:
                break
        final_metrics = self.request_metrics_snapshot()
        has_next = next_url is not None
        return PaginatedResult(
            items=rows,
            raw_pages=archives,
            complete=not has_next,
            pages_fetched=pages_this_call,
            observed_items=observed_this_call,
            has_next=has_next,
            http_calls=int(final_metrics["http_calls"] - initial_metrics["http_calls"]),
            rate_limited_count=int(final_metrics["rate_limited_count"] - initial_metrics["rate_limited_count"]),
            timeout_count=int(final_metrics["timeout_count"] - initial_metrics["timeout_count"]),
            duration_ms=max(0.0, (time.monotonic() - started_at) * 1000),
        )


def validate_full_name(value: str) -> tuple[str, str]:
    value = value.strip()
    if value.lower().endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or not all(REPO_NAME.fullmatch(part) for part in parts) or parts[0] in {".", ".."} or parts[1] in {".", ".."}:
        raise AppError(400, "INVALID_REPOSITORY_URL", "请输入有效的 GitHub owner/repo")
    return parts[0], parts[1]


def parse_repository_input(value: str) -> str:
    value = value.strip()
    if value.startswith(("https://", "http://")):
        try:
            parsed = urlsplit(value)
            if parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
                raise ValueError
            if parsed.scheme != "https":
                raise ValueError
            path = parsed.path.strip("/")
            if parsed.path.startswith("//") or path.count("/") != 1:
                raise ValueError
            owner, repo = validate_full_name(path)
            return f"{owner}/{repo}"
        except ValueError as exc:
            raise AppError(400, "INVALID_REPOSITORY_URL", "只接受 https://github.com/owner/repo 或 owner/repo") from exc
    try:
        owner, repo = validate_full_name(value)
        return f"{owner}/{repo}"
    except AppError as exc:
        raise AppError(400, "INVALID_REPOSITORY_URL", "只接受 https://github.com/owner/repo 或 owner/repo") from exc


def retry_after_seconds(response: httpx.Response) -> int | None:
    header = response.headers.get("Retry-After")
    if header and header.isdigit():
        return int(header)
    if header:
        try:
            retry_at = parsedate_to_datetime(header)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0, int((retry_at - datetime.now(UTC)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            pass
    reset = response.headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        return max(0, int(reset) - int(time.time()))
    return None


def is_rate_limited_response(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    if retry_after_seconds(response) is not None or response.headers.get("X-RateLimit-Remaining") == "0":
        return True
    try:
        message = str(response.json().get("message", "")).lower()
    except (AttributeError, ValueError):
        return False
    return "rate limit" in message or "abuse detection" in message


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效 JSON") from exc


def _is_github_api_url(value: str) -> bool:
    try:
        target = urlsplit(value)
        return target.scheme == "https" and target.hostname == "api.github.com" and not target.username and not target.password and target.port is None
    except ValueError:
        return False
