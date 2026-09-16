"""A retro game can be given a trailer the same way an ordinary game can.

Reported: "brak mozliwosci pobrania video w grach retro tak jak w normalnych
grach". Precise, and worth restating because a ROM was not short of video
altogether: its metadata editor already offers ScreenScraper's own videos, a
file upload and a pasted URL, and the ROM scraper downloads a video when
ScreenScraper has one (rom_scrape_handler.py:650).

What it could not do is the one thing a library game can: pick a trailer from a
provider and have the server FETCH it. A game searches IGDB by title, gets
YouTube ids back, and yt-dlp pulls the chosen one onto the server so it is
served locally rather than hot-linked - the project's rule for every other kind
of media. A ROM had none of that, because all four video routes were written on
the library router and none was ever mirrored.

The download itself was never game-specific except in one line: it wrote to the
library's media directory. So the fetching is shared and only the destination
differs, which is what the first test here pins.
"""
from __future__ import annotations

import io
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MEDIA = BACKEND / "handler" / "library" / "media_handler.py"
ROMS = BACKEND / "endpoints" / "roms" / "roms_router.py"
LIBRARY = BACKEND / "endpoints" / "library" / "library_router.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


def _scopes(source: str, verb: str, path: str) -> set[str]:
    match = re.search(
        r'@protected_route\([a-z_]+\.' + verb + r',\s*"' + re.escape(path)
        + r'",\s*scopes=\[([^\]]*)\]', source)
    assert match, f"nie znalazlem trasy {verb.upper()} {path}"
    return {s.strip().split(".")[-1] for s in match.group(1).split(",") if s.strip()}


# ── The fetching is shared; only the destination differs ─────────────────────

def test_the_downloader_can_be_pointed_at_a_directory():
    """It used to take a game id and derive the library path from it, which is
    the only reason it could not serve a ROM."""
    from handler.library.media_handler import download_youtube_to

    assert callable(download_youtube_to)


def test_the_game_route_still_goes_through_the_same_code():
    """Two copies of a yt-dlp invocation is two sets of options to drift apart,
    and the one that drifts is always the one nobody is looking at."""
    source = _source(MEDIA)
    assert source.count("YoutubeDL(") == 1, "jest wiecej niz jedno wywolanie yt-dlp"


def test_a_rom_trailer_lands_in_the_rom_media_directory():
    """Under resources/roms/{platform}/{id}/, where every other piece of a ROM's
    media already lives, so one delete of that folder takes the lot."""
    source = _source(ROMS)
    start = source.index('"/{rom_id}/video/download"')
    body = source[start:source.index("\n@", start)]
    assert "_rom_media_dir" in body or "rom_media_dir" in body, (
        "pobrany zwiastun nie trafia do katalogu mediow ROM-u"
    )


# ── The three routes a ROM was missing ───────────────────────────────────────

def test_a_rom_offers_trailer_candidates():
    """Searched live by title, exactly as a game's are: a ROM has no column of
    stored candidates and does not need one."""
    declared = _scopes(_source(ROMS), "get", "/{rom_id}/videos")
    assert declared == {"LIBRARY_WRITE", "ROMS_READ"}


def test_a_rom_trailer_can_be_fetched():
    declared = _scopes(_source(ROMS), "post", "/{rom_id}/video/download")
    assert declared == {"LIBRARY_WRITE", "ROMS_READ"}


def test_the_editor_can_ask_how_the_fetch_is_going():
    """yt-dlp runs in the background, so without this the editor shows a spinner
    that never resolves - which is the failure the game side already had once."""
    declared = _scopes(_source(ROMS), "get", "/{rom_id}/video/status")
    assert declared == {"LIBRARY_WRITE", "ROMS_READ"}


def test_the_scopes_match_the_rest_of_the_rom_metadata_routes():
    """Editing a ROM's metadata is LIBRARY_WRITE plus an emulation permission,
    and a trailer is metadata. ROMS_READ is not decoration: an account with
    emulation switched off has it revoked, and a guard test refuses any ROM
    route that names none."""
    source = _source(ROMS)
    assert _scopes(source, "patch", "/{rom_id}") == {"LIBRARY_WRITE", "ROMS_READ"}


# ── The padlock reaches this too ─────────────────────────────────────────────

def test_a_locked_rom_refuses_a_trailer():
    """An admin closing a ROM's metadata closes all of it. The game route asks
    the same question (library_router.py, download_game_video), and a media
    route that skipped it would be the way around the padlock."""
    source = _source(ROMS)
    start = source.index('"/{rom_id}/video/download"')
    body = source[start:source.index("\n@", start)]
    assert "assert_unlocked" in body, "pobieranie zwiastuna omija klodke"


# ── And the editor has somewhere to put it ───────────────────────────────────

def test_the_rom_editor_offers_the_same_choice():
    """The ROM editor already had a video tab with ScreenScraper's videos, an
    upload and a URL box. What it lacked was the provider trailers, which is
    what the report was about."""
    panel = BACKEND.parent / "frontend" / "src" / "views" / "emulation" / "EmulationRomMetadataPanel.vue"
    source = _source(panel)
    assert "/video/download" in source, "okno ROM-u nie potrafi zlecic pobrania"
    assert "/videos" in source, "okno ROM-u nie pyta o kandydatow"


# ── A refusal has to say which refusal it is ─────────────────────────────────
#
# Found by the sweep that went with this work, in the upload path beside it.
# save_uploaded_video returned None when the size cap was hit AND when the write
# itself failed, and the route turned any None into 413 "Video too large (max
# 1 GB)". So a full disk, a permissions problem or a broken stream all told the
# person their video was too big, and the one thing they could try - a smaller
# file - was the one thing that could not help.
#
# This is the same defect the trailer downloader in the same module already had
# and already fixed: its docstring records that returning None either way made a
# refused download indistinguishable from one still running.

def test_a_failed_upload_is_not_reported_as_an_oversized_one():
    source = _source(MEDIA)
    start = source.index("async def save_uploaded_video")
    body = source[start:source.index("\nasync def ", start + 10)]
    assert "too_large" in body, "przekroczenie rozmiaru nie ma wlasnego kodu"
    assert "write_failed" in body or "failed" in body, "blad zapisu nie ma wlasnego kodu"


def test_the_route_tells_the_two_apart():
    """413 says "send a smaller one", which is only true for one of them."""
    source = _source(LIBRARY)
    start = source.index('"/games/{game_id}/video/upload"')
    body = source[start:source.index("\n@", start)]
    assert "too_large" in body, "trasa nie rozroznia powodow odmowy"
    assert "413" in body and ("500" in body or "507" in body), (
        "obie odmowy nadal maja ten sam kod"
    )
