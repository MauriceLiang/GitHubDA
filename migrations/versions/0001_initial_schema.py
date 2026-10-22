"""Initial backend schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op

from backend.app.persistence.db import Base
from backend.app.persistence import models  # noqa: F401


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

LATER_TABLES = {"dataset_import_jobs", "dataset_import_staging_records"}


def upgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in LATER_TABLES]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in LATER_TABLES]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables)
