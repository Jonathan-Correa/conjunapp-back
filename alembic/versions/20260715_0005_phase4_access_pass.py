"""phase4 access_code for reservation passes

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0005"
down_revision: Union[str, Sequence[str], None] = "20260715_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("reservations")}
    if "access_code" not in cols:
        op.add_column("reservations", sa.Column("access_code", sa.String(length=40), nullable=True))
        op.create_unique_constraint("uq_reservations_access_code", "reservations", ["access_code"])
    if "access_pin" not in cols:
        op.add_column("reservations", sa.Column("access_pin", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_constraint("uq_reservations_access_code", "reservations", type_="unique")
    op.drop_column("reservations", "access_pin")
    op.drop_column("reservations", "access_code")
