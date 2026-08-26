"""Fix realtime assignment_type check constraints to include current enum values.

Revision ID: 0013_fix_assignment_type
Revises: 0012_gtfs_trip_operation_day
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0013_fix_assignment_type"
down_revision: Union[str, None] = "0012_gtfs_trip_operation_day"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_check_constraints(table_name)
    if any(constraint["name"] == constraint_name for constraint in constraints):
        op.drop_constraint(constraint_name, table_name, type_="check")


def upgrade() -> None:
    for table_name, constraint_name in (
        ("realtime_trips", "ck_rt_trp_assignment_type"),
        ("realtime_vehicle_positions", "ck_rt_vhc_pos_assignment_type"),
    ):
        _drop_constraint_if_exists(table_name, constraint_name)

        op.create_check_constraint(
            constraint_name,
            table_name,
            "assignment_type IN ('DIRECT_BY_ID', 'MATCH_BY_CACHED_ID', "
            "'MATCHED_BY_START_STOP', 'MATCHED_BY_INTERMEDIATE_STOPS', "
            "'NO_MATCH_GENERAL', 'NO_MATCH_AMBIGUOUS_TRIP')",
        )


def downgrade() -> None:
    for table_name, constraint_name in (
        ("realtime_trips", "ck_rt_trp_assignment_type"),
        ("realtime_vehicle_positions", "ck_rt_vhc_pos_assignment_type"),
    ):
        _drop_constraint_if_exists(table_name, constraint_name)

        op.create_check_constraint(
            constraint_name,
            table_name,
            "assignment_type IN ('DIRECT_BY_ID', 'MATCHED_BY_START_STOP', "
            "'MATCHED_BY_CURRENT_STOP', 'NO_MATCH_GENERAL', 'NO_MATCH_AMBIGUOUS_TRIP')",
        )
