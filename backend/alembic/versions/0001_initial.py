"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    
    ###
    # System Tables
    ###
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=2048), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_technical_contact", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("config", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("cron", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "invalid_reference_policy",
            sa.String(length=32),
            server_default=sa.text("'not_specified'"),
            nullable=False,
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "invalid_reference_policy IN ('discard_alert', 'keep_alert', 'discard_invalid', "
            "'discard_invalid_elements', 'not_specified')",
            name="chk_invalid_reference_policy",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )    

    op.create_table(
        "data_source_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "data_source_enrichments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("enrichment_type", sa.String(length=32), nullable=False),
        sa.Column("source_field", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("enrichment_type IN ('cause', 'effect', 'severity')", name="chk_enrichment_type"),
        sa.CheckConstraint(
            "source_field IN ('header', 'description', 'header_description')",
            name="chk_source_field",
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "data_source_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_url", sa.String(length=2048), nullable=False),
        sa.Column("request_headers", sa.Text(), nullable=True),
        sa.Column("response_headers", sa.Text(), nullable=True),
        sa.Column("response_mimetype", sa.String(length=255), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_size", sa.BigInteger(), nullable=True),
        sa.Column("log_file_uuid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    ###
    # GTFS Nominal Tables
    ###
    op.create_table(
        "gtfs_agencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gtfs_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gtfs_id"),
    )

    op.create_table(
        "gtfs_routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gtfs_id", sa.String(length=128), nullable=False),
        sa.Column("short_name", sa.String(length=128), nullable=False),
        sa.Column("long_name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gtfs_id"),
    )

    op.create_table(
        "gtfs_stops",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gtfs_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gtfs_id"),
    )

    ###
    # GTFS Realtime Service Alert Tables
    ###
    op.create_table(
        "service_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("cause", sa.String(length=32), nullable=False),
        sa.Column("effect", sa.String(length=32), nullable=False),
        sa.Column("severity_level", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "service_alert_active_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(length=32), server_default=sa.text("'impact_period'"), nullable=False),
        sa.Column("start_time", sa.BigInteger(), nullable=True),
        sa.Column("end_time", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "period_type IN ('impact_period', 'communication_period')",
            name="chk_period_type",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["service_alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "service_alert_informed_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("agency_id", sa.String(length=128), nullable=True),
        sa.Column("route_id", sa.String(length=128), nullable=True),
        sa.Column("route_type", sa.Integer(), nullable=True),
        sa.Column("stop_id", sa.String(length=128), nullable=True),
        sa.Column("trip_id", sa.String(length=128), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["service_alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "service_alert_translations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("header_text", sa.String(length=512), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["service_alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    ###
    # Indexes
    ###
    # app_settings: lookup by key is covered by the primary key index
    # users: lookup by id is covered by PK; lookup by username is covered by UNIQUE(username)

    op.create_index("ix_data_source_mappings_data_source_id", "data_source_mappings", ["data_source_id"], unique=False)
    op.create_index("ix_data_source_enrichments_data_source_id", "data_source_enrichments", ["data_source_id"], unique=False)
    op.create_index("ix_data_source_logs_data_source_id", "data_source_logs", ["data_source_id"], unique=False)

    # gtfs_agencies/gtfs_routes/gtfs_stops lookup by id is covered by PK indexes

    # service_alerts lookup by id is covered by the primary key index
    op.create_index("ix_service_alert_active_periods_alert_id", "service_alert_active_periods", ["alert_id"], unique=False)
    op.create_index("ix_service_alert_informed_entities_alert_id", "service_alert_informed_entities", ["alert_id"], unique=False)
    op.create_index("ix_service_alert_translations_alert_id", "service_alert_translations", ["alert_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_service_alert_translations_alert_id", table_name="service_alert_translations")
    op.drop_index("ix_service_alert_informed_entities_alert_id", table_name="service_alert_informed_entities")
    op.drop_index("ix_service_alert_active_periods_alert_id", table_name="service_alert_active_periods")
    op.drop_index("ix_data_source_logs_data_source_id", table_name="data_source_logs")
    op.drop_index("ix_data_source_enrichments_data_source_id", table_name="data_source_enrichments")
    op.drop_index("ix_data_source_mappings_data_source_id", table_name="data_source_mappings")

    op.drop_table("service_alert_translations")
    op.drop_table("service_alert_informed_entities")
    op.drop_table("service_alert_active_periods")
    op.drop_table("service_alerts")
    op.drop_table("gtfs_stops")
    op.drop_table("gtfs_routes")
    op.drop_table("gtfs_agencies")
    op.drop_table("data_source_logs")
    op.drop_table("data_source_enrichments")
    op.drop_table("data_source_mappings")
    op.drop_table("data_sources")
    op.drop_table("users")
    op.drop_table("app_settings")
