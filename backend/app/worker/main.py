import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.app.core.config import get_settings
from backend.app.integrations.github.client import GitHubClient, is_rate_limited_response, retry_after_seconds
from backend.app.persistence.db import SessionLocal
from backend.app.persistence.models import ApiRateLimitState, TaskModuleProgress
from backend.app.worker.executor import execute_task
from backend.app.worker.queue import claim_next_task, heartbeat
from backend.app.worker.scheduler import start_scheduler


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("repovantage.worker")


def _persist_rate_limit_state(response) -> None:
    resource = response.headers.get("X-RateLimit-Resource", "core")[:30] or "core"
    limit = _header_int(response.headers.get("X-RateLimit-Limit"))
    remaining = _header_int(response.headers.get("X-RateLimit-Remaining"))
    reset_epoch = _header_int(response.headers.get("X-RateLimit-Reset"))
    reset_at = datetime.fromtimestamp(reset_epoch, UTC).replace(tzinfo=None) if reset_epoch is not None else None
    retry_seconds = retry_after_seconds(response)
    limited = is_rate_limited_response(response)
    if limited:
        delay = retry_seconds if retry_seconds is not None else 60
        retry_after = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=delay)
    else:
        retry_after = None
    with SessionLocal() as session:
        row = session.get(ApiRateLimitState, resource)
        if row is None:
            row = ApiRateLimitState(resource=resource)
            session.add(row)
        row.limit = limit
        row.remaining = remaining
        row.reset_at = reset_at
        row.retry_after = retry_after
        row.observed_at = datetime.now(UTC).replace(tzinfo=None)
        session.commit()


def _header_int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def main() -> None:
    settings = get_settings()
    worker_id = f"worker-{uuid4()}"
    active_task: dict[str, str | None] = {"id": None}
    active_lock = threading.Lock()
    stop = threading.Event()
    scheduler = start_scheduler()
    session = SessionLocal()
    try:
        heartbeat(session, worker_id, None, settings.worker_lease_seconds)
    except Exception:
        session.rollback()
        logger.exception("Initial worker heartbeat failed")
    finally:
        session.close()

    def heartbeat_loop() -> None:
        while not stop.wait(settings.worker_heartbeat_seconds):
            with active_lock:
                task_id = active_task["id"]
            session = SessionLocal()
            try:
                heartbeat(session, worker_id, task_id, settings.worker_lease_seconds)
            except Exception:
                session.rollback()
                logger.exception("Worker heartbeat update failed")
            finally:
                session.close()

    thread = threading.Thread(target=heartbeat_loop, name="worker-heartbeat", daemon=True)
    thread.start()
    logger.info("Worker started")
    try:
        while True:
            session = SessionLocal()
            try:
                task = claim_next_task(session, worker_id, settings.worker_lease_seconds)
            except Exception:
                session.rollback()
                logger.exception("Unable to claim task")
                task = None
            finally:
                session.close()
            if task is None:
                stop.wait(settings.worker_poll_seconds)
                continue
            with active_lock:
                active_task["id"] = task.task_id
            logger.info("Claimed task %s for repository %s", task.task_id, task.repository_id)
            try:
                progress_session = SessionLocal()
                try:
                    module_progress = progress_session.get(TaskModuleProgress, (task.task_id, "commits"))
                    max_pages = module_progress.page_cap if module_progress else None
                finally:
                    progress_session.close()
                with GitHubClient(
                    request_id=task.task_id,
                    max_pages=max_pages,
                    unbounded=(task.scope_kind in {"window", "incremental"}),
                    on_response=_persist_rate_limit_state,
                ) as github:
                    execute_task(SessionLocal, task.task_id, github)
            except Exception:
                logger.exception("Task %s failed outside executor", task.task_id)
            finally:
                with active_lock:
                    active_task["id"] = None
    except KeyboardInterrupt:
        logger.info("Worker stopping")
    finally:
        stop.set()
        scheduler.shutdown(wait=False)
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
