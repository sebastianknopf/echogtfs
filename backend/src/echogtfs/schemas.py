from datetime import datetime
import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from echogtfs.models import (
    InvalidReferencePolicy, 
    EnrichmentType, 
    SourceField,
    AlertCause,
    AlertEffect,
    AlertSeverityLevel,
    ExpiredAlertPolicy
)

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
    is_technical_contact: bool | None = None


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    is_technical_contact: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# App settings (theme + title + GTFS-RT config)
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


class AppSettings(BaseModel):
    """Combined app settings including theme and GTFS-RT configuration."""
    color_primary:   str = '#008c99'
    color_secondary: str = '#99cc04'
    app_title:       str = 'echogtfs'
    app_language:    str = 'de'  # 'de' or 'en'
    
    # GTFS-RT endpoint configuration
    gtfs_rt_path:     str = 'realtime/service-alerts.pbf'
    gtfs_rt_username: str = ''
    gtfs_rt_password: str | None = ''
    
    # Data cleanup configuration
    cleanup_cron:             str = '*/10 * * * *'  # Every 10 minutes
    cleanup_expired_policy:   ExpiredAlertPolicy = ExpiredAlertPolicy.DEACTIVATE
    cleanup_delete_after_days: int = -1  # -1 = never, >= 0 = days after expiration

    @field_validator('color_primary', 'color_secondary')
    @classmethod
    def must_be_hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError('Must be a 6-digit hex color, e.g. #008c99')
        return v.lower()
    
    @field_validator('cleanup_delete_after_days')
    @classmethod
    def validate_delete_days(cls, v: int) -> int:
        if v < -1:
            raise ValueError('cleanup_delete_after_days must be >= -1 (-1 = never)')
        return v


class PublicAppSettings(BaseModel):
    """Public app settings available without authentication (theme and language)."""
    color_primary:   str = '#008c99'
    color_secondary: str = '#99cc04'
    app_title:       str = 'echogtfs'
    app_language:    str = 'de'  # 'de' or 'en'
    app_version:     str = '0.0.0'

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
    cron: str | None = None



class GtfsStatusRead(BaseModel):
    feed_url:    str
    cron:        str | None = None
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


# ---------------------------------------------------------------------------
# ServiceAlerts (GTFS-RT)
# ---------------------------------------------------------------------------

class ServiceAlertTranslationCreate(BaseModel):
    """Translation data for creating/updating alerts."""
    language: str
    header_text: str | None = None
    description_text: str | None = None
    url: str | None = None


class ServiceAlertTranslationRead(ServiceAlertTranslationCreate):
    """Read model with ID."""
    id: int
    model_config = {"from_attributes": True}


class ServiceAlertActivePeriodCreate(BaseModel):
    """Active period for creating/updating alerts."""
    start_time: int | None = None
    end_time: int | None = None


class ServiceAlertActivePeriodRead(ServiceAlertActivePeriodCreate):
    """Read model with ID."""
    id: int
    model_config = {"from_attributes": True}


class ServiceAlertInformedEntityCreate(BaseModel):
    """Informed entity for creating/updating alerts."""
    agency_id: str | None = None
    route_id: str | None = None
    route_type: int | None = None
    stop_id: str | None = None
    trip_id: str | None = None
    direction_id: int | None = None


class ServiceAlertInformedEntityRead(ServiceAlertInformedEntityCreate):
    """Read model with ID, validation status, and resolved names."""
    id: int
    is_valid: bool  # Validation status of the entity reference
    # Resolved names from GTFS data (populated by API, not from DB)
    agency_name: str | None = None
    route_name: str | None = None
    stop_name: str | None = None
    model_config = {"from_attributes": True}


class ServiceAlertCreate(BaseModel):
    """Create a new service alert."""
    cause: str = "UNKNOWN_CAUSE"
    effect: str = "UNKNOWN_EFFECT"
    severity_level: str = "UNKNOWN_SEVERITY"
    is_active: bool = True
    translations: list[ServiceAlertTranslationCreate] = []
    active_periods: list[ServiceAlertActivePeriodCreate] = []
    informed_entities: list[ServiceAlertInformedEntityCreate] = []


class ServiceAlertUpdate(BaseModel):
    """Update an existing service alert."""
    cause: str | None = None
    effect: str | None = None
    severity_level: str | None = None
    is_active: bool | None = None
    translations: list[ServiceAlertTranslationCreate] | None = None
    active_periods: list[ServiceAlertActivePeriodCreate] | None = None
    informed_entities: list[ServiceAlertInformedEntityCreate] | None = None


