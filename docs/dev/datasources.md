# Data Sources

## Purpose

Data sources connect EchoGTFS to external realtime feeds and convert received data into records that the application can validate and synchronize as GTFS-Realtime service alerts, trip updates, or vehicle positions. A persisted source identifies its adapter type and configuration, and controls when that adapter is invoked.

The registry in `echogtfs.datasources` maps each stored source type to its concrete adapter class. The scheduler loads the source record, adds execution context to its configuration, and runs the adapter. Datasource processing and persistence details for differential and incremental data are documented in [differential-incremental.md](differential-incremental.md).

## Integration With the Application

Source records are stored in the `data_sources` table, including each source's cron expression; cron configuration is not stored in `app_settings`. `sources.py` manages source configuration and execution through `/api/sources`. Public event-based execution is provided by `push.py` at `/api/push`, and `internal_execute.py` handles the internal callback at `/internal/execute`. Their endpoint contracts are documented in [push-api.md](push-api.md) and [internal-push-api.md](internal-push-api.md). The SIRI consumer, subscription lifecycle, and network boundaries are described in [siricomservice.md](siricomservice.md).

At application startup, `main.py` initializes the single-instance `DatasourceSchedulerService` and asks it to register scheduled jobs for active sources with cron expressions. `CleanupService` removes datasource logs older than 24 hours.

## Processing Architecture

The processing flow separates transport and source-specific parsing from record transformation and realtime synchronization:

1. The scheduler or a push endpoint selects the datasource implementation through the registry.
2. The datasource validates its configuration, performs the external request or accepts the supplied payload, and parses the source format.
3. The datasource selects and invokes a transformer for the configured format and record type. Transformers convert decoded source data into the internal record envelope:

   ```python
   {
       "record_type": "service_alerts" | "trip_updates" | "vehicle_positions",
       "records": [...],
   }
   ```

   A transformer has no responsibility for datasource configuration, network requests, or database persistence.
4. `DatasourceBase` normalizes the envelope and passes the records to `RealtimeProcessingDispatcherService`.
5. The dispatcher selects the entity-specific processing service. That layer applies identifier mapping, enrichment, validity checks, and matching where required, then synchronizes records through the repositories within a transaction.

The concrete transformer return contract and record shapes are documented in [transformation.md](transformation.md). Trip matching and stop propagation are described in [matching.md](matching.md) and [stop-propagation.md](stop-propagation.md).

`RealtimeProcessingDispatcherService` wraps record synchronization in a transaction provided by the realtime repository, so each synchronization operation is atomic. Writes are buffered and committed together, and the GTFS-RT exports read snapshots, so they never see an uncommitted run. Details are in [realtime-storage.md](realtime-storage.md). Nominal GTFS IDs are validated against a Redis cache instead of being loaded per run, see [gtfs-id-cache.md](gtfs-id-cache.md).

## Base Types

### DatasourceBase

`DatasourceBase` is the common abstract base for every datasource adapter. It implements the shared execution path and requires concrete adapters to provide configuration validation and record fetching. Adapters also provide payload-based parsing for push execution and a configuration schema for the UI.

The base class supplies shared behavior such as source context injection, request logging, common XML parsing helpers, and realtime dispatcher integration. A concrete adapter owns the external protocol details and chooses how its decoded payload is transformed.

### SubscriptionDatasourceBase

`SubscriptionDatasourceBase` extends `DatasourceBase` for adapters that can describe a managed subscription. It adds the abstract `get_subscription_params()` method; the method returns datasource-specific configuration for the subscription manager. The subscription manager adds the datasource ID reference and internal HTTP sink.

The base type alone does not select execution mode. A persisted `subscription_based` execution type selects subscription lifecycle management, and the adapter must also inherit `SubscriptionDatasourceBase` to supply its configuration. Currently, SIRI-ET, SIRI-SX, SIRI-VM, and VDV454 implement this contract; SIRI-Lite and GTFS-RT use `DatasourceBase` directly.

## Execution Modes

`DataSourceExecutionType` is the authoritative selector for how an active datasource is triggered:

| Value | Trigger | Scheduler and manual execution behavior |
|---|---|---|
| `time_based` | Cron schedule or manual run | The scheduler runs the source according to its cron expression. Manual run is available. |
| `event_based` | Public push API | No cron polling. The public push endpoint accepts this mode; manual run is unavailable. Polling-only adapter fields can be optional. |
| `subscription_based` | Managed SIRI subscription | No cron polling. The source receives payloads through the internal push endpoint; public push and manual run reject it. |

The public and internal push endpoint contracts are documented in [push-api.md](push-api.md) and [internal-push-api.md](internal-push-api.md). Subscription setup and callback delivery are documented in [siricomservice.md](siricomservice.md).

The frontend clears cron values for event-based and subscription-based sources. It also sets differential updates to true and disables that switch for subscription-based sources. Differential synchronization behavior is documented in [differential-incremental.md](differential-incremental.md).

## Scheduling and Worker Execution

`DatasourceSchedulerService` registers cron jobs for active sources with a cron expression. It supports five-field minute-based and six-field second-based cron expressions. It skips subscription-based sources and logs a warning rather than polling them. Scheduled source runs execute in a process pool. Each worker process creates its own repository instances, including the MongoDB client of the realtime repository, from the same connection settings.

| Configuration | Default | Meaning |
|---|---|---|
| `DATASOURCE_PROCESS_POOL_SIZE` | `2` | Maximum number of worker processes used for source execution. |

The scheduler prevents overlapping executions for the same source. Cron and push-triggered runs use shared per-source running state, so concurrent activity cannot process the same source at once. Scheduled imports are also skipped while a GTFS import is running.

The scheduler tracks active runs in a local set and shared application state, and clears both states when a run finishes. Deactivation removes the source's scheduled job, then `wait_for_source_idle(...)` waits for active cron or push-triggered runs to finish before deleting that source's realtime alerts, trips, and vehicles. If a run does not finish within 300 seconds, the source update returns `409` and leaves the realtime objects in place. Deactivation does not start another run.

## Monitoring Compatibility

Monitoring can only report invalid realtime entities that remain available for inspection. Configure sources to disable invalid entities or references rather than discard them; discarded entities are not available to the monitoring API.
