"""Lawn measurement tests.

The area is what a rebate is calculated from, so it is computed server-side from the geometry and
never taken from the client. These tests check that PostGIS is measuring what we think it is, that a
malformed outline is refused with something actionable, and that a property whose utility we could
not determine sees every programme rather than a guessed one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db

# A rectangle in Danville, sized so the expected area is easy to reason about independently.
# 0.001° of latitude is ~111.2 m; 0.001° of longitude at 37.82°N is ~88.0 m.
LAWN = {
    "type": "Polygon",
    "coordinates": [
        [
            [-121.9999, 37.8216],
            [-121.9989, 37.8216],
            [-121.9989, 37.8226],
            [-121.9999, 37.8226],
            [-121.9999, 37.8216],
        ]
    ],
}


async def _seed(dsn: str, *, utility: str | None) -> UUID:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
        return await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
        )
    finally:
        await conn.close()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, tmp_path, migrated_dsn: str) -> Iterator[tuple]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.setenv("GROUNDWORK_PHOTO_STORAGE_ROOT", str(tmp_path / "photos"))
    monkeypatch.delenv("GROUNDWORK_SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    user_id = asyncio.run(_seed(TEST_DSN, utility=None))
    with TestClient(create_app()) as client:
        yield client, {"X-Groundwork-User": str(user_id)}
    get_settings.cache_clear()


def make_property(client: TestClient, headers: dict, utility: str | None, db_exec) -> str:
    body = client.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", "lat": 37.8216, "lng": -121.9999},
        headers=headers,
    ).json()
    if utility:
        db_exec("UPDATE properties SET water_utility = $2 WHERE id = $1", UUID(body["id"]), utility)
    return body["id"]


def test_the_area_is_measured_geodesically_by_the_server(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    body = client.post(
        f"/v1/properties/{property_id}/lawn",
        json={"label": "Front lawn", "geojson": LAWN},
        headers=headers,
    ).json()

    # ~88.0 m x ~111.2 m is ~9,790 m², about 105,000 sq ft. Wide bounds: the point is that PostGIS
    # measured a real geodesic area, not that we can predict it to the foot.
    area = Decimal(body["area_sqft"])
    assert Decimal("100000") < area < Decimal("112000")


def test_the_rebate_uses_the_properties_own_utility(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "DSRSD", db_exec)

    body = client.post(
        f"/v1/properties/{property_id}/lawn", json={"geojson": LAWN}, headers=headers
    ).json()

    assert body["utility"] == "DSRSD"
    assert body["showing_all_programs"] is False
    assert len(body["rebates"]) == 1
    # A lawn this size is far past every cap, which is the common real-world case.
    assert body["rebates"][0]["amount_usd"] == "3000.00"
    assert body["rebates"][0]["capped"] is True


def test_an_unknown_utility_shows_every_programme(api, db_exec) -> None:
    """Better three named agencies than one confident wrong rate."""
    client, headers = api
    property_id = make_property(client, headers, None, db_exec)

    body = client.post(
        f"/v1/properties/{property_id}/lawn", json={"geojson": LAWN}, headers=headers
    ).json()

    assert body["showing_all_programs"] is True
    assert {r["agency"] for r in body["rebates"]} == {"EBMUD", "CCWD", "DSRSD"}


def test_every_response_carries_the_pre_approval_warning(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    body = client.post(
        f"/v1/properties/{property_id}/lawn", json={"geojson": LAWN}, headers=headers
    ).json()

    assert "BEFORE" in body["warning"]
    for rebate in body["rebates"]:
        assert rebate["warning"]


def test_the_water_saving_is_reported_with_its_basis(api, db_exec) -> None:
    """A gallons figure without its basis reads as a measurement rather than an estimate."""
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    body = client.post(
        f"/v1/properties/{property_id}/lawn", json={"geojson": LAWN}, headers=headers
    ).json()

    assert int(body["annual_gallons_saved"]) > 0
    assert "estimate" in body["savings_basis"].lower()


def test_an_unclosed_ring_is_refused(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    response = client.post(
        f"/v1/properties/{property_id}/lawn",
        json={
            "geojson": {
                "type": "Polygon",
                "coordinates": [[[-121.99, 37.82], [-121.98, 37.82], [-121.98, 37.83]]],
            }
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_a_non_polygon_is_refused(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    response = client.post(
        f"/v1/properties/{property_id}/lawn",
        json={"geojson": {"type": "Point", "coordinates": [-121.99, 37.82]}},
        headers=headers,
    )

    assert response.status_code == 422


def test_another_household_cannot_measure_your_lawn(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)

    response = client.post(
        f"/v1/properties/{property_id}/lawn",
        json={"geojson": LAWN},
        headers={"X-Groundwork-User": str(uuid4())},
    )

    assert response.status_code == 404


def test_saved_lawns_can_be_listed_again(api, db_exec) -> None:
    client, headers = api
    property_id = make_property(client, headers, "CCWD", db_exec)
    client.post(
        f"/v1/properties/{property_id}/lawn",
        json={"label": "Front", "geojson": LAWN},
        headers=headers,
    )

    listed = client.get(f"/v1/properties/{property_id}/lawn", headers=headers).json()

    assert len(listed) == 1
    assert listed[0]["label"] == "Front"


def test_the_programme_catalogue_is_served(api) -> None:
    client, headers = api

    body = client.get("/v1/programs/rebates", headers=headers).json()

    assert {p["agency"] for p in body["programs"]} == {"EBMUD", "CCWD", "DSRSD"}
    assert "BEFORE" in body["warning"]
