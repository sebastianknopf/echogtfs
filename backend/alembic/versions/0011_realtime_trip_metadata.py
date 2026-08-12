"""Add metadata columns to realtime trips for original and scheduled trip references.

Revision ID: 0011_realtime_trip_metadata
Revises: 0007_realtime_is_valid_flag
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0011_realtime_trip_metadata"
down_revision: Union[str, None] = "0010_vhc_stop_seq_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists("realtime_trips", "original_trip_id"):
        op.add_column(
            "realtime_trips",
            sa.Column("original_trip_id", sa.Text(), nullable=True),
        )

    if not _column_exists("realtime_trips", "scheduled_start_stop_id"):
        op.add_column(
            "realtime_trips",
            sa.Column("scheduled_start_stop_id", sa.Text(), nullable=True),
        )

    if not _column_exists("realtime_trips", "scheduled_end_stop_id"):
        op.add_column(
            "realtime_trips",
            sa.Column("scheduled_end_stop_id", sa.Text(), nullable=True),
        )

    if not _column_exists("realtime_trips", "scheduled_start_time"):
        op.add_column(
            "realtime_trips",
            sa.Column("scheduled_start_time", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("realtime_trips", "scheduled_end_time"):
        op.add_column(
            "realtime_trips",
            sa.Column("scheduled_end_time", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("realtime_trips", "scheduled_end_time"):
        op.drop_column("realtime_trips", "scheduled_end_time")

    if _column_exists("realtime_trips", "scheduled_start_time"):
        op.drop_column("realtime_trips", "scheduled_start_time")

    if _column_exists("realtime_trips", "scheduled_end_stop_id"):
        op.drop_column("realtime_trips", "scheduled_end_stop_id")

    if _column_exists("realtime_trips", "scheduled_start_stop_id"):
        op.drop_column("realtime_trips", "scheduled_start_stop_id")

    if _column_exists("realtime_trips", "original_trip_id"):
        op.drop_column("realtime_trips", "original_trip_id")
