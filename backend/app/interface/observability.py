"""Request ids, the access log and JSON log lines (D60).

Every HTTP request gets an id: the caller's `X-Request-ID` when it is short and plain, else a
fresh one. It goes back on the response and onto every log line written while the request
runs, services included. Lines from the worker thread carry no id.
"""

from __future__ import annotations

import json
import logging
import logging.config
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.metrics import MetricsService

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

UNMATCHED = "unmatched"  # route label for paths no route matched; keeps labels bounded
# JSON logging for the whole process tree. The image also hands it to uvicorn as --log-config,
# because uvicorn's supervisor process logs before (and without) ever calling build().
JSON_LOG_CONFIG = Path(__file__).resolve().parents[1] / "log_config.json"
_PLAIN_ID = re.compile(r"[A-Za-z0-9-]{1,64}")
_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

access_log = logging.getLogger("ghostseats.http")


class JsonFormatter(logging.Formatter):
    """One JSON object per line. A call's `extra={"fields": {...}}` is merged into it."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id.get()
        if rid is not None:
            line["request_id"] = rid
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging(log_format: str) -> None:
    """JSON: every line, uvicorn's included, through JsonFormatter, with `uvicorn.access` off
    because RequestContext writes the access line. Text: the app's lines in a plain format;
    uvicorn keeps its own handlers."""
    if log_format == "json":
        logging.config.dictConfig(json.loads(JSON_LOG_CONFIG.read_text()))
    else:
        logging.basicConfig(level=logging.INFO, format=_TEXT_FORMAT)


def route_template(scope: Scope) -> str:
    """The matched route's path template (`/api/requests/{request_id}`), never the raw path."""
    route = scope.get("route")
    return getattr(route, "path", UNMATCHED) if route is not None else UNMATCHED


class RequestContext:
    """Pure ASGI middleware: assigns the request id, echoes it, writes one access line and
    records the request's duration and body bytes. A live stream (`text/event-stream`, D61) is
    recorded as a stream instead: its duration is how long a phone stayed, not a latency."""

    def __init__(self, app: ASGIApp, metrics: MetricsService) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = _incoming_id(scope) or uuid.uuid4().hex
        # Not reset afterwards: each request runs in its own task with its own context, and
        # the outermost error handler, which runs after this middleware returns, still needs it.
        request_id.set(rid)
        started = time.perf_counter()
        status = 500  # what the client gets if the app raises before responding
        stream = False
        sent = 0

        async def send_with_id(message: Message) -> None:
            nonlocal status, stream, sent
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", rid)
                stream = headers.get("content-type", "").startswith("text/event-stream")
                if stream:
                    self.metrics.stream_opened()
            elif message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed_s = time.perf_counter() - started
            elapsed_ms = elapsed_s * 1000
            method, path, route = scope["method"], scope["path"], route_template(scope)
            self.metrics.count_bytes(route, sent)
            if stream:
                self.metrics.stream_closed(elapsed_s)
            else:
                self.metrics.observe_request(method, route, status, elapsed_s)
            access_log.info(
                "%s %s %d %.1fms",
                method,
                path,
                status,
                elapsed_ms,
                extra={
                    "fields": {
                        "method": method,
                        "path": path,
                        "route": route,
                        "status": status,
                        "duration_ms": round(elapsed_ms, 1),
                        "bytes": sent,
                        "stream": stream,
                    }
                },
            )


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            text = value.decode("latin-1")
            return text if _PLAIN_ID.fullmatch(text) else None
    return None
