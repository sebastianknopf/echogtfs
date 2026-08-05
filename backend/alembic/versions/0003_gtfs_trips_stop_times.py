"""Add GTFS trip and stop time tables.

Revision ID: 0003_gtfs_trips_stop_times
Revises: 0002_database_design
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_gtfs_trips_stop_times"
down_revision: Union[str, None] = "0002_database_design"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gtfs_trips",
        sa.Column("gtfs_id", sa.Text(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("direction_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_stop_id", sa.Text(), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_stop_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["gtfs_routes.gtfs_id"]),
        sa.ForeignKeyConstraint(["start_stop_id"], ["gtfs_stops.gtfs_id"]),
        sa.ForeignKeyConstraint(["end_stop_id"], ["gtfs_stops.gtfs_id"]),
        sa.PrimaryKeyConstraint("gtfs_id"),
    )

    op.create_index(
        "ix_gtfs_trips_route_start_end_lookup",
        "gtfs_trips",
        ["route_id", "start_stop_id", "start_time", "end_stop_id", "end_time"],
        unique=False,
    )

    op.create_table(
        "gtfs_stop_times",
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("stop_id", sa.Text(), nullable=False),
        sa.Column("stop_sequence", sa.Integer(), nullable=False),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["gtfs_trips.gtfs_id"]),
        sa.ForeignKeyConstraint(["stop_id"], ["gtfs_stops.gtfs_id"]),
        sa.PrimaryKeyConstraint("trip_id", "stop_id", "stop_sequence"),
    )


def downgrade() -> None:
    op.drop_table("gtfs_stop_times")

    op.drop_index("ix_gtfs_trips_route_start_end_lookup", table_name="gtfs_trips")
    op.drop_table("gtfs_trips")