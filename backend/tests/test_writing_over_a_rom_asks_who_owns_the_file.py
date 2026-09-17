"""Two ways round the gate that decides whether a name may be written over.

THE ALIAS. `PLATFORM_MAP` holds several keys for one platform - `psx` and
`playstation`, `snes` and `super-nintendo`, eighteen such groups in all - and
the upload route built its destination as `roms_base / slug` from whatever the
URL said. `_init_rom_dirs` deliberately makes only the canonical folder, and
`/roms/platforms/known` deliberately offers only the canonical slug, so
`<roms>/playstation/` is a directory that only an upload can bring into being.

It does not sit there quietly. The scan walks EVERY directory under the root and
upserts the platform by URL slug - "aliased fs_slugs reuse the existing row by
slug", as the scanner puts it - so both folders resolve to one platform row. A
ROM's identity is (platform, file name) with no uniqueness constraint, so the
same name arriving through the alias folder does not overwrite anybody's bytes:
it repoints THEIR row at MY file on the next scan. The ownership check never
ran, because in a folder of its own the name was not there yet.

THE MISSING ROW. `_may_replace` answered True whenever the database had no row,
and its only call site sits under `if dest_path.exists()`. So "no row" never
meant "nothing is here"; it meant "something is here that the library does not
know about". Subchannel files are always in that state - .sbi and .sub are
deliberately not ROM extensions, so no scan will ever give one a row - which
made somebody else's LibCrypt patch writable by anyone who knew its name, and
the test that was meant to cover this was called "a name that is not there yet
is nobody's" and asserted a case this route cannot reach.

A file on the shelf with no row is now nobody's to take, exactly as an unowned
ROW already was. A subchannel file is the one thing that can never have a row of
its own and is not orphaned either: it belongs to the disc it is named after, so
that disc's owner is asked about it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from handler.auth.scopes import Scope

ME = 7
SOMEBODY_ELSE = 9
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
ADMIN = UPLOADER | {Scope.ROMS_WRITE}
BUDGET = 4096


class _Upload:
    def __init__(self, filename: str, size: int = 16):
        self.filename = filename
        self._data = b"n" * size
        self._at = 0

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


@pytest.fixture
def route(tmp_path, monkeypatch):
    """The upload route with a real ROM tree and a database of my own making."""
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    rows: dict[str, object] = {}

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return BUDGET

    async def nothing(*a, **k):
        return None

    async def clam_off():
        return False

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="playstation", fs_slug="psx")

    async def by_fs_name(_platform_id, fs_name):
        row = rows.get(fs_name)
        # A real row always names its folder, and a replacement has to be the
        # file in THAT folder (test_a_second_copy_of_your_own_rom_is_not_free).
        # These rows are the files on the psx shelf.
        if row is not None and not getattr(row, "fs_path", None):
            row.fs_path = str(tmp_path / "psx")
        return row

    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", by_fs_name)

    async def newest_rom_id():
        return 0

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)

    async def no_live_limit(_user, **_k):
        # The budget here is the ceiling above. Uploads running side by side
        # are checked live as well, and that has its own tests
        # (test_uploads_running_side_by_side_see_each_other).
        return quota.Reservation(None, limit=0)

    monkeypatch.setattr(quota, "reservation_for", no_live_limit)
    monkeypatch.setattr(rsh, "scan_after_write", nothing)
    monkeypatch.setattr(R, "_stamp_uploaded", nothing)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    return R, tmp_path, rows


def _request(scopes=UPLOADER, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


async def _upload(R, files, *, slug="psx", scopes=UPLOADER, user_id=ME):
    tasks = BackgroundTasks()
    return await R.upload_roms(_request(scopes, user_id), slug=slug,
                               background_tasks=tasks, files=files)


def _row(fs_name, owner):
    return SimpleNamespace(id=abs(hash(fs_name)) % 1000, fs_name=fs_name,
                           published_by=owner)


# ── The alias shelf ──────────────────────────────────────────────────────────

def test_the_map_really_holds_two_names_for_one_shelf():
    """A guard on the test. If these ever stopped colliding, everything below
    would pass while measuring nothing."""
    from handler.metadata.rom_platform_map import PLATFORM_MAP, slug_from_fs_slug

    assert "psx" in PLATFORM_MAP and "playstation" in PLATFORM_MAP
    assert slug_from_fs_slug("psx") == slug_from_fs_slug("playstation"), (
        "test nie odtwarza mapy platform - te dwie slugi nie wskazuja juz "
        "jednej polki"
    )


def test_every_alias_resolves_to_one_canonical_shelf():
    """The rule `_init_rom_dirs` already applies when it makes the folders, said
    once so the upload route and the folder maker cannot drift apart."""
    from handler.metadata.rom_platform_map import (
        PLATFORM_MAP, canonical_fs_slug, slug_from_fs_slug,
    )

    for fs_slug in PLATFORM_MAP:
        canonical = canonical_fs_slug(fs_slug)
        assert canonical in PLATFORM_MAP
        assert slug_from_fs_slug(canonical) == slug_from_fs_slug(fs_slug), (
            f"{fs_slug} zostal skanonizowany do INNEJ platformy: {canonical}"
        )
    assert canonical_fs_slug("playstation") == "psx"
    assert canonical_fs_slug("super-nintendo") == "snes"
    assert canonical_fs_slug("psx") == "psx", "kanoniczna sluga ma zostac soba"


@pytest.mark.asyncio
async def test_an_alias_slug_writes_to_the_canonical_shelf(route):
    R, tmp_path, _rows = route

    out = await _upload(R, [_Upload("Game.iso")], slug="playstation")

    assert out["saved"] == ["Game.iso"]
    assert (tmp_path / "psx" / "Game.iso").is_file(), (
        "wgranie przez sluge aliasowa nie trafilo na polke platformy"
    )
    assert not (tmp_path / "playstation").exists(), (
        "sluga aliasowa zaklada DRUGI katalog tej samej platformy - skaner "
        "chodzi po kazdym katalogu i upsertuje po slugu URL, wiec plik o tej "
        "samej nazwie przepnie cudzy wiersz na siebie, nie dotykajac jego bajtow"
    )


@pytest.mark.asyncio
async def test_the_alias_route_still_asks_who_owns_what_is_there(route):
    """The point of the redirect. Once both slugs land in one folder, the
    ownership check sees the file that is already there."""
    R, tmp_path, rows = route
    (tmp_path / "psx").mkdir(parents=True)
    (tmp_path / "psx" / "Game.iso").write_bytes(b"THEIRS")
    rows["Game.iso"] = _row("Game.iso", SOMEBODY_ELSE)

    out = await _upload(R, [_Upload("Game.iso")], slug="playstation")

    assert out["saved"] == []
    assert [r["action"] for r in out["rejected"]] == ["already_here"]
    assert (tmp_path / "psx" / "Game.iso").read_bytes() == b"THEIRS"


# ── A file on the shelf that the library has no row for ──────────────────────

@pytest.mark.asyncio
async def test_a_file_with_no_row_is_not_free_to_overwrite(route):
    R, tmp_path, _rows = route
    (tmp_path / "psx").mkdir(parents=True)
    (tmp_path / "psx" / "Game.iso").write_bytes(b"THEIRS")

    out = await _upload(R, [_Upload("Game.iso")])

    assert out["saved"] == [], (
        "plik lezacy na polce bez wiersza w bazie jest traktowany jak niczyj, "
        "a wywolanie siedzi pod `if dest_path.exists()` - wiec brak wiersza "
        "nigdy nie znaczy 'nic tu nie ma'"
    )
    assert (tmp_path / "psx" / "Game.iso").read_bytes() == b"THEIRS"


@pytest.mark.asyncio
async def test_an_administrator_may_still_write_over_it(route):
    """The way back. Somebody has to be able to tidy up a shelf whose files the
    library never catalogued, and it is the same permission the rest of the ROM
    API treats as administrative."""
    R, tmp_path, _rows = route
    (tmp_path / "psx").mkdir(parents=True)
    (tmp_path / "psx" / "Game.iso").write_bytes(b"OLD")

    out = await _upload(R, [_Upload("Game.iso")], scopes=ADMIN, user_id=1)

    assert out["saved"] == ["Game.iso"]
    assert (tmp_path / "psx" / "Game.iso").read_bytes() == b"n" * 16


# ── Subchannel files, which can never have a row of their own ────────────────

@pytest.mark.asyncio
async def test_a_subchannel_file_belongs_to_the_disc_it_names(route):
    """`.sbi` is 452 bytes that a PAL PlayStation disc needs to boot. It never
    gets a row, so the name check can never protect it, and the ownership check
    read "no row" as "nobody's"."""
    R, tmp_path, rows = route
    shelf = tmp_path / "psx"
    shelf.mkdir(parents=True)
    (shelf / "Victim (Disc 1).cue").write_bytes(b"disc")
    (shelf / "Victim (Disc 1).sbi").write_bytes(b"THEIR PATCH")
    rows["Victim (Disc 1).cue"] = _row("Victim (Disc 1).cue", SOMEBODY_ELSE)

    out = await _upload(R, [_Upload("Victim (Disc 1).sbi")])

    assert out["saved"] == [], (
        "cudzy plik podkanalu da sie nadpisac, znajac sama nazwe"
    )
    assert (shelf / "Victim (Disc 1).sbi").read_bytes() == b"THEIR PATCH"


@pytest.mark.asyncio
async def test_i_may_replace_the_subchannel_file_of_my_own_disc(route):
    """The legal case, and the reason the gate was opened to these files at all:
    a LibCrypt patch is something a person swaps for a better one."""
    R, tmp_path, rows = route
    shelf = tmp_path / "psx"
    shelf.mkdir(parents=True)
    (shelf / "Mine (Disc 1).cue").write_bytes(b"disc")
    (shelf / "Mine (Disc 1).sbi").write_bytes(b"OLD PATCH")
    rows["Mine (Disc 1).cue"] = _row("Mine (Disc 1).cue", ME)

    out = await _upload(R, [_Upload("Mine (Disc 1).sbi")])

    assert out["saved"] == ["Mine (Disc 1).sbi"], (
        "wlasciciel plyty nie moze podmienic jej wlasnego pliku podkanalu"
    )
    assert (shelf / "Mine (Disc 1).sbi").read_bytes() == b"n" * 16


@pytest.mark.asyncio
async def test_a_first_subchannel_file_still_lands(route):
    """Nothing to replace, so nothing to ask about. This is the ordinary case
    the gate was opened for and it must not have been closed again."""
    R, tmp_path, rows = route
    shelf = tmp_path / "psx"
    shelf.mkdir(parents=True)
    (shelf / "Mine (Disc 1).cue").write_bytes(b"disc")
    rows["Mine (Disc 1).cue"] = _row("Mine (Disc 1).cue", ME)

    out = await _upload(R, [_Upload("Mine (Disc 1).sbi")])

    assert out["saved"] == ["Mine (Disc 1).sbi"]
    assert (shelf / "Mine (Disc 1).sbi").is_file()


# ── ...and the ordinary uploads still work ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_new_name_still_lands(route):
    R, tmp_path, _rows = route
    out = await _upload(R, [_Upload("Fresh.iso")])
    assert out["saved"] == ["Fresh.iso"]


@pytest.mark.asyncio
async def test_replacing_my_own_rom_still_works(route):
    R, tmp_path, rows = route
    (tmp_path / "psx").mkdir(parents=True)
    (tmp_path / "psx" / "Game.iso").write_bytes(b"MY OLD DUMP")
    rows["Game.iso"] = _row("Game.iso", ME)

    out = await _upload(R, [_Upload("Game.iso")])

    assert out["saved"] == ["Game.iso"]
    assert (tmp_path / "psx" / "Game.iso").read_bytes() == b"n" * 16
