from datetime import datetime
from typing import ClassVar
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from echogtfs.enum.gtfsrt import (
    AlertCause,
    AlertEffect,
    AlertSeverityLevel,
    AssignmentType,
    CongestionLevel,
    PeriodType,
    VehicleStopStatus,
    WheelchairAccessible,
)
from echogtfs.enum.system import EnrichmentType, ExpiredRealtimeObjectPolicy, InvalidReferencePolicy, SourceField


# ---------------------------------------------------------------------------
# System models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class AppSetting(Base):
    """Key-value store for application-wide settings persisted in the database."""

    __tablename__ = "sys_app_settings"

    KEY_COLOR_PRIMARY: ClassVar[str] = "color_primary"
    KEY_COLOR_SECONDARY: ClassVar[str] = "color_secondary"
    KEY_APP_TITLE: ClassVar[str] = "app_title"
    KEY_APP_LANGUAGE: ClassVar[str] = "app_language"

    KEY_GTFS_RT_SERVICE_ALERTS_PATH: ClassVar[str] = "gtfs_rt_service_alerts_path"
    KEY_GTFS_RT_TRIP_UPDATES_PATH: ClassVar[str] = "gtfs_rt_trip_updates_path"
    KEY_GTFS_RT_VEHICLE_POSITIONS_PATH: ClassVar[str] = "gtfs_rt_vehicle_positions_path"
    KEY_GTFS_RT_USERNAME: ClassVar[str] = "gtfs_rt_username"
    KEY_GTFS_RT_PASSWORD: ClassVar[str] = "gtfs_rt_password"

    KEY_CLEANUP_CRON: ClassVar[str] = "cleanup_cron"
    KEY_CLEANUP_EXPIRED_POLICY: ClassVar[str] = "cleanup_expired_policy"
    KEY_CLEANUP_DELETE_AFTER_DAYS: ClassVar[str] = "cleanup_delete_after_days"

    KEY_GTFS_FEED_URL: ClassVar[str] = "gtfs_feed_url"
    KEY_GTFS_IMPORT_STATUS: ClassVar[str] = "gtfs_import_status"
    KEY_GTFS_IMPORT_TIME: ClassVar[str] = "gtfs_import_time"
    KEY_GTFS_IMPORT_MESSAGE: ClassVar[str] = "gtfs_import_message"
    KEY_GTFS_CRON: ClassVar[str] = "gtfs_cron"

    ALL_KEYS: ClassVar[tuple[str, ...]] = (
        KEY_COLOR_PRIMARY,
        KEY_COLOR_SECONDARY,
        KEY_APP_TITLE,
        KEY_APP_LANGUAGE,
        KEY_GTFS_RT_SERVICE_ALERTS_PATH,
        KEY_GTFS_RT_TRIP_UPDATES_PATH,
        KEY_GTFS_RT_VEHICLE_POSITIONS_PATH,
        KEY_GTFS_RT_USERNAME,
        KEY_GTFS_RT_PASSWORD,
        KEY_CLEANUP_CRON,
        KEY_CLEANUP_EXPIRED_POLICY,
        KEY_CLEANUP_DELETE_AFTER_DAYS,
        KEY_GTFS_FEED_URL,
        KEY_GTFS_IMPORT_STATUS,
        KEY_GTFS_IMPORT_TIME,
        KEY_GTFS_IMPORT_MESSAGE,
        KEY_GTFS_CRON,
    )

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(2048))  # wider for URLs + messages


