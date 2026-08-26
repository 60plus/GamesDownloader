"""Unit tests for RequestSizeLimitMiddleware (middleware.request_size).

The middleware exists because every write in this API accepted a body of any
size: FastAPI spools the upload first and the handler only decides afterwards,
so the disk and the memory are spent before the refusal. These tests hold both
halves of the fix.

The honest oversized request is checked by asserting the handler never ran at
all, which is the whole claim - refusing after the body has been read would
also produce a 413 and would be worthless.

The dishonest ones go in through the raw ASGI interface rather than the test
client, on purpose. An HTTP client computes `Content-Length` for you, so there
is no way to ask one to under-declare a body; hand-building the receive channel
is the only way to prove the running total catches a request that lies, and the
same route covers the chunked body that declares no length at all.
"""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from middleware.request_size import (
    DEFAULT_MAX_BODY,
    RequestSizeLimitMiddleware,
    limit_for,
)

_MB = 1024 * 1024


# ── Which ceiling applies where ───────────────────────────────────────────────


def test_unlisted_route_gets_the_default():
    assert limit_for("/api/collections/retro/cover") == DEFAULT_MAX_BODY
    assert limit_for("/api/users/me/avatar") == DEFAULT_MAX_BODY


def test_streaming_uploads_are_left_alone():
    # These carry tens of gigabytes legitimately and police themselves as they
    # write. A number here would be a worse lie than no number.
    assert limit_for("/api/library/games/42/upload") is None
    assert limit_for("/api/roms/platforms/snes/upload") is None
    assert limit_for("/api/settings/metadata-backup/restore") is None


def test_specific_route_wins_over_the_prefix_below_it():
    # /api/savestates/ would swallow /api/savestates/import if the order of the
    # rules were reversed, and a bulk import of many saves needs the larger of
    # the two. This is the assertion that keeps the table in order.
    assert limit_for("/api/savestates/import") == 512 * _MB
    assert limit_for("/api/savestates/7/states") == 80 * _MB


def test_rom_media_video_has_its_own_ceiling():
    # This route had no ceiling of any kind before the middleware: it streams
    # into the resources directory a megabyte at a time and never totals up.
    assert limit_for("/api/roms/12/media/video/upload") == 256 * _MB
    # A cover on the same route shape is an image, so the default is right.
    assert limit_for("/api/roms/12/media/cover/upload") == DEFAULT_MAX_BODY


# ── Behaviour through a real request ──────────────────────────────────────────


@pytest.fixture
def app_and_log():
    """A throwaway app that records the bodies its handlers actually saw."""
    seen: list[int] = []

    async def echo(request):
        body = await request.body()
        seen.append(len(body))
        return JSONResponse({"got": len(body)})

    routes = [
        Route("/api/echo", echo, methods=["POST", "GET"]),
        Route("/api/library/games/1/upload", echo, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(RequestSizeLimitMiddleware)
    return app, seen


def test_body_under_the_ceiling_arrives_whole(app_and_log):
    app, seen = app_and_log
    payload = b"x" * 1024
    with TestClient(app) as client:
        r = client.post("/api/echo", content=payload)
    assert r.status_code == 200
    assert r.json() == {"got": 1024}
    assert seen == [1024]


def test_oversized_body_is_refused_before_the_handler_runs(app_and_log):
    app, seen = app_and_log
    payload = b"x" * (DEFAULT_MAX_BODY + 1)
    with TestClient(app) as client:
        r = client.post("/api/echo", content=payload)
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()
    # The point of the whole exercise: nothing read it.
    assert seen == []


def test_a_method_without_a_body_is_untouched(app_and_log):
    app, seen = app_and_log
    with TestClient(app) as client:
        r = client.get("/api/echo")
    assert r.status_code == 200


def test_streaming_route_still_accepts_an_enormous_body(app_and_log):
    app, seen = app_and_log
    payload = b"x" * (DEFAULT_MAX_BODY + 4096)
    with TestClient(app) as client:
        r = client.post("/api/library/games/1/upload", content=payload)
    assert r.status_code == 200
    assert seen == [len(payload)]


# ── The dishonest cases, driven straight through ASGI ─────────────────────────


async def _drive(app, *, chunks: list[bytes], declared: int | None, path="/api/echo"):
    """Push `chunks` at `app` as one POST and return (status, handler_saw)."""
    headers = [(b"host", b"test")]
    if declared is not None:
        headers.append((b"content-length", str(declared).encode()))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }

    pending = list(chunks)

    async def receive():
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, sent


def _wrapped_echo():
    saw: list[int] = []

    async def raw_app(scope, receive, send):
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                # What a real handler reading a body sees once we cut it off.
                raise RuntimeError("client disconnected")
            total += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        saw.append(total)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    return RequestSizeLimitMiddleware(raw_app), saw


@pytest.mark.asyncio
async def test_a_body_that_under_declares_its_length_is_still_refused():
    app, saw = _wrapped_echo()
    # Declares one kilobyte, sends far more. The header check waves this
    # through, so only the running total can catch it.
    chunks = [b"x" * _MB] * (DEFAULT_MAX_BODY // _MB + 1)
    status, _ = await _drive(app, chunks=chunks, declared=1024)
    assert status == 413
    assert saw == []


@pytest.mark.asyncio
async def test_a_chunked_body_with_no_declared_length_is_refused():
    app, saw = _wrapped_echo()
    chunks = [b"x" * _MB] * (DEFAULT_MAX_BODY // _MB + 1)
    status, _ = await _drive(app, chunks=chunks, declared=None)
    assert status == 413
    assert saw == []


@pytest.mark.asyncio
async def test_a_chunked_body_under_the_ceiling_gets_through():
    app, saw = _wrapped_echo()
    status, _ = await _drive(app, chunks=[b"x" * 4096, b"y" * 4096], declared=None)
    assert status == 200
    assert saw == [8192]


@pytest.mark.asyncio
async def test_the_refusal_is_the_only_response_sent():
    """A handler cut off mid-read must not also get to answer.

    Without the send guard the client would receive the handler's reply (or a
    500 from the exception the disconnect causes) followed by our 413, which is
    two responses on one request.
    """
    app, _ = _wrapped_echo()
    chunks = [b"x" * _MB] * (DEFAULT_MAX_BODY // _MB + 1)
    _, sent = await _drive(app, chunks=chunks, declared=None)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 413


# ── The middleware is actually mounted ────────────────────────────────────────


def test_the_real_app_has_the_ceiling_installed():
    """A ceiling that is written but never added to the stack protects nothing."""
    import main

    # `main.app` is rebound at the end of the module to the Socket.IO wrapper,
    # so the FastAPI instance carrying the middleware stack sits underneath it.
    fastapi_app = getattr(main.app, "other_asgi_app", main.app)
    names = [m.cls.__name__ for m in fastapi_app.user_middleware]
    assert "RequestSizeLimitMiddleware" in names
    # Added last means outermost, so it decides before authentication does.
    assert names[0] == "RequestSizeLimitMiddleware"
