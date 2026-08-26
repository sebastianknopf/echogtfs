"""Add origin and implied flags to realtime stop events.

Revision ID: 0015_stop_event_implication
Revises: 0014_trip_route_validity
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0015_stop_event_implication"
down_revision: Union[str, None] = "0014_trip_route_validity"
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
    if not _column_exists("realtime_stop_events", "original_stop_id"):
        op.add_column(
            "realtime_stop_events",
            sa.Column("original_stop_id", sa.Text(), nullable=True),
        )

    if _column_exists("realtime_stop_events", "original_stop_id"):
        op.execute(
            """
            UPDATE realtime_stop_events
            SET original_stop_id = COALESCE(original_stop_id, stop_id)
            WHERE original_stop_id IS NULL
            """
        )

    if _column_exists("realtime_stop_events", "original_stop_id") and _column_nullable("realtime_stop_events", "original_stop_id"):
        op.alter_column("realtime_stop_events", "original_stop_id", existing_type=sa.Text(), nullable=False)

    if not _column_exists("realtime_stop_events", "is_implied_schedule_relationship"):
        op.add_column(
            "realtime_stop_events",
            sa.Column(
                "is_implied_schedule_relationship",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    else:
        op.execute(
            """
            UPDATE realtime_stop_events
            SET is_implied_schedule_relationship = COALESCE(is_implied_schedule_relationship, false)
            WHERE is_implied_schedule_relationship IS NULL
            """
        )
        if _column_nullable("realtime_stop_events", "is_implied_schedule_relationship"):
            op.alter_column(
                "realtime_stop_events",
                "is_implied_schedule_relationship",
                existing_type=sa.Boolean(),
                nullable=False,
            )

    if _column_exists("realtime_stop_events", "is_implied_schedule_relationship"):
        op.alter_column(
            "realtime_stop_events",
            "is_implied_schedule_relationship",
            existing_type=sa.Boolean(),
            server_default=sa.text("false"),
        )


def downgrade() -> None:
    if _column_exists("realtime_stop_events", "is_implied_schedule_relationship"):
        op.drop_column("realtime_stop_events", "is_implied_schedule_relationship")

    if _column_exists("realtime_stop_events", "original_stop_id"):
        op.drop_column("realtime_stop_events", "original_stop_id")
