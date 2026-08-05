"""Groundwork API entrypoint.

A single FastAPI service fronts everything the client needs. Routers are mounted under `/v1` so the
mobile app can pin a version and we can evolve the contract without breaking installed dev builds.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import pool
from app.db.migrate import migrate
from app.routers import (
    account,
    health,
    plants,
    properties,
    reports,
    resources,
    rules,
    scans,
    water,
)
from app.rules.rulebook import load_rulebook
from app.storage import init_storage

API_PREFIX = "/v1"

logger = logging.getLogger(__name__)


async def _warn_about_pending_migrations(settings) -> None:
    """Say something loud when the schema is behind the code.

    A missing column surfaces as a 500 on whichever endpoint touches it first, which reads like a
    broken feature rather than an unapplied migration. Tests never hit this because they rebuild
    their database from scratch, so a long-lived development database is exactly where it bites.
    Fatal in production, where serving against a half-migrated schema is worse than not starting.
    """
    try:
        pending = await migrate(settings.database_url, status_only=True)
    except Exception:
        logger.warning("could not check for pending migrations")
        return

    if not pending:
        return
    message = (
        f"{len(pending)} pending migration(s): {', '.join(pending)}. Run: python -m app.db.migrate"
    )
    if settings.is_production:
        raise RuntimeError(message)
    logger.warning("=" * 78)
    logger.warning(message)
    logger.warning("=" * 78)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the connection pool on startup and close it on shutdown.

    A missing database URL is fatal in production and merely logged elsewhere, so unit tests and a
    fresh checkout can still boot the app and read /docs before anyone has provisioned Postgres.
    """
    settings = get_settings()

    # Fail fast on a rulebook that cannot load. Every score cites it, so a deployment pinned to a
    # version that is not present would serve findings it cannot justify.
    load_rulebook(settings.rulebook_version)
    init_storage(Path(settings.photo_storage_root))

    if settings.database_url:
        await pool.init_pool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
        )
        await _warn_about_pending_migrations(settings)
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

    app.include_router(account.router, prefix=API_PREFIX)
    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(properties.router, prefix=API_PREFIX)
    app.include_router(rules.router, prefix=API_PREFIX)
    app.include_router(scans.router, prefix=API_PREFIX)
    app.include_router(water.router, prefix=API_PREFIX)
    app.include_router(plants.router, prefix=API_PREFIX)
    app.include_router(resources.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)

    return app


app = create_app()
