"""GTFS static feed import service implementation."""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.models import AppSetting
from echogtfs.services.gtfs.intf_gtfs_import import GtfsImportInterface

logger = logging.getLogger("uvicorn")


class GtfsImportService(GtfsImportInterface):
    """Service responsible for GTFS static feed import and scheduling."""

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    _scheduler: AsyncIOScheduler | None = None

    def __init__(self, repository: RepositoryInterface, gtfs_repository: GtfsRepositoryInterface):
        self._repository = repository
        self._gtfs_repository = gtfs_repository

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
                    CronTrigger.from_crontab(cron_expr),
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

            message = (
                f"{result['agencies']} agencies, "
                f"{result['stops']} stops, "
                f"{result['routes']} routes imported"
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

        buffer = io.BytesIO()
        async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
            async with client.stream("GET", feed_url) as response:
                response.raise_for_status()

                async for chunk in response.aiter_bytes(65_536):
                    buffer.write(chunk)

        buffer.seek(0)
        with zipfile.ZipFile(buffer) as zip_file:
            agency_rows = self._parse_csv(self._find_in_zip(zip_file, "agency.txt"))
            stop_rows = self._parse_csv(self._find_in_zip(zip_file, "stops.txt"))
            route_rows = self._parse_csv(self._find_in_zip(zip_file, "routes.txt"))

        agencies = self._map_agencies(agency_rows)
        stops = self._map_stops(stop_rows)
        routes = self._map_routes(route_rows)

        await self._gtfs_repository.replace_gtfs_static_data(
            agencies=agencies,
            stops=stops,
            routes=routes,
        )

        return {
            "agencies": len(agencies),
            "stops": len(stops),
            "routes": len(routes),
        }

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
    def _map_agencies(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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
    def _map_stops(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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
    def _map_routes(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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
