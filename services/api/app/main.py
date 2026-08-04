"""Groundwork API entrypoint.

A single FastAPI service fronts everything the client needs. Routers are mounted under `/v1` so the
mobile app can pin a version and we can evolve the contract without breaking installed dev builds.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import pool
from app.routers import health, properties

API_PREFIX = "/v1"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the connection pool on startup and close it on shutdown.

    A missing database URL is fatal in production and merely logged elsewhere, so unit tests and a
    fresh checkout can still boot the app and read /docs before anyone has provisioned Postgres.
    """
    settings = get_settings()
    if settings.database_url:
        await pool.init_pool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
        )
    elif settings.is_production:
        raise RuntimeError("GROUNDWORK_DATABASE_URL is required in production")
    else:
        logger.warning("starting without a database: GROUNDWORK_DATABASE_URL is unset")

    try:
        yield
    finally:
        await pool.close_pool()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        lifespan=lifespan,
        title="Groundwork API",
        version=settings.version,
        description=(
            "Backend for Groundwork: defensible-space hazard assessment, deterministic rules "
            "engine, and water-rebate math for California properties."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(properties.router, prefix=API_PREFIX)

    return app


app = create_app()
