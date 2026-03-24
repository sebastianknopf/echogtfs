from datetime import datetime
import re

from pydantic import BaseModel, EmailStr, field_validator

_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# App settings (theme + title)
# ---------------------------------------------------------------------------

class ThemeSettings(BaseModel):
    color_primary:   str = '#008c99'
    color_secondary: str = '#99cc04'
    app_title:       str = 'echogtfs'

    @field_validator('color_primary', 'color_secondary')
    @classmethod
    def must_be_hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError('Must be a 6-digit hex color, e.g. #008c99')
        return v.lower()

    @field_validator('app_title')
    @classmethod
    def clean_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('App title cannot be empty')
        return v[:80]


# ---------------------------------------------------------------------------
# GTFS
# ---------------------------------------------------------------------------

class GtfsFeedConfig(BaseModel):
    feed_url: str


class GtfsStatusRead(BaseModel):
    feed_url:    str
    status:      str        # idle | running | success | error
    imported_at: str | None
    message:     str | None


class AgencyRead(BaseModel):
    id:      int
    gtfs_id: str
    name:    str
    model_config = {"from_attributes": True}


class StopRead(BaseModel):
    id:      int
    gtfs_id: str
    name:    str
    model_config = {"from_attributes": True}


class RouteRead(BaseModel):
    id:         int
    gtfs_id:    str
    short_name: str
    long_name:  str
    model_config = {"from_attributes": True}
