"""The public impact numbers: real totals, and an honest zero before there is anything to count."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, migrated_dsn: str) -> Iterator[TestClient]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.delenv("GROUNDWORK_SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    async def wipe() -> None:
        conn = await asyncpg.connect(TEST_DSN)
        try:
            await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
        finally:
            await conn.close()

    asyncio.run(wipe())
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_an_empty_install_reports_zeros_not_errors(client) -> None:
    body = client.get("/v1/stats/impact").json()

    assert body == {
        "properties": 0,
        "assessments": 0,
        "plan_items_done": 0,
        "hazards_addressed": 0,
        "lawn_sqft_measured": 0,
        "annual_gallons_saved": 0,
        "rebate_dollars_identified": 0,
    }


def test_impact_needs_no_authentication(client) -> None:
    # The welcome screen shows this before anyone has an account.
    assert client.get("/v1/stats/impact").status_code == 200
