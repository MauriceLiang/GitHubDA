from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.persistence.models import CollectionTask


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
        if task.attempt >= MAX_ATTEMPTS:
            task.status = "failed"
            task.finished_at = now
            task.phase = None
            task.error_code = "WORKER_LEASE_EXPIRED"
            task.error_message = "Worker 租约过期且已达到最大尝试次数"
            task.message = task.error_message
        else:
            task.status = "queued"
            task.phase = None
            task.message = "Worker 重启后重新排队"
        task.lease_owner = None
        task.lease_until = None

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

    task = session.scalar(select(CollectionTask).where(CollectionTask.status == "queued").order_by(CollectionTask.created_at).limit(1))
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


def update_phase(session: Session, task_id: str, phase: str, message: str) -> None:
    task = session.get(CollectionTask, task_id)
    if not task or task.status != "running":
        return
    task.phase = phase
    task.message = message
    task.heartbeat_at = utc_now()
    session.commit()
