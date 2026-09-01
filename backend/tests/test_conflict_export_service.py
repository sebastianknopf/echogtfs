from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.conflict_export_service import ConflictExportService
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDatasourceGroupObject


class TestConflictExportService(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_trip(
        *,
        data_source_id: int,
        data_source_name: str,
        created_at: datetime,
        trip_id: str = "trip-1",
        route_id: str = "route-1",
        is_route_valid: bool = True,
        is_trip_valid: bool = True,
        scheduled_start_stop_id: str | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_end_time: datetime | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            data_source_id=data_source_id,
            data_source_name=data_source_name,
            created_at=created_at,
            trip_id=trip_id,
            route_id=route_id,
            is_route_valid=is_route_valid,
            is_trip_valid=is_trip_valid,
            scheduled_start_stop_id=scheduled_start_stop_id,
            scheduled_start_time=scheduled_start_time,
            scheduled_end_stop_id=scheduled_end_stop_id,
            scheduled_end_time=scheduled_end_time,
        )

    @staticmethod
    def _make_stop_event(
        *,
        trip: SimpleNamespace,
        trip_id: str,
        stop_id: str,
        stop_sequence: str | None = None,
        schedule_relationship: str = "SCHEDULED",
        original_stop_id: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            trip=trip,
            trip_id=trip_id,
            stop_id=stop_id,
            stop_sequence=stop_sequence,
            schedule_relationship=schedule_relationship,
            original_stop_id=original_stop_id,
        )

    @staticmethod
    def _make_service(*, system_failures=None, realtime_overrides=None):
        system_repository = SimpleNamespace(
            list_data_sources_with_failures=AsyncMock(return_value=system_failures or [])
        )

        realtime_defaults = {
            "list_stop_events_with_invalid_references": AsyncMock(return_value=[]),
            "list_trips_with_invalid_references": AsyncMock(return_value=[]),
            "list_stop_events_with_implied_deviation_schedule_relationships": AsyncMock(return_value=[]),
            "list_stop_events_with_changed_stop_id": AsyncMock(return_value=[]),
            "list_stop_events_with_non_global_ids": AsyncMock(return_value=[]),
            "list_trips_with_non_global_ids": AsyncMock(return_value=[]),
            "list_stop_events_with_departure_before_arrival": AsyncMock(return_value=[]),
        }

        if realtime_overrides:
            realtime_defaults.update(realtime_overrides)

        realtime_repository = SimpleNamespace(**realtime_defaults)
        return (
            ConflictExportService(system_repository=system_repository, realtime_repository=realtime_repository),
            system_repository,
            realtime_repository,
        )

    async def test_export_smoke_generates_conflicts_calls_dependencies_and_sorts_desc(self):
        t1 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 1, 10, 1, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 8, 1, 10, 2, 0, tzinfo=timezone.utc)
        t4 = datetime(2026, 8, 1, 10, 3, 0, tzinfo=timezone.utc)
        t5 = datetime(2026, 8, 1, 10, 4, 0, tzinfo=timezone.utc)
        t6 = datetime(2026, 8, 1, 10, 5, 0, tzinfo=timezone.utc)
        t7 = datetime(2026, 8, 1, 10, 6, 0, tzinfo=timezone.utc)

        ds = SimpleNamespace(
            id=10,
            name="ds-a",
            logs=[SimpleNamespace(timestamp=t1, status_code=500)],
        )

        trip_invalid_refs = self._make_trip(
            data_source_id=10,
            data_source_name="ds-a",
            created_at=t2,
            trip_id="trip-invalid",
            route_id="route-invalid",
            is_route_valid=False,
            is_trip_valid=False,
            scheduled_start_stop_id="start-stop",
            scheduled_start_time=t2,
            scheduled_end_stop_id="end-stop",
            scheduled_end_time=t3,
        )

        trip_for_events = self._make_trip(
            data_source_id=10,
            data_source_name="ds-a",
            created_at=t4,
            trip_id="trip-evt",
            route_id="route-evt",
        )

        non_global_trip = self._make_trip(
            data_source_id=10,
            data_source_name="ds-a",
            created_at=t6,
            trip_id="non-global-trip",
            route_id="non-global-route",
        )

        service, system_repository, realtime_repository = self._make_service(
            system_failures=[ds],
            realtime_overrides={
                "list_stop_events_with_invalid_references": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=trip_for_events,
                            trip_id=trip_for_events.trip_id,
                            stop_id="invalid-stop",
                            stop_sequence="5",
                        )
                    ]
                ),
                "list_trips_with_invalid_references": AsyncMock(return_value=[trip_invalid_refs]),
                "list_stop_events_with_implied_deviation_schedule_relationships": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=trip_for_events,
                            trip_id=trip_for_events.trip_id,
                            stop_id="stop-added",
                            stop_sequence="6",
                            schedule_relationship="ADDED",
                        ),
                        self._make_stop_event(
                            trip=trip_for_events,
                            trip_id=trip_for_events.trip_id,
                            stop_id="stop-skipped",
                            stop_sequence="7",
                            schedule_relationship="SKIPPED",
                        ),
                    ]
                ),
                "list_stop_events_with_changed_stop_id": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=trip_for_events,
                            trip_id=trip_for_events.trip_id,
                            stop_id="changed-stop",
                            stop_sequence="8",
                            original_stop_id="original-stop",
                        )
                    ]
                ),
                "list_stop_events_with_non_global_ids": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=trip_for_events,
                            trip_id=trip_for_events.trip_id,
                            stop_id="plain-stop-id",
                        )
                    ]
                ),
                "list_trips_with_non_global_ids": AsyncMock(return_value=[non_global_trip]),
                "list_stop_events_with_departure_before_arrival": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=self._make_trip(
                                data_source_id=10,
                                data_source_name="ds-a",
                                created_at=t7,
                                trip_id="trip-premature",
                                route_id="route-premature",
                            ),
                            trip_id="trip-premature",
                            stop_id="stop-premature",
                            stop_sequence="9",
                        )
                    ]
                ),
            },
        )

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ):
            conflicts = await service.export()

        self.assertEqual(len(conflicts), 11)

        timestamps = [conflict.timestamp for conflict in conflicts]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

        codes = {conflict.code for conflict in conflicts}
        self.assertIn(ConflictType.ERROR_DATASOURCE_FAILURE, codes)
        self.assertIn(ConflictType.ERROR_NO_STOP_FOUND, codes)
        self.assertIn(ConflictType.ERROR_NO_ROUTE_FOUND, codes)
        self.assertIn(ConflictType.ERROR_NO_TRIP_FOUND, codes)
        self.assertIn(ConflictType.WARNING_IMPLIED_ADDITIONAL_STOP, codes)
        self.assertIn(ConflictType.WARNING_IMPLIED_CANCELED_STOP, codes)
        self.assertIn(ConflictType.WARNING_WRONG_QUAY, codes)
        self.assertIn(ConflictType.WARNING_STOP_NO_GLOBAL_ID, codes)
        self.assertIn(ConflictType.WARNING_ROUTE_NO_GLOBAL_ID, codes)
        self.assertIn(ConflictType.WARNING_TRIP_NO_GLOBAL_ID, codes)
        self.assertIn(ConflictType.WARNING_PREMATURE_DEPARTURE, codes)

        system_repository.list_data_sources_with_failures.assert_awaited_once_with(min_num_failures=5)
        realtime_repository.list_stop_events_with_invalid_references.assert_awaited_once()
        realtime_repository.list_trips_with_invalid_references.assert_awaited_once()
        realtime_repository.list_stop_events_with_implied_deviation_schedule_relationships.assert_awaited_once()
        realtime_repository.list_stop_events_with_changed_stop_id.assert_awaited_once()
        realtime_repository.list_stop_events_with_non_global_ids.assert_awaited_once_with("^de:[a-z]+:[^\\s:]+$")
        realtime_repository.list_trips_with_non_global_ids.assert_awaited_once_with("^de:[a-z]+:[^\\s:]+$")
        realtime_repository.list_stop_events_with_departure_before_arrival.assert_awaited_once()

    async def test_export_with_filter_datasource_id_includes_only_matching_conflicts(self):
        t1 = datetime(2026, 8, 1, 11, 0, 0, tzinfo=timezone.utc)
        ds_10 = SimpleNamespace(id=10, name="ds-10", logs=[SimpleNamespace(timestamp=t1, status_code=500)])
        ds_20 = SimpleNamespace(id=20, name="ds-20", logs=[SimpleNamespace(timestamp=t1, status_code=503)])

        trip_10 = self._make_trip(
            data_source_id=10,
            data_source_name="ds-10",
            created_at=t1,
            trip_id="trip-10",
            route_id="route-10",
            is_route_valid=False,
            is_trip_valid=False,
        )
        trip_20 = self._make_trip(
            data_source_id=20,
            data_source_name="ds-20",
            created_at=t1,
            trip_id="trip-20",
            route_id="route-20",
            is_route_valid=False,
            is_trip_valid=False,
        )

        service, _, _ = self._make_service(
            system_failures=[ds_10, ds_20],
            realtime_overrides={
                "list_stop_events_with_invalid_references": AsyncMock(
                    return_value=[
                        self._make_stop_event(trip=trip_10, trip_id="trip-10", stop_id="stop-10"),
                        self._make_stop_event(trip=trip_20, trip_id="trip-20", stop_id="stop-20"),
                    ]
                ),
                "list_trips_with_invalid_references": AsyncMock(return_value=[trip_10, trip_20]),
            },
        )

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ):
            conflicts = await service.export(filter_datasource_id=10)

        self.assertGreaterEqual(len(conflicts), 1)
        self.assertTrue(all(conflict.datasource.id == 10 for conflict in conflicts))

    async def test_export_returns_empty_when_no_conflicts(self):
        service, _, _ = self._make_service(system_failures=[], realtime_overrides={})

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ):
            conflicts = await service.export()

        self.assertEqual(conflicts, [])

    async def test_export_non_global_stop_uses_stop_specific_conflict_type(self):
        t1 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        trip = self._make_trip(
            data_source_id=11,
            data_source_name="ds-11",
            created_at=t1,
            trip_id="trip-11",
            route_id="route-11",
        )

        service, _, _ = self._make_service(
            realtime_overrides={
                "list_stop_events_with_non_global_ids": AsyncMock(
                    return_value=[
                        self._make_stop_event(trip=trip, trip_id=trip.trip_id, stop_id="plain-stop")
                    ]
                )
            }
        )

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ):
            conflicts = await service.export()

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].code, ConflictType.WARNING_STOP_NO_GLOBAL_ID)
        self.assertEqual(conflicts[0].message, ConflictType.WARNING_STOP_NO_GLOBAL_ID.name)

    async def test_export_non_global_trip_skips_route_conflict_when_route_is_global(self):
        t1 = datetime(2026, 8, 1, 12, 30, 0, tzinfo=timezone.utc)
        trip = self._make_trip(
            data_source_id=12,
            data_source_name="ds-12",
            created_at=t1,
            trip_id="LOCAL-TRIP",
            route_id="GLOBAL-ROUTE",
        )

        service, _, _ = self._make_service(
            realtime_overrides={
                "list_trips_with_non_global_ids": AsyncMock(return_value=[trip])
            }
        )

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ), patch(
            "echogtfs.services.conflict.conflict_export_service.GlobalId.is_global_id",
            side_effect=lambda value: value == "GLOBAL-ROUTE",
        ):
            conflicts = await service.export()

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].code, ConflictType.WARNING_TRIP_NO_GLOBAL_ID)
        self.assertEqual(conflicts[0].properties.get("trip_id"), "LOCAL-TRIP")

    async def test_export_implied_deviation_ignores_unsupported_relationships(self):
        t1 = datetime(2026, 8, 1, 13, 0, 0, tzinfo=timezone.utc)
        trip = self._make_trip(
            data_source_id=13,
            data_source_name="ds-13",
            created_at=t1,
            trip_id="trip-13",
            route_id="route-13",
        )

        service, _, _ = self._make_service(
            realtime_overrides={
                "list_stop_events_with_implied_deviation_schedule_relationships": AsyncMock(
                    return_value=[
                        self._make_stop_event(
                            trip=trip,
                            trip_id=trip.trip_id,
                            stop_id="stop-unsupported",
                            stop_sequence="1",
                            schedule_relationship="SCHEDULED",
                        )
                    ]
                )
            }
        )

        with patch(
            "echogtfs.services.conflict.conflict_export_service.settings.global_id_pattern",
            "^de:[a-z]+:[^\\s:]+$",
        ):
            conflicts = await service.export()

        self.assertEqual(conflicts, [])

    def test_unique_conflict_id_is_order_independent(self):
        service, _, _ = self._make_service()

        cid_a = service._unique_conflict_id(datasource_id=1, stop_id="a", conflict_type=ConflictType.ERROR_NO_STOP_FOUND)
        cid_b = service._unique_conflict_id(stop_id="a", conflict_type=ConflictType.ERROR_NO_STOP_FOUND, datasource_id=1)

        self.assertEqual(cid_a, cid_b)

    def test_add_conflict_deduplicates_same_id(self):
        service, _, _ = self._make_service()
        timestamp = datetime(2026, 8, 1, 14, 0, 0, tzinfo=timezone.utc)

        conflict = MonitoringConflictObject(
            id="duplicate-id",
            timestamp=timestamp,
            code=ConflictType.ERROR_NO_STOP_FOUND,
            message=ConflictType.ERROR_NO_STOP_FOUND.name,
            datasource=MonitoringDatasourceGroupObject(id=1, name="source-1"),
            properties={"datasource_id": 1, "stop_id": "stop-1"},
        )

        existing_conflicts: list[MonitoringConflictObject] = []
        service._add_conflict(conflict, existing_conflicts)
        service._add_conflict(conflict, existing_conflicts)

        self.assertEqual(len(existing_conflicts), 1)
