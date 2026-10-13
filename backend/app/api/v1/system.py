from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.core.clock import iso_z, utc_now
from backend.app.core.config import get_settings
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.models import CollectionTask, WorkerStatus
from backend.app.schemas.analytics import SystemStatusResponse
from backend.app.schemas.common import SuccessEnvelope


router = APIRouter()


@router.get("/system/status", response_model=SuccessEnvelope[SystemStatusResponse])
def system_status(request: Request, session: Session = Depends(get_session)):
    database = "ok"
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        session.rollback()
        database = "unknown"
    worker_status = session.scalar(select(WorkerStatus).order_by(WorkerStatus.last_heartbeat_at.desc()).limit(1))
    last_heartbeat = worker_status.last_heartbeat_at if worker_status else None
    worker = "unknown" if last_heartbeat is None else ("ok" if utc_now() - last_heartbeat <= timedelta(seconds=get_settings().worker_stale_seconds) else "stale")
    counts = {status: int(session.scalar(select(func.count()).select_from(CollectionTask).where(CollectionTask.status == status)) or 0) for status in ("queued", "running", "failed")}
    rate = GitHubClient.rate_limit_snapshot()
    return envelope(request, {
        "api": "ok",
        "database": database,
        "worker": worker,
        "worker_last_heartbeat_at": iso_z(last_heartbeat),
        "github": {"rate_limit_remaining": rate["remaining"], "rate_limit_reset_at": rate["reset_at"], "checked_at": rate["checked_at"]},
        "queue": counts,
    })
