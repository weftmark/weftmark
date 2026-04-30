from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging
from app.middleware import SecurityHeadersMiddleware
from app.routers import activities, admin, auth, health, logs, looms, projects, users, yarn
from app.version import VERSION

settings = get_settings()
configure_logging(settings.log_level)

start_time: datetime = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global start_time
    start_time = datetime.now(timezone.utc)

    from app.routers.health import run_startup_probes, set_readiness

    readiness = await run_startup_probes()
    set_readiness(readiness)

    yield


app = FastAPI(
    title="WeftMark API",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

app.add_middleware(SecurityHeadersMiddleware, production=settings.app_env == "production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(logs.router)
app.include_router(auth.router)
app.include_router(users.eula_router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(looms.router)
app.include_router(yarn.router)
app.include_router(activities.router)
app.include_router(admin.router)
