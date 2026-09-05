"""Split service-alert informed-entity validity into per-reference flags.

Revision ID: 0016_alert_entity_validity_split
Revises: 0015_stop_event_implication
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0016_alert_entity_validity_split"
down_revision: Union[str, None] = "0015_stop_event_implication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "realtime_service_alert_informed_entities"
_OLD_FLAG = "is_valid"
_NEW_FLAGS = (
    "is_agency_valid",
    "is_route_valid",
    "is_stop_valid",
    "is_trip_valid",
)


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _column_nullable(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    for column in columns:
        if column["name"] == column_name:
            return bool(column["nullable"])
    return True


def upgrade() -> None:
    for column_name in _NEW_FLAGS:
        if not _column_exists(_TABLE_NAME, column_name):
            op.add_column(
                _TABLE_NAME,
                sa.Column(column_name, sa.Boolean(), server_default=sa.text("true"), nullable=False),
            )

    if _column_exists(_TABLE_NAME, _OLD_FLAG):
        op.execute(
            """
            UPDATE realtime_service_alert_informed_entities
            SET
                is_agency_valid = COALESCE(is_agency_valid, is_valid, true),
                is_route_valid = COALESCE(is_route_valid, is_valid, true),
                is_stop_valid = COALESCE(is_stop_valid, is_valid, true),
                is_trip_valid = COALESCE(is_trip_valid, is_valid, true)
            """
        )
    else:
        op.execute(
            """
            UPDATE realtime_service_alert_informed_entities
            SET
                is_agency_valid = COALESCE(is_agency_valid, true),
                is_route_valid = COALESCE(is_route_valid, true),
                is_stop_valid = COALESCE(is_stop_valid, true),
                is_trip_valid = COALESCE(is_trip_valid, true)
            """
        )

    for column_name in _NEW_FLAGS:
        if _column_exists(_TABLE_NAME, column_name) and _column_nullable(_TABLE_NAME, column_name):
            op.alter_column(
                _TABLE_NAME,
                column_name,
                existing_type=sa.Boolean(),
                nullable=False,
            )

        if _column_exists(_TABLE_NAME, column_name):
            op.alter_column(
                _TABLE_NAME,
                column_name,
                existing_type=sa.Boolean(),
                server_default=sa.text("true"),
            )

    if _column_exists(_TABLE_NAME, _OLD_FLAG):
        op.drop_column(_TABLE_NAME, _OLD_FLAG)


def downgrade() -> None:
    if not _column_exists(_TABLE_NAME, _OLD_FLAG):
        op.add_column(
            _TABLE_NAME,
            sa.Column(_OLD_FLAG, sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )

    if _column_exists(_TABLE_NAME, _OLD_FLAG):
        op.execute(
            """
            UPDATE realtime_service_alert_informed_entities
            SET is_valid = COALESCE(
                is_valid,
                COALESCE(is_agency_valid, true)
                AND COALESCE(is_route_valid, true)
                AND COALESCE(is_stop_valid, true)
                AND COALESCE(is_trip_valid, true)
            )
            """
        )

        if _column_nullable(_TABLE_NAME, _OLD_FLAG):
            op.alter_column(
                _TABLE_NAME,
                _OLD_FLAG,
                existing_type=sa.Boolean(),
                nullable=False,
            )

        op.alter_column(
            _TABLE_NAME,
            _OLD_FLAG,
            existing_type=sa.Boolean(),
            server_default=sa.text("true"),
        )

    for column_name in _NEW_FLAGS:
        if _column_exists(_TABLE_NAME, column_name):
            op.drop_column(_TABLE_NAME, column_name)
