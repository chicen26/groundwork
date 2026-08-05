"""Account deletion tests.

The privacy screen says deleting an account deletes the photographs. A cascade alone would leave the
files in storage — orphaned, but still photographs of somebody's house. These tests check the bytes
are gone, not just the rows.
"""

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


def photo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 150), (60, 90, 50)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def _seed(dsn: str) -> UUID:
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

    user_id = asyncio.run(_seed(TEST_DSN))
    with TestClient(create_app()) as client:
        yield client, {"X-Groundwork-User": str(user_id)}, tmp_path / "photos"
    get_settings.cache_clear()


def build_account(client: TestClient, headers: dict) -> str:
    property_id = client.post(
        "/v1/properties",
        json={"address": "1 Test Way, Danville, CA", "lat": 37.8216, "lng": -121.9999},
        headers=headers,
    ).json()["id"]
    scan_id = client.post(f"/v1/properties/{property_id}/scans", headers=headers).json()["id"]
    client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "front_elevation"},
        files={"file": ("front.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    )
    return property_id


def test_deleting_an_account_removes_the_photo_files(api, db_exec) -> None:
    """The promise on the privacy screen, checked against the filesystem."""
    client, headers, photo_root = api
    build_account(client, headers)
    files_before = list(Path(photo_root).rglob("*.jpg"))
    assert files_before, "the fixture must actually have written a photo"

    receipt = client.request(
        "DELETE", "/v1/account", json={"confirm": "DELETE"}, headers=headers
    ).json()

    assert receipt["photos_deleted"] == 1
    assert receipt["files_removed"] == 1
    assert receipt["files_failed"] == 0
    assert list(Path(photo_root).rglob("*.jpg")) == []


def test_deleting_an_account_removes_every_row(api, db_exec) -> None:
    client, headers, _ = api
    build_account(client, headers)

    client.request("DELETE", "/v1/account", json={"confirm": "DELETE"}, headers=headers)

    assert db_exec("SELECT count(*) FROM properties") == 0
    assert db_exec("SELECT count(*) FROM scans") == 0
    assert db_exec("SELECT count(*) FROM photos") == 0
    assert db_exec("SELECT count(*) FROM users") == 0


def test_deletion_requires_explicit_confirmation(api, db_exec) -> None:
    """A stray request must not be able to destroy somebody's data."""
    client, headers, _ = api
    build_account(client, headers)

    response = client.request("DELETE", "/v1/account", json={"confirm": "yes"}, headers=headers)

    assert response.status_code == 400
    assert db_exec("SELECT count(*) FROM properties") == 1


def test_deletion_does_not_touch_another_household(api, db_exec) -> None:
    client, headers, photo_root = api
    build_account(client, headers)

    other = uuid4()
    db_exec("INSERT INTO users (id, email) VALUES ($1, $2) RETURNING id", other, "b@example.test")
    other_headers = {"X-Groundwork-User": str(other)}
    build_account(client, other_headers)

    client.request("DELETE", "/v1/account", json={"confirm": "DELETE"}, headers=headers)

    assert db_exec("SELECT count(*) FROM users") == 1
    assert db_exec("SELECT count(*) FROM properties") == 1
    assert len(list(Path(photo_root).rglob("*.jpg"))) == 1


def test_deleting_an_empty_account_succeeds(api, db_exec) -> None:
    client, headers, _ = api

    receipt = client.request(
        "DELETE", "/v1/account", json={"confirm": "DELETE"}, headers=headers
    ).json()

    assert receipt["photos_deleted"] == 0
    assert receipt["files_failed"] == 0
