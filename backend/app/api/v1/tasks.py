from datetime import timedelta
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import desc, func, literal, select, union_all, update
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    CollectionTask,
    DatasetImportJob,
    DatasetImportStagingRecord,
    Repository,
    TaskModuleProgress,
)
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.tasks import RetryResponse, TaskListResponse, TaskResponse
from backend.app.services.dataset_import import _json_object
from backend.app.services.repositories import add_idempotency_response, cached_idempotency_response


router = APIRouter(prefix="/tasks", tags=["tasks"])
TASK_STATUSES = {"queued", "running", "succeeded", "partial", "failed", "cancelled"}
TASK_TYPES = {"repository_collection", "dataset_import"}
MODULE_ORDER = ("profile", "commits", "issues", "pulls", "releases")


def task_payload(task: CollectionTask, module_progress: list[TaskModuleProgress] | None = None, repository_name: str | None = None) -> dict:
    error = {"code": task.error_code, "message": task.error_message} if task.error_code else None
    module_by_name = {row.module: row for row in module_progress or []}
    modules = [
        {
            "name": name,
            "status": module_by_name[name].status,
            "coverage": module_by_name[name].coverage,
            "pages_fetched": module_by_name[name].pages_fetched,
            "page_cap": module_by_name[name].page_cap,
            "observed_items": module_by_name[name].observed_items,
            "elapsed_seconds": module_by_name[name].elapsed_seconds,
            "error_code": module_by_name[name].error_code,
        }
        for name in MODULE_ORDER
        if name in module_by_name
    ]
    elapsed_seconds = None
    if task.started_at is not None:
        elapsed_end = task.finished_at or utc_now()
        elapsed_seconds = round(max(0.0, (elapsed_end - task.started_at).total_seconds()), 3)
    try:
        scope = json.loads(task.scope_json or "{}")
    except (TypeError, ValueError):
        scope = {}
    window_start = scope.get("window_start") if isinstance(scope, dict) else None
    window_end = scope.get("window_end") if isinstance(scope, dict) else None
    window_days = scope.get("window_days") if isinstance(scope, dict) else None
    if not isinstance(window_days, int) or isinstance(window_days, bool):
        if task.scope_kind in {"quick", "window"}:
            start = parse_github_datetime(window_start)
            end = parse_github_datetime(window_end)
            window_days = max(1, round((end - start).total_seconds() / 86400)) if start is not None and end is not None and start < end else None
        else:
            window_days = None
    return {
        "task_id": task.task_id,
        "task_type": "repository_collection",
        "target_type": "repository",
        "target_id": str(task.repository_id),
        "display_name": repository_name or f"仓库 #{task.repository_id}",
        "operation": task.type,
        "repository_id": task.repository_id,
        "type": task.type,
        "depth": task.depth,
        "scope_kind": task.scope_kind or "quick",
        "window_days": window_days,
        "window_start": window_start if isinstance(window_start, str) else None,
        "window_end": window_end if isinstance(window_end, str) else None,
        "status": task.status,
        "phase": task.phase,
        "progress_percent": task.progress_percent,
        "message": task.message,
        "attempt": task.attempt,
        "created_at": iso_z(task.created_at),
        "started_at": iso_z(task.started_at),
        "finished_at": iso_z(task.finished_at),
        "resume_after": iso_z(task.resume_after),
        "error": error,
        "progress_kind": task.progress_kind or "unknown",
        "progress_updated_at": iso_z(task.progress_updated_at),
        "current_module": task.current_module,
        "modules": modules,
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": None,
        "updated_at": iso_z(task.progress_updated_at or task.heartbeat_at or task.finished_at or task.started_at or task.created_at),
        "current_file": None,
        "processed_records": None,
        "total_records": None,
        "result": None,
        "retry_of": task.retry_of,
    }


