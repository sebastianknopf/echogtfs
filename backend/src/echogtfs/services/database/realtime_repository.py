from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import re
from typing import Any
import uuid

from pymongo import ASCENDING, DESCENDING, DeleteMany, IndexModel, ReturnDocument, UpdateMany, UpdateOne
from sqlalchemy import select

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.models import DataSource, GtfsTrip
from echogtfs.services.database.mongo_base import MongoRepositoryBase
from echogtfs.services.database.mongo_indexes import (
    SERVICE_ALERTS_COLLECTION,
    TRIP_UPDATES_COLLECTION,
    VEHICLE_POSITIONS_COLLECTION,
    realtime_index_definitions,
)
from echogtfs.services.database.postgres_base import PostgresRepositoryBase
from echogtfs.services.database.realtime_models import (
    ServiceAlert,
    ServiceAlertActivePeriod,
    ServiceAlertInformedEntity,
    ServiceAlertTranslation,
    StopEvent,
    TripUpdate,
    VehiclePosition,
    VehicleTripDescriptor,
)

# Flags stored on trip-update documents (multikey index) to find conflicts and dashboard states without scans.
FLAG_INVALID_REFERENCE = "invalid_reference"
FLAG_INVALID_STOP = "invalid_stop"
FLAG_IMPLIED_DEVIATION = "implied_deviation"
FLAG_CHANGED_STOP_ID = "changed_stop_id"
FLAG_DEPARTURE_BEFORE_ARRIVAL = "departure_before_arrival"
FLAG_REALTIME = "realtime"

_NO_STOP_EVENTS = {"stop_events": 0}


