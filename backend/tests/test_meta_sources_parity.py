"""The two metadata searches must answer identically before they become one.

`external_meta.search_meta_source` and `meta_sources.fetch_meta_source` were
extracted from two different editors at two different times and grew apart in
wording while staying the same in behaviour: one builds a list with a loop where
the other uses a comprehension, one names a variable `items` and the other
`search_results`. Reading them side by side is not proof. Feeding both the same
canned answers and comparing what they return is.

This runs first as evidence for merging them, and stays afterwards as the thing
that would notice if the survivor ever drifted from what four editors expect.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from handler.metadata import external_meta, meta_sources

RAWG_SEARCH = {"results": [
    {"id": 3498, "slug": "gta-v", "name": "GTA V", "released": "2013-09-17",
     "background_image": "https://img/gta.jpg", "rating": 4.47},
    {"id": 4200, "slug": "portal-2", "name": "Portal 2", "released": "2011-04-18",
     "background_image": "https://img/p2.jpg", "rating": 4.61},
]}
RAWG_DETAIL = {
    "id": 3498, "slug": "gta-v", "name": "GTA V", "released": "2013-09-17",
    "description_raw": "A big open world.", "background_image": "https://img/gta.jpg",
    "rating": 4.47, "metacritic": 92,
    "platforms": [{"platform": {"name": "PC"},
                   "requirements": {"minimum": "OS: Windows 7", "recommended": "OS: Windows 10"}}],
}
STEAM_SEARCH = {"items": [{"id": 271590, "name": "Grand Theft Auto V"}]}
STEAM_DETAIL = {"271590": {"success": True, "data": {
    "name": "Grand Theft Auto V", "detailed_description": "<p>Big</p>",
    "short_description": "Big open world", "header_image": "https://img/steam.jpg",
    "pc_requirements": {"minimum": "<strong>OS:</strong> Windows 7"},
    "release_date": {"date": "14 Apr, 2015"}, "metacritic": {"score": 96},
}}}


def _canned_answer(request: httpx.Request) -> httpx.Response:
    """One canned answer per host, so both functions see exactly the same world."""
    u = str(request.url)
    if "api.rawg.io/api/games?" in u or ("api.rawg.io/api/games" in u and "search=" in u):
        return httpx.Response(200, json=RAWG_SEARCH)
    if "api.rawg.io/api/games/" in u:
        return httpx.Response(200, json=RAWG_DETAIL)
    if "storesearch" in u:
        return httpx.Response(200, json=STEAM_SEARCH)
    if "appdetails" in u:
        return httpx.Response(200, json=STEAM_DETAIL)
    if "id.twitch.tv" in u:
        return httpx.Response(200, json={"access_token": "t", "expires_in": 9999})
    if "api.igdb.com" in u:
        return httpx.Response(200, text=json.dumps([{
            "id": 1, "name": "GTA V", "summary": "A big open world.",
            "first_release_date": 1379376000, "rating": 90,
        }]))
    return httpx.Response(404, json={})


@pytest.fixture(autouse=True)
def canned_world(monkeypatch):
    """No network, and a RAWG key both functions can find."""
    transport = httpx.MockTransport(_canned_answer)
    real_client = httpx.AsyncClient

    def make_client(*a, **kw):
        kw.pop("transport", None)
        return real_client(*a, **{**kw, "transport": transport})

    monkeypatch.setattr(httpx, "AsyncClient", make_client)

    class _Config:
        async def get(self, key, default=None):
            return {"rawg_api_key": "test-key", "igdb_client_id": "id",
                    "igdb_client_secret": "secret"}.get(key, default)

    import handler.config.config_handler as ch
    monkeypatch.setattr(ch, "config_handler", _Config())


@pytest.mark.parametrize("source", ["rawg", "rawg-detail", "steam", "igdb"])
def test_both_searches_answer_the_same(source):
    """Same source, same query, same canned world: the answers must match."""
    a = asyncio.run(external_meta.search_meta_source(source, "GTA V", "gta-v", game=None))
    b = asyncio.run(meta_sources.fetch_meta_source(source, search_term="GTA V", q="gta-v"))
    assert a == b, f"{source}: the two searches disagree"


def test_the_gog_branch_survives_being_entered():
    """GOG is missing from the parity list above, and that is where it broke.

    The parity test needs canned answers per source, and nobody wrote GOG's, so
    the branch was never entered by any test. It then spent a refactor importing
    two names that had moved out of `library_scrape_handler`, and because the
    import sits inside the function body, importing the module proved nothing:
    every metadata search on a GOG game answered 500 while the suite stayed
    green.

    This does not compare the two implementations. It only walks far enough into
    the branch to execute its imports, with the canned world answering 404 so no
    real request happens. A "no match" answer is a pass: it means the code got
    as far as asking.
    """
    out = asyncio.run(meta_sources.fetch_meta_source("gog", search_term="GTA V"))
    assert out["source"] == "gog"
    assert out["found"] is False          # 404 world, so nothing to find
    assert "error" in out                 # and it says so rather than crashing


def test_an_unknown_source_is_refused_the_same_way():
    a = asyncio.run(external_meta.search_meta_source("nonsense", "GTA V", "", game=None))
    b = asyncio.run(meta_sources.fetch_meta_source("nonsense", search_term="GTA V"))
    assert a == b


def test_the_shared_shape_is_what_the_editors_read():
    """Every answer says which source it came from and whether it found anything."""
    for out in (asyncio.run(external_meta.search_meta_source("rawg", "GTA V", "", game=None)),
                asyncio.run(meta_sources.fetch_meta_source("rawg", search_term="GTA V"))):
        assert out["source"] == "rawg"
        assert out["found"] is True
        assert [c["slug"] for c in out["candidates"]] == ["gta-v", "portal-2"]


def test_the_merged_answer_keeps_both_editors_fields():
    """One payload now feeds four editors, so it carries the union of what they read.

    The collection editor shows IGDB's storyline on its own; the library and
    catalogue editors write the OS flags and the language table onto the record.
    Dropping either set would leave one editor quietly missing a field rather
    than failing, which is why it is asserted here and not left to a reviewer.
    """
    out = asyncio.run(meta_sources.fetch_meta_source("igdb", search_term="GTA V"))
    candidate = out["candidates"][0]
    for field in ("storyline", "os_windows", "os_mac", "os_linux", "languages"):
        assert field in candidate, f"IGDB result lost {field}"
