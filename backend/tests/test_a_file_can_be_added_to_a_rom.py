"""A file can be added to a ROM game from its page, and taken away again.

The owner (2026-09-18): "Add file" on a ROM, the way a GOG or custom game has
it - an extra, a mod or the manual, by administrators and uploaders alike, and
a bin beside each file for whoever may remove it.

What follows from uploaders being allowed:

  * the bytes count against the account that brought them in. The files beside
    a game are read off the disk and have no rows, so each one added through
    the page gets a row (models/rom_added_file.py) the quota sums;
  * replacing or removing a file is the account's that added it, or an
    administrator's. A file put there over FTP has no row and counts against
    nobody; it is treated as the game's, so the ROM's owner may, like a file
    with no row in a game's folder (ownership.can_replace_file) - but only
    when every game in that folder is theirs (1.0.36 audit);
  * a game lying loose on its shelf shares the shelf's extras/ and mods/ with
    every loose game there, so it is given a folder of its own first
    (game_folder.own_folder_held) - and when it cannot be, nothing is written.

The manual is saved as the game's extras/Manual.pdf, only if it is a PDF, and
becomes the game's manual at once: the Manual button needs no scrape.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

ME, SOMEBODY, ADMIN_ID = 7, 9, 1
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
ADMIN = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ, Scope.ROMS_WRITE}


class _Upload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._at = 0

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


class _Rows:
    """rom_added_file_handler, over a list."""

    def __init__(self):
        self.rows: list = []
        self.next_id = 1

    async def in_folder(self, fs_path, **_k):
        return [r for r in self.rows if r.folder == fs_path]

    async def record(self, rom_id, fs_path, rel_path, size_bytes, published_by, **_k):
        for r in self.rows:
            if r.folder == fs_path and r.rel_path == rel_path:
                r.size_bytes, r.published_by = size_bytes, published_by or r.published_by
                return r
        row = SimpleNamespace(id=self.next_id, rom_id=rom_id, folder=fs_path, rel_path=rel_path,
                              size_bytes=size_bytes, published_by=published_by)
        self.next_id += 1
        self.rows.append(row)
        return row

    async def forget(self, ids, **_k):
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.id not in set(ids)]
        return before - len(self.rows)

    async def of_rom(self, rom_id, published_by=None, **_k):
        return [r for r in self.rows if r.rom_id == rom_id
                and (published_by is None or r.published_by == published_by)]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import game_folder

    folder = tmp_path / "psx" / "Medievil"
    folder.mkdir(parents=True)
    (folder / "MediEvil (USA).chd").write_bytes(b"disc")
    rom = SimpleNamespace(id=5, fs_path=str(folder), fs_name="MediEvil (USA).chd",
                          platform=SimpleNamespace(fs_slug="psx"), platform_id=1,
                          published_by=SOMEBODY, manual_path=None, name="MediEvil",
                          track_of=None, disk_number=None)
    # `others`: the owners of the other games in this folder, besides this one.
    state = SimpleNamespace(rom=rom, folder=folder, rows=_Rows(), own=folder,
                            budget=1 << 30, metadata=[], others=set())

    async def with_platform(rom_id, **_k):
        return state.rom if rom_id == 5 else None

    async def own(rom_id, *, roms_base):
        return state.own

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return state.budget

    async def unbounded(_user, **_k):
        return quota.Reservation(None, limit=0)

    async def clam_off():
        return False

    async def the_set(_rom_id, **_k):
        return [state.rom]

    async def update_metadata(rom_id, data, **_k):
        state.metadata.append((rom_id, data))
        if rom_id == state.rom.id and "manual_path" in data:
            state.rom.manual_path = data["manual_path"]

    async def owners_in_folder(fs_path, **_k):
        return {state.rom.published_by} | state.others if fs_path == str(state.folder) else set()

    # `other_id`: another game in the folder, for the manual's name.
    state.other_id = None

    async def another_in_folder(_fs_path, _exclude, **_k):
        return state.other_id

    async def manual_claimed(*_a, **_k):
        return False

    monkeypatch.setattr(R.rom_handler, "owners_in_folder", owners_in_folder)
    monkeypatch.setattr(R.rom_handler, "another_in_folder", another_in_folder)
    monkeypatch.setattr(R.rom_handler, "manual_claimed", manual_claimed)
    monkeypatch.setattr(R.rom_handler, "get_with_platform", with_platform)
    monkeypatch.setattr(R.rom_handler, "disk_set", the_set)
    monkeypatch.setattr(R.rom_handler, "update_metadata", update_metadata)
    monkeypatch.setattr(game_folder, "own_folder_held", own)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(R, "rom_added_file_handler", state.rows)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)
    monkeypatch.setattr(quota, "reservation_for", unbounded)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    state.R = R
    return state


def _request(scopes=UPLOADER, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


def _route(fn):
    return getattr(fn, "__wrapped__", fn)


async def _add(lib, name, data=b"x" * 100, kind="extra", *, scopes=UPLOADER, user_id=ME,
               overwrite=False):
    return await _route(lib.R.add_rom_file)(
        _request(scopes, user_id), 5, file=_Upload(name, data), kind=kind, overwrite=overwrite)


# ── Adding ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, where", [("extra", "extras"), ("mod", "mods")])
async def test_an_extra_or_a_mod_lands_in_the_games_folder_and_is_charged(lib, kind, where):
    out = await _add(lib, "Map.png", b"p" * 300, kind)

    assert (lib.folder / where / "Map.png").read_bytes() == b"p" * 300
    assert out["path"] == f"{where}/Map.png"
    [row] = lib.rows.rows
    assert (row.rel_path, row.size_bytes, row.published_by) == (f"{where}/Map.png", 300, ME)
    assert not list(lib.folder.rglob("*.part")), "zostal niedokonczony plik"


@pytest.mark.asyncio
async def test_the_manual_becomes_the_games_manual(lib):
    await _add(lib, "whatever I called it.pdf", b"%PDF-1.4 booklet", "manual")

    assert (lib.folder / "extras" / "Manual.pdf").read_bytes() == b"%PDF-1.4 booklet"
    assert lib.rom.manual_path == "extras/Manual.pdf", "przycisk Manual nie pojawi sie bez scrape"


@pytest.mark.asyncio
async def test_a_manual_sent_into_a_folder_other_games_share_is_named_after_its_game(lib):
    """The scrape names a manual after its game in a folder several games live
    in (manuals.manual_home); a manual sent from the page is named the same
    way, or the second region's was refused as already there, or replaced the
    first region's booklet (1.0.36 audit, round 2)."""
    lib.other_id = 40
    await _add(lib, "m.pdf", b"%PDF-1.4 mine", "manual")

    assert (lib.folder / "extras" / "MediEvil - Manual.pdf").is_file()
    assert not (lib.folder / "extras" / "Manual.pdf").exists()
    assert lib.rom.manual_path == "extras/MediEvil - Manual.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, name", [("manual", "any.pdf"), ("extra", "Manual.pdf")])
