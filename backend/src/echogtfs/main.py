from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from echogtfs.config import settings
from echogtfs.extensions import limiter
from echogtfs.services.database.alembic_migration_service import AlembicMigrationService
from echogtfs.services.database import SqlAlchemyRepository, set_repository
from echogtfs.services.database.models import  User  # noqa: F401
from echogtfs.routers.alerts import router as alerts_router
from echogtfs.routers.auth import router as auth_router
from echogtfs.routers.gtfs import router as gtfs_router
from echogtfs.routers.realtime import router as realtime_router
from echogtfs.services.gtfs import GtfsImportService
from echogtfs.services.alert_import import schedule_all_data_sources
from echogtfs.services.cleanup import CleanupService
from echogtfs.routers.settings import router as settings_router
from echogtfs.routers.sources import router as sources_router
from echogtfs.routers.users import router as users_router
from echogtfs.security import create_access_token, hash_password

logger = logging.getLogger("uvicorn.error")


# -- Sliding Token Middleware --------------------------------------------------

class SlidingTokenMiddleware(BaseHTTPMiddleware):
    """
    Middleware that issues a new JWT token on every successful authenticated request.
    This implements a "sliding session" pattern where the session automatically
    extends with user activity, expiring only after a period of inactivity.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Only issue new token for successful responses (2xx status codes)
        if 200 <= response.status_code < 300:
            # Check if user was authenticated for this request
            # Use getattr with default to safely access request.state.user
            user = getattr(request.state, "user", None)
            if user is not None:
                # Generate new token with extended expiration
                new_token = create_access_token(user.username)
                # Add new token to response header for frontend to update
                response.headers["X-New-Token"] = new_token
                logger.info(f"[SlidingToken] Issued new token for user: {user.username}")
            else:
                logger.debug(f"[SlidingToken] No user in request.state for {request.url.path}")
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    
    # run Alembic migrations to head on startup
    migration_service: AlembicMigrationService = AlembicMigrationService()
    await migration_service.upgrade_head()

    repository = SqlAlchemyRepository(settings.database_url, settings.debug)
    await repository.initialize()
    set_repository(repository)
    
    # Bootstrap first superuser when the database is empty
    async with repository.get_session() as db:
        result = await db.execute(select(User).limit(1))
        if result.first() is None:
            db.add(
                User(
                    username=settings.first_superuser,
                    email=settings.first_superuser_email,
                    hashed_password=hash_password(settings.first_superuser_password),
                    is_active=True,
                    is_superuser=True,
                )
            )
            await db.commit()


    # Schedule GTFS import cron on startup
    await GtfsImportService(repository).schedule_import_from_cron()
    
    # Schedule all data source alert imports on startup
    await schedule_all_data_sources()
    
    # Schedule cleanup job on startup
    await CleanupService(repository).schedule_from_settings()
    
    yield

    # Close database repository on shutdown
    await repository.close()


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
app.include_router(gtfs_router,     prefix="/api/gtfs",     tags=["gtfs"])
app.include_router(sources_router,  prefix="/api/sources",  tags=["sources"])
app.include_router(alerts_router,   prefix="/api/alerts",   tags=["alerts"])
app.include_router(realtime_router, prefix="/api",          tags=["realtime"])


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
