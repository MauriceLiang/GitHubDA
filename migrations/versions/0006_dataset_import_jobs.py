"""Persist featured dataset imports and their staged records."""

import sqlalchemy as sa
from alembic import op


revision = "0006_dataset_import_jobs"
down_revision = "0005_collection_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_import_jobs",
        sa.Column("task_id", sa.String(length=36), primary_key=True),
        sa.Column("dataset_id", sa.String(length=100), nullable=False),
        sa.Column("bundle_version", sa.String(length=64), nullable=False),
        sa.Column("bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("progress_kind", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("processed_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=True),
        sa.Column("current_file", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retry_of", sa.String(length=36), sa.ForeignKey("dataset_import_jobs.task_id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True, unique=True),
        sa.Column("staging_state_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(length=100), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_dataset_import_status_created", "dataset_import_jobs", ["status", "created_at"])
    op.create_index("ix_dataset_import_status_lease", "dataset_import_jobs", ["status", "lease_until"])
    op.create_index(
        "uq_dataset_import_active_bundle",
        "dataset_import_jobs",
        ["dataset_id", "bundle_hash"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "dataset_import_staging_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("dataset_import_jobs.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False),
        sa.Column("record_key", sa.String(length=100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("task_id", "record_type", "record_key", name="uq_dataset_import_staging_key"),
    )
    op.create_index("ix_dataset_import_staging_task_ordinal", "dataset_import_staging_records", ["task_id", "record_type", "ordinal"])
    op.create_index(
        "ix_dataset_import_staging_repository",
        "dataset_import_staging_records",
        ["task_id", "record_type", "repository_id", "ordinal"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_import_staging_repository", table_name="dataset_import_staging_records")
    op.drop_index("ix_dataset_import_staging_task_ordinal", table_name="dataset_import_staging_records")
    op.drop_table("dataset_import_staging_records")
    op.drop_index("uq_dataset_import_active_bundle", table_name="dataset_import_jobs")
    op.drop_index("ix_dataset_import_status_lease", table_name="dataset_import_jobs")
    op.drop_index("ix_dataset_import_status_created", table_name="dataset_import_jobs")
    op.drop_table("dataset_import_jobs")
