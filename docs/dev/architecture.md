# EchoGTFS System Architecture

## Overview

EchoGTFS is a self-hosted, containerized web application for creating and managing GTFS-Realtime ServiceAlerts. It combines a manually authored alert workflow with an automated import pipeline that can pull alerts from external data sources (GTFS-RT feeds, SIRI SX, SIRI Lite). The resulting alerts are published as a standards-compliant GTFS-Realtime feed.

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
    src/echogtfs/          # All Python application code
      routers/             # FastAPI route handlers (one file per resource)
      services/            # Business logic: import, cleanup, scheduling
        adapters/          # External data source adapters
      migrations/          # Numbered SQL migration files (001.sql, ...)
      main.py              # Application entry point, middleware registration
      config.py            # Pydantic Settings configuration model
      database.py          # SQLAlchemy async engine and session factory
      models.py            # SQLAlchemy ORM models
      schemas.py           # Pydantic request/response schemas
      security.py          # Password hashing, JWT, FastAPI dependencies
      migrations.py        # Migration runner
    tests/                 # unittest-based test suite
  frontend/
    index.html             # Single HTML file; all views rendered here
    js/                    # ES6 JavaScript modules (no bundler)
    css/app.css            # All styles; single stylesheet
    nginx.conf             # NGINX configuration
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
- google.protobuf: Protobuf serialization for GTFS-RT output

## Frontend Technology Stack

- Vanilla JavaScript (ES6+), no framework, no build step
- HTML5 single-page application with multiple view divs
- NGINX for serving static files and proxying `/api`

## Application Startup Sequence

1. `main.py` `lifespan` context manager runs at startup.
2. SQLAlchemy `Base.metadata.create_all` creates any missing tables.
3. `AlembicMigrationService` applies all pending numbered SQL migrations.
4. If the `sys_users` table is empty, a first superuser is created from `FIRST_SUPERUSER*` environment variables.
5. Scheduled jobs are configured:
   - `schedule_import_from_cron`: Reads the `gtfs_cron` key from the `app_settings` table and registers a GTFS Static feed import job.
   - `schedule_all_data_sources`: Queries all active `DataSource` rows whose `cron` column is set and registers one polling job per data source. Cron expressions are stored per data source in the `data_sources` table, not in `app_settings`.
   - `schedule_cleanup_from_settings`: Reads cleanup configuration from `app_settings` and registers the alert expiry cleanup job.
6. FastAPI app starts accepting requests.

## API Routers

Each router file under `routers/` maps to a URL prefix registered in `main.py`:

| File | Prefix | Description |
|---|---|---|
| `auth.py` | `/api/auth` | OAuth2 password-flow login, returns JWT |
| `alerts.py` | `/api/alerts` | ServiceAlert CRUD |
| `gtfs.py` | `/api/gtfs` | GTFS Static feed management and entity lookup |
| `realtime.py` | `/api/realtime` | GTFS-RT protobuf and JSON feed output |
| `sources.py` | `/api/sources` | External data source CRUD and manual trigger |
| `settings.py` | `/api/settings` | Application settings key-value store |
| `users.py` | `/api/users` | User management (superuser only) |

## Data Model

### Core Tables

Tables are split into `sys_` tables which are internal application tables, `gtfs_` tables for holding the nominal reference data and `realtime_` tables for the reatime data.

### Database Migrations

Migrations are generated for running with Alembic. All pending migrations are applied during application startup.

## GTFS-Realtime Feed

The `/api/realtime/feed` endpoint is the public output endpoint. It serializes active `ServiceAlert` rows into a GTFS-RT `FeedMessage` protobuf using the generated `gtfs_realtime_pb2` module (from `gtfs-realtime.proto`). The endpoint also supports a `?format=json` query parameter for JSON output. A simple in-memory cache (TTL 30 seconds) reduces database load; the cache is invalidated on every alert write operation.

Optional Basic Auth can be enabled for the realtime endpoint by storing `gtfs_rt_username` and `gtfs_rt_password` in `app_settings`.

## External Data Source Adapters

Adapters live in `services/adapters/` and inherit from `BaseAdapter` (defined in `base.py`). Each adapter implements:

- `CONFIG_SCHEMA`: A list of field descriptor dicts describing required and optional configuration fields.
- `_validate_config()`: Raises `ValueError` on missing or invalid configuration.
- `fetch_alerts()`: Fetches and returns raw alert data from the external source.
- `transform()`: Converts raw data into the internal `ServiceAlert` schema.
- `import_alerts()`: Persists transformed alerts to the database.

APScheduler runs polling jobs for each active data source on a configurable interval.

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
