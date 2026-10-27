"""Request ids, the access line and JSON logs (D60)."""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.interface.observability import JsonFormatter, configure_logging
from tests.api.conftest import World
from tests.api.harness import PERSON
from tests.conftest import NODE_KEY
from tests.world import NODE

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def json_lines() -> Iterator[Callable[[], list[dict[str, Any]]]]:
    """Every log line written during the test, through the JSON formatter."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(level)


def _access(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [line for line in lines if line["logger"] == "ghostseats.http"]


def test_every_response_carries_a_generated_request_id(world: World) -> None:
    first = world.phone().get("/api/buildings").headers["X-Request-ID"]
    second = world.phone().get("/api/buildings").headers["X-Request-ID"]
    assert GENERATED_ID.fullmatch(first) and GENERATED_ID.fullmatch(second)
    assert first != second


@pytest.mark.parametrize(
    ("sent", "kept"),
    [("lb-7f3a-0001", True), ("a" * 64, True), ("a" * 65, False), ("id with spaces", False)],
)
def test_a_plain_incoming_id_is_kept_and_anything_else_replaced(
    world: World, sent: str, kept: bool
) -> None:
    got = world.phone().get("/api/buildings", headers={"X-Request-ID": sent}).headers
    assert (got["X-Request-ID"] == sent) is kept
    if not kept:
        assert GENERATED_ID.fullmatch(got["X-Request-ID"])


def test_access_line_has_the_route_template_status_and_duration(
    world: World, json_lines: Callable[[], list[dict[str, Any]]]
) -> None:
    phone = world.phone()
    phone.get("/api/buildings/lib", headers={"X-Request-ID": "req-1"})
    phone.get("/api/nothing-here", headers={"X-Request-ID": "req-2"})
    lines = {line["request_id"]: line for line in _access(json_lines())}
    assert lines["req-1"]["route"] == "/api/buildings/{building_id}"
    assert lines["req-1"]["path"] == "/api/buildings/lib"
    assert lines["req-1"]["status"] == 200 and lines["req-1"]["method"] == "GET"
    assert isinstance(lines["req-1"]["duration_ms"], float)
    assert lines["req-2"]["route"] == "unmatched" and lines["req-2"]["status"] == 404


def test_service_log_lines_inside_a_request_carry_its_id(
    world: World, json_lines: Callable[[], list[dict[str, Any]]]
) -> None:
    """The id must cross into the threadpool where sync routes and services run."""
    unknown_seat = {"seat_id": "nope", "object_present": True, "human_present": True}
    r = world.node.http.post(
        "/api/readings",
        json={"node_id": NODE, "readings": [unknown_seat]},
        headers={"X-Node-Key": NODE_KEY, "X-Request-ID": "ingest-1"},
    )
    assert r.status_code == 200
    skipped = [line for line in json_lines() if line["logger"] == "ghostseats.readings"]
    assert [line.get("request_id") for line in skipped] == ["ingest-1"]


def test_lines_outside_a_request_have_no_id(
    world: World, json_lines: Callable[[], list[dict[str, Any]]]
) -> None:
    world.node.set("s1", PERSON)
    world.node.post()  # a request ran; its id must not leak into the caller's context
    logging.getLogger("ghostseats.worker").info("tick")
    (tick,) = [line for line in json_lines() if line["logger"] == "ghostseats.worker"]
    assert tick["msg"] == "tick" and "request_id" not in tick


def test_an_unhandled_error_keeps_its_id_on_the_response_and_the_log(
    world: World,
    json_lines: Callable[[], list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(world.services.map, "buildings", boom)
    client = TestClient(world.app, raise_server_exceptions=False)
    r = client.get("/api/buildings", headers={"X-Request-ID": "fail-1"})
    assert r.status_code == 500 and r.headers["X-Request-ID"] == "fail-1"
    errors = [line for line in json_lines() if line["logger"] == "ghostseats.errors"]
    assert errors[0]["request_id"] == "fail-1"
    assert "RuntimeError: boom" in errors[0]["exc"]


def test_json_mode_routes_uvicorn_through_the_root_and_turns_its_access_log_off() -> None:
    names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    root = logging.getLogger()
    saved_root = (root.handlers[:], root.level)
    saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names}
    try:
        logging.getLogger("uvicorn").addHandler(logging.NullHandler())
        logging.getLogger("uvicorn.access").propagate = True
        configure_logging("json")
        assert [type(h.formatter) for h in root.handlers] == [JsonFormatter]
        for name in ("uvicorn", "uvicorn.error"):
            assert logging.getLogger(name).handlers == [] and logging.getLogger(name).propagate
        access = logging.getLogger("uvicorn.access")
        assert not access.hasHandlers()  # uvicorn checks exactly this before logging
    finally:
        root.handlers[:], level = saved_root
        root.setLevel(level)
        for name, (handlers, propagate) in saved.items():
            logging.getLogger(name).handlers[:] = handlers
            logging.getLogger(name).propagate = propagate
