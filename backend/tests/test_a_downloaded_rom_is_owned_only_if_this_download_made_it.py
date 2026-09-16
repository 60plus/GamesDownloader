"""A downloaded ROM becomes the downloader's only if this download brought it.

The download-side twin of finding #8 in the 1.0.34 pre-release audit. The ROM
downloader is open to non-admins from 1.0.34, and after a file lands
`_register_and_scrape` looked the row up by (platform, file name) and stamped the
downloader as its owner whenever it had none. The same lookup that let an upload
take a ROM over finds rows that are not this file's:

  * a copy of the same name under `roms/`, which the download's own `exists()`
    check at the shelf does not see, folded into one row by the scan;
  * the same name in other letter case, because the database compares names
    without regard to case;
  * a ROM scanned in long ago at exactly this path, re-fetched over with `force`.

Owning any of those lets the account delete a file it did not fetch, and the
delete takes every account's saves for that ROM with it.

So the stamp needs the same two answers the upload path now asks for: there was
no row for this name before the download registered, and the row that exists
afterwards carries exactly this name in exactly this shelf.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

OWNER = 7


def _key(name: str) -> str:
    """How the database compares file names: without regard to case."""
    return name.casefold()


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.metadata import rom_scrape_handler as scrape
    from handler.roms import rom_source_handler as rsh

    psx = tmp_path / "psx"
    psx.mkdir()
    state = SimpleNamespace(rows={}, stamped=[], landed=[], scan_places={})

    async def scan_after_write():
        for name in state.landed:
            state.rows.setdefault(_key(name), SimpleNamespace(
                id=100 + len(state.rows), fs_name=name,
                fs_path=state.scan_places.get(name, str(psx)), published_by=None))

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="psx", fs_slug="psx")

    async def get_by_fs_name(_platform_id, name):
        return state.rows.get(_key(name))

    async def set_owner(rom_id, user_id):
        state.stamped.append((rom_id, user_id))

    async def with_platform(_rom_id):
        return SimpleNamespace(id=_rom_id, platform=None)

    async def no_scrape(*_a, **_k):
        return None

    monkeypatch.setattr(rsh, "scan_after_write", scan_after_write)
    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))
    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", get_by_fs_name)
    monkeypatch.setattr(R.rom_handler, "set_owner", set_owner)
    monkeypatch.setattr(R.rom_handler, "get_with_platform", with_platform)
    monkeypatch.setattr(scrape, "scrape_rom", no_scrape)

    async def newest_rom_id():
        # Rows already in the library are older than this; rows a scan makes
        # during a test are newer (ids from 100).
        return 50

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id, raising=False)
    return SimpleNamespace(rsh=rsh, state=state, psx=psx)


def _already_there(env, fs_name, folder):
    env.state.rows[_key(fs_name)] = SimpleNamespace(
        id=5, fs_name=fs_name, fs_path=str(folder), published_by=None)


async def _landed(env, filename):
    env.state.landed = [filename]
    await env.rsh._register_and_scrape("psx", filename, owner_id=OWNER)


@pytest.mark.asyncio
async def test_a_rom_already_in_the_roms_subfolder_is_not_given_to_the_downloader(downloads):
    _already_there(downloads, "Game.chd", downloads.psx / "roms")

    await _landed(downloads, "Game.chd")

    assert downloads.state.stamped == [], (
        "pobierajacy zostal wlascicielem ROM-u, ktory lezal juz w roms/ - "
        "usuniecie skasuje oryginal i zapisy wszystkich kont"
    )


@pytest.mark.asyncio
async def test_a_case_variant_of_a_rom_on_the_shelf_is_not_given_to_the_downloader(downloads):
    _already_there(downloads, "Crash Bandicoot (Europe).chd", downloads.psx)

    await _landed(downloads, "crash bandicoot (europe).chd")

    assert downloads.state.stamped == []


@pytest.mark.asyncio
async def test_a_rom_scanned_in_before_is_not_given_to_whoever_fetches_it_again(downloads):
    """A forced re-download over a ROM the library already held: exactly this
    name, exactly this folder - and still not this account's."""
    _already_there(downloads, "Old.bin", downloads.psx)

    await _landed(downloads, "Old.bin")

    assert downloads.state.stamped == [], (
        "ponowne pobranie przepisalo ROM z biblioteki na pobierajacego"
    )


