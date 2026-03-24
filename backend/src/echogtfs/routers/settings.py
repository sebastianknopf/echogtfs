from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import get_db
from echogtfs.models import AppSetting
from echogtfs.schemas import ThemeSettings
from echogtfs.security import CurrentSuperuser

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]

# Keys stored in the database
_KEY_PRIMARY   = "color_primary"
_KEY_SECONDARY = "color_secondary"
_KEY_TITLE     = "app_title"

DEFAULTS = ThemeSettings(color_primary="#008c99", color_secondary="#99cc04", app_title="echogtfs")


async def _load(db: AsyncSession) -> ThemeSettings:
    result = await db.execute(select(AppSetting))
    rows = {row.key: row.value for row in result.scalars()}
    return ThemeSettings(
        color_primary  =rows.get(_KEY_PRIMARY,   DEFAULTS.color_primary),
        color_secondary=rows.get(_KEY_SECONDARY, DEFAULTS.color_secondary),
        app_title      =rows.get(_KEY_TITLE,     DEFAULTS.app_title),
    )


async def _upsert(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


@router.get("/", response_model=ThemeSettings)
async def get_settings(db: _DB) -> ThemeSettings:
    """Public: returns the current theme colours."""
    return await _load(db)


@router.put("/", response_model=ThemeSettings)
async def update_settings(
    payload: ThemeSettings, _: CurrentSuperuser, db: _DB
) -> ThemeSettings:
    """Admin only: persists theme colours."""
    await _upsert(db, _KEY_PRIMARY,   payload.color_primary)
    await _upsert(db, _KEY_SECONDARY, payload.color_secondary)
    await _upsert(db, _KEY_TITLE,     payload.app_title)
    await db.commit()
    return payload
