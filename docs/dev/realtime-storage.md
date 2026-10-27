# Realtime Storage (MongoDB)

Realtime objects are stored in MongoDB as hierarchical documents. PostgreSQL holds only the `sys_` and `gtfs_` tables. The semantic relations between the realtime models are described in [realtime.md](realtime.md).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MONGO_URL` | `mongodb://mongo:27017/?replicaSet=rs0` | MongoDB connection string. Must point at a replica set. |
| `MONGO_DATABASE` | `echogtfs` | Database that holds the realtime collections. |

Transactions and snapshot reads require a replica set. The compose `mongo` service (`mongo:7`) runs as a single-node replica set `rs0`. Its healthcheck initiates the replica set if needed, and `backend` starts only after the service is healthy.

## Collections

The three collections have no relations to each other. Names are defined in `mongo_indexes.py`.

| Collection | Document | Embedded structures |
|---|---|---|
| `realtime_service_alerts` | `ServiceAlert` | `translations`, `active_periods`, `informed_entities` |
| `realtime_trip_updates` | `TripUpdate` | `stop_events` |
| `realtime_vehicle_positions` | `VehiclePosition` | `trip` (`VehicleTripDescriptor`) |

Field names match the dataclasses in `realtime_models.py`. The repository sets back-references on read (`stop_event.trip`, `informed_entity.alert`, `trip.vehicle`) and derives translation, period and informed-entity IDs from the array position.

### Derived Fields

The repository maintains these fields on write so that list, statistics, and conflict queries need no scans.

| Collection | Field | Meaning |
|---|---|---|
| `realtime_service_alerts` | `first_start`, `max_end_time` | Earliest period start and latest period end, used for expiry. |
| `realtime_service_alerts` | `has_invalid_reference` | True if any informed entity has an invalid reference. |
| `realtime_trip_updates` | `stop_event_count` | Number of embedded stop events. |
| `realtime_trip_updates` | `flags` | Subset of `invalid_reference`, `invalid_stop`, `implied_deviation`, `changed_stop_id`, `departure_before_arrival`, `realtime`, set by `_trip_flags`. |

### Vehicle Trip Descriptor

The embedded `trip` carries `trip_id` (matched ID), `original_trip_id`, `route_id`, `start_date`, `start_time`, `schedule_relationship`, `assignment_type`, the `scheduled_*` anchors, `is_trip_valid`, and `is_route_valid`. A vehicle has no validity or assignment type of its own. `VehiclePosition.is_valid` returns the `is_valid` of its trip descriptor, which is `is_trip_valid and is_route_valid`, like for trip updates. Matching works as for trip updates, see [matching.md](matching.md).

### Activation Flag

`is_active` is set once when a document is created by a data source sync (`$setOnInsert`, together with `created_at`). Afterwards only a user action changes it. All other synchronized fields are written with `$set`.

## Indices

Indices are created idempotently by `RealtimeRepository.initialize()` at startup, from `index_definitions()`.

| Collection | Index | Purpose |
|---|---|---|
| `realtime_service_alerts` | `data_source_id` | Per-source reads and deletes. |
| | `is_active` | Export. |
| | `max_end_time`, `first_start` | Expiry and period queries. |
| | `has_invalid_reference` (partial, only `true`) | Conflict and monitoring queries. |
| `realtime_trip_updates` | `trip_id` (unique) | One trip update per matched trip ID. |
| | `is_active`, `created_at`, `trip_id` | Export order. |
| | `data_source_id` | Per-source reads and deletes. |
| | `updated_at` (descending) | Cleanup. |
| | `flags` (multikey) | Invalid trips and stop events, statistics, conflicts. |
| | `start_date`, `start_time`, `trip_id` | Sorted lists. |
| `realtime_vehicle_positions` | `trip.trip_id` (unique) | One vehicle per matched trip ID, join to trip updates. |
| | `is_active` | Export. |
| | `data_source_id` | Per-source reads and deletes. |
| | `updated_at` (descending) | Cleanup. |

## Transactions and Snapshots

`MongoRepositoryBase` provides the two access patterns. The `RealtimeProcessingDispatcherService` and the exports use them through the repository.

### Write Transactions

`transaction()` is scoped to the current async context. A nested call by the same repository joins the running transaction. The `isolation_level` argument exists only for parity with the SQL repositories and is ignored.

1. Per-record sync methods (for example `update_trip_update_from_sync`) do not write directly. They append operations to a buffer of the current transaction.
2. Before any read inside the same transaction, `read_session()` flushes the buffer, so the read sees the run's own writes. A flush starts the MongoDB transaction if it has not started yet. Operations are sent as ordered bulk writes per collection.
3. At the end of the block, the remaining buffer is flushed and the transaction is committed. An `UnknownTransactionCommitResult` is retried up to five times. A run without prior flush is written with `with_transaction`.
4. On an exception, the transaction is aborted and nothing becomes visible.

Delete and bulk update methods return `0` while their operation is buffered, because the affected count is unknown before the flush. Outside a transaction, writes execute immediately.

### Snapshot Reads

`snapshot()` opens a session with snapshot read concern. All reads inside the block see the committed data as of the first read. The three export methods use it:

- `get_realtime_service_alerts`
- `get_realtime_trips`: reads the active trip updates and the vehicle positions inside one snapshot and attaches each vehicle by `trip.trip_id`.
- `get_realtime_vehicles`

An export therefore never sees a partially applied data source run, and a run that commits while an export is reading does not affect that export. Writers are not blocked, and the 60 second transaction lifetime does not apply.

## Data Source Names

`data_source_name` is a plain field filled by the repository from one PostgreSQL query per list, toggle, or conflict read. Sync and export paths do not query it.

## Cleanup and Source Deletion

- `CleanupService` deletes expired trip updates by `updated_at` and expired vehicle positions by `updated_at` independently of each other.
- Deactivating or deleting a data source calls the `delete_*_for_data_source` repository methods for all three collections, see [datasources.md](datasources.md).

## Migration From PostgreSQL

Alembic revision `0020_drop_realtime_tables` drops the former PostgreSQL realtime tables and their enums. The downgrade recreates them empty. Existing data is not migrated automatically.
