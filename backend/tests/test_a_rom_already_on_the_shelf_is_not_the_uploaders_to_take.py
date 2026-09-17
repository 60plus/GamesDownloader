"""A ROM already on the shelf is not the uploader's to take.

Finding #8 of the 1.0.34 pre-release audit, confirmed by a skeptic who walked the
whole path for an account holding only LIBRARY_UPLOAD and ROMS_READ.

The upload route asked about ownership only `if dest_path.exists()`. A file that
was already in the library under the same name, but not at that exact path,
slipped past the question through either of two doors:

  * THE `roms/` SUBFOLDER. The scan walks `psx/` and `psx/roms/`, and a ROM is
    identified by (platform, file name) with no uniqueness constraint, so
    `psx/roms/Game.chd` and a freshly uploaded `psx/Game.chd` are one row - while
    `exists()` at `psx/` said there was nothing there.
  * A CASE VARIANT. MariaDB's default collation compares names without regard to
    case, so `crash bandicoot (europe).chd` finds the row of
    `Crash Bandicoot (Europe).chd`. On the case-sensitive filesystem the container
    runs on, the variant is a different path and `exists()` said no.

Either way the file was written, the scan folded it into the existing row, and
`_stamp_uploaded` recorded the uploader as the owner of a row that was never
theirs. The delete button reads that owner - and deleting removes the ORIGINAL
file and every account's saves with it.

No malice is needed. An uploader re-sending a ROM that is already on the shelf
became its owner, and tidying up "their" upload later wiped everybody's saves.

The fix asks the question the upload is really about - does this name already have
a row on this platform - before anything is written, whether or not a file sits at
the destination. And the stamp goes only onto a row this upload brought into
being: a name with no row when the request arrived, whose row afterwards carries
exactly that name, in exactly the folder the file was written to.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from handler.auth.scopes import Scope

UPLOADER_ID = 7
#: The highest ROM id before an upload's scan. Rows on the shelf are older.
NEWEST_BEFORE = 50
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
#: ROMS_WRITE is what the rest of the ROM API treats as administrative.
ADMIN = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ, Scope.ROMS_WRITE}


class _Upload:
    """Enough of UploadFile for the route: a name and a stream."""

    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._at = 0

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


def _key(name: str) -> str:
    """How the database compares file names: without regard to case."""
    return name.casefold()


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    psx = tmp_path / "psx"
    psx.mkdir()
    #: `scan_places` says which folder the scan's row ends up pointing at for a
    #: name, when that is not the shelf itself.
    state = SimpleNamespace(rows={}, stamped=[], pending=[], scan_places={})

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return 1024 ** 3

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="psx", fs_slug="psx")

    async def get_by_fs_name(_platform_id, name):
        return state.rows.get(_key(name))

    async def set_owner(rom_id, user_id):
        state.stamped.append((rom_id, user_id))

    async def clam_off():
        return False

    async def scan_after_write():
        # What a scan does as far as this route is concerned: each landed name
        # gets a row, unless a row already holds that name - compared the way
        # the database compares it.
        for name in state.pending:
            state.rows.setdefault(_key(name), SimpleNamespace(
                id=100 + len(state.rows), fs_name=name,
                fs_path=state.scan_places.get(name, str(psx)),
                published_by=None, fs_size_bytes=9))

    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)

    async def no_live_limit(_user, **_k):
        # The budget here is the ceiling above. Uploads running side by side
        # are checked live as well, and that has its own tests
        # (test_uploads_running_side_by_side_see_each_other).
        return quota.Reservation(None, limit=0)

    monkeypatch.setattr(quota, "reservation_for", no_live_limit)
    monkeypatch.setattr(rsh, "scan_after_write", scan_after_write)
    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", get_by_fs_name)
    monkeypatch.setattr(R.rom_handler, "set_owner", set_owner)
    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)

    async def newest_rom_id():
        # Every row already on the shelf is older than this; every row a scan
        # makes during a test is newer (ids from 100).
        return NEWEST_BEFORE

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id, raising=False)
    return SimpleNamespace(R=R, state=state, psx=psx)


def _request(scopes, user_id=UPLOADER_ID):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


async def _upload(env, names, scopes=UPLOADER):
    env.state.pending = list(names)
    tasks = BackgroundTasks()
    out = await env.R.upload_roms(
        _request(scopes), slug="psx", background_tasks=tasks,
        files=[_Upload(n, b"rom bytes") for n in names],
    )
    await tasks()          # the route defers the scan; run it as the server would
    return out


def _already_on_shelf(env, fs_name, folder, owner=None):
    """A ROM the library has held for a while: a file, and a row for it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / fs_name).write_bytes(b"THE ORIGINAL")
    row = SimpleNamespace(id=5, fs_name=fs_name, fs_path=str(folder),
                          published_by=owner, fs_size_bytes=12)
    env.state.rows[_key(fs_name)] = row
    return row


