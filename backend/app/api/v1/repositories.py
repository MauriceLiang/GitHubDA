import json
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.clock import iso_z
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import CollectionTask, Repository, RepositorySnapshot
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.repositories import (
    AnalysisResponse,
    ClearRepositoryDataRequest,
    ClearRepositoryDataResponse,
    RefreshRequest,
    RefreshResponse,
    RepositoryDetail,
    SeriesResponse,
)
from backend.app.services.repositories import add_idempotency_response, analysis_status, cached_idempotency_response, enqueue_refresh, latest_analysis, latest_snapshot, summary
from backend.app.services.repository_data import clear_repository_data


router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("/data/clear", response_model=SuccessEnvelope[ClearRepositoryDataResponse])
def clear_selected_repository_data(
    request: Request,
    body: ClearRepositoryDataRequest,
    session: Session = Depends(get_session),
):
    result = clear_repository_data(
        session,
        body.repository_ids,
        remove_from_library=body.remove_from_library,
    )
    return envelope(request, result)


@router.get("/{repository_id}", response_model=SuccessEnvelope[RepositoryDetail])
def repository_detail(repository_id: int, request: Request, session: Session = Depends(get_session)):
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    snapshot = latest_snapshot(session, repository_id)
    analysis = latest_analysis(session, repository_id)
    topics = []
    if repo.topics_json:
        try:
            topics = json.loads(repo.topics_json)
        except ValueError:
            topics = []
    metadata = None
    if snapshot:
        metadata = {"source": "GitHub REST API", "collected_at": iso_z(snapshot.collected_at), "window_start": None, "window_end": None, "sample_size": 1, "dataset_id": None, "coverage": analysis.coverage if analysis else "complete", "notes": []}
    return envelope(request, {
        "repository": summary(session, repo),
        "html_url": repo.html_url,
        "topics": topics,
        "license_spdx": repo.license_spdx,
        "size_kb": repo.size_kb,
        "open_issues_and_pr_count": snapshot.open_issues_and_pr_count if snapshot else None,
        "source_metadata": metadata,
    })


@router.post("/{repository_id}/refresh", response_model=SuccessEnvelope[RefreshResponse], status_code=202)
def refresh_repository(
    repository_id: int,
    request: Request,
    body: RefreshRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
):
    cached = cached_idempotency_response(session, "repository.refresh", idempotency_key)
    if cached:
        response.status_code = cached[1]
        return envelope(request, cached[0])
    result = enqueue_refresh(session, repository_id, body.depth, idempotency_key, force=body.force, scope_kind=body.scope_kind)
    result, status_code = add_idempotency_response(session, "repository.refresh", idempotency_key, result, 202)
    response.status_code = status_code
    return envelope(request, result)


@router.get("/{repository_id}/analysis", response_model=SuccessEnvelope[AnalysisResponse])
def repository_analysis(repository_id: int, request: Request, depth: str = Query(default="basic", pattern="^(basic|deep)$"), session: Session = Depends(get_session)):
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    result = latest_analysis(session, repository_id, depth)
    task = session.scalar(select(CollectionTask).where(CollectionTask.repository_id == repository_id, CollectionTask.depth == depth).order_by(desc(CollectionTask.created_at)).limit(1))
    if result:
        analysis_state = "partial" if result.coverage == "partial" else "completed"
        metrics = json.loads(result.metrics_json)
        collected_at = result.source_collected_at
        modules = {
            "profile": {"coverage": "complete"},
            "activity": {"coverage": "not_collected" if depth == "basic" else result.coverage},
            "community": {"coverage": "not_collected" if depth == "basic" else result.coverage},
        }
        metadata = {"source": "GitHub REST API", "collected_at": iso_z(collected_at), "window_start": iso_z(result.window_start), "window_end": iso_z(result.window_end), "sample_size": 1, "dataset_id": None, "coverage": result.coverage, "notes": []}
        limitations = json.loads(result.limitations_json)
    else:
        if task and task.status in {"queued", "running"}:
            analysis_state = "queued" if task.status == "queued" else "processing"
        elif task and task.status in {"partial", "failed"}:
            analysis_state = task.status
        else:
            analysis_state = "not_started"
        metrics = None
        modules = {"profile": {"coverage": "not_collected"}, "activity": {"coverage": "not_collected"}, "community": {"coverage": "not_collected"}}
        metadata = None
        limitations = ["尚无该分析深度的有效结果"]
    return envelope(request, {"repository_id": repository_id, "depth": depth, "analysis_status": analysis_state, "metrics": metrics, "modules": modules, "source_metadata": metadata, "limitations": limitations})


@router.get("/{repository_id}/series", response_model=SuccessEnvelope[SeriesResponse])
def repository_series(
    repository_id: int,
    request: Request,
    metric: str = Query(pattern="^(stars|forks)$"),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    granularity: str = Query(default="day", pattern="^day$"),
    session: Session = Depends(get_session),
):
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    if from_day and to_day and from_day > to_day:
        raise AppError(422, "VALIDATION_ERROR", "from 不能晚于 to", {"fields": [{"field": "from", "message": "必须早于或等于 to"}]})
    snapshots = session.scalars(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(RepositorySnapshot.collected_at, RepositorySnapshot.id)).all()
    per_day = {}
    for snapshot in snapshots:
        day = snapshot.collected_at.date()
        if (from_day and day < from_day) or (to_day and day > to_day):
            continue
        value = getattr(snapshot, metric)
        if value is not None:
            per_day[day.isoformat()] = value
    points = [{"date": day, "value": value} for day, value in sorted(per_day.items())]
    return envelope(request, {"repository_id": repository_id, "metric": metric, "points": points, "observed_days": len(points), "note": "仅包含实际采集日期，没有补值"})