async def test_a_manual_somebody_sends_is_theirs_and_a_scrape_keeps_it(lib, kind, name):
    """A forced scrape replaces what a provider gave and keeps what a person
    chose (keep_existing_media), and it tells them apart by the row's media
    origin. A manual sent over a scraped one left the origin saying "scrape",
    so the next forced scrape fetched ScreenScraper's copy over it (1.0.36
    audit)."""
    await _add(lib, name, b"%PDF-1.4 mine", kind)

    written = [data for rom_id, data in lib.metadata if rom_id == 5 and "manual_path" in data]
    assert written, "reczna instrukcja nie zostala instrukcja gry"
    assert (written[-1].get("media_source") or {}).get("manual_path") == "manual", (
        "instrukcja wyslana reka wyglada na pobrana przez scrape"
    )


@pytest.mark.asyncio
async def test_a_manual_that_is_not_a_pdf_is_refused_and_nothing_is_left(lib):
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "manual.pdf", b"<html>not a pdf</html>", "manual")

    assert refused.value.status_code == 400
    assert not (lib.folder / "extras").exists() or not any((lib.folder / "extras").iterdir())
    assert lib.rows.rows == [] and lib.rom.manual_path is None


@pytest.mark.asyncio
async def test_an_extra_that_lands_where_the_manual_lives_has_to_be_a_pdf(lib):
    """extras/Manual.pdf is the manual's own name. Sent as an extra it skipped
    the PDF check and became a manual nobody could open (1.0.36 audit)."""
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "Manual.pdf", b"<html>not a pdf</html>", "extra")
    assert refused.value.status_code == 400
    assert not (lib.folder / "extras" / "Manual.pdf").exists() and lib.rows.rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [".hidden", "half.zip.part", "", "..", ".",
                                  "two\nlines.txt", "nul\x00.txt", "tab\there.txt"])
