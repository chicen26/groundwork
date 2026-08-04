"""Local resources and planting palette tests.

Two product commitments get pinned here:

* The palette recommends nothing for the first five feet, and says why. A plant list for the band
  the draft Zone 0 rule wants non-combustible would contradict the advice beside it.
* No plant enters the database without a citation. Calscape's terms require attribution, and an
  uncited horticultural recommendation is not one we are in a position to make.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.routers.plants import EMBER_RESISTANT_ZONE
from app.routers.resources import resources_for_district
from scripts.import_plants import PlantImportError, validate
from tests.conftest import TEST_DSN, requires_db


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client wired to the test database when one is configured.

    Entered as a context manager so the app's lifespan runs and the connection pool actually
    exists — the palette queries the database, and a client built without lifespan would fail with
    an unhelpful "pool is not initialised" rather than a real result.

    The resource and import tests need no database at all; the palette ones are marked
    `requires_db` and skip cleanly on a checkout without Postgres.
    """
    if TEST_DSN:
        monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


# --------------------------------------------------------------------------- resources


def test_universal_resources_reach_everyone(client: TestClient) -> None:
    """An undetermined district must not read as "there is no help available"."""
    resources = resources_for_district(None)

    assert resources
    assert all(r.universal for r in resources)


def test_district_specific_resources_are_filtered_in() -> None:
    moraga = resources_for_district("MOFD")
    danville = resources_for_district("SRVFPD")

    assert any(r.key == "mofd_vent_mesh" for r in moraga)
    assert not any(r.key == "mofd_vent_mesh" for r in danville)
    assert any(r.key == "srvfpd_inspection" for r in danville)


def test_district_matching_is_case_insensitive() -> None:
    assert resources_for_district("mofd") == resources_for_district("MOFD")


def test_every_resource_links_to_its_own_agency() -> None:
    """We name the agency and link out rather than restating terms that go stale annually."""
    for resource in resources_for_district("MOFD"):
        assert resource.url.startswith("https://")
        assert resource.agency


def test_the_evacuation_link_disclaims_evacuation_guidance() -> None:
    """Groundwork gives none. The one evacuation-adjacent entry has to say so on its face."""
    genasys = next(r for r in resources_for_district(None) if r.key == "genasys_evacuation_zones")

    assert genasys.external_only is True
    assert genasys.disclaimer and "no evacuation guidance" in genasys.disclaimer.lower()


def test_resources_are_served_over_http(client: TestClient) -> None:
    body = client.get("/v1/resources?district=MOFD").json()

    assert any(r["key"] == "mofd_chipping" for r in body)


# --------------------------------------------------------------------------- palette


def test_the_palette_recommends_nothing_for_the_first_five_feet(client: TestClient) -> None:
    body = client.get(f"/v1/plants?zone={EMBER_RESISTANT_ZONE}").json()

    assert body["plants"] == []
    assert "non-combustible" in body["note"]
    # And it says Zone 0 is not law yet, wherever it appears.
    assert "draft" in body["note"].lower()


@requires_db
def test_the_palette_always_carries_its_attribution(client: TestClient, migrated_dsn: str) -> None:
    body = client.get("/v1/plants?zone=5-30ft").json()

    assert "WUCOLS" in body["attribution"]
    assert "California Native Plant Society" in body["attribution"]


@requires_db
def test_an_empty_palette_says_so_rather_than_looking_broken(
    client: TestClient, migrated_dsn: str
) -> None:
    """Before the imports run there are no plants, and the screen should be honest about that."""
    body = client.get("/v1/plants?zone=30-100ft").json()

    if not body["plants"]:
        assert body["note"]


# --------------------------------------------------------------------------- plant import


def base_plant() -> dict:
    return {
        "common_name": "Test plant",
        "scientific_name": "Testus plantus",
        "wucols_rating": "low",
        "native": True,
        "zones_allowed": ["5-30ft"],
        "sources": ["WUCOLS V", "Calscape (CNPS)"],
    }


def test_a_plant_without_sources_is_refused() -> None:
    entry = base_plant()
    entry["sources"] = []

    with pytest.raises(PlantImportError, match="sources"):
        validate(entry, 1)


def test_a_plant_cannot_be_allowed_in_the_first_five_feet() -> None:
    """The importer refuses it, so no future data drop can quietly contradict the Zone 0 advice."""
    entry = base_plant()
    entry["zones_allowed"] = ["0-5ft"]

    with pytest.raises(PlantImportError, match="non-combustible"):
        validate(entry, 1)


def test_an_unknown_water_rating_is_refused() -> None:
    entry = base_plant()
    entry["wucols_rating"] = "quite thirsty"

    with pytest.raises(PlantImportError, match="WUCOLS"):
        validate(entry, 1)


def test_a_plant_without_a_name_is_refused() -> None:
    entry = base_plant()
    entry["scientific_name"] = ""

    with pytest.raises(PlantImportError, match="scientific_name"):
        validate(entry, 1)


def test_a_well_formed_plant_validates() -> None:
    result = validate(base_plant(), 1)

    assert result["scientific_name"] == "Testus plantus"
    assert result["sources"] == ["WUCOLS V", "Calscape (CNPS)"]


def test_the_resources_file_flags_everything_for_re_verification() -> None:
    """Funding and deadlines change yearly; sending someone to a closed programme wastes a trip."""
    path = Path(__file__).resolve().parents[1] / "programs" / "resources.json"
    payload = json.loads(path.read_text())

    for entry in payload["resources"]:
        assert entry.get("verify_before_launch") is True, entry["key"]
