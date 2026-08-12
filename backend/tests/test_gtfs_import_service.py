from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.gtfs.gtfs_import_service import GtfsImportService, _TripWindow


@contextmanager
def _temp_zip_file(data: bytes):
    """Write bytes to a temp .zip file and yield its path; tolerates prior deletion by the code under test."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)

    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


class TestGtfsImportService(unittest.IsolatedAsyncioTestCase):
    async def test_run_import_task_success_sets_status(self):
        repo = SimpleNamespace(set_app_setting=AsyncMock())
        gtfs_repo = SimpleNamespace(replace_gtfs_static_data=AsyncMock())
        service = GtfsImportService(repo, gtfs_repo)
        progress_reporter = SimpleNamespace(report_progress=AsyncMock())

        with patch.object(service, "_import_feed", AsyncMock(return_value={"agencies": 1, "stops": 2, "routes": 3})):
            await service.run_import_task(progress_reporter)

        self.assertTrue(repo.set_app_setting.await_count >= 5)

    def test_parse_map_helpers(self):
        csv_data = b"stop_id,stop_name,location_type\nS1,Main,0\nS2,,0\n"
        parsed = GtfsImportService._parse_csv(csv_data)
        stops = GtfsImportService._map_stops(parsed)
        self.assertEqual(stops, [{"gtfs_id": "S1", "name": "Main"}])

    def test_find_in_zip(self):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("folder/agency.txt", "agency_id,agency_name\nA,Agency\n")
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            payload = GtfsImportService._find_in_zip(zf, "agency.txt")

        self.assertIn(b"agency_name", payload)

    async def test_import_feed_raises_when_feed_url_missing(self):
        repo = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={}))
        gtfs_repo = SimpleNamespace(replace_gtfs_static_data=AsyncMock())
        service = GtfsImportService(repo, gtfs_repo)
        progress_reporter = SimpleNamespace(report_progress=AsyncMock())

        with self.assertRaises(ValueError):
            await service._import_feed(progress_reporter)

    def test_find_in_zip_raises_when_missing_file(self):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("folder/routes.txt", "route_id\nR1\n")
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            with self.assertRaises(KeyError):
                GtfsImportService._find_in_zip(zf, "agency.txt")

    def test_map_stop_time_row_updates_trip_window_and_uses_time_fallback(self):
        trip_windows: dict[str, object] = {}
        row = {
            "trip_id": "T1",
            "stop_id": "S1",
            "stop_sequence": "1",
            "arrival_time": "",
            "departure_time": "08:01:00",
        }

        mapped = GtfsImportService._map_stop_time_row(
            row,
            trip_meta={"T1": ("R1", 0)},
            stop_ids={"S1"},
            trip_windows=trip_windows,
            service_date=date(2026, 7, 20),
            feed_timezone=ZoneInfo("UTC"),
            target_timezone=ZoneInfo("UTC"),
        )

        self.assertIsNotNone(mapped)
        assert mapped is not None
        self.assertEqual(mapped["trip_id"], "T1")
        self.assertEqual(mapped["stop_id"], "S1")
        self.assertEqual(mapped["stop_sequence"], 1)
        self.assertEqual(mapped["arrival_time"], mapped["departure_time"])
        self.assertEqual(len(trip_windows), 1)

    def test_derive_trip_rows_uses_first_departure_and_last_arrival(self):
        start_departure = datetime(1970, 1, 1, 8, 5, 0, tzinfo=UTC)
        start_arrival = datetime(1970, 1, 1, 8, 4, 0, tzinfo=UTC)
        end_arrival = datetime(1970, 1, 1, 9, 0, 0, tzinfo=UTC)
        end_departure = datetime(1970, 1, 1, 9, 2, 0, tzinfo=UTC)

        trip_windows = {
            "T1": _TripWindow(
                first_sequence=1,
                first_stop_id="S1",
                first_arrival_time=start_arrival,
                first_departure_time=start_departure,
                last_sequence=5,
                last_stop_id="S5",
                last_arrival_time=end_arrival,
                last_departure_time=end_departure,
            )
        }

        trips = GtfsImportService._derive_trip_rows(
            {"T1": ("R1", 1)}, trip_windows, service_date=date(2026, 7, 20)
        )

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["gtfs_id"], "T1")
        self.assertEqual(trips[0]["route_id"], "R1")
        self.assertEqual(trips[0]["direction_id"], 1)
        self.assertEqual(trips[0]["start_stop_id"], "S1")
        self.assertEqual(trips[0]["end_stop_id"], "S5")
        self.assertEqual(trips[0]["start_time"], start_departure)
        self.assertEqual(trips[0]["end_time"], end_arrival)
        self.assertEqual(trips[0]["operation_day_date"], date(2026, 7, 20))

    def test_parse_gtfs_time_supports_values_beyond_24_hours(self):
        value = GtfsImportService._parse_gtfs_time(
            "25:10:05",
            service_date=date(2026, 7, 20),
            feed_timezone=ZoneInfo("UTC"),
            target_timezone=ZoneInfo("UTC"),
        )

        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value, datetime(2026, 7, 21, 1, 10, 5, tzinfo=UTC))

    def test_parse_gtfs_time_converts_feed_timezone_to_server_timezone(self):
        value = GtfsImportService._parse_gtfs_time(
            "08:00:00",
            service_date=date(2026, 7, 20),
            feed_timezone=ZoneInfo("Europe/Zurich"),
            target_timezone=ZoneInfo("UTC"),
        )

        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value, datetime(2026, 7, 20, 6, 0, 0, tzinfo=UTC))

    async def test_import_stop_times_uses_configured_timezone_for_conversion(self):
        repo = SimpleNamespace()
        gtfs_repo = SimpleNamespace(insert_gtfs_stop_times=AsyncMock())

        with patch("echogtfs.services.gtfs.gtfs_import_service.settings", SimpleNamespace(timezone="Europe/Berlin")):
            service = GtfsImportService(repo, gtfs_repo)

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr(
                "stop_times.txt",
                "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
                "T1,S1,1,08:00:00,08:05:00\n",
            )
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            batches = await service._map_stop_times(
                zf,
                trip_meta={"T1": ("R1", 0)},
                stop_ids={"S1"},
                trip_windows={},
                service_date=date(2026, 7, 20),
                feed_timezone=ZoneInfo("UTC"),
            )

        total = sum(len(batch) for batch in batches)
        self.assertEqual(total, 1)
        gtfs_repo.insert_gtfs_stop_times.assert_not_awaited()
        inserted_batch = batches[0]
        inserted = inserted_batch[0]
        self.assertEqual(inserted["arrival_time"], datetime(2026, 7, 20, 10, 0, 0, tzinfo=ZoneInfo("Europe/Berlin")))
        self.assertEqual(inserted["departure_time"], datetime(2026, 7, 20, 10, 5, 0, tzinfo=ZoneInfo("Europe/Berlin")))

    async def test_schedule_import_from_cron_uses_server_timezone(self):
        repo = SimpleNamespace(get_app_setting=AsyncMock(return_value="*/15 * * * *"))
        gtfs_repo = SimpleNamespace()

        class _FakeScheduler:
            def __init__(self) -> None:
                self.job: object | None = None

            def get_job(self, _job_id: str) -> object | None:
                return self.job

            def remove_job(self, _job_id: str) -> None:
                self.job = None

            def add_job(self, func, trigger, id, replace_existing) -> None:
                self.job = trigger

        with patch("echogtfs.services.gtfs.gtfs_import_service.settings", SimpleNamespace(timezone="Europe/Berlin")):
            service = GtfsImportService(repo, gtfs_repo)

        GtfsImportService._scheduler = _FakeScheduler()

        with patch(
            "echogtfs.services.gtfs.gtfs_import_service.CronTrigger.from_crontab",
            return_value="trigger",
        ) as from_crontab_mock:
            await service.schedule_from_settings()

        from_crontab_mock.assert_called_once()
        self.assertEqual(from_crontab_mock.call_args.kwargs["timezone"], ZoneInfo("Europe/Berlin"))

    # === operation_day_date / calendar handling ===

    def test_parse_gtfs_date_parses_valid_value(self):
        self.assertEqual(GtfsImportService._parse_gtfs_date("20260720"), date(2026, 7, 20))

    def test_parse_gtfs_date_returns_none_for_invalid_length(self):
        self.assertIsNone(GtfsImportService._parse_gtfs_date("2026-7-20"))

    def test_parse_gtfs_date_returns_none_for_invalid_value(self):
        self.assertIsNone(GtfsImportService._parse_gtfs_date("20261320"))

    def test_compute_valid_service_ids_includes_calendar_weekday_within_range(self):
        calendar_rows = [
            {
                "service_id": "SVC1",
                "monday": "1", "tuesday": "0", "wednesday": "0", "thursday": "0",
                "friday": "0", "saturday": "0", "sunday": "0",
                "start_date": "20260101", "end_date": "20261231",
            }
        ]

        service_ids = GtfsImportService._compute_valid_service_ids(
            calendar_rows, [], operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, {"SVC1"})

    def test_compute_valid_service_ids_excludes_wrong_weekday(self):
        calendar_rows = [
            {
                "service_id": "SVC1",
                "monday": "0", "tuesday": "0", "wednesday": "0", "thursday": "0",
                "friday": "0", "saturday": "0", "sunday": "1",
                "start_date": "20260101", "end_date": "20261231",
            }
        ]

        # 2026-07-20 is a Monday, calendar only allows Sunday
        service_ids = GtfsImportService._compute_valid_service_ids(
            calendar_rows, [], operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, set())

    def test_compute_valid_service_ids_excludes_dates_outside_range(self):
        calendar_rows = [
            {
                "service_id": "SVC1",
                "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1",
                "friday": "1", "saturday": "1", "sunday": "1",
                "start_date": "20260101", "end_date": "20260101",
            }
        ]

        service_ids = GtfsImportService._compute_valid_service_ids(
            calendar_rows, [], operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, set())

    def test_compute_valid_service_ids_adds_exception_type_1(self):
        calendar_dates_rows = [
            {"service_id": "SVC-EXTRA", "date": "20260720", "exception_type": "1"},
        ]

        service_ids = GtfsImportService._compute_valid_service_ids(
            [], calendar_dates_rows, operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, {"SVC-EXTRA"})

    def test_compute_valid_service_ids_removes_exception_type_2(self):
        calendar_rows = [
            {
                "service_id": "SVC1",
                "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1",
                "friday": "1", "saturday": "1", "sunday": "1",
                "start_date": "20260101", "end_date": "20261231",
            }
        ]
        calendar_dates_rows = [
            {"service_id": "SVC1", "date": "20260720", "exception_type": "2"},
        ]

        service_ids = GtfsImportService._compute_valid_service_ids(
            calendar_rows, calendar_dates_rows, operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, set())

    def test_compute_valid_service_ids_ignores_exceptions_for_other_dates(self):
        calendar_dates_rows = [
            {"service_id": "SVC-OTHER-DAY", "date": "20260721", "exception_type": "1"},
        ]

        service_ids = GtfsImportService._compute_valid_service_ids(
            [], calendar_dates_rows, operation_day=date(2026, 7, 20)
        )

        self.assertEqual(service_ids, set())

    def test_map_trips_filters_out_trips_with_invalid_service_id(self):
        rows = [
            {"trip_id": "T1", "route_id": "R1", "service_id": "SVC1", "direction_id": "0"},
            {"trip_id": "T2", "route_id": "R1", "service_id": "SVC-INVALID", "direction_id": "0"},
        ]

        trips = GtfsImportService._map_trips(rows, route_ids={"R1"}, valid_service_ids={"SVC1"})

        self.assertEqual(list(trips.keys()), ["T1"])

    def test_derive_trip_rows_includes_operation_day_date(self):
        window = _TripWindow(
            first_sequence=1,
            first_stop_id="S1",
            first_arrival_time=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            first_departure_time=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            last_sequence=2,
            last_stop_id="S2",
            last_arrival_time=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
            last_departure_time=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
        )

        trips = GtfsImportService._derive_trip_rows(
            {"T1": ("R1", 0)}, {"T1": window}, service_date=date(2026, 7, 20)
        )

        self.assertEqual(trips[0]["operation_day_date"], date(2026, 7, 20))

    def test_iter_csv_rows_optional_returns_empty_for_missing_file(self):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("routes.txt", "route_id\nR1\n")
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            rows = list(GtfsImportService._iter_csv_rows_optional(zf, "calendar.txt"))

        self.assertEqual(rows, [])

    @staticmethod
    def _build_gtfs_zip_bytes() -> bytes:
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("agency.txt", "agency_id,agency_name\nA,Agency\n")
            zf.writestr("stops.txt", "stop_id,stop_name,location_type\nS1,Stop1,0\nS2,Stop2,0\n")
            zf.writestr("routes.txt", "route_id,route_short_name,route_long_name\nR1,1,Route1\n")
            zf.writestr(
                "calendar.txt",
                "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                "SVC1,1,1,1,1,1,1,1,20251201,20260201\n",
            )
            zf.writestr("trips.txt", "trip_id,route_id,service_id,direction_id\nT1,R1,SVC1,0\n")
            zf.writestr(
                "stop_times.txt",
                "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
                "T1,S1,1,08:00:00,08:00:00\nT1,S2,2,08:10:00,08:10:00\n",
            )
        return mem.getvalue()

    async def test_import_feed_operation_day_respects_configured_timezone_at_midnight(self):
        """When no operation_day is given, 'today' must be derived in server timezone, not UTC."""
        repo = SimpleNamespace(
            get_all_app_settings=AsyncMock(
                return_value={"gtfs_feed_url": "https://example.com/feed.zip"}
            )
        )
        gtfs_repo = SimpleNamespace(
            clear_gtfs_static_data=AsyncMock(),
            insert_gtfs_agencies=AsyncMock(),
            insert_gtfs_routes=AsyncMock(),
            insert_gtfs_stops=AsyncMock(),
            insert_gtfs_trips=AsyncMock(),
            insert_gtfs_stop_times=AsyncMock(),
        )

        with patch("echogtfs.services.gtfs.gtfs_import_service.settings", SimpleNamespace(timezone="Europe/Berlin")):
            service = GtfsImportService(repo, gtfs_repo)

        # 23:30 UTC on Jan 1 is already 00:30 CET on Jan 2 in Berlin.
        fixed_utc_instant = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)

        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_utc_instant.astimezone(tz) if tz is not None else fixed_utc_instant

        zip_path = Path(self.enterContext(_temp_zip_file(self._build_gtfs_zip_bytes())))
        progress_reporter = SimpleNamespace(report_progress=AsyncMock())

        with (
            patch("echogtfs.services.gtfs.gtfs_import_service.datetime", _FixedDateTime),
            patch.object(service, "_download_gtfs_zip", AsyncMock(return_value=zip_path)),
        ):
            await service._import_feed(progress_reporter)

        inserted_trips = gtfs_repo.insert_gtfs_trips.await_args.args[0]
        self.assertEqual(len(inserted_trips), 1)
        self.assertEqual(inserted_trips[0]["operation_day_date"], date(2026, 1, 2))

    async def test_import_feed_uses_explicit_operation_day_over_current_time(self):
        repo = SimpleNamespace(
            get_all_app_settings=AsyncMock(
                return_value={"gtfs_feed_url": "https://example.com/feed.zip"}
            )
        )
        gtfs_repo = SimpleNamespace(
            clear_gtfs_static_data=AsyncMock(),
            insert_gtfs_agencies=AsyncMock(),
            insert_gtfs_routes=AsyncMock(),
            insert_gtfs_stops=AsyncMock(),
            insert_gtfs_trips=AsyncMock(),
            insert_gtfs_stop_times=AsyncMock(),
        )
        service = GtfsImportService(repo, gtfs_repo)

        zip_path = Path(self.enterContext(_temp_zip_file(self._build_gtfs_zip_bytes())))
        progress_reporter = SimpleNamespace(report_progress=AsyncMock())

        with patch.object(service, "_download_gtfs_zip", AsyncMock(return_value=zip_path)):
            await service._import_feed(progress_reporter, date(2026, 1, 5))

        inserted_trips = gtfs_repo.insert_gtfs_trips.await_args.args[0]
        self.assertEqual(len(inserted_trips), 1)
        self.assertEqual(inserted_trips[0]["operation_day_date"], date(2026, 1, 5))

    async def test_import_feed_excludes_trips_without_valid_service_id(self):
        repo = SimpleNamespace(
            get_all_app_settings=AsyncMock(
                return_value={"gtfs_feed_url": "https://example.com/feed.zip"}
            )
        )
        gtfs_repo = SimpleNamespace(
            clear_gtfs_static_data=AsyncMock(),
            insert_gtfs_agencies=AsyncMock(),
            insert_gtfs_routes=AsyncMock(),
            insert_gtfs_stops=AsyncMock(),
            insert_gtfs_trips=AsyncMock(),
            insert_gtfs_stop_times=AsyncMock(),
        )
        service = GtfsImportService(repo, gtfs_repo)

        zip_bytes = self._build_gtfs_zip_bytes()
        zip_path = Path(self.enterContext(_temp_zip_file(zip_bytes)))
        progress_reporter = SimpleNamespace(report_progress=AsyncMock())

        # Calendar only covers 2025-12-01..2026-02-01; requesting an operation day outside
        # that range must exclude all trips (negative case).
        with patch.object(service, "_download_gtfs_zip", AsyncMock(return_value=zip_path)):
            await service._import_feed(progress_reporter, date(2026, 6, 1))

        inserted_trips = gtfs_repo.insert_gtfs_trips.await_args.args[0]
        self.assertEqual(inserted_trips, [])