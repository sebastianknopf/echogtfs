"""Add operation_day_date column to gtfs_trips table.

Revision ID: 0012_gtfs_trip_operation_day
Revises: 0011_realtime_trip_metadata
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0012_gtfs_trip_operation_day"
down_revision: Union[str, None] = "0011_realtime_trip_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists("gtfs_trips", "operation_day_date"):
        op.add_column(
            "gtfs_trips",
            sa.Column(
                "operation_day_date",
                sa.Date(),
                nullable=False,
                server_default=sa.func.current_date(),
            ),
        )
        op.alter_column("gtfs_trips", "operation_day_date", server_default=None)


def downgrade() -> None:
    if _column_exists("gtfs_trips", "operation_day_date"):
        op.drop_column("gtfs_trips", "operation_day_date")
