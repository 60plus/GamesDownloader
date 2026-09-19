"""Removing a ROM removes the whole set, so the whole set is what gets asked about.

`DELETE /roms/{id}` expands the row it is given into its disk set - every disc
of the title, every track file of every disc - and then deletes the rows, the
media, the ROM files and, for each of them, *every account's* savestates and
memory cards.

The ownership check asked about `disks[0]`, with a comment saying that was "the
row the caller named". It is not: `disk_set` re-queries the group ordered by
disc number, so `disks[0]` is the lowest-numbered disc whichever one was asked
for. An uploader who fetched disc 1 was therefore allowed to delete disc 2, and
disc 3, and the saves of everyone who had ever played them, by naming their own
disc.

Two halves are tested here, because a guard that refuses everything would pass
half of them: the set that must be refused, and the ordinary set that must
still go through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope
from handler.library.ownership import can_delete_rom_set

UPLOADER_ID = 7
SOMEBODY_ELSE = 9

UPLOADER_SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
ADMIN_SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ, Scope.ROMS_WRITE}


@dataclass
class _Rom:
    """The three fields the deletion path reads off a row."""
    id: int = 1
    fs_name: str = "Game (Disc 1).cue"
    published_by: int | None = UPLOADER_ID
    platform_id: int = 1
    fs_path: str = "psx"
    track_of: str | None = None
    disk_group: str | None = "game"


# ── the rule ──────────────────────────────────────────────────────────────────

def test_an_uploader_may_not_take_a_disc_somebody_else_fetched():
    """The defect, stated as a rule. Disc 1 is theirs, disc 2 is not, and
    deleting the set takes both."""
    mine = _Rom(id=1, published_by=UPLOADER_ID)
    theirs = _Rom(id=2, fs_name="Game (Disc 2).cue", published_by=SOMEBODY_ELSE)
    assert not can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, mine, [mine, theirs])


def test_naming_their_own_disc_does_not_change_the_answer():
    """The same set asked about from the other end. `disk_set` sorts, so this is
    the call that used to be allowed no matter which disc was named."""
    mine = _Rom(id=2, fs_name="Game (Disc 2).cue", published_by=UPLOADER_ID)
    theirs = _Rom(id=1, published_by=SOMEBODY_ELSE)
    assert not can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, mine, [theirs, mine])


def test_an_unowned_track_goes_with_the_sheet_that_owns_it():
    """Ownership is stamped on the file that was fetched, one row at a time
    (rom_source_handler._register_and_scrape). The .bin behind an uploaded .cue
    normally has no owner at all, and refusing that would stop an uploader
    removing their own upload - which is the entire reason this route is open to
    them."""
    sheet = _Rom(id=1, published_by=UPLOADER_ID)
    track = _Rom(id=2, fs_name="Game (Disc 1).bin", published_by=None,
                 track_of="Game (Disc 1).cue", disk_group=None)
    assert can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, sheet, [sheet, track])


def test_the_row_the_caller_named_still_decides():
    """An unowned ROM is nobody's, and an uploader does not get one by asking
    about it beside a disc that is theirs."""
    nobodys = _Rom(id=1, published_by=None)
    mine = _Rom(id=2, fs_name="Game (Disc 2).cue", published_by=UPLOADER_ID)
    assert not can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, nobodys, [nobodys, mine])


def test_an_admin_may_delete_a_set_several_people_fetched():
    """Nothing here narrows what an administrator could already do."""
    one = _Rom(id=1, published_by=UPLOADER_ID)
    two = _Rom(id=2, fs_name="Game (Disc 2).cue", published_by=SOMEBODY_ELSE)
    assert can_delete_rom_set(ADMIN_SCOPES, 1, one, [one, two])


def test_a_plain_account_is_refused_its_own_set():
    """The scope half of the rule is not skipped by the set half."""
    mine = _Rom(id=1, published_by=UPLOADER_ID)
    assert not can_delete_rom_set({Scope.ROMS_READ}, UPLOADER_ID, mine, [mine])


# ── the route ─────────────────────────────────────────────────────────────────
#
# A rule nothing asks is not a rule. These drive the handler itself.

@dataclass
class _Handlers:
    """The three handler calls the deletion path makes before it starts
    deleting, plus a record of what it deleted."""
    rows: list = field(default_factory=list)
    deleted: list = field(default_factory=list)

    async def get_by_id(self, rom_id):
        return next((r for r in self.rows if r.id == rom_id), None)

    async def disk_set(self, rom_id):
        return list(self.rows)

    async def delete(self, rom_id):
        self.deleted.append(rom_id)
        return True


def _request(scopes, user_id):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


@pytest.fixture
def route(monkeypatch):
    """The real handler, with the database and the disk stubbed out.

    Everything stubbed here happens *after* the ownership check, so a test that
    reaches it has proved the check let the call through.
    """
    from endpoints.roms import roms_router as R

    handlers = _Handlers()
    monkeypatch.setattr(R.rom_handler, "get_by_id", handlers.get_by_id)
    monkeypatch.setattr(R.rom_handler, "disk_set", handlers.disk_set)
    monkeypatch.setattr(R.rom_handler, "delete", handlers.delete)

    async def _platform(_pid):
        return SimpleNamespace(slug="psx")

    async def _none(_rom_id):
        return []

    monkeypatch.setattr(R.rom_platform_handler, "get_by_id", _platform)
    monkeypatch.setattr(R.save_state_handler, "list_states_for_rom", _none)
    monkeypatch.setattr(R.save_state_handler, "list_saves_for_rom", _none)
    monkeypatch.setattr(R.rom_removal, "delete_save_files", lambda *a, **k: 0)
    monkeypatch.setattr(R.rom_removal, "delete_media_dir", lambda *a, **k: False)
    monkeypatch.setattr(R.rom_removal, "spoken_for_elsewhere", lambda *a, **k: set())

    # No other game in the folder unless a test says so.
    handlers.survivor = None
    handlers.handed = []

    async def _another(_fs_path, _exclude, **_k):
        return handlers.survivor

    async def _hand_to(from_ids, to_id, **_k):
        handlers.handed.append((sorted(from_ids), to_id))
        return 0

    monkeypatch.setattr(R.rom_handler, "another_in_folder", _another)
    monkeypatch.setattr(R.rom_added_file_handler, "hand_to", _hand_to)

    # The files that go with a set, and the file of each disc: an uploader's
    # delete always takes them (the owner, 2026-09-19), so every route test
    # reaches this part. Recorded, never touching a disk.
    handlers.taken = []

    async def _nothing(*_a, **_k):
        return []

    monkeypatch.setattr(R, "removable_tracks", _nothing)
    monkeypatch.setattr(R, "_extras_going_with", _nothing)
    monkeypatch.setattr(R, "_playlists_naming", lambda *a, **k: [])
    monkeypatch.setattr(R, "subchannel_files_for", lambda *a, **k: [])
    monkeypatch.setattr(R.rom_removal, "delete_rom_file",
                        lambda disk, **_k: handlers.taken.append(disk.id) or True)
    return R, handlers


@pytest.mark.asyncio
async def test_files_added_to_a_game_that_shares_its_folder_stay_counted(route):
    """In a folder two games share, the extras and mods are the folder's and
    stay when one game goes. Their rows went with the game's row (ON DELETE
    CASCADE), so the bytes stayed on the disk and counted against nobody, and
    the account that added them could no longer remove them (1.0.36 audit).
    They go to the game that stays."""
    R, handlers = route
    handlers.rows = [_Rom(id=1, published_by=UPLOADER_ID, disk_group=None)]
    handlers.survivor = 40

    await R.delete_rom(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)

    assert handlers.handed == [([1], 40)]
    assert handlers.deleted == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("scopes,uid,files_go", [
    (UPLOADER_SCOPES, UPLOADER_ID, True),
    (ADMIN_SCOPES, 1, False),
], ids=["uploader", "admin"])
async def test_an_uploader_removing_a_rom_always_takes_its_files(route, scopes, uid, files_go):
    """The owner, 2026-09-19: an uploader's delete takes the file too, and only
    an administrator may keep it. Removed with the file kept, the ROM stopped
    counting against the uploader while it stayed on the disk, and the next
    scan brought it back owned by nobody (1.0.36 audit)."""
    R, handlers = route
    handlers.rows = [_Rom(id=1, published_by=UPLOADER_ID, disk_group=None)]

    await R.delete_rom(_request(scopes, uid), rom_id=1, delete_files=False)

    assert bool(handlers.taken) is files_go
    assert handlers.deleted == [1]


@pytest.mark.asyncio
async def test_a_row_removed_in_bulk_hands_its_added_files_on_too(route):
    """Removing missing rows and applying exclusions delete one row at a time
    through _take_the_bytes_too, and the same cascade takes the added-file rows."""
    R, handlers = route
    handlers.rows = [_Rom(id=5, fs_path="/l/psx/Hacks", disk_group=None)]
    handlers.survivor = 6

    await R._take_the_bytes_too(5, "psx")

    assert handlers.handed == [([5], 6)]


@pytest.mark.asyncio
async def test_a_game_alone_in_its_folder_hands_nothing_on(route):
    R, handlers = route
    handlers.rows = [_Rom(id=1, published_by=UPLOADER_ID, disk_group=None)]

    await R.delete_rom(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)

    assert handlers.handed == []


@pytest.mark.asyncio
async def test_the_route_refuses_a_set_holding_somebody_elses_disc(route):
    R, handlers = route
    handlers.rows = [
        _Rom(id=1, published_by=UPLOADER_ID),
        _Rom(id=2, fs_name="Game (Disc 2).cue", published_by=SOMEBODY_ELSE),
    ]

    with pytest.raises(HTTPException) as raised:
        await R.delete_rom(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)

    assert raised.value.status_code == 403
    assert handlers.deleted == [], "odmowa, a wiersze i tak znikly"


@pytest.mark.asyncio
async def test_the_route_still_deletes_an_ordinary_set(route):
    """The other half. A guard that refused everything would pass the test
    above and break the feature."""
    R, handlers = route
    handlers.rows = [
        _Rom(id=1, published_by=UPLOADER_ID),
        _Rom(id=2, fs_name="Game (Disc 1).bin", published_by=None,
             track_of="Game (Disc 1).cue", disk_group=None),
    ]

    out = await R.delete_rom(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)

    assert out["ok"] is True
    assert handlers.deleted == [1, 2]


@pytest.mark.asyncio
async def test_a_missing_rom_is_still_a_404(route):
    R, handlers = route
    handlers.rows = []
    with pytest.raises(HTTPException) as raised:
        await R.delete_rom(_request(ADMIN_SCOPES, 1), rom_id=99)
    assert raised.value.status_code == 404


# ── An unowned member is not always harmless ─────────────────────────────────
#
# The rule waved every unowned member through, reasoning that ownership is
# stamped on the file that was fetched, so the .bin behind an uploaded .cue has
# none and refusing it would stop an uploader removing their own upload.
#
# True of a TRACK FILE, which belongs to its sheet and has no life of its own.
# Not true of a DISC. A set scanned in long ago carries no owner and carries
# everybody's saves; an uploader who adds the one disc that was missing would
# then delete the other three - and their savestates - by removing their own.

def test_an_unowned_track_still_goes_with_the_sheet(): 
    """The case the rule was written for, unchanged."""
    sheet = _Rom(id=1, published_by=UPLOADER_ID)
    track = _Rom(id=2, fs_name="Game (Disc 1).bin", published_by=None,
                 track_of="Game (Disc 1).cue", disk_group=None)
    assert can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, sheet, [sheet, track])


def test_an_unowned_disc_does_not():
    """Discs 1-3 scanned in years ago, with other people's saves on them. The
    uploader adds the missing disc 4 and then removes it."""
    mine = _Rom(id=4, fs_name="FF IX (Disc 4).chd", published_by=UPLOADER_ID)
    theirs = [_Rom(id=n, fs_name=f"FF IX (Disc {n}).chd", published_by=None)
              for n in (1, 2, 3)]
    assert not can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, mine, [mine, *theirs]), (
        "uploader zabiera trzy cudze plyty i zapisy graczy, kasujac swoja jedna"
    )


def test_an_administrator_may_still_remove_such_a_set():
    """Somebody has to be able to clear one up."""
    mine = _Rom(id=4, published_by=UPLOADER_ID)
    theirs = _Rom(id=1, published_by=None)
    assert can_delete_rom_set(ADMIN_SCOPES, 1, mine, [mine, theirs])


def test_a_set_the_uploader_brought_in_whole_is_still_theirs():
    """Every disc stamped to them, plus the track files that carry no stamp."""
    discs = [_Rom(id=n, fs_name=f"Game (Disc {n}).cue", published_by=UPLOADER_ID)
             for n in (1, 2)]
    tracks = [_Rom(id=10 + n, fs_name=f"Game (Disc {n}).bin", published_by=None,
                   track_of=f"Game (Disc {n}).cue", disk_group=None)
              for n in (1, 2)]
    assert can_delete_rom_set(UPLOADER_SCOPES, UPLOADER_ID, discs[0], discs + tracks)