@pytest.mark.asyncio
async def test_a_rom_this_download_brought_is_still_its_downloaders(downloads):
    """THE LEGAL CASE the stamp exists for: without it the ROM counts against no
    quota and the account that fetched it cannot remove it."""
    await _landed(downloads, "Fresh.bin")

    assert downloads.state.stamped == [(100, OWNER)], (
        "nowo pobrany ROM stracil wlasciciela"
    )


@pytest.mark.asyncio
async def test_a_row_the_scan_made_for_a_case_variant_is_not_given_to_the_downloader(downloads):
    """No row when the download registered, and one afterwards - but the scan made
    it for `CRASH.CHD`, another file on a case-sensitive disk that landed in the
    meantime. The lookup compares names without regard to case and hands that
    row back for `crash.chd`."""
    downloads.state.landed = ["CRASH.CHD"]

    await downloads.rsh._register_and_scrape("psx", "crash.chd", owner_id=OWNER)

    assert downloads.state.stamped == [], (
        "pobierajacy zostal wlascicielem wiersza innego pliku o tej samej nazwie"
    )


@pytest.mark.asyncio
async def test_a_row_the_scan_points_at_the_roms_subfolder_is_not_given_to_the_downloader(downloads):
    """A copy under `roms/` that no scan had reached yet has no row before the
    download, and the scan that follows can leave the one row it makes pointing
    at that copy. Deleting "the download" would delete it."""
    downloads.state.scan_places["Quiet.bin"] = str(downloads.psx / "roms")

    await _landed(downloads, "Quiet.bin")

    assert downloads.state.stamped == [], (
        "stempel poszedl na wiersz wskazujacy inny plik niz pobrany"
    )


@pytest.mark.asyncio
async def test_a_row_the_scan_carried_over_from_a_vanished_file_is_not_the_downloaders(downloads, monkeypatch):
    """The scanner's rename adoption. A ROM whose file vanished from the disk
    after the last scan, and the same bytes arriving under another name: the scan
    keeps the OLD row - saves, play history and collections key on its id - and
    moves the new file's name and folder onto it. So after the scan the row
    carries exactly this name in exactly this shelf, and no row had that name
    before. Only its id says it was not made by this download."""
    old = SimpleNamespace(id=5, fs_name="Super Mario World (USA).sfc",
                          fs_path=str(downloads.psx), published_by=None)

    async def scan_adopts():
        old.fs_name = "smw.sfc"
        downloads.state.rows[_key("smw.sfc")] = old

    monkeypatch.setattr(downloads.rsh, "scan_after_write", scan_adopts)

    await downloads.rsh._register_and_scrape("psx", "smw.sfc", owner_id=OWNER)

    assert downloads.state.stamped == [], (
        "pobierajacy zostal wlascicielem starego wiersza z zapisami innych kont, "
        "ktory skaner przepisal na nazwe pobranego pliku"
    )


@pytest.mark.asyncio
async def test_a_carried_over_row_that_is_the_newest_in_the_library_is_not_the_downloaders(downloads, monkeypatch):
    """The boundary. The ROM whose file vanished can be the last one scanned in,
    so its id is exactly the newest before this download - and still old."""
    old = SimpleNamespace(id=50, fs_name="Last Scanned (USA).sfc",
                          fs_path=str(downloads.psx), published_by=None)

    async def scan_adopts():
        old.fs_name = "last.sfc"
        downloads.state.rows[_key("last.sfc")] = old

    monkeypatch.setattr(downloads.rsh, "scan_after_write", scan_adopts)

    await downloads.rsh._register_and_scrape("psx", "last.sfc", owner_id=OWNER)

    assert downloads.state.stamped == []


@pytest.mark.asyncio
async def test_the_newest_row_is_read_before_the_scan_that_makes_this_one(downloads, monkeypatch):
    """THE LEGAL CASE for the id check. Read after the scan, the row this download
    brought would itself be the newest, and no download would ever be owned."""
    downloads.state.rows[_key("Older.bin")] = SimpleNamespace(
        id=7, fs_name="Older.bin", fs_path=str(downloads.psx), published_by=None)

    async def newest_rom_id():
        return max((r.id for r in downloads.state.rows.values()), default=0)

    monkeypatch.setattr(downloads.rsh.rom_handler, "max_rom_id", newest_rom_id)

    await _landed(downloads, "Fresh.bin")

    assert downloads.state.stamped and downloads.state.stamped[0][1] == OWNER, (
        "pobrany ROM nie dostal wlasciciela - granica id czytana po skanie"
    )
