from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy
from _realtimeprocessing_test_support import _SystemRepositoryStub, _RealtimeRepositoryStub, _GtfsRepositoryStub, make_processor
from echogtfs.services.realtimeprocessing.service_alert_processing_service import ServiceAlertProcessingService

class TestServiceAlertProcessingService(unittest.IsolatedAsyncioTestCase):
    async def test_sync_service_alert_records_applies_policy_and_upserts(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(ServiceAlertProcessingService, {})
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda e: e,
        )
        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 0,
            apply_enrichment=lambda _a, _b: None,
        )

        records = [
            {
                "id": "alert-1",
                "cause": "UNKNOWN_CAUSE",
                "effect": "UNKNOWN_EFFECT",
                "severity_level": "UNKNOWN_SEVERITY",
                "is_active": True,
                "translations": [],
                "active_periods": [],
                "informed_entities": [{"agency_id": "x", "route_id": None, "stop_id": None}],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()
        kwargs = realtime_repository.upsert_service_alert_from_sync.await_args.kwargs
        self.assertEqual(kwargs["alert_id"], "alert-1")
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertEqual(kwargs["informed_entities"], [])
    async def test_sync_service_alert_records_keeps_effect_for_closing_alert(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(ServiceAlertProcessingService, {})
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda e: e,
        )

        def _apply_enrichment(alert_data, _adapter_type):
            alert_data["cause"] = "ACCIDENT"
            alert_data["effect"] = "DETOUR"

        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 1,
            apply_enrichment=_apply_enrichment,
        )

        records = [
            {
                "id": "alert-1",
                "cause": "UNKNOWN_CAUSE",
                "effect": "UNKNOWN_EFFECT",
                "severity_level": "UNKNOWN_SEVERITY",
                "is_active": True,
                "is_closing_alert": True,
                "translations": [],
                "active_periods": [],
                "informed_entities": [{"agency_id": "a1", "route_id": None, "stop_id": None}],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()
        kwargs = realtime_repository.upsert_service_alert_from_sync.await_args.kwargs
        self.assertEqual(kwargs["cause"], "ACCIDENT")
        self.assertEqual(kwargs["effect"], "UNKNOWN_EFFECT")

    async def test_sync_service_alert_records_populates_original_and_mapped_ids(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(ServiceAlertProcessingService, {})

        def _apply_mapping(entity):
            mapped = dict(entity)
            if mapped.get("agency_id") == "x":
                mapped["agency_id"] = "a1"
            return mapped

        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 1,
            apply_mapping=_apply_mapping,
        )
        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 0,
            apply_enrichment=lambda _a, _b: None,
        )

        records = [
            {
                "id": "alert-1",
                "cause": "UNKNOWN_CAUSE",
                "effect": "UNKNOWN_EFFECT",
                "severity_level": "UNKNOWN_SEVERITY",
                "is_active": True,
                "translations": [],
                "active_periods": [],
                "informed_entities": [
                    {"agency_id": "x", "route_id": None, "stop_id": None, "trip_id": None}
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.upsert_service_alert_from_sync.await_args.kwargs
        entity = kwargs["informed_entities"][0]
        self.assertEqual(entity["agency_id"], "a1")
        self.assertEqual(entity["mapped_agency_id"], "a1")
        self.assertEqual(entity["original_agency_id"], "x")

    @staticmethod
    def _alert_processor():
        datasource = make_processor(ServiceAlertProcessingService, {})
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda e: e,
        )
        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 0,
            apply_enrichment=lambda _a, _b: None,
        )
        return datasource

    @staticmethod
    def _alert_record(alert_id, **overrides):
        record = {
            "id": alert_id,
            "cause": "UNKNOWN_CAUSE",
            "effect": "UNKNOWN_EFFECT",
            "severity_level": "UNKNOWN_SEVERITY",
            "is_active": True,
            "translations": [],
            "active_periods": [],
            "informed_entities": [{"agency_id": "a1", "route_id": None, "stop_id": None}],
        }
        record.update(overrides)
        return record

    async def _sync(self, datasource, realtime_repository, records):
        return await datasource.sync_records(
            repository=_SystemRepositoryStub(),
            realtime_repository=realtime_repository,
            gtfs_repository=_GtfsRepositoryStub(),
            source_id=2,
            source_name="Demo",
            records=records,
        )

    async def test_sync_service_alert_records_deletes_flagged_alert_by_id(self):
        realtime_repository = _RealtimeRepositoryStub()
        datasource = self._alert_processor()

        await self._sync(datasource, realtime_repository, [self._alert_record("alert-1", is_deleted=True)])

        realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_awaited_once_with(2, ["alert-1"])
        realtime_repository.upsert_service_alert_from_sync.assert_not_awaited()

    async def test_sync_service_alert_records_ignores_missing_flagged_alert(self):
        realtime_repository = _RealtimeRepositoryStub()
        realtime_repository.delete_service_alerts_for_data_source_by_ids = AsyncMock(return_value=0)
        datasource = self._alert_processor()

        result = await self._sync(
            datasource,
            realtime_repository,
            [
                self._alert_record("gone", is_deleted=True),
                self._alert_record("alert-2"),
            ],
        )

        realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_awaited_once_with(2, ["gone"])
        realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()
        self.assertEqual(
            realtime_repository.upsert_service_alert_from_sync.await_args.kwargs["alert_id"],
            "alert-2",
        )
        self.assertEqual(result["added"], 1)

    async def test_sync_service_alert_records_does_not_delete_unflagged_alerts(self):
        for overrides in ({}, {"is_deleted": False}):
            with self.subTest(overrides=overrides):
                realtime_repository = _RealtimeRepositoryStub()
                datasource = self._alert_processor()

                await self._sync(datasource, realtime_repository, [self._alert_record("alert-1", **overrides)])

                realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_not_awaited()
                realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()

    async def test_sync_service_alert_records_flagged_alert_does_not_require_payload(self):
        realtime_repository = _RealtimeRepositoryStub()
        datasource = self._alert_processor()

        await self._sync(datasource, realtime_repository, [{"id": "alert-1", "is_deleted": True}])

        realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_awaited_once_with(2, ["alert-1"])

    async def test_sync_service_alert_records_differential_keeps_untouched_alerts(self):
        for is_differential, expected_deletes in ((True, 0), (False, 1)):
            with self.subTest(is_differential=is_differential):
                realtime_repository = _RealtimeRepositoryStub()
                realtime_repository.list_service_alerts_for_data_source = AsyncMock(
                    return_value=[SimpleNamespace(id="old", data_source_id=2)]
                )
                datasource = self._alert_processor()
                repository = _SystemRepositoryStub()
                repository.get_data_source_is_differential_updates = AsyncMock(return_value=is_differential)

                result = await datasource.sync_records(
                    repository=repository,
                    realtime_repository=realtime_repository,
                    gtfs_repository=_GtfsRepositoryStub(),
                    source_id=2,
                    source_name="Demo",
                    records=[self._alert_record("new")],
                )

                self.assertEqual(result["deleted"], expected_deletes)

    async def test_sync_service_alert_records_flagged_alert_does_not_delete_others_in_differential_mode(self):
        realtime_repository = _RealtimeRepositoryStub()
        realtime_repository.list_service_alerts_for_data_source = AsyncMock(
            return_value=[SimpleNamespace(id="old", data_source_id=2)]
        )
        datasource = self._alert_processor()
        repository = _SystemRepositoryStub()
        repository.get_data_source_is_differential_updates = AsyncMock(return_value=True)

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=_GtfsRepositoryStub(),
            source_id=2,
            source_name="Demo",
            records=[{"id": "gone", "is_deleted": True}],
        )

        realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_awaited_once_with(2, ["gone"])

    async def test_sync_service_alert_records_flagged_alert_without_id_is_ignored(self):
        realtime_repository = _RealtimeRepositoryStub()
        datasource = self._alert_processor()

        await self._sync(datasource, realtime_repository, [{"is_deleted": True}])

        realtime_repository.delete_service_alerts_for_data_source_by_ids.assert_not_awaited()
        realtime_repository.upsert_service_alert_from_sync.assert_not_awaited()