class User(Base):
    __tablename__ = "sys_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_technical_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DataSource(Base):
    """
    External data source configuration.
    
    Each data source has a type that determines how it should be processed.
    Type-specific configuration is stored as JSON string in the config field.
    Mappings define how GTFS entities map to external data source values.
    """
    __tablename__ = "sys_data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    type: Mapped[str] = mapped_column(String(64))
    
    # Type-specific configuration stored as JSON string
    config: Mapped[str] = mapped_column(Text, default="{}")
    
    # Optional cron expression for automatic updates
    cron: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Active status - inactive sources don't run and their alerts are deleted
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Controls whether response dump files should be persisted for this source
    log_dumps: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Policy for handling invalid entity references
    invalid_reference_policy: Mapped[InvalidReferencePolicy] = mapped_column(
        String(32), default=InvalidReferencePolicy.NOT_SPECIFIED
    )
    
    # Last execution timestamp
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    enrichments: Mapped[list["DataSourceEnrichment"]] = relationship(
        back_populates="data_source", 
        cascade="all, delete-orphan",
        order_by="DataSourceEnrichment.sort_order"
    )
    alerts: Mapped[list["ServiceAlert"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )
    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )
    logs: Mapped[list["DataSourceLog"]] = relationship(
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
    __tablename__ = "sys_data_source_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_data_sources.id"), index=True)
    
    # GTFS entity type: "agency", "route", "stop", "trip", etc.
    entity_type: Mapped[str] = mapped_column(String(32))
    
    # Mapping key-value pair
    # Key: external identifier from data source
    # Value: GTFS entity ID (the ID field, not a separate entity_id column)
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(512))
    
    # Relationship
    data_source: Mapped["DataSource"] = relationship(back_populates="mappings")


class DataSourceEnrichment(Base):
    """
    Enrichment rules for extracting cause, effect, and severity from alert text.
    
    Enrichments allow pattern matching in alert header/description text to
    automatically derive cause, effect, or severity values. Unlike mappings,
    enrichments are sortable to control priority when multiple patterns match.
    
    The key field can contain text or regex patterns to match against the
    specified source field(s). When a match is found, the value is applied.
    """
    __tablename__ = "sys_data_source_enrichments"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_data_sources.id", ondelete="CASCADE"), index=True
    )
    
    # Enrichment configuration
    enrichment_type: Mapped[EnrichmentType] = mapped_column(String(32))
    source_field: Mapped[SourceField] = mapped_column(String(32))
    
    # Pattern matching
    # Key: text or regex pattern to match in the source field
    # Value: the value to assign (e.g., "STRIKE", "NO_SERVICE", "SEVERE")
    key: Mapped[str] = mapped_column(String(512))
    value: Mapped[str] = mapped_column(String(128))
    
    # Sort order for priority (lower number = higher priority)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationship
    data_source: Mapped["DataSource"] = relationship(back_populates="enrichments")


class DataSourceLog(Base):
    """
    Log entry for external data source requests.
    
    Tracks HTTP requests to external data sources with metadata stored
    in the database and full response dumps stored as files.
    """
    __tablename__ = "sys_data_source_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_data_sources.id", ondelete="CASCADE"), index=True
    )
    
    # Request timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    # Request metadata
    request_url: Mapped[str] = mapped_column(String(2048))
    request_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Response metadata
    response_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_mimetype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    
    # Reference to log file (UUID filename in named volume)
    log_file_uuid: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    
    # Creation timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    # Relationship
    data_source: Mapped["DataSource"] = relationship(back_populates="logs")

# ---------------------------------------------------------------------------
# GTFS static models
# ---------------------------------------------------------------------------

class GtfsAgency(Base):
    """Imported GTFS agencies (agency.txt)."""
    __tablename__ = "gtfs_agencies"

    gtfs_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name:    Mapped[str] = mapped_column(String(255))


class GtfsStop(Base):
    """Imported GTFS stops (stops.txt)."""
    __tablename__ = "gtfs_stops"

    gtfs_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name:    Mapped[str] = mapped_column(String(255))

    start_trips: Mapped[list["GtfsTrip"]] = relationship(
        back_populates="start_stop",
        foreign_keys="GtfsTrip.start_stop_id",
    )
    end_trips: Mapped[list["GtfsTrip"]] = relationship(
        back_populates="end_stop",
        foreign_keys="GtfsTrip.end_stop_id",
    )
    stop_times: Mapped[list["GtfsStopTime"]] = relationship(back_populates="stop")


