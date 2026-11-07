"""Add role column to users, replacing is_superuser and is_technical_contact.

Revision ID: 0021_user_role
Revises: 0020_drop_realtime_tables
Create Date: 2026-11-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0021_user_role"
down_revision: Union[str, None] = "0020_drop_realtime_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(32), server_default=sa.text("'USER'"), nullable=False),
    )
    op.execute(
        "UPDATE users SET role = CASE "
        "WHEN is_superuser THEN 'ADMIN' "
        "WHEN is_technical_contact THEN 'POWERUSER' "
        "ELSE 'USER' END"
    )
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_technical_contact")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_technical_contact", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        "UPDATE users SET is_superuser = (role = 'ADMIN'), "
        "is_technical_contact = (role = 'POWERUSER')"
    )
    op.drop_column("users", "role")
