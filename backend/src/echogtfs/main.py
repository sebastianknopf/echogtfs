from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from echogtfs.config import settings
from echogtfs.database import AsyncSessionLocal, Base, engine
from echogtfs.extensions import limiter
from echogtfs.models import GtfsAgency, GtfsRoute, GtfsStop, User  # noqa: F401
from echogtfs.routers.auth import router as auth_router
from echogtfs.routers.gtfs import router as gtfs_router
from echogtfs.services.gtfs_import import schedule_import_from_cron
from echogtfs.routers.settings import router as settings_router
from echogtfs.routers.users import router as users_router
from echogtfs.security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Create tables on startup (use Alembic for production migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Bootstrap first superuser when the database is empty
    async with AsyncSessionLocal() as db:
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
    await schedule_import_from_cron()
    yield


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

# -- CORS ----------------------------------------------------------------------
# Origins are controlled by CORS_ORIGINS env var (comma-separated).
# An empty list means no cross-origin requests are accepted.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router,     prefix="/api/auth",     tags=["auth"])
app.include_router(users_router,    prefix="/api/users",    tags=["users"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(gtfs_router,     prefix="/api/gtfs",     tags=["gtfs"])


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
