"""GTFS Static feed import service.

Downloads a GTFS Static ZIP from a configured URL, extracts agency.txt,
stops.txt and routes.txt, and upserts the entities into the database.

Import state is tracked via four AppSetting keys:
    gtfs_feed_url       – the feed URL (set via PUT /api/gtfs/feed-url)
    gtfs_import_status  – idle | running | success | error
    gtfs_import_time    – ISO-8601 timestamp of the last state change
    gtfs_import_message – human-readable result or error description
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import AsyncSessionLocal
from echogtfs.models import AppSetting, GtfsAgency, GtfsRoute, GtfsStop


# ---------------------------------------------------------------------------
# AppSetting keys
# ---------------------------------------------------------------------------

KEY_FEED_URL = "gtfs_feed_url"
KEY_STATUS   = "gtfs_import_status"
KEY_TIME     = "gtfs_import_time"
KEY_MSG      = "gtfs_import_message"

STATUS_IDLE    = "idle"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR   = "error"


# ---------------------------------------------------------------------------
# Data class returned by a successful import
# ---------------------------------------------------------------------------

@dataclass
class ImportResult:
    agencies: int
    stops:    int
    routes:   int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _upsert_setting(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await db.commit()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_csv(data: bytes) -> list[dict[str, str]]:
    """Parse a CSV byte string; handles UTF-8 BOM and strips whitespace."""
    text = data.decode("utf-8-sig")   # utf-8-sig silently strips BOM
    reader = csv.DictReader(io.StringIO(text))
    # Strip surrounding whitespace from both keys and values
    return [
        {k.strip(): (v.strip() if v else "") for k, v in row.items()}
        for row in reader
    ]


def _find_in_zip(
    zf: zipfile.ZipFile,
    filename: str,
) -> bytes:
    """Return raw bytes for *filename* inside *zf*, regardless of subdirectory depth."""
    target = filename.lower()
    for member in zf.namelist():
        if member.lower() == target or member.lower().endswith("/" + target):
            return zf.read(member)
    raise KeyError(f"'{filename}' not found in GTFS ZIP")


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

async def _do_import(db: AsyncSession) -> ImportResult:
    """Download, parse, and persist the GTFS feed. Raises on any error."""

    # 1. Read feed URL from settings
    row = await db.get(AppSetting, KEY_FEED_URL)
    if row is None or not row.value.strip():
        raise ValueError("Kein GTFS-Feed-URL konfiguriert.")
    feed_url = row.value.strip()

    # 2. Download ZIP (stream into memory; 300-second timeout covers large feeds)
    buffer = io.BytesIO()
    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        async with client.stream("GET", feed_url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(65_536):
                buffer.write(chunk)

    # 3. Parse ZIP
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as zf:
        agency_rows = _parse_csv(_find_in_zip(zf, "agency.txt"))
        stop_rows   = _parse_csv(_find_in_zip(zf, "stops.txt"))
        route_rows  = _parse_csv(_find_in_zip(zf, "routes.txt"))

    # 4. Build insert payloads (deduplicate by gtfs_id)
    agencies: dict[str, dict] = {}
    for r in agency_rows:
        gtfs_id = r.get("agency_id") or ""
        name    = r.get("agency_name") or ""
        if not name:
            continue
        # Single-agency feeds may omit agency_id; use name as key
        if not gtfs_id:
            gtfs_id = name
        agencies[gtfs_id] = {"gtfs_id": gtfs_id, "name": name}

    stops: dict[str, dict] = {}
    for r in stop_rows:
        gtfs_id = r.get("stop_id") or ""
        name    = r.get("stop_name") or ""
        if not gtfs_id or not name:
            continue
        stops[gtfs_id] = {"gtfs_id": gtfs_id, "name": name}

    routes: dict[str, dict] = {}
    for r in route_rows:
        gtfs_id    = r.get("route_id") or ""
        short_name = r.get("route_short_name") or ""
        long_name  = r.get("route_long_name") or ""
        if not gtfs_id:
            continue
        routes[gtfs_id] = {
            "gtfs_id":    gtfs_id,
            "short_name": short_name,
            "long_name":  long_name,
        }

    # 5. Atomic replace: truncate then bulk-insert
    await db.execute(delete(GtfsAgency))
    await db.execute(delete(GtfsStop))
    await db.execute(delete(GtfsRoute))

    agencies_list = list(agencies.values())
    stops_list    = list(stops.values())
    routes_list   = list(routes.values())

    if agencies_list:
        await db.execute(insert(GtfsAgency), agencies_list)
    if stops_list:
        await db.execute(insert(GtfsStop), stops_list)
    if routes_list:
        await db.execute(insert(GtfsRoute), routes_list)

    await db.commit()

    return ImportResult(
        agencies=len(agencies_list),
        stops=len(stops_list),
        routes=len(routes_list),
    )


# ---------------------------------------------------------------------------
# Background-task entry point (creates its own session)
# ---------------------------------------------------------------------------

async def run_import_task() -> None:
    """
    Called as an FastAPI BackgroundTask.
    Opens a dedicated DB session so the request session can be released first.
    Updates import status keys throughout.
    """
    async with AsyncSessionLocal() as db:
        await _upsert_setting(db, KEY_STATUS, STATUS_RUNNING)
        await _upsert_setting(db, KEY_TIME,   _now_iso())
        try:
            result = await _do_import(db)
            msg = (
                f"{result.agencies} Betreiber, "
                f"{result.stops} Haltestellen, "
                f"{result.routes} Linien importiert"
            )
            await _upsert_setting(db, KEY_STATUS, STATUS_SUCCESS)
            await _upsert_setting(db, KEY_MSG,    msg)
            await _upsert_setting(db, KEY_TIME,   _now_iso())
        except Exception as exc:  # noqa: BLE001
            await _upsert_setting(db, KEY_STATUS, STATUS_ERROR)
            await _upsert_setting(db, KEY_MSG,    str(exc))
            await _upsert_setting(db, KEY_TIME,   _now_iso())
