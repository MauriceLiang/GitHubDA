from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from backend.app.core.clock import utc_now
from backend.app.core.config import get_settings
from backend.app.persistence.db import SessionLocal, begin_immediate
from backend.app.persistence.models import CollectionTask, DatasetRepository
from backend.app.services.repositories import LIBRARY_ID, RESEARCH_ID, latest_snapshot, make_task


def enqueue_due_refreshes() -> int:
    session = SessionLocal()
    added = 0
    try:
        begin_immediate(session)
        memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id.in_([LIBRARY_ID, RESEARCH_ID]))).all()
        now = utc_now()
        for member in memberships:
            snapshot = latest_snapshot(session, member.repository_id)
            if snapshot and now - snapshot.collected_at < timedelta(hours=get_settings().base_refresh_hours):
                continue
            existing_active = session.scalar(
                select(CollectionTask.task_id).where(CollectionTask.repository_id == member.repository_id, CollectionTask.status.in_(["queued", "running"])).limit(1)
            )
            if existing_active is None:
                make_task(session, member.repository_id, "basic")
                added += 1
        session.commit()
        return added
    finally:
        session.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(enqueue_due_refreshes, "cron", hour=3, minute=0, id="daily-basic-refresh", max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
