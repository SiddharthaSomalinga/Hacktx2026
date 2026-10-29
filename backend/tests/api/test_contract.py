"""Every endpoint in REQUIREMENTS §7 is registered, and documented in /docs (contract first)."""

from __future__ import annotations

from fastapi.testclient import TestClient

REQUIRED = {
    ("GET", "/api/health"),
    ("POST", "/api/readings"),
    ("GET", "/api/buildings"),
    ("GET", "/api/buildings/{building_id}"),
    ("GET", "/api/seats/{seat_id}"),
    ("GET", "/api/recommend"),
    ("GET", "/api/buildings/{building_id}/history"),
    ("GET", "/api/demo-users"),
    ("POST", "/api/login"),
    ("POST", "/api/logout"),
    ("GET", "/api/me"),
    ("POST", "/api/search"),
    ("POST", "/api/search/{search_id}/join"),
    ("GET", "/api/search/{search_id}"),
    ("POST", "/api/search/{search_id}/cancel"),
    ("POST", "/api/host/link"),
    ("POST", "/api/host/topic"),
    ("POST", "/api/host/toggle"),
    ("POST", "/api/host/mute"),
    ("POST", "/api/host/confirm"),
    ("GET", "/api/host/inbox"),
    ("POST", "/api/requests/{request_id}/accept"),
    ("POST", "/api/requests/{request_id}/decline"),
    ("GET", "/api/matches/{match_id}"),
    ("POST", "/api/matches/{match_id}/arrived"),
    ("POST", "/api/matches/{match_id}/cancel"),
    ("POST", "/api/block"),
    ("POST", "/api/report"),
    ("GET", "/api/push/vapid-public-key"),
    ("POST", "/api/push/subscribe"),
    ("DELETE", "/api/push/subscribe"),
    ("GET", "/api/live"),
}


def test_every_contract_endpoint_is_in_the_openapi_document(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    registered = {(method.upper(), path) for path, ops in spec["paths"].items() for method in ops}
    assert REQUIRED - registered == set()


def test_unknown_route_uses_the_error_body(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_validation_errors_use_the_error_body(client: TestClient) -> None:
    response = client.post("/api/login", json={"user_id": ""})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_readings_require_the_node_key(client: TestClient) -> None:
    response = client.post("/api/readings", json={"node_id": "n", "readings": []})
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_node_key"


def test_health_reports_database_reachability(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"ok": True, "db": True}


def test_settings_reject_a_short_secret_key() -> None:
    import pytest
    from pydantic import ValidationError

    from tests.conftest import make_settings

    with pytest.raises(ValidationError):
        make_settings(secret_key="short")
