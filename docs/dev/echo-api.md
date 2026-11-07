# Echo API

The Echo API groups the machine-facing HTTP endpoints of EchoGTFS: the **Push API** (`/api/push`) for feeding event-based data sources and the **Monitoring API** (`/api/monitoring`) for reading system state. Both are meant for accounts with the `API` role.

## Authentication and Authorization

Both APIs use the `CurrentApiUser` dependency (`echogtfs.common.security`, backed by `SecurityService.get_current_api_user`).

1. A client obtains a JWT via `/auth/token` with the credentials of an account.
2. The client sends `Authorization: Bearer <token>` with every request.
3. `CurrentApiUser` accepts any active account: `API`, `USER`, `POWERUSER` and `ADMIN`.

`API` is the lowest role in the hierarchy (`API` < `USER` < `POWERUSER` < `ADMIN`). `API` accounts can only use the Push and Monitoring APIs; the regular management endpoints (`CurrentUser` and above) and the web UI reject them.

Common error responses for both APIs:

| HTTP | Detail |
|---|---|
| `401` | `error.401_unauthorized`: missing or invalid token. |
| `403` | `error.403_permission`: inactive account or insufficient role. |

## Monitoring API

Read-only router `routers/monitoring.py`, mounted at `/api/monitoring`. It has no feature switch and no settings.

| Endpoint | Query parameter | Response model | Description |
|---|---|---|---|
| `GET /api/monitoring/system` | – | `MonitoringSystemResponse` | App version, instance name (`app_title` setting), `status` and the filter values (active data sources, GTFS routes). |
| `GET /api/monitoring/statistics` | `routeId` (optional) | `MonitoringStatisticsResponse` | Static GTFS statistics and realtime statistics. |
| `GET /api/monitoring/conflicts` | `datasourceId` (optional) | `MonitoringConflictsResponse` | Current conflicts in the system. |

### Implementation Notes

- `/system` lists only active data sources and up to 10000 GTFS routes. The version comes from `echogtfs._version`.
- `/statistics` combines:
  - static data from `GtfsRepository` (`list_gtfs_object_statistics`, `list_gtfs_operation_day_dates`) plus the `gtfs_import_time` and `gtfs_import_status` app settings,
  - realtime data from `RealtimeRepository.list_realtime_object_statistics`, restricted to `routeId` if given, otherwise to all routes. It reports alert counts, per-route trip counts (running, realtime, monitored), vehicle counts and assignment-type counts (`AssignmentType`).
- `/conflicts` delegates to `ConflictExportService.export(filter_datasource_id=...)`.

## Push API

Router `routers/push.py`, mounted at `/api/push`. Endpoint: `POST /api/push/datasource/{source_id}` with the raw payload as body.

### Configuration

Push API settings are persisted in `sys_app_settings`:

| Setting Key | Default | Meaning |
|---|---|---|
| `push_api_enabled` | `false` | Global feature switch for push endpoint. |

### Authentication Flow

1. `CurrentApiUser` validates the token; a missing or invalid token returns `401` (`error.401_unauthorized`).
2. `check_push_api_enabled()` loads the settings; if `push_api_enabled` is `false`, it returns `403` (`error.push_api_disabled`).

### Execution Flow

1. Router reads `payload` bytes and `content_type`.
2. Router calls `DatasourceSchedulerService.run_push_task(source_id, payload, content_type)`.
3. Scheduler checks source existence (`404` if missing).
4. Scheduler checks source activity (`403` if inactive).
5. Scheduler checks `execution_type` is `event_based` (`403` otherwise).
6. Scheduler checks GTFS import status (`409` if GTFS import is running).
7. Scheduler enforces per-source concurrency via in-memory running-set (`409` if already running).
8. Scheduler executes sync in process pool (`_run_datasource_push_process`).
9. Child process revalidates source existence/activity/execution type.
10. Child process instantiates adapter and runs `sync_records_from_payload(...)`.
11. Scheduler updates `last_run_at` and clears running-set state in `finally`.
12. Router maps `PushServiceError` to HTTP response.

### Status Code Mapping

| HTTP | Detail/Error |
|---|---|
| `200` | Success, returns sync counters (`added`, `updated`, `deleted`). |
| `401` | `error.401_unauthorized`: missing or invalid token. |
| `403` | `error.403_permission` (inactive account), `error.push_api_disabled`, `error.source_not_active`, or `error.source_not_event_based`. |
| `404` | `error.source_not_found`. |
| `409` | `error.gtfs_import_running` or `error.source_already_running`. |
| `422` | Adapter payload-validation errors. |
| `500` | `error.push_failed` for unexpected scheduler/runtime failures. |
| `503` | `error.scheduler_closing` during shutdown window. |

### Adapter Contract for Push

`DatasourceInterface` defines dedicated payload-based methods:

- `_fetch_records_from_payload(payload, content_type)`
- `sync_records_from_payload(payload, content_type, ...)`

### Logging Behavior

Push-triggered adapter logs are written through `DatalogService` into `sys_data_source_logs`.

- `request_url` for push-triggered entries is stored as `""`.
- `request_headers` can contain pushed `Content-Type`.
- `response_content` dump follows `DataSource.log_dumps`.
