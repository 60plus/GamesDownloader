"""Refusing an oversized request body before anything has read it.

Every write in this API used to accept a body of any size. FastAPI spools a
multipart upload to a temporary file and hands the handler an `UploadFile`, so
a handler that checks `len(await file.read())` has already spent the disk and
the memory by the time it decides to say no. That is a denial of service that
costs the attacker one request, and any account with the plain user role can
send it: a save, a savestate, an avatar, a collection image, a torrent file.

A reverse proxy would normally hold this line with `client_max_body_size`, but
GD publishes uvicorn directly, so there is nothing in front to hold it. This
middleware is that missing ceiling.

Two halves, and both are needed. The declared `Content-Length` turns away an
honestly labelled giant before a single byte is read, which is the cheap and
common case. The running total is there for the request that lies about its
length or declines to state one at all: a chunked body carries no length, so
without counting it would sail past untouched.

Routes that legitimately carry tens of gigabytes are listed with no ceiling on
purpose. A ROM, a game build and a metadata restore all stream to disk and
enforce their own limit as they go, and inventing a number for them here would
be a worse lie than no number.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MB = 1024 * 1024
_GB = 1024 * _MB

#: Applies to anything the table below does not name. Almost every write in
#: this API is a JSON body of a few kilobytes, so this is generous by orders of
#: magnitude and still finite, which is the whole point.
DEFAULT_MAX_BODY = 16 * _MB

#: `None` means the route streams to disk and polices itself while it does.
#: First match wins, so the order of this list is the policy - put the specific
#: route above the prefix that would otherwise swallow it.
_RULES: list[tuple[re.Pattern[str], int | None]] = [
    # Streams to disk, own ceiling, legitimately enormous.
    (re.compile(r"^/api/library/games/\d+/upload$"), None),
    (re.compile(r"^/api/roms/platforms/[^/]+/upload$"), None),
    (re.compile(r"^/api/settings/metadata-backup/restore$"), None),

    # Large but bounded.
    (re.compile(r"^/api/library/games/\d+/video/upload$"), 1 * _GB + 16 * _MB),
    (re.compile(r"^/api/savestates/import$"), 512 * _MB),
    # A trailer, not a feature film. This route had no ceiling of any kind
    # before: it streams straight to the resources directory in one megabyte
    # chunks without ever totalling them up.
    (re.compile(r"^/api/roms/\d+/media/video/upload$"), 256 * _MB),
    (re.compile(r"^/api/plugins/install$"), 256 * _MB),
    (re.compile(r"^/api/firmware/"), 128 * _MB),
    (re.compile(r"^/api/whdload/"), 128 * _MB),
    # 64 MB per state plus 4 MB per screenshot, plus multipart framing.
    (re.compile(r"^/api/savestates/"), 80 * _MB),
]

# Deliberately absent: the torrent upload. Its handler allows a 10 MB .torrent,
# and a ceiling here below that would refuse a file the route accepts. Where a
# handler already states a limit, this table stays above it and lets the
# handler be the authority.

_METHODS_WITH_BODIES = frozenset({"POST", "PUT", "PATCH"})


def limit_for(path: str) -> int | None:
    """The ceiling for *path*, or None when the route polices itself."""
    for pattern, ceiling in _RULES:
        if pattern.match(path):
            return ceiling
    return DEFAULT_MAX_BODY


def _declared_length(scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class RequestSizeLimitMiddleware:
    """Answer 413 for a body over the route's ceiling, before it is read.

    Written against the raw ASGI interface rather than `BaseHTTPMiddleware`
    because the point is to intervene in the receive channel itself, which the
    Starlette base class does not expose.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODIES:
            await self.app(scope, receive, send)
            return

        ceiling = limit_for(scope.get("path", ""))
        if ceiling is None:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > ceiling:
            await self._refuse(scope, send, ceiling, declared)
            return

        seen = 0
        refused = False

        async def counting_receive():
            nonlocal seen, refused
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > ceiling:
                    refused = True
                    # Telling the application the client hung up is the only
                    # way to stop it reading without inventing an exception it
                    # has no reason to expect. Whatever it answers is dropped
                    # below and replaced with the refusal.
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not refused:
                await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            # A handler part way through reading a body sees the disconnect and
            # may well raise. That is our doing, so it is not an error worth
            # propagating; anything raised for another reason still is.
            if not refused:
                raise

        if refused:
            await self._refuse(scope, send, ceiling, None)

    async def _refuse(self, scope, send, ceiling: int, declared: int | None) -> None:
        logger.warning(
            "Refused %s %s: body over the %d MB ceiling for this route (%s)",
            scope.get("method"), scope.get("path"), ceiling // _MB,
            f"declared {declared} bytes" if declared is not None else "measured while reading",
        )
        body = (
            b'{"detail":"Request body is too large. The limit for this endpoint is '
            + str(ceiling // _MB).encode()
            + b' MB."}'
        )
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
