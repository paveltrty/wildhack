"""Add fura_count, gazel_count, planned_volume to transport_order

Revision ID: 002
Revises: 001
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transport_order",
        sa.Column("fura_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transport_order",
        sa.Column("gazel_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transport_order",
        sa.Column("planned_volume", sa.Float(), nullable=True),
    )
    op.alter_column("transport_order", "vehicle_type", nullable=True)
    op.alter_column("transport_order", "vehicle_count", nullable=True)


def downgrade() -> None:
    op.alter_column("transport_order", "vehicle_count", nullable=False)
    op.alter_column("transport_order", "vehicle_type", nullable=False)
    op.drop_column("transport_order", "planned_volume")
    op.drop_column("transport_order", "gazel_count")
    op.drop_column("transport_order", "fura_count")
