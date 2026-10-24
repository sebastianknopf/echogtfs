from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

# Plain dataclasses for the documents stored in MongoDB. Attribute names match the former SQLAlchemy
# models so exports, routers, the conflict service and Pydantic schemas (from_attributes) keep working.
# Back-references (stop_event.trip, informed_entity.alert, trip.vehicle) are set by the repository on read.


@dataclass
class ServiceAlertTranslation:
    id: int
    language: str
    header_text: str | None = None
    description_text: str | None = None
    url: str | None = None


@dataclass
class ServiceAlertActivePeriod:
    id: int
    period_type: str
    start_time: int | None = None
    end_time: int | None = None


@dataclass
class ServiceAlertInformedEntity:
    id: int
    agency_id: str | None = None
    route_id: str | None = None
    route_type: int | None = None
    stop_id: str | None = None
    trip_id: str | None = None
    direction_id: int | None = None
    is_agency_valid: bool = True
    is_route_valid: bool = True
    is_stop_valid: bool = True
    is_trip_valid: bool = True
    alert: ServiceAlert | None = field(default=None, repr=False, compare=False)


@dataclass
class ServiceAlert:
    id: uuid.UUID
    data_source_id: int | None
    cause: str
    effect: str
    severity_level: str
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    translations: list[ServiceAlertTranslation] = field(default_factory=list)
    active_periods: list[ServiceAlertActivePeriod] = field(default_factory=list)
    informed_entities: list[ServiceAlertInformedEntity] = field(default_factory=list)
    data_source_name: str | None = None


@dataclass
class StopEvent:
    trip_id: str
    stop_id: str
    original_stop_id: str
    stop_sequence: str
    arrival_time: datetime | None
    departure_time: datetime | None
    scheduled_arrival_time: datetime | None = None
    scheduled_departure_time: datetime | None = None
    schedule_relationship: str = "SCHEDULED"
    is_implied_schedule_relationship: bool = False
    is_valid: bool = True
    trip: TripUpdate | None = field(default=None, repr=False, compare=False)


@dataclass
class TripUpdate:
    id: uuid.UUID
    data_source_id: int | None
    source: str
    trip_id: str
    original_trip_id: str | None
    scheduled_start_stop_id: str | None
    scheduled_end_stop_id: str | None
    scheduled_start_time: datetime | None
    scheduled_end_time: datetime | None
    start_time: str | None
    start_date: str
    route_id: str
    schedule_relationship: str
    assignment_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    is_trip_valid: bool = True
    is_route_valid: bool = True
    is_complete_stop_sequence: bool = True
    stop_events: list[StopEvent] = field(default_factory=list)
    vehicle: VehiclePosition | None = field(default=None, repr=False, compare=False)
    data_source_name: str | None = None

    @property
    def is_valid(self) -> bool:
        return bool(self.is_trip_valid and self.is_route_valid)


@dataclass
class VehicleTripDescriptor:
    """Trip reference embedded in a vehicle position, with the same validity flags as a trip update."""

    trip_id: str
    original_trip_id: str | None
    route_id: str
    start_date: str
    start_time: str | None
    schedule_relationship: str
    assignment_type: str
    is_trip_valid: bool = True
    is_route_valid: bool = True

    @property
    def is_valid(self) -> bool:
        return bool(self.is_trip_valid and self.is_route_valid)


@dataclass
class VehiclePosition:
    id: uuid.UUID
    data_source_id: int | None
    source: str
    vehicle_id: str
    vehicle_label: str | None
    vehicle_license_plate: str | None
    vehicle_wheelchair_accessible: str
    timestamp: Any
    latitude: float
    longitude: float
    current_stop_sequence: int | None
    current_status: str
    assignment_type: str
    congestion_level: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    is_valid: bool
    trip: VehicleTripDescriptor
    data_source_name: str | None = None

    @property
    def trip_id(self) -> str:
        return self.trip.trip_id
