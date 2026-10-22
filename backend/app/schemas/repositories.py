from typing import Any, Literal

from pydantic import Field, field_validator

from backend.app.schemas.common import DTO, SourceMetadata


class RepositoryPreview(DTO):
    repository_id: int
    full_name: str
    html_url: str
    description: str | None
    language: str | None
    stars: int | None
    forks: int | None
    archived: bool
    is_fork: bool
    already_in_library: bool
    github_updated_at: str | None


class RepositorySummary(DTO):
    repository_id: int
    full_name: str
    description: str | None
    language: str | None
    stars: int | None
    forks: int | None
    created_at: str | None
    pushed_at: str | None
    archived: bool
    analysis_status: str
    data_status: str
    last_successful_collection_at: str | None
    latest_task_id: str | None
    datasets: list[str]


class RepositoryDetail(DTO):
    repository: RepositorySummary
    html_url: str
    topics: list[str]
    license_spdx: str | None
    size_kb: int | None
    open_issues_and_pr_count: int | None
    source_metadata: SourceMetadata | None


class ResolveRequest(DTO):
    input: str = Field(min_length=1, max_length=500)


class AddRepositoryRequest(DTO):
    full_name: str = Field(min_length=3, max_length=200)
    auto_analyze: bool = True
    depth: Literal["basic", "deep"] = "basic"


class AddRepositoryResponse(DTO):
    repository_id: int
    membership_created: bool
    analysis_status: str
    task_id: str | None


class RefreshRequest(DTO):
    depth: Literal["basic", "deep"] = "basic"
    force: bool = False


class RefreshResponse(DTO):
    task_id: str
    reused: bool
    status: Literal["queued", "running", "succeeded", "partial"]


class AnalysisResponse(DTO):
    repository_id: int
    depth: Literal["basic", "deep"]
    analysis_status: str
    metrics: dict[str, Any] | None
    modules: dict[str, Any]
    source_metadata: SourceMetadata | None
    limitations: list[str]


class SeriesPoint(DTO):
    date: str
    value: int


class SeriesResponse(DTO):
    repository_id: int
    metric: Literal["stars", "forks"]
    points: list[SeriesPoint]
    observed_days: int
    note: str


class ComparisonRequest(DTO):
    repository_ids: list[int] = Field(min_length=2, max_length=5)
    depth: Literal["basic", "deep"] = "basic"

    @field_validator("repository_ids")
    @classmethod
    def validate_distinct_ids(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("repository_ids must be unique")
        return values


class InsightsComparisonRequest(ComparisonRequest):
    mode: Literal["same_period", "individual_periods"] = "same_period"
