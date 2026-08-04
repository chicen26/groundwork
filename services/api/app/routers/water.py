"""Lawn measurement and what it is worth.

The client draws a polygon on a satellite basemap and sends the GeoJSON. The area that any money is
calculated from is computed **here**, geodesically, by PostGIS — never taken from the client. A
number that decides a rebate should not be something the app could get wrong on a slow phone.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator

from app.auth import CurrentUser
from app.db import pool
from app.water.rebates import (
    annual_gallons_saved,
    estimate,
    estimate_all,
    load_programs,
    program_for,
    savings_basis,
    universal_warning,
)

router = APIRouter(tags=["water"])

SQ_METRES_TO_SQ_FEET = Decimal("10.763910416709722")


class LawnPolygon(BaseModel):
    """A GeoJSON Polygon, as drawn on the map."""

    label: str | None = Field(default=None, max_length=80)
    geojson: dict[str, Any]
    # Which EBMUD tier the planting plan qualifies for, when the user has chosen one.
    tier_key: str | None = None

    @field_validator("geojson")
    @classmethod
    def must_be_a_closed_polygon(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "Polygon":
            raise ValueError("geojson must be a Polygon")
        rings = value.get("coordinates")
        if not rings or not rings[0]:
            raise ValueError("polygon has no coordinates")
        ring = rings[0]
        if len(ring) < 4:
            raise ValueError("a polygon needs at least three distinct corners")
        if ring[0] != ring[-1]:
            raise ValueError("polygon ring must be closed (first point repeated at the end)")
        return value


class LawnResponse(BaseModel):
    id: UUID
    label: str | None
    area_sqft: str
    annual_gallons_saved: str
    savings_basis: str
    rebates: list[dict]
    warning: str
    utility: str | None
    # True when we could not determine the utility and are showing every programme instead.
    showing_all_programs: bool


@router.get("/programs/rebates", tags=["water"])
def list_rebate_programs() -> dict:
    """The rebate programmes we know about, with their rates and caps."""
    return {
        "warning": universal_warning(),
        "programs": [
            {
                "key": p.key,
                "agency": p.agency,
                "agency_full": p.agency_full,
                "name": p.name,
                "rate_per_sqft": str(p.rate_per_sqft),
                "cap_usd": str(p.cap_usd),
                "minimum_sqft": p.minimum_sqft,
                "url": p.url,
                "tiers": [
                    {
                        "key": t.key,
                        "label": t.label,
                        "rate_per_sqft": str(t.rate_per_sqft),
                        "requirements": t.requirements,
                    }
                    for t in p.tiers
                ],
            }
            for p in load_programs()
        ],
    }


@router.post(
    "/properties/{property_id}/lawn",
    response_model=LawnResponse,
    status_code=status.HTTP_201_CREATED,
)
async def measure_lawn(
    user_id: CurrentUser, property_id: Annotated[UUID, Path()], payload: LawnPolygon
) -> LawnResponse:
    async with pool.acquire_as_user(user_id) as conn:
        utility = await conn.fetchval(
            "SELECT water_utility FROM properties WHERE id = $1", property_id
        )
        owns = await conn.fetchval("SELECT 1 FROM properties WHERE id = $1", property_id)
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found")

        # Geodesic area, computed by the database from the geometry itself. ST_MakeValid repairs
        # the self-intersections a finger-drawn polygon produces constantly.
        area_sqm = await conn.fetchval(
            """
            SELECT ST_Area(ST_MakeValid(ST_GeomFromGeoJSON($1))::geography)
            """,
            json.dumps(payload.geojson),
        )
        if area_sqm is None or area_sqm <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="that outline does not enclose an area — try drawing it again",
            )

        area_sqft = (Decimal(str(area_sqm)) * SQ_METRES_TO_SQ_FEET).quantize(Decimal("0.01"))

        row = await conn.fetchrow(
            """
            INSERT INTO lawn_polygons (property_id, label, geom, area_sqft)
            VALUES ($1, $2, ST_MakeValid(ST_GeomFromGeoJSON($3))::geography, $4)
            RETURNING id
            """,
            property_id,
            payload.label,
            json.dumps(payload.geojson),
            area_sqft,
        )

    program = program_for(utility)
    if program:
        rebates = [estimate(program, area_sqft, tier_key=payload.tier_key).as_dict()]
    else:
        # No utility resolved: show every programme with its agency named rather than guess one.
        rebates = estimate_all(area_sqft, tier_key=payload.tier_key)

    return LawnResponse(
        id=row["id"],
        label=payload.label,
        area_sqft=str(area_sqft),
        annual_gallons_saved=str(annual_gallons_saved(area_sqft)),
        savings_basis=savings_basis(),
        rebates=rebates,
        warning=universal_warning(),
        utility=utility,
        showing_all_programs=program is None,
    )


@router.get("/properties/{property_id}/lawn", response_model=list[LawnResponse])
async def list_lawns(
    user_id: CurrentUser, property_id: Annotated[UUID, Path()]
) -> list[LawnResponse]:
    async with pool.acquire_as_user(user_id) as conn:
        utility = await conn.fetchval(
            "SELECT water_utility FROM properties WHERE id = $1", property_id
        )
        rows = await conn.fetch(
            """
            SELECT id, label, area_sqft FROM lawn_polygons
            WHERE property_id = $1 ORDER BY computed_at DESC
            """,
            property_id,
        )

    program = program_for(utility)
    responses = []
    for row in rows:
        area = Decimal(str(row["area_sqft"]))
        responses.append(
            LawnResponse(
                id=row["id"],
                label=row["label"],
                area_sqft=str(area),
                annual_gallons_saved=str(annual_gallons_saved(area)),
                savings_basis=savings_basis(),
                rebates=([estimate(program, area).as_dict()] if program else estimate_all(area)),
                warning=universal_warning(),
                utility=utility,
                showing_all_programs=program is None,
            )
        )
    return responses
