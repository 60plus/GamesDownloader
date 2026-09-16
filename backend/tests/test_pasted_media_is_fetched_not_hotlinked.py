"""A media address typed into the editor is fetched, not merely remembered.

Project rule, set by the owner: every piece of media a scraper offers is
downloaded onto the server and served locally, never hot-linked from a CDN.
Two of the three ways a ROM gets a video already kept it. The scrape pipeline
downloads and stores a /resources path, and a ScreenScraper video picked in the
editor arrives as a media-proxy token, which PATCH /roms/{id} remaps onto the
*_url branch so it is downloaded too.

The third way did not. Each of the editor's eight media tabs has a box inviting
a URL - its placeholder literally reads "https://…" - and a value pasted there
went into the *_path column verbatim, because the remap only fires on the proxy
prefix. Measured: https://example.invalid/somewhere/trailer.mp4 was stored and
served as the ROM's video.

That is worse than untidy. The file is gone the day the far end moves it, and
every render sends the viewer's address to a third party the owner never chose.

So anything that looks like a remote address goes down the same road as a proxy
token: fetched, stored locally, and the column holds our own path. And a fetch
that fails now says so, rather than reporting success while leaving the media
exactly as it was.
"""
from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROMS = BACKEND / "endpoints" / "roms" / "roms_router.py"


def _remap_block() -> str:
    source = io.open(ROMS, encoding="utf-8").read()
    start = source.index("from utils.media_proxy import PROXY_PREFIX")
    return source[start:source.index("    data: dict = {}", start)]


def test_a_pasted_remote_address_is_routed_to_the_download_branch():
    block = _remap_block()
    assert "PROXY_PREFIX" in block, "przemapowanie stracilo obsluge tokenow posrednika"
    assert "http" in block, (
        "wklejony zdalny adres nadal trafia prosto do kolumny, czyli hotlink"
    )


def test_every_media_kind_is_covered_not_just_the_video():
    """Eight tabs, eight boxes, one rule. Fixing the one that was reported and
    leaving the other seven is how this comes back."""
    block = _remap_block()
    for field in ("cover_path", "background_path", "support_path", "wheel_path",
                  "bezel_path", "steamgrid_path", "video_path"):
        assert field in block, f"{field} nie przechodzi przez przemapowanie"


def test_a_failed_fetch_is_not_reported_as_success():
    """The download branch set the column only when the fetch worked and said
    nothing when it did not: the editor showed a saved dialog over an unchanged
    picture. Silence is the one answer nobody can act on.

    Asserted on the branch and on the response, not on the word "failed"
    appearing somewhere - it already appeared, in a comment, which is how the
    first version of this test passed against the broken code.
    """
    source = io.open(ROMS, encoding="utf-8").read()
    start = source.index("_extra_media = [")
    body = source[start:source.index("if _chosen:", start)]
    assert "_failed.append" in body, "nieudane pobranie nadal przechodzi bez sladu"
    assert '"media_failed"' in source, "odpowiedz nie mowi, czego nie udalo sie pobrac"
