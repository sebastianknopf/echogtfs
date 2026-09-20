"""Add execution_type column to data sources.

Revision ID: 0017_data_source_execution_type
Revises: 0016_alert_entity_validity_split
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0017_data_source_execution_type"
down_revision: Union[str, None] = "0016_alert_entity_validity_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "sys_data_sources"
_COLUMN_NAME = "execution_type"


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists(_TABLE_NAME, _COLUMN_NAME):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _COLUMN_NAME,
                sa.String(32),
                server_default=sa.text("'time_based'"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    if _column_exists(_TABLE_NAME, _COLUMN_NAME):
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
