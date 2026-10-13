from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.clock import utc_now
from backend.app.persistence.db import Base


class Repository(Base):
    __tablename__ = "repositories"

    repository_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    html_url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100), index=True)
    topics_json: Mapped[str | None] = mapped_column(Text)
    license_spdx: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    pushed_at: Mapped[object | None] = mapped_column(DateTime)
    github_updated_at: Mapped[object | None] = mapped_column(DateTime)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size_kb: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_seen_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)

    memberships: Mapped[list["DatasetRepository"]] = relationship(back_populates="repository")


class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    rules_version: Mapped[str | None] = mapped_column(String(100))
    frozen_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_metadata_json: Mapped[str | None] = mapped_column(Text)
    memberships: Mapped[list["DatasetRepository"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class DatasetRepository(Base):
    __tablename__ = "dataset_repositories"
    __table_args__ = (UniqueConstraint("dataset_id", "repository_id", name="uq_dataset_repository"),)

    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id", ondelete="CASCADE"), primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.repository_id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    selection_tier: Mapped[str | None] = mapped_column(String(100))
    inclusion_reason: Mapped[str | None] = mapped_column(Text)
    exclusion_status: Mapped[str | None] = mapped_column(String(100))
    selection_source: Mapped[str | None] = mapped_column(String(200))
    repository: Mapped[Repository] = relationship(back_populates="memberships")
    dataset: Mapped[Dataset] = relationship(back_populates="memberships")


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"
    __table_args__ = (Index("ix_snapshot_repo_collected", "repository_id", "collected_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.repository_id", ondelete="CASCADE"), index=True)
    collected_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    stars: Mapped[int | None] = mapped_column(Integer)
    forks: Mapped[int | None] = mapped_column(Integer)
    open_issues_and_pr_count: Mapped[int | None] = mapped_column(Integer)
    pushed_at: Mapped[object | None] = mapped_column(DateTime)
    github_updated_at: Mapped[object | None] = mapped_column(DateTime)
    response_etag: Mapped[str | None] = mapped_column(String(500))
    source_http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    source_archive_path: Mapped[str | None] = mapped_column(Text)
    valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CollectionTask(Base):
    __tablename__ = "collection_tasks"
    __table_args__ = (
        Index("ix_task_status_created", "status", "created_at"),
        Index("ix_task_repo_status", "repository_id", "status"),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.repository_id"), index=True)
    type: Mapped[str] = mapped_column(String(50), default="collect_repository", nullable=False)
    depth: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    phase: Mapped[str | None] = mapped_column(String(20))
    progress_percent: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_of: Mapped[str | None] = mapped_column(ForeignKey("collection_tasks.task_id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[object | None] = mapped_column(DateTime)


class ActivityWindow(Base):
    __tablename__ = "repository_activity_windows"
    __table_args__ = (UniqueConstraint("repository_id", "depth", "window_start", "window_end", "collected_at", name="uq_activity_window"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.repository_id", ondelete="CASCADE"), index=True)
    depth: Mapped[str] = mapped_column(String(10), nullable=False)
    window_start: Mapped[object] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[object] = mapped_column(DateTime, nullable=False)
    commits_count: Mapped[int | None] = mapped_column(Integer)
    issues_opened_count: Mapped[int | None] = mapped_column(Integer)
    issues_closed_count: Mapped[int | None] = mapped_column(Integer)
    pulls_opened_count: Mapped[int | None] = mapped_column(Integer)
    pulls_merged_count: Mapped[int | None] = mapped_column(Integer)
    releases_count: Mapped[int | None] = mapped_column(Integer)
    coverage: Mapped[str] = mapped_column(String(20), nullable=False)
    collected_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_archive_path: Mapped[str | None] = mapped_column(Text)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (Index("ix_analysis_repo_kind_collected", "repository_id", "analysis_kind", "source_collected_at"),)

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.repository_id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.dataset_id", ondelete="CASCADE"), index=True)
    analysis_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_version: Mapped[str] = mapped_column(String(50), nullable=False)
    window_start: Mapped[object | None] = mapped_column(DateTime)
    window_end: Mapped[object | None] = mapped_column(DateTime)
    source_collected_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    calculated_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    coverage: Mapped[str] = mapped_column(String(20), nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    valid_sample_size: Mapped[int | None] = mapped_column(Integer)


class CollectionLog(Base):
    __tablename__ = "collection_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    repository_id: Mapped[int | None] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_endpoint: Mapped[str | None] = mapped_column(String(500))
    http_status: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    message_redacted: Mapped[str | None] = mapped_column(Text)


class WorkerStatus(Base):
    __tablename__ = "worker_status"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_heartbeat_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    version: Mapped[str | None] = mapped_column(String(50))


class SamplingRun(Base):
    __tablename__ = "sampling_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id"), nullable=False)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    query_json: Mapped[str] = mapped_column(Text, nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejection_counts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    candidate_decisions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    started_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[object | None] = mapped_column(DateTime)


class RequestIdempotency(Base):
    __tablename__ = "request_idempotency"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, default=utc_now, nullable=False)
    expires_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
