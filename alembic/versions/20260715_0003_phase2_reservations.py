"""phase2 availability, reject status, reservation events

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0003"
down_revision: Union[str, Sequence[str], None] = "20260715_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Add enum value for rejected (PostgreSQL)
    op.execute("ALTER TYPE reservationstatus ADD VALUE IF NOT EXISTS 'rejected'")

    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("reservations")}
    if "reject_reason" not in cols:
        op.add_column("reservations", sa.Column("reject_reason", sa.String(length=240), nullable=True))

    tables = set(inspector.get_table_names())
    if "reservation_events" not in tables:
        op.create_table(
            "reservation_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("reservation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("actor_type", sa.String(length=20), nullable=False),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_reservation_events_reservation", "reservation_events", ["reservation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reservation_events_reservation", table_name="reservation_events")
    op.drop_table("reservation_events")
    op.drop_column("reservations", "reject_reason")
    # PostgreSQL cannot easily remove enum values; leave 'rejected' in place.
