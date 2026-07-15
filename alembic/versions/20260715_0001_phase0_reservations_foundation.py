"""phase0 reservations foundation: admin.complex_id + indexes

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("admin_users")}
    if "complex_id" not in columns:
        op.add_column(
            "admin_users",
            sa.Column("complex_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_admin_users_complex_id",
            "admin_users",
            "residential_complexes",
            ["complex_id"],
            ["id"],
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("common_areas")}
    if "ix_common_areas_complex_active" not in indexes:
        op.create_index(
            "ix_common_areas_complex_active",
            "common_areas",
            ["complex_id", "is_active"],
            unique=False,
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("reservations")}
    if "ix_reservations_area_times" not in indexes:
        op.create_index(
            "ix_reservations_area_times",
            "reservations",
            ["common_area_id", "starts_at", "ends_at"],
            unique=False,
        )
    if "ix_reservations_resident_status" not in indexes:
        op.create_index(
            "ix_reservations_resident_status",
            "reservations",
            ["resident_id", "status"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_reservations_resident_status", table_name="reservations")
    op.drop_index("ix_reservations_area_times", table_name="reservations")
    op.drop_index("ix_common_areas_complex_active", table_name="common_areas")
    op.drop_constraint("fk_admin_users_complex_id", "admin_users", type_="foreignkey")
    op.drop_column("admin_users", "complex_id")