class ServiceAlertRead(BaseModel):
    """Read model for service alerts."""
    id: UUID
    data_source_id: int | None
    cause: str
    effect: str
    severity_level: str
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    translations: list[ServiceAlertTranslationRead]
    active_periods: list[ServiceAlertActivePeriodRead]
    informed_entities: list[ServiceAlertInformedEntityRead]
    data_source_name: str | None = None
    
    model_config = {"from_attributes": True}


class ServiceAlertListResponse(BaseModel):
    """Paginated response for service alerts list."""
    total: int
    page: int
    limit: int
    total_pages: int
    items: list[ServiceAlertRead]


# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

class DataSourceMappingCreate(BaseModel):
    """Mapping data for creating/updating data sources.
    
    Maps external keys to GTFS entity IDs:
    - entity_type: Type of GTFS entity ("agency", "route", "stop", etc.)
    - key: External identifier from data source
    - value: GTFS entity ID (agency_id, route_id, stop_id, etc.)
    """
    entity_type: str
    key: str
    value: str


class DataSourceMappingRead(DataSourceMappingCreate):
    """Read model with ID."""
    id: int
    model_config = {"from_attributes": True}


class DataSourceEnrichmentCreate(BaseModel):
    """Enrichment data for creating/updating data sources.
    
    Enrichments extract cause, effect, or severity from alert text fields:
    - enrichment_type: Type of enrichment ("cause", "effect", "severity")
    - source_field: Where to look ("header", "description", "header_description")
    - key: Text or regex pattern to match
    - value: Value to assign when matched (e.g., "STRIKE", "NO_SERVICE", "SEVERE")
    - sort_order: Priority (lower numbers processed first)
    """
    enrichment_type: EnrichmentType
    source_field: SourceField
    key: str
    value: str
    sort_order: int = 0

    @model_validator(mode='after')
    def validate_enrichment_value(self):
        """Validate that value matches the enrichment_type."""
        if self.enrichment_type == EnrichmentType.CAUSE:
            # Validate against AlertCause enum
            valid_values = [cause.value for cause in AlertCause]
            if self.value not in valid_values:
                raise ValueError(
                    f"Invalid cause value '{self.value}'. Must be one of: {', '.join(valid_values)}"
                )
        elif self.enrichment_type == EnrichmentType.EFFECT:
            # Validate against AlertEffect enum
            valid_values = [effect.value for effect in AlertEffect]
            if self.value not in valid_values:
                raise ValueError(
                    f"Invalid effect value '{self.value}'. Must be one of: {', '.join(valid_values)}"
                )
        elif self.enrichment_type == EnrichmentType.SEVERITY:
            # Validate against AlertSeverityLevel enum
            valid_values = [severity.value for severity in AlertSeverityLevel]
            if self.value not in valid_values:
                raise ValueError(
                    f"Invalid severity value '{self.value}'. Must be one of: {', '.join(valid_values)}"
                )
        return self


class DataSourceEnrichmentRead(DataSourceEnrichmentCreate):
    """Read model with ID."""
    id: int
    model_config = {"from_attributes": True}


class DataSourceCreate(BaseModel):
    """Create a new data source."""
    name: str
    type: str
    config: str = "{}"
    cron: str | None = None
    is_active: bool = True
    invalid_reference_policy: InvalidReferencePolicy = InvalidReferencePolicy.NOT_SPECIFIED
    mappings: list[DataSourceMappingCreate] = []
    enrichments: list[DataSourceEnrichmentCreate] = []


class DataSourceUpdate(BaseModel):
    """Update an existing data source."""
    name: str | None = None
    type: str | None = None
    config: str | None = None
    cron: str | None = None
    is_active: bool | None = None
    invalid_reference_policy: InvalidReferencePolicy | None = None
    mappings: list[DataSourceMappingCreate] | None = None
    enrichments: list[DataSourceEnrichmentCreate] | None = None


class DataSourceRead(BaseModel):
    """Read model for data sources."""
    id: int
    name: str
    type: str
    config: str
    cron: str | None
    is_active: bool
    invalid_reference_policy: InvalidReferencePolicy
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    mappings: list[DataSourceMappingRead]
    enrichments: list[DataSourceEnrichmentRead]
    model_config = {"from_attributes": True}
