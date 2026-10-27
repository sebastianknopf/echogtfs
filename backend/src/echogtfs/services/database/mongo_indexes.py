from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel

SERVICE_ALERTS_COLLECTION = "realtime_service_alerts"
TRIP_UPDATES_COLLECTION = "realtime_trip_updates"
VEHICLE_POSITIONS_COLLECTION = "realtime_vehicle_positions"


def realtime_index_definitions() -> dict[str, list[IndexModel]]:
    """Indices for the three realtime collections (see implementation.md, target data model)."""
    return {
        SERVICE_ALERTS_COLLECTION: [
            IndexModel([("data_source_id", ASCENDING)], name="data_source_id"),
            IndexModel([("is_active", ASCENDING)], name="is_active"),
            IndexModel([("max_end_time", ASCENDING)], name="max_end_time"),
            IndexModel([("first_start", ASCENDING)], name="first_start"),
            IndexModel(
                [("has_invalid_reference", ASCENDING)],
                name="has_invalid_reference_partial",
                partialFilterExpression={"has_invalid_reference": True},
            ),
        ],
        TRIP_UPDATES_COLLECTION: [
            IndexModel([("trip_id", ASCENDING)], name="trip_id_unique", unique=True),
            IndexModel(
                [("is_active", ASCENDING), ("created_at", ASCENDING), ("trip_id", ASCENDING)],
                name="is_active_created_at_trip_id",
            ),
            IndexModel([("data_source_id", ASCENDING)], name="data_source_id"),
            IndexModel([("updated_at", DESCENDING)], name="updated_at"),
            IndexModel([("flags", ASCENDING)], name="flags"),
            IndexModel(
                [("start_date", ASCENDING), ("start_time", ASCENDING), ("trip_id", ASCENDING)],
                name="start_date_start_time_trip_id",
            ),
        ],
        VEHICLE_POSITIONS_COLLECTION: [
            IndexModel([("trip.trip_id", ASCENDING)], name="trip_trip_id_unique", unique=True),
            IndexModel([("is_active", ASCENDING)], name="is_active"),
            IndexModel([("data_source_id", ASCENDING)], name="data_source_id"),
            IndexModel([("updated_at", DESCENDING)], name="updated_at"),
        ],
    }
