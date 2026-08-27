"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging
from app.schema_guard import validate_runtime_schema
from app.routers import (
    auth,
    coach,
    dashboard,
    decks,
    health,
    oss,
    realtime,
    settings as settings_router,
    study,
    study_session,
    user_decks,
)

# Configure logging
setup_logging()

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="LanGear API",
    description="LanGear MVP Backend - English Speaking Training Platform",
    version="2.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(oss.router)
app.include_router(decks.router)
app.include_router(realtime.router)
app.include_router(study.router)
app.include_router(study_session.router)
app.include_router(user_decks.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)
app.include_router(coach.router)

logger.info("LanGear API started successfully")


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting LanGear API v2.0")
    if settings.sqlite_database_path is not None:
        logger.info(f"SQLite database path: {settings.sqlite_database_path}")
    else:
        logger.info("Database driver: non-sqlite")
    logger.info(f"CORS origins: {settings.cors_origins_list}")
    validate_runtime_schema()
    logger.info("Runtime database schema validation passed")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Shutting down LanGear API")
