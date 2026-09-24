"""Add differential/incremental update support fields.

Revision ID: 0018_differential_updates
Revises: 0017_data_source_execution_type
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0018_differential_updates"
down_revision: Union[str, None] = "0017_data_source_execution_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists("sys_data_sources", "is_differential_updates"):
        op.add_column(
            "sys_data_sources",
            sa.Column(
                "is_differential_updates",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )

    if not _column_exists("realtime_trips", "is_complete_stop_sequence"):
        op.add_column(
            "realtime_trips",
            sa.Column(
                "is_complete_stop_sequence",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
        )

    if not _column_exists("realtime_stop_events", "scheduled_arrival_time"):
        op.add_column(
            "realtime_stop_events",
            sa.Column("scheduled_arrival_time", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("realtime_stop_events", "scheduled_departure_time"):
        op.add_column(
            "realtime_stop_events",
            sa.Column("scheduled_departure_time", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("realtime_stop_events", "scheduled_departure_time"):
        op.drop_column("realtime_stop_events", "scheduled_departure_time")

    if _column_exists("realtime_stop_events", "scheduled_arrival_time"):
        op.drop_column("realtime_stop_events", "scheduled_arrival_time")

    if _column_exists("realtime_trips", "is_complete_stop_sequence"):
        op.drop_column("realtime_trips", "is_complete_stop_sequence")

    if _column_exists("sys_data_sources", "is_differential_updates"):
        op.drop_column("sys_data_sources", "is_differential_updates")
