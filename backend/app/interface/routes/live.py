"""GET /api/live: the live stream (D61). Server-Sent Events, one stream per open app."""

from __future__ import annotations

import logging
from contextlib import aclosing
from typing import Annotated

import anyio
from fastapi import APIRouter, Header, Query, Response
from starlette.types import Message, Receive, Scope, Send

from app.interface.deps import OptionalUserId, ServicesDep
from app.services.live import LiveEvent, LiveService, Subscription

log = logging.getLogger("ghostseats.live")

router = APIRouter(prefix="/api", tags=["live"])


@router.get(
    "/live",
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-Sent Events"}},
)
async def live(
    services: ServicesDep,
    user_id: OptionalUserId,
    building: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    last_event_id: Annotated[str | None, Query(max_length=200)] = None,
    last_event_id_header: Annotated[
        str | None, Header(alias="Last-Event-ID", max_length=200)
    ] = None,
) -> Response:
    """Opened (or refused with the usual JSON error) before the first byte is streamed."""
    sub = await services.live.open(user_id, building, last_event_id_header or last_event_id)
    return LiveStream(sub, services.live)


def encode(event: LiveEvent) -> bytes:
    lines = [f"event: {event.kind}", f"id: {event.id}"]
    lines += [f"data: {line}" for line in event.data.split("\n")]
    return ("\n".join(lines) + "\n\n").encode()


class LiveStream(Response):
    """Streams one subscription until the client leaves, and closes it whatever happens. Each
    write has LIVE_STALL_S to complete: a client that stops reading (a phone gone from the
    network) is dropped rather than holding the connection."""

    media_type = "text/event-stream"

    def __init__(self, sub: Subscription, live: LiveService) -> None:
        super().__init__(
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            media_type=self.media_type,
        )
        self.raw_headers = [(k, v) for k, v in self.raw_headers if k != b"content-length"]
        self._sub = sub
        self._live = live

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await send({"type": "http.response.start", "status": 200, "headers": self.raw_headers})
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._until_disconnect, receive, tg.cancel_scope)
                await self._write(send, f"retry: {self._live.retry_ms()}\n\n".encode())
                async with aclosing(self._sub.events()) as events:
                    async for event in events:
                        await self._write(send, encode(event))
        except TimeoutError:
            pass  # stalled: the connection is abandoned with the stream
        except anyio.get_cancelled_exc_class():
            # Only the server cancels a stream from outside: its graceful-shutdown timeout ran
            # out. Ending here, rather than re-raising, spares the log one traceback per phone;
            # clients reconnect to whichever instance is up.
            log.info("live stream closed by server shutdown")
        finally:
            self._live.close(self._sub)

    async def _write(self, send: Send, chunk: bytes) -> None:
        message: Message = {"type": "http.response.body", "body": chunk, "more_body": True}
        with anyio.fail_after(self._live.stall_s):
            await send(message)

    @staticmethod
    async def _until_disconnect(receive: Receive, scope: anyio.CancelScope) -> None:
        while (await receive())["type"] != "http.disconnect":
            pass
        scope.cancel()
