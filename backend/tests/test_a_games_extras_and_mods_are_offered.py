"""What a game keeps in its folder's extras/ and mods/, offered on its page.

The owner's decision (2026-09-19): a ROM shows the files beside it the way a
GOG or custom game shows its extras - a list with what each file is (GAME,
EXTRA, MOD) and its size, and a download picker that ticks the game and offers
the rest. They are put there over FTP, subfolders included, so the list is read
off the disk rather than out of the database.

Three rules follow from the folder being one people write to over FTP:

  * only files, and only inside extras/ or mods/. A hidden file, a transfer that
    has not finished (.part) and a link pointing out of the folder are not
    offered, and a path that walks out of those two folders is not served;
  * the ticket names the file it was issued for, so it cannot be presented for
    a different one - a download of the game is not a pass to the extras, and
    one extra is not a pass to another;
  * a game lying loose on a shared shelf has no folder of its own, so its only
    extra is its manual, named after it in the shared extras/.

And the owner's decision D: deleting a game with its files takes its extras and
mods too, listed in the warning first - unless another game shares the folder,
because then they are not only this game's.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from handler.roms import game_extras


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def game(tmp_path):
    """A game with a folder of its own, and a few things beside it."""
    folder = tmp_path / "psx" / "Final Fantasy IX"
    _write(folder / "ff9 (Disc 1).chd", b"disc")
    _write(folder / "extras" / "Manual.pdf", b"%PDF-manual")
    _write(folder / "extras" / "Maps" / "world.png", b"png" * 10)
    _write(folder / "mods" / "widescreen.ips", b"ips")
    _write(folder / "mods" / ".DS_Store", b"junk")
    _write(folder / "extras" / "soundtrack.zip.part", b"half")
    outside = _write(tmp_path / "secret.txt", b"not yours")
    try:
        os.symlink(outside, folder / "extras" / "link.txt")
    except (OSError, NotImplementedError):
        pass
    rom = SimpleNamespace(id=5, fs_path=str(folder), fs_name="ff9 (Disc 1).chd",
                          manual_path="extras/Manual.pdf", name="Final Fantasy IX")
    return SimpleNamespace(rom=rom, folder=folder, base=str(tmp_path), slug="psx")


def _listed(g):
    return game_extras.extras_of(g.rom, library_root=g.base, fs_slug=g.slug)


# ── What is offered ─────────────────────────────────────────────────────────


def test_the_extras_and_mods_beside_a_game_are_listed(game):
    got = _listed(game)

    assert [(f["kind"], f["path"], f["name"]) for f in got] == [
        ("extra", "extras/Manual.pdf", "Manual.pdf"),
        ("extra", "extras/Maps/world.png", "Maps/world.png"),
        ("mod", "mods/widescreen.ips", "widescreen.ips"),
    ], "lista pokazuje cos, czego nie powinna, albo czegos brakuje"
    assert got[1]["size"] == 30


def test_a_loose_game_offers_only_its_own_manual(tmp_path):
    shelf = tmp_path / "psx"
    _write(shelf / "crash.chd")
    _write(shelf / "extras" / "Crash Bandicoot - Manual.pdf", b"%PDF-c")
    _write(shelf / "extras" / "Spyro - Manual.pdf", b"%PDF-s")
    _write(shelf / "mods" / "somebodys.ips")
    rom = SimpleNamespace(id=1, fs_path=str(shelf), fs_name="crash.chd",
                          manual_path="extras/Crash Bandicoot - Manual.pdf", name="Crash")

    got = game_extras.extras_of(rom, library_root=str(tmp_path), fs_slug="psx")

    assert [f["path"] for f in got] == ["extras/Crash Bandicoot - Manual.pdf"]


def test_a_game_with_nothing_beside_it_offers_nothing(tmp_path):
    folder = tmp_path / "psx" / "Crash"
    _write(folder / "crash.chd")
    rom = SimpleNamespace(id=1, fs_path=str(folder), fs_name="crash.chd",
                          manual_path=None, name="Crash")

    assert game_extras.extras_of(rom, library_root=str(tmp_path), fs_slug="psx") == []


# ── What is served ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "extras/../ff9 (Disc 1).chd",
    "mods/../../secret.txt",
    "ff9 (Disc 1).chd",
    "extras/link.txt",
    "extras/soundtrack.zip.part",
    "mods/.DS_Store",
    "/etc/passwd",
    "extras",
])
def test_only_a_listed_file_is_served(game, path):
    assert game_extras.extra_path(game.rom, path, library_root=game.base,
                                  fs_slug=game.slug) is None


def test_a_listed_file_is_served(game):
    assert game_extras.extra_path(game.rom, "extras/Maps/world.png", library_root=game.base,
                                  fs_slug=game.slug) == game.folder / "extras" / "Maps" / "world.png"


# ── Going with the game ─────────────────────────────────────────────────────


def test_deleting_the_game_takes_its_extras_and_mods(game):
    """Everything in them, the hidden and the unfinished included: what is left
    behind is what keeps an emptied folder on the disk for good."""
    got = game_extras.removable_extras(game.rom, library_root=game.base, fs_slug=game.slug,
                                       folder_shared=False)

    names = {p.relative_to(game.folder).as_posix() for p in got}
    assert names == {"extras/Manual.pdf", "extras/Maps/world.png", "mods/widescreen.ips",
                     "mods/.DS_Store", "extras/soundtrack.zip.part"}
    assert all(game.folder in p.parents for p in got), "kasowanie wychodzi poza folder gry"


def test_a_link_in_there_is_never_followed_by_the_delete(game, tmp_path):
    """Deleting resolves a path before it unlinks it. A link in mods/ to
    another game's ROM would otherwise take that game's file."""
    other = _write(tmp_path / "psx" / "Other Game" / "other.chd", b"somebody's game")
    try:
        os.symlink(other, game.folder / "mods" / "shortcut.chd")
        os.symlink(other.parent, game.folder / "mods" / "whole-folder")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks on this filesystem")

    got = game_extras.removable_extras(game.rom, library_root=game.base, fs_slug=game.slug,
                                       folder_shared=False)

    assert not any(p.resolve() == other.resolve() for p in got), (
        "kasowanie gry siegneloby po plik innej gry przez dowiazanie"
    )


def test_a_folder_another_game_shares_keeps_its_extras(game):
    assert game_extras.removable_extras(game.rom, library_root=game.base, fs_slug=game.slug,
                                        folder_shared=True) == []


def test_a_loose_game_takes_only_its_own_manual(tmp_path):
    shelf = tmp_path / "psx"
    _write(shelf / "extras" / "Crash Bandicoot - Manual.pdf")
    _write(shelf / "extras" / "Spyro - Manual.pdf")
    rom = SimpleNamespace(id=1, fs_path=str(shelf), fs_name="crash.chd",
                          manual_path="extras/Crash Bandicoot - Manual.pdf", name="Crash")

    got = game_extras.removable_extras(rom, library_root=str(tmp_path), fs_slug="psx",
                                       folder_shared=True)

    assert got == [shelf / "extras" / "Crash Bandicoot - Manual.pdf"]


@pytest.mark.asyncio
async def test_another_game_in_the_folder_is_counted(tmp_path):
    """Whether the folder is shared is asked of the database: two games put in
    one folder over FTP are two rows there."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from handler.database.rom_handler import rom_handler
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
        for rid, folder, name in ((1, "/l/psx/FF9", "d1.chd"), (2, "/l/psx/FF9", "d2.chd"),
                                  (3, "/l/psx/FF9", "other.chd"), (4, "/l/psx/Crash", "c.chd")):
            db.add(Rom(id=rid, platform_id=1, name=name, fs_name=name, fs_name_no_ext=name,
                       fs_extension="chd", fs_path=folder, fs_size_bytes=1))
        await db.commit()

        shared = await rom_handler.rows_in_folder_besides(1, "/l/psx/FF9", [1, 2], session=db)
        alone = await rom_handler.rows_in_folder_besides(1, "/l/psx/Crash", [4], session=db)
    await engine.dispose()

    assert (shared, alone) == (1, 0)


