"""Add event facts and immutable insight runs; preserve all existing tables."""
import sqlalchemy as sa
from alembic import op

revision = "0003_activity_insights"
down_revision = "0002_task_progress"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("repository_activity_events"):
        op.create_table("repository_activity_events",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id"), primary_key=False, nullable=False),
            sa.Column("event_type", sa.String(length=20), primary_key=False, nullable=False),
            sa.Column("source_item_id", sa.String(length=64), primary_key=False, nullable=False),
            sa.Column("event_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("created_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("closed_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("merged_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("published_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("updated_at", sa.DateTime(), primary_key=False, nullable=True),
            sa.Column("author_key", sa.String(length=64), primary_key=False, nullable=True),
            sa.Column("is_draft", sa.Boolean(), primary_key=False, nullable=True),
            sa.Column("is_prerelease", sa.Boolean(), primary_key=False, nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), primary_key=False, nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), primary_key=False, nullable=False),
            sa.Column("source_task_id", sa.String(length=100), primary_key=False, nullable=False),
            sa.UniqueConstraint('repository_id', 'event_type', 'source_item_id', name='uq_activity_event'),
        )
        op.create_index('ix_event_repo_created', 'repository_activity_events', ['repository_id', 'created_at'], unique=False)
        op.create_index('ix_event_repo_type_time', 'repository_activity_events', ['repository_id', 'event_type', 'event_at'], unique=False)
    if not sa.inspect(op.get_bind()).has_table("repository_insight_runs"):
        op.create_table("repository_insight_runs",
            sa.Column("run_id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("input_fingerprint", sa.String(length=64), primary_key=False, nullable=False),
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id"), primary_key=False, nullable=False),
            sa.Column("metric_version", sa.String(length=50), primary_key=False, nullable=False),
            sa.Column("window_start", sa.DateTime(), primary_key=False, nullable=False),
            sa.Column("window_end", sa.DateTime(), primary_key=False, nullable=False),
            sa.Column("analyzed_at", sa.DateTime(), primary_key=False, nullable=False),
            sa.Column("source_task_ids_json", sa.Text(), primary_key=False, nullable=False),
            sa.Column("source_archive_paths_json", sa.Text(), primary_key=False, nullable=False),
            sa.Column("module_coverage_json", sa.Text(), primary_key=False, nullable=False),
            sa.Column("status", sa.String(length=20), primary_key=False, nullable=False),
            sa.Column("limitations_json", sa.Text(), primary_key=False, nullable=False),
            sa.Column("result_json", sa.Text(), primary_key=False, nullable=False),
            sa.UniqueConstraint('input_fingerprint', name=None),
        )
        op.create_index('ix_insight_repo_analyzed', 'repository_insight_runs', ['repository_id', 'analyzed_at'], unique=False)


def downgrade():
    op.drop_table("repository_insight_runs")
    op.drop_table("repository_activity_events")
