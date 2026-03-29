from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    is_technical_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppSetting(Base):
    """Key-value store for application-wide settings persisted in the database."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(2048))  # wider for URLs + messages


# ---------------------------------------------------------------------------
# GTFS-RT ServiceAlert enums
# ---------------------------------------------------------------------------

class AlertCause(str, Enum):
    """GTFS-RT Alert cause enum."""
    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"
    OTHER_CAUSE = "OTHER_CAUSE"
    TECHNICAL_PROBLEM = "TECHNICAL_PROBLEM"
    STRIKE = "STRIKE"
    DEMONSTRATION = "DEMONSTRATION"
    ACCIDENT = "ACCIDENT"
    HOLIDAY = "HOLIDAY"
    WEATHER = "WEATHER"
    MAINTENANCE = "MAINTENANCE"
    CONSTRUCTION = "CONSTRUCTION"
    POLICE_ACTIVITY = "POLICE_ACTIVITY"
    MEDICAL_EMERGENCY = "MEDICAL_EMERGENCY"


class SiriLiteDialect(str, Enum):
    """SIRI-Lite dialect variants for different regional implementations."""
    SWISS = "swiss"
    NORDIC = "nordic"
    FRANCE = "france"


class AlertEffect(str, Enum):
    """GTFS-RT Alert effect enum."""
    NO_SERVICE = "NO_SERVICE"
    REDUCED_SERVICE = "REDUCED_SERVICE"
    SIGNIFICANT_DELAYS = "SIGNIFICANT_DELAYS"
    DETOUR = "DETOUR"
    ADDITIONAL_SERVICE = "ADDITIONAL_SERVICE"
    MODIFIED_SERVICE = "MODIFIED_SERVICE"
    OTHER_EFFECT = "OTHER_EFFECT"
    UNKNOWN_EFFECT = "UNKNOWN_EFFECT"
    STOP_MOVED = "STOP_MOVED"
    NO_EFFECT = "NO_EFFECT"
    ACCESSIBILITY_ISSUE = "ACCESSIBILITY_ISSUE"


class AlertSeverityLevel(str, Enum):
    """GTFS-RT Alert severity level enum (SeverityLevel)."""
    UNKNOWN_SEVERITY = "UNKNOWN_SEVERITY"
    INFO = "INFO"
    WARNING = "WARNING"
    SEVERE = "SEVERE"


# ---------------------------------------------------------------------------
# GTFS-RT ServiceAlert tables
# ---------------------------------------------------------------------------

class ServiceAlert(Base):
    """
    GTFS-RT Service Alert.
    
    Main table for service alerts. Translations and affected entities
    are stored in separate tables with foreign keys.
    
    No foreign keys to GTFS static data - entity references are stored
    as strings only for search purposes.
    
    Alerts can be internal (created in echogtfs UI) or external (imported
    from data sources). External alerts have a data_source_id and cannot
    be edited in the UI.
    """
    __tablename__ = "service_alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    
    # Data source relation (NULL = internal alert, created in echogtfs UI)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    # Alert metadata
    cause: Mapped[AlertCause] = mapped_column(String(32), default=AlertCause.UNKNOWN_CAUSE)
    effect: Mapped[AlertEffect] = mapped_column(String(32), default=AlertEffect.UNKNOWN_EFFECT)
    severity_level: Mapped[AlertSeverityLevel] = mapped_column(
        String(32), default=AlertSeverityLevel.UNKNOWN_SEVERITY
    )
    source: Mapped[str] = mapped_column(String(128), default="echogtfs", index=True)
    
    # Status flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationships (with cascade delete)
    data_source: Mapped["DataSource | None"] = relationship(back_populates="alerts")
    translations: Mapped[list["ServiceAlertTranslation"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    active_periods: Mapped[list["ServiceAlertActivePeriod"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    informed_entities: Mapped[list["ServiceAlertInformedEntity"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    
    @property
    def data_source_name(self) -> str | None:
        """Return the name of the data source if this is an external alert."""
        return self.data_source.name if self.data_source else None



class ServiceAlertTranslation(Base):
    """
    Translations for service alert text content.
    
    Stores header, description, and URL in multiple languages.
    One alert can have multiple translations.
    """
    __tablename__ = "service_alert_translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # Language code (ISO 639-1: 'de', 'en', 'fr', etc.)
    language: Mapped[str] = mapped_column(String(8), index=True)
    
    # Alert content in this language
    header_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    
    # Relationship
    alert: Mapped["ServiceAlert"] = relationship(back_populates="translations")


class ServiceAlertActivePeriod(Base):
    """
    Time period during which an alert is active.
    
    An alert can have multiple active periods (e.g., same disruption
    on multiple days). If no periods are defined, the alert is always active.
    """
    __tablename__ = "service_alert_active_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # Unix timestamps (seconds since epoch)
    # If start is None, active from beginning of time
    # If end is None, active until end of time
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    end_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    
    # Relationship
    alert: Mapped["ServiceAlert"] = relationship(back_populates="active_periods")


class ServiceAlertInformedEntity(Base):
    """
    Entity (route, stop, trip, etc.) that is affected by an alert.
    
    References GTFS entities by their IDs (strings), but does NOT use
    foreign keys to GTFS static tables. This allows alerts to reference
    entities that may not be in the database or may change over time.
    
    Multiple fields can be set to narrow down the affected entity:
    - route_id only: entire route affected
    - route_id + stop_id: specific stop on a route
    - trip_id: specific trip affected
    - stop_id only: entire stop affected
    """
    __tablename__ = "service_alert_informed_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # GTFS entity references (NO FOREIGN KEYS - just string IDs for search)
    agency_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    route_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    route_type: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    stop_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    trip_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    
    # Optional direction filter (0 or 1)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Relationship
    alert: Mapped["ServiceAlert"] = relationship(back_populates="informed_entities")


# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

class DataSource(Base):
    """
    External data source configuration.
    
    Each data source has a type that determines how it should be processed.
    Type-specific configuration is stored as JSON string in the config field.
    Mappings define how GTFS entities map to external data source values.
    """
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    
    # Type-specific configuration stored as JSON string
    config: Mapped[str] = mapped_column(Text, default="{}")
    
    # Optional cron expression for automatic updates
    cron: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Active status - inactive sources don't run and their alerts are deleted
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Last execution timestamp
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationships (with cascade delete)
    mappings: Mapped[list["DataSourceMapping"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["ServiceAlert"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )


class DataSourceMapping(Base):
    """
    Mapping between GTFS entities and external data source values.
    
    Maps external data source keys to GTFS entity IDs. The value field
    contains the GTFS entity ID (agency_id, route_id, stop_id, etc.).
    
    No foreign keys to GTFS static tables - entity references are stored
    as strings to allow flexibility and to avoid breaking when GTFS data changes.
    """
    __tablename__ = "data_source_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), index=True)
    
    # GTFS entity type: "agency", "route", "stop", "trip", etc.
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    
    # Mapping key-value pair
    # Key: external identifier from data source
    # Value: GTFS entity ID (the ID field, not a separate entity_id column)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[str] = mapped_column(String(512), index=True)
    
    # Relationship
    data_source: Mapped["DataSource"] = relationship(back_populates="mappings")
