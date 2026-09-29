"""M8: the HTTP layer. It must add nothing but transport."""

import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app

SAMPLE = "tests/vulnerable_samples/flask_app"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_scan_returns_the_same_report_the_cli_produces(client):
    response = client.post("/scan", json={"path": SAMPLE, "mock": True})

    assert response.status_code == 200
    report = response.json()
    assert report["candidates_found"] == 1
    item = report["items"][0]
    assert item["id"] == "VULN-001"
    assert item["analysis"]["status"] == "Likely Vulnerable"
    assert item["analysis"]["data_flow"] == [
        "routes/search.py", "services/search_service.py", "database/user_repository.py"
    ]
    assert item["explanation"] and item["suggested_fix"]


@pytest.mark.parametrize(
    "payload",
    [{}, {"path": "a", "repo_url": "b"}],  # neither source, and both at once
    ids=["no source", "two sources"],
)
def test_request_must_name_exactly_one_source(client, payload):
    assert client.post("/scan", json=payload).status_code == 422


def test_bad_path_is_a_client_error(client):
    response = client.post("/scan", json={"path": "/no/such/place", "mock": True})
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_schema_is_published(client):
    schema = client.get("/openapi.json").json()
    assert "/scan" in schema["paths"] and "/health" in schema["paths"]
