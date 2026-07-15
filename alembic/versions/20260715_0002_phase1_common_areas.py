"""phase1 common areas: booking rules, schedules, blackouts, images

Revision ID: 20260715_0002
Revises: 20260715_0001
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0002"
down_revision: Union[str, Sequence[str], None] = "20260715_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("common_areas", sa.Column("category", sa.String(length=60), server_default="general", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("description", sa.Text(), server_default="", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("has_cost", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    _add_column_if_missing("common_areas", sa.Column("is_bookable", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    _add_column_if_missing("common_areas", sa.Column("min_duration_minutes", sa.Integer(), server_default="60", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("max_duration_minutes", sa.Integer(), server_default="240", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("min_advance_minutes", sa.Integer(), server_default="0", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("max_advance_days", sa.Integer(), server_default="90", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("cleanup_buffer_minutes", sa.Integer(), server_default="0", nullable=False))
    _add_column_if_missing("common_areas", sa.Column("max_active_per_resident", sa.Integer(), server_default="3", nullable=False))
    _add_column_if_missing(
        "common_areas",
        sa.Column("required_documents", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "common_area_schedules" not in tables:
        op.create_table(
            "common_area_schedules",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("common_area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("weekday", sa.Integer(), nullable=False),
            sa.Column("open_time", sa.Time(), nullable=True),
            sa.Column("close_time", sa.Time(), nullable=True),
            sa.Column("is_closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("common_area_id", "weekday", name="uq_common_area_weekday"),
        )

    if "common_area_blackouts" not in tables:
        op.create_table(
            "common_area_blackouts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("common_area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reason_type", sa.String(length=40), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            sa.Column("note", sa.String(length=240), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_common_area_blackouts_range", "common_area_blackouts", ["common_area_id", "starts_at", "ends_at"])

    if "common_area_images" not in tables:
        op.create_table(
            "common_area_images",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("common_area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    # Backfill has_cost from hourly_rate
    op.execute("UPDATE common_areas SET has_cost = TRUE WHERE hourly_rate > 0")


def downgrade() -> None:
    op.drop_table("common_area_images")
    op.drop_index("ix_common_area_blackouts_range", table_name="common_area_blackouts")
    op.drop_table("common_area_blackouts")
    op.drop_table("common_area_schedules")
    for col in (
        "required_documents",
        "max_active_per_resident",
        "cleanup_buffer_minutes",
        "max_advance_days",
        "min_advance_minutes",
        "max_duration_minutes",
        "min_duration_minutes",
        "is_bookable",
        "has_cost",
        "description",
        "category",
    ):
        op.drop_column("common_areas", col)
