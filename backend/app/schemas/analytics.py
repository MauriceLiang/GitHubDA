from typing import Any, Literal

from pydantic import Field

from backend.app.schemas.common import DTO, SourceMetadata


class ItemListResponse(DTO):
    items: list[dict[str, Any]]


class RepositoryListResponse(DTO):
    items: list[Any]


class SearchResponse(DTO):
    items: list[Any]


class DatasetItem(DTO):
    dataset_id: str
    name: str
    type: Literal["research", "library", "featured"]
    sample_size: int
    frozen_at: str | None
    rules_version: str | None


class DatasetListResponse(DTO):
    items: list[DatasetItem]


class SystemStatusResponse(DTO):
    api: Literal["ok"]
    database: Literal["ok", "stale", "unknown"]
    worker: Literal["ok", "stale", "unknown"]
    worker_last_heartbeat_at: str | None
    github: dict[str, Any]
    queue: dict[str, int]


class OverviewResponse(DTO):
    scope: Literal["research", "library"]
    dataset_id: str | None
    kpis: dict[str, Any]
    language_distribution: list[dict[str, Any]]
    stars_distribution: list[dict[str, Any]]
    source_metadata: SourceMetadata


class StatisticsResponse(DTO):
    dataset_id: str
    group_by: Literal["language", "star_tier", "age_tier"]
    valid_sample_size: int
    summary: dict[str, Any]
    groups: list[dict[str, Any]]
    correlations: list[dict[str, Any]]
    source_metadata: SourceMetadata


class MissingFieldResponse(DTO):
    field: str
    count: int = Field(ge=0)
    rate: float | None = Field(ge=0, le=1)


class ExcludedByReasonResponse(DTO):
    reason: str
    count: int = Field(ge=0)


class DataQualityResponse(DTO):
    dataset_id: str
    records_total: int
    records_analyzable: int
    missing_fields: list[MissingFieldResponse]
    excluded_by_reason: list[ExcludedByReasonResponse]
    stale_count: int
    sampling_rules_version: str | None
    coverage_notes: list[str]


class ComparisonResponse(DTO):
    repositories: list[dict[str, Any]]
    comparison_basis: dict[str, Any]
