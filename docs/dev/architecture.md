# EchoGTFS System Architecture

## Overview

EchoGTFS is a self-hosted, containerized web application for creating and managing GTFS-Realtime data. It combines a manually authored data with an automated import pipeline that can pull data from external data sources (GTFS-RT feeds, SIRI SX, SIRI Lite). The resulting data are published as a standards-compliant GTFS-Realtime feed.

## Container Layout

The application is composed of three Docker containers defined in `docker-compose.yml`:

- `backend`: Python/FastAPI HTTP service, port 8000 (internal only).
- `frontend`: NGINX web server that serves the static single-page application and reverse-proxies `/api` requests to the backend. Exposed on the host at the port defined by `FRONTEND_PORT` (default 80).
- `database`: PostgreSQL 16. Accessible only to the backend container.

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
- Pydantic / pydantic-settings: Data validation and environment configuration
- PyJWT + bcrypt: Token creation and password hashing
- slowapi: Rate limiting (wraps limits library)
- APScheduler: Cron-based job scheduling for GTFS imports and data source polling
- httpx: Async HTTP client used by adapters
- google.protobuf: Protobuf serialization for GTFS-RT output (locally compiled with `protoc`)

## Frontend Technology Stack

- NGINX for serving static files and proxying `/api`
- Vanilla JavaScript (ES6+), no framework, no build step
- HTML5 single-page application with multiple view divs

## Application Startup Sequence

1. `main.py` `lifespan` context manager runs at startup.
3. `AlembicMigrationService` applies all pending numbered SQL migrations.
4. If the `sys_users` table is empty, a first superuser is created from `FIRST_SUPERUSER*` environment variables.
5. Scheduled jobs are configured:
   - `GtfsImportService.schedule_from_settings`: Reads the `gtfs_cron` key from the `app_settings` table and registers a GTFS Static feed import job.
   - `DatasourceSchedulerService.schedule_all_data_sources`: Queries all active `DataSource` rows whose `cron` column is set and registers one polling job per data source. Cron expressions are stored per data source in the `data_sources` table, not in `app_settings`.
   - `CleanupService.schedule_from_settings`: Reads cleanup configuration from `app_settings` and registers the alert expiry cleanup job.
6. FastAPI app starts accepting requests.

## API Routers

Each router file under `routers/` maps to a URL prefix registered in `main.py`:

| File | Prefix | Description |
|---|---|---|
| `auth.py` | `/api/auth` | OAuth2 password-flow login, returns JWT |
| `alerts.py` | `/api/alerts` | ServiceAlert CRUD |
| `sources.py` | `/api/sources` | External data source CRUD and manual trigger |
| `users.py` | `/api/users` | User management (superuser only) |
| `settings.py` | `/api/settings` | Application settings key-value store |
| `gtfs.py` | `/api/gtfs` | GTFS Static feed management and entity lookup |
| `realtime.py` | `/api/realtime` | GTFS-RT protobuf and JSON feed output |

The API routers are meant to have as less logic as possible and only do the I/O networking stuff, mainly communication to the frontend, but also provision of GTFS-RT data.

## Services
Services are meant to encapsulate all the logic which is not a) direct database access and b) not networking or API related code. All services are located in `backend/src/echogtfs/services` and the corresponding sub-directories.

### Single-Instance Services
Most services are instantiated when they're used in the code. Some special services are meant to be single-instance services used globally around the whole python process. These services are currently:

- `SecurityService` (related for security related issues)
- `DatasourceSchedulerService` (responsible for scheduling datasources by their cron job)

The single instance services are initialized in the `main.py` module during the startup sequence of the application and also used across other modules and services.

Other services initialized in `main.py` are:

- `AlembicMigrationService` (responsible for running the Alembic migrations)
- `GtfsImportService` (responsible for loading and updating the GTFS static nominal data)
- `CleanupService` (responsible for cleanup of **internal** deprecated GTFS-RT entities and datasource logs)

Those services are not designed as single-instance service but only used by `main.py`.

## Data Model

### Core Tables

Tables are split into `sys_` tables which are internal application tables, `gtfs_` tables for holding the nominal reference data and `realtime_` tables for the reatime data.

### Database Migrations

Migrations are generated for running with Alembic. All pending migrations are applied during application startup.

### Repositories

There're several repositories for structured database access. The repositories are grouped into domain specific repositories. The repositories are initialized in the `main.py` module during application lifecycle startup. Current repositories are:

- `SystemRepository`: responsible for general database access especially for `sys_` tables
- `GtfsRepository`: reponsible for GTFS nominal data access of `gtfs_` tables
- `RealtimeRepository`: responsible for GTFS-RT data access of `realtime_` tables

Each repository has an interface defined for testing purposes.

## External Data Sources

External datasources live in `backend/src/echogtfs/datasources` and inherit from `DatasourceBase` (`base.py`). The `DatasourceBase` encapsulates all main logic for calling the mapping service, the enrichment service and the finally the matching if the entities could not be matched to a GTFS entity by ID.

The specific datasource implementation encapsulates source related specifics like request / response patterns, content and I/O handling, and datasource related parameters.

For reading and parsing the external data, the transformers are implemented in `backend/src/echogtfs/datasources/transformers`. There's one transformer interface for each GTFS-RT entity and several specific transformer implementations. The transformers are kept as generic as possible, however, proprietary transformers may be required to include arbitrary data.

Compared to other cron-based tasks (e.g. GTFS import, cleanup), the datasources **can be defined with a second based cron expression with 6 places** like this:

`*/30 * * * * *`

This cron expression would run the datasource every 30 seconds (on ':00 and on ':30).

## GTFS-Realtime Feed

The GTFS-RT endpoint is the public output endpoint. It serializes realtime data to GTFS-RT compliant protobuf stream. The endpoint also supports a `?format=json` query parameter for JSON output. 

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
