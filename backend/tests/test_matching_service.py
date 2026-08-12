from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.services.matching.matching_service import MatchingService


class TestMatchingService(unittest.IsolatedAsyncioTestCase):
    async def test_match_returns_cached_trip_id_without_querying_repository(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(
            get_trip_id=AsyncMock(return_value="CACHED-T42"),
            put_trip_id=AsyncMock(),
        )
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(result, "CACHED-T42")
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_route_id_missing(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id=None,
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_start_time_missing(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
        )

        self.assertIsNone(result)
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_unique_trip_id(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T42"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            scheduled_end_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            scheduled_start_stop_id="de:123:stopA:platform1",
            scheduled_end_stop_id="de:123:stopB:platform2",
        )

        self.assertEqual(result, "T42")
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(
            route_id="R1",
            operation_day_date=datetime(2026, 1, 1, 8, 0, tzinfo=UTC).date(),
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            scheduled_end_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            scheduled_start_stop_id="de:123:stopA",
            scheduled_end_stop_id="de:123:stopB",
        )
        caching_service.put_trip_id.assert_awaited_once_with("external-trip-1", "T42")

    async def test_match_returns_none_for_no_match(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=None))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_for_ambiguous_match(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1", "T2"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_uses_explicit_operation_day_date_over_start_time_date(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T42"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            operation_day_date=date(2026, 1, 2),
            scheduled_start_time=datetime(2026, 1, 1, 23, 55, tzinfo=UTC),
        )

        self.assertEqual(result, "T42")
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(
            route_id="R1",
            operation_day_date=date(2026, 1, 2),
            scheduled_start_time=datetime(2026, 1, 1, 23, 55, tzinfo=UTC),
            scheduled_end_time=None,
            scheduled_start_stop_id=None,
            scheduled_end_stop_id=None,
        )

    async def test_match_falls_back_to_start_time_date_when_operation_day_date_missing(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T42"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(
            repository.find_trip_ids_by_match_properties.await_args.kwargs["operation_day_date"],
            date(2026, 1, 1),
        )

    async def test_match_intermediate_fallback_uses_explicit_operation_day_date(self):
        matching_trip = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform1",
                    departure_time=datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC),
                )
            ]
        )
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]),
            get_gtfs_trip_with_stop_times=AsyncMock(return_value=matching_trip),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            operation_day_date=date(2026, 1, 1),
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                ("de:123:stopA:platformX", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC)),
            ],
        )

        self.assertEqual(result, "T1")
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(
            route_id="R1", operation_day_date=date(2026, 1, 1)
        )

    async def test_match_uses_intermediate_stop_fallback_when_start_and_end_are_missing(self):
        candidate_trip_a = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform99",
                    departure_time=datetime(2026, 1, 1, 8, 5, 30, tzinfo=UTC),
                ),
                SimpleNamespace(
                    stop_id="de:123:stopB:platform2",
                    departure_time=datetime(2026, 1, 1, 8, 11, 0, tzinfo=UTC),
                ),
            ]
        )
        candidate_trip_b = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform88",
                    departure_time=datetime(2026, 1, 1, 8, 7, 30, tzinfo=UTC),
                )
            ]
        )

        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=["T1", "T2"]),
            get_gtfs_trip_with_stop_times=AsyncMock(side_effect=[candidate_trip_a, candidate_trip_b]),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                ("de:123:stopA:platform1", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC)),
                ("de:123:stopB:platformX", datetime(2026, 1, 1, 8, 10, 0, tzinfo=UTC)),
            ],
        )

        self.assertEqual(result, "T1")
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(route_id="R1", operation_day_date=None)
        self.assertEqual(repository.get_gtfs_trip_with_stop_times.await_count, 2)
        caching_service.put_trip_id.assert_awaited_once_with("external-trip-1", "T1")

    async def test_match_does_not_use_intermediate_fallback_when_start_time_exists(self):
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=None),
            get_gtfs_trip_with_stop_times=AsyncMock(),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                ("de:123:stopA:platform1", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC))
            ],
        )

        self.assertIsNone(result)
        repository.find_trip_ids_by_match_properties.assert_awaited_once()
        repository.get_gtfs_trip_with_stop_times.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_does_not_use_intermediate_fallback_when_end_time_exists(self):
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(),
            get_gtfs_trip_with_stop_times=AsyncMock(),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            scheduled_intermediate_stops=[
                ("de:123:stopA:platform1", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC))
            ],
        )

        self.assertIsNone(result)
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        repository.get_gtfs_trip_with_stop_times.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_intermediate_fallback_is_ambiguous(self):
        matching_trip = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform1",
                    departure_time=datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC),
                )
            ]
        )
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=["T1", "T2"]),
            get_gtfs_trip_with_stop_times=AsyncMock(side_effect=[matching_trip, matching_trip]),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                ("de:123:stopA:platformX", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC))
            ],
        )

        self.assertIsNone(result)
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(route_id="R1", operation_day_date=None)
        self.assertEqual(repository.get_gtfs_trip_with_stop_times.await_count, 2)
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_intermediate_fallback_has_no_valid_inputs(self):
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(),
            get_gtfs_trip_with_stop_times=AsyncMock(),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                ("", datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC)),
                ("de:123:stopA:platformX", "2026-01-01T08:05:00Z"),
            ],
        )

        self.assertIsNone(result)
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        repository.get_gtfs_trip_with_stop_times.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_intermediate_fallback_respects_sixty_second_bias(self):
        matching_trip = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform1",
                    departure_time=datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC),
                )
            ]
        )
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]),
            get_gtfs_trip_with_stop_times=AsyncMock(return_value=matching_trip),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                (
                    "de:123:stopA:platformX",
                    datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC) + timedelta(seconds=60),
                )
            ],
        )

        self.assertEqual(result, "T1")
        caching_service.put_trip_id.assert_awaited_once_with("external-trip-1", "T1")

    async def test_match_intermediate_fallback_rejects_outside_sixty_second_bias(self):
        non_matching_trip = SimpleNamespace(
            stop_times=[
                SimpleNamespace(
                    stop_id="de:123:stopA:platform1",
                    departure_time=datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC),
                )
            ]
        )
        repository = SimpleNamespace(
            find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]),
            get_gtfs_trip_with_stop_times=AsyncMock(return_value=non_matching_trip),
        )
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_intermediate_stops=[
                (
                    "de:123:stopA:platformX",
                    datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC) + timedelta(seconds=61),
                )
            ],
        )

        self.assertIsNone(result)
        caching_service.put_trip_id.assert_not_awaited()
