"""Geo endpoints that work before a property exists.

Both are deliberately unauthenticated: they answer questions about places, not about anyone's
account, and they are exactly what a visitor tries before deciding to sign up. Neither stores
anything the caller typed beyond the shared lookup cache.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.db import pool
from app.geo.resolve import resolve_point
from app.geo.suggest import SuggestionsUnavailable, suggest_addresses, zip_centroid

router = APIRouter(prefix="/geo", tags=["geo"])


class Suggestion(BaseModel):
    label: str
    lat: float
    lng: float


class QuickLook(BaseModel):
    """The rough, honest answer to "what does my ZIP look like?".

    `approximate` is always true and the client is expected to say so: a ZIP centroid is one point
    standing in for square miles, and presenting it as a property answer would be a lie.
    """

    zip: str
    place: str | None
    state_code: str | None
    lat: float
    lng: float
    fhsz: str
    fhsz_source_version: str | None
    fire_district: str | None
    water_utility: str | None
    unresolved: list[str]
    approximate: bool = True


@router.get("/suggest", response_model=list[Suggestion])
async def suggest(
    q: Annotated[str, Query(min_length=3, max_length=200)],
) -> list[Suggestion]:
    """Address completions for a partial query. Empty on any upstream trouble, never an error."""
    async with pool.acquire_service() as conn:
        suggestions = await suggest_addresses(conn, q)
    return [Suggestion(label=s.label, lat=s.lat, lng=s.lng) for s in suggestions]


@router.get("/quick-look", response_model=QuickLook)
async def quick_look(
    zip: Annotated[str, Query(pattern=r"^\d{5}$")],
) -> QuickLook:
    """What we can say from a ZIP alone: the hazard picture at the area's center point."""
    async with pool.acquire_service() as conn:
        try:
            centroid = await zip_centroid(conn, zip)
        except SuggestionsUnavailable as exc:
            # 422 rather than 500: the request was fine, we just could not place the ZIP. The
            # client's next step is a full address, so say so.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"could not place ZIP {zip} right now; try a full street address",
            ) from exc

        resolution = await resolve_point(conn, lat=centroid.lat, lng=centroid.lng)

    return QuickLook(
        zip=centroid.zip,
        place=centroid.place,
        state_code=centroid.state_code or resolution.implied_state,
        lat=centroid.lat,
        lng=centroid.lng,
        fhsz=resolution.fhsz,
        fhsz_source_version=resolution.fhsz_source_version,
        fire_district=resolution.fire_district,
        water_utility=resolution.water_utility,
        unresolved=resolution.unresolved,
    )
