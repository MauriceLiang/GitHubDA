from typing import Any, Literal
from pydantic import BaseModel, Field

InsightStatus = Literal["ready", "partial", "missing", "insufficient_samples", "failed"]


class MetricQuality(BaseModel):
    status: InsightStatus
    coverage: Literal["complete", "partial", "not_collected"]
    valid_samples: int = Field(ge=0)
    reason: str | None
    limit_reached: bool = False
    rejected_records: int = 0
    invalid_event_times: int = 0


class InsightPoint(BaseModel):
    start: str
    end: str
    value: int | None
    observed_events: int
    quality: InsightStatus
    complete_week: bool


class InsightMetric(BaseModel):
    # Business-specific values accompany the common, documented contract.
    model_config = {"extra": "allow"}
    metric_key: str
    unit: str
    window_start: str
    window_end: str
    quality: MetricQuality


class CommitActivity(InsightMetric):
    metric_key: Literal["commits_weekly"]
    weekly: list[InsightPoint]
    recent_4w: int | None
    previous_4w: int | None
    delta: int | None
    change_rate_pct: float | None
    comparison_reason: str | None


class HistogramBucket(BaseModel):
    label: str
    count: int


class DurationMetric(InsightMetric):
    metric_key: Literal["issue_closed_duration_hours", "pr_merge_duration_hours"]
    observed_terminal_count: int
    observed_without_terminal: int
    excluded_invalid_duration: int
    missing_duration_rate: float | None
    median_hours: float | None
    p75_hours: float | None
    p90_hours: float | None
    histogram: list[HistogramBucket]
    weekly: list[InsightPoint]


class ReleasePoint(BaseModel):
    id: str
    published_at: str


class ReleaseDetail(BaseModel):
    id: str
    name: str | None
    body: str | None


class DetailCoverage(BaseModel):
    state: Literal["complete", "partial", "missing"]
    label: str
    detail: str | None


class IssueCoverage(DetailCoverage):
    pass


class ClosedIssueRecord(BaseModel):
    number: int
    title: str
    created_at: str | None
    closed_at: str
    duration_days: float | None
    state: Literal["closed"]
    url: str


class ClosedIssueDetail(ClosedIssueRecord):
    body: str | None
    comments_count: int = Field(ge=0)


class IssueComment(BaseModel):
    author: str
    body: str
    created_at: str | None


class OnlineIssueDetail(BaseModel):
    number: int
    title: str
    body: str | None
    state: Literal["open", "closed"]
    author: str | None
    labels: list[str]
    created_at: str | None
    closed_at: str | None
    updated_at: str | None
    url: str
    comments_count: int = Field(ge=0)
    comments: list[IssueComment]
    comments_complete: bool
    comments_error: str | None


class PullRequestRecord(BaseModel):
    number: int
    title: str
    created_at: str | None
    closed_at: str | None
    merged_at: str | None
    duration_days: float | None
    state: Literal["closed", "merged"]
    draft: bool
    comments_count: int = Field(ge=0)
    url: str


class PullRequestDetail(PullRequestRecord):
    body: str | None


class PullRequestComment(BaseModel):
    author: str
    body: str
    created_at: str | None


class OnlinePullRequestDetail(BaseModel):
    number: int
    title: str
    body: str | None
    state: Literal["open", "closed", "merged"]
    author: str | None
    labels: list[str]
    created_at: str | None
    closed_at: str | None
    merged_at: str | None
    updated_at: str | None
    url: str
    comments_count: int = Field(ge=0)
    comments: list[PullRequestComment]
    comments_complete: bool
    comments_error: str | None


class PullRequestPage(BaseModel):
    available: bool
    coverage: DetailCoverage
    note: str
    window_start: str | None
    window_end: str | None
    items: list[PullRequestRecord]
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class ClosedIssuePage(BaseModel):
    available: bool
    coverage: IssueCoverage
    note: str
    window_start: str | None
    window_end: str | None
    items: list[ClosedIssueRecord]
    page: int
    per_page: int
    total: int


class CommitDailyCount(BaseModel):
    date: str
    count: int = Field(ge=0)


class CommitAuthorContribution(BaseModel):
    author: str
    commits: int = Field(ge=0)
    is_bot: bool
    anonymous: bool


class CommitRecord(BaseModel):
    sha: str
    title: str
    author: str
    is_bot: bool
    anonymous: bool
    date: str
    url: str


class CommitActivityPage(BaseModel):
    available: bool
    coverage: DetailCoverage
    note: str
    window_start: str | None
    window_end: str | None
    commit_count: int = Field(ge=0)
    author_count: int = Field(ge=0)
    daily_counts: list[CommitDailyCount]
    authors: list[CommitAuthorContribution]
    items: list[CommitRecord]
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class ReleaseMetric(InsightMetric):
    metric_key: Literal["release_intervals_days"]
    release_count: int
    prerelease_count: int
    timeline: list[ReleasePoint]
    intervals_days: list[float]
    median_interval_days: float | None


class RepositoryInsights(BaseModel):
    repository_id: int
    run_id: str | None
    metric_version: str
    status: InsightStatus
    window_start: str | None
    window_end: str | None
    timezone: Literal["UTC"]
    analyzed_at: str | None
    source_task_ids: list[str]
    source_archive_paths: list[str]
    origin: str | None
    sources: dict[str, dict[str, Any]]
    insights: dict[str, CommitActivity | DurationMetric | ReleaseMetric]
    limitations: list[str]


class InsightSeries(BaseModel):
    metric: str
    window_start: str | None
    window_end: str | None
    timezone: Literal["UTC"]
    unit: str
    points: list[InsightPoint]
    notes: list[str]


class InsightQuality(BaseModel):
    run_id: str | None
    metric_version: str
    analyzed_at: str | None
    sources: dict[str, dict[str, Any]]
    metrics: dict[str, MetricQuality]
    limitations: list[str]
