from typing import Any, Literal

from pydantic import Field

from backend.app.schemas.common import DTO


class TaskModuleProgressResponse(DTO):
    name: Literal["profile", "commits", "issues", "pulls", "releases"]
    status: Literal["pending", "running", "complete", "partial", "failed", "skipped"]
    coverage: Literal["complete", "partial", "not_collected", "unknown"]
    pages_fetched: int = Field(default=0, ge=0)
    page_cap: int | None = Field(default=None, ge=1)
    observed_items: int = Field(default=0, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    error_code: str | None = None


class TaskResponse(DTO):
    task_id: str
    repository_id: int
    type: str
    depth: Literal["basic", "deep"]
    status: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
    phase: Literal["collecting", "cleaning", "analyzing", "persisting"] | None
    progress_percent: float | None = Field(ge=0, le=100)
    message: str | None
    attempt: int = Field(ge=0)
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: dict[str, Any] | None
    progress_kind: Literal["stages", "unknown"] = "unknown"
    progress_updated_at: str | None = None
    current_module: Literal["profile", "commits", "issues", "pulls", "releases"] | None = None
    modules: list[TaskModuleProgressResponse] = Field(default_factory=list)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    eta_seconds: float | None = Field(default=None, ge=0)


class TaskListResponse(DTO):
    items: list[TaskResponse]


class RetryResponse(DTO):
    task_id: str
    retry_of: str
    status: Literal["queued"]


class TaskListFilter(DTO):
    status: str | None = None
    repository_id: int | None = None
