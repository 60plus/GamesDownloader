"""A route excused from the body ceiling has to enforce one of its own.

middleware/request_size.py caps every request body, and names a few routes with
no ceiling at all. Its own header says why: "A ROM, a game build and a metadata
restore all stream to disk and enforce their own limit as they go, and inventing
a number for them here would be a worse lie than no number."

That is a promise the middleware makes on those routes' behalf, and one of them
was not keeping it. The ROM upload writes `while chunk := await upload.read(...)`
with nothing counting, no per-file cap, and no quota read in either direction, so
between the exemption and the empty loop there was no limit anywhere on the path.
A single account could fill the disk, and the account did not even have to be the
one being billed, because nothing was billing anybody.

The tests below are structural on purpose. The hole was not a wrong number, it
was an absent one, and the thing worth pinning is that every name on that list
has a counter behind it.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MIDDLEWARE = BACKEND / "middleware" / "request_size.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


# Each route the middleware excuses, and the handler that then has to do the
# counting itself. Adding a `None` rule without adding a line here fails the
# first test, which is the point: the list is the promise.
POLICED_BY_THEIR_OWN_HANDLER = {
    r"^/api/library/games/\d+/upload$":
        BACKEND / "endpoints" / "library" / "upload_router.py",
    r"^/api/roms/platforms/[^/]+/upload$":
        BACKEND / "endpoints" / "roms" / "roms_router.py",
    r"^/api/settings/metadata-backup/restore$":
        BACKEND / "endpoints" / "settings" / "metadata_backup_router.py",
}


def exempt_routes() -> list[str]:
    """The patterns the middleware lets through with no ceiling."""
    source = _source(MIDDLEWARE)
    return re.findall(r're\.compile\(r"([^"]+)"\),\s*None\)', source)


def test_the_scan_found_the_rules():
    """A guard on the guard: a rewrite that made the pattern match nothing would
    leave every assertion below vacuously true."""
    assert len(exempt_routes()) >= 3, f"znalazlem tylko {exempt_routes()}"


@pytest.mark.parametrize("pattern", sorted(exempt_routes()))
def test_every_excused_route_is_named_here(pattern):
    assert pattern in POLICED_BY_THEIR_OWN_HANDLER, (
        f"{pattern} jest zwolniona z limitu ciala, a nikt nie zapisal, "
        "co ma go pilnowac zamiast tego"
    )


def test_the_rom_upload_asks_the_quota_for_its_ceiling():
    """The route the promise was false about. Same shape as the library upload
    next door, which has always done this."""
    source = _source(BACKEND / "endpoints" / "roms" / "roms_router.py")
    start = source.index('"/platforms/{slug}/upload"')
    body = source[start:source.index("\n@protected_route", start + 10)]
    assert "ceiling_for" in body, "wgranie ROM-u nie pyta o pulap"


def test_the_rom_upload_counts_what_it_writes():
    """A ceiling nobody counts against is not a ceiling. The loop has to stop,
    not just know a number."""
    source = _source(BACKEND / "endpoints" / "roms" / "roms_router.py")
    start = source.index('"/platforms/{slug}/upload"')
    body = source[start:source.index("\n@protected_route", start + 10)]
    assert "written" in body or "total" in body, "petla nie sumuje zapisanych bajtow"
    assert "413" in body or "REQUEST_ENTITY_TOO_LARGE" in body, (
        "petla nie ma jak odmowic po przekroczeniu"
    )


def test_a_refused_upload_does_not_leave_the_half_written_file():
    """Stopping mid-write leaves bytes on the disk the limit just refused. The
    partial file has to go, or the refusal costs the same space as the upload."""
    source = _source(BACKEND / "endpoints" / "roms" / "roms_router.py")
    start = source.index('"/platforms/{slug}/upload"')
    body = source[start:source.index("\n@protected_route", start + 10)]
    assert "unlink" in body, "odmowa zostawia niedopisany plik na dysku"
