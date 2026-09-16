"""Two things the ROM upload route never asked before it opened a file.

WHERE. The shelf comes straight from the URL: `dest_dir = Path(roms_base) / slug`
with nothing between. A slug is a path segment, so a caller who sends one with
`..` in it writes outside the ROM tree entirely, and one that is simply unknown
makes a directory nobody asked for and drops files into it, where no platform
row will ever pick them up.

WHETHER IT IS ALREADY THERE. `open(dest_path, "wb")` truncates. Every other way
into this library asks first - the library upload has `_refuse_existing`, the
downloader skips unless `force` - and this one wrote over whatever it found.
Knowing nothing but a file name was enough to destroy somebody else's ROM,
while the row kept THEIR name on it, so the bytes went on their quota and not
on the uploader's.

Replacing your own file is left working, because that is the ordinary reason to
upload the same name twice: a bad dump swapped for a good one. The rule is the
one the rest of the ROM API uses - an administrator, or the account that brought
it in - so this and the delete button answer the same question.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

OWNER = 7
SOMEBODY_ELSE = 9

UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
ADMIN = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ, Scope.ROMS_WRITE}


def _request(scopes, user_id):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


# ── Where the files land ─────────────────────────────────────────────────────

@pytest.mark.parametrize("slug", [
    "../etc", "..", "a/../..", "psx/../../..", "/etc", "a/b", ".", "",
])
def test_a_slug_that_is_not_one_shelf_is_refused(slug):
    from endpoints.roms import roms_router as R

    assert not R._is_shelf_slug(slug), f"sluga {slug!r} wychodzi poza polke"


@pytest.mark.parametrize("slug", ["psx", "snes", "pc-engine", "3do", "n64"])
def test_an_ordinary_shelf_slug_is_allowed(slug):
    from endpoints.roms import roms_router as R

    assert R._is_shelf_slug(slug)


def test_the_route_checks_the_slug_before_it_makes_the_directory():
    """Order matters: `mkdir(parents=True)` on a bad slug has already made the
    directory by the time anything else looks."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index("async def upload_roms(")
    body = source[at:source.index("\n@", at)]

    assert "_is_shelf_slug(" in body, "trasa nie sprawdza slugi wcale"
    assert body.index("_is_shelf_slug(") < body.index("mkdir("), (
        "sluga jest sprawdzana PO utworzeniu katalogu, wiec katalog i tak "
        "powstaje w miejscu, ktorego nikt nie chcial"
    )


def test_an_unknown_shelf_is_refused_even_when_the_slug_looks_fine():
    """`psx-typo` is a perfectly good path segment and a platform nobody has.

    ASKED OF THE MAP OF KNOWN PLATFORMS, not of the database. The first version
    of this check called `rom_platform_handler.get_by_slug`, which is a SELECT
    against `rom_platforms` - and those rows are written in exactly one place,
    the scanner's upsert, which skips a platform whose folder is empty and has
    no rows. Meanwhile `_init_rom_dirs()` creates a folder for every known
    platform on first boot. A fresh install therefore has a hundred folders and
    zero rows, and the check refused an upload to EVERY one of them: the only
    way a person puts their first ROM on a shelf, closed by a fix meant to stop
    a slug reaching out of the ROM tree.

    The map is the same source `/roms/platforms/known` hands the screen, so what
    the interface offers and what the route accepts are one list.
    """
    from handler.metadata.rom_platform_map import PLATFORM_MAP

    assert "psx-typo" not in PLATFORM_MAP
    assert "snes" in PLATFORM_MAP, "test nie odtwarza mapy znanych platform"


def test_a_known_platform_with_no_rows_yet_is_still_accepted():
    """The case the database check broke, and it is not academic: every platform
    looks like this until its first ROM lands."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index("async def upload_roms(")
    body = source[at:source.index("\n@", at)]
    gate = body[:body.index("mkdir(")]

    assert "PLATFORM_MAP" in gate, (
        "trasa pyta bazy, czy platforma istnieje - a wiersz powstaje dopiero "
        "przy pierwszym skanie, wiec na swiezej instalacji odmawia KAZDEJ"
    )
    assert "get_by_slug(" not in gate, (
        "obecnosc wiersza w bazie nadal decyduje o przyjeciu pliku"
    )


# ── Whether the file is already there ────────────────────────────────────────

def _existing(owner):
    return SimpleNamespace(id=1, published_by=owner)


def test_an_uploader_may_replace_their_own_file():
    from endpoints.roms import roms_router as R

    assert R._may_replace(_request(UPLOADER, OWNER), _existing(OWNER))


def test_an_uploader_may_not_replace_somebody_elses():
    from endpoints.roms import roms_router as R

    assert not R._may_replace(_request(UPLOADER, OWNER), _existing(SOMEBODY_ELSE))


def test_an_uploader_may_not_replace_a_file_nobody_owns():
    """A ROM scanned in years ago has no owner and carries other people's saves.
    Reading "nobody" as "mine" would open every one of them."""
    from endpoints.roms import roms_router as R

    assert not R._may_replace(_request(UPLOADER, OWNER), _existing(None))


def test_an_administrator_may_replace_any_file():
    from endpoints.roms import roms_router as R

    assert R._may_replace(_request(ADMIN, 1), _existing(SOMEBODY_ELSE))


def test_a_file_on_disk_with_no_row_is_not_free_to_overwrite():
    """This test used to be called "a name that is not there yet is nobody's"
    and asserted the opposite, for a case this route cannot reach: the only
    call sits inside `if dest_path.exists()`, so the file IS there and a missing
    row says the library has not catalogued it. Subchannel files are in that
    state permanently - .sbi is not a ROM extension, so no scan will ever give
    one a row - which made every one of them writable by name alone.
    """
    from endpoints.roms import roms_router as R

    assert not R._may_replace(_request(UPLOADER, OWNER), None)


def test_an_administrator_may_overwrite_a_file_with_no_row():
    """The way back, so the refusal above is not a dead end: somebody has to be
    able to tidy up a shelf whose files the library never catalogued."""
    from endpoints.roms import roms_router as R

    assert R._may_replace(_request(ADMIN, 1), None)


def test_the_rule_is_the_same_one_the_delete_button_uses():
    """Not a second opinion about ownership. If these two ever disagree, one of
    them is offering something the other refuses."""
    from handler.library.ownership import can_delete_rom

    from endpoints.roms import roms_router as R

    for scopes, uid, owner in [
        (UPLOADER, OWNER, OWNER), (UPLOADER, OWNER, SOMEBODY_ELSE),
        (UPLOADER, OWNER, None), (ADMIN, 1, SOMEBODY_ELSE),
    ]:
        rom = _existing(owner)
        assert R._may_replace(_request(scopes, uid), rom) == can_delete_rom(scopes, uid, rom)


def test_the_route_asks_before_it_opens_the_file():
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index("async def upload_roms(")
    body = source[at:source.index("\n@", at)]

    assert "_may_replace(" in body, (
        "trasa nadal otwiera plik w trybie 'wb' bez pytania, wiec kazde konto "
        "z prawem uploadu kasuje cudzy ROM znajac sama nazwe pliku"
    )
    assert body.index("_may_replace(") < body.index('open(dest_path, "wb")'), (
        "pytanie pada PO otwarciu pliku, a otwarcie w trybie 'wb' juz go obcielo"
    )
