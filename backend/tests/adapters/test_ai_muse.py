"""MuseAI against a scripted Model API: request shape, reply validation, and the NFR-3 fallback."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from app.adapters.ai_fallback import FallbackAI
from app.adapters.ai_muse import NO_COURSE, MuseAI, MuseError
from app.domain.topic_rules import normalize_fallback
from app.domain.types import Topic
from app.services.ai_guard import GuardedAI
from app.wiring import build_ai
from tests.conftest import make_settings

KEY = "test-muse-key"
Handler = Callable[[httpx.Request], httpx.Response]


@dataclass(frozen=True)
class Host:
    id: str
    topic: Topic
    about_me: str | None = None


def reply(content: dict[str, Any] | str) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def muse(handler: Handler, seen: list[httpx.Request] | None = None) -> MuseAI:
    def record(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    return MuseAI(KEY, "https://muse.test/v1", "muse-spark-1.3", 2.0, httpx.MockTransport(record))


def body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)  # type: ignore[no-any-return]


def user_payload(request: httpx.Request) -> dict[str, Any]:
    return json.loads(body(request)["messages"][1]["content"])  # type: ignore[no-any-return]


ORGO = normalize_fallback("CH 320M stereochem")
TREES = normalize_fallback("C S 314 trees")


# normalize_topic


def test_request_is_strict_json_schema_with_minimal_reasoning() -> None:
    seen: list[httpx.Request] = []
    ai = muse(
        lambda r: reply({"course_code": "CH 320M", "subject": "chemistry", "keywords": []}), seen
    )
    ai.normalize_topic("orgo 1 exam prep")

    (request,) = seen
    assert request.url == "https://muse.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    sent = body(request)
    assert sent["model"] == "muse-spark-1.3"
    assert sent["reasoning_effort"] == "minimal"
    fmt = sent["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert NO_COURSE in schema["properties"]["course_code"]["enum"]
    # User text travels as JSON data in the user turn, never inside the instructions.
    assert user_payload(request) == {"text": "orgo 1 exam prep"}
    assert "orgo 1 exam prep" not in sent["messages"][0]["content"]


def test_catalog_course_takes_catalog_subject_and_label() -> None:
    ai = muse(
        lambda r: reply(
            {
                "course_code": "CH 320M",
                "subject": "chemistry",
                "keywords": ["Stereochemistry", "chair flips", "exam", "the", "SN2"],
            }
        )
    )
    topic = ai.normalize_topic("orgo 1 exam prep")
    assert topic.course_code == "CH 320M"
    assert topic.subject == "chemistry"
    assert topic.label == "CH 320M · Organic Chemistry I"
    # Same word rules as the fallback, so Jaccard ranking compares like with like.
    assert topic.keywords == ("stereochemistry", "chair", "flips", "sn2")


def test_no_catalog_course_keeps_an_explicit_code_from_the_text() -> None:
    ai = muse(
        lambda r: reply(
            {"course_code": NO_COURSE, "subject": "computer science", "keywords": ["compilers"]}
        )
    )
    topic = ai.normalize_topic("c s 375 compilers project")
    assert topic.course_code == "C S 375"
    assert topic.subject == "computer science"
    assert topic.keywords == ("compilers",)


def test_no_course_at_all_uses_the_muse_subject() -> None:
    ai = muse(
        lambda r: reply({"course_code": NO_COURSE, "subject": "physics", "keywords": ["torque"]})
    )
    topic = ai.normalize_topic("rotational motion stuff")
    assert topic == Topic(None, "physics", ("torque",), "Physics")


@pytest.mark.parametrize(
    "content",
    [
        {"course_code": "CH 999", "subject": "chemistry", "keywords": []},
        {"course_code": "CH 320M", "subject": "astrology", "keywords": []},
        {"course_code": "CH 320M", "subject": "chemistry"},
        "not json",
        "[]",
    ],
)
def test_out_of_schema_topic_raises(content: dict[str, Any] | str) -> None:
    with pytest.raises(MuseError):
        muse(lambda r: reply(content)).normalize_topic("orgo")


# rank_hosts


def test_rank_uses_aliases_and_maps_scores_back() -> None:
    seen: list[httpx.Request] = []
    hosts = [Host("sess-db-1", ORGO, "I like flashcards"), Host("sess-db-2", TREES)]
    ai = muse(
        lambda r: reply({"scores": [{"host": "h2", "score": 12}, {"host": "h1", "score": 150}]}),
        seen,
    )

    assert ai.rank_hosts(ORGO, hosts) == {"sess-db-1": 100, "sess-db-2": 12}  # clamped to 0-100
    raw = seen[0].content.decode()
    assert "sess-db-" not in raw
    sent = user_payload(seen[0])
    assert [h["id"] for h in sent["hosts"]] == ["h1", "h2"]
    assert sent["hosts"][0]["about_me"] == "I like flashcards"
    schema = body(seen[0])["response_format"]["json_schema"]["schema"]
    score_item = schema["properties"]["scores"]["items"]
    assert score_item["properties"]["host"]["enum"] == ["h1", "h2"]


@pytest.mark.parametrize(
    "scores",
    [
        [{"host": "h1", "score": 50}],  # one host missing
        [{"host": "h1", "score": 50}, {"host": "h1", "score": 60}],  # repeated
        [{"host": "h1", "score": 50}, {"host": "h9", "score": 60}],  # invented
    ],
)
def test_rank_rejects_incomplete_or_invented_scores(scores: list[dict[str, Any]]) -> None:
    hosts = [Host("a", ORGO), Host("b", TREES)]
    with pytest.raises(MuseError):
        muse(lambda r: reply({"scores": scores})).rank_hosts(ORGO, hosts)


def test_rank_with_no_hosts_makes_no_call() -> None:
    seen: list[httpx.Request] = []
    assert muse(lambda r: reply({}), seen).rank_hosts(ORGO, []) == {}
    assert seen == []


# icebreaker


def test_icebreaker_is_one_line_and_names_the_shared_course() -> None:
    seen: list[httpx.Request] = []
    ai = muse(lambda r: reply({"icebreaker": "  Which chair flip\nis tripping you up?  "}), seen)
    assert ai.icebreaker(ORGO, ORGO) == "Which chair flip is tripping you up?"
    assert user_payload(seen[0])["shared_course"] == ORGO.label
    ai.icebreaker(ORGO, TREES)
    assert user_payload(seen[1])["shared_course"] is None


# transport failures


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, json={"error": {"type": "server_error"}}),
        lambda r: httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}),
        lambda r: httpx.Response(401, json={"error": {"code": "invalid_api_key"}}),
        lambda r: httpx.Response(200, json={"choices": []}),
        lambda r: httpx.Response(200, text="<html>"),
    ],
)
def test_provider_errors_raise(handler: Handler) -> None:
    with pytest.raises(MuseError):
        muse(handler).icebreaker(ORGO, ORGO)


def test_connection_failure_raises() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(MuseError):
        muse(refuse).normalize_topic("orgo")


@pytest.fixture
def slow_server() -> Iterator[str]:
    class Slow(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            time.sleep(2)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def test_slow_provider_is_cut_off_at_the_timeout(slow_server: str) -> None:
    ai = MuseAI(KEY, slow_server, "muse-spark-1.3", timeout_s=0.3)
    started = time.monotonic()
    with pytest.raises(MuseError):
        ai.normalize_topic("orgo")
    assert time.monotonic() - started < 1.0


# NFR-3 through the guard, and wiring


def test_guarded_muse_failure_gives_the_fallback_answer() -> None:
    broken = GuardedAI(muse(lambda r: httpx.Response(503)))
    fallback = FallbackAI()
    hosts = [Host("a", ORGO), Host("b", TREES)]
    assert broken.normalize_topic("orgo 1 exam prep") == fallback.normalize_topic(
        "orgo 1 exam prep"
    )
    assert broken.rank_hosts(ORGO, hosts) == fallback.rank_hosts(ORGO, hosts)
    assert broken.icebreaker(ORGO, TREES) == fallback.icebreaker(ORGO, TREES)


def test_wiring_picks_muse_only_with_a_key() -> None:
    assert isinstance(build_ai(make_settings()), FallbackAI)
    assert isinstance(build_ai(make_settings(muse_api_key="k")), MuseAI)