@pytest.mark.asyncio
async def test_what_goes_with_a_deleted_game_is_worked_out_in_one_place(game, monkeypatch):
    from endpoints.roms import roms_router as R

    async def platform(_pid, **_k):
        return SimpleNamespace(fs_slug="psx")

    async def nobody_else(*_a, **_k):
        return 0

    async def roms_path():
        return game.base

    monkeypatch.setattr(R.rom_platform_handler, "get_by_id", platform)
    monkeypatch.setattr(R.rom_handler, "rows_in_folder_besides", nobody_else)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    disc2 = SimpleNamespace(id=6, platform_id=1, fs_path=game.rom.fs_path, manual_path=None)
    disc1 = SimpleNamespace(**vars(game.rom), platform_id=1)

    got = await R._extras_going_with([disc2, disc1])

    assert "extras/Manual.pdf" in {p.relative_to(game.folder).as_posix() for p in got}


@pytest.mark.asyncio
async def test_the_warning_names_the_extras_apart_from_the_disc_files(game, monkeypatch):
    """The warning said "the N data files the disc sheets name go with it" of
    everything in `files`, and the extras went into that list too: a game with
    a manual and two mods was said to have three data files behind its discs.
    Decision D deletes them only after a warning, so it has to say what they are."""
    from endpoints.roms import roms_router as R

    disc = SimpleNamespace(**vars(game.rom), platform_id=1, track_of=None, disk_number=1)
    folder = game.folder

    async def one(_rom_id):
        return disc

    async def the_set(_rom_id):
        return [disc]

    async def nothing(*_a, **_k):
        return []

    async def tracks(_members):
        return [folder / "ff9 (Disc 1) (Track 2).bin"]

    async def extras(_members):
        return [folder / "extras" / "Manual.pdf", folder / "mods" / "widescreen.ips"]

    monkeypatch.setattr(R.rom_handler, "get_by_id", one)
    monkeypatch.setattr(R.rom_handler, "disk_set", the_set)
    monkeypatch.setattr(R, "assert_can_delete_rom_set", lambda *a, **k: None)
    monkeypatch.setattr(R.save_state_handler, "list_states_for_rom", nothing)
    monkeypatch.setattr(R.save_state_handler, "list_saves_for_rom", nothing)
    monkeypatch.setattr(R.rom_removal, "spoken_for_elsewhere", lambda *a, **k: set())
    monkeypatch.setattr(R, "removable_tracks", tracks)
    monkeypatch.setattr(R, "_playlists_naming", lambda *a, **k: [])
    monkeypatch.setattr(R, "subchannel_files_for", lambda *a, **k: [])
    monkeypatch.setattr(R, "_extras_going_with", extras)

    out = await _route(R.rom_removal_preview)(_request(), rom_id=5)

    assert out["files"] == ["ff9 (Disc 1) (Track 2).bin"], "dodatki policzone jako pliki plyt"
    assert out["extras"] == ["extras/Manual.pdf", "mods/widescreen.ips"]


