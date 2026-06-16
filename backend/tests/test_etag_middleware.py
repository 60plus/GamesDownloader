"""Unit tests for ETagMiddleware (middleware.etag).

Mounts the middleware on a throwaway Starlette app so the conditional-GET
logic is exercised without the database or the full FastAPI stack.

Regression guard (session 39): a response larger than the 1 MiB cap must be
passed through UNCHANGED - never buffered-and-truncated against a stale
Content-Length, which previously corrupted large library downloads.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from middleware.etag import ETagMiddleware, _MAX_ETAG_BODY


def _build_app() -> Starlette:
    async def small(request):
        return JSONResponse({"hello": "world"})

    async def big(request):
        # > 1 MiB JSON; JSONResponse sets an accurate Content-Length so the
        # middleware should bail out at the header check and stream it whole.
        return JSONResponse({"blob": "x" * (_MAX_ETAG_BODY + 1024)})

    async def attachment(request):
        return PlainTextResponse(
            "file-bytes",
            headers={"content-disposition": "attachment; filename=game.zip"},
        )

    async def notfound(request):
        return JSONResponse({"detail": "nope"}, status_code=404)

    routes = [
        Route("/api/small", small),
        Route("/api/big", big),
        Route("/api/attachment", attachment),
        Route("/api/notfound", notfound),
        Route("/health", small),  # non-/api path -> middleware skips entirely
    ]
    app = Starlette(routes=routes)
    app.add_middleware(ETagMiddleware)
    return app


client = TestClient(_build_app())


def test_small_get_gets_weak_etag():
    r = client.get("/api/small")
    assert r.status_code == 200
    assert r.headers.get("etag", "").startswith('W/"')


def test_matching_if_none_match_returns_304_empty():
    etag = client.get("/api/small").headers["etag"]
    r = client.get("/api/small", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b""


def test_non_matching_if_none_match_returns_200():
    r = client.get("/api/small", headers={"If-None-Match": 'W/"deadbeef"'})
    assert r.status_code == 200
    assert "etag" in r.headers


def test_large_body_passes_through_untruncated_without_etag():
    r = client.get("/api/big")
    assert r.status_code == 200
    assert "etag" not in r.headers
    # The whole payload must survive intact - no 1 MiB truncation.
    assert len(r.content) > _MAX_ETAG_BODY


def test_attachment_is_not_etagged():
    r = client.get("/api/attachment")
    assert r.status_code == 200
    assert "etag" not in r.headers


def test_non_200_is_not_etagged():
    r = client.get("/api/notfound")
    assert r.status_code == 404
    assert "etag" not in r.headers


def test_non_api_path_is_skipped():
    r = client.get("/health")
    assert "etag" not in r.headers
