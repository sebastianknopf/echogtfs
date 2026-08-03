from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from echogtfs.common.config import settings
from echogtfs.common.security import SlidingTokenMiddleware
from echogtfs.common.extensions import limiter
from echogtfs.services.database.alembic_migration_service import AlembicMigrationService
from echogtfs.services.database import (
    GtfsRepository,
    RealtimeRepository,
    SystemRepository,
    set_gtfs_repository,
    set_realtime_repository,
    set_system_repository,
)
from echogtfs.services.scheduler import DatasourceSchedulerService, set_datasource_scheduler_service
from echogtfs.services.security import SecurityService, get_security_service, set_security_service
from echogtfs.services.caching import CachingService, set_caching_service
from echogtfs.routers.alerts import router as alerts_router
from echogtfs.routers.auth import router as auth_router
from echogtfs.routers.gtfs import router as gtfs_router
from echogtfs.routers.realtime import router as realtime_router
from echogtfs.routers.dashboard import router as dashboard_router
from echogtfs.routers.trips import router as trips_router
from echogtfs.routers.vehicles import router as vehicles_router
from echogtfs.services.gtfs import GtfsImportService
from echogtfs.services.cleanup import CleanupService
from echogtfs.routers.settings import router as settings_router
from echogtfs.routers.systemcopy import router as systemcopy_router
from echogtfs.routers.sources import router as sources_router
from echogtfs.routers.users import router as users_router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    
    # run Alembic migrations to head on startup
    migration_service: AlembicMigrationService = AlembicMigrationService()
    await migration_service.upgrade_head()

    # intialize repositories
    system_repository = SystemRepository(settings.database_url, settings.debug)
    await system_repository.initialize()
    set_system_repository(system_repository)

    gtfs_repository = GtfsRepository(settings.database_url, settings.debug)
    await gtfs_repository.initialize()
    set_gtfs_repository(gtfs_repository)

    realtime_repository = RealtimeRepository(settings.database_url, settings.debug)
    await realtime_repository.initialize()
    set_realtime_repository(realtime_repository)

    # intialize single-instance services
    set_security_service(SecurityService(system_repository))
    caching_service = CachingService(settings.redis_url)

    await caching_service.initialize()
    set_caching_service(caching_service)

    datasource_scheduler_service = DatasourceSchedulerService(
        system_repository,
        realtime_repository,
        gtfs_repository,
    )
    set_datasource_scheduler_service(datasource_scheduler_service)

    # bootstrap first superuser when the database is empty
    users = await system_repository.list_users()
    if not users:
        await system_repository.create_user(
            username=settings.first_superuser,
            email=settings.first_superuser_email,
            hashed_password=get_security_service().hash_password(settings.first_superuser_password),
            is_active=True,
            is_superuser=True,
        )

    # start schedulers for all scheduled services
    await GtfsImportService(system_repository, gtfs_repository).schedule_from_settings()
    await CleanupService(system_repository, realtime_repository).schedule_from_settings()
    
    await datasource_scheduler_service.schedule_all_data_sources()
    
    yield

    # close database repositories on shutdown
    await caching_service.close()
    await gtfs_repository.close()
    await realtime_repository.close()
    await system_repository.close()


# -- FastAPI app ---------------------------------------------------------------
# Docs are disabled by default; set DOCS_ENABLED=true to re-enable.
_docs_url    = "/api/docs"    if settings.docs_enabled else None
_redoc_url   = "/api/redoc"   if settings.docs_enabled else None
_openapi_url = "/api/openapi.json" if settings.docs_enabled else None

app = FastAPI(
    title="echogtfs",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# -- Rate-limiter state & error handler ----------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# -- Sliding Token Middleware --------------------------------------------------
# IMPORTANT: Must be added BEFORE CORS middleware!
# Middleware execution order (response flow): Route → SlidingToken → CORS → Client
# This ensures the X-New-Token header is set before CORS processes it
app.add_middleware(SlidingTokenMiddleware)

# -- CORS ----------------------------------------------------------------------
# Origins are controlled by CORS_ORIGINS env var (comma-separated).
# An empty list means no cross-origin requests are accepted.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-New-Token"],  # Allow frontend to read new token from response
)

app.include_router(auth_router,     prefix="/api/auth",     tags=["auth"])
app.include_router(users_router,    prefix="/api/users",    tags=["users"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(systemcopy_router, prefix="/api/systemcopy", tags=["systemcopy"])
app.include_router(gtfs_router,     prefix="/api/gtfs",     tags=["gtfs"])
app.include_router(sources_router,  prefix="/api/sources",  tags=["sources"])
app.include_router(alerts_router,   prefix="/api/alerts",   tags=["alerts"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(trips_router,    prefix="/api/trips",    tags=["trips"])
app.include_router(vehicles_router, prefix="/api/vehicles", tags=["vehicles"])
app.include_router(realtime_router, prefix="/api",          tags=["realtime"])


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
