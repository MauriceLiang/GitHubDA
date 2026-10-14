"""Pydantic DTOs matching the v1 API contract."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Ignore additive API fields while validating fields the UI consumes."""

    model_config = ConfigDict(extra="ignore")


T = TypeVar("T")


class Pagination(ContractModel):
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total: int | None = Field(default=None, ge=0)
    has_next: bool


class SearchMetadata(ContractModel):
    total_count: int = Field(ge=0)
    incomplete_results: bool
    result_window_limit: int = Field(ge=1)


class ResponseMeta(ContractModel):
    request_id: str
    generated_at: datetime
    pagination: Pagination | None = None
    search: SearchMetadata | None = None


class APIEnvelope(ContractModel, Generic[T]):
    data: T
    meta: ResponseMeta


class HealthResponse(ContractModel):
    status: Literal["ok"]


class RepositoryPreview(ContractModel):
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
    github_updated_at: datetime | None


AnalysisStatus = Literal["not_started", "queued", "processing", "completed", "partial", "failed"]
DataStatus = Literal["missing", "fresh", "stale"]
Coverage = Literal["complete", "partial", "not_collected"]
TaskStatus = Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
TaskPhase = Literal["collecting", "cleaning", "analyzing", "persisting"]


class RepositorySummary(ContractModel):
    repository_id: int
    full_name: str
    description: str | None
    language: str | None
    stars: int | None
    forks: int | None
    created_at: datetime | None
    pushed_at: datetime | None
    archived: bool
    analysis_status: AnalysisStatus
    data_status: DataStatus
    last_successful_collection_at: datetime | None
    latest_task_id: str | None
    datasets: list[str]


class SourceMetadata(ContractModel):
    source: str
    collected_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    sample_size: int | None = Field(ge=0)
    dataset_id: str | None
    coverage: Coverage
    notes: list[str]


class RepositorySearchData(ContractModel):
    items: list[RepositoryPreview]


class AddRepositoryData(ContractModel):
    repository_id: int
    membership_created: bool
    analysis_status: AnalysisStatus
    task_id: str | None


class RepositoryListData(ContractModel):
    items: list[RepositorySummary]


class RepositoryDetailData(ContractModel):
    repository: RepositorySummary
    html_url: str
    topics: list[str]
    license_spdx: str | None
    size_kb: int | None
    open_issues_and_pr_count: int | None
    source_metadata: SourceMetadata | None


class RefreshTaskData(ContractModel):
    task_id: str
    reused: bool
    status: Literal["queued", "running", "succeeded", "partial"]


class AnalysisMetrics(ContractModel):
    stars: int | None
    forks: int | None
    age_days: float | None
    days_since_push: float | None
    release_count_365d: int | None
    commits_90d: int | None
    issues_closed_90d: int | None
    pr_merged_90d: int | None


class ModuleCoverage(ContractModel):
    coverage: Coverage


class RepositoryAnalysisData(ContractModel):
    repository_id: int
    depth: Literal["basic", "deep"]
    analysis_status: AnalysisStatus
    metrics: AnalysisMetrics | None
    modules: dict[str, ModuleCoverage] = Field(default_factory=dict)
    source_metadata: SourceMetadata | None = None
    limitations: list[str] = Field(default_factory=list)


class SeriesPoint(ContractModel):
    date: date
    value: int


class RepositorySeriesData(ContractModel):
    repository_id: int
    metric: Literal["stars", "forks"]
    points: list[SeriesPoint]
    observed_days: int = Field(ge=0)
    note: str | None = None


class Task(ContractModel):
    task_id: str
    repository_id: int
    type: str
    depth: Literal["basic", "deep"]
    status: TaskStatus
    phase: TaskPhase | None
    progress_percent: float | None = Field(ge=0, le=100)
    message: str | None
    attempt: int = Field(ge=0)
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: dict[str, Any] | None


class TaskListData(ContractModel):
    items: list[Task]


class RetryTaskData(ContractModel):
    task_id: str
    retry_of: str
    status: Literal["queued"]


class GitHubQuota(ContractModel):
    rate_limit_remaining: int | None = Field(ge=0)
    rate_limit_reset_at: datetime | None
    checked_at: datetime | None


class QueueSnapshot(ContractModel):
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    failed: int = Field(ge=0)


class SystemStatusData(ContractModel):
    api: str
    database: str
    worker: Literal["ok", "stale", "unknown"]
    worker_last_heartbeat_at: datetime | None
    github: GitHubQuota
    queue: QueueSnapshot


class Dataset(ContractModel):
    dataset_id: str
    name: str
    type: Literal["research", "library", "featured"]
    sample_size: int = Field(ge=0)
    frozen_at: datetime | None
    rules_version: str | None


class DatasetListData(ContractModel):
    items: list[Dataset]


class OverviewKpis(ContractModel):
    repositories_total: int = Field(ge=0)
    repositories_analyzed: int = Field(ge=0)
    stars_median: float | None
    recently_pushed_90d_count: int | None = Field(default=None, ge=0)


class DistributionCount(ContractModel):
    language: str
    count: int = Field(ge=0)


class StarDistributionBucket(ContractModel):
    bucket: str
    count: int = Field(ge=0)


class OverviewData(ContractModel):
    scope: Literal["research", "library"]
    dataset_id: str | None
    kpis: OverviewKpis
    language_distribution: list[DistributionCount]
    stars_distribution: list[StarDistributionBucket]
    source_metadata: SourceMetadata


class NumericSummary(ContractModel):
    count: int = Field(ge=0)
    mean: float | None
    median: float | None
    std: float | None


class ResearchGroup(ContractModel):
    group: str
    n: int = Field(ge=0)
    stars_median: float | None
    forks_median: float | None
    recently_pushed_90d_pct: float | None


class Correlation(ContractModel):
    x: str
    y: str
    method: str
    n: int = Field(ge=0)
    coefficient: float | None
    p_value: float | None
    note: str | None = None


class ResearchStatisticsData(ContractModel):
    dataset_id: str
    group_by: Literal["language", "star_tier", "age_tier"]
    valid_sample_size: int = Field(ge=0)
    summary: dict[str, NumericSummary]
    groups: list[ResearchGroup]
    correlations: list[Correlation]
    source_metadata: SourceMetadata


class MissingField(ContractModel):
    field: str
    count: int = Field(ge=0)
    rate: float | None = Field(ge=0, le=1)


class ExcludedByReason(ContractModel):
    reason: str
    count: int = Field(ge=0)


class DataQualityData(ContractModel):
    dataset_id: str
    records_total: int = Field(ge=0)
    records_analyzable: int = Field(ge=0)
    missing_fields: list[MissingField]
    excluded_by_reason: list[ExcludedByReason]
    stale_count: int = Field(ge=0)
    sampling_rules_version: str | None
    coverage_notes: list[str]


class ComparisonMetrics(ContractModel):
    stars: int | None = None
    forks: int | None = None
    age_days: float | None = None
    days_since_push: float | None = None
    commits_90d: int | None = None
    release_count_365d: int | None = None
    issues_closed_90d: int | None = None
    pr_merged_90d: int | None = None


class ComparisonRepository(ContractModel):
    repository_id: int
    full_name: str
    metrics: ComparisonMetrics
    coverage: Coverage


class ComparisonBasis(ContractModel):
    depth: Literal["basic", "deep"]
    metric_window: str
    same_project_type: bool
    warnings: list[str]


class ComparisonData(ContractModel):
    repositories: list[ComparisonRepository]
    comparison_basis: ComparisonBasis


class ErrorInfo(ContractModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(ContractModel):
    error: ErrorInfo
    request_id: str | None = None
