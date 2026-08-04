import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["environment"]


def test_health_exposes_rulebook_version(client: TestClient) -> None:
    """Findings cite rules, so the client must always be able to name the rulebook behind them."""
    body = client.get("/v1/health").json()

    assert "rulebook_version" in body
    assert body["rulebook_version"]


def test_openapi_schema_is_served(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/v1/health" in schema["paths"]
