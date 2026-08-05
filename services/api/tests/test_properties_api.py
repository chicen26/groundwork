"""Properties endpoint tests — the full path from a request to a resolved zone.

These use the synchronous TestClient on purpose. It drives the app's real lifespan (so the
connection pool is created exactly as it is in production) on its own event loop, and keeping the
async work inside the app avoids the loop-mixing that async fixtures invite.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db

DANVILLE = {"lat": 37.8216, "lng": -121.9999}


async def _arrange(dsn: str) -> UUID:
    """Create a user and a hazard zone covering the test coordinate."""
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
        )
        version_id = await conn.fetchval(
            """
            INSERT INTO gis_layer_versions (layer, source_url, source_version, is_active)
            VALUES ('fhsz_lra', 'https://example.test', 'CAL FIRE FHSZ in LRA, 2025 v1', true)
            RETURNING id
            """
        )
        await conn.execute(
            """
            INSERT INTO fhsz_zones (layer_version_id, responsibility, fhsz, geom)
            VALUES ($1, 'LRA', 'very_high',
                    ST_Multi(ST_MakeEnvelope(-122.1, 37.7, -121.9, 37.9, 4326)))
            """,
            version_id,
        )
        return user_id
    finally:
        await conn.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, UUID]]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.delenv("GROUNDWORK_SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    user_id = asyncio.run(_arrange(TEST_DSN))
    with TestClient(create_app()) as test_client:
        yield test_client, user_id

    get_settings.cache_clear()


def auth(user_id: UUID) -> dict[str, str]:
    return {"X-Groundwork-User": str(user_id)}


def test_creating_a_property_resolves_its_hazard_zone(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, user_id = client

    response = api.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", "label": "Home", **DANVILLE},
        headers=auth(user_id),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["geo"]["fhsz"] == "very_high"
    assert body["geo"]["fhsz_responsibility"] == "LRA"
    # The zone is a claim about a specific published map, so the map must be named.
    assert body["geo"]["fhsz_source_version"] == "CAL FIRE FHSZ in LRA, 2025 v1"


def test_unresolved_layers_are_reported_rather_than_left_blank(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, user_id = client

    body = api.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", **DANVILLE},
        headers=auth(user_id),
    ).json()

    assert body["geo"]["fire_district"] is None
    assert set(body["geo"]["unresolved"]) == {"fire_district", "water_utility"}


def test_property_outside_every_layer_is_unknown(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, user_id = client

    body = api.post(
        "/v1/properties",
        json={"address": "Somewhere in Nevada", "lat": 39.5, "lng": -119.8},
        headers=auth(user_id),
    ).json()

    assert body["geo"]["fhsz"] == "unknown"


def test_coordinates_must_be_supplied_as_a_pair(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, user_id = client

    response = api.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", "lat": 37.8},
        headers=auth(user_id),
    )

    assert response.status_code == 422


def test_a_property_is_only_visible_to_its_owner(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, user_id = client
    created = api.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", **DANVILLE},
        headers=auth(user_id),
    ).json()

    stranger = uuid4()
    assert api.get(f"/v1/properties/{created['id']}", headers=auth(stranger)).status_code == 404
    assert api.get("/v1/properties", headers=auth(stranger)).json() == []
    assert len(api.get("/v1/properties", headers=auth(user_id)).json()) == 1


def test_requests_without_credentials_are_refused(
    client: tuple[TestClient, UUID], migrated_dsn: str
) -> None:
    api, _user_id = client

    assert api.get("/v1/properties").status_code == 401
