"""The platform row does not exist until a scan has made it.

`rom_platforms` is written in exactly one place: the scanner's upsert. So on the
first download to a platform nobody has scanned yet there is nothing to find,
and `_register_and_scrape` asked before it scanned:

    platform = await rom_platform_handler.get_by_slug(...)
    if platform is None:
        return None                       # ...and the scan never runs

Which is the ordinary way a shelf begins. `_init_rom_dirs` makes a folder for
every known platform at boot, and the folders stay empty and row-less until
something lands in one. So the first game fetched onto a new shelf returned
None: the browser got `rom_id: null` and could not open the page, no metadata
was fetched, and when a later scan finally made the row it was owner-blind by
design - the ROM belonged to nobody, counted against no quota, and the account
that fetched it could not delete it.

That is the complaint this whole package of fixes was written for, reintroduced
by moving two statements past each other.
"""

from __future__ import annotations

import types

import pytest


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


@pytest.fixture
def download(monkeypatch, tmp_path):
    """A shelf whose platform row appears only once a scan has run."""
    from handler.roms import rom_source_handler as rsh

    state = {"scans": 0, "row": None, "owner_set": None}
    # A real row carries the folder it was scanned in, and the stamp checks that
    # it is this shelf's (1.0.34 audit, finding #8).
    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))

    async def _scan():
        state["scans"] += 1
        # The scanner's upsert, which is the only writer of this table.
        if state["scans"] >= 1:
            state["row"] = types.SimpleNamespace(id=1, slug="amiga", fs_slug="amiga")

    async def _get_platform(_slug):
        return state["row"]

    async def _by_fs_name(_platform_id, filename):
        if state["row"] is None:
            return None
        return types.SimpleNamespace(id=42, fs_name=filename,
                                     fs_path=str(tmp_path / "amiga"), published_by=None)

    async def _set_owner(rom_id, owner_id):
        state["owner_set"] = (rom_id, owner_id)
        return True

    async def _boom_scrape(*a, **k):
        raise RuntimeError("scrape nie jest przedmiotem tego testu")

    monkeypatch.setattr(rsh, "scan_after_write", _scan)
    monkeypatch.setattr(rsh.rom_platform_handler, "get_by_slug", _get_platform)
    monkeypatch.setattr(rsh.rom_handler, "get_by_fs_name", _by_fs_name)
    monkeypatch.setattr(rsh.rom_handler, "set_owner", _set_owner)
    monkeypatch.setattr(rsh.rom_handler, "get_with_platform", _boom_scrape)
    # Older than the row the scan makes here (42), as every row already in the
    # library would be.
    monkeypatch.setattr(rsh.rom_handler, "max_rom_id", _fake_async(10), raising=False)
    return rsh, state


@pytest.mark.asyncio
async def test_the_first_rom_on_a_shelf_is_registered(download):
    rsh, state = download

    rom_id = await rsh._register_and_scrape("amiga", "Turrican.adf", owner_id=5)

    assert state["scans"] >= 1, (
        "pytanie o platforme pada PRZED skanem, wiec przy pierwszym pobraniu na "
        "nowa polke funkcja wychodzi, zanim cokolwiek zeskanuje"
    )
    assert rom_id == 42, "pobrana gra nie zostala zarejestrowana"


@pytest.mark.asyncio
async def test_the_account_that_fetched_it_owns_it(download):
    """The half that cannot be repaired later: the scan is owner-blind on
    purpose, so a row that misses its stamp belongs to nobody for ever."""
    rsh, state = download

    await rsh._register_and_scrape("amiga", "Turrican.adf", owner_id=5)

    assert state["owner_set"] == (42, 5), (
        "ROM nie dostal wlasciciela, wiec nie liczy sie do zadnego przydzialu "
        "i konto, ktore go sciagnelo, nie moze go usunac"
    )


@pytest.mark.asyncio
async def test_a_shelf_that_never_gets_a_row_gives_up_after_three_scans(monkeypatch):
    """The other half. Retrying without end would let a platform that genuinely
    cannot be scanned hold the download path open for ever."""
    from handler.roms import rom_source_handler as rsh

    scans = {"n": 0}

    async def _scan():
        scans["n"] += 1

    monkeypatch.setattr(rsh, "scan_after_write", _scan)
    monkeypatch.setattr(rsh.rom_platform_handler, "get_by_slug", _fake_async(None))
    monkeypatch.setattr(rsh.rom_handler, "get_by_fs_name", _fake_async(None))
    monkeypatch.setattr(rsh.rom_handler, "max_rom_id", _fake_async(10), raising=False)

    assert await rsh._register_and_scrape("amiga", "x.adf", owner_id=5) is None
    assert scans["n"] == 3, f"skan uruchomiony {scans['n']} razy zamiast trzech"
