"""A file arriving for a game already in the library goes into that game's folder.

Found on 2026-09-18, after the owner's library had moved into folders named after
titles. A download worked out its folder from the file name alone, which is all
a download knows when it starts - and once a game lived in `Final Fantasy IX`,
that stopped being where its files were:

  * the next disc, `Final Fantasy IX (Europe) (Disc 2).chd`, went into a new
    folder `Final Fantasy IX (Europe)`. Two folders are two games, and the
    player cannot switch to a disc in the other one;
  * the "already have it" check looked in the folder named after the file, did
    not find the file sitting in the title's folder, and downloaded it again.

So a file now asks where its game already is: the same file, or another disc of
the same title, on either shelf of the platform or in a game's folder on one.
Only a game the library does not have yet gets a folder named after the file,
which is where its title finds it later.

And the answer is taken when the transfer STARTS, not when it is queued. Four
discs queued together all asked while none of them was here; disc 1 then
landed, was scraped, and its folder took the title - and disc 2, still waiting
in the queue with its answer from before, wrote into a folder of the old name.
Choosing the folder and renaming one hold the same lock, and the choice leaves
its .part behind before letting go, so a rename that comes second sees a
transfer in progress and waits for the last disc.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.roms import game_folder
from handler.roms import rom_source_handler as rsh
from handler.roms.game_folder import choose_home, home_for
from models.rom import Rom
from models.rom_platform import RomPlatform

FF9 = "Final Fantasy IX (Europe) (Disc {n}).chd"


def _rows(*pairs):
    return [(name, str(folder)) for name, folder in pairs]


# ── Where a game already is ─────────────────────────────────────────────────


def test_the_same_file_is_found_in_its_titles_folder(tmp_path):
    psx = tmp_path / "psx"
    title = psx / "Final Fantasy IX"

    got = choose_home(FF9.format(n=1), _rows((FF9.format(n=1), title)), psx)

    assert got == title, "plik, ktory juz jest, nie zostal znaleziony w folderze tytulu"


def test_the_next_disc_joins_the_ones_already_here(tmp_path):
    psx = tmp_path / "psx"
    title = psx / "Final Fantasy IX"

    got = choose_home(FF9.format(n=3), _rows(
        (FF9.format(n=1), title), (FF9.format(n=2), title)), psx)

    assert got == title, "kolejna plyta laduje w osobnym folderze, zestaw sie rozpada"


def test_a_disc_joins_its_set_lying_flat_on_the_shelf(tmp_path):
    """A library nobody has moved into folders: disc 1 on the shelf. Disc 2 in
    a folder of its own would be a game of its own."""
    psx = tmp_path / "psx"

    got = choose_home(FF9.format(n=2), _rows((FF9.format(n=1), psx)), psx)

    assert got == psx


def test_roms_and_the_folders_inside_it_are_places_too(tmp_path):
    psx = tmp_path / "psx"
    inside = psx / "roms" / "Final Fantasy IX"

    assert choose_home(FF9.format(n=2), _rows((FF9.format(n=1), inside)), psx) == inside
    assert choose_home(FF9.format(n=2), _rows((FF9.format(n=1), psx / "roms")), psx) == (
        psx / "roms")


def test_a_set_already_split_is_joined_where_most_of_it_is(tmp_path):
    psx = tmp_path / "psx"
    most, one = psx / "Final Fantasy IX", psx / "Final Fantasy IX (Europe)"

    got = choose_home(FF9.format(n=4), _rows(
        (FF9.format(n=1), one), (FF9.format(n=2), most), (FF9.format(n=3), most)), psx)

    assert got == most


@pytest.mark.parametrize("arriving, present", [
    # Another title that starts the same way.
    ("Final Fantasy IX (Europe) (Disc 2).chd", "Final Fantasy VIII (Europe) (Disc 1).chd"),
    ("Game (Disc 2).chd", "Game (Hack) (Disc 1).chd"),
    # Not discs at all: a lone game is never somebody's set.
    ("Crash Bandicoot (Beta).chd", "Crash Bandicoot.chd"),
    ("Game.smc", "Game.sfc"),
    # A trailing letter says "disk B" only beside A and C, which a file arriving
    # on its own cannot see.
    ("Ishar 2 (Silmarils) B.adf", "Ishar 2 (Silmarils) A.adf"),
])
def test_a_name_that_merely_looks_alike_is_not_its_game(tmp_path, arriving, present):
    psx = tmp_path / "psx"

    assert choose_home(arriving, _rows((present, psx / "Somebody")), psx) is None


def test_a_row_outside_this_platform_is_no_home(tmp_path):
    """A library moved to another disk, rows still naming the old place."""
    psx = tmp_path / "psx"

    assert choose_home(FF9.format(n=2), _rows(
        (FF9.format(n=1), Path("/old/library/psx/Final Fantasy IX"))), psx) is None
    assert choose_home(FF9.format(n=2), _rows(
        (FF9.format(n=1), psx / "Final Fantasy IX" / "mods")), psx) is None


# ── Asked of the library ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
        session.add(RomPlatform(id=2, fs_slug="saturn", slug="saturn", name="Saturn"))
        await session.commit()
        yield session
    await engine.dispose()


def _row(db, rom_id, directory, fs_name, platform_id=1, **extra):
    stem, _, ext = fs_name.rpartition(".")
    db.add(Rom(id=rom_id, platform_id=platform_id, name=stem, fs_name=fs_name,
               fs_name_no_ext=stem, fs_extension=ext, fs_path=str(directory),
               fs_size_bytes=4, **extra))


@pytest.mark.asyncio
async def test_the_library_is_asked(db, tmp_path):
    title = tmp_path / "psx" / "Final Fantasy IX"
    _row(db, 1, title, FF9.format(n=1))
    await db.commit()

    assert await home_for("psx", FF9.format(n=2), roms_base=str(tmp_path), session=db) == title
    assert await home_for("psx", "Crash.chd", roms_base=str(tmp_path), session=db) == (
        tmp_path / "psx" / "Crash"), "nowa gra nie dostala folderu z nazwy pliku"


@pytest.mark.asyncio
async def test_only_this_platform_is_asked(db, tmp_path):
    _row(db, 1, tmp_path / "saturn" / "Final Fantasy IX", FF9.format(n=1), platform_id=2)
    await db.commit()

    assert await home_for("psx", FF9.format(n=2), roms_base=str(tmp_path), session=db) == (
        tmp_path / "psx" / "Final Fantasy IX (Europe)")


@pytest.mark.asyncio
async def test_a_row_whose_file_is_gone_is_no_home(db, tmp_path):
    _row(db, 1, tmp_path / "psx" / "Final Fantasy IX", FF9.format(n=1), missing_from_fs=True)
    await db.commit()

    assert await home_for("psx", FF9.format(n=2), roms_base=str(tmp_path), session=db) == (
        tmp_path / "psx" / "Final Fantasy IX (Europe)")


@pytest.mark.asyncio
async def test_a_name_with_like_wildcards_in_it_is_asked_for_as_written(db, tmp_path):
    """% and _ are wildcards to SQL LIKE, and MariaDB also takes a backslash as
    its escape unless told otherwise, which would make `AC\\DC` miss itself.
    Unescaped, `100%_Game` asks for every file starting with `100`."""
    from handler.database.rom_handler import rom_handler

    _row(db, 1, tmp_path / "psx" / "Hundred", "100%_Game (Disc 1).chd")
    _row(db, 2, tmp_path / "psx" / "Other", "100 Other Game (Disc 1).chd")
    await db.commit()

    got = await rom_handler.files_starting_with("psx", "100%_Game", session=db)

    assert [name for name, _ in got] == ["100%_Game (Disc 1).chd"]


# ── The download asks when it starts ────────────────────────────────────────

BODY = b"disc" * 4096


class _Source(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - name fixed by the base class
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *a):
        pass


@pytest.fixture
def source_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Source)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/disc.chd"
    srv.shutdown()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    async def _allow(request):
        """httpx awaits its event hooks, so the stand-in has to be a coroutine."""

    async def _no_database(fs_slug, filename, *, owner_id=None, dest_dir=None):
        return None

    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))
    monkeypatch.setattr(rsh, "make_request_guard", lambda **kw: _allow)
    monkeypatch.setattr(rsh, "max_rom_bytes", lambda: 64 * 1024 ** 3)
    monkeypatch.setattr(rsh, "assert_room_for", lambda *a, **kw: None)
    monkeypatch.setattr(rsh, "_register_and_scrape", _no_database)
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()
    yield tmp_path
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()


def _job(url, filename):
    job = rsh._RomJob(
        id=1, source_id="test", entry_id="e1", url=url, filename=filename,
        fs_slug="psx", headers=None, cookies=None, actor=None,
        entry_key=("test", "e1"), dest_key=("psx", filename))
    rsh._jobs[1] = job
    rsh._dest_locks.add(job.dest_key)
    rsh._in_flight.add(job.entry_key)
    return job


def test_a_download_writes_into_the_folder_its_game_is_in(source_url, sandbox, monkeypatch):
    title = sandbox / "psx" / "Final Fantasy IX"
    asked = []

    async def _home(fs_slug, filename, *, roms_base=None, session=None):
        asked.append(game_folder.folder_moves.locked())
        return title

    monkeypatch.setattr(game_folder, "home_for", _home)
    job = _job(source_url, FF9.format(n=2))

    asyncio.run(rsh._rom_download_job(job))

    assert job.status == "completed"
    landed = title / FF9.format(n=2)
    assert hashlib.sha256(landed.read_bytes()).digest() == hashlib.sha256(BODY).digest(), (
        "druga plyta nie trafila do folderu, w ktorym jest jej gra"
    )
    assert asked == [True], (
        "folder wybrany bez blokady, ktora trzyma zmiana nazwy folderu"
    )
    assert job.dest_dir == title


def test_the_choice_leaves_its_mark_before_the_lock_goes(source_url, sandbox, monkeypatch):
    """A rename waiting on the lock must find the transfer in progress, or it
    renames the folder out from under the disc about to be written into it."""
    title = sandbox / "psx" / "Final Fantasy IX"
    seen = []

    async def _home(fs_slug, filename, *, roms_base=None, session=None):
        return title

    real_release = game_folder.folder_moves.release

    def _release():
        seen.append(sorted(p.name for p in title.iterdir()) if title.exists() else None)
        real_release()

    monkeypatch.setattr(game_folder, "home_for", _home)
    monkeypatch.setattr(game_folder.folder_moves, "release", _release)
    job = _job(source_url, FF9.format(n=2))

    asyncio.run(rsh._rom_download_job(job))

    assert seen and seen[0] == [FF9.format(n=2) + ".part"], (
        f"blokada puszczona, zanim w folderze stanal plik .part: {seen}"
    )


def test_a_library_that_cannot_answer_fails_the_download_out_loud(source_url, sandbox, monkeypatch):
    """Not a quiet fall back to a folder named after the file: that is how a
    set splits in two without anybody seeing it happen."""
    async def _home(*_a, **_k):
        raise ConnectionError("database away")

    monkeypatch.setattr(game_folder, "home_for", _home)
    job = _job(source_url, FF9.format(n=2))

    asyncio.run(rsh._rom_download_job(job))

    assert job.status == "failed"
    assert not any(sandbox.rglob("*.chd")), "plik zapisany mimo braku odpowiedzi biblioteki"


# ── An upload asks the same question ────────────────────────────────────────
#
# Three things the browser sends went wrong the same way once the owner's games
# had moved into their titles' folders: a better dump of your own ROM was
# refused as "already here", the next disc of a set landed in a folder of its
# own, and a .sbi could not find the disc it belongs to. A ROM lying flat in
# roms/ is still refused, as it always was: that is two files for one row, a
# question older than folders (test_a_rom_already_on_the_shelf_...).

from test_a_rom_already_on_the_shelf_is_not_the_uploaders_to_take import (  # noqa: E402
    UPLOADER_ID,
    _already_on_shelf,
    _upload,
    shelf,  # noqa: F401 - the fixture, used by name below
)


@pytest.mark.asyncio
async def test_your_own_rom_in_its_titles_folder_is_replaced_where_it_is(shelf):  # noqa: F811
    title = shelf.psx / "Final Fantasy IX"
    _already_on_shelf(shelf, "ff9.chd", title, owner=UPLOADER_ID)

    out = await _upload(shelf, ["ff9.chd"])

    assert out["saved"] == ["ff9.chd"], f"podmiana wlasnego ROM-u odrzucona: {out}"
    assert (title / "ff9.chd").read_bytes() == b"rom bytes"
    assert not (shelf.psx / "ff9").exists(), "druga kopia w folderze nazwanym jak plik"


@pytest.mark.asyncio
async def test_the_next_disc_uploaded_joins_its_set(shelf):  # noqa: F811
    title = shelf.psx / "Final Fantasy IX"
    _already_on_shelf(shelf, FF9.format(n=1), title)

    out = await _upload(shelf, [FF9.format(n=2)])

    assert out["saved"] == [FF9.format(n=2)]
    assert (title / FF9.format(n=2)).is_file(), (
        "druga plyta w osobnym folderze, zestaw sie rozpadl"
    )


@pytest.mark.asyncio
async def test_that_disc_becomes_the_uploaders(shelf):  # noqa: F811
    """The stamp compared the row's folder with the one named after the file,
    so a disc written into its set's folder was owned by nobody and counted
    against no quota - the download's quiet failure, on this road."""
    title = shelf.psx / "Final Fantasy IX"
    _already_on_shelf(shelf, FF9.format(n=1), title)
    shelf.state.scan_places[FF9.format(n=2)] = str(title)

    await _upload(shelf, [FF9.format(n=2)])

    assert [who for _, who in shelf.state.stamped] == [UPLOADER_ID], (
        "plyta wgrana do folderu zestawu nie ma wlasciciela"
    )


