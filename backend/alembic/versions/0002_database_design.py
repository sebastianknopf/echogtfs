"""Rename system and realtime tables with explicit prefixes.

Revision ID: 0002_database_design
Revises: 0001_initial
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002_database_design"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_RENAMES = [
    ("app_settings", "sys_app_settings"),
    ("users", "sys_users"),
    ("data_sources", "sys_data_sources"),
    ("data_source_mappings", "sys_data_source_mappings"),
    ("data_source_enrichments", "sys_data_source_enrichments"),
    ("data_source_logs", "sys_data_source_logs"),
    ("service_alerts", "realtime_service_alerts"),
    ("service_alert_active_periods", "realtime_service_alert_active_periods"),
    ("service_alert_informed_entities", "realtime_service_alert_informed_entities"),
    ("service_alert_translations", "realtime_service_alert_translations"),
]


SEQUENCE_RENAMES = [
    ("users_id_seq", "sys_users_id_seq"),
    ("data_sources_id_seq", "sys_data_sources_id_seq"),
    ("data_source_mappings_id_seq", "sys_data_source_mappings_id_seq"),
    ("data_source_enrichments_id_seq", "sys_data_source_enrichments_id_seq"),
    ("data_source_logs_id_seq", "sys_data_source_logs_id_seq"),
    (
        "service_alert_active_periods_id_seq",
        "realtime_service_alert_active_periods_id_seq",
    ),
    (
        "service_alert_informed_entities_id_seq",
        "realtime_service_alert_informed_entities_id_seq",
    ),
    (
        "service_alert_translations_id_seq",
        "realtime_service_alert_translations_id_seq",
    ),
]


DROP_CONSTRAINT_TYPES = ("f", "p", "u", "c")


CREATE_OLD_CONSTRAINTS = [
    ("app_settings", "app_settings_pkey", "primary", ["key"]),
    ("users", "users_pkey", "primary", ["id"]),
    ("users", "users_email_key", "unique", ["email"]),
    ("users", "users_username_key", "unique", ["username"]),
    ("data_sources", "data_sources_pkey", "primary", ["id"]),
    ("data_sources", "data_sources_name_key", "unique", ["name"]),
    (
        "data_sources",
        "chk_invalid_reference_policy",
        "check",
        "invalid_reference_policy IN ('discard_alert', 'keep_alert', 'discard_invalid', 'discard_invalid_elements', 'not_specified')",
    ),
    ("data_source_mappings", "data_source_mappings_pkey", "primary", ["id"]),
    ("data_source_enrichments", "data_source_enrichments_pkey", "primary", ["id"]),
    (
        "data_source_enrichments",
        "chk_enrichment_type",
        "check",
        "enrichment_type IN ('cause', 'effect', 'severity')",
    ),
    (
        "data_source_enrichments",
        "chk_source_field",
        "check",
        "source_field IN ('header', 'description', 'header_description')",
    ),
    ("data_source_logs", "data_source_logs_pkey", "primary", ["id"]),
    ("service_alerts", "service_alerts_pkey", "primary", ["id"]),
    ("service_alert_active_periods", "service_alert_active_periods_pkey", "primary", ["id"]),
    (
        "service_alert_active_periods",
        "chk_period_type",
        "check",
        "period_type IN ('impact_period', 'communication_period')",
    ),
    ("service_alert_informed_entities", "service_alert_informed_entities_pkey", "primary", ["id"]),
    ("service_alert_translations", "service_alert_translations_pkey", "primary", ["id"]),
    ("data_source_mappings", "data_source_mappings_data_source_id_fkey", "foreign", ["data_source_id"], "data_sources", ["id"], "CASCADE"),
    ("data_source_enrichments", "data_source_enrichments_data_source_id_fkey", "foreign", ["data_source_id"], "data_sources", ["id"], "CASCADE"),
    ("data_source_logs", "data_source_logs_data_source_id_fkey", "foreign", ["data_source_id"], "data_sources", ["id"], "CASCADE"),
    ("service_alerts", "service_alerts_data_source_id_fkey", "foreign", ["data_source_id"], "data_sources", ["id"], "CASCADE"),
    ("service_alert_active_periods", "service_alert_active_periods_alert_id_fkey", "foreign", ["alert_id"], "service_alerts", ["id"], "CASCADE"),
    ("service_alert_informed_entities", "service_alert_informed_entities_alert_id_fkey", "foreign", ["alert_id"], "service_alerts", ["id"], "CASCADE"),
    ("service_alert_translations", "service_alert_translations_alert_id_fkey", "foreign", ["alert_id"], "service_alerts", ["id"], "CASCADE"),
]


NEW_CONSTRAINTS = [
    ("sys_app_settings", "pk_sys_app_stg", "primary", ["key"]),
    ("sys_users", "pk_sys_usr", "primary", ["id"]),
    ("sys_users", "uq_sys_usr_email", "unique", ["email"]),
    ("sys_users", "uq_sys_usr_username", "unique", ["username"]),
    ("sys_data_sources", "pk_sys_dt_src", "primary", ["id"]),
    ("sys_data_sources", "uq_sys_dt_src_name", "unique", ["name"]),
    (
        "sys_data_sources",
        "ck_sys_dt_src_inv_ref_plc",
        "check",
        "invalid_reference_policy IN ('discard_alert', 'keep_alert', 'discard_invalid', 'discard_invalid_elements', 'not_specified')",
    ),
    ("sys_data_source_mappings", "pk_sys_dt_src_mpg", "primary", ["id"]),
    ("sys_data_source_mappings", "fk_sys_dt_src_mpg_dt_src", "foreign", ["data_source_id"], "sys_data_sources", ["id"], "CASCADE"),
    ("sys_data_source_enrichments", "pk_sys_dt_src_enr", "primary", ["id"]),
    (
        "sys_data_source_enrichments",
        "ck_sys_dt_src_enr_enr_type",
        "check",
        "enrichment_type IN ('cause', 'effect', 'severity')",
    ),
    (
        "sys_data_source_enrichments",
        "ck_sys_dt_src_enr_src_fld",
        "check",
        "source_field IN ('header', 'description', 'header_description')",
    ),
    ("sys_data_source_enrichments", "fk_sys_dt_src_enr_dt_src", "foreign", ["data_source_id"], "sys_data_sources", ["id"], "CASCADE"),
    ("sys_data_source_logs", "pk_sys_dt_src_log", "primary", ["id"]),
    ("sys_data_source_logs", "fk_sys_dt_src_log_dt_src", "foreign", ["data_source_id"], "sys_data_sources", ["id"], "CASCADE"),
    ("realtime_service_alerts", "pk_rt_sv_al", "primary", ["id"]),
    ("realtime_service_alerts", "fk_rt_sv_al_dt_src", "foreign", ["data_source_id"], "sys_data_sources", ["id"], "CASCADE"),
    ("realtime_service_alert_active_periods", "pk_rt_sv_al_act_prd", "primary", ["id"]),
    (
        "realtime_service_alert_active_periods",
        "ck_rt_sv_al_act_prd_prd_type",
        "check",
        "period_type IN ('impact_period', 'communication_period')",
    ),
    ("realtime_service_alert_active_periods", "fk_rt_sv_al_act_prd_sv_al", "foreign", ["alert_id"], "realtime_service_alerts", ["id"], "CASCADE"),
    ("realtime_service_alert_informed_entities", "pk_rt_sv_al_inf_ent", "primary", ["id"]),
    ("realtime_service_alert_informed_entities", "fk_rt_sv_al_inf_ent_sv_al", "foreign", ["alert_id"], "realtime_service_alerts", ["id"], "CASCADE"),
    ("realtime_service_alert_translations", "pk_rt_sv_al_trn", "primary", ["id"]),
    ("realtime_service_alert_translations", "fk_rt_sv_al_trn_sv_al", "foreign", ["alert_id"], "realtime_service_alerts", ["id"], "CASCADE"),
]


OLD_REQUIRED_INDEXES = [
    ("ix_data_source_mappings_data_source_id", "data_source_mappings", ["data_source_id"]),
    ("ix_data_source_enrichments_data_source_id", "data_source_enrichments", ["data_source_id"]),
    ("ix_data_source_logs_data_source_id", "data_source_logs", ["data_source_id"]),
    ("ix_service_alert_active_periods_alert_id", "service_alert_active_periods", ["alert_id"]),
    ("ix_service_alert_informed_entities_alert_id", "service_alert_informed_entities", ["alert_id"]),
    ("ix_service_alert_translations_alert_id", "service_alert_translations", ["alert_id"]),
]


NEW_REQUIRED_INDEXES = [
    ("idx_sys_dt_src_mpg_data_source_id", "sys_data_source_mappings", ["data_source_id"]),
    ("idx_sys_dt_src_enr_data_source_id", "sys_data_source_enrichments", ["data_source_id"]),
    ("idx_sys_dt_src_log_data_source_id", "sys_data_source_logs", ["data_source_id"]),
    ("idx_rt_sv_al_act_prd_alert_id", "realtime_service_alert_active_periods", ["alert_id"]),
    ("idx_rt_sv_al_inf_ent_alert_id", "realtime_service_alert_informed_entities", ["alert_id"]),
    ("idx_rt_sv_al_trn_alert_id", "realtime_service_alert_translations", ["alert_id"]),
]


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name} CASCADE")


def _drop_constraints_by_type(table_name: str, constraint_types: tuple[str, ...]) -> None:
    types_sql = ", ".join(f"'{constraint_type}'" for constraint_type in constraint_types)
    op.execute(
        f"""
        DO $$
        DECLARE con record;
        BEGIN
            FOR con IN
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema()
                  AND t.relname = '{table_name}'
                  AND c.contype IN ({types_sql})
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I CASCADE',
                    '{table_name}',
                    con.conname
                );
            END LOOP;
        END $$;
        """
    )


def _drop_all_indexes_for_table(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        DECLARE idx record;
        BEGIN
            FOR idx IN
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = '{table_name}'
            LOOP
                EXECUTE format('DROP INDEX IF EXISTS %I', idx.indexname);
            END LOOP;
        END $$;
        """
    )


