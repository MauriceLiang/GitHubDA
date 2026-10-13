from typing import Any, Literal

from backend.app.schemas.common import DTO


class TaskResponse(DTO):
    task_id: str
    repository_id: int
    type: str
    depth: Literal["basic", "deep"]
    status: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
    phase: Literal["collecting", "cleaning", "analyzing", "persisting"] | None
    progress_percent: float | None
    message: str | None
    attempt: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: dict[str, Any] | None


class TaskListResponse(DTO):
    items: list[TaskResponse]


class RetryResponse(DTO):
    task_id: str
    retry_of: str
    status: Literal["queued"]


class TaskListFilter(DTO):
    status: str | None = None
    repository_id: int | None = None
