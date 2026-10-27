# EchoGTFS System Architecture

## Overview

EchoGTFS is a self-hosted, containerized web application for creating and managing GTFS-Realtime data. It combines manually authored and imported data and publishes the result as a standards-compliant GTFS-Realtime feed.

## Container Layout

The application is composed of five core Docker services and one optional service defined in `docker-compose.yml`:

- `backend`: Python/FastAPI HTTP service, port 8000 (internal only).
- `frontend`: NGINX web server that serves the static single-page application and reverse-proxies `/api` requests to the backend. Exposed on the host at the port defined by `FRONTEND_PORT` (default 80).
- `database`: PostgreSQL 16. Holds system and nominal GTFS data. Accessible only to the backend container.
- `mongo`: MongoDB 7 single-node replica set. Holds the realtime objects, see [realtime-storage.md](realtime-storage.md). Accessible only to the backend container.
- `redis`: Redis service used for caching and event streaming inside the application, including the nominal GTFS ID cache described in [gtfs-id-cache.md](gtfs-id-cache.md).
- `siricomservice`: Optional SIRI consumer communication service for managed SIRI subscriptions. Compose starts it only when the `siripubsub` profile is enabled.

All runtime configuration is injected via environment variables. The canonical source of variable names is `.env.example`.

## Directory Structure

```
echogtfs/
  backend/
    src/echogtfs/          # Code base for backend
  frontend/
    index.html             # Code base for frontend
```

## Backend Technology Stack

- Python >= 3.11
- FastAPI: HTTP framework and dependency injection
- SQLAlchemy (async): ORM and query builder
- asyncpg: Async PostgreSQL driver
- pymongo (async client): MongoDB driver for the realtime collections
- Pydantic / pydantic-settings: Data validation and environment configuration
- PyJWT + bcrypt: Token creation and password hashing
- slowapi: Rate limiting (wraps limits library)
- APScheduler: Cron-based job scheduling for GTFS imports and scheduled jobs
- httpx: Async HTTP client used by adapters
- google.protobuf: Protobuf serialization for GTFS-RT output (locally compiled with `protoc`)

## Frontend Technology Stack

- NGINX for serving static files and proxying `/api`
- Vanilla JavaScript (ES6+), no framework, no build step
- HTML5 single-page application with multiple view divs

## Application Startup Sequence

1. `main.py` `lifespan` context manager runs at startup.
2. `AlembicMigrationService` applies all pending numbered SQL migrations.
3. The system, GTFS, and realtime repositories are initialized. `RealtimeRepository.initialize()` checks the MongoDB connection and creates the realtime indices.
4. `CachingService` is initialized and builds the nominal GTFS ID cache if it is not present yet.
5. If the `sys_users` table is empty, a first superuser is created from `FIRST_SUPERUSER*` environment variables.
6. Scheduled jobs are configured:
   - `GtfsImportService.schedule_from_settings`: Reads the `gtfs_cron` key from the `app_settings` table and registers a GTFS Static feed import job.
   - `CleanupService.schedule_from_settings`: Reads cleanup configuration from `app_settings` and registers the alert expiry cleanup job.
7. FastAPI app starts accepting requests.

## API Routers

Each router file under `routers/` maps to a URL prefix registered in `main.py`:

| File | Prefix | Description |
|---|---|---|
| `auth.py` | `/api/auth` | OAuth2 password-flow login, returns JWT |
| `dashboard.py` | `/api/dashboard` | Dashboard data endpoint |
| `alerts.py` | `/api/alerts` | ServiceAlert CRUD |
| `trips.py` | `/api/trips` | Authenticated realtime trip listing and activation control |
| `vehicles.py` | `/api/vehicles` | Authenticated realtime vehicle listing and activation control |
| `sources.py` | `/api/sources` | See [datasources.md](datasources.md) |
| `users.py` | `/api/users` | User management (superuser only) |
| `settings.py` | `/api/settings` | Application settings key-value store |
| `gtfs.py` | `/api/gtfs` | GTFS Static feed management and entity lookup |
| `systemcopy.py` | `/api/systemcopy` | Superuser system configuration export and import |
| `realtime.py` | `/api` | Public GTFS-RT feed output in protobuf or JSON format |
| `push.py` | `/api/push` | See [push-api.md](push-api.md) |
| `internal_execute.py` | `/internal/execute` | See [internal-push-api.md](internal-push-api.md) |
| `service.py` | `/api/service/siri` | Authenticated SIRI service liveness check |
| `capabilities.py` | `/api/capabilities` | Authenticated capability discovery, including optional service readiness |

The API routers are meant to have as less logic as possible and only do the I/O networking stuff, mainly communication to the frontend, but also provision of GTFS-RT data.

## Services
Services are meant to encapsulate all the logic which is not a) direct database access and b) not networking or API related code. All services are located in `backend/src/echogtfs/services` and the corresponding sub-directories.

