from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError


router = APIRouter(prefix="/api/browser", tags=["browser"])
SESSION_COOKIE = "githubda_browser_session"
SESSION_TTL_SECONDS = 1800
MAX_REQUEST_BYTES = 1_000_000
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class BrowserSession:
    session_id: str
    csrf_token: str


@dataclass
class SessionEntry:
    csrf_token: str
    expires_at: float


def _loopback_name(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip("[]").rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _local_request(request: Request) -> bool:
    peer = request.client.host if request.client else ""
    return _loopback_name(peer) and _loopback_name(request.url.hostname)


def _origin_allowed(request: Request, origin: str) -> bool:
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    if not _loopback_name(parsed.hostname):
        return False
    if parsed.scheme != request.url.scheme and not (parsed.scheme == "http" and request.url.scheme == "http"):
        return False
    allowed = {request.base_url.netloc.lower()}
    configured = [item.strip().lower().rstrip("/") for item in os.getenv("BROWSER_ALLOWED_ORIGINS", "").split(",") if item.strip()]
    if origin.lower().rstrip("/") in configured or parsed.netloc.lower() in allowed:
        return True
    # Vite's local development origin is accepted only as a loopback origin.
    return parsed.port == 5173 and parsed.scheme == "http"


def _security_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": {}}, "request_id": getattr(request.state, "request_id", "req_unknown")},
        headers={"Cache-Control": "no-store"},
    )


def _sessions(request: Request) -> dict[str, SessionEntry]:
    sessions = getattr(request.app.state, "browser_sessions", None)
    if sessions is None:
        sessions = {}
        request.app.state.browser_sessions = sessions
    return sessions


def _check_local_origin(request: Request) -> tuple[int, str, str] | None:
    if not _local_request(request):
        return 403, "LOCAL_ACCESS_ONLY", "浏览器入口仅允许本机访问"
    origin = request.headers.get("origin")
    if origin and not _origin_allowed(request, origin):
        return 403, "ORIGIN_NOT_ALLOWED", "请求来源未获允许"
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        return 403, "CROSS_SITE_REQUEST", "拒绝跨站浏览器请求"
    if request.headers.get("x-gda-request") != "browser":
        return 403, "BROWSER_REQUEST_REQUIRED", "请求缺少浏览器校验标记"
    return None


@router.get("/session", include_in_schema=False)
def create_browser_session(request: Request, response: Response):
    blocked = _check_local_origin(request)
    if blocked:
        return _security_error(request, *blocked)

    now = time.time()
    sessions = _sessions(request)
    for session_id, entry in list(sessions.items()):
        if entry.expires_at <= now:
            sessions.pop(session_id, None)

    session_id = request.cookies.get(SESSION_COOKIE)
    entry = sessions.get(session_id or "")
    if entry is None or entry.expires_at <= now:
        session_id = secrets.token_urlsafe(32)
        entry = SessionEntry(csrf_token=secrets.token_urlsafe(32), expires_at=now + SESSION_TTL_SECONDS)
        sessions[session_id] = entry

    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/api/browser",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": entry.csrf_token, "expires_in": SESSION_TTL_SECONDS}


def require_browser_session(request: Request) -> BrowserSession:
    blocked = _check_local_origin(request)
    if blocked:
        raise AppError(*blocked)
    session_id = request.cookies.get(SESSION_COOKIE)
    entry = _sessions(request).get(session_id or "")
    if not session_id or not entry or entry.expires_at <= time.time():
        if session_id:
            _sessions(request).pop(session_id, None)
        raise AppError(401, "BROWSER_SESSION_EXPIRED", "本机浏览器会话已过期，请刷新页面重新连接")
    if request.method.upper() not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if not origin or not _origin_allowed(request, origin):
            raise AppError(403, "ORIGIN_NOT_ALLOWED", "修改数据的请求必须来自本机允许的页面")
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied, entry.csrf_token):
            raise AppError(403, "CSRF_VALIDATION_FAILED", "请求校验失败，请刷新页面后重试")
    return BrowserSession(session_id=session_id, csrf_token=entry.csrf_token)


@router.post("/session/revoke", include_in_schema=False)
def revoke_browser_session(request: Request, browser_session: BrowserSession = Depends(require_browser_session)):
    _sessions(request).pop(browser_session.session_id, None)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/api/browser", httponly=True, samesite="strict", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.api_route("/v1/{path:path}", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def proxy_api(path: str, request: Request, browser_session: BrowserSession = Depends(require_browser_session)):
    del browser_session
    segments = path.split("/")
    if not path or any(segment in {"", ".", ".."} for segment in segments) or "\\" in path:
        return _security_error(request, 404, "RESOURCE_NOT_FOUND", "请求的资源不存在")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return _security_error(request, 413, "REQUEST_TOO_LARGE", "请求内容过大")

    key = get_settings().internal_api_key
    if not key:
        return _security_error(request, 503, "BACKEND_UNAVAILABLE", "后端尚未配置内部 API 凭据")

    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        return _security_error(request, 413, "REQUEST_TOO_LARGE", "请求内容过大")
    headers = {"X-Internal-Api-Key": key, "X-Request-ID": getattr(request.state, "request_id", "req_unknown")}
    for name in ("accept", "content-type", "idempotency-key"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    target = f"/api/v1/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    try:
        transport = httpx.ASGITransport(app=request.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://githubda.internal", timeout=25.0) as client:
            upstream = await client.request(request.method, target, headers=headers, content=body or None)
    except httpx.RequestError:
        return _security_error(request, 503, "BACKEND_UNAVAILABLE", "本机 API 暂时不可用")

    forwarded = {name: value for name, value in upstream.headers.items() if name.lower() in {"content-type", "content-disposition", "x-request-id", "cache-control"}}
    forwarded["Cache-Control"] = "no-store"
    return Response(content=upstream.content, status_code=upstream.status_code, headers=forwarded)