def test_the_warning_and_the_delete_both_ask_it():
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "endpoints" / "roms"
              / "roms_router.py").read_text(encoding="utf-8")
    preview = source[source.index("async def rom_removal_preview("):]
    preview = preview[:preview.index("\n@")]
    delete = source[source.index("async def delete_rom("):]
    delete = delete[:delete.index("\nasync def ")]
    assert "_extras_going_with(" in preview, "okno kasowania nie wymienia dodatkow i modow"
    assert "_extras_going_with(" in delete, "kasowanie z plikami zostawia dodatki i mody"


# ── The routes ──────────────────────────────────────────────────────────────


@pytest.fixture
def routes(game, monkeypatch):
    from endpoints.roms import roms_router as R

    row = SimpleNamespace(**vars(game.rom), platform=SimpleNamespace(fs_slug="psx"),
                          platform_id=1)

    async def with_platform(rom_id, **_k):
        return row if rom_id == 5 else None

    async def roms_path():
        return game.base

    monkeypatch.setattr(R.rom_handler, "get_with_platform", with_platform)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    return SimpleNamespace(R=R, game=game)


def _request(user_id=1):
    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=user_id)))


def _route(fn):
    return getattr(fn, "__wrapped__", fn)


def _ticket(url: str):
    """(user, expires, sig, path) out of the link a ticket route hands back."""
    from urllib.parse import parse_qs, urlsplit

    parts = urlsplit(url)
    user, expires, sig = parts.path.split("/extra/")[1].split("/")
    return int(user), int(expires), sig, parse_qs(parts.query)["path"][0]


@pytest.mark.asyncio
async def test_a_ticket_downloads_the_file_it_names(routes):
    R = routes.R
    body = R.ExtraTicketBody(path="mods/widescreen.ips")

    out = await _route(R.rom_extra_ticket)(_request(), 5, body)
    user, expires, sig, path = _ticket(out["url"])
    response = await R.rom_extra_with_ticket(5, user, expires, sig, path=path)

    assert path == "mods/widescreen.ips"
    assert Path(response.path) == routes.game.folder / "mods" / "widescreen.ips"
    assert response.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_a_ticket_for_one_file_does_not_open_another(routes):
    from fastapi import HTTPException

    R = routes.R
    out = await _route(R.rom_extra_ticket)(_request(), 5, R.ExtraTicketBody(path="extras/Manual.pdf"))
    user, expires, sig, _path = _ticket(out["url"])

    with pytest.raises(HTTPException) as refused:
        await R.rom_extra_with_ticket(5, user, expires, sig, path="mods/widescreen.ips")
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_a_download_ticket_is_not_a_pass_to_the_extras(routes):
    from fastapi import HTTPException

    from utils import download_tickets

    expires, sig = download_tickets.issue(5, 1)
    with pytest.raises(HTTPException) as refused:
        await routes.R.rom_extra_with_ticket(5, 1, expires, sig, path="extras/Manual.pdf")
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_no_ticket_is_issued_for_a_file_that_is_not_offered(routes):
    from fastapi import HTTPException

    R = routes.R
    with pytest.raises(HTTPException) as refused:
        await _route(R.rom_extra_ticket)(_request(), 5, R.ExtraTicketBody(path="extras/../ff9 (Disc 1).chd"))
    assert refused.value.status_code == 404
