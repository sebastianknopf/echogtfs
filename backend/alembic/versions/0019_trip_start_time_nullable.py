"""Allow NULL in realtime_trips.start_time.

Revision ID: 0019_trip_start_time_nullable
Revises: 0018_differential_updates
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0019_trip_start_time_nullable"
down_revision: Union[str, None] = "0018_differential_updates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_nullable(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    for column in columns:
        if column["name"] == column_name:
            return bool(column["nullable"])
    return True


def upgrade() -> None:
    if not _column_nullable("realtime_trips", "start_time"):
        op.alter_column(
            "realtime_trips",
            "start_time",
            existing_type=sa.Text(),
            nullable=True,
        )


def downgrade() -> None:
    if _column_nullable("realtime_trips", "start_time"):
        op.execute(
            """
            UPDATE realtime_trips
            SET start_time = ''
            WHERE start_time IS NULL
            """
        )
        op.alter_column(
            "realtime_trips",
            "start_time",
            existing_type=sa.Text(),
            nullable=False,
        )
