"""Make realtime vehicle current_stop_sequence nullable.

Revision ID: 0010_vhc_stop_seq_nullable
Revises: 0009_data_source_log_dumps
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0010_vhc_stop_seq_nullable"
down_revision: Union[str, None] = "0009_data_source_log_dumps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _get_column(table_name: str, column_name: str) -> dict[str, Any] | None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for column in inspector.get_columns(table_name):
        if column.get("name") == column_name:
            return column
    return None


def upgrade() -> None:
    if not _table_exists("realtime_vehicle_positions"):
        return

    column = _get_column("realtime_vehicle_positions", "current_stop_sequence")
    if column is not None and column.get("nullable") is False:
        op.alter_column(
            "realtime_vehicle_positions",
            "current_stop_sequence",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    if not _table_exists("realtime_vehicle_positions"):
        return

    column = _get_column("realtime_vehicle_positions", "current_stop_sequence")
    if column is not None and column.get("nullable") is True:
        op.execute("UPDATE realtime_vehicle_positions SET current_stop_sequence = 0 WHERE current_stop_sequence IS NULL")
        op.alter_column(
            "realtime_vehicle_positions",
            "current_stop_sequence",
            existing_type=sa.Integer(),
            nullable=False,
        )