def dataset_task_payload(job: DatasetImportJob) -> dict:
    error = {"code": job.error_code, "message": job.error_message} if job.error_code else None
    elapsed_seconds = None
    if job.started_at is not None:
        elapsed_end = job.finished_at or utc_now()
        elapsed_seconds = round(max(0.0, (elapsed_end - job.started_at).total_seconds()), 3)
    return {
        "task_id": job.task_id,
        "task_type": "dataset_import",
        "target_type": "dataset",
        "target_id": job.dataset_id,
        "display_name": "精选仓库数据集",
        "operation": "import",
        "repository_id": None,
        "type": "dataset_import",
        "depth": None,
        "scope_kind": None,
        "window_start": None,
        "window_end": None,
        "status": job.status,
        "phase": job.phase,
        "progress_percent": job.progress_percent,
        "message": job.message,
        "attempt": job.attempt,
        "created_at": iso_z(job.created_at),
        "started_at": iso_z(job.started_at),
        "finished_at": iso_z(job.finished_at),
        "resume_after": None,
        "error": error,
        "progress_kind": job.progress_kind,
        "progress_updated_at": iso_z(job.updated_at),
        "current_module": None,
        "modules": [],
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": None,
        "updated_at": iso_z(job.updated_at),
        "current_file": job.current_file,
        "processed_records": job.processed_records,
        "total_records": job.total_records,
        "result": _json_object(job.result_json),
        "retry_of": job.retry_of,
        "version": job.bundle_version,
    }