def _refused_as_already_here(out, name):
    return any(r.get("filename") == name and r.get("action") == "already_here"
               for r in out.get("rejected", []))


# ── The two doors ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_rom_in_the_roms_subfolder_is_not_taken_over(shelf):
    _already_on_shelf(shelf, "Game.chd", shelf.psx / "roms")

    out = await _upload(shelf, ["Game.chd"])

    assert _refused_as_already_here(out, "Game.chd"), (
        "wgranie przeszlo, choc ta gra juz ma wiersz na tej platformie - skan "
        "polaczy oba pliki w jeden wiersz"
    )
    assert not (shelf.psx / "Game.chd").exists(), "plik i tak zostal zapisany"
    assert shelf.state.stamped == [], (
        "wgrywajacy zostal wlascicielem cudzego ROM-u, a przycisk usuwania "
        "skasuje oryginal i zapisy wszystkich kont"
    )


@pytest.mark.asyncio
async def test_a_case_variant_of_a_rom_on_the_shelf_is_not_taken_over(shelf):
    """On a case-sensitive filesystem - the one the container runs on - the variant
    is a different path, so `exists()` said there was nothing to protect."""
    _already_on_shelf(shelf, "Crash Bandicoot (Europe).chd", shelf.psx)

    out = await _upload(shelf, ["crash bandicoot (europe).chd"])

    assert _refused_as_already_here(out, "crash bandicoot (europe).chd"), (
        "wariant wielkosci liter przeszedl, a baza porownuje nazwy bez wielkosci "
        "liter, wiec to ten sam wiersz"
    )
    assert shelf.state.stamped == []


@pytest.mark.asyncio
async def test_the_stamp_goes_only_on_a_row_this_upload_made_in_its_own_folder(shelf):
    """A name with no row when the upload arrived can still land in a row that is
    not this file's. A copy under `psx/roms/` that no scan had reached yet is
    folded into the same row by the scan that follows, and the walk can leave the
    row pointing at that copy. Deleting "the upload" would then delete it."""
    (shelf.psx / "roms").mkdir()
    (shelf.psx / "roms" / "Quiet.bin").write_bytes(b"NEVER SCANNED")
    shelf.state.scan_places["Quiet.bin"] = str(shelf.psx / "roms")

    await _upload(shelf, ["Quiet.bin"])

    assert shelf.state.stamped == [], (
        "stempel poszedl na wiersz, ktory wskazuje na inny plik niz ten wgrany"
    )


@pytest.mark.asyncio
async def test_the_stamp_needs_exactly_this_name_not_one_the_database_calls_equal(shelf, monkeypatch):
    """No row when the upload arrived, and one afterwards - but the scan made it
    for `QUIET.BIN`, another file on a case-sensitive disk that landed between
    the question and the stamp. The lookup compares names without regard to
    case and hands that row back for `quiet.bin`."""
    from handler.roms import rom_source_handler as rsh

    async def another_file_scanned_in():
        shelf.state.rows.setdefault(_key("QUIET.BIN"), SimpleNamespace(
            id=300, fs_name="QUIET.BIN", fs_path=str(shelf.psx),
            published_by=None, fs_size_bytes=9))

    monkeypatch.setattr(rsh, "scan_after_write", another_file_scanned_in)

    await _upload(shelf, ["quiet.bin"])

    assert shelf.state.stamped == [], (
        "wgrywajacy zostal wlascicielem wiersza innego pliku o tej samej nazwie"
    )


