"""Add realtime trip, stop event, and vehicle position tables.

Revision ID: 005_realtime_tables
Revises: 0004_gtfs_static_pk
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_realtime_tables"
down_revision: Union[str, None] = "0004_gtfs_static_pk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


vehicle_wheelchair_accessible_enum = sa.Enum(
    "NO_VALUE",
    "UNKNOWN",
    "WHEELCHAIR_ACCESSIBLE",
    "WHEELCHAIR_INACCESSIBLE",
    name="vehicle_wheelchair_accessible",
)

vehicle_stop_status_enum = sa.Enum(
    "INCOMING_AT",
    "STOPPED_AT",
    "IN_TRANSIT_TO",
    name="vehicle_stop_status",
)

congestion_level_enum = sa.Enum(
    "UNKNOWN_CONGESTION_LEVEL",
    "RUNNING_SMOOTHLY",
    "STOP_AND_GO",
    "CONGESTION",
    "SEVERE_CONGESTION",
    name="congestion_level",
)


ASSIGNMENT_TYPE_CHECK = (
    "assignment_type IN ('DIRECT_BY_ID', 'MATCHED_BY_START_STOP', "
    "'MATCHED_BY_CURRENT_STOP', 'NO_MATCH_GENERAL', 'NO_MATCH_AMBIGUOUS_TRIP')"
)


def upgrade() -> None:
    op.create_table(
        "realtime_trips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), server_default=sa.text("'echogtfs'"), nullable=False),
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Text(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("schedule_relationship", sa.Text(), server_default=sa.text("'SCHEDULED'"), nullable=False),
        sa.Column("assignment_type", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(ASSIGNMENT_TYPE_CHECK, name="ck_rt_trp_assignment_type"),
        sa.ForeignKeyConstraint(["data_source_id"], ["sys_data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )

    op.create_index(
        "idx_rt_trp_data_source_id",
        "realtime_trips",
        ["data_source_id"],
        unique=False,
    )

    op.create_table(
        "realtime_stop_events",
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("stop_id", sa.Text(), nullable=False),
        sa.Column("stop_sequence", sa.Text(), nullable=False),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_relationship", sa.Text(), server_default=sa.text("'SCHEDULE'"), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["realtime_trips.trip_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trip_id", "stop_id", "stop_sequence"),
    )

    op.create_table(
        "realtime_vehicle_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), server_default=sa.text("'echogtfs'"), nullable=False),
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("vehicle_id", sa.Text(), nullable=False),
        sa.Column("vehicle_label", sa.Text(), server_default=sa.text("NULL"), nullable=True),
        sa.Column("vehicle_license_plate", sa.Text(), server_default=sa.text("NULL"), nullable=True),
        sa.Column(
            "vehicle_wheelchair_accessible",
            vehicle_wheelchair_accessible_enum,
            server_default=sa.text("'NO_VALUE'"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("current_stop_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "current_status",
            vehicle_stop_status_enum,
            server_default=sa.text("'IN_TRANSIT_TO'"),
            nullable=False,
        ),
        sa.Column("assignment_type", sa.Text(), nullable=False),
        sa.Column(
            "congestion_level",
            congestion_level_enum,
            server_default=sa.text("'UNKNOWN_CONGESTION_LEVEL'"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(ASSIGNMENT_TYPE_CHECK, name="ck_rt_vhc_pos_assignment_type"),
        sa.ForeignKeyConstraint(["data_source_id"], ["sys_data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["realtime_trips.trip_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )


def downgrade() -> None:
    op.drop_table("realtime_vehicle_positions")
    op.drop_table("realtime_stop_events")

    op.drop_index("idx_rt_trp_data_source_id", table_name="realtime_trips")
    op.drop_table("realtime_trips")

    bind = op.get_bind()
    vehicle_wheelchair_accessible_enum.drop(bind, checkfirst=True)
    vehicle_stop_status_enum.drop(bind, checkfirst=True)
    congestion_level_enum.drop(bind, checkfirst=True)
