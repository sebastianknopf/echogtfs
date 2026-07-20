"""GTFS static feed import service implementation."""

from __future__ import annotations

import csv
import io
import logging
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.common.config import settings
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import AppSetting
from echogtfs.services.gtfs.intf_gtfs_import import GtfsImportInterface

logger = logging.getLogger("uvicorn")


@dataclass
class _TripWindow:
    first_sequence: int
    first_stop_id: str
    first_arrival_time: datetime | None
    first_departure_time: datetime | None
    last_sequence: int
    last_stop_id: str
    last_arrival_time: datetime | None
    last_departure_time: datetime | None


class GtfsImportService(GtfsImportInterface):
    """Service responsible for GTFS static feed import and scheduling."""

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STOP_TIME_BATCH_SIZE = 10_000

    _scheduler: AsyncIOScheduler | None = None

    def __init__(self, repository: SystemRepositoryInterface, gtfs_repository: GtfsRepositoryInterface):
        self._repository = repository
        self._gtfs_repository = gtfs_repository
        
        timezone_name = getattr(settings, "timezone", "UTC")
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            timezone_name = "UTC"
        
        self._server_timezone = self._resolve_timezone(timezone_name)

    @classmethod
    def _get_scheduler(cls) -> AsyncIOScheduler:
        if cls._scheduler is None:
            cls._scheduler = AsyncIOScheduler()
            cls._scheduler.start()
            
        return cls._scheduler

    async def _get_filtered_settings(self, keys: list[str]) -> dict[str, str | None]:
        all_settings = await self._repository.get_all_app_settings()

        return {key: all_settings.get(key) for key in keys}

    async def get_status(self) -> dict[str, str | None]:
        settings = await self._get_filtered_settings(
            [
                AppSetting.KEY_GTFS_FEED_URL,
                AppSetting.KEY_GTFS_CRON,
                AppSetting.KEY_GTFS_IMPORT_STATUS,
                AppSetting.KEY_GTFS_IMPORT_TIME,
                AppSetting.KEY_GTFS_IMPORT_MESSAGE,
            ]
        )

        feed_url = settings.get(AppSetting.KEY_GTFS_FEED_URL)
        cron = settings.get(AppSetting.KEY_GTFS_CRON)
        status_value = settings.get(AppSetting.KEY_GTFS_IMPORT_STATUS)
        imported_at = settings.get(AppSetting.KEY_GTFS_IMPORT_TIME)
        message = settings.get(AppSetting.KEY_GTFS_IMPORT_MESSAGE)

        return {
            "feed_url": feed_url or "",
            "cron": cron if cron not in (None, "") else None,
            "status": status_value or self.STATUS_IDLE,
            "imported_at": imported_at,
            "message": message,
        }

    async def is_import_running(self) -> bool:
        status_value = await self._repository.get_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS)

        return status_value == self.STATUS_RUNNING

    async def update_configuration(self, *, feed_url: str | None, cron: str | None) -> dict[str, str]:
        if feed_url:
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_FEED_URL, feed_url)

        if cron is not None:
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_CRON, cron)

        if cron is not None:
            await self.schedule_import_from_cron()

        return {
            "feed_url": feed_url or "",
            "cron": cron or "",
        }

    async def schedule_import_from_cron(self) -> None:
        cron_expr = await self._repository.get_app_setting(AppSetting.KEY_GTFS_CRON)
        scheduler = self._get_scheduler()

        job_id = "gtfs_import_cron"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("[GTFS] Scheduler: removed existing GTFS import job")

        if cron_expr:
            try:
                logger.info("[GTFS] Scheduler: setting new cron job: %s", cron_expr)

                scheduler.add_job(
                    self.run_import_task,
                    CronTrigger.from_crontab(cron_expr, timezone=self._server_timezone),
                    id=job_id,
                    replace_existing=True,
                )

                logger.info("[GTFS] Scheduler: cron job set successfully")
            except Exception as exc:  # noqa: BLE001
                logger.error("[GTFS] Invalid cron expression: %s (%s)", cron_expr, exc)

        else:
            logger.info("[GTFS] Scheduler: no cron expression set, no job scheduled")

    async def run_import_task(self) -> None:
        logger.info("[GTFS] Import task started")

        await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS, self.STATUS_RUNNING)
        await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_TIME, self._now_iso())

        try:
            result = await self._import_feed()
            agencies_count = int(result.get("agencies", 0))
            stops_count = int(result.get("stops", 0))
            routes_count = int(result.get("routes", 0))
            trips_count = int(result.get("trips", 0))
            stop_times_count = int(result.get("stop_times", 0))

            message = (
                f"{agencies_count} agencies, "
                f"{stops_count} stops, "
                f"{routes_count} routes, "
                f"{trips_count} trips, "
                f"{stop_times_count} stop_times imported"
            )

            logger.info("[GTFS] Import successful: %s", message)

            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS, self.STATUS_SUCCESS)
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_MESSAGE, message)
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_TIME, self._now_iso())
        except Exception as exc:  # noqa: BLE001
            logger.error("[GTFS] Import error: %s", exc)

            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS, self.STATUS_ERROR)
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_MESSAGE, str(exc))
            await self._repository.set_app_setting(AppSetting.KEY_GTFS_IMPORT_TIME, self._now_iso())

    async def _import_feed(self) -> dict[str, int]:
        settings = await self._get_filtered_settings([AppSetting.KEY_GTFS_FEED_URL])
        feed_url = (settings.get(AppSetting.KEY_GTFS_FEED_URL) or "").strip()

        if not feed_url:
            raise ValueError("No GTFS feed URL configured")

        zip_path = await self._download_gtfs_zip(feed_url)

        try:
            with zipfile.ZipFile(zip_path) as zip_file:
                agency_rows = list(self._iter_csv_rows(zip_file, "agency.txt"))
                agencies = self._map_agencies(agency_rows)
                feed_timezone = self._extract_feed_timezone(agency_rows)
                service_date = datetime.now(feed_timezone).date()
                stops = self._map_stops(self._iter_csv_rows(zip_file, "stops.txt"))
                routes = self._map_routes(self._iter_csv_rows(zip_file, "routes.txt"))

                stop_ids = {row["gtfs_id"] for row in stops}
                route_ids = {row["gtfs_id"] for row in routes}

                trip_meta = self._map_trips(
                    self._iter_csv_rows(zip_file, "trips.txt"),
                    route_ids=route_ids,
                )

                trip_windows: dict[str, _TripWindow] = {}
                await self._import_stop_times(
                    zip_file,
                    trip_meta=trip_meta,
                    stop_ids=stop_ids,
                    trip_windows=trip_windows,
                    persist=False,
                    service_date=service_date,
                    feed_timezone=feed_timezone,
                )

                trip_rows = self._derive_trip_rows(trip_meta, trip_windows)

            await self._gtfs_repository.clear_gtfs_static_data()
            await self._gtfs_repository.insert_gtfs_agencies(agencies)
            await self._gtfs_repository.insert_gtfs_stops(stops)
            await self._gtfs_repository.insert_gtfs_routes(routes)
            await self._gtfs_repository.insert_gtfs_trips(trip_rows)

            with zipfile.ZipFile(zip_path) as zip_file:
                stop_time_count = await self._import_stop_times(
                    zip_file,
                    trip_meta=trip_meta,
                    stop_ids=stop_ids,
                    trip_windows={},
                    persist=True,
                    service_date=service_date,
                    feed_timezone=feed_timezone,
                )

            return {
                "agencies": len(agencies),
                "stops": len(stops),
                "routes": len(routes),
                "trips": len(trip_rows),
                "stop_times": stop_time_count,
            }
        
        finally:
            zip_path.unlink(missing_ok=True)

    async def _download_gtfs_zip(self, feed_url: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = Path(tmp.name)

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                async with client.stream("GET", feed_url) as response:
                    response.raise_for_status()

                    with zip_path.open("wb") as out_stream:
                        async for chunk in response.aiter_bytes(65_536):
                            out_stream.write(chunk)
        except Exception:
            zip_path.unlink(missing_ok=True)
            raise

        return zip_path

    @staticmethod
    def _iter_csv_rows(zip_file: zipfile.ZipFile, filename: str) -> Iterator[dict[str, str]]:
        target = filename.lower()

        for member in zip_file.namelist():
            lower_member = member.lower()
            if lower_member == target or lower_member.endswith("/" + target):
                with zip_file.open(member) as payload:
                    with io.TextIOWrapper(payload, encoding="utf-8-sig", newline="") as text_payload:
                        reader = csv.DictReader(text_payload)
                        
                        for row in reader:
                            cleaned_row: dict[str, str] = {}
                            for key, value in row.items():
                                if key is None:
                                    continue
                                cleaned_row[key.strip()] = (value.strip() if value else "")
                            
                            yield cleaned_row
                return

        raise KeyError(f"'{filename}' not found in GTFS ZIP")

    @staticmethod
    def _map_trips(
        rows: Iterable[dict[str, str]],
        *,
        route_ids: set[str],
    ) -> dict[str, tuple[str, int]]:
        trips: dict[str, tuple[str, int]] = {}

        for row in rows:
            trip_id = row.get("trip_id") or ""
            route_id = row.get("route_id") or ""

            if not trip_id or not route_id or route_id not in route_ids:
                continue

            direction_raw = row.get("direction_id") or "0"
            direction_id = GtfsImportService._parse_int(direction_raw)
            
            if direction_id is None:
                continue

            trips[trip_id] = (route_id, direction_id)

        return trips

    async def _import_stop_times(
        self,
        zip_file: zipfile.ZipFile,
        *,
        trip_meta: dict[str, tuple[str, int]],
        stop_ids: set[str],
        trip_windows: dict[str, _TripWindow],
        persist: bool,
        service_date: date,
        feed_timezone: ZoneInfo,
    ) -> int:
        batch: list[dict[str, str | int | datetime]] = []
        total = 0

        for row in self._iter_csv_rows(zip_file, "stop_times.txt"):
            stop_time_row = self._map_stop_time_row(
                row,
                trip_meta=trip_meta,
                stop_ids=stop_ids,
                trip_windows=trip_windows,
                service_date=service_date,
                feed_timezone=feed_timezone,
                target_timezone=self._server_timezone,
            )
            
            if stop_time_row is None:
                continue

            batch.append(stop_time_row)
            if len(batch) >= self.STOP_TIME_BATCH_SIZE:
                
                if persist:
                    await self._gtfs_repository.insert_gtfs_stop_times(batch)
                
                total += len(batch)
                batch = []

        if batch:
            if persist:
                await self._gtfs_repository.insert_gtfs_stop_times(batch)
            
            total += len(batch)

        return total

    @staticmethod
    def _map_stop_time_row(
        row: dict[str, str],
        *,
        trip_meta: dict[str, tuple[str, int]],
        stop_ids: set[str],
        trip_windows: dict[str, _TripWindow],
        service_date: date,
        feed_timezone: ZoneInfo,
        target_timezone: ZoneInfo,
    ) -> dict[str, str | int | datetime] | None:
        trip_id = row.get("trip_id") or ""
        stop_id = row.get("stop_id") or ""

        if not trip_id or trip_id not in trip_meta or not stop_id or stop_id not in stop_ids:
            return None

        stop_sequence = GtfsImportService._parse_int(row.get("stop_sequence") or "")
        if stop_sequence is None:
            return None

        arrival_time_raw = row.get("arrival_time") or ""
        departure_time_raw = row.get("departure_time") or ""

        arrival_time = GtfsImportService._parse_gtfs_time(
            arrival_time_raw,
            service_date=service_date,
            feed_timezone=feed_timezone,
            target_timezone=target_timezone,
        )
        departure_time = GtfsImportService._parse_gtfs_time(
            departure_time_raw,
            service_date=service_date,
            feed_timezone=feed_timezone,
            target_timezone=target_timezone,
        )

        if arrival_time is None and departure_time is None:
            return None

        fallback_arrival = arrival_time or departure_time
        fallback_departure = departure_time or arrival_time
        if fallback_arrival is None or fallback_departure is None:
            return None

        GtfsImportService._update_trip_window(
            trip_windows,
            trip_id=trip_id,
            stop_sequence=stop_sequence,
            stop_id=stop_id,
            arrival_time=arrival_time,
            departure_time=departure_time,
        )

        return {
            "trip_id": trip_id,
            "stop_id": stop_id,
            "stop_sequence": stop_sequence,
            "arrival_time": fallback_arrival,
            "departure_time": fallback_departure,
        }

    @staticmethod
    def _update_trip_window(
        trip_windows: dict[str, _TripWindow],
        *,
        trip_id: str,
        stop_sequence: int,
        stop_id: str,
        arrival_time: datetime | None,
        departure_time: datetime | None,
    ) -> None:
        window = trip_windows.get(trip_id)
        if window is None:
            trip_windows[trip_id] = _TripWindow(
                first_sequence=stop_sequence,
                first_stop_id=stop_id,
                first_arrival_time=arrival_time,
                first_departure_time=departure_time,
                last_sequence=stop_sequence,
                last_stop_id=stop_id,
                last_arrival_time=arrival_time,
                last_departure_time=departure_time,
            )
            
            return

        if stop_sequence < window.first_sequence:
            window.first_sequence = stop_sequence
            window.first_stop_id = stop_id
            window.first_arrival_time = arrival_time
            window.first_departure_time = departure_time

        if stop_sequence > window.last_sequence:
            window.last_sequence = stop_sequence
            window.last_stop_id = stop_id
            window.last_arrival_time = arrival_time
            window.last_departure_time = departure_time

    @staticmethod
    def _derive_trip_rows(
        trip_meta: dict[str, tuple[str, int]],
        trip_windows: dict[str, _TripWindow],
    ) -> list[dict[str, str | int | datetime]]:
        trips: list[dict[str, str | int | datetime]] = []

        for trip_id, (route_id, direction_id) in trip_meta.items():
            window = trip_windows.get(trip_id)
            if window is None:
                continue

            start_time = window.first_departure_time or window.first_arrival_time
            end_time = window.last_arrival_time or window.last_departure_time
            if start_time is None or end_time is None:
                continue

            trips.append(
                {
                    "gtfs_id": trip_id,
                    "route_id": route_id,
                    "direction_id": direction_id,
                    "start_time": start_time,
                    "start_stop_id": window.first_stop_id,
                    "end_time": end_time,
                    "end_stop_id": window.last_stop_id,
                }
            )

        return trips

    @staticmethod
    def _parse_int(value: str) -> int | None:
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_gtfs_time(
        value: str,
        *,
        service_date: date,
        feed_timezone: ZoneInfo,
        target_timezone: ZoneInfo,
    ) -> datetime | None:
        if not value:
            return None

        parts = value.split(":")
        if len(parts) != 3:
            return None

        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        except ValueError:
            return None

        if minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59 or hours < 0:
            return None

        base = datetime.combine(service_date, datetime.min.time(), tzinfo=feed_timezone)
        feed_timestamp = base + timedelta(hours=hours, minutes=minutes, seconds=seconds)
        return feed_timestamp.astimezone(target_timezone)

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("[GTFS] Unknown TIMEZONE '%s'. Falling back to UTC", timezone_name)
            return ZoneInfo("UTC")

    def _extract_feed_timezone(self, agency_rows: Iterable[dict[str, str]]) -> ZoneInfo:
        for row in agency_rows:
            timezone_name = (
                row.get("agency_timezone")
                or row.get("agency.timezone")
                or row.get("timezone")
                or ""
            ).strip()

            if timezone_name:
                return self._resolve_timezone(timezone_name)

        return self._server_timezone

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _parse_csv(data: bytes) -> list[dict[str, str]]:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        return [
            {key.strip(): (value.strip() if value else "") for key, value in row.items()}
            for row in reader
        ]

    @staticmethod
    def _find_in_zip(zip_file: zipfile.ZipFile, filename: str) -> bytes:
        target = filename.lower()

        for member in zip_file.namelist():
            lower_member = member.lower()
            if lower_member == target or lower_member.endswith("/" + target):
                return zip_file.read(member)
            
        raise KeyError(f"'{filename}' not found in GTFS ZIP")

    @staticmethod
    def _map_agencies(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        agencies: dict[str, dict[str, str]] = {}
        
        for row in rows:
            gtfs_id = row.get("agency_id") or ""
            name = row.get("agency_name") or ""

            if not name:
                continue

            if not gtfs_id:
                gtfs_id = name

            agencies[gtfs_id] = {"gtfs_id": gtfs_id, "name": name}

        return list(agencies.values())

    @staticmethod
    def _map_stops(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        stops: dict[str, dict[str, str]] = {}
        
        for row in rows:
            gtfs_id = row.get("stop_id") or ""
            name = row.get("stop_name") or ""
            location_type = row.get("location_type") or ""

            if not gtfs_id or not name:
                continue

            if location_type and location_type not in ("0", "1"):
                continue

            stops[gtfs_id] = {"gtfs_id": gtfs_id, "name": name}

        return list(stops.values())

    @staticmethod
    def _map_routes(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        routes: dict[str, dict[str, str]] = {}
        
        for row in rows:
            gtfs_id = row.get("route_id") or ""
            short_name = row.get("route_short_name") or ""
            long_name = row.get("route_long_name") or ""
            if not gtfs_id:
                continue

            routes[gtfs_id] = {
                "gtfs_id": gtfs_id,
                "short_name": short_name,
                "long_name": long_name,
            }
            
        return list(routes.values())