### Single-Instance Services
Most services are instantiated when they're used in the code. Some special services are meant to be single-instance services used globally around the whole python process. These services are currently:

- `SecurityService` (related for security related issues)
- `SiriSubscriptionService` (consumer API client for subscription lifecycle, status, readiness, and liveness)
- `CachingService` (abstraction layer for redis access: trip ID matching cache and nominal GTFS ID cache)

The single instance services are initialized in the `main.py` module during the startup sequence of the application and also used across other modules and services.

Other services initialized in `main.py` are:

- `AlembicMigrationService` (responsible for running the Alembic migrations)
- `GtfsImportService` (responsible for loading and updating the GTFS static nominal data)
- `CleanupService` (responsible for scheduled cleanup tasks)

Those services are not designed as single-instance service but only used by `main.py`.

## Data Model

### Core Tables

PostgreSQL tables are split into `sys_` tables which are internal application tables and `gtfs_` tables for holding the nominal reference data.

The realtime data is not stored in PostgreSQL. It lives in the MongoDB collections `realtime_service_alerts`, `realtime_trip_updates` and `realtime_vehicle_positions`, described in [realtime-storage.md](realtime-storage.md).

### Database Migrations

Migrations are generated for running with Alembic. All pending migrations are applied during application startup.

### Repositories

There're several repositories for structured database access. The repositories are grouped into domain specific repositories. The repositories are initialized in the `main.py` module during application lifecycle startup. Current repositories are:

- `SystemRepository`: responsible for general database access especially for `sys_` tables
- `GtfsRepository`: reponsible for GTFS nominal data access of `gtfs_` tables
- `RealtimeRepository`: responsible for GTFS-RT data access of the realtime MongoDB collections

Each repository has an interface defined for testing purposes.

`SystemRepository` and `GtfsRepository` derive from `PostgresRepositoryBase` and open a separate database connection on demand for each query. `RealtimeRepository` derives from `MongoRepositoryBase` and uses `PostgresRepositoryBase` only for data source names and statistics on nominal GTFS trips. Transactions, snapshot reads and indices of the realtime repository are described in [realtime-storage.md](realtime-storage.md). Realtime synchronization is described in [datasources.md](datasources.md).

## Data Sources

Data source behavior and its integration with the rest of the system are documented in [datasources.md](datasources.md).

## GTFS-Realtime Feed

The GTFS-RT endpoint is the public output endpoint. It serializes realtime data to GTFS-RT compliant protobuf stream. Each feed is built from one snapshot read of the realtime collections, so it contains only fully committed data source runs, see [realtime-storage.md](realtime-storage.md). The endpoint also supports a `?format=json` query parameter for JSON output. 

Optional Basic Auth can be enabled for the realtime endpoint by storing `gtfs_rt_username` and `gtfs_rt_password` in `app_settings`.

## Frontend Single-Page Application

`index.html` contains all view markup as `div.view[data-view]` elements. Only one view is visible at a time. JavaScript modules are loaded as plain `<script>` tags in dependency order:

1. `languages.js`: Defines `window.translations` with all localization strings.
2. `localization.js`: Defines the `i18n` module; requires `languages.js`.
3. `core.js`: API client, UI utilities, token handling; requires `localization.js`.
4. Domain modules: `alerts.js`, `sources.js`, `accounts.js`, `settings.js`, `main.js`.

The frontend stores the JWT in `localStorage` under the key `auth-token`. The `core.js` API client automatically injects the `Authorization: Bearer` header and handles 401 responses by clearing local state and reloading.

## Cross-Cutting Concerns

### Rate Limiting

The `/api/auth/token` endpoint is rate-limited using `slowapi`. The limit is configured via the `LOGIN_RATE_LIMIT` environment variable (default `10/minute`). The `limiter` instance is defined in `extensions.py` and registered with the FastAPI app in `main.py`.

### CORS

CORS is configured via the `CORS_ORIGINS` environment variable (comma-separated list of allowed origins). The `CORSMiddleware` is registered in `main.py`. An empty value means no cross-origin requests are allowed, which is the correct default when the frontend and backend share the same origin through the NGINX proxy.

### Logging

All application logging goes through Python's standard `logging` module using the `uvicorn.error` logger name. Log level is controlled by the `DEBUG` environment variable.

## Monitoring-API

The monitoring API is designed to open access of EchoGTFS backend to external monitoring and dashboard tools. Its main purpose is to provide a controlled access to the actual realtime availability state and conflicts detected in the system under following circumstances:

- The API **always provides access to the current status of the system**, there's no overview over historical conflicts and status values
- The API provides access to the **conflicts within the system**, conflicts in the incoming base data are currently **not monitored** and available
- Configuration that determines which invalid entities are visible to monitoring is described in [datasources.md](datasources.md).

The statistics are completely computed by the `RealtimeRepository`. Most of the conflict detection work is also done in the `RealtimeRepository`, however, packaging and final checks on the conflicts as well as uniquifying them is done in the separate `ConflictExportService` class and then handed to the API endpoint.
