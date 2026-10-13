import hmac
from collections.abc import Generator

from fastapi import Header, Request

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.db import get_session


def require_internal_api_key(x_internal_api_key: str | None = Header(default=None, alias="X-Internal-Api-Key")) -> None:
    configured = get_settings().internal_api_key
    if not configured:
        raise AppError(503, "BACKEND_UNAVAILABLE", "后端未配置 INTERNAL_API_KEY")
    if not x_internal_api_key or not hmac.compare_digest(x_internal_api_key, configured):
        raise AppError(401, "UNAUTHORIZED_CLIENT", "内部 API Key 无效")


def get_github_client(request: Request) -> Generator[GitHubClient, None, None]:
    client = GitHubClient(request_id=getattr(request.state, "request_id", None))
    try:
        yield client
    finally:
        client.close()
