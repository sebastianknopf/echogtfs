"""Split realtime trip validity into trip and route flags.

Revision ID: 0014_trip_route_validity
Revises: 0013_fix_assignment_type
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0014_trip_route_validity"
down_revision: Union[str, None] = "0013_fix_assignment_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    if not _column_exists("realtime_trips", "is_trip_valid"):
        op.add_column(
            "realtime_trips",
            sa.Column(
                "is_trip_valid",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
        )

    if not _column_exists("realtime_trips", "is_route_valid"):
        op.add_column(
            "realtime_trips",
            sa.Column(
                "is_route_valid",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
        )

    if _column_exists("realtime_trips", "is_valid"):
        op.execute(
            """
            UPDATE realtime_trips
            SET
                is_trip_valid = COALESCE(is_trip_valid, is_valid),
                is_route_valid = COALESCE(is_route_valid, is_valid)
            """
        )

    op.execute(
        """
        UPDATE realtime_trips
        SET
            is_trip_valid = COALESCE(is_trip_valid, true),
            is_route_valid = COALESCE(is_route_valid, true)
        WHERE is_trip_valid IS NULL OR is_route_valid IS NULL
        """
    )

    if _column_exists("realtime_trips", "is_trip_valid") and _column_nullable("realtime_trips", "is_trip_valid"):
        op.alter_column("realtime_trips", "is_trip_valid", existing_type=sa.Boolean(), nullable=False)

    if _column_exists("realtime_trips", "is_route_valid") and _column_nullable("realtime_trips", "is_route_valid"):
        op.alter_column("realtime_trips", "is_route_valid", existing_type=sa.Boolean(), nullable=False)

    if _column_exists("realtime_trips", "is_trip_valid"):
        op.alter_column("realtime_trips", "is_trip_valid", existing_type=sa.Boolean(), server_default=None)

    if _column_exists("realtime_trips", "is_route_valid"):
        op.alter_column("realtime_trips", "is_route_valid", existing_type=sa.Boolean(), server_default=None)

    if _column_exists("realtime_trips", "is_valid"):
        op.drop_column("realtime_trips", "is_valid")


def downgrade() -> None:
    if not _column_exists("realtime_trips", "is_valid"):
        op.add_column(
            "realtime_trips",
            sa.Column("is_valid", sa.Boolean(), nullable=True),
        )

    if _column_exists("realtime_trips", "is_trip_valid"):
        op.execute(
            """
            UPDATE realtime_trips
            SET is_valid = COALESCE(is_valid, is_trip_valid)
            """
        )

    if _column_exists("realtime_trips", "is_valid"):
        op.execute(
            """
            UPDATE realtime_trips
            SET is_valid = COALESCE(is_valid, true)
            WHERE is_valid IS NULL
            """
        )

    if _column_exists("realtime_trips", "is_valid") and _column_nullable("realtime_trips", "is_valid"):
        op.alter_column("realtime_trips", "is_valid", existing_type=sa.Boolean(), nullable=False)

    if _column_exists("realtime_trips", "is_route_valid"):
        op.drop_column("realtime_trips", "is_route_valid")

    if _column_exists("realtime_trips", "is_trip_valid"):
        op.drop_column("realtime_trips", "is_trip_valid")
