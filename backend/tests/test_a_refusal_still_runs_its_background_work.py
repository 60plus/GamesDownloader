"""A refusal has to leave the server the way a success does.

The ROM upload route registers whatever already reached the disk before it
refuses the rest: ten files in one request and a 413 on the ninth used to leave
eight files with no row, so no owner, so nothing counted against the quota that
had just refused them - repeatable for ever.

The fix scheduled a background task in the `except HTTPException` branch and
re-raised. That does nothing at all. FastAPI attaches the BackgroundTasks object
to the response it builds FROM THE RETURN VALUE (fastapi/routing.py, after
`run_endpoint_function`); when the endpoint raises, Starlette's exception
handling builds a fresh JSONResponse with `background=None` and the tasks are
dropped on the floor.

The old test passed anyway, because it called `await tasks()` itself - which is
the one thing the server does not do on this path. So it verified the content of
the task and never the thing that was broken.

This one drives the whole ASGI stack with the real framework instead: a route of
the same shape as the real one, the app's own middleware shape around it, and a
TestClient request. It fails on `raise` and passes on `return`, which is the
only difference that matters.
"""

from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.testclient import TestClient


def _app(handler):
    """The real framework, with this project's middleware shape around it."""
    app = FastAPI()

    class _Passthrough(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await call_next(request)

    app.add_middleware(_Passthrough)

    # main.py registers exactly one custom handler, for 404. Nothing catches the
    # 413 an upload raises, so it takes Starlette's default path.
    @app.exception_handler(404)
    async def _spa(_request, _exc):
        return JSONResponse({"detail": "not found"}, status_code=404)

    app.post("/upload")(handler)
    return app


def _ran():
    landed: list[str] = []

    def _register(name: str) -> None:
        landed.append(name)

    return landed, _register


def test_the_framework_runs_background_work_after_a_normal_return():
    """The control. Without this, a failure below could mean the harness is
    wrong rather than the route."""
    landed, register = _ran()

    async def handler(request: Request, background_tasks: BackgroundTasks):
        background_tasks.add_task(register, "a.iso")
        return {"saved": ["a.iso"]}

    with TestClient(_app(handler)) as client:
        assert client.post("/upload").status_code == 200
    assert landed == ["a.iso"]


def test_the_framework_drops_background_work_when_the_handler_raises():
    """The measurement this whole file exists for. Not a wish about how FastAPI
    ought to behave - the behaviour itself, from the installed version."""
    landed, register = _ran()

    async def handler(request: Request, background_tasks: BackgroundTasks):
        background_tasks.add_task(register, "a.iso")
        raise HTTPException(status_code=413, detail="no room")

    with TestClient(_app(handler)) as client:
        assert client.post("/upload").status_code == 413
    assert landed == [], (
        "framework jednak uruchamia zadania tla po wyjatku - jesli to sie "
        "zmienilo, naprawa ponizej jest niepotrzebna, ale NIE szkodliwa"
    )


def test_returning_the_refusal_keeps_the_background_work():
    """The shape the route has to use: build the refusal, do not throw it."""
    landed, register = _ran()

    async def handler(request: Request, background_tasks: BackgroundTasks):
        background_tasks.add_task(register, "a.iso")
        return JSONResponse({"detail": "no room"}, status_code=413)

    with TestClient(_app(handler)) as client:
        assert client.post("/upload").status_code == 413
    assert landed == ["a.iso"]


# ── And the route itself ─────────────────────────────────────────────────────

def test_the_upload_route_returns_its_refusal_rather_than_raising():
    """Asked of the source, because standing the real route up needs the whole
    application. The two tests above settle what the difference means; this one
    settles that the route is on the right side of it.
    """
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()

    at = source.index("async def upload_roms(")
    body = source[at:source.index("\n@", at)]
    branch = body[body.index("except HTTPException"):]
    branch = branch[:branch.index("except Exception")]

    assert "_schedule_registration(" in branch, "galaz ratunkowa zniknela"
    # A `raise` STATEMENT, not the letters. The branch explains itself in a
    # comment that uses the word, and matching that would fail over prose.
    throws = [ln for ln in branch.splitlines()
              if ln.strip() == "raise" or ln.strip().startswith("raise ")]
    assert not throws, (
        "galaz ratunkowa nadal rzuca, wiec FastAPI wyrzuca zaplanowane zadanie "
        "i pliki, ktore juz wyladowaly, zostaja bez wiersza i bez wlasciciela: "
        + "; ".join(t.strip() for t in throws)
    )
    assert "JSONResponse" in branch or "Response(" in branch, (
        "odmowa musi byc ZWROCONA jako odpowiedz, zeby framework dopial tlo"
    )
