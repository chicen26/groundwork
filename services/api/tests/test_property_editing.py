"""Editing and deleting a property after setup."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db

DANVILLE = {"lat": 37.8216, "lng": -121.9999}
NEVADA = {"lat": 39.5, "lng": -119.8}


async def _seed(dsn: str) -> UUID:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
        )
        version = await conn.fetchval(
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
            version,
        )
        return user_id
    finally:
        await conn.close()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, tmp_path, migrated_dsn: str) -> Iterator[tuple]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.setenv("GROUNDWORK_PHOTO_STORAGE_ROOT", str(tmp_path / "photos"))
    get_settings.cache_clear()
    user_id = asyncio.run(_seed(TEST_DSN))
    with TestClient(create_app()) as client:
        yield client, {"X-Groundwork-User": str(user_id)}, tmp_path / "photos"
    get_settings.cache_clear()


def make_property(client, headers) -> dict:
    return client.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", **DANVILLE},
        headers=headers,
    ).json()


def test_renaming_changes_nothing_else(api) -> None:
    client, headers, _ = api
    prop = make_property(client, headers)

    body = client.patch(
        f"/v1/properties/{prop['id']}", json={"label": "Home"}, headers=headers
    ).json()

    assert body["label"] == "Home"
    assert body["geo"]["fhsz"] == "very_high"


def test_moving_re_resolves_the_zone(api) -> None:
    """A moved property is a different property as far as the law is concerned."""
    client, headers, _ = api
    prop = make_property(client, headers)

    body = client.patch(
        f"/v1/properties/{prop['id']}",
        json={"address": "2 Elsewhere, NV", **NEVADA},
        headers=headers,
    ).json()

    assert body["geo"]["fhsz"] == "unknown"
    assert body["lat"] == pytest.approx(NEVADA["lat"])


def test_a_stranger_cannot_edit_or_delete(api) -> None:
    client, headers, _ = api
    prop = make_property(client, headers)
    stranger = {"X-Groundwork-User": str(uuid4())}

    assert (
        client.patch(f"/v1/properties/{prop['id']}", json={"label": "x"}, headers=stranger)
    ).status_code == 404
    assert client.delete(f"/v1/properties/{prop['id']}", headers=stranger).status_code == 404
    assert client.get(f"/v1/properties/{prop['id']}", headers=headers).status_code == 200


def test_deleting_a_property_removes_its_photo_files(api) -> None:
    """Same promise as account deletion, scoped to one address."""
    client, headers, photo_root = api
    prop = make_property(client, headers)
    scan = client.post(f"/v1/properties/{prop['id']}/scans", headers=headers).json()
    buffer = io.BytesIO()
    Image.new("RGB", (200, 150), (60, 90, 50)).save(buffer, format="JPEG")
    client.post(
        f"/v1/scans/{scan['id']}/photos",
        data={"station": "front_elevation"},
        files={"file": ("f.jpg", buffer.getvalue(), "image/jpeg")},
        headers=headers,
    )
    assert list(Path(photo_root).rglob("*.jpg"))

    assert client.delete(f"/v1/properties/{prop['id']}", headers=headers).status_code == 204

    assert client.get("/v1/properties", headers=headers).json() == []
    assert list(Path(photo_root).rglob("*.jpg")) == []


def test_half_a_coordinate_is_refused(api) -> None:
    client, headers, _ = api
    prop = make_property(client, headers)

    response = client.patch(f"/v1/properties/{prop['id']}", json={"lat": 39.5}, headers=headers)

    assert response.status_code == 422
