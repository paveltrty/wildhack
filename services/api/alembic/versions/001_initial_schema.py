"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_1", sa.Float()),
        sa.Column("status_2", sa.Float()),
        sa.Column("status_3", sa.Float()),
        sa.Column("status_4", sa.Float()),
        sa.Column("status_5", sa.Float()),
        sa.Column("status_6", sa.Float()),
        sa.Column("status_7", sa.Float()),
        sa.Column("status_8", sa.Float()),
        sa.Column("pipeline_velocity", sa.Float()),
        sa.Column("target_2h", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raw_events_route_ts", "raw_events", ["route_id", "timestamp"])
    op.create_index("ix_raw_events_office_ts", "raw_events", ["office_from_id", "timestamp"])

    op.create_table(
        "route_metadata",
        sa.Column("route_id", sa.String(), primary_key=True),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("avg_duration_min", sa.Float(), nullable=False),
        sa.Column("stddev_duration_min", sa.Float(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "warehouse_forecast",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("minutes_ahead", sa.Integer(), nullable=False),
        sa.Column("y_hat", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("y_hat_low", sa.Float()),
        sa.Column("y_hat_high", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_ts", "office_from_id", "horizon", name="uq_forecast_run_office_h"),
    )
    op.create_index("ix_forecast_office_run", "warehouse_forecast", ["office_from_id", "run_ts"])

    op.create_table(
        "vehicle_state",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="free"),
        sa.Column("route_id", sa.String(), sa.ForeignKey("route_metadata.route_id"), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta_return", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_vehicle_warehouse_status", "vehicle_state", ["warehouse_id", "status"])

    op.create_table(
        "transport_order",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("scheduled_departure", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=False),
        sa.Column("vehicle_count", sa.Integer(), nullable=False),
        sa.Column("capacity_units", sa.Float(), nullable=False),
        sa.Column("chosen_horizon", sa.Integer(), nullable=False),
        sa.Column("optimizer_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_warehouse_departure", "transport_order", ["warehouse_id", "scheduled_departure"])
    op.create_index("ix_order_status", "transport_order", ["status"])

    op.create_table(
        "warehouse_config",
        sa.Column("warehouse_id", sa.String(), primary_key=True),
        sa.Column("gazel_capacity", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("fura_capacity", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("lead_time_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("safety_factor", sa.Float(), nullable=False, server_default="1.05"),
        sa.Column("alpha", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("beta", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("travel_buffer_min", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "actuals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_shipments", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("actuals")
    op.drop_table("warehouse_config")
    op.drop_table("transport_order")
    op.drop_table("vehicle_state")
    op.drop_table("warehouse_forecast")
    op.drop_table("route_metadata")
    op.drop_table("raw_events")
