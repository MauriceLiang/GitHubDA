from collections.abc import Callable
from datetime import datetime
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.services.application_settings import get_github_max_pages
from backend.app.persistence.models import CollectionTask, TaskModuleProgress


MODULE_ORDER = ("profile", "commits", "issues", "pulls", "releases")
MODULE_LABELS = {
    "profile": "仓库资料",
    "commits": "Commits",
    "issues": "Issues",
    "pulls": "Pull Requests",
    "releases": "Releases",
}
MODULE_PROGRESS = {"profile": 12, "commits": 28, "issues": 48, "pulls": 68, "releases": 88}
TERMINAL_MODULE_STATUSES = {"complete", "partial", "failed", "skipped"}


class StaleTaskAttempt(RuntimeError):
    """Raised when a worker no longer owns the task attempt it is reporting."""


class TaskProgressReporter:
    def __init__(self, session_factory: Callable[[], Session], task_id: str, attempt: int, lease_owner: str):
        self.session_factory = session_factory
        self.task_id = task_id
        self.attempt = attempt
        self.lease_owner = lease_owner

    def begin_module(self, module: str, page_cap: int | None) -> None:
        _validate_module(module)

        def update(session: Session, task: CollectionTask, now: datetime) -> None:
            progress = session.get(TaskModuleProgress, (self.task_id, module))
            if progress is None:
                progress = TaskModuleProgress(
                    task_id=self.task_id,
                    module=module,
                    status="pending",
                    coverage="not_collected",
                    pages_fetched=0,
                    page_cap=page_cap,
                    observed_items=0,
                    attempt=self.attempt,
                    last_updated_at=now,
                )
                session.add(progress)
            elif progress.attempt != self.attempt:
                raise StaleTaskAttempt("Task module progress belongs to a different attempt")

            if progress.status == "pending":
                progress.status = "running"
                progress.coverage = "unknown"
                progress.started_at = now
                progress.page_cap = page_cap
            elif progress.status != "running":
                raise ValueError(f"Cannot restart terminal task module {module}")
            progress.last_updated_at = now
            task.phase = "collecting"
            task.current_module = module
            task.message = f"正在采集{MODULE_LABELS[module]}"
            _touch_task(task, now)

        self._write(update)

    def page_fetched(self, module: str, pages_fetched: int, observed_items: int) -> None:
        _validate_module(module)
        if pages_fetched < 0 or observed_items < 0:
            raise ValueError("Page and item counts must be non-negative")

        def update(session: Session, task: CollectionTask, now: datetime) -> None:
            progress = _running_module(session, self.task_id, module, self.attempt)
            if pages_fetched < progress.pages_fetched or observed_items < progress.observed_items:
                raise ValueError("Task module counters cannot move backwards")
            progress.pages_fetched = pages_fetched
            progress.observed_items = observed_items
            progress.last_updated_at = now
            task.current_module = module
            task.message = f"正在采集{MODULE_LABELS[module]}：已获取 {pages_fetched} 页"
            _touch_task(task, now)

        self._write(update)

    def finish_module(
        self,
        module: str,
        *,
        status: str,
        coverage: str,
        elapsed_seconds: float,
        error_code: str | None = None,
    ) -> None:
        _validate_module(module)
        if status not in TERMINAL_MODULE_STATUSES:
            raise ValueError(f"Invalid terminal module status: {status}")
        if coverage not in {"complete", "partial", "not_collected", "unknown"}:
            raise ValueError(f"Invalid module coverage: {coverage}")

        def update(session: Session, task: CollectionTask, now: datetime) -> None:
            progress = session.get(TaskModuleProgress, (self.task_id, module))
            if progress is None or progress.attempt != self.attempt:
                raise StaleTaskAttempt("Task module progress is missing or belongs to a different attempt")
            if progress.status in TERMINAL_MODULE_STATUSES:
                if progress.status == status and progress.coverage == coverage:
                    return
                raise ValueError(f"Task module {module} is already terminal")
            if progress.status != "running":
                raise ValueError(f"Task module {module} must be running before it can finish")
            progress.status = status
            progress.coverage = coverage
            progress.finished_at = now
            progress.elapsed_seconds = max(0.0, elapsed_seconds)
            progress.error_code = error_code
            progress.last_updated_at = now
            task.current_module = None
            if status == "complete":
                task.progress_percent = max(task.progress_percent or 0, MODULE_PROGRESS[module])
            task.message = _module_result_message(module, status)
            _touch_task(task, now)

        self._write(update)

    def set_phase(self, phase: str, message: str, progress_percent: int | None = None) -> None:
        if progress_percent is not None and not 0 <= progress_percent <= 100:
            raise ValueError("Progress percent must be between 0 and 100")

        def update(_session: Session, task: CollectionTask, now: datetime) -> None:
            task.phase = phase
            task.message = message
            if progress_percent is not None:
                task.progress_percent = max(task.progress_percent or 0, progress_percent)
            _touch_task(task, now)

        self._write(update)

    def _write(self, update: Callable[[Session, CollectionTask, datetime], None]) -> None:
        for retry in range(2):
            try:
                with self.session_factory() as session:
                    now = utc_now()
                    task = session.get(CollectionTask, self.task_id)
                    if (
                        task is None
                        or task.status != "running"
                        or task.attempt != self.attempt
                        or task.lease_owner != self.lease_owner
                        or task.lease_until is None
                        or task.lease_until <= now
                    ):
                        raise StaleTaskAttempt("Task lease or attempt changed before progress could be saved")
                    update(session, task, now)
                    session.commit()
                return
            except OperationalError as exc:
                if retry == 0 and "locked" in str(exc).lower():
                    time.sleep(0.05)
                    continue
                raise


def initialize_attempt_progress(session: Session, task: CollectionTask, now: datetime) -> None:
    github_max_pages = get_github_max_pages(session)
    for module in MODULE_ORDER:
        session.add(TaskModuleProgress(
            task_id=task.task_id,
            module=module,
            status="pending",
            coverage="not_collected",
            pages_fetched=0,
            page_cap=1 if module == "profile" else github_max_pages,
            observed_items=0,
            last_updated_at=now,
            attempt=task.attempt,
        ))


def _running_module(session: Session, task_id: str, module: str, attempt: int) -> TaskModuleProgress:
    progress = session.get(TaskModuleProgress, (task_id, module))
    if progress is None or progress.attempt != attempt:
        raise StaleTaskAttempt("Task module progress is missing or belongs to a different attempt")
    if progress.status != "running":
        raise ValueError(f"Task module {module} is not running")
    return progress


def _validate_module(module: str) -> None:
    if module not in MODULE_ORDER:
        raise ValueError(f"Unknown task module: {module}")


def _touch_task(task: CollectionTask, now: datetime) -> None:
    task.progress_kind = "stages"
    task.progress_updated_at = now


def _module_result_message(module: str, status: str) -> str:
    if status == "complete":
        return f"{MODULE_LABELS[module]}采集完成"
    if status == "skipped":
        return f"{MODULE_LABELS[module]}未采集"
    if status == "failed":
        return f"{MODULE_LABELS[module]}采集失败"
    return f"{MODULE_LABELS[module]}采集不完整"
