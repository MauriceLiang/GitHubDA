import json
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import desc, select

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.config import get_settings
from backend.app.persistence.db import SessionLocal, begin_immediate
from backend.app.persistence.models import CollectionTask, DatasetRepository, RepositoryInsightRun
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, RESEARCH_ID, latest_snapshot, make_task


INCREMENTAL_OVERLAP_DAYS = 7
INCREMENTAL_ANALYSIS_DAYS = 90


def enqueue_due_refreshes() -> int:
    session = SessionLocal()
    added = 0
    try:
        begin_immediate(session)
        memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id.in_([LIBRARY_ID, RESEARCH_ID, FEATURED_ID]))).all()
        now = utc_now()
        for repository_id in sorted({member.repository_id for member in memberships}):
            snapshot = latest_snapshot(session, repository_id)
            if snapshot and now - snapshot.collected_at < timedelta(hours=get_settings().base_refresh_hours):
                continue
            existing_active = session.scalar(
                select(CollectionTask.task_id).where(CollectionTask.repository_id == repository_id, CollectionTask.status.in_(["queued", "running"])).limit(1)
            )
            if existing_active is None:
                make_task(session, repository_id, "basic")
                added += 1
        session.commit()
        return added
    finally:
        session.close()


def enqueue_due_incremental_syncs() -> int:
    """Queue rolling-window syncs only where a complete baseline already exists."""
    session = SessionLocal()
    added = 0
    try:
        begin_immediate(session)
        memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id.in_([LIBRARY_ID, RESEARCH_ID, FEATURED_ID]))).all()
        now = utc_now()
        for repository_id in sorted({member.repository_id for member in memberships}):
            active = session.scalar(select(CollectionTask.task_id).where(
                CollectionTask.repository_id == repository_id,
                CollectionTask.status.in_(["queued", "running"]),
            ).limit(1))
            if active is not None:
                continue
            recently_scheduled = session.scalar(select(CollectionTask.task_id).where(
                CollectionTask.repository_id == repository_id,
                CollectionTask.scope_kind == "incremental",
                CollectionTask.created_at >= now - timedelta(hours=20),
            ).limit(1))
            if recently_scheduled is not None:
                continue
            baseline = session.scalar(select(RepositoryInsightRun).where(
                RepositoryInsightRun.repository_id == repository_id,
                RepositoryInsightRun.metric_version == "insights-v1",
            ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
            if baseline is None or baseline.status != "ready":
                continue
            try:
                module_coverage = json.loads(baseline.module_coverage_json)
            except (TypeError, ValueError):
                continue
            if not isinstance(module_coverage, dict) or any(
                not isinstance(module_coverage.get(module), dict)
                or module_coverage[module].get("coverage") != "complete"
                for module in ("commits", "issues", "pulls", "releases")
            ):
                continue
            query_start = baseline.window_end - timedelta(days=INCREMENTAL_OVERLAP_DAYS)
            analysis_start = now - timedelta(days=INCREMENTAL_ANALYSIS_DAYS)
            scope = {
                "window_start": iso_z(query_start),
                "window_end": iso_z(now),
                "analysis_window_start": iso_z(analysis_start),
                "analysis_window_end": iso_z(now),
                "overlap_days": INCREMENTAL_OVERLAP_DAYS,
            }
            make_task(session, repository_id, "deep", scope_kind="incremental", scope_json=json.dumps(scope))
            added += 1
        session.commit()
        return added
    finally:
        session.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(enqueue_due_refreshes, "cron", hour=3, minute=0, id="daily-basic-refresh", max_instances=1, coalesce=True)
    scheduler.add_job(enqueue_due_incremental_syncs, "cron", hour=4, minute=0, id="daily-incremental-sync", max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
