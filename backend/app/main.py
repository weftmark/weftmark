from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import activities, admin, auth, health, looms, projects, users, yarn
from app.version import VERSION

settings = get_settings()

start_time: datetime = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global start_time
    start_time = datetime.now(timezone.utc)
    yield


app = FastAPI(
    title="WeftMark API",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(looms.router)
app.include_router(yarn.router)
app.include_router(activities.router)
app.include_router(admin.router)