async def test_a_name_the_list_would_never_show_is_refused(lib, name):
    with pytest.raises(HTTPException) as refused:
        await _add(lib, name)
    assert refused.value.status_code == 400
    assert lib.rows.rows == []


@pytest.mark.asyncio
async def test_a_directory_in_the_name_is_dropped(lib):
    out = await _add(lib, "../../evil/../Notes.txt")
    assert out["path"] == "extras/Notes.txt"
    assert (lib.folder / "extras" / "Notes.txt").is_file()


@pytest.mark.asyncio
async def test_a_kind_it_does_not_know_is_refused(lib):
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "a.zip", kind="dlc")
    assert refused.value.status_code == 400


@pytest.mark.asyncio
async def test_a_game_that_can_have_no_folder_of_its_own_gets_nothing(lib):
    lib.own = None
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "Notes.txt")
    assert refused.value.status_code == 409
    assert not (lib.folder / "extras").exists() and lib.rows.rows == []


@pytest.mark.asyncio
async def test_a_file_bigger_than_what_is_left_is_refused_and_taken_away(lib):
    lib.budget = 50
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "big.zip", b"x" * 400)
    assert refused.value.status_code == 413
    assert not list(lib.folder.rglob("big.zip*")) and lib.rows.rows == []


# ── Replacing ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_name_already_there_is_not_written_over_unasked(lib):
    await _add(lib, "Notes.txt", b"mine")
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "Notes.txt", b"again")
    assert refused.value.status_code == 409
    assert (lib.folder / "extras" / "Notes.txt").read_bytes() == b"mine"


@pytest.mark.asyncio
async def test_somebody_elses_file_is_not_theirs_to_replace(lib):
    await _add(lib, "Notes.txt", b"theirs", user_id=SOMEBODY)
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "Notes.txt", b"mine", overwrite=True)
    assert refused.value.status_code == 403
    assert (lib.folder / "extras" / "Notes.txt").read_bytes() == b"theirs"


@pytest.mark.asyncio
async def test_an_administrator_may_replace_it_and_the_row_follows_the_bytes(lib):
    await _add(lib, "Notes.txt", b"theirs", user_id=SOMEBODY)
    await _add(lib, "Notes.txt", b"better notes", overwrite=True, scopes=ADMIN, user_id=ADMIN_ID)
    [row] = lib.rows.rows
    assert (row.size_bytes, row.published_by) == (len(b"better notes"), ADMIN_ID)


# ── Why, in a word the screen can translate ─────────────────────────────────
#
# The server names the reason and the screen says it (lib/uploadResult.ts,
# project_tlumaczenia_bledow): the sentence in `detail` stays for anything that
# does not know the name, and X-GD-Reason carries it for RomAddFileForm.


async def _reason_of(coro) -> tuple[int, str | None]:
    with pytest.raises(HTTPException) as refused:
        await coro
    return refused.value.status_code, (refused.value.headers or {}).get("X-GD-Reason")


@pytest.mark.asyncio
async def test_every_refusal_names_its_reason(lib):
    assert await _reason_of(_add(lib, ".hidden")) == (400, "bad_name")
    assert await _reason_of(_add(lib, "m.pdf", b"<html>", "manual")) == (400, "not_pdf")
    await _add(lib, "Notes.txt", b"theirs", user_id=SOMEBODY)
    assert await _reason_of(_add(lib, "Notes.txt")) == (409, "already_here")
    assert await _reason_of(_add(lib, "Notes.txt", overwrite=True)) == (403, "not_yours")
    lib.budget = 1
    assert await _reason_of(_add(lib, "big.zip", b"x" * 100)) == (413, "no_room")
    lib.own = None
    assert await _reason_of(_add(lib, "Other.txt")) == (409, "no_folder")


# ── Removing ─────────────────────────────────────────────────────────────────


async def _remove(lib, path, *, scopes=UPLOADER, user_id=ME):
    return await _route(lib.R.remove_rom_extra)(_request(scopes, user_id), 5, path=path)