@pytest.mark.asyncio
async def test_a_subchannel_file_finds_its_disc_in_the_titles_folder(shelf):  # noqa: F811
    title = shelf.psx / "Final Fantasy IX"
    _already_on_shelf(shelf, FF9.format(n=1), title, owner=UPLOADER_ID)
    sbi = FF9.format(n=1).replace(".chd", ".sbi")

    out = await _upload(shelf, [sbi])

    assert out["saved"] == [sbi], f".sbi nie znalazl swojej plyty: {out}"
    assert (title / sbi).is_file()


def test_no_rename_can_come_between_an_uploads_choice_and_its_part_file():
    """The choice is made under the lock a rename holds, and from there to the
    .part nothing waits on anything, so no other task - a rename included - can
    run in between. The .part then marks the folder busy."""
    import io
    router = Path(rsh.__file__).resolve().parent.parent.parent / "endpoints" / "roms" / "roms_router.py"
    source = io.open(router, encoding="utf-8").read()
    body = source[source.index("async def upload_roms("):]
    lock = body.index("async with game_folder.folder_moves:")
    choice = body.index("dest_dir = _upload_dest_dir(", lock)
    part = body.index('open(part_path, "wb")', choice)
    assert "await " not in body[choice:part], (
        "miedzy wyborem folderu a plikiem .part cos czeka - zmiana nazwy moze wejsc w srodek"
    )


def test_the_already_have_it_checks_ask_the_same_question():
    """Both of them - the queue and the import primitive - ask where the game
    is, not where a file of this name would go if it were new."""
    import io
    source = io.open(Path(rsh.__file__), encoding="utf-8").read()
    at = source.find("if not force and")
    found = 0
    while at != -1:
        found += 1
        assert "_already_here(" in source[at:at + 200], (
            "sprawdzenie 'juz jest' patrzy tylko w folder nazwany jak plik"
        )
        at = source.find("if not force and", at + 1)
    assert found == 2
    helper = source[source.index("async def _already_here("):]
    assert "_home_for(" in helper[:helper.index("\n\n\n")]
