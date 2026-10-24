# GTFS ID Cache

Realtime processing validates references against nominal GTFS IDs. To avoid loading these IDs from PostgreSQL on every data source run, they are cached in Redis and checked in bulk.

## Redis Keys

All keys are written by `CachingService`.

| Key | Type | Content |
|---|---|---|
| `echogtfs:data:ids:agency` | SET | Nominal agency IDs |
| `echogtfs:data:ids:route` | SET | Nominal route IDs |
| `echogtfs:data:ids:stop` | SET | Nominal stop IDs |
| `echogtfs:data:ids:trip` | SET | Nominal trip IDs |
| `echogtfs:data:ids:meta:ready` | string | Marker that all sets are complete |
| `echogtfs:data:ids:meta:lock` | string | Rebuild lock (`SET NX EX`, 600 seconds) |

The external-to-nominal trip ID mapping used by matching is a separate key family (`echogtfs:data:trips`, 24 hour TTL), see [matching.md](matching.md).

## Rebuild

`rebuild_gtfs_ids` runs in these situations:

1. Backend startup, only if the ready marker is missing.
2. End of the nominal data load of a GTFS import, always (`force=True`), after the new rows are inserted.
3. Lazily from a processing run, if the marker is missing when IDs are checked.

Flow:

1. Acquire the lock. Wait up to 600 seconds if another process holds it.
2. Unless forced, return if the ready marker exists.
3. Load the IDs per kind from `GtfsRepository.list_gtfs_entity_ids(kinds=...)`.
4. Write each kind into a temporary key with chunked `SADD`.
5. In one `MULTI` transaction, rename the temporary keys over the live keys and set the marker. An empty kind deletes the live key.
6. Release the lock.

Live keys are replaced atomically and never emptied first, so concurrent runs see either the previous or the new complete cache.

## Validation in Processing Runs

`GtfsIdValidator` is created once per run by the processing services.

1. A processor applies identifier mapping to all records first.
2. It calls `prefetch(kind, ids)` per kind. IDs not yet checked are sent to Redis in one pipeline (`SMISMEMBER` plus `EXISTS` on the marker). If the marker is missing, the result is discarded, the cache is rebuilt, and the check is repeated.
3. Confirmed IDs are exposed through `valid_ids()`. Validation helpers in the processing loops use plain set lookups. An ID that was never prefetched counts as unknown.

Trip updates and vehicle positions prefetch `route`, `stop`, and `trip` IDs. Service alerts prefetch the `agency`, `route`, and `stop` IDs of their informed entities.

The nominal trip is still loaded per trip from PostgreSQL where its stop times are needed, which is the only per-trip lookup in the processing loops (`get_gtfs_trip_with_stop_times`, also used by the matching service). Holding all nominal trips in memory is avoided on purpose.

## Manual Alert Editing

`routers/alerts.py` calls `GtfsRepository.list_gtfs_entity_ids` without `kinds` and does not use the cache.