@pytest.mark.asyncio
async def test_the_account_that_added_a_file_takes_it_away(lib):
    await _add(lib, "Notes.txt")
    await _remove(lib, "extras/Notes.txt")
    assert not (lib.folder / "extras" / "Notes.txt").exists() and lib.rows.rows == []
    assert (lib.folder / "MediEvil (USA).chd").is_file(), "kosz siegnal po gre"


@pytest.mark.asyncio
async def test_somebody_elses_file_stays(lib):
    await _add(lib, "Notes.txt", user_id=SOMEBODY)
    with pytest.raises(HTTPException) as refused:
        await _remove(lib, "extras/Notes.txt")
    assert refused.value.status_code == 403
    assert (lib.folder / "extras" / "Notes.txt").is_file()


@pytest.mark.asyncio
async def test_a_file_put_there_over_ftp_is_the_games_owners(lib):
    (lib.folder / "mods").mkdir()
    (lib.folder / "mods" / "ftp.zip").write_bytes(b"z")
    with pytest.raises(HTTPException):
        await _remove(lib, "mods/ftp.zip")                       # not my game
    lib.rom.published_by = ME
    await _remove(lib, "mods/ftp.zip")                           # my game now
    assert not (lib.folder / "mods" / "ftp.zip").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [SOMEBODY, None], ids=["another-account", "nobodys"])
async def test_a_file_nobody_added_is_not_theirs_while_another_game_shares_the_folder(lib, other):
    """An uploader could get a game of their own into somebody else's folder -
    a further disc sent `into` it is enough - and the files nobody added there
    were then theirs to bin or overwrite, because the rule asked only who owns
    THIS game (1.0.36 audit). Those files are the folder's, and the folder is
    theirs only when every game in it is."""
    (lib.folder / "mods").mkdir()
    (lib.folder / "mods" / "ftp.zip").write_bytes(b"z")
    (lib.folder / "extras").mkdir()
    (lib.folder / "extras" / "Manual.pdf").write_bytes(b"%PDF-1.4 theirs")
    lib.rom.published_by = ME
    lib.others = {other}

    with pytest.raises(HTTPException) as refused:
        await _remove(lib, "mods/ftp.zip")
    assert refused.value.status_code == 403
    with pytest.raises(HTTPException) as refused:
        await _add(lib, "m.pdf", b"%PDF-1.4 mine", "manual", overwrite=True)
    assert refused.value.status_code == 403
    listed = [{"path": "mods/ftp.zip"}]
    await lib.R._mark_extras(_request(), lib.rom, listed)
    assert listed[0]["can_delete"] is False

    assert (lib.folder / "mods" / "ftp.zip").is_file()
    assert (lib.folder / "extras" / "Manual.pdf").read_bytes() == b"%PDF-1.4 theirs"


@pytest.mark.asyncio
async def test_what_an_account_added_stays_theirs_in_a_shared_folder(lib):
    """The other half: a file with a row is its adder's wherever it is."""
    lib.others = {SOMEBODY}
    await _add(lib, "Mine.txt")
    await _remove(lib, "extras/Mine.txt")
    assert not (lib.folder / "extras" / "Mine.txt").exists()


@pytest.mark.asyncio
async def test_only_a_listed_file_can_be_binned(lib):
    with pytest.raises(HTTPException) as refused:
        await _remove(lib, "MediEvil (USA).chd", scopes=ADMIN, user_id=ADMIN_ID)
    assert refused.value.status_code == 404
    assert (lib.folder / "MediEvil (USA).chd").is_file()


@pytest.mark.asyncio
async def test_binning_the_manual_takes_the_button_away(lib):
    await _add(lib, "m.pdf", b"%PDF-1.4", "manual")
    await _remove(lib, "extras/Manual.pdf")
    assert lib.rom.manual_path is None


@pytest.mark.asyncio
async def test_remove_my_files_takes_mine_and_leaves_theirs(lib):
    await _add(lib, "Mine.txt")
    await _add(lib, "Theirs.txt", user_id=SOMEBODY)

    out = await _route(lib.R.remove_my_rom_files)(_request(), 5)

    assert out["removed"] == 1
    assert not (lib.folder / "extras" / "Mine.txt").exists()
    assert (lib.folder / "extras" / "Theirs.txt").is_file()
    assert [r.rel_path for r in lib.rows.rows] == ["extras/Theirs.txt"]


