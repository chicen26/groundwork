"""The planting palette.

What to put back once a lawn or a hazard is gone, filtered by which defensible-space zone it is
going into, how much sun that spot gets, and whether the homeowner is going for a native-only
planting.

The zone filter carries a product decision worth stating plainly: **the palette recommends nothing
for the first five feet.** Under the draft Zone 0 rule that band is meant to be non-combustible —
gravel, stone, or bare soil — so a plant list there would undercut the advice on the same screen.
The endpoint returns an empty list with the reason rather than a shorter list of "safer" plants.

Plant data is imported from WUCOLS V, UC ANR and fire-safe-council lists, and Calscape, each row
carrying its sources. Nothing is seeded by hand: a plant recommendation with no cited source is a
horticultural claim we are not in a position to make.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db import pool

router = APIRouter(prefix="/plants", tags=["plants"])

# The band the draft Zone 0 rule covers.
EMBER_RESISTANT_ZONE = "0-5ft"

ZONE_0_EXPLANATION = (
    "The first five feet is meant to be non-combustible under the proposed Zone 0 rule — gravel, "
    "stone, pavers, or bare soil. We do not recommend plants for this band, including "
    "low-water and fire-resistant ones. (Zone 0 is a draft regulation and has not been "
    "finally adopted.)"
)


class Plant(BaseModel):
    id: str
    common_name: str
    scientific_name: str
    wucols_rating: str | None
    fire_notes: str | None
    native: bool
    sun: str | None
    zones_allowed: list[str]
    # Where each claim about this plant came from. Shown in the app, per our attribution
    # obligations to Calscape and WUCOLS.
    sources: list[str]


class PaletteResponse(BaseModel):
    zone: str | None
    plants: list[Plant]
    # Set when the zone itself is the reason the list is empty, rather than our data being thin.
    note: str | None = None
    attribution: str


ATTRIBUTION = (
    "Water needs from WUCOLS V (UC Davis). Native status and plant data from Calscape, "
    "California Native Plant Society, used non-commercially with attribution. Fire-wise guidance "
    "from UC ANR and local fire safe council lists."
)


@router.get("", response_model=PaletteResponse)
async def list_plants(
    zone: Annotated[str | None, Query(description="Defensible-space zone, e.g. 5-30ft")] = None,
    sun: Annotated[str | None, Query()] = None,
    native_only: Annotated[bool, Query()] = False,
    # EBMUD's higher rebate tier requires native planting, so this filter is money-relevant.
    max_water: Annotated[str | None, Query(description="WUCOLS rating ceiling")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaletteResponse:
    if zone == EMBER_RESISTANT_ZONE:
        return PaletteResponse(
            zone=zone, plants=[], note=ZONE_0_EXPLANATION, attribution=ATTRIBUTION
        )

    conditions = ["true"]
    params: list[object] = []

    if zone:
        params.append(zone)
        conditions.append(f"${len(params)} = ANY(zones_allowed)")
    if sun:
        params.append(sun)
        conditions.append(f"sun = ${len(params)}")
    if native_only:
        conditions.append("native")
    if max_water:
        # WUCOLS ratings are ordinal, so "at most moderate" means very low, low, or moderate.
        ladder = ["very low", "low", "moderate", "high"]
        if max_water.lower() in ladder:
            allowed = ladder[: ladder.index(max_water.lower()) + 1]
            params.append(allowed)
            conditions.append(f"lower(wucols_rating) = ANY(${len(params)}::text[])")

    params.append(limit)
    query = f"""
        SELECT id, common_name, scientific_name, wucols_rating, fire_notes, native, sun,
               zones_allowed, sources
        FROM plants
        WHERE {" AND ".join(conditions)}
        ORDER BY native DESC, common_name
        LIMIT ${len(params)}
    """

    async with pool.acquire_service() as conn:
        rows = await conn.fetch(query, *params)

    return PaletteResponse(
        zone=zone,
        plants=[
            Plant(
                id=str(row["id"]),
                common_name=row["common_name"],
                scientific_name=row["scientific_name"],
                wucols_rating=row["wucols_rating"],
                fire_notes=row["fire_notes"],
                native=row["native"],
                sun=row["sun"],
                zones_allowed=list(row["zones_allowed"]),
                sources=list(row["sources"]),
            )
            for row in rows
        ],
        note=None if rows else "No plants in our data match those filters yet.",
        attribution=ATTRIBUTION,
    )
