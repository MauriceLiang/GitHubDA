"""Persist user-adjustable application settings."""
import sqlalchemy as sa
from alembic import op


revision = "0004_application_settings"
down_revision = "0003_activity_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("application_settings"):
        op.create_table(
            "application_settings",
            sa.Column("setting_key", sa.String(length=100), primary_key=True, nullable=False),
            sa.Column("setting_value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("application_settings"):
        op.drop_table("application_settings")
