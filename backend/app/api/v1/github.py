import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_github_client, get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient, parse_repository_input, validate_full_name
from backend.app.schemas.analytics import SearchResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.repositories import RepositoryPreview, ResolveRequest
from backend.app.services.repositories import LIBRARY_ID, membership_exists, preview
from backend.app.persistence.models import DatasetRepository


router = APIRouter(prefix="/github", tags=["github"])
LANGUAGES = {"all", "c", "c++", "c#", "go", "java", "javascript", "typescript", "python", "rust", "ruby", "php", "swift", "kotlin", "scala", "shell", "html", "css", "jupyter notebook", "objective-c", "dart", "elixir", "haskell", "lua", "perl", "r", "sql", "vue", "svelte"}
SAFE_QUERY = re.compile(r"^[\w ._+/#-]+$", re.UNICODE)


@router.get("/search", response_model=SuccessEnvelope[SearchResponse])
def search_repositories(
    request: Request,
    q: str = Query(min_length=2, max_length=100),
    language: str | None = None,
    stars_min: int | None = Query(default=None, ge=0, le=1_000_000),
    sort: str = Query(default="best_match", pattern="^(best_match|stars|updated)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1, le=10),
    per_page: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    github: GitHubClient = Depends(get_github_client),
):
    if (page - 1) * per_page >= 1000:
        raise AppError(422, "VALIDATION_ERROR", "搜索页超出 GitHub 1000 条结果窗口", {"fields": [{"field": "page", "message": "page 与 per_page 的乘积必须小于 1000"}]})
    if not SAFE_QUERY.fullmatch(q) or any(ord(char) < 32 for char in q) or ":" in q:
        raise AppError(422, "VALIDATION_ERROR", "搜索词包含不支持的字符或 GitHub 查询语法", {"fields": [{"field": "q", "message": "请输入普通仓库名称或关键词"}]})
    if language is not None and language.lower() not in LANGUAGES:
        raise AppError(422, "VALIDATION_ERROR", "language 不在允许列表中", {"fields": [{"field": "language", "message": "请使用支持的语言名称或 all"}]})
    result = github.search_repositories(q, language, stars_min, sort, order, page, per_page)
    rows = []
    for item in result["items"]:
        is_member = session.get(DatasetRepository, (LIBRARY_ID, item.get("id"))) is not None
        rows.append(preview(item, is_member))
    visible_total = min(result["total_count"], 1000)
    search_meta = {"total_count": result["total_count"], "incomplete_results": result["incomplete_results"], "result_window_limit": 1000}
    page_meta = pagination(page, per_page, visible_total)
    page_meta["has_next"] = page * per_page < visible_total and (page * per_page) < 1000
    return envelope(request, {"items": rows}, pagination=page_meta, search=search_meta)


@router.post("/resolve", response_model=SuccessEnvelope[RepositoryPreview])
def resolve_repository(request: Request, body: ResolveRequest, session: Session = Depends(get_session), github: GitHubClient = Depends(get_github_client)):
    full_name = parse_repository_input(body.input)
    owner, repo = validate_full_name(full_name)
    payload, _status, _etag = github.get_repository(f"{owner}/{repo}")
    if not payload or payload.get("private") is not False:
        raise AppError(404, "REPOSITORY_NOT_FOUND", "仓库不存在或不可公开访问")
    return envelope(request, preview(payload, membership_exists(session, payload["id"])))
