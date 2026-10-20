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
