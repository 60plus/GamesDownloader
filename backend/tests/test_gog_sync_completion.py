"""A GOG sync that stops partway must not report success.

The page loop broke out on any error and then fell through to a hardcoded
`return {"ok": True, "synced": synced}`. The caller took that at face value: it
set the status to finished and sent "Library Synced - 100 games" by webhook and
by email, over a library of four hundred whose sync had died on page two. The
next run then saw the games it had never fetched as absent.

Now the loop retries a page before giving up, and completion is derived from
having actually reached the end.
"""
from __future__ import annotations

import httpx
import pytest

import handler.gog.gog_sync_handler as sync_module
from handler.gog.gog_sync_handler import GogSyncHandler

PAGE_SIZE = 3


class FakeGogAPI:
    """Serves `pages` pages of products, failing the ones it was told to."""

    def __init__(self, pages: int, fails: dict[int, int] | None = None):
        self.pages = pages
        self.fails = dict(fails or {})
        self.requested: list[int] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url: str):
        page = int(url.rsplit("page=", 1)[1])
        self.requested.append(page)
        if self.fails.get(page, 0) > 0:
            self.fails[page] -= 1
            raise httpx.ConnectError("connection reset")
        return FakeResponse({
            "totalPages": self.pages,
            "products": [
                {"id": page * 100 + i, "title": f"Game {page}.{i}"}
                for i in range(PAGE_SIZE)
            ],
        })


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def gog(monkeypatch):
    """A handler whose network, clock and database are all stubbed out."""
    api_holder: dict = {}

    def make_client(*_args, **_kwargs):
        return api_holder["api"]

    async def no_sleep(_seconds):
        return None

    async def token(*_args, **_kwargs):
        return "an-access-token"

    async def no_upsert(_self, _product, owner_user_id=None, *, session=None):
        return None

    monkeypatch.setattr(sync_module.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(sync_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(sync_module.gog_auth_handler, "get_access_token", token)
    monkeypatch.setattr(GogSyncHandler, "_upsert_game", no_upsert)

    def run(pages: int, fails: dict[int, int] | None = None):
        api_holder["api"] = FakeGogAPI(pages, fails)
        # A non-None session makes begin_session hand it straight through
        # instead of opening a real one.
        return GogSyncHandler().sync_library(session=object()), api_holder["api"]

    return run


async def test_a_complete_run_reports_completion(gog):
    coro, api = gog(pages=3)
    result = await coro
    assert result["ok"] is True
    assert result["synced"] == 3 * PAGE_SIZE
    assert result["pages_done"] == 3
    assert result["pages_total"] == 3
    assert result["error"] is None
    assert api.requested == [1, 2, 3]


async def test_a_run_that_dies_partway_reports_failure(gog):
    """The bug: this used to come back ok:True with a third of the library."""
    coro, api = gog(pages=3, fails={2: 99})
    result = await coro
    assert result["ok"] is False
    assert result["synced"] == PAGE_SIZE, "only page one got through"
    assert result["pages_done"] == 1
    assert result["pages_total"] == 3
    assert result["error"]


async def test_it_does_not_stop_on_the_first_blip(gog):
    """One dropped connection used to end the whole run."""
    coro, api = gog(pages=3, fails={2: 2})
    result = await coro
    assert result["ok"] is True
    assert result["synced"] == 3 * PAGE_SIZE
    assert api.requested.count(2) == 3, "page two was retried, not abandoned"


async def test_it_gives_up_rather_than_retrying_forever(gog):
    coro, api = gog(pages=2, fails={1: 99})
    result = await coro
    assert result["ok"] is False
    assert result["synced"] == 0
    assert api.requested == [1, 1, 1]


async def test_a_missing_account_is_not_a_partial_sync(gog, monkeypatch):
    async def no_token(*_args, **_kwargs):
        return None

    monkeypatch.setattr(sync_module.gog_auth_handler, "get_access_token", no_token)
    coro, _api = gog(pages=3)
    result = await coro
    assert result["ok"] is False
    assert result["synced"] == 0


async def test_the_error_text_carries_no_url(gog):
    """Anything that reaches the status pane goes through loggable_error, which
    reports the exception type and never the request URL."""
    coro, _api = gog(pages=2, fails={1: 99})
    result = await coro
    assert "http" not in (result["error"] or "").lower()
