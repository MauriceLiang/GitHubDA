import re
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError


GITHUB_API = "https://api.github.com"
_rate_lock = threading.Lock()
_request_lock = threading.Lock()
_rate_cache: dict[str, Any] = {"remaining": None, "reset_at": None, "checked_at": None}
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class GitHubClient:
    def __init__(self, client: httpx.Client | None = None, request_id: str | None = None):
        settings = get_settings()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "GitHubDA/0.1",
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
        self.max_pages = settings.github_max_pages

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

    def _request_locked(self, method: str, path_or_url: str, *, params: dict[str, Any] | None = None, etag: str | None = None, redirect_depth: int = 0) -> httpx.Response:
        if path_or_url.startswith("http"):
            if not _is_github_api_url(path_or_url):
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效分页地址")
        headers = {"If-None-Match": etag} if etag else None
        for attempt in range(3):
            try:
                response = self.client.request(method, path_or_url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                raise AppError(504, "GITHUB_TIMEOUT", "GitHub 请求超时") from exc
            except httpx.RequestError as exc:
                if attempt < 2:
                    time.sleep(0.15 * (2**attempt))
                    continue
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "无法连接 GitHub") from exc
            self._cache_rate_limit(response)
            if response.status_code == 429 or _is_rate_limited_403(response):
                retry_after = _retry_after(response)
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

    def list_issues(self, full_name: str, since: str, state: str = "all"):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/issues", {"state": state, "since": since})

    def list_pulls(self, full_name: str, state: str = "closed"):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/pulls", {"state": state, "sort": "updated", "direction": "desc"})

    def list_releases(self, full_name: str):
        owner, repo = validate_full_name(full_name)
        return self.list_paginated(f"/repos/{owner}/{repo}/releases", {})

    def list_paginated(self, path: str, params: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], bool, list[str]]:
        rows: list[dict[str, Any]] = []
        archives: list[str] = []
        next_url: str | None = path
        current_params = {"per_page": 100, **(params or {})}
        complete = True
        for page in range(self.max_pages):
            response = self._request("GET", next_url, params=current_params if page == 0 else None)
            data = _json(response)
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回了无效分页数据")
            rows.extend(data)
            archives.append(response.text)
            link = response.links.get("next")
            next_url = link["url"] if link else None
            current_params = {}
            if next_url is None:
                return rows, complete, archives
        if next_url:
            complete = False
        return rows, complete, archives


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


def _retry_after(response: httpx.Response) -> int | None:
    header = response.headers.get("Retry-After")
    if header and header.isdigit():
        return int(header)
    reset = response.headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        return max(0, int(reset) - int(time.time()))
    return None


def _is_rate_limited_403(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    if _retry_after(response) is not None or response.headers.get("X-RateLimit-Remaining") == "0":
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
