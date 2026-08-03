from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_gtfs_static_pk.py"


def load_migration_module(executed_statements: list[str]) -> types.ModuleType:
    original_alembic = sys.modules.get("alembic")
    original_alembic_op = sys.modules.get("alembic.op")
    fake_alembic = types.ModuleType("alembic")
    fake_op = types.SimpleNamespace(execute=executed_statements.append)
    fake_alembic.op = fake_op
    sys.modules["alembic"] = fake_alembic
    sys.modules["alembic.op"] = fake_op

    try:
        spec = importlib.util.spec_from_file_location("gtfs_static_pk_migration", MIGRATION_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if original_alembic is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = original_alembic

        if original_alembic_op is None:
            sys.modules.pop("alembic.op", None)
        else:
            sys.modules["alembic.op"] = original_alembic_op


class TestGtfsStaticPkMigration(unittest.TestCase):
    def test_upgrade_drops_foreign_keys_before_replacing_gtfs_stops_unique_constraint(self) -> None:
        executed_statements: list[str] = []
        module = load_migration_module(executed_statements)

        module.upgrade()

        self.assertEqual(
            executed_statements[:4],
            [
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_route_id_fkey",
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_start_stop_id_fkey",
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_end_stop_id_fkey",
                "ALTER TABLE gtfs_stop_times DROP CONSTRAINT IF EXISTS gtfs_stop_times_stop_id_fkey",
            ],
        )
        self.assertIn("ALTER TABLE gtfs_stops DROP CONSTRAINT IF EXISTS gtfs_stops_gtfs_id_key", executed_statements)
        self.assertLess(
            executed_statements.index("ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_route_id_fkey"),
            executed_statements.index("ALTER TABLE gtfs_stops DROP CONSTRAINT IF EXISTS gtfs_stops_gtfs_id_key"),
        )
        self.assertGreater(
            executed_statements.index("ALTER TABLE gtfs_trips ADD CONSTRAINT gtfs_trips_route_id_fkey FOREIGN KEY (route_id) REFERENCES gtfs_routes (gtfs_id)"),
            executed_statements.index("ALTER TABLE gtfs_routes DROP CONSTRAINT IF EXISTS gtfs_routes_gtfs_id_key"),
        )

    def test_downgrade_restores_foreign_keys_after_recreating_gtfs_stops_unique_constraint(self) -> None:
        executed_statements: list[str] = []
        module = load_migration_module(executed_statements)

        module.downgrade()

        self.assertEqual(
            executed_statements[:4],
            [
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_route_id_fkey",
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_start_stop_id_fkey",
                "ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_end_stop_id_fkey",
                "ALTER TABLE gtfs_stop_times DROP CONSTRAINT IF EXISTS gtfs_stop_times_stop_id_fkey",
            ],
        )
        self.assertGreater(
            executed_statements.index("ALTER TABLE gtfs_trips ADD CONSTRAINT gtfs_trips_route_id_fkey FOREIGN KEY (route_id) REFERENCES gtfs_routes (gtfs_id)"),
            executed_statements.index("ALTER TABLE gtfs_routes ADD CONSTRAINT gtfs_routes_gtfs_id_key UNIQUE (gtfs_id)"),
        )
        self.assertGreater(
            executed_statements.index("ALTER TABLE gtfs_stop_times ADD CONSTRAINT gtfs_stop_times_stop_id_fkey FOREIGN KEY (stop_id) REFERENCES gtfs_stops (gtfs_id)"),
            executed_statements.index("ALTER TABLE gtfs_stops ADD CONSTRAINT gtfs_stops_gtfs_id_key UNIQUE (gtfs_id)"),
        )