@pytest.mark.asyncio
async def test_a_row_the_scan_carried_over_from_a_vanished_file_is_not_the_uploaders(shelf, monkeypatch):
    """The scanner's rename adoption. A ROM whose file vanished from the disk
    after the last scan, and the same bytes uploaded under another name: the scan
    keeps the OLD row - saves, play history and collections key on its id - and
    moves the new file's name and folder onto it. After the scan that row carries
    exactly this name in exactly this shelf, and no row had the name before the
    upload. Only its id says the upload did not make it; the delete button would
    have taken every account's saves with it."""
    from handler.roms import rom_source_handler as rsh

    old = SimpleNamespace(id=5, fs_name="Super Mario World (USA).sfc",
                          fs_path=str(shelf.psx), published_by=None, fs_size_bytes=9)
    shelf.state.rows[_key(old.fs_name)] = old

    async def scan_adopts():
        shelf.state.rows.pop(_key(old.fs_name), None)
        old.fs_name = "smw.sfc"
        shelf.state.rows[_key("smw.sfc")] = old

    monkeypatch.setattr(rsh, "scan_after_write", scan_adopts)

    out = await _upload(shelf, ["smw.sfc"])

    assert out["saved"] == ["smw.sfc"], "wgranie nowej nazwy zostalo odrzucone"
    assert shelf.state.stamped == [], (
        "wgrywajacy zostal wlascicielem starego wiersza z zapisami innych kont, "
        "ktory skaner przepisal na nazwe wgranego pliku"
    )


@pytest.mark.asyncio
async def test_a_carried_over_row_that_is_the_newest_in_the_library_is_not_the_uploaders(shelf, monkeypatch):
    """The boundary. The ROM whose file vanished can be the last one scanned in,
    so its id is exactly the newest before this upload - and still old."""
    from handler.roms import rom_source_handler as rsh

    old = SimpleNamespace(id=NEWEST_BEFORE, fs_name="Last Scanned (USA).sfc",
                          fs_path=str(shelf.psx), published_by=None, fs_size_bytes=9)
    shelf.state.rows[_key(old.fs_name)] = old

    async def scan_adopts():
        shelf.state.rows.pop(_key(old.fs_name), None)
        old.fs_name = "last.sfc"
        shelf.state.rows[_key("last.sfc")] = old

    monkeypatch.setattr(rsh, "scan_after_write", scan_adopts)

    await _upload(shelf, ["last.sfc"])

    assert shelf.state.stamped == []


# ── What must keep working ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_new_rom_is_still_stamped_for_its_uploader(shelf):
    """THE LEGAL CASE the stamp exists for: without it the upload counts against
    nobody's quota and its uploader cannot delete it."""
    out = await _upload(shelf, ["Fresh.bin"])

    assert out["saved"] == ["Fresh.bin"]
    assert shelf.state.stamped == [(100, UPLOADER_ID)], (
        "nowy ROM stracil wlasciciela"
    )


@pytest.mark.asyncio
async def test_a_new_rom_another_scan_registers_first_is_still_its_uploaders(shelf, monkeypatch):
    """THE LEGAL CASE for the id check. Registration runs after the response,
    and a scan started by somebody else's upload can reach this file first. Its
    row is still this upload's - it did not exist when the request arrived - so
    the "newest row so far" has to be read when the request arrives too. Read
    once the file was already on the disk, that row counted as older and the
    ROM was left owned by nobody."""
    async def newest_rom_id():
        return max((r.id for r in shelf.state.rows.values()), default=0)

    monkeypatch.setattr(shelf.R.rom_handler, "max_rom_id", newest_rom_id)

    tasks = BackgroundTasks()
    shelf.state.pending = ["Early.bin"]
    out = await shelf.R.upload_roms(
        _request(UPLOADER), slug="psx", background_tasks=tasks,
        files=[_Upload("Early.bin", b"rom bytes")])
    assert out["saved"] == ["Early.bin"]

    # Another upload's scan gets there before this one's registration runs.
    shelf.state.rows[_key("Early.bin")] = SimpleNamespace(
        id=100, fs_name="Early.bin", fs_path=str(shelf.psx),
        published_by=None, fs_size_bytes=9)
    await tasks()

    assert shelf.state.stamped == [(100, UPLOADER_ID)], (
        "ROM zarejestrowany przez cudzy skan zostal bez wlasciciela - nie liczy "
        "sie do limitu, a wgrywajacy nie moze go usunac"
    )


