"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-10
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
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("route_id", "timestamp"),
        sa.UniqueConstraint("route_id", "timestamp", name="uq_raw_events_route_ts"),
    )
    op.create_index(
        "ix_raw_events_office_ts",
        "raw_events",
        ["office_from_id", sa.text("timestamp DESC")],
    )

    op.create_table(
        "actuals",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipments", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_id", "window_start", name="uq_actuals_route_window"),
    )
    op.create_index(
        "ix_actuals_route_window",
        "actuals",
        ["route_id", sa.text("window_start DESC")],
    )

    op.create_table(
        "route_forecast",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("run_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("y_hat_raw", sa.Float(), nullable=False),
        sa.Column("y_hat_future", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("y_hat_low", sa.Float()),
        sa.Column("y_hat_high", sa.Float()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_id", "run_ts", "horizon", name="uq_forecast_route_run_h"),
    )
    op.create_index("ix_forecast_route_run", "route_forecast", ["route_id", sa.text("run_ts DESC")])
    op.create_index("ix_forecast_office_run", "route_forecast", ["office_from_id", sa.text("run_ts DESC")])

    op.create_table(
        "route_metadata",
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("avg_duration_min", sa.Float(), nullable=False, server_default="120"),
        sa.Column("stddev_duration_min", sa.Float(), server_default="15"),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("route_id"),
    )

    op.create_table(
        "vehicle_state",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="free"),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("eta_return", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_warehouse_status", "vehicle_state", ["warehouse_id", "status"])

    op.create_table(
        "transport_order",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("office_from_id", sa.String(), nullable=False),
        sa.Column("scheduled_departure", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=False),
        sa.Column("vehicle_count", sa.Integer(), nullable=False),
        sa.Column("capacity_units", sa.Float(), nullable=False),
        sa.Column("chosen_horizon", sa.Integer(), nullable=False),
        sa.Column("optimizer_score", sa.Float(), nullable=False),
        sa.Column("y_hat_future", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_office_departure", "transport_order", ["office_from_id", "scheduled_departure"])
    op.create_index("ix_order_route_status", "transport_order", ["route_id", "status"])

    op.create_table(
        "warehouse_config",
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("gazel_capacity", sa.Float(), server_default="10.0"),
        sa.Column("fura_capacity", sa.Float(), server_default="40.0"),
        sa.Column("lead_time_min", sa.Integer(), server_default="60"),
        sa.Column("safety_factor", sa.Float(), server_default="1.05"),
        sa.Column("alpha", sa.Float(), server_default="0.7"),
        sa.Column("beta", sa.Float(), server_default="0.3"),
        sa.Column("travel_buffer_min", sa.Integer(), server_default="15"),
        sa.Column("avg_route_duration_min", sa.Float(), server_default="120"),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("warehouse_id"),
    )


def downgrade() -> None:
    op.drop_table("warehouse_config")
    op.drop_table("transport_order")
    op.drop_table("vehicle_state")
    op.drop_table("route_metadata")
    op.drop_table("route_forecast")
    op.drop_table("actuals")
    op.drop_table("raw_events")
