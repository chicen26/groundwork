"""Address suggestions and the ZIP quick look.

Photon is faked at the module's request functions, the same seam the geocoder tests use for the
Census service: the tests own what "upstream said" so they can assert on caching, filtering, and
what happens when upstream says nothing at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.geo import suggest as suggest_module
from app.geo.suggest import AddressSuggestion, SuggestionsUnavailable, ZipCentroid
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db

# Matches the fhsz fixture polygon below.
DANVILLE_ZIP = ZipCentroid(
    zip="94526", place="Danville", state_code="CA", lat=37.8216, lng=-121.9999
)


async def _arrange(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
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
    finally:
        await conn.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.delenv("GROUNDWORK_SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    asyncio.run(_arrange(TEST_DSN))
    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_suggestions_come_back_labelled_with_coordinates(client, monkeypatch) -> None:
    monkeypatch.setattr(
        suggest_module,
        "_request_suggestions",
        lambda text: [
            AddressSuggestion(label="100 Love Ln, Danville, California 94526", lat=37.8, lng=-122.0)
        ],
    )

    body = client.get("/v1/geo/suggest", params={"q": "100 love"}).json()

    assert body == [
        {"label": "100 Love Ln, Danville, California 94526", "lat": 37.8, "lng": -122.0}
    ]


def test_suggestions_are_cached_so_a_repeat_never_calls_photon_twice(client, monkeypatch) -> None:
    calls: list[str] = []

    def fake(text: str) -> list[AddressSuggestion]:
        calls.append(text)
        return [AddressSuggestion(label="1 Test Way, Danville, California", lat=37.8, lng=-122.0)]

    monkeypatch.setattr(suggest_module, "_request_suggestions", fake)

    first = client.get("/v1/geo/suggest", params={"q": "1 Test Way"}).json()
    second = client.get("/v1/geo/suggest", params={"q": "  1 test  way "}).json()

    assert first == second
    assert calls == ["1 Test Way"]  # the second spelling normalised onto the cached entry


def test_photon_trouble_yields_an_empty_list_not_an_error(client, monkeypatch) -> None:
    def broken(text: str) -> list[AddressSuggestion]:
        raise SuggestionsUnavailable("photon unreachable")

    monkeypatch.setattr(suggest_module, "_request_suggestions", broken)

    response = client.get("/v1/geo/suggest", params={"q": "100 love"})

    assert response.status_code == 200
    assert response.json() == []


def test_quick_look_resolves_the_zone_at_the_zip_centroid(client, monkeypatch) -> None:
    monkeypatch.setattr(suggest_module, "_request_zip", lambda z: DANVILLE_ZIP)

    body = client.get("/v1/geo/quick-look", params={"zip": "94526"}).json()

    assert body["fhsz"] == "very_high"
    assert body["place"] == "Danville"
    assert body["state_code"] == "CA"
    # The client must be able to say "this is rough" without inferring it.
    assert body["approximate"] is True
    assert set(body["unresolved"]) == {"fire_district", "water_utility"}


def test_quick_look_for_an_unplaceable_zip_says_try_a_full_address(client, monkeypatch) -> None:
    def broken(zip_code: str) -> ZipCentroid:
        raise SuggestionsUnavailable("no US place found")

    monkeypatch.setattr(suggest_module, "_request_zip", broken)

    response = client.get("/v1/geo/quick-look", params={"zip": "99999"})

    assert response.status_code == 422
    assert "full street address" in response.json()["detail"]


def test_quick_look_rejects_anything_that_is_not_five_digits(client) -> None:
    assert client.get("/v1/geo/quick-look", params={"zip": "9452"}).status_code == 422
    assert client.get("/v1/geo/quick-look", params={"zip": "abcde"}).status_code == 422
