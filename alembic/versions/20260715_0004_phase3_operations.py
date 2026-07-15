"""phase3 completed, receipt, special hours

Revision ID: 20260715_0004
Revises: 20260715_0003
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0004"
down_revision: Union[str, Sequence[str], None] = "20260715_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE reservationstatus ADD VALUE IF NOT EXISTS 'completed'")

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("reservations")}
    if "receipt_number" not in cols:
        op.add_column("reservations", sa.Column("receipt_number", sa.String(length=40), nullable=True))
        op.create_unique_constraint("uq_reservations_receipt_number", "reservations", ["receipt_number"])

    tables = set(inspector.get_table_names())
    if "common_area_special_hours" not in tables:
        op.create_table(
            "common_area_special_hours",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("common_area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("on_date", sa.Date(), nullable=False),
            sa.Column("open_time", sa.Time(), nullable=True),
            sa.Column("close_time", sa.Time(), nullable=True),
            sa.Column("is_closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("note", sa.String(length=240), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("common_area_id", "on_date", name="uq_common_area_special_date"),
        )


def downgrade() -> None:
    op.drop_table("common_area_special_hours")
    op.drop_constraint("uq_reservations_receipt_number", "reservations", type_="unique")
    op.drop_column("reservations", "receipt_number")
