from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import get_db
from echogtfs.models import AppSetting
from echogtfs.schemas import AppSettings, ThemeSettings
from echogtfs.security import CurrentSuperuser, hash_password

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]

# Keys stored in the database
_KEY_PRIMARY       = "color_primary"
_KEY_SECONDARY     = "color_secondary"
_KEY_TITLE         = "app_title"
_KEY_LANGUAGE      = "app_language"
_KEY_GTFS_RT_PATH  = "gtfs_rt_path"
_KEY_GTFS_RT_USER  = "gtfs_rt_username"
_KEY_GTFS_RT_PASS  = "gtfs_rt_password"

DEFAULTS = AppSettings(
    color_primary="#008c99",
    color_secondary="#99cc04",
    app_title="echogtfs",
    app_language="de",
    gtfs_rt_path="realtime/service-alerts.pbf",
    gtfs_rt_username="",
    gtfs_rt_password="",
)


async def _load(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSetting))
    rows = {row.key: row.value for row in result.scalars()}
    
    # Initialize defaults in database if not present
    needs_commit = False
    if _KEY_GTFS_RT_PATH not in rows:
        await _upsert(db, _KEY_GTFS_RT_PATH, DEFAULTS.gtfs_rt_path)
        rows[_KEY_GTFS_RT_PATH] = DEFAULTS.gtfs_rt_path
        needs_commit = True
    if _KEY_GTFS_RT_USER not in rows:
        await _upsert(db, _KEY_GTFS_RT_USER, DEFAULTS.gtfs_rt_username)
        rows[_KEY_GTFS_RT_USER] = DEFAULTS.gtfs_rt_username
        needs_commit = True
    if _KEY_GTFS_RT_PASS not in rows:
        await _upsert(db, _KEY_GTFS_RT_PASS, DEFAULTS.gtfs_rt_password)
        rows[_KEY_GTFS_RT_PASS] = DEFAULTS.gtfs_rt_password
        needs_commit = True
    
    if needs_commit:
        await db.commit()
    
    return AppSettings(
        color_primary    = rows.get(_KEY_PRIMARY,      DEFAULTS.color_primary),
        color_secondary  = rows.get(_KEY_SECONDARY,    DEFAULTS.color_secondary),
        app_title        = rows.get(_KEY_TITLE,        DEFAULTS.app_title),
        app_language     = rows.get(_KEY_LANGUAGE,     DEFAULTS.app_language),
        gtfs_rt_path     = rows.get(_KEY_GTFS_RT_PATH, DEFAULTS.gtfs_rt_path),
        gtfs_rt_username = rows.get(_KEY_GTFS_RT_USER, DEFAULTS.gtfs_rt_username),
        gtfs_rt_password = rows.get(_KEY_GTFS_RT_PASS, DEFAULTS.gtfs_rt_password),
    )


async def _upsert(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


@router.get("/", response_model=AppSettings)
async def get_settings(db: _DB) -> AppSettings:
    """Public: returns the current app settings (theme + GTFS-RT config)."""
    return await _load(db)


@router.put("/", response_model=AppSettings)
async def update_settings(
    payload: AppSettings, _: CurrentSuperuser, db: _DB
) -> AppSettings:
    """Admin only: persists app settings."""
    await _upsert(db, _KEY_PRIMARY,      payload.color_primary)
    await _upsert(db, _KEY_SECONDARY,    payload.color_secondary)
    await _upsert(db, _KEY_TITLE,        payload.app_title)
    await _upsert(db, _KEY_LANGUAGE,     payload.app_language)
    await _upsert(db, _KEY_GTFS_RT_PATH, payload.gtfs_rt_path)
    
    # Basic Auth handling: Only clear both username and password if BOTH are empty/None
    # Otherwise, update individually
    username_is_empty = not payload.gtfs_rt_username
    password_is_empty = payload.gtfs_rt_password == "" or payload.gtfs_rt_password is None
    
    if username_is_empty and password_is_empty:
        # Both empty/None → disable Basic Auth completely
        await _upsert(db, _KEY_GTFS_RT_USER, "")
        await _upsert(db, _KEY_GTFS_RT_PASS, "")
    else:
        # Update username
        await _upsert(db, _KEY_GTFS_RT_USER, payload.gtfs_rt_username)
        
        # Update password only if explicitly provided (not None)
        if payload.gtfs_rt_password is not None:
            if payload.gtfs_rt_password:
                # Hash and store new password
                await _upsert(db, _KEY_GTFS_RT_PASS, hash_password(payload.gtfs_rt_password))
            else:
                # Empty string with username present → keep existing password unchanged
                pass
        # else: None means keep existing password
    
    await db.commit()
    
    # Return current settings (reload to get actual stored password status)
    return await _load(db)
