from typing import Any

from backend.app.core.clock import parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import validate_full_name


def clean_repository_profile(payload: dict[str, Any], expected_id: int) -> dict[str, Any]:
    if payload.get("id") != expected_id:
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回的仓库 ID 与待采集仓库不一致")
    if payload.get("private") is not False:
        raise AppError(404, "REPOSITORY_NOT_FOUND", "仓库不存在或不可公开访问")
    stars, forks = _count(payload, "stargazers_count"), _count(payload, "forks_count")
    if stars is None or forks is None or not isinstance(payload.get("full_name"), str):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库指标缺少有效值")
    owner, repo = validate_full_name(payload["full_name"])
    return {
        "stars": stars,
        "forks": forks,
        "full_name": f"{owner}/{repo}",
        "open_issues_and_pr_count": _count(payload, "open_issues_count"),
        "created_at": parse_github_datetime(payload.get("created_at")),
        "pushed_at": parse_github_datetime(payload.get("pushed_at")),
        "github_updated_at": parse_github_datetime(payload.get("updated_at")),
    }


def _count(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None
