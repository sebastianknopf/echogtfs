# Push API

## Configuration

Push API settings are persisted in `sys_app_settings`:

| Setting Key | Default | Meaning |
|---|---|---|
| `push_api_enabled` | `false` | Global feature switch for push endpoint. |
| `push_api_username` | `""` | Optional Basic Auth username. |
| `push_api_password` | `""` | Optional hashed Basic Auth password. |

Password handling follows the same pattern as GTFS-RT credentials:

1. `PUT /api/settings` hashes non-empty passwords before storing.
2. If both username and password are empty, both are cleared.
3. If username is set and password is empty string, existing hash is kept.

## Authentication Flow

`check_push_api_auth()` executes before endpoint logic:

1. Load push settings from `sys_app_settings`.
2. If `push_api_enabled` is `false`, return `403` (`error.push_api_disabled`).
3. If username or password is missing, allow request without Basic Auth.
4. If both are configured, require `Authorization: Basic ...`.
5. Decode credentials and verify password hash via `SecurityService.verify_password`.
6. Return `422` (`error.invalid_credentials`) on invalid credentials.

## Execution Flow

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

## Status Code Mapping

| HTTP | Detail/Error |
|---|---|
| `200` | Success, returns sync counters (`added`, `updated`, `deleted`). |
| `401` | Missing Basic Auth when credentials are configured. |
| `403` | `error.push_api_disabled`, `error.source_not_active`, or `error.source_not_event_based`. |
| `404` | `error.source_not_found`. |
| `409` | `error.gtfs_import_running` or `error.source_already_running`. |
| `422` | `error.invalid_credentials` or adapter payload-validation errors. |
| `500` | `error.push_failed` for unexpected scheduler/runtime failures. |
| `503` | `error.scheduler_closing` during shutdown window. |

## Adapter Contract for Push

`DatasourceInterface` defines dedicated payload-based methods:

- `_fetch_records_from_payload(payload, content_type)`
- `sync_records_from_payload(payload, content_type, ...)`

`DatasourceBase` provides shared sync orchestration and payload helpers. The scheduler injects `_execution_type` into adapter config before adapter construction.

Validation behavior:

- For `time_based` sources, polling-specific fields (for example endpoint URLs) remain required.
- For `event_based` sources, polling-specific fields are optional.

## Logging Behavior

Push-triggered adapter logs are written through `DatalogService` into `sys_data_source_logs`.

- `request_url` for push-triggered entries is stored as `""`.
- `request_headers` can contain pushed `Content-Type`.
- `response_content` dump follows `DataSource.log_dumps`.

## Relation to Manual Run Endpoint

`POST /api/sources/{source_id}/run` is restricted to time-based sources.

- Event-based sources return `403` (`error.source_event_based`) on manual run attempts.
- Frontend hides the run button for event-based sources.
