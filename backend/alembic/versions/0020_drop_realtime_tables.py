"""Drop the PostgreSQL realtime tables, realtime objects are stored in MongoDB.

Revision ID: 0020_drop_realtime_tables
Revises: 0019_trip_start_time_nullable
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0020_drop_realtime_tables"
down_revision: Union[str, None] = "0019_trip_start_time_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REALTIME_TABLES = (
    "realtime_service_alert_informed_entities",
    "realtime_service_alert_active_periods",
    "realtime_service_alert_translations",
    "realtime_service_alerts",
    "realtime_stop_events",
    "realtime_vehicle_positions",
    "realtime_trips",
)

wheelchair_enum = sa.Enum(
    "NO_VALUE", "UNKNOWN", "WHEELCHAIR_ACCESSIBLE", "WHEELCHAIR_INACCESSIBLE",
    name="vehicle_wheelchair_accessible",
)
stop_status_enum = sa.Enum("INCOMING_AT", "STOPPED_AT", "IN_TRANSIT_TO", name="vehicle_stop_status")
congestion_enum = sa.Enum(
    "UNKNOWN_CONGESTION_LEVEL", "RUNNING_SMOOTHLY", "STOP_AND_GO", "CONGESTION", "SEVERE_CONGESTION",
    name="congestion_level",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    for table in REALTIME_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    bind = op.get_bind()
    wheelchair_enum.drop(bind, checkfirst=True)
    stop_status_enum.drop(bind, checkfirst=True)
    congestion_enum.drop(bind, checkfirst=True)


def downgrade() -> None:
    """Recreate the tables empty; data has to be restored from a backup."""
    op.create_table(
        "realtime_service_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("sys_data_sources.id", ondelete="CASCADE")),
        sa.Column("cause", sa.String(32), nullable=False),
        sa.Column("effect", sa.String(32), nullable=False),
        sa.Column("severity_level", sa.String(32), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "realtime_service_alert_translations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("header_text", sa.String(512)),
        sa.Column("description_text", sa.Text()),
        sa.Column("url", sa.String(1024)),
    )
    op.create_index("ix_realtime_service_alert_translations_alert_id", "realtime_service_alert_translations", ["alert_id"])
    op.create_table(
        "realtime_service_alert_active_periods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_type", sa.String(32), nullable=False),
        sa.Column("start_time", sa.BigInteger()),
        sa.Column("end_time", sa.BigInteger()),
    )
    op.create_index("ix_realtime_service_alert_active_periods_alert_id", "realtime_service_alert_active_periods", ["alert_id"])
    op.create_table(
        "realtime_service_alert_informed_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agency_id", sa.String(128)),
        sa.Column("route_id", sa.String(128)),
        sa.Column("route_type", sa.Integer()),
        sa.Column("stop_id", sa.String(128)),
        sa.Column("trip_id", sa.String(128)),
        sa.Column("direction_id", sa.Integer()),
        sa.Column("is_agency_valid", sa.Boolean(), nullable=False),
        sa.Column("is_route_valid", sa.Boolean(), nullable=False),
        sa.Column("is_stop_valid", sa.Boolean(), nullable=False),
        sa.Column("is_trip_valid", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_realtime_service_alert_informed_entities_alert_id", "realtime_service_alert_informed_entities", ["alert_id"])

    op.create_table(
        "realtime_trips",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("sys_data_sources.id", ondelete="CASCADE")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("trip_id", sa.Text(), nullable=False, unique=True),
        sa.Column("original_trip_id", sa.Text()),
        sa.Column("scheduled_start_stop_id", sa.Text()),
        sa.Column("scheduled_end_stop_id", sa.Text()),
        sa.Column("scheduled_start_time", sa.DateTime(timezone=True)),
        sa.Column("scheduled_end_time", sa.DateTime(timezone=True)),
        sa.Column("start_time", sa.Text()),
        sa.Column("start_date", sa.Text(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("schedule_relationship", sa.Text(), nullable=False),
        sa.Column("assignment_type", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.Column("is_trip_valid", sa.Boolean(), nullable=False),
        sa.Column("is_route_valid", sa.Boolean(), nullable=False),
        sa.Column("is_complete_stop_sequence", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_realtime_trips_data_source_id", "realtime_trips", ["data_source_id"])
    op.create_table(
        "realtime_stop_events",
        sa.Column("trip_id", sa.Text(), sa.ForeignKey("realtime_trips.trip_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("stop_id", sa.Text(), primary_key=True),
        sa.Column("original_stop_id", sa.Text(), nullable=False),
        sa.Column("stop_sequence", sa.Text(), primary_key=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_arrival_time", sa.DateTime(timezone=True)),
        sa.Column("scheduled_departure_time", sa.DateTime(timezone=True)),
        sa.Column("schedule_relationship", sa.Text(), nullable=False),
        sa.Column("is_implied_schedule_relationship", sa.Boolean(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "realtime_vehicle_positions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("sys_data_sources.id", ondelete="CASCADE")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("trip_id", sa.Text(), sa.ForeignKey("realtime_trips.trip_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("vehicle_id", sa.Text(), nullable=False),
        sa.Column("vehicle_label", sa.Text()),
        sa.Column("vehicle_license_plate", sa.Text()),
        sa.Column("vehicle_wheelchair_accessible", wheelchair_enum, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("current_stop_sequence", sa.Integer()),
        sa.Column("current_status", stop_status_enum, nullable=False),
        sa.Column("assignment_type", sa.String(64), nullable=False),
        sa.Column("congestion_level", congestion_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
    )