class RealtimeRepository(MongoRepositoryBase, RealtimeRepositoryInterface):
    """MongoDB repository for realtime alerts, trip updates and vehicle positions.

    PostgreSQL is only used to resolve data source names and running GTFS trips for statistics.
    """

    def __init__(
        self,
        database_url: str,
        debug: bool = False,
        mongo_url: str | None = None,
        mongo_database: str | None = None,
    ):
        from echogtfs.common.config import settings

        super().__init__(mongo_url or settings.mongo_url, mongo_database or settings.mongo_database)
        self._postgres = PostgresRepositoryBase(database_url, debug)

    async def initialize(self) -> None:
        """Validate PostgreSQL and MongoDB connectivity and create the MongoDB indices."""
        await self._postgres.initialize()
        await super().initialize()

    async def close(self) -> None:
        """Close the MongoDB client and dispose the PostgreSQL engine."""
        await super().close()
        await self._postgres.close()

    def index_definitions(self) -> dict[str, list[IndexModel]]:
        return realtime_index_definitions()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _text(value: Any) -> Any:
        return value.value if isinstance(value, Enum) else value

    @staticmethod
    def _ids(values: list[uuid.UUID]) -> list[str]:
        return [str(value) for value in values]

    async def _session_options(self, session: Any = None) -> dict[str, Any]:
        """Return the session keyword for reads: an explicit snapshot session, or the open transaction."""
        if session is None:
            session = await self.read_session()

        return {"session": session} if session is not None else {}

    async def _find(
        self,
        collection_name: str,
        filter_: dict[str, Any] | None = None,
        *,
        projection: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 0,
        session: Any = None,
    ) -> list[dict[str, Any]]:
        options = await self._session_options(session)
        cursor = self.collection(collection_name).find(filter_ or {}, projection, **options)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)

        return await cursor.to_list()

    async def _count(self, collection_name: str, filter_: dict[str, Any] | None = None) -> int:
        options = await self._session_options()
        return int(await self.collection(collection_name).count_documents(filter_ or {}, **options))

    async def _aggregate(
        self,
        collection_name: str,
        pipeline: list[dict[str, Any]],
        session: Any = None,
    ) -> list[dict[str, Any]]:
        options = await self._session_options(session)
        cursor = await self.collection(collection_name).aggregate(pipeline, **options)
        return await cursor.to_list()

    async def _delete(self, collection_name: str, filter_: dict[str, Any]) -> int:
        """Delete matching documents; inside a sync transaction the delete is buffered and 0 is returned."""
        if self._current_context() is not None:
            await self.write(collection_name, DeleteMany(filter_))
            return 0

        result = await self.collection(collection_name).delete_many(filter_)
        return int(result.deleted_count)

    async def _update_many(self, collection_name: str, filter_: dict[str, Any], update: Any) -> int:
        if self._current_context() is not None:
            await self.write(collection_name, UpdateMany(filter_, update))
            return 0

        result = await self.collection(collection_name).update_many(filter_, update)
        return int(result.modified_count)

    async def _data_source_names(self) -> dict[int, str]:
        async with self._postgres.get_session() as db:
            result = await db.execute(select(DataSource.id, DataSource.name))
            return {row[0]: row[1] for row in result.all()}

    async def _fill_data_source_names(self, items: list[Any]) -> None:
        """Set data_source_name on the given alerts, trips or vehicles using one PostgreSQL select."""
        if not any(item.data_source_id is not None for item in items):
            return

        names = await self._data_source_names()
        for item in items:
            item.data_source_name = names.get(item.data_source_id) if item.data_source_id is not None else None

    # ------------------------------------------------------------------
    # Document <-> dataclass mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _alert_from_doc(doc: dict[str, Any]) -> ServiceAlert:
        alert = ServiceAlert(
            id=uuid.UUID(doc["_id"]),
            data_source_id=doc.get("data_source_id"),
            cause=doc.get("cause"),
            effect=doc.get("effect"),
            severity_level=doc.get("severity_level"),
            is_active=bool(doc.get("is_active", True)),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            translations=[
                ServiceAlertTranslation(
                    id=index,
                    language=item.get("language"),
                    header_text=item.get("header_text"),
                    description_text=item.get("description_text"),
                    url=item.get("url"),
                )
                for index, item in enumerate(doc.get("translations", []), start=1)
            ],
            active_periods=[
                ServiceAlertActivePeriod(
                    id=index,
                    period_type=item.get("period_type"),
                    start_time=item.get("start_time"),
                    end_time=item.get("end_time"),
                )
                for index, item in enumerate(doc.get("active_periods", []), start=1)
            ],
        )

        alert.informed_entities = [
            RealtimeRepository._informed_entity_from_doc(item, index, alert)
            for index, item in enumerate(doc.get("informed_entities", []), start=1)
        ]

        return alert

    @staticmethod
    def _informed_entity_from_doc(
        item: dict[str, Any],
        entity_id: int,
        alert: ServiceAlert,
    ) -> ServiceAlertInformedEntity:
        return ServiceAlertInformedEntity(
            id=entity_id,
            agency_id=item.get("agency_id"),
            route_id=item.get("route_id"),
            route_type=item.get("route_type"),
            stop_id=item.get("stop_id"),
            trip_id=item.get("trip_id"),
            direction_id=item.get("direction_id"),
            is_agency_valid=bool(item.get("is_agency_valid", True)),
            is_route_valid=bool(item.get("is_route_valid", True)),
            is_stop_valid=bool(item.get("is_stop_valid", True)),
            is_trip_valid=bool(item.get("is_trip_valid", True)),
            alert=alert,
        )

    @staticmethod
    def _stop_event_from_doc(item: dict[str, Any], trip_id: str, trip: TripUpdate | None) -> StopEvent:
        return StopEvent(
            trip_id=trip_id,
            stop_id=item.get("stop_id"),
            original_stop_id=item.get("original_stop_id"),
            stop_sequence=item.get("stop_sequence", ""),
            arrival_time=item.get("arrival_time"),
            departure_time=item.get("departure_time"),
            scheduled_arrival_time=item.get("scheduled_arrival_time"),
            scheduled_departure_time=item.get("scheduled_departure_time"),
            schedule_relationship=item.get("schedule_relationship", "SCHEDULED"),
            is_implied_schedule_relationship=bool(item.get("is_implied_schedule_relationship", False)),
            is_valid=bool(item.get("is_valid", True)),
            trip=trip,
        )

    @staticmethod
    def _trip_from_doc(doc: dict[str, Any], *, include_stop_events: bool = True) -> TripUpdate:
        trip = TripUpdate(
            id=uuid.UUID(doc["_id"]),
            data_source_id=doc.get("data_source_id"),
            trip_id=doc["trip_id"],
            original_trip_id=doc.get("original_trip_id"),
            scheduled_start_stop_id=doc.get("scheduled_start_stop_id"),
            scheduled_end_stop_id=doc.get("scheduled_end_stop_id"),
            scheduled_start_time=doc.get("scheduled_start_time"),
            scheduled_end_time=doc.get("scheduled_end_time"),
            start_time=doc.get("start_time"),
            start_date=doc.get("start_date", ""),
            route_id=doc.get("route_id", ""),
            schedule_relationship=doc.get("schedule_relationship", "SCHEDULED"),
            assignment_type=doc.get("assignment_type"),
            is_active=bool(doc.get("is_active", True)),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            is_trip_valid=bool(doc.get("is_trip_valid", True)),
            is_route_valid=bool(doc.get("is_route_valid", True)),
            is_complete_stop_sequence=bool(doc.get("is_complete_stop_sequence", True)),
        )

        if include_stop_events:
            trip.stop_events = [
                RealtimeRepository._stop_event_from_doc(item, trip.trip_id, trip)
                for item in doc.get("stop_events", [])
            ]

        return trip

    @staticmethod
    def _vehicle_from_doc(doc: dict[str, Any]) -> VehiclePosition:
        trip_doc = doc.get("trip", {})

        return VehiclePosition(
            id=uuid.UUID(doc["_id"]),
            data_source_id=doc.get("data_source_id"),
            vehicle_id=doc.get("vehicle_id"),
            vehicle_label=doc.get("vehicle_label"),
            vehicle_license_plate=doc.get("vehicle_license_plate"),
            vehicle_wheelchair_accessible=doc.get("vehicle_wheelchair_accessible"),
            timestamp=doc.get("timestamp"),
            latitude=doc.get("latitude"),
            longitude=doc.get("longitude"),
            current_stop_sequence=doc.get("current_stop_sequence"),
            current_status=doc.get("current_status"),
            congestion_level=doc.get("congestion_level"),
            is_active=bool(doc.get("is_active", True)),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            trip=VehicleTripDescriptor(
                trip_id=trip_doc.get("trip_id"),
                original_trip_id=trip_doc.get("original_trip_id"),
                route_id=trip_doc.get("route_id", ""),
                start_date=trip_doc.get("start_date", ""),
                start_time=trip_doc.get("start_time"),
                schedule_relationship=trip_doc.get("schedule_relationship", "SCHEDULED"),
                assignment_type=trip_doc.get("assignment_type"),
                scheduled_start_stop_id=trip_doc.get("scheduled_start_stop_id"),
                scheduled_end_stop_id=trip_doc.get("scheduled_end_stop_id"),
                scheduled_start_time=trip_doc.get("scheduled_start_time"),
                scheduled_end_time=trip_doc.get("scheduled_end_time"),
                is_trip_valid=bool(trip_doc.get("is_trip_valid", True)),
                is_route_valid=bool(trip_doc.get("is_route_valid", True)),
            ),
        )

    @staticmethod
    def _normalize_informed_entity_payload(entity_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize service-alert informed-entity payload for persistence."""
        return {
            "agency_id": entity_data.get("agency_id"),
            "route_id": entity_data.get("route_id"),
            "route_type": entity_data.get("route_type"),
            "stop_id": entity_data.get("stop_id"),
            "trip_id": entity_data.get("trip_id"),
            "direction_id": entity_data.get("direction_id"),
            "is_agency_valid": bool(entity_data.get("is_agency_valid", True)),
            "is_route_valid": bool(entity_data.get("is_route_valid", True)),
            "is_stop_valid": bool(entity_data.get("is_stop_valid", True)),
            "is_trip_valid": bool(entity_data.get("is_trip_valid", True)),
        }

    @classmethod
    def _alert_child_fields(
        cls,
        translations: list[dict[str, Any]],
        active_periods: list[dict[str, Any]],
        informed_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the embedded child arrays plus the derived fields used by queries and sorting."""
        translation_docs = [
            {
                "language": item.get("language"),
                "header_text": item.get("header_text"),
                "description_text": item.get("description_text"),
                "url": item.get("url"),
            }
            for item in translations
        ]
        period_docs = [
            {
                "period_type": cls._text(item.get("period_type")),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
            }
            for item in active_periods
        ]
        entity_docs = [cls._normalize_informed_entity_payload(item) for item in informed_entities]

        starts = [item["start_time"] for item in period_docs if item["start_time"] is not None]
        ends = [item["end_time"] for item in period_docs if item["end_time"] is not None]
        first_start = min(starts) if starts else None

        return {
            "translations": translation_docs,
            "active_periods": period_docs,
            "informed_entities": entity_docs,
            "first_start": first_start,
            "has_first_start": first_start is not None,
            "max_end_time": max(ends) if ends else None,
            "has_invalid_reference": any(
                not (
                    item["is_agency_valid"]
                    and item["is_route_valid"]
                    and item["is_stop_valid"]
                    and item["is_trip_valid"]
                )
                for item in entity_docs
            ),
        }

    @classmethod
    def _stop_event_document(cls, payload: dict[str, Any]) -> dict[str, Any]:
        original_stop_id = payload.get("original_stop_id")
        if original_stop_id in (None, ""):
            original_stop_id = payload.get("stop_id")

        stop_sequence = payload.get("stop_sequence")

        return {
            "stop_id": payload.get("stop_id"),
            "original_stop_id": original_stop_id,
            "stop_sequence": "" if stop_sequence is None else str(stop_sequence),
            "arrival_time": payload.get("arrival_time"),
            "departure_time": payload.get("departure_time"),
            "scheduled_arrival_time": payload.get("scheduled_arrival_time"),
            "scheduled_departure_time": payload.get("scheduled_departure_time"),
            "schedule_relationship": cls._text(payload.get("schedule_relationship") or "SCHEDULED"),
            "is_implied_schedule_relationship": bool(payload.get("is_implied_schedule_relationship", False)),
            "is_valid": bool(payload.get("is_valid", True)),
        }

    @staticmethod
    def _trip_flags(stop_events: list[dict[str, Any]], is_trip_valid: bool, is_route_valid: bool) -> list[str]:
        flags: list[str] = []

        def add(flag: str) -> None:
            if flag not in flags:
                flags.append(flag)

        if not (is_trip_valid and is_route_valid):
            add(FLAG_INVALID_REFERENCE)

        for event in stop_events:
            if not event["is_valid"]:
                add(FLAG_INVALID_STOP)

            if event["schedule_relationship"] != "NO_DATA":
                add(FLAG_REALTIME)

            if event["is_implied_schedule_relationship"] and event["schedule_relationship"] in ("ADDED", "SKIPPED"):
                add(FLAG_IMPLIED_DEVIATION)

            if event["stop_id"] != event["original_stop_id"]:
                add(FLAG_CHANGED_STOP_ID)

            try:
                if (
                    event["arrival_time"] is not None
                    and event["departure_time"] is not None
                    and event["departure_time"] < event["arrival_time"]
                ):
                    add(FLAG_DEPARTURE_BEFORE_ARRIVAL)
            except TypeError:
                pass

        return flags

    @staticmethod
    def _stop_event_sort_key(stop_sequence: str) -> tuple[int, int, str]:
        """Sort numeric stop_sequence values first, then fall back to string comparison."""
        try:
            return (0, int(stop_sequence), "")
        except (TypeError, ValueError):
            return (1, 0, str(stop_sequence))

    # ------------------------------------------------------------------
    # Service alerts
    # ------------------------------------------------------------------

    async def delete_alerts_for_data_source(self, source_id: int) -> int:
        return await self._delete(SERVICE_ALERTS_COLLECTION, {"data_source_id": source_id})

    async def get_realtime_service_alerts(self) -> list[ServiceAlert]:
        """Return active alerts as one consistent snapshot for the GTFS-RT export."""
        async with self.snapshot() as session:
            docs = await self._find(
                SERVICE_ALERTS_COLLECTION,
                {"is_active": True},
                sort=[("_id", ASCENDING)],
                session=session,
            )

        return [self._alert_from_doc(doc) for doc in docs]

    async def list_expired_alert_ids(self, current_timestamp: int, *, only_active: bool) -> list[uuid.UUID]:
        filter_: dict[str, Any] = {"max_end_time": {"$lt": current_timestamp}}
        if only_active:
            filter_["is_active"] = True

        docs = await self._find(SERVICE_ALERTS_COLLECTION, filter_, projection={"_id": 1})
        return [uuid.UUID(doc["_id"]) for doc in docs]

    async def list_alert_ids_expired_before(self, cutoff_timestamp: int) -> list[uuid.UUID]:
        docs = await self._find(
            SERVICE_ALERTS_COLLECTION,
            {"max_end_time": {"$lt": cutoff_timestamp}},
            projection={"_id": 1},
        )
        return [uuid.UUID(doc["_id"]) for doc in docs]

    async def deactivate_service_alerts(self, alert_ids: list[uuid.UUID]) -> int:
        if not alert_ids:
            return 0

        return await self._update_many(
            SERVICE_ALERTS_COLLECTION,
            {"_id": {"$in": self._ids(alert_ids)}},
            {"$set": {"is_active": False, "updated_at": self._now()}},
        )

    async def delete_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> int:
        if not alert_ids:
            return 0

        return await self._delete(SERVICE_ALERTS_COLLECTION, {"_id": {"$in": self._ids(alert_ids)}})

    async def list_service_alerts_for_data_source(self, source_id: int) -> list[ServiceAlert]:
        docs = await self._find(SERVICE_ALERTS_COLLECTION, {"data_source_id": source_id})
        return [self._alert_from_doc(doc) for doc in docs]

    async def list_service_alerts_paginated(
        self,
        *,
        page: int,
        limit: int,
        sort: str,
        search: str,
        is_active: bool | None,
        has_data_source: bool | None,
    ) -> tuple[list[ServiceAlert], int]:
        page = max(1, page)
        limit = max(1, min(100, limit))
        normalized_sort = sort.lower() if sort in ["newest", "oldest"] else "newest"

        filter_: dict[str, Any] = {}
        trimmed_search = search.strip()
        if trimmed_search:
            filter_["translations.header_text"] = {"$regex": re.escape(trimmed_search), "$options": "i"}

        if is_active is not None:
            filter_["is_active"] = is_active

        if has_data_source is not None:
            filter_["data_source_id"] = {"$ne": None} if has_data_source else None

        # Alerts without any period start come first, then by first start
        start_direction = DESCENDING if normalized_sort == "newest" else ASCENDING
        docs = await self._find(
            SERVICE_ALERTS_COLLECTION,
            filter_,
            sort=[("has_first_start", ASCENDING), ("first_start", start_direction), ("_id", ASCENDING)],
            skip=(page - 1) * limit,
            limit=limit,
        )
        total = await self._count(SERVICE_ALERTS_COLLECTION, filter_)

        items = [self._alert_from_doc(doc) for doc in docs]
        await self._fill_data_source_names(items)

        return items, total

    async def _load_alert(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        docs = await self._find(SERVICE_ALERTS_COLLECTION, {"_id": str(alert_id)})
        if not docs:
            return None

        alert = self._alert_from_doc(docs[0])
        await self._fill_data_source_names([alert])

        return alert

    async def get_service_alert_by_id_with_relations(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        return await self._load_alert(alert_id)

    async def create_service_alert(
        self,
        *,
        cause: str,
        effect: str,
        severity_level: str,
        is_active: bool,
        translations: list[dict[str, Any]],
        active_periods: list[dict[str, Any]],
        informed_entities: list[dict[str, Any]],
    ) -> ServiceAlert:
        alert_id = uuid.uuid4()
        now = self._now()

        document = {
            "_id": str(alert_id),
            "data_source_id": None,
            "cause": self._text(cause),
            "effect": self._text(effect),
            "severity_level": self._text(severity_level),
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
            **self._alert_child_fields(translations, active_periods, informed_entities),
        }
        await self.collection(SERVICE_ALERTS_COLLECTION).insert_one(document)

        return self._alert_from_doc(document)

    async def update_service_alert(
        self,
        alert_id: uuid.UUID,
        *,
        cause: str | None = None,
        effect: str | None = None,
        severity_level: str | None = None,
        is_active: bool | None = None,
        translations: list[dict[str, Any]] | None = None,
        active_periods: list[dict[str, Any]] | None = None,
        informed_entities: list[dict[str, Any]] | None = None,
    ) -> ServiceAlert | None:
        docs = await self._find(SERVICE_ALERTS_COLLECTION, {"_id": str(alert_id)})
        if not docs:
            return None

        current = docs[0]
        changes: dict[str, Any] = {"updated_at": self._now()}

        if cause is not None:
            changes["cause"] = self._text(cause)
        if effect is not None:
            changes["effect"] = self._text(effect)
        if severity_level is not None:
            changes["severity_level"] = self._text(severity_level)
        if is_active is not None:
            changes["is_active"] = is_active

        if translations is not None or active_periods is not None or informed_entities is not None:
            changes.update(
                self._alert_child_fields(
                    translations if translations is not None else current.get("translations", []),
                    active_periods if active_periods is not None else current.get("active_periods", []),
                    informed_entities if informed_entities is not None else current.get("informed_entities", []),
                )
            )

        await self.collection(SERVICE_ALERTS_COLLECTION).update_one({"_id": str(alert_id)}, {"$set": changes})

        return await self._load_alert(alert_id)

    async def toggle_service_alert_active(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        doc = await self.collection(SERVICE_ALERTS_COLLECTION).find_one_and_update(
            {"_id": str(alert_id)},
            [{"$set": {"is_active": {"$not": ["$is_active"]}, "updated_at": self._now()}}],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None

        alert = self._alert_from_doc(doc)
        await self._fill_data_source_names([alert])

        return alert

    async def list_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> list[ServiceAlert]:
        if not alert_ids:
            return []

        docs = await self._find(SERVICE_ALERTS_COLLECTION, {"_id": {"$in": self._ids(alert_ids)}})
        return [self._alert_from_doc(doc) for doc in docs]

    async def delete_service_alerts_for_data_source_by_ids(
        self,
        source_id: int,
        alert_ids: list[uuid.UUID],
    ) -> int:
        if not alert_ids:
            return 0

        return await self._delete(
            SERVICE_ALERTS_COLLECTION,
            {"data_source_id": source_id, "_id": {"$in": self._ids(alert_ids)}},
        )

    async def upsert_service_alert_from_sync(
        self,
        *,
        alert_id: uuid.UUID,
        source_id: int,
        cause: str,
        effect: str,
        severity_level: str,
        is_active_on_create: bool,
        translations: list[dict[str, Any]],
        active_periods: list[dict[str, Any]],
        informed_entities: list[dict[str, Any]],
    ) -> str:
        """Queue the upsert of one synchronized alert; is_active is only set when the alert is created."""
        now = self._now()
        fields = {
            "data_source_id": source_id,
            "cause": self._text(cause),
            "effect": self._text(effect),
            "severity_level": self._text(severity_level),
            "updated_at": now,
            **self._alert_child_fields(translations, active_periods, informed_entities),
        }

        await self.write(
            SERVICE_ALERTS_COLLECTION,
            UpdateOne(
                {"_id": str(alert_id)},
                {"$set": fields, "$setOnInsert": {"is_active": is_active_on_create, "created_at": now}},
                upsert=True,
            ),
        )

        return "upserted"

    # ------------------------------------------------------------------
    # Trip updates
    # ------------------------------------------------------------------

    async def _vehicles_by_trip_id(self, trip_ids: list[str] | None, session: Any = None) -> dict[str, VehiclePosition]:
        filter_ = {"trip.trip_id": {"$in": trip_ids}} if trip_ids is not None else {}
        docs = await self._find(VEHICLE_POSITIONS_COLLECTION, filter_, session=session)

        return {doc["trip"]["trip_id"]: self._vehicle_from_doc(doc) for doc in docs}

    async def get_realtime_trips(self) -> list[TripUpdate]:
        """Return active trips with stop events and linked vehicle as one consistent snapshot."""
        async with self.snapshot() as session:
            docs = await self._find(
                TRIP_UPDATES_COLLECTION,
                {"is_active": True},
                sort=[("created_at", ASCENDING), ("trip_id", ASCENDING)],
                session=session,
            )
            vehicles = await self._vehicles_by_trip_id(None, session=session)

        trips = [self._trip_from_doc(doc) for doc in docs]
        for trip in trips:
            trip.vehicle = vehicles.get(trip.trip_id)

        await self._fill_data_source_names(trips)

        return trips

    async def list_trips_paginated(
        self,
        *,
        page: int,
        limit: int,
        sort: str,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[TripUpdate], int]:
        page = max(1, page)
        limit = max(1, min(100, limit))
        normalized_sort = sort.lower() if sort in ["asc", "desc"] else "asc"

        filter_: dict[str, Any] = {"stop_event_count": {"$gt": 0}}
        trimmed_search = search.strip()
        if trimmed_search:
            pattern = {"$regex": re.escape(trimmed_search), "$options": "i"}
            filter_["$or"] = [{"trip_id": pattern}, {"route_id": pattern}, {"start_date": pattern}, {"start_time": pattern}]

        if is_active is not None:
            filter_["is_active"] = is_active

        direction = DESCENDING if normalized_sort == "desc" else ASCENDING
        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            filter_,
            sort=[("start_date", direction), ("start_time", direction), ("trip_id", ASCENDING)],
            skip=(page - 1) * limit,
            limit=limit,
        )
        total = await self._count(TRIP_UPDATES_COLLECTION, filter_)

        items = [self._trip_from_doc(doc) for doc in docs]
        vehicles = await self._vehicles_by_trip_id([trip.trip_id for trip in items])
        for trip in items:
            trip.vehicle = vehicles.get(trip.trip_id)

        await self._fill_data_source_names(items)

        return items, total

    async def list_trip_ids_with_invalid_stop_events(self, trip_ids: list[str]) -> set[str]:
        if not trip_ids:
            return set()

        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            {"trip_id": {"$in": trip_ids}, "flags": FLAG_INVALID_STOP},
            projection={"trip_id": 1},
        )
        return {doc["trip_id"] for doc in docs}

    async def toggle_trip_active(self, trip_uuid: uuid.UUID) -> TripUpdate | None:
        doc = await self.collection(TRIP_UPDATES_COLLECTION).find_one_and_update(
            {"_id": str(trip_uuid)},
            [{"$set": {"is_active": {"$not": ["$is_active"]}, "updated_at": self._now()}}],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None

        trip = self._trip_from_doc(doc)
        trip.vehicle = (await self._vehicles_by_trip_id([trip.trip_id])).get(trip.trip_id)
        await self._fill_data_source_names([trip])

        return trip

    async def delete_trips_for_data_source(self, source_id: int) -> int:
        return await self._delete(TRIP_UPDATES_COLLECTION, {"data_source_id": source_id})

    async def list_trips_for_data_source(self, source_id: int) -> list[TripUpdate]:
        docs = await self._find(TRIP_UPDATES_COLLECTION, {"data_source_id": source_id}, projection=_NO_STOP_EVENTS)
        return [self._trip_from_doc(doc, include_stop_events=False) for doc in docs]

    async def list_trips_by_ids(self, trip_ids: list[uuid.UUID]) -> list[TripUpdate]:
        if not trip_ids:
            return []

        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            {"_id": {"$in": self._ids(trip_ids)}},
            projection=_NO_STOP_EVENTS,
        )
        return [self._trip_from_doc(doc, include_stop_events=False) for doc in docs]

    async def list_trips_by_trip_ids(self, trip_ids: list[str]) -> list[TripUpdate]:
        if not trip_ids:
            return []

        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            {"trip_id": {"$in": trip_ids}},
            projection=_NO_STOP_EVENTS,
        )
        return [self._trip_from_doc(doc, include_stop_events=False) for doc in docs]

    async def list_stop_events_for_trip(self, trip_id: str) -> list[StopEvent]:
        docs = await self._find(TRIP_UPDATES_COLLECTION, {"trip_id": trip_id}, projection={"trip_id": 1, "stop_events": 1})
        if not docs:
            return []

        events = [self._stop_event_from_doc(item, trip_id, None) for item in docs[0].get("stop_events", [])]
        events.sort(key=lambda event: self._stop_event_sort_key(event.stop_sequence))

        return events

    async def list_trip_ids_updated_before(self, cutoff: datetime) -> list[str]:
        docs = await self._find(TRIP_UPDATES_COLLECTION, {"updated_at": {"$lt": cutoff}}, projection={"trip_id": 1})
        return [doc["trip_id"] for doc in docs]

    async def delete_trips_by_trip_ids(self, trip_ids: list[str]) -> int:
        if not trip_ids:
            return 0

        return await self._delete(TRIP_UPDATES_COLLECTION, {"trip_id": {"$in": trip_ids}})

    async def delete_trips_for_data_source_by_ids(
        self,
        source_id: int,
        trip_ids: list[uuid.UUID],
    ) -> int:
        if not trip_ids:
            return 0

        return await self._delete(
            TRIP_UPDATES_COLLECTION,
            {"data_source_id": source_id, "_id": {"$in": self._ids(trip_ids)}},
        )

    async def update_trip_update_from_sync(
        self,
        *,
        trip_uuid: uuid.UUID,
        source_id: int,
        trip_id: str,
        start_time: str | None,
        start_date: str,
        route_id: str,
        schedule_relationship: str,
        assignment_type: str,
        is_active_on_create: bool,
        is_trip_valid: bool,
        is_route_valid: bool,
        stop_events: list[dict[str, Any]],
        original_trip_id: str | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        is_complete_stop_sequence: bool = True,
    ) -> str:
        """Queue the upsert of one synchronized trip update, replacing its embedded stop events.

        is_active and created_at are only set on creation. A cached-id assignment never overwrites
        the assignment type of an existing trip.
        """
        now = self._now()
        event_docs = [self._stop_event_document(item) for item in stop_events]
        event_docs.sort(key=lambda item: self._stop_event_sort_key(item["stop_sequence"]))

        fields: dict[str, Any] = {
            "data_source_id": source_id,
            "trip_id": trip_id,
            "original_trip_id": original_trip_id,
            "scheduled_start_stop_id": scheduled_start_stop_id,
            "scheduled_end_stop_id": scheduled_end_stop_id,
            "scheduled_start_time": scheduled_start_time,
            "scheduled_end_time": scheduled_end_time,
            "start_time": start_time,
            "start_date": start_date,
            "route_id": route_id,
            "schedule_relationship": self._text(schedule_relationship),
            "is_trip_valid": is_trip_valid,
            "is_route_valid": is_route_valid,
            "is_complete_stop_sequence": is_complete_stop_sequence,
            "stop_events": event_docs,
            "stop_event_count": len(event_docs),
            "flags": self._trip_flags(event_docs, is_trip_valid, is_route_valid),
            "updated_at": now,
        }
        on_insert: dict[str, Any] = {"is_active": is_active_on_create, "created_at": now}

        if assignment_type != AssignmentType.MATCH_BY_CACHED_ID:
            fields["assignment_type"] = self._text(assignment_type)
        else:
            on_insert["assignment_type"] = self._text(assignment_type)

        await self.write(
            TRIP_UPDATES_COLLECTION,
            UpdateOne({"_id": str(trip_uuid)}, {"$set": fields, "$setOnInsert": on_insert}, upsert=True),
        )

        return "upserted"

    # ------------------------------------------------------------------
    # Vehicle positions
    # ------------------------------------------------------------------

    async def get_realtime_vehicles(self) -> list[VehiclePosition]:
        """Return active vehicle positions as one consistent snapshot for the GTFS-RT export."""
        async with self.snapshot() as session:
            docs = await self._find(
                VEHICLE_POSITIONS_COLLECTION,
                {"is_active": True},
                sort=[("created_at", ASCENDING), ("trip.trip_id", ASCENDING)],
                session=session,
            )

        return [self._vehicle_from_doc(doc) for doc in docs]

    async def list_vehicles_paginated(
        self,
        *,
        page: int,
        limit: int,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[VehiclePosition], int]:
        page = max(1, page)
        limit = max(1, min(1000, limit))

        filter_: dict[str, Any] = {}
        trimmed_search = search.strip()
        if trimmed_search:
            pattern = {"$regex": re.escape(trimmed_search), "$options": "i"}
            filter_["$or"] = [
                {"vehicle_id": pattern},
                {"trip.trip_id": pattern},
                {"vehicle_label": pattern},
                {"vehicle_license_plate": pattern},
            ]

        if is_active is not None:
            filter_["is_active"] = is_active

        docs = await self._find(
            VEHICLE_POSITIONS_COLLECTION,
            filter_,
            sort=[("timestamp", DESCENDING), ("vehicle_id", ASCENDING)],
            skip=(page - 1) * limit,
            limit=limit,
        )
        total = await self._count(VEHICLE_POSITIONS_COLLECTION, filter_)

        items = [self._vehicle_from_doc(doc) for doc in docs]
        await self._fill_data_source_names(items)

        return items, total

    async def toggle_vehicle_active(self, vehicle_uuid: uuid.UUID) -> VehiclePosition | None:
        doc = await self.collection(VEHICLE_POSITIONS_COLLECTION).find_one_and_update(
            {"_id": str(vehicle_uuid)},
            [{"$set": {"is_active": {"$not": ["$is_active"]}, "updated_at": self._now()}}],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None

        vehicle = self._vehicle_from_doc(doc)
        await self._fill_data_source_names([vehicle])

        return vehicle

    async def delete_vehicles_for_data_source(self, source_id: int) -> int:
        return await self._delete(VEHICLE_POSITIONS_COLLECTION, {"data_source_id": source_id})

    async def list_vehicles_for_data_source(self, source_id: int) -> list[VehiclePosition]:
        docs = await self._find(VEHICLE_POSITIONS_COLLECTION, {"data_source_id": source_id})
        return [self._vehicle_from_doc(doc) for doc in docs]

    async def list_vehicles_by_ids(self, vehicle_ids: list[uuid.UUID]) -> list[VehiclePosition]:
        if not vehicle_ids:
            return []

        docs = await self._find(VEHICLE_POSITIONS_COLLECTION, {"_id": {"$in": self._ids(vehicle_ids)}})
        return [self._vehicle_from_doc(doc) for doc in docs]

    async def list_vehicles_updated_before(self, cutoff: datetime) -> list[VehiclePosition]:
        docs = await self._find(VEHICLE_POSITIONS_COLLECTION, {"updated_at": {"$lt": cutoff}})
        return [self._vehicle_from_doc(doc) for doc in docs]

    async def delete_vehicles_by_ids(self, vehicle_ids: list[uuid.UUID]) -> int:
        if not vehicle_ids:
            return 0

        return await self._delete(VEHICLE_POSITIONS_COLLECTION, {"_id": {"$in": self._ids(vehicle_ids)}})

    async def delete_vehicles_for_data_source_by_ids(
        self,
        source_id: int,
        vehicle_ids: list[uuid.UUID],
    ) -> int:
        if not vehicle_ids:
            return 0

        return await self._delete(
            VEHICLE_POSITIONS_COLLECTION,
            {"data_source_id": source_id, "_id": {"$in": self._ids(vehicle_ids)}},
        )

    async def update_vehicle_position_from_sync(
        self,
        *,
        vehicle_uuid: uuid.UUID,
        source_id: int,
        trip_id: str,
        trip_original_trip_id: str | None,
        trip_start_time: str,
        trip_start_date: str,
        trip_route_id: str,
        trip_schedule_relationship: str,
        trip_assignment_type: str,
        trip_is_trip_valid: bool,
        trip_is_route_valid: bool,
        trip_scheduled_start_stop_id: str | None,
        trip_scheduled_end_stop_id: str | None,
        trip_scheduled_start_time: datetime | None,
        trip_scheduled_end_time: datetime | None,
        vehicle_id: str,
        vehicle_label: str | None,
        vehicle_license_plate: str | None,
        vehicle_wheelchair_accessible: str,
        timestamp: Any,
        latitude: float,
        longitude: float,
        current_stop_sequence: int | None,
        current_status: str,
        congestion_level: str,
        is_active_on_create: bool,
    ) -> str:
        """Queue the upsert of one synchronized vehicle position with its embedded trip descriptor.

        is_active and created_at are only set on creation. A cached-id assignment never overwrites
        an existing assignment type.
        """
        now = self._now()
        fields: dict[str, Any] = {
            "data_source_id": source_id,
            "vehicle_id": vehicle_id,
            "vehicle_label": vehicle_label,
            "vehicle_license_plate": vehicle_license_plate,
            "vehicle_wheelchair_accessible": self._text(vehicle_wheelchair_accessible),
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "current_stop_sequence": current_stop_sequence,
            "current_status": self._text(current_status),
            "congestion_level": self._text(congestion_level),
            "trip.trip_id": trip_id,
            "trip.scheduled_start_stop_id": trip_scheduled_start_stop_id,
            "trip.scheduled_end_stop_id": trip_scheduled_end_stop_id,
            "trip.scheduled_start_time": trip_scheduled_start_time,
            "trip.scheduled_end_time": trip_scheduled_end_time,
            "trip.original_trip_id": trip_original_trip_id,
            "trip.route_id": trip_route_id,
            "trip.start_date": trip_start_date,
            "trip.start_time": trip_start_time,
            "trip.schedule_relationship": self._text(trip_schedule_relationship),
            "trip.is_trip_valid": trip_is_trip_valid,
            "trip.is_route_valid": trip_is_route_valid,
            "updated_at": now,
        }
        on_insert: dict[str, Any] = {"is_active": is_active_on_create, "created_at": now}

        if trip_assignment_type != AssignmentType.MATCH_BY_CACHED_ID:
            fields["trip.assignment_type"] = self._text(trip_assignment_type)
        else:
            on_insert["trip.assignment_type"] = self._text(trip_assignment_type)

        await self.write(
            VEHICLE_POSITIONS_COLLECTION,
            UpdateOne({"_id": str(vehicle_uuid)}, {"$set": fields, "$setOnInsert": on_insert}, upsert=True),
        )

        return "upserted"

    # ------------------------------------------------------------------
    # Dashboard and statistics
    # ------------------------------------------------------------------

    async def count_service_alerts_by_active(self) -> tuple[int, int]:
        active = await self._count(SERVICE_ALERTS_COLLECTION, {"is_active": True})
        inactive = await self._count(SERVICE_ALERTS_COLLECTION, {"is_active": False})

        return active, inactive

    async def count_trip_updates_by_status(self) -> tuple[int, int, int]:
        """Return the number of active (realtime), monitored (no realtime data yet) and inactive trips."""
        active = await self._count(TRIP_UPDATES_COLLECTION, {"is_active": True, "flags": FLAG_REALTIME})
        monitored = await self._count(
            TRIP_UPDATES_COLLECTION,
            {"is_active": True, "stop_event_count": {"$gt": 0}, "flags": {"$ne": FLAG_REALTIME}},
        )
        inactive = await self._count(TRIP_UPDATES_COLLECTION, {"is_active": False, "stop_event_count": {"$gt": 0}})

        return active, monitored, inactive

    async def count_vehicle_positions_by_active(self) -> tuple[int, int]:
        active = await self._count(VEHICLE_POSITIONS_COLLECTION, {"is_active": True})
        inactive = await self._count(VEHICLE_POSITIONS_COLLECTION, {"is_active": False})

        return active, inactive

    async def _list_running_gtfs_trips(self, route_ids: list[str]) -> dict[str, str]:
        """Return GTFS trip id -> route id for trips running right now on the given routes."""
        now_value = self._now()
        stmt = (
            select(GtfsTrip.route_id, GtfsTrip.gtfs_id)
            .where(
                GtfsTrip.route_id.in_(route_ids),
                GtfsTrip.start_time <= now_value,
                GtfsTrip.end_time >= now_value,
            )
            .distinct()
        )

        async with self._postgres.get_session() as db:
            result = await db.execute(stmt)
            return {str(gtfs_id): str(route_id) for route_id, gtfs_id in result.all()}

    async def list_realtime_object_statistics(self, route_ids: list[str]) -> dict[str, Any]:
        """Return active alert count plus route-based trip and vehicle statistics."""
        unique_route_ids = list(dict.fromkeys(route_ids))
        assignment_type_values = [
            assignment_type.value
            for assignment_type in AssignmentType
            if assignment_type != AssignmentType.MATCH_BY_CACHED_ID
        ]

        def _assignment_types(counts: dict[str, int]) -> list[dict[str, int]]:
            return [{assignment_type: counts.get(assignment_type, 0)} for assignment_type in assignment_type_values]

        trips_stats = {
            route_id: {
                "num_running_trips": 0,
                "num_realtime_trips": 0,
                "num_monitored_trips": 0,
                "assignment_types": _assignment_types({}),
            }
            for route_id in unique_route_ids
        }
        vehicles_stats = {
            route_id: {
                "num_running_trips": 0,
                "num_vehicles": 0,
                "assignment_types": _assignment_types({}),
            }
            for route_id in unique_route_ids
        }

        num_alerts = await self._count(SERVICE_ALERTS_COLLECTION, {"is_active": True})

        if unique_route_ids:
            running_trips = await self._list_running_gtfs_trips(unique_route_ids)

            for route_id in running_trips.values():
                trips_stats[route_id]["num_running_trips"] += 1
                vehicles_stats[route_id]["num_running_trips"] += 1

            running_trip_ids = list(running_trips.keys())

            def _event_count(excluded: list[str]) -> dict[str, Any]:
                return {
                    "$size": {
                        "$filter": {
                            "input": {"$ifNull": ["$stop_events", []]},
                            "as": "event",
                            "cond": {"$not": [{"$in": ["$$event.schedule_relationship", excluded]}]},
                        }
                    }
                }

            trip_docs = await self._aggregate(
                TRIP_UPDATES_COLLECTION,
                [
                    {"$match": {"is_active": True, "trip_id": {"$in": running_trip_ids}}},
                    {
                        "$project": {
                            "_id": 0,
                            "trip_id": 1,
                            "assignment_type": 1,
                            "stop_event_count": 1,
                            "num_non_no_data_events": _event_count(["NO_DATA"]),
                            "num_realtime_events": _event_count(["NO_DATA", "ADDED"]),
                        }
                    },
                ],
            )

            trip_assignment_counts: dict[str, dict[str, int]] = {route_id: {} for route_id in unique_route_ids}
            for doc in trip_docs:
                route_id = running_trips[doc["trip_id"]]
                assignment_type = doc.get("assignment_type")

                if assignment_type in assignment_type_values:
                    counts = trip_assignment_counts[route_id]
                    counts[assignment_type] = counts.get(assignment_type, 0) + 1

                if doc.get("stop_event_count", 0) > 0:
                    if doc["num_non_no_data_events"] == 0:
                        trips_stats[route_id]["num_monitored_trips"] += 1

                    if doc["num_realtime_events"] > 0:
                        trips_stats[route_id]["num_realtime_trips"] += 1

            for route_id in unique_route_ids:
                trips_stats[route_id]["assignment_types"] = _assignment_types(trip_assignment_counts[route_id])

            vehicle_docs = await self._find(
                VEHICLE_POSITIONS_COLLECTION,
                {"is_active": True, "trip.trip_id": {"$in": running_trip_ids}},
                projection={"trip.trip_id": 1, "trip.assignment_type": 1},
            )

            vehicle_assignment_counts: dict[str, dict[str, int]] = {route_id: {} for route_id in unique_route_ids}
            for doc in vehicle_docs:
                route_id = running_trips[doc["trip"]["trip_id"]]
                vehicles_stats[route_id]["num_vehicles"] += 1

                assignment_type = doc["trip"].get("assignment_type")
                if assignment_type in assignment_type_values:
                    counts = vehicle_assignment_counts[route_id]
                    counts[assignment_type] = counts.get(assignment_type, 0) + 1

            for route_id in unique_route_ids:
                vehicles_stats[route_id]["assignment_types"] = _assignment_types(vehicle_assignment_counts[route_id])

        return {
            "num_alerts": num_alerts,
            "trips": trips_stats,
            "vehicles": vehicles_stats,
        }

    # ------------------------------------------------------------------
    # Conflict queries
    # ------------------------------------------------------------------

    @staticmethod
    def _not_matching(pattern: str) -> dict[str, Any]:
        return {"$ne": None, "$not": re.compile(pattern)}

    async def _list_informed_entities(
        self,
        entity_filter: dict[str, Any],
        alert_filter: dict[str, Any] | None = None,
    ) -> list[ServiceAlertInformedEntity]:
        pipeline: list[dict[str, Any]] = []
        if alert_filter:
            pipeline.append({"$match": alert_filter})

        pipeline += [
            {"$sort": {"_id": 1}},
            {"$unwind": {"path": "$informed_entities", "includeArrayIndex": "entity_index"}},
            {"$match": entity_filter},
        ]

        alerts: dict[str, ServiceAlert] = {}
        entities: list[ServiceAlertInformedEntity] = []
        for doc in await self._aggregate(SERVICE_ALERTS_COLLECTION, pipeline):
            alert = alerts.get(doc["_id"])
            if alert is None:
                alert = self._alert_from_doc({**doc, "informed_entities": []})
                alerts[doc["_id"]] = alert

            entities.append(
                self._informed_entity_from_doc(doc["informed_entities"], int(doc["entity_index"]) + 1, alert)
            )

        await self._fill_data_source_names(list(alerts.values()))

        return entities

    async def _list_stop_events(
        self,
        event_filter: dict[str, Any],
        trip_filter: dict[str, Any] | None = None,
    ) -> list[StopEvent]:
        pipeline: list[dict[str, Any]] = []
        if trip_filter:
            pipeline.append({"$match": trip_filter})

        pipeline += [
            {"$sort": {"trip_id": 1}},
            {"$unwind": "$stop_events"},
            {"$match": event_filter},
        ]

        trips: dict[str, TripUpdate] = {}
        events: list[StopEvent] = []
        for doc in await self._aggregate(TRIP_UPDATES_COLLECTION, pipeline):
            trip = trips.get(doc["_id"])
            if trip is None:
                trip = self._trip_from_doc({**doc, "stop_events": []}, include_stop_events=False)
                trips[doc["_id"]] = trip

            events.append(self._stop_event_from_doc(doc["stop_events"], trip.trip_id, trip))

        await self._fill_data_source_names(list(trips.values()))

        return events

    async def list_informed_entities_with_invalid_references(self) -> list[ServiceAlertInformedEntity]:
        return await self._list_informed_entities(
            {
                "$or": [
                    {"informed_entities.is_agency_valid": False},
                    {"informed_entities.is_route_valid": False},
                    {"informed_entities.is_stop_valid": False},
                    {"informed_entities.is_trip_valid": False},
                ]
            },
            {"has_invalid_reference": True},
        )

    async def list_stop_events_with_invalid_references(self) -> list[StopEvent]:
        return await self._list_stop_events({"stop_events.is_valid": False}, {"flags": FLAG_INVALID_STOP})

    async def list_trips_with_invalid_references(self) -> list[TripUpdate]:
        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            {"flags": FLAG_INVALID_REFERENCE},
            projection=_NO_STOP_EVENTS,
            sort=[("trip_id", ASCENDING)],
        )

        trips = [self._trip_from_doc(doc, include_stop_events=False) for doc in docs]
        await self._fill_data_source_names(trips)

        return trips

    async def list_stop_events_with_implied_deviation_schedule_relationships(self) -> list[StopEvent]:
        return await self._list_stop_events(
            {
                "stop_events.is_implied_schedule_relationship": True,
                "stop_events.schedule_relationship": {"$in": ["ADDED", "SKIPPED"]},
            },
            {"flags": FLAG_IMPLIED_DEVIATION},
        )

    async def list_stop_events_with_changed_stop_id(self) -> list[StopEvent]:
        return await self._list_stop_events(
            {"$expr": {"$ne": ["$stop_events.stop_id", "$stop_events.original_stop_id"]}},
            {"flags": FLAG_CHANGED_STOP_ID},
        )

    async def list_informed_entities_with_non_global_ids(self, pattern: str) -> list[ServiceAlertInformedEntity]:
        return await self._list_informed_entities(
            {
                "$or": [
                    {f"informed_entities.{field}": self._not_matching(pattern)}
                    for field in ("agency_id", "route_id", "stop_id", "trip_id")
                ]
            }
        )

    async def list_stop_events_with_non_global_ids(self, pattern: str) -> list[StopEvent]:
        return await self._list_stop_events({"stop_events.stop_id": self._not_matching(pattern)})

    async def list_trips_with_non_global_ids(self, pattern: str) -> list[TripUpdate]:
        docs = await self._find(
            TRIP_UPDATES_COLLECTION,
            {"$or": [{"trip_id": self._not_matching(pattern)}, {"route_id": self._not_matching(pattern)}]},
            projection=_NO_STOP_EVENTS,
            sort=[("trip_id", ASCENDING)],
        )

        trips = [self._trip_from_doc(doc, include_stop_events=False) for doc in docs]
        await self._fill_data_source_names(trips)

        return trips

    async def list_stop_events_with_departure_before_arrival(self) -> list[StopEvent]:
        return await self._list_stop_events(
            {
                "stop_events.arrival_time": {"$ne": None},
                "stop_events.departure_time": {"$ne": None},
                "$expr": {"$lt": ["$stop_events.departure_time", "$stop_events.arrival_time"]},
            },
            {"flags": FLAG_DEPARTURE_BEFORE_ARRIVAL},
        )
