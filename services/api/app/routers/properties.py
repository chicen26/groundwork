"""Properties: the first thing a homeowner creates, and where geo resolution happens.

Creating a property answers "what rules apply to me": the fire hazard severity zone from the
published CAL FIRE maps, the fire district, and the water utility. Every answer names the map it
came from, and any answer we cannot determine is returned as unresolved rather than guessed.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field, model_validator

from app.auth import CurrentUser
from app.db import pool
from app.geo.geocode import GeocodingUnavailable, geocode
from app.geo.resolve import GeoResolution, resolve_point

router = APIRouter(prefix="/properties", tags=["properties"])


class PropertyCreate(BaseModel):
    address: str = Field(min_length=4, max_length=300)
    label: str | None = Field(default=None, max_length=80)
    # Supplying coordinates skips geocoding entirely — the client does this after a map pin drop,
    # and it is the path the demo uses so a slow geocoder can never stall it.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinates_come_as_a_pair(self) -> PropertyCreate:
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be provided together")
        return self


class GeoSummary(BaseModel):
    fhsz: str
    fhsz_responsibility: str | None
    fhsz_source_version: str | None
    fire_district: str | None
    water_utility: str | None
    state_code: str | None = None
    # Named explicitly so the client can say "we could not determine your fire district" instead of
    # rendering a blank field that reads like "you do not have one".
    unresolved: list[str]

    @classmethod
    def from_resolution(
        cls, resolution: GeoResolution, state_code: str | None = None
    ) -> GeoSummary:
        return cls(
            state_code=state_code,
            fhsz=resolution.fhsz,
            fhsz_responsibility=resolution.fhsz_responsibility,
            fhsz_source_version=resolution.fhsz_source_version,
            fire_district=resolution.fire_district,
            water_utility=resolution.water_utility,
            unresolved=resolution.unresolved,
        )


class PropertyResponse(BaseModel):
    id: UUID
    address: str
    label: str | None
    lat: float
    lng: float
    geo: GeoSummary


async def ensure_user_row(conn, user_id: UUID) -> None:
    """Make sure the signed-in user has a row for foreign keys to point at.

    Supabase owns identity; this is a mirror created on first use. Doing it here rather than on
    every authenticated request keeps the cost on the one call that actually needs it, and
    ON CONFLICT makes it safe to race with itself.
    """
    await conn.execute("INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", user_id)


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(payload: PropertyCreate, user_id: CurrentUser) -> PropertyResponse:
    async with pool.acquire_as_user(user_id) as conn:
        await ensure_user_row(conn, user_id)

        lat, lng, address = payload.lat, payload.lng, payload.address
        state_code: str | None = None

        if lat is None or lng is None:
            try:
                located = await geocode(conn, payload.address)
            except GeocodingUnavailable as exc:
                # 422 rather than 500: the request was fine, we just could not place it. The client
                # responds by asking the user to drop a pin.
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"could not locate that address ({exc}); place it on the map instead",
                ) from exc
            lat, lng, address = located.lat, located.lng, located.matched_address
            state_code = located.state_code

        resolution = await resolve_point(conn, lat=lat, lng=lng)
        # A dropped pin has no address to read a state from, but a CAL FIRE match proves California.
        state_code = state_code or resolution.implied_state

        row = await conn.fetchrow(
            """
            INSERT INTO properties (
                user_id, label, address, location,
                fhsz, fhsz_responsibility, fhsz_source_version,
                fire_district, water_utility, state_code, geo_resolved_at
            )
            VALUES (
                $1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography,
                $6::fhsz_class, $7, $8, $9, $10, $11, now()
            )
            RETURNING id
            """,
            user_id,
            payload.label,
            address,
            lng,
            lat,
            resolution.fhsz,
            resolution.fhsz_responsibility,
            resolution.fhsz_source_version,
            resolution.fire_district,
            resolution.water_utility,
            state_code,
        )

    return PropertyResponse(
        id=row["id"],
        address=address,
        label=payload.label,
        lat=lat,
        lng=lng,
        geo=GeoSummary.from_resolution(resolution, state_code),
    )


@router.get("", response_model=list[PropertyResponse])
async def list_properties(user_id: CurrentUser) -> list[PropertyResponse]:
    async with pool.acquire_as_user(user_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, address, label,
                   ST_Y(location::geometry) AS lat,
                   ST_X(location::geometry) AS lng,
                   fhsz::text AS fhsz, fhsz_responsibility, fhsz_source_version,
                   fire_district, water_utility, state_code
            FROM properties
            ORDER BY created_at DESC
            """
        )

    return [_row_to_response(row) for row in rows]


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    user_id: CurrentUser, property_id: Annotated[UUID, Path()]
) -> PropertyResponse:
    async with pool.acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, address, label,
                   ST_Y(location::geometry) AS lat,
                   ST_X(location::geometry) AS lng,
                   fhsz::text AS fhsz, fhsz_responsibility, fhsz_source_version,
                   fire_district, water_utility, state_code
            FROM properties WHERE id = $1
            """,
            property_id,
        )

    # Row-level security means another household's property is simply not visible here, so "not
    # found" is the honest answer and does not leak whether the id exists.
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found")
    return _row_to_response(row)


def _row_to_response(row) -> PropertyResponse:
    resolution = GeoResolution(
        fhsz=row["fhsz"],
        fhsz_responsibility=row["fhsz_responsibility"],
        fhsz_source_version=row["fhsz_source_version"],
        fire_district=row["fire_district"],
        water_utility=row["water_utility"],
    )
    return PropertyResponse(
        id=row["id"],
        address=row["address"],
        label=row["label"],
        lat=row["lat"],
        lng=row["lng"],
        geo=GeoSummary.from_resolution(resolution, row["state_code"]),
    )
