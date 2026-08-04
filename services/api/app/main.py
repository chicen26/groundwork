"""Groundwork API entrypoint.

A single FastAPI service fronts everything the client needs. Routers are mounted under `/v1` so the
mobile app can pin a version and we can evolve the contract without breaking installed dev builds.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health

API_PREFIX = "/v1"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
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

    return app


app = create_app()
