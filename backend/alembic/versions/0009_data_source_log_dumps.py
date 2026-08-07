"""Add data source log dump toggle and make log dump file UUID optional.

Revision ID: 0009_data_source_log_dumps
Revises: 0008_inv_ref_policy_names
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009_data_source_log_dumps"
down_revision: Union[str, None] = "0008_inv_ref_policy_names"
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
    if _table_exists("sys_data_sources") and _get_column("sys_data_sources", "log_dumps") is None:
        op.add_column(
            "sys_data_sources",
            sa.Column("log_dumps", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        )

    if _table_exists("sys_data_source_logs"):
        column = _get_column("sys_data_source_logs", "log_file_uuid")
        if column is not None and column.get("nullable") is False:
            op.alter_column(
                "sys_data_source_logs",
                "log_file_uuid",
                existing_type=sa.Uuid(),
                nullable=True,
            )


def downgrade() -> None:
    if _table_exists("sys_data_source_logs"):
        column = _get_column("sys_data_source_logs", "log_file_uuid")
        if column is not None and column.get("nullable") is True:
            op.execute("DELETE FROM sys_data_source_logs WHERE log_file_uuid IS NULL")
            op.alter_column(
                "sys_data_source_logs",
                "log_file_uuid",
                existing_type=sa.Uuid(),
                nullable=False,
            )

    if _table_exists("sys_data_sources") and _get_column("sys_data_sources", "log_dumps") is not None:
        op.drop_column("sys_data_sources", "log_dumps")
