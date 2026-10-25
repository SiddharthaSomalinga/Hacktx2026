"""Security floor checks: bounded inputs, cookie flags, quiet failures, static-file containment."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import World
from tests.conftest import make_settings


def test_overlong_path_ids_are_rejected_before_any_lookup(world: World) -> None:
    alex = world.phone("alex")
    assert alex.error("GET", "/api/search/" + "a" * 65) == (422, "validation_error")
    assert world.phone().error("GET", "/api/buildings/" + "b" * 65) == (422, "validation_error")


def test_overlong_bodies_are_rejected(world: World) -> None:
    alex = world.phone("alex")
    assert alex.error("POST", "/api/search", {"topic_raw": "x" * 201}) == (422, "validation_error")
    assert alex.error("POST", "/api/report", {"user_id": "sam", "reason": "x" * 501}) == (
        422,
        "validation_error",
    )
    assert alex.error("POST", "/api/search", {"topic_raw": "x", "extra": 1}) == (
        422,
        "validation_error",
    )


def test_session_cookie_is_httponly_and_samesite_lax(world: World) -> None:
    r = world.phone().http.post("/api/login", json={"user_id": "alex"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie


def test_secure_cookie_in_production(make_world: Callable[..., World]) -> None:
    w = make_world(map_cache_s=0, cookie_secure=True)
    r = TestClient(w.app, base_url="https://testserver").post(
        "/api/login", json={"user_id": "alex"}
    )
    assert "secure" in r.headers["set-cookie"].lower()


def test_tampered_session_cookie_is_not_trusted(world: World) -> None:
    client = TestClient(world.app)
    client.cookies.set("gs_session", "eyJ1c2VyX2lkIjogImFsZXgifQ==.forged.signature")
    r = client.get("/api/me")
    assert r.json()["user"] is None


def test_unexpected_errors_do_not_leak_internals(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> object:
        raise RuntimeError('psycopg: relation "secret_table" does not exist at /srv/app.py')

    monkeypatch.setattr(world.services.map, "buildings", boom)
    r = TestClient(world.app, raise_server_exceptions=False).get("/api/buildings")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error", "message": "Something went wrong on our side"}


def test_static_frontend_cannot_escape_its_folder(tmp_path: Path, world: World) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>app")
    (dist / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    app = create_app(make_settings(frontend_dist=str(dist)), world.services)
    client = TestClient(app)
    assert client.get("/app.js").text == "console.log(1)"
    assert client.get("/seat/t1-s1").text == "<!doctype html>app"  # SPA route
    for probe in (
        "/../secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/a/../../secret.txt",
    ):
        assert "TOP SECRET" not in client.get(probe).text, probe


@pytest.mark.xfail(strict=True, reason="bug: the SPA catch-all answers unknown /api paths")
def test_unknown_api_paths_stay_json_404_with_the_frontend_mounted(
    tmp_path: Path, world: World
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>app")
    client = TestClient(create_app(make_settings(frontend_dist=str(dist)), world.services))
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
