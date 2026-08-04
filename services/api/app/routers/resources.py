"""Local programmes, filtered to the district a property actually sits in.

Two things this deliberately does not do. It does not restate a programme's terms — funding rounds
and deadlines change annually, so we name the agency and link to their page rather than keep a copy
that quietly goes stale. And it does not give evacuation guidance: the Genasys entry is a link to
the official source and says so, which is the only form that appears anywhere in this product.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi import Path as PathParam
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import pool

router = APIRouter(prefix="/resources", tags=["resources"])

RESOURCES_PATH = Path(__file__).resolve().parents[2] / "programs" / "resources.json"


class Resource(BaseModel):
    key: str
    agency: str
    name: str
    type: str
    summary: str
    url: str
    phone: str | None = None
    disclaimer: str | None = None
    external_only: bool = False
    # True when this entry applies to any district, rather than being district-specific.
    universal: bool = True


@lru_cache
def _all_resources() -> list[dict]:
    return json.loads(RESOURCES_PATH.read_text())["resources"]


def _to_model(entry: dict) -> Resource:
    return Resource(
        key=entry["key"],
        agency=entry["agency"],
        name=entry["name"],
        type=entry["type"],
        summary=entry["summary"],
        url=entry["url"],
        phone=entry.get("phone"),
        disclaimer=entry.get("disclaimer"),
        external_only=entry.get("external_only", False),
        universal=not entry.get("applies_to_districts"),
    )


def resources_for_district(district: str | None) -> list[Resource]:
    """Programmes relevant to one district, plus the county-wide ones.

    A property whose district we could not determine gets the universal entries rather than nothing:
    the Diablo Fire Safe Council chipping programme is useful regardless, and an empty screen would
    read as "there is no help available".
    """
    results = []
    for entry in _all_resources():
        districts = entry.get("applies_to_districts") or []
        if not districts or (district and any(d.lower() == district.lower() for d in districts)):
            results.append(_to_model(entry))
    return results


@router.get("", response_model=list[Resource])
def list_resources(
    district: Annotated[str | None, Query()] = None,
) -> list[Resource]:
    return resources_for_district(district)


@router.get("/for-property/{property_id}", response_model=list[Resource])
async def resources_for_property(
    user_id: CurrentUser, property_id: Annotated[UUID, PathParam()]
) -> list[Resource]:
    async with pool.acquire_as_user(user_id) as conn:
        row = await conn.fetchrow("SELECT fire_district FROM properties WHERE id = $1", property_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found")

    return resources_for_district(row["fire_district"])
