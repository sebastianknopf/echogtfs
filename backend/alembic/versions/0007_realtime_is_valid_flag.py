"""Add is_valid flag to realtime trips, stop events, and vehicle positions.

Revision ID: 0007_realtime_is_valid_flag
Revises: 006_gtfs_rt_path_settings_split
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_realtime_is_valid_flag"
down_revision: Union[str, None] = "006_gtfs_rt_path_settings_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists("realtime_trips", "is_valid"):
        op.add_column(
            "realtime_trips",
            sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )

    if not _column_exists("realtime_stop_events", "is_valid"):
        op.add_column(
            "realtime_stop_events",
            sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )

    if not _column_exists("realtime_vehicle_positions", "is_valid"):
        op.add_column(
            "realtime_vehicle_positions",
            sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )


def downgrade() -> None:
    if _column_exists("realtime_vehicle_positions", "is_valid"):
        op.drop_column("realtime_vehicle_positions", "is_valid")

    if _column_exists("realtime_stop_events", "is_valid"):
        op.drop_column("realtime_stop_events", "is_valid")

    if _column_exists("realtime_trips", "is_valid"):
        op.drop_column("realtime_trips", "is_valid")
