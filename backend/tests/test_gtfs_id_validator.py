from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

from echogtfs.services.realtimeprocessing.gtfs_id_validator import GtfsIdValidator


class TestGtfsIdValidator(unittest.IsolatedAsyncioTestCase):
    async def test_prefetch_checks_each_id_once_and_exposes_valid_ids(self):
        caching_service = SimpleNamespace(
            contains_gtfs_ids=AsyncMock(return_value={"r1"}),
            rebuild_gtfs_ids=AsyncMock(),
        )
        validator = GtfsIdValidator(caching_service, SimpleNamespace())

        await validator.prefetch("route", ["r1", "r2", None, "r1"])
        await validator.prefetch("route", ["r1", "r2"])

        caching_service.contains_gtfs_ids.assert_awaited_once_with("route", ["r1", "r2"])
        caching_service.rebuild_gtfs_ids.assert_not_awaited()
        self.assertEqual(validator.valid_ids()["route"], {"r1"})
        self.assertEqual(validator.valid_ids()["stop"], set())

    async def test_prefetch_rebuilds_cache_when_not_built_and_retries(self):
        caching_service = SimpleNamespace(
            contains_gtfs_ids=AsyncMock(side_effect=[None, {"s1"}]),
            rebuild_gtfs_ids=AsyncMock(),
        )
        gtfs_repository = SimpleNamespace()
        validator = GtfsIdValidator(caching_service, gtfs_repository)

        await validator.prefetch("stop", ["s1"])

        caching_service.rebuild_gtfs_ids.assert_awaited_once_with(gtfs_repository, force=False)
        self.assertEqual(validator.valid_ids()["stop"], {"s1"})

    async def test_prefetch_raises_when_cache_unavailable_after_rebuild(self):
        caching_service = SimpleNamespace(
            contains_gtfs_ids=AsyncMock(return_value=None),
            rebuild_gtfs_ids=AsyncMock(),
        )
        validator = GtfsIdValidator(caching_service, SimpleNamespace())

        with self.assertRaises(RuntimeError):
            await validator.prefetch("agency", ["a1"])

    async def test_prefetch_exposes_nominal_trips_in_valid_ids(self):
        caching_service = SimpleNamespace(contains_gtfs_ids=AsyncMock(return_value={"t1"}))
        validator = GtfsIdValidator(caching_service, SimpleNamespace())

        await validator.prefetch("trip", ["t1", "missing"])

        caching_service.contains_gtfs_ids.assert_awaited_once_with("trip", ["missing", "t1"])
        self.assertEqual(validator.valid_ids()["trip"], {"t1"})
