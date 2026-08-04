"""Rulebook endpoint tests.

The client renders citations and caveats from what this serves, so the shape it returns is part of
the promise that a finding can always be traced to its source.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_the_active_rulebook_is_listed(client: TestClient) -> None:
    body = client.get("/v1/rulebooks").json()

    assert body["active"] in body["available"], "the pinned rulebook must actually ship"


def test_a_rulebook_serves_its_rules_with_citations(client: TestClient) -> None:
    body = client.get("/v1/rulebooks/2026.08").json()

    assert body["disclaimer"]
    assert body["rules"]
    for rule in body["rules"]:
        assert rule["citation"] and rule["authority"]


def test_pending_rules_serve_their_caveat(client: TestClient) -> None:
    body = client.get("/v1/rulebooks/2026.08").json()

    for rule in body["rules"]:
        if rule["status"] == "pending_adoption":
            assert rule["caveat"]


def test_an_unknown_rulebook_is_a_404(client: TestClient) -> None:
    assert client.get("/v1/rulebooks/1999.01").status_code == 404
