from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import CollectionTask, Repository, RequestIdempotency
from backend.app.persistence.db import begin_immediate
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.tasks import RetryResponse, TaskListResponse, TaskResponse
from backend.app.services.repositories import add_idempotency_response, cached_idempotency_response, make_task


router = APIRouter(prefix="/tasks", tags=["tasks"])
TASK_STATUSES = {"queued", "running", "succeeded", "partial", "failed", "cancelled"}


def task_payload(task: CollectionTask) -> dict:
    error = {"code": task.error_code, "message": task.error_message} if task.error_code else None
    return {"task_id": task.task_id, "repository_id": task.repository_id, "type": task.type, "depth": task.depth, "status": task.status, "phase": task.phase, "progress_percent": task.progress_percent, "message": task.message, "attempt": task.attempt, "created_at": iso_z(task.created_at), "started_at": iso_z(task.started_at), "finished_at": iso_z(task.finished_at), "error": error}


@router.get("", response_model=SuccessEnvelope[TaskListResponse])
def list_tasks(
    request: Request,
    status: str | None = Query(default=None, pattern="^(queued|running|succeeded|partial|failed|cancelled)$"),
    repository_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    statement = select(CollectionTask)
    count_statement = select(func.count()).select_from(CollectionTask)
    if status:
        statement = statement.where(CollectionTask.status == status)
        count_statement = count_statement.where(CollectionTask.status == status)
    if repository_id:
        statement = statement.where(CollectionTask.repository_id == repository_id)
        count_statement = count_statement.where(CollectionTask.repository_id == repository_id)
    total = int(session.scalar(count_statement) or 0)
    tasks = session.scalars(statement.order_by(desc(CollectionTask.created_at)).offset((page - 1) * per_page).limit(per_page)).all()
    return envelope(request, {"items": [task_payload(task) for task in tasks]}, pagination=pagination(page, per_page, total))


@router.get("/{task_id}", response_model=SuccessEnvelope[TaskResponse])
def get_task(task_id: str, request: Request, session: Session = Depends(get_session)):
    task = session.get(CollectionTask, task_id)
    if task is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "任务不存在")
    return envelope(request, task_payload(task))


@router.post("/{task_id}/retry", response_model=SuccessEnvelope[RetryResponse], status_code=202)
def retry_task(
    task_id: str,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
):
    cached = cached_idempotency_response(session, "task.retry", idempotency_key)
    if cached:
        response.status_code = cached[1]
        return envelope(request, cached[0])
    original = session.get(CollectionTask, task_id)
    if original is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "任务不存在")
    if original.status not in {"failed", "partial"}:
        raise AppError(409, "CONFLICTING_OPERATION", "只有 failed 或 partial 任务可以重试")
    active = session.scalar(select(CollectionTask.task_id).where(CollectionTask.repository_id == original.repository_id, CollectionTask.status.in_(["queued", "running"])).limit(1))
    if active:
        raise AppError(409, "CONFLICTING_OPERATION", "该仓库已有排队或执行中的采集任务")
    if idempotency_key:
        previous = session.scalar(select(CollectionTask).where(CollectionTask.idempotency_key == idempotency_key))
        if previous and previous.created_at >= utc_now() - timedelta(hours=24):
            result = {"task_id": previous.task_id, "retry_of": previous.retry_of, "status": "queued"}
            response.status_code = 202
            return envelope(request, result)
    begin_immediate(session)
    original = session.get(CollectionTask, task_id)
    if original is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "任务不存在")
    if original.status not in {"failed", "partial"}:
        raise AppError(409, "CONFLICTING_OPERATION", "只有 failed 或 partial 任务可以重试")
    active = session.scalar(select(CollectionTask.task_id).where(CollectionTask.repository_id == original.repository_id, CollectionTask.status.in_(["queued", "running"])).limit(1))
    if active:
        raise AppError(409, "CONFLICTING_OPERATION", "该仓库已有排队或执行中的采集任务")
    task = CollectionTask(task_id=str(uuid4()), repository_id=original.repository_id, depth=original.depth, status="queued", retry_of=original.task_id, idempotency_key=idempotency_key)
    session.add(task)
    result = {"task_id": task.task_id, "retry_of": original.task_id, "status": "queued"}
    session.commit()
    result, status_code = add_idempotency_response(session, "task.retry", idempotency_key, result, 202)
    response.status_code = status_code
    return envelope(request, result)
