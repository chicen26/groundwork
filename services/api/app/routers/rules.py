"""Rulebook endpoints.

The client renders citations, caveats, and the disclaimer from the same document the engine scores
with. Serving it rather than duplicating the text in the app means a finding on screen and the rule
that produced it can never drift apart.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.routers.health import SettingsDep
from app.rules.rulebook import Rulebook, available_versions, load_rulebook

router = APIRouter(prefix="/rulebooks", tags=["rules"])


class RulebookIndex(BaseModel):
    active: str
    available: list[str]


@router.get("", response_model=RulebookIndex)
def list_rulebooks(settings: SettingsDep) -> RulebookIndex:
    return RulebookIndex(active=settings.rulebook_version, available=available_versions())


@router.get("/{version}", response_model=Rulebook)
def get_rulebook(version: Annotated[str, Path()]) -> Rulebook:
    try:
        return load_rulebook(version)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no rulebook {version!r}"
        ) from exc


def active_rulebook(settings: Settings | None = None) -> Rulebook:
    """The rulebook this deployment scores with."""
    return load_rulebook((settings or get_settings()).rulebook_version)