@pytest.mark.asyncio
async def test_an_owner_may_still_resend_their_own_rom(shelf):
    """Swapping a bad dump for a good one is the ordinary reason to send the same
    name twice."""
    _already_on_shelf(shelf, "Mine.bin", shelf.psx, owner=UPLOADER_ID)

    out = await _upload(shelf, ["Mine.bin"])

    assert out["saved"] == ["Mine.bin"]
    assert (shelf.psx / "Mine.bin").read_bytes() == b"rom bytes"


@pytest.mark.asyncio
async def test_an_admin_may_still_replace_an_unowned_rom_without_becoming_its_owner(shelf):
    """Somebody has to be able to tidy up a shelf. Replacing a ROM the library
    has held for years does not make it the admin's own upload, though - it
    carries other accounts' saves exactly as before."""
    _already_on_shelf(shelf, "Shared.bin", shelf.psx)

    out = await _upload(shelf, ["Shared.bin"], scopes=ADMIN)

    assert out["saved"] == ["Shared.bin"]
    assert shelf.state.stamped == [], (
        "podmiana wspolnego ROM-u przez admina przepisala go na jego konto"
    )

# ── A second copy of your own ROM is not free ─────────────────────────────────
#
# A second copy of your own ROM is not free storage.
#
# Found by the 1.0.34 audit round on ROM ownership and left for 1.0.35 to confirm:
# "wlasciciel wgrywa wariant wielkosci liter (ucieczka od limitu)".
#
# Confirmed from the route. A ROM row is found by name the way MariaDB compares
# names - without regard to case - and a row in `psx/roms/` answers for `psx/` too.
# When that row is the uploader's own, the route read the upload as REPLACING it
# and let it through. But the bytes did not replace anything:
#
#   * `GAME.chd` beside `Game.chd` is another file on the case-sensitive disk the
#     container runs on;
#   * `psx/Game.chd` beside `psx/roms/Game.chd` is another file in another folder.
#
# The original stays, the new file lands beside it, and the scan folds both into
# the one row that is already charged - or leaves the second without a row at all.
# Either way the second copy counts against nothing, and an account at its limit
# can repeat it with every spelling of the name.
#
# A replacement is the same file: the same name in the same folder. Anything else
# that the database calls the same ROM is refused like a name somebody else holds.
# The owner swapping a bad dump for a good one under the SAME name keeps working,
# and is tested here beside the refusals.

@pytest.mark.asyncio
async def test_a_case_variant_of_your_own_rom_is_refused(shelf):
    _already_on_shelf(shelf, "Game.chd", shelf.psx, owner=UPLOADER_ID)

    out = await _upload(shelf, ["GAME.chd"])

    assert _refused_as_already_here(out, "GAME.chd"), (
        "wlasny ROM pod inna wielkoscia liter przeszedl jako 'podmiana', a to drugi "
        "plik obok pierwszego, ktorego nic nie liczy do limitu"
    )
    assert not (shelf.psx / "GAME.chd").exists()
    assert (shelf.psx / "Game.chd").read_bytes() == b"THE ORIGINAL"


@pytest.mark.asyncio
async def test_a_copy_of_your_own_rom_in_the_other_folder_is_refused(shelf):
    _already_on_shelf(shelf, "Game.chd", shelf.psx / "roms", owner=UPLOADER_ID)

    out = await _upload(shelf, ["Game.chd"])

    assert _refused_as_already_here(out, "Game.chd")
    assert not (shelf.psx / "Game.chd").exists()


@pytest.mark.asyncio
async def test_an_administrator_does_not_make_a_second_copy_either(shelf):
    """Not a question of permission: two files for one row confuse every later
    scan and delete, whoever made them."""
    _already_on_shelf(shelf, "Game.chd", shelf.psx, owner=UPLOADER_ID)

    out = await _upload(shelf, ["game.CHD"], scopes=ADMIN)

    assert _refused_as_already_here(out, "game.CHD")


@pytest.mark.asyncio
async def test_replacing_your_own_rom_under_the_same_name_still_works(shelf):
    """THE LEGAL CASE: a better dump sent under the name it already has."""
    _already_on_shelf(shelf, "Game.chd", shelf.psx, owner=UPLOADER_ID)

    out = await _upload(shelf, ["Game.chd"])

    assert out["saved"] == ["Game.chd"], f"podmiana wlasnego ROM-u zostala odrzucona: {out}"
    assert (shelf.psx / "Game.chd").read_bytes() == b"rom bytes"
