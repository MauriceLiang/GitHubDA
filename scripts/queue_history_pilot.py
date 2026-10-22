"""Plan or queue resumable full-history pilot collections for five repositories."""
import argparse
import json
from datetime import timedelta

from sqlalchemy import desc, select

from backend.app.core.clock import iso_z, utc_now
from backend.app.persistence.db import SessionLocal, begin_immediate
from backend.app.persistence.models import CollectionTask, Repository
from backend.app.services.repositories import make_task


PILOT_REPOSITORIES = (
    "pallets/flask",
    "vuejs/core",
    "spring-projects/spring-boot",
    "labstack/echo",
    "sharkdp/fd",
)


def queue_history_pilot(session, *, now=None, queue=False):
    now = now or utc_now()
    if queue:
        begin_immediate(session)
    result = []
    for full_name in PILOT_REPOSITORIES:
        repository = session.scalar(select(Repository).where(Repository.full_name == full_name))
        if repository is None:
            result.append({"repository": full_name, "status": "missing_local_repository"})
            continue
        active = session.scalar(select(CollectionTask).where(
            CollectionTask.repository_id == repository.repository_id,
            CollectionTask.status.in_(["queued", "running"]),
        ).order_by(desc(CollectionTask.created_at)).limit(1))
        if active is not None:
            result.append({"repository": full_name, "status": "already_active", "task_id": active.task_id})
            continue
        previous = session.scalar(select(CollectionTask).where(
            CollectionTask.repository_id == repository.repository_id,
            CollectionTask.scope_kind == "backfill",
        ).order_by(desc(CollectionTask.created_at)).limit(1))
        if previous is not None and previous.status == "succeeded":
            result.append({"repository": full_name, "status": "already_completed", "task_id": previous.task_id})
            continue
        if previous is not None and previous.scope_json:
            try:
                scope = json.loads(previous.scope_json)
            except (TypeError, ValueError):
                scope = None
        else:
            scope = None
        if not isinstance(scope, dict) or not isinstance(scope.get("window_start"), str):
            if repository.created_at is None:
                result.append({"repository": full_name, "status": "missing_repository_created_at"})
                continue
            scope = {
                "window_start": iso_z(repository.created_at),
                "window_end": iso_z(now),
                "analysis_window_start": iso_z(now - timedelta(days=90)),
                "analysis_window_end": iso_z(now),
                "start_basis": "github_repository_created_at",
                "pilot": True,
            }
        if queue:
            task = make_task(
                session,
                repository.repository_id,
                "deep",
                scope_kind="backfill",
                scope_json=json.dumps(scope, sort_keys=True),
            )
            result.append({"repository": full_name, "status": "queued", "task_id": task.task_id, "window_start": scope["window_start"], "window_end": scope.get("window_end")})
        else:
            result.append({"repository": full_name, "status": "would_queue", "window_start": scope["window_start"], "window_end": scope.get("window_end")})
    if queue:
        session.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", action="store_true", help="write resumable backfill tasks to the local database; Worker execution remains separate")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = queue_history_pilot(session, queue=args.queue)
    print(json.dumps({"mode": "queued" if args.queue else "dry_run", "items": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
