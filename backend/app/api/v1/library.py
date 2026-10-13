from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_github_client, get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient, validate_full_name
from backend.app.persistence.models import DatasetRepository, Repository
from backend.app.schemas.analytics import RepositoryListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.repositories import AddRepositoryRequest, AddRepositoryResponse
from backend.app.services.repositories import LIBRARY_ID, add_idempotency_response, cached_idempotency_response, enqueue_add, summary


router = APIRouter(prefix="/library/repositories", tags=["library"])


@router.post("", response_model=SuccessEnvelope[AddRepositoryResponse], status_code=201, responses={200: {"model": SuccessEnvelope[AddRepositoryResponse]}})
def add_repository(
    request: Request,
    body: AddRepositoryRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
    github: GitHubClient = Depends(get_github_client),
):
    cached = cached_idempotency_response(session, "library.add", idempotency_key)
    if cached:
        response.status_code = cached[1]
        return envelope(request, cached[0])
    owner, repo_name = validate_full_name(body.full_name)
    payload, _status, _etag = github.get_repository(f"{owner}/{repo_name}")
    if not payload or payload.get("private") is not False:
        raise AppError(404, "REPOSITORY_NOT_FOUND", "仓库不存在或不可公开访问")
    data, status_code = enqueue_add(session, payload, body.auto_analyze, body.depth, idempotency_key)
    data, status_code = add_idempotency_response(session, "library.add", idempotency_key, data, status_code)
    response.status_code = status_code
    return envelope(request, data)


@router.get("", response_model=SuccessEnvelope[RepositoryListResponse])
def list_repositories(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    language: str | None = None,
    status: str | None = Query(default=None, pattern="^(not_started|queued|processing|completed|partial|failed)$"),
    sort: str = Query(default="name", pattern="^(name|stars|last_collected)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    repo_ids = select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == LIBRARY_ID)
    statement = select(Repository).where(Repository.repository_id.in_(repo_ids))
    if q:
        statement = statement.where(Repository.full_name.ilike(f"%{q}%") | Repository.description.ilike(f"%{q}%"))
    if language:
        statement = statement.where(Repository.language == language)
    all_repos = session.scalars(statement).all()
    rows = [summary(session, repo) for repo in all_repos]
    if status:
        rows = [row for row in rows if row["analysis_status"] == status]
    reverse = order == "desc"
    if sort == "name":
        rows.sort(key=lambda row: row["full_name"].casefold(), reverse=reverse)
    elif sort == "stars":
        rows.sort(key=lambda row: (row["stars"] is None, row["stars"] or 0), reverse=reverse)
    else:
        rows.sort(key=lambda row: (row["last_successful_collection_at"] is None, row["last_successful_collection_at"] or ""), reverse=reverse)
    total = len(rows)
    start = (page - 1) * per_page
    return envelope(request, {"items": rows[start : start + per_page]}, pagination=pagination(page, per_page, total))


@router.delete("/{repository_id}", status_code=204)
def remove_repository(repository_id: int, session: Session = Depends(get_session)):
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    membership = session.get(DatasetRepository, (LIBRARY_ID, repository_id))
    if membership:
        session.delete(membership)
        session.commit()
    return Response(status_code=204)
