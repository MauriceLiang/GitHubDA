from datetime import timedelta

from sqlalchemy import case, delete, select, text
from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.persistence.models import ApiRateLimitState, CollectionTask, TaskModuleProgress
from backend.app.worker.progress import initialize_attempt_progress


MAX_ATTEMPTS = 3


def claim_next_task(session: Session, worker_id: str, lease_seconds: int) -> CollectionTask | None:
    session.execute(text("BEGIN IMMEDIATE"))
    now = utc_now()
    stale = session.scalars(
        select(CollectionTask).where(
            CollectionTask.status == "running",
            CollectionTask.lease_until.is_not(None),
            CollectionTask.lease_until < now,
        )
    ).all()
    for task in stale:
        for progress in session.scalars(
            select(TaskModuleProgress).where(
                TaskModuleProgress.task_id == task.task_id,
                TaskModuleProgress.attempt == task.attempt,
                TaskModuleProgress.status == "running",
            )
        ).all():
            progress.status = "failed"
            progress.coverage = "partial"
            progress.finished_at = now
            progress.elapsed_seconds = max(0.0, (now - progress.started_at).total_seconds()) if progress.started_at else None
            progress.error_code = "WORKER_LEASE_EXPIRED"
            progress.last_updated_at = now
        if task.attempt >= MAX_ATTEMPTS:
            task.status = "failed"
            task.finished_at = now
            task.heartbeat_at = now
            task.phase = None
            task.progress_updated_at = now if task.progress_kind == "stages" else task.progress_updated_at
            task.current_module = None
            task.error_code = "WORKER_LEASE_EXPIRED"
            task.error_message = "Worker 租约过期且已达到最大尝试次数"
            task.message = task.error_message
        else:
            task.status = "queued"
            task.phase = None
            task.progress_kind = "unknown"
            task.progress_percent = None
            task.progress_updated_at = now
            task.current_module = None
            task.message = "Worker 重启后重新排队"
            session.execute(delete(TaskModuleProgress).where(TaskModuleProgress.task_id == task.task_id))
        task.lease_owner = None
        task.lease_until = None

    quota = session.get(ApiRateLimitState, "core")
    if quota is not None and (quota.remaining == 0 or quota.retry_after is not None):
        blocked_until = quota.retry_after or quota.reset_at
        if blocked_until is not None and blocked_until > now:
            session.commit()
            return None

    active = session.scalar(
        select(CollectionTask.task_id).where(
            CollectionTask.status == "running",
            CollectionTask.lease_until.is_not(None),
            CollectionTask.lease_until >= now,
        ).limit(1)
    )
    if active:
        session.commit()
        return None

    task = session.scalar(
        select(CollectionTask)
        .where(CollectionTask.status == "queued", (CollectionTask.resume_after.is_(None) | (CollectionTask.resume_after <= now)))
        .order_by(case((CollectionTask.scope_kind == "backfill", 1), else_=0), CollectionTask.created_at)
        .limit(1)
    )
    if task is None:
        session.commit()
        return None
    task.status = "running"
    task.phase = "collecting"
    task.attempt += 1
    task.started_at = task.started_at or now
    task.heartbeat_at = now
    task.lease_owner = worker_id
    task.lease_until = now + timedelta(seconds=lease_seconds)
    task.message = "正在从 GitHub 获取仓库数据"
    if task.depth == "deep":
        session.execute(delete(TaskModuleProgress).where(TaskModuleProgress.task_id == task.task_id))
        task.progress_kind = "stages"
        task.progress_percent = 0
        task.progress_updated_at = now
        task.current_module = "profile"
        initialize_attempt_progress(session, task, now)
    else:
        task.progress_kind = "unknown"
        task.progress_percent = None
        task.progress_updated_at = None
        task.current_module = None
    session.commit()
    session.refresh(task)
    return task


def heartbeat(session: Session, worker_id: str, active_task_id: str | None, lease_seconds: int) -> None:
    from backend.app.persistence.models import WorkerStatus

    now = utc_now()
    row = session.get(WorkerStatus, worker_id)
    if row is None:
        row = WorkerStatus(worker_id=worker_id, started_at=now, last_heartbeat_at=now, version="0.1.0")
        session.add(row)
    row.last_heartbeat_at = now
    if active_task_id:
        task = session.get(CollectionTask, active_task_id)
        if task and task.status == "running" and task.lease_owner == worker_id:
            task.heartbeat_at = now
            task.lease_until = now + timedelta(seconds=lease_seconds)
    session.commit()


def update_phase(
    session: Session,
    task_id: str,
    phase: str,
    message: str,
    *,
    attempt: int | None = None,
    lease_owner: str | None = None,
    progress_percent: int | None = None,
) -> None:
    task = session.get(CollectionTask, task_id)
    if not task or task.status != "running":
        return
    if attempt is not None and task.attempt != attempt:
        return
    if lease_owner is not None and task.lease_owner != lease_owner:
        return
    now = utc_now()
    if (attempt is not None or lease_owner is not None) and (task.lease_until is None or task.lease_until <= now):
        return
    task.phase = phase
    task.message = message
    task.heartbeat_at = now
    if progress_percent is not None:
        task.progress_kind = "stages"
        task.progress_percent = max(task.progress_percent or 0, progress_percent)
        task.progress_updated_at = now
    session.commit()
