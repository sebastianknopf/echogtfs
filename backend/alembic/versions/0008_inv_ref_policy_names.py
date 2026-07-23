"""Rename invalid reference policy values to object-generic names.

Revision ID: 0008_inv_ref_policy_names
Revises: 0007_realtime_is_valid_flag
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008_inv_ref_policy_names"
down_revision: Union[str, None] = "0007_realtime_is_valid_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_VALUES_CHECK = (
    "invalid_reference_policy IN ('discard_alert', 'keep_alert', 'discard_invalid', "
    "'discard_invalid_elements', 'not_specified')"
)

NEW_VALUES_CHECK = (
    "invalid_reference_policy IN ('discard_entire_object', 'keep_object_disabled', "
    "'discard_invalid', 'discard_invalid_elements', 'not_specified')"
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _drop_policy_constraints() -> None:
    # Support both current and legacy constraint names.
    op.execute("ALTER TABLE sys_data_sources DROP CONSTRAINT IF EXISTS ck_sys_dt_src_inv_ref_plc")
    op.execute("ALTER TABLE sys_data_sources DROP CONSTRAINT IF EXISTS chk_invalid_reference_policy")


def upgrade() -> None:
    table_name = "sys_data_sources"
    if not _table_exists(table_name):
        return

    _drop_policy_constraints()

    op.execute(
        """
        UPDATE sys_data_sources
        SET invalid_reference_policy = 'discard_entire_object'
        WHERE invalid_reference_policy = 'discard_alert'
        """
    )
    op.execute(
        """
        UPDATE sys_data_sources
        SET invalid_reference_policy = 'keep_object_disabled'
        WHERE invalid_reference_policy = 'keep_alert'
        """
    )
    op.create_check_constraint(
        "ck_sys_dt_src_inv_ref_plc",
        "sys_data_sources",
        NEW_VALUES_CHECK,
    )


def downgrade() -> None:
    table_name = "sys_data_sources"
    if not _table_exists(table_name):
        return

    _drop_policy_constraints()

    op.execute(
        """
        UPDATE sys_data_sources
        SET invalid_reference_policy = 'discard_alert'
        WHERE invalid_reference_policy = 'discard_entire_object'
        """
    )
    op.execute(
        """
        UPDATE sys_data_sources
        SET invalid_reference_policy = 'keep_alert'
        WHERE invalid_reference_policy = 'keep_object_disabled'
        """
    )
    op.create_check_constraint(
        "ck_sys_dt_src_inv_ref_plc",
        "sys_data_sources",
        OLD_VALUES_CHECK,
    )