@pytest.mark.asyncio
async def test_remove_my_files_keeps_counting_a_file_it_could_not_remove(lib, monkeypatch):
    """The row is what the quota sums. Forgotten while the file stayed, the
    bytes stopped counting against anybody (1.0.36 audit)."""
    await _add(lib, "Stuck.txt")
    monkeypatch.setattr(lib.R, "_unlink_added", lambda path, folder: False)

    await _route(lib.R.remove_my_rom_files)(_request(), 5)

    assert [r.rel_path for r in lib.rows.rows] == ["extras/Stuck.txt"]


@pytest.mark.asyncio
async def test_the_bin_keeps_counting_a_file_it_could_not_remove(lib, monkeypatch):
    """Round 2 of the audit: the bin beside one file forgot the row whatever
    the removal did, the same leak Remove my files had."""
    await _add(lib, "Stuck.txt")
    monkeypatch.setattr(lib.R, "_unlink_added", lambda path, folder: False)

    with pytest.raises(HTTPException):
        await _remove(lib, "extras/Stuck.txt")

    assert [r.rel_path for r in lib.rows.rows] == ["extras/Stuck.txt"]


@pytest.mark.asyncio
async def test_remove_my_files_forgets_nothing_while_the_folder_is_not_there(lib):
    """Storage gone offline reads every file as gone."""
    await _add(lib, "Mine.txt")
    lib.folder.rename(lib.folder.with_name("Medievil (elsewhere)"))

    with pytest.raises(HTTPException) as refused:
        await _route(lib.R.remove_my_rom_files)(_request(), 5)

    assert refused.value.status_code == 409
    assert [r.rel_path for r in lib.rows.rows] == ["extras/Mine.txt"]


@pytest.mark.asyncio
async def test_remove_my_files_forgets_a_file_that_was_already_gone(lib):
    await _add(lib, "Gone.txt")
    (lib.folder / "extras" / "Gone.txt").unlink()

    await _route(lib.R.remove_my_rom_files)(_request(), 5)

    assert lib.rows.rows == []


@pytest.mark.asyncio
async def test_remove_my_files_holds_the_folder_where_it_is(lib, monkeypatch):
    """A title change moving the folder mid-way left the files where they
    were and their rows forgotten."""
    from handler.roms import game_folder

    seen = []
    real = lib.R._unlink_added

    def spy(path, folder):
        seen.append(game_folder.folder_moves.locked())
        return real(path, folder)

    await _add(lib, "Mine.txt")
    monkeypatch.setattr(lib.R, "_unlink_added", spy)

    await _route(lib.R.remove_my_rom_files)(_request(), 5)

    assert seen == [True], "pliki kasowane bez blokady przenoszenia folderu"


# ── What the page is told ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_each_listed_file_says_whether_its_bin_would_work(lib):
    await _add(lib, "Mine.txt")
    await _add(lib, "Theirs.txt", user_id=SOMEBODY)
    listed = [{"path": "extras/Mine.txt"}, {"path": "extras/Theirs.txt"}]

    await lib.R._mark_extras(_request(), lib.rom, listed)

    assert [e["can_delete"] for e in listed] == [True, False]


@pytest.mark.asyncio
async def test_a_row_whose_file_went_over_ftp_stops_counting(lib):
    await _add(lib, "Gone.txt")
    (lib.folder / "extras" / "Gone.txt").unlink()

    await lib.R._mark_extras(_request(), lib.rom, [])

    assert lib.rows.rows == [], "wiersz znikniętego pliku nadal liczy sie do limitu"


@pytest.mark.asyncio
async def test_a_folder_that_is_not_there_forgets_nobody(lib):
    """Storage gone offline, or the moment between a folder's rename and its
    rows catching up: every file reads as missing, and a page view forgot every
    charge for good (1.0.36 audit)."""
    await _add(lib, "Mine.txt")
    lib.folder.rename(lib.folder.with_name("Medievil (elsewhere)"))

    await lib.R._mark_extras(_request(), lib.rom, [])

    assert [r.rel_path for r in lib.rows.rows] == ["extras/Mine.txt"]


def test_the_page_marks_them():
    source = (Path(__file__).resolve().parent.parent / "endpoints" / "roms"
              / "roms_router.py").read_text(encoding="utf-8")
    page = source[source.index("async def get_rom("):]
    page = page[:page.index("\n@")]
    assert "_mark_extras(" in page
