"""Liveness and build-identity endpoint.

The rulebook version is surfaced here deliberately: when a finding cites a rule, we need to be able
to say exactly which rulebook produced it, and the client shows this on the assessment screen.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    rulebook_version: str


@router.get("/", include_in_schema=False)
def root(settings: SettingsDep) -> dict:
    """A signpost at the root.

    Nothing is served here, but a bare 404 while someone is checking their server started is an
    unhelpful first impression — this says what is running and where to look.
    """
    return {
        "service": "Groundwork API",
        "version": settings.version,
        "docs": "/docs",
        "health": "/v1/health",
    }


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.version,
        environment=settings.environment,
        rulebook_version=settings.rulebook_version,
    )