def _rename_sequence_if_exists(old_name: str, new_name: str) -> None:
    op.execute(f"ALTER SEQUENCE IF EXISTS {old_name} RENAME TO {new_name}")


def _create_constraint(definition: tuple) -> None:
    table_name = definition[0]
    constraint_name = definition[1]
    constraint_type = definition[2]

    if constraint_type == "primary":
        op.create_primary_key(constraint_name, table_name, definition[3])
        return

    if constraint_type == "unique":
        op.create_unique_constraint(constraint_name, table_name, definition[3])
        return

    if constraint_type == "check":
        op.create_check_constraint(constraint_name, table_name, definition[3])
        return

    if constraint_type == "foreign":
        op.create_foreign_key(
            constraint_name,
            table_name,
            definition[4],
            definition[3],
            definition[5],
            ondelete=definition[6],
        )
        return

    raise ValueError(f"Unsupported constraint type: {constraint_type}")


def upgrade() -> None:
    for old_name, _ in TABLE_RENAMES:
        _drop_constraints_by_type(old_name, DROP_CONSTRAINT_TYPES)
        _drop_all_indexes_for_table(old_name)

    op.execute("DROP TABLE IF EXISTS _migrations")

    for old_name, new_name in TABLE_RENAMES:
        op.rename_table(old_name, new_name)

    for old_name, new_name in SEQUENCE_RENAMES:
        _rename_sequence_if_exists(old_name, new_name)

    for constraint in NEW_CONSTRAINTS:
        _create_constraint(constraint)

    for index_name, table_name, columns in NEW_REQUIRED_INDEXES:
        op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    for index_name, table_name, _ in reversed(NEW_REQUIRED_INDEXES):
        op.drop_index(index_name, table_name=table_name)

    for _, current_name in TABLE_RENAMES:
        _drop_constraints_by_type(current_name, DROP_CONSTRAINT_TYPES)
        _drop_all_indexes_for_table(current_name)

    for new_name, old_name in reversed([(new_name, old_name) for old_name, new_name in SEQUENCE_RENAMES]):
        _rename_sequence_if_exists(new_name, old_name)

    for new_name, old_name in reversed([(new_name, old_name) for old_name, new_name in TABLE_RENAMES]):
        op.rename_table(new_name, old_name)

    for constraint in CREATE_OLD_CONSTRAINTS:
        _create_constraint(constraint)

    for index_name, table_name, columns in OLD_REQUIRED_INDEXES:
        op.create_index(index_name, table_name, columns, unique=False)