class GtfsRoute(Base):
    """Imported GTFS routes (routes.txt)."""
    __tablename__ = "gtfs_routes"

    gtfs_id:    Mapped[str] = mapped_column(String(128), primary_key=True)
    short_name: Mapped[str] = mapped_column(String(128))
    long_name:  Mapped[str] = mapped_column(String(255))

    trips: Mapped[list["GtfsTrip"]] = relationship(back_populates="route")


class GtfsTrip(Base):
    """Imported GTFS trips (trips.txt)."""
    __tablename__ = "gtfs_trips"

    gtfs_id: Mapped[str] = mapped_column(Text, primary_key=True)
    route_id: Mapped[str] = mapped_column(Text, ForeignKey("gtfs_routes.gtfs_id"))
    direction_id: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_stop_id: Mapped[str] = mapped_column(Text, ForeignKey("gtfs_stops.gtfs_id"))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_stop_id: Mapped[str] = mapped_column(Text, ForeignKey("gtfs_stops.gtfs_id"))

    route: Mapped["GtfsRoute"] = relationship(back_populates="trips")
    start_stop: Mapped["GtfsStop"] = relationship(
        back_populates="start_trips",
        foreign_keys=[start_stop_id],
    )
    end_stop: Mapped["GtfsStop"] = relationship(
        back_populates="end_trips",
        foreign_keys=[end_stop_id],
    )
    stop_times: Mapped[list["GtfsStopTime"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="GtfsStopTime.stop_sequence",
    )

    __table_args__ = (
        Index(
            "ix_gtfs_trips_route_start_end_lookup",
            "route_id",
            "start_stop_id",
            "start_time",
            "end_stop_id",
            "end_time",
        ),
    )


class GtfsStopTime(Base):
    """Imported GTFS stop times (stop_times.txt)."""
    __tablename__ = "gtfs_stop_times"

    trip_id: Mapped[str] = mapped_column(Text, ForeignKey("gtfs_trips.gtfs_id"), primary_key=True)
    stop_id: Mapped[str] = mapped_column(Text, ForeignKey("gtfs_stops.gtfs_id"), primary_key=True)
    stop_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    trip: Mapped["GtfsTrip"] = relationship(back_populates="stop_times")
    stop: Mapped["GtfsStop"] = relationship(back_populates="stop_times")

# ---------------------------------------------------------------------------
# GTFS-RT models
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
    __tablename__ = "realtime_service_alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    
    # Data source relation (NULL = internal alert, created in echogtfs UI)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sys_data_sources.id", ondelete="CASCADE"), nullable=True
    )
    
    # Alert metadata
    cause: Mapped[AlertCause] = mapped_column(String(32), default=AlertCause.UNKNOWN_CAUSE)
    effect: Mapped[AlertEffect] = mapped_column(String(32), default=AlertEffect.UNKNOWN_EFFECT)
    severity_level: Mapped[AlertSeverityLevel] = mapped_column(
        String(32), default=AlertSeverityLevel.UNKNOWN_SEVERITY
    )
    source: Mapped[str] = mapped_column(String(128), default="echogtfs")
    
    # Status flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
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
    __tablename__ = "realtime_service_alert_translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # Language code (ISO 639-1: 'de', 'en', 'fr', etc.)
    language: Mapped[str] = mapped_column(String(8))
    
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
    
    The period_type field distinguishes between:
    - impact_period: The actual validity period (when the alert affects service)
    - communication_period: The publication period (when the alert should be shown)
    """
    __tablename__ = "realtime_service_alert_active_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # Period type: impact_period or communication_period
    period_type: Mapped[PeriodType] = mapped_column(
        String(32), default=PeriodType.IMPACT_PERIOD
    )
    
    # Unix timestamps (seconds since epoch)
    # If start is None, active from beginning of time
    # If end is None, active until end of time
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    
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
    __tablename__ = "realtime_service_alert_informed_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("realtime_service_alerts.id", ondelete="CASCADE"), index=True
    )
    
    # GTFS entity references (NO FOREIGN KEYS - just string IDs for search)
    agency_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    route_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trip_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    
    # Optional direction filter (0 or 1)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Validation status - marks whether this entity reference is valid
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationship
    alert: Mapped["ServiceAlert"] = relationship(back_populates="informed_entities")


class Trip(Base):
    """GTFS-RT trip entity for stop events and vehicle positions."""

    __tablename__ = "realtime_trips"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sys_data_sources.id", ondelete="CASCADE"), index=True, nullable=True
    )
    source: Mapped[str] = mapped_column(Text, default="echogtfs")
    trip_id: Mapped[str] = mapped_column(Text, unique=True)
    original_trip_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_start_stop_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_end_stop_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_time: Mapped[str] = mapped_column(Text)
    start_date: Mapped[str] = mapped_column(Text)
    route_id: Mapped[str] = mapped_column(Text)
    schedule_relationship: Mapped[str] = mapped_column(Text, default="SCHEDULED")
    assignment_type: Mapped[AssignmentType] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    data_source: Mapped["DataSource | None"] = relationship(back_populates="trips")
    stop_events: Mapped[list["StopEvent"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    vehicle: Mapped["Vehicle | None"] = relationship(
        back_populates="trip", cascade="all, delete-orphan", uselist=False
    )

    @property
    def data_source_name(self) -> str | None:
        """Return the name of the data source if this is an external realtime trip."""
        return self.data_source.name if self.data_source else None


class StopEvent(Base):
    """GTFS-RT stop event tied to a realtime trip."""

    __tablename__ = "realtime_stop_events"

    trip_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("realtime_trips.trip_id", ondelete="CASCADE"),
        primary_key=True,
    )
    stop_id: Mapped[str] = mapped_column(Text, primary_key=True)
    stop_sequence: Mapped[str] = mapped_column(Text, primary_key=True)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schedule_relationship: Mapped[str] = mapped_column(Text, default="SCHEDULED")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    trip: Mapped["Trip"] = relationship(back_populates="stop_events")


class Vehicle(Base):
    """GTFS-RT vehicle position tied 1:1 to a realtime trip."""

    __tablename__ = "realtime_vehicle_positions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sys_data_sources.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, default="echogtfs")
    trip_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("realtime_trips.trip_id", ondelete="CASCADE"),
        unique=True,
    )
    vehicle_id: Mapped[str] = mapped_column(Text)
    vehicle_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    vehicle_license_plate: Mapped[str | None] = mapped_column(Text, nullable=True)
    vehicle_wheelchair_accessible: Mapped[WheelchairAccessible] = mapped_column(
        Enum(WheelchairAccessible, name="vehicle_wheelchair_accessible"),
        default=WheelchairAccessible.NO_VALUE,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    current_stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_status: Mapped[VehicleStopStatus] = mapped_column(
        Enum(VehicleStopStatus, name="vehicle_stop_status"),
        default=VehicleStopStatus.IN_TRANSIT_TO,
    )
    assignment_type: Mapped[AssignmentType] = mapped_column(String(64))
    congestion_level: Mapped[CongestionLevel] = mapped_column(
        Enum(CongestionLevel, name="congestion_level"),
        default=CongestionLevel.UNKNOWN_CONGESTION_LEVEL,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    data_source: Mapped["DataSource | None"] = relationship(back_populates="vehicles")
    trip: Mapped["Trip"] = relationship(back_populates="vehicle")

    @property
    def data_source_name(self) -> str | None:
        """Return the name of the data source if this is an external vehicle position."""
        return self.data_source.name if self.data_source else None