@router.get("", response_model=SuccessEnvelope[TaskListResponse])
def list_tasks(
    request: Request,
    status: str | None = Query(default=None, pattern="^(queued|running|succeeded|partial|failed|cancelled)$"),
    repository_id: int | None = Query(default=None, gt=0),
    task_type: str | None = Query(default=None, pattern="^(repository_collection|dataset_import)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    collection_query = select(
        CollectionTask.task_id.label("task_id"),
        CollectionTask.created_at.label("created_at"),
        literal("repository_collection").label("task_type"),
    )
    dataset_query = select(
        DatasetImportJob.task_id.label("task_id"),
        DatasetImportJob.created_at.label("created_at"),
        literal("dataset_import").label("task_type"),
    )
    if status:
        collection_query = collection_query.where(CollectionTask.status == status)
        dataset_query = dataset_query.where(DatasetImportJob.status == status)
    if repository_id:
        collection_query = collection_query.where(CollectionTask.repository_id == repository_id)
        dataset_query = dataset_query.where(False)
    if task_type == "repository_collection":
        dataset_query = dataset_query.where(False)
    elif task_type == "dataset_import":
        collection_query = collection_query.where(False)

    combined = union_all(collection_query, dataset_query).subquery()
    total = int(session.scalar(select(func.count()).select_from(combined)) or 0)
    page_rows = session.execute(
        select(combined.c.task_id, combined.c.task_type)
        .order_by(desc(combined.c.created_at), desc(combined.c.task_id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    collection_ids = [task_id for task_id, kind in page_rows if kind == "repository_collection"]
    dataset_ids = [task_id for task_id, kind in page_rows if kind == "dataset_import"]
    collections = {task.task_id: task for task in session.scalars(select(CollectionTask).where(CollectionTask.task_id.in_(collection_ids))).all()} if collection_ids else {}
    jobs = {job.task_id: job for job in session.scalars(select(DatasetImportJob).where(DatasetImportJob.task_id.in_(dataset_ids))).all()} if dataset_ids else {}
    repository_ids = [task.repository_id for task in collections.values()]
    repositories = {repository.repository_id: repository.full_name for repository in session.scalars(select(Repository).where(Repository.repository_id.in_(repository_ids))).all()} if repository_ids else {}
    module_rows = session.scalars(select(TaskModuleProgress).where(TaskModuleProgress.task_id.in_(collection_ids))).all() if collection_ids else []
    progress_by_task: dict[str, list[TaskModuleProgress]] = {}
    for module in module_rows:
        progress_by_task.setdefault(module.task_id, []).append(module)
    items = []
    for task_id, kind in page_rows:
        if kind == "repository_collection" and task_id in collections:
            collection = collections[task_id]
            items.append(task_payload(collection, progress_by_task.get(task_id), repositories.get(collection.repository_id)))
        elif kind == "dataset_import" and task_id in jobs:
            items.append(dataset_task_payload(jobs[task_id]))
    return envelope(request, {"items": items}, pagination=pagination(page, per_page, total))


@router.get("/{task_id}", response_model=SuccessEnvelope[TaskResponse])
def get_task(task_id: str, request: Request, session: Session = Depends(get_session)):
    job = session.get(DatasetImportJob, task_id)
    if job is not None:
        return envelope(request, dataset_task_payload(job))
    task = session.get(CollectionTask, task_id)
    if task is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "任务不存在")
    modules = session.scalars(select(TaskModuleProgress).where(TaskModuleProgress.task_id == task_id)).all()
    repository = session.get(Repository, task.repository_id)
    return envelope(request, task_payload(task, modules, repository.full_name if repository else None))


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
    dataset_job = session.get(DatasetImportJob, task_id)
    if dataset_job is not None:
        return _retry_dataset_import(request, response, session, dataset_job, idempotency_key)

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
    if original is None or original.status not in {"failed", "partial"}:
        raise AppError(409, "CONFLICTING_OPERATION", "任务状态已变化，不能重试")
    active = session.scalar(select(CollectionTask.task_id).where(CollectionTask.repository_id == original.repository_id, CollectionTask.status.in_(["queued", "running"])).limit(1))
    if active:
        raise AppError(409, "CONFLICTING_OPERATION", "该仓库已有排队或执行中的采集任务")
    task = CollectionTask(
        task_id=str(uuid4()), repository_id=original.repository_id, type=original.type, depth=original.depth,
        scope_kind=original.scope_kind or "quick", scope_json=original.scope_json,
        status="queued", retry_of=original.task_id, idempotency_key=idempotency_key,
    )
    session.add(task)
    result = {"task_id": task.task_id, "retry_of": original.task_id, "status": "queued"}
    session.commit()
    result, status_code = add_idempotency_response(session, "task.retry", idempotency_key, result, 202)
    response.status_code = status_code
    return envelope(request, result)


def _retry_dataset_import(request: Request, response: Response, session: Session, original: DatasetImportJob, idempotency_key: str | None):
    if original.status != "failed":
        raise AppError(409, "CONFLICTING_OPERATION", "只有失败的数据集导入任务可以重试")
    if idempotency_key:
        previous = session.scalar(select(DatasetImportJob).where(DatasetImportJob.idempotency_key == idempotency_key))
        if previous and previous.created_at >= utc_now() - timedelta(hours=24):
            result = {"task_id": previous.task_id, "retry_of": previous.retry_of, "status": "queued"}
            response.status_code = 202
            return envelope(request, result)

    begin_immediate(session)
    original = session.get(DatasetImportJob, original.task_id)
    if original is None or original.status != "failed":
        raise AppError(409, "CONFLICTING_OPERATION", "任务状态已变化，不能重试")
    active = session.scalar(
        select(DatasetImportJob.task_id).where(
            DatasetImportJob.dataset_id == original.dataset_id,
            DatasetImportJob.bundle_hash == original.bundle_hash,
            DatasetImportJob.status.in_(["queued", "running"]),
        ).limit(1)
    )
    if active:
        raise AppError(409, "CONFLICTING_OPERATION", "同一精选数据包已有排队或执行中的导入任务")

    staged_count = int(session.scalar(
        select(func.count()).select_from(DatasetImportStagingRecord)
        .where(DatasetImportStagingRecord.task_id == original.task_id)
    ) or 0)
    task = DatasetImportJob(
        task_id=str(uuid4()),
        dataset_id=original.dataset_id,
        bundle_version=original.bundle_version,
        bundle_hash=original.bundle_hash,
        status="queued",
        phase="staging" if staged_count else "validating",
        progress_kind="records" if staged_count else "indeterminate",
        progress_percent=(min(90, staged_count * 90 / original.total_records) if staged_count and original.total_records else None),
        processed_records=staged_count,
        total_records=original.total_records,
        message="从已暂存记录恢复导入" if staged_count else "等待导入 Worker",
        retry_of=original.task_id,
        idempotency_key=idempotency_key,
        staging_state_json="{}",
    )
    session.add(task)
    session.flush()
    session.execute(
        update(DatasetImportStagingRecord)
        .where(DatasetImportStagingRecord.task_id == original.task_id)
        .values(task_id=task.task_id)
    )
    result = {"task_id": task.task_id, "retry_of": original.task_id, "status": "queued"}
    session.commit()
    result, status_code = add_idempotency_response(session, "task.retry", idempotency_key, result, 202)
    response.status_code = status_code
    return envelope(request, result)
