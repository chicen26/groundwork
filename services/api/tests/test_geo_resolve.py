"""Geo resolution tests.

Synthetic polygons rather than the real CAL FIRE layers: these tests must pass in CI without
reaching out to an ArcGIS server, and the behaviour under test is our resolution logic — layer
precedence, version activation, honest gaps — not CAL FIRE's cartography.

The real layers are exercised separately by importing them and spot-checking known addresses; see
infra/gis/README.md.
"""

from __future__ import annotations

import asyncpg
import pytest

from app.geo.resolve import resolve_point
from app.geo.sources import _fhsz_class_from_description
from tests.conftest import requires_db

pytestmark = requires_db


async def add_layer_version(
    conn: asyncpg.Connection, layer: str, *, version: str, active: bool = True
) -> str:
    return await conn.fetchval(
        """
        INSERT INTO gis_layer_versions (layer, source_url, source_version, is_active)
        VALUES ($1, 'https://example.test/layer', $2, $3) RETURNING id
        """,
        layer,
        version,
        active,
    )


async def add_fhsz_square(
    conn: asyncpg.Connection,
    version_id: str,
    *,
    responsibility: str,
    fhsz: str,
    bounds: tuple[float, float, float, float] = (-122.0, 37.8, -121.9, 37.9),
) -> None:
    west, south, east, north = bounds
    await conn.execute(
        """
        INSERT INTO fhsz_zones (layer_version_id, responsibility, fhsz, geom)
        VALUES ($1, $2, $3::fhsz_class, ST_Multi(ST_MakeEnvelope($4, $5, $6, $7, 4326)))
        """,
        version_id,
        responsibility,
        fhsz,
        west,
        south,
        east,
        north,
    )


async def test_point_inside_a_zone_resolves_to_it(clean_db: asyncpg.Connection) -> None:
    version = await add_layer_version(clean_db, "fhsz_lra", version="LRA test 1")
    await add_fhsz_square(clean_db, version, responsibility="LRA", fhsz="very_high")

    resolution = await resolve_point(clean_db, lat=37.85, lng=-121.95)

    assert resolution.fhsz == "very_high"
    assert resolution.fhsz_responsibility == "LRA"
    assert resolution.fhsz_source_version == "LRA test 1"
    assert resolution.is_wildland_hazard_zone


async def test_point_outside_every_polygon_is_unknown_not_guessed(
    clean_db: asyncpg.Connection,
) -> None:
    """A gap in coverage must read as "we do not know", never as a nearby zone."""
    version = await add_layer_version(clean_db, "fhsz_lra", version="LRA test 1")
    await add_fhsz_square(clean_db, version, responsibility="LRA", fhsz="very_high")

    resolution = await resolve_point(clean_db, lat=39.5, lng=-120.0)

    assert resolution.fhsz == "unknown"
    assert resolution.fhsz_source_version is None
    assert not resolution.is_wildland_hazard_zone
    assert "fhsz" in resolution.unresolved


async def test_local_map_wins_where_both_cover_the_point(clean_db: asyncpg.Connection) -> None:
    """Where LRA and SRA overlap, the local designation governs the property."""
    lra = await add_layer_version(clean_db, "fhsz_lra", version="LRA 2025")
    sra = await add_layer_version(clean_db, "fhsz_sra", version="SRA 2023")
    await add_fhsz_square(clean_db, lra, responsibility="LRA", fhsz="moderate")
    await add_fhsz_square(clean_db, sra, responsibility="SRA", fhsz="very_high")

    resolution = await resolve_point(clean_db, lat=37.85, lng=-121.95)

    assert resolution.fhsz == "moderate"
    assert resolution.fhsz_responsibility == "LRA"


async def test_inactive_versions_are_ignored(clean_db: asyncpg.Connection) -> None:
    """A half-loaded import must never leak into somebody's assessment."""
    stale = await add_layer_version(clean_db, "fhsz_lra", version="stale", active=False)
    await add_fhsz_square(clean_db, stale, responsibility="LRA", fhsz="very_high")

    resolution = await resolve_point(clean_db, lat=37.85, lng=-121.95)

    assert resolution.fhsz == "unknown"


async def test_only_one_version_of_a_layer_can_be_active(clean_db: asyncpg.Connection) -> None:
    await add_layer_version(clean_db, "fhsz_lra", version="first")

    with pytest.raises(asyncpg.UniqueViolationError):
        await add_layer_version(clean_db, "fhsz_lra", version="second")


async def test_district_and_utility_are_reported_when_present(
    clean_db: asyncpg.Connection,
) -> None:
    district_version = await add_layer_version(clean_db, "fire_districts", version="districts v1")
    utility_version = await add_layer_version(clean_db, "water_utilities", version="utilities v1")
    await clean_db.execute(
        """
        INSERT INTO fire_districts (layer_version_id, name, agency_code, geom)
        VALUES ($1, 'San Ramon Valley Fire Protection District', 'SRVFPD',
                ST_Multi(ST_MakeEnvelope(-122.0, 37.8, -121.9, 37.9, 4326)))
        """,
        district_version,
    )
    await clean_db.execute(
        """
        INSERT INTO water_utilities (layer_version_id, name, utility_code, geom)
        VALUES ($1, 'East Bay Municipal Utility District', 'EBMUD',
                ST_Multi(ST_MakeEnvelope(-122.0, 37.8, -121.9, 37.9, 4326)))
        """,
        utility_version,
    )

    resolution = await resolve_point(clean_db, lat=37.85, lng=-121.95)

    assert resolution.fire_district == "San Ramon Valley Fire Protection District"
    assert resolution.water_utility == "East Bay Municipal Utility District"
    assert resolution.unresolved == ["fhsz"]


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        ("Very High", "very_high"),
        ("very high", "very_high"),
        ("High", "high"),
        ("Moderate", "moderate"),
        ("NonWildland", "non_wildland"),
        ("Non Wildland", "non_wildland"),
        (None, "unknown"),
        ("", "unknown"),
        ("Extremely Spicy", "unknown"),
    ],
)
def test_publisher_labels_map_onto_our_classes(published: str | None, expected: str) -> None:
    """An unrecognised label becomes unknown, because the zone decides what obligations we state."""
    assert _fhsz_class_from_description(published) == expected
