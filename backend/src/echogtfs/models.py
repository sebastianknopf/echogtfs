from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from echogtfs.database import Base


# ---------------------------------------------------------------------------
# GTFS entity tables
# ---------------------------------------------------------------------------

class GtfsAgency(Base):
    """Imported GTFS agencies (agency.txt)."""
    __tablename__ = "gtfs_agencies"

    id:      Mapped[int] = mapped_column(primary_key=True)
    gtfs_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name:    Mapped[str] = mapped_column(String(255))


class GtfsStop(Base):
    """Imported GTFS stops (stops.txt)."""
    __tablename__ = "gtfs_stops"

    id:      Mapped[int] = mapped_column(primary_key=True)
    gtfs_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name:    Mapped[str] = mapped_column(String(255))


class GtfsRoute(Base):
    """Imported GTFS routes (routes.txt)."""
    __tablename__ = "gtfs_routes"

    id:         Mapped[int] = mapped_column(primary_key=True)
    gtfs_id:    Mapped[str] = mapped_column(String(128), unique=True, index=True)
    short_name: Mapped[str] = mapped_column(String(128))
    long_name:  Mapped[str] = mapped_column(String(255))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppSetting(Base):
    """Key-value store for application-wide settings persisted in the database."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(2048))  # wider for URLs + messages
