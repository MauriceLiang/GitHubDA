"""Persist task and module progress.

Revision ID: 0002_task_progress
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op


revision = "0002_task_progress"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    task_columns = {column["name"] for column in sa.inspect(bind).get_columns("collection_tasks")}
    if "progress_kind" not in task_columns:
        op.add_column(
            "collection_tasks",
            sa.Column("progress_kind", sa.String(length=20), server_default="unknown", nullable=False),
        )
    if "progress_updated_at" not in task_columns:
        op.add_column("collection_tasks", sa.Column("progress_updated_at", sa.DateTime(), nullable=True))
    if "current_module" not in task_columns:
        op.add_column("collection_tasks", sa.Column("current_module", sa.String(length=20), nullable=True))

    if not sa.inspect(bind).has_table("task_module_progress"):
        op.create_table(
            "task_module_progress",
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("module", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("coverage", sa.String(length=20), nullable=False),
            sa.Column("pages_fetched", sa.Integer(), server_default="0", nullable=False),
            sa.Column("page_cap", sa.Integer(), nullable=True),
            sa.Column("observed_items", sa.Integer(), server_default="0", nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("elapsed_seconds", sa.Float(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("last_updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["collection_tasks.task_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("task_id", "module"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("task_module_progress"):
        op.drop_table("task_module_progress")
    task_columns = {column["name"] for column in sa.inspect(bind).get_columns("collection_tasks")}
    for name in ("current_module", "progress_updated_at", "progress_kind"):
        if name in task_columns:
            op.drop_column("collection_tasks", name)
