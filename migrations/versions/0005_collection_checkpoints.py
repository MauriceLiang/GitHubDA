"""Persist collection scope, pagination checkpoints, and GitHub quota state."""
import sqlalchemy as sa
from alembic import op


revision = "0005_collection_checkpoints"
down_revision = "0004_application_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("collection_tasks"):
        columns = {column["name"] for column in inspector.get_columns("collection_tasks")}
        with op.batch_alter_table("collection_tasks") as batch:
            if "scope_kind" not in columns:
                batch.add_column(sa.Column("scope_kind", sa.String(length=20), server_default="quick", nullable=False))
            if "scope_json" not in columns:
                batch.add_column(sa.Column("scope_json", sa.Text(), nullable=True))
            if "resume_after" not in columns:
                batch.add_column(sa.Column("resume_after", sa.DateTime(), nullable=True))
        if "resume_after" not in columns:
            op.create_index("ix_collection_tasks_resume_after", "collection_tasks", ["resume_after"], unique=False)

    if not inspector.has_table("collection_checkpoints"):
        op.create_table(
            "collection_checkpoints",
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("module", sa.String(length=20), primary_key=True, nullable=False),
            sa.Column("scope_fingerprint", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("window_start", sa.DateTime(), nullable=False),
            sa.Column("window_end", sa.DateTime(), nullable=False),
            sa.Column("task_id", sa.String(length=36), sa.ForeignKey("collection_tasks.task_id", ondelete="SET NULL"), nullable=True),
            sa.Column("next_url", sa.Text(), nullable=True),
            sa.Column("last_seen_key", sa.String(length=100), nullable=True),
            sa.Column("pages_fetched", sa.Integer(), server_default="0", nullable=False),
            sa.Column("records_written", sa.Integer(), server_default="0", nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("resume_after", sa.DateTime(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.UniqueConstraint("repository_id", "module", "scope_fingerprint", name="uq_collection_checkpoint_scope"),
        )
        op.create_index("ix_checkpoint_status_resume", "collection_checkpoints", ["status", "resume_after"], unique=False)

    if not inspector.has_table("api_rate_limit_state"):
        op.create_table(
            "api_rate_limit_state",
            sa.Column("resource", sa.String(length=30), primary_key=True, nullable=False),
            sa.Column("limit", sa.Integer(), nullable=True),
            sa.Column("remaining", sa.Integer(), nullable=True),
            sa.Column("reset_at", sa.DateTime(), nullable=True),
            sa.Column("retry_after", sa.DateTime(), nullable=True),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("api_rate_limit_state"):
        op.drop_table("api_rate_limit_state")
    if inspector.has_table("collection_checkpoints"):
        op.drop_table("collection_checkpoints")
    if inspector.has_table("collection_tasks"):
        columns = {column["name"] for column in inspector.get_columns("collection_tasks")}
        if "resume_after" in columns:
            op.drop_index("ix_collection_tasks_resume_after", table_name="collection_tasks")
        with op.batch_alter_table("collection_tasks") as batch:
            if "resume_after" in columns:
                batch.drop_column("resume_after")
            if "scope_json" in columns:
                batch.drop_column("scope_json")
            if "scope_kind" in columns:
                batch.drop_column("scope_kind")
