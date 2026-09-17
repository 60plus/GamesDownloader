"""Where a finished torrent is allowed to put its files.

THE HOLE. The slug a torrent lands under is derived from its title by stripping
everything that is not ASCII alphanumeric. A title made entirely of characters
that do not survive that - Cyrillic, Chinese, Japanese, or a name that is only
punctuation - leaves the empty string, and nothing checked. `os.path.join(root,
"games", folder, "")` is the library folder ITSELF, so every file in the torrent
was written straight into the library root, and `shutil.move` overwrites without
asking. A game already sitting there under a matching relative path was
replaced.

The router two files away has the same slugify and it already ends with
`or "game"`. This one never got the fallback.

TWO MORE THINGS ARE CLOSED HERE, because they are the same journey.

`shutil.move` overwrites, full stop. Every other write path in this release was
made to refuse rather than destroy - the ROM upload writes a `.part` and
`os.replace`s it, the quota refuses instead of deleting - and this one silently
replaced whatever it found. A destination that already exists is now a refusal.

And the names come from OUTSIDE. What is on the disk under the download
directory was decided by a torrent somebody else made. `os.walk` will not
descend a symlinked directory, but it does list symlinked FILES, and moving one
into the library puts a pointer to somewhere else entirely behind the library's
own file server. They are skipped, and the destination is checked to be inside
the folder it is supposed to be inside - which cannot currently be violated
through `relpath`, and is asserted anyway because that is one refactor away from
being untrue and there is no test between here and the file system.
"""

from __future__ import annotations

import os

import pytest

from handler.torrent import seed_monitor as M


# ── The slug ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Тетрис",              # Cyrillic
    "スーパーマリオ",        # Japanese
    "极品飞车",             # Chinese
    "...",                 # punctuation only
    "",                    # nothing at all
    "   ",
])
def test_a_title_that_survives_nothing_still_gets_a_folder(title):
    """Every one of these produced the empty string, and the empty string is
    the library root."""
    slug = M._slug_for(title)
    assert slug, (
        f"tytul {title!r} daje pusty slug, a pusty slug to KORZEN biblioteki - "
        "pliki z torrenta nadpisza tam cudze gry"
    )
    assert slug.strip("-/. "), f"slug {slug!r} nadal jest pusty po odcieciu"


@pytest.mark.parametrize("title,expected", [
    ("Far Cry 5: Gold Edition", "far-cry-5-gold-edition"),
    ("Prince of Persia", "prince-of-persia"),
    ("Terminator 2D: NO FATE", "terminator-2d-no-fate"),
])
def test_an_ordinary_title_is_unchanged(title, expected):
    """THE LEGAL CASE. Every game already in a library was filed under this
    exact derivation, so changing what it produces for ordinary titles would
    strand them."""
    assert M._slug_for(title) == expected


# ── The move ─────────────────────────────────────────────────────────────────

def _torrent(tmp_path, *names):
    src = tmp_path / "dl"
    src.mkdir()
    for name in names:
        f = src / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("bytes")
    return str(src)


def test_a_file_already_there_is_not_replaced(tmp_path):
    """The library is somebody's collection. Nothing else in this release
    destroys what it finds, and this used to."""
    src = _torrent(tmp_path, "gra.bin")
    dest_root = tmp_path / "games" / "CUSTOM" / "gra"
    dest_root.mkdir(parents=True)
    (dest_root / "gra.bin").write_text("CUDZA GRA")

    with pytest.raises(FileExistsError):
        M._move_into_library([os.path.join(src, "gra.bin")], src, str(dest_root))

    assert (dest_root / "gra.bin").read_text() == "CUDZA GRA", (
        "plik istniejacej gry zostal nadpisany zawartoscia torrenta"
    )


def test_an_ordinary_move_still_works(tmp_path):
    """THE LEGAL CASE for the guard above: a torrent landing in a folder of its
    own has to go through untouched, subdirectories included."""
    src = _torrent(tmp_path, "gra.bin", "DATA/plik.pak")
    dest_root = tmp_path / "games" / "CUSTOM" / "gra"

    moved = M._move_into_library(
        [os.path.join(src, "gra.bin"), os.path.join(src, "DATA", "plik.pak")],
        src, str(dest_root))

    assert len(moved) == 2
    assert (dest_root / "gra.bin").is_file()
    assert (dest_root / "DATA" / "plik.pak").is_file(), (
        "podkatalogi z torrenta przestaly byc odwzorowywane"
    )
    assert all(size == len("bytes") for _, size in moved)


def test_a_collision_partway_through_moves_nothing(tmp_path):
    """The refusal used to come at the colliding file, after the ones before it
    had already gone. Those sat in the library with no rows - outside the quota
    and invisible in the app - the torrent's own folder was left incomplete, so
    seeding broke, and the transfer said the files were still in the download
    folder. Every destination is checked before anything moves."""
    src = _torrent(tmp_path, "a.bin", "b.bin", "c.bin")
    dest_root = tmp_path / "games" / "CUSTOM" / "gra"
    dest_root.mkdir(parents=True)
    (dest_root / "b.bin").write_text("CUDZY PLIK")

    with pytest.raises(FileExistsError):
        M._move_into_library(
            [os.path.join(src, n) for n in ("a.bin", "b.bin", "c.bin")], src, str(dest_root))

    assert sorted(os.listdir(src)) == ["a.bin", "b.bin", "c.bin"], (
        "pliki sprzed kolizji wyjechaly z folderu pobierania mimo odmowy"
    )
    assert sorted(os.listdir(dest_root)) == ["b.bin"], (
        "w bibliotece zostaly pliki bez wpisow"
    )
    assert (dest_root / "b.bin").read_text() == "CUDZY PLIK"


def test_a_move_that_breaks_off_puts_back_what_it_had_moved(tmp_path, monkeypatch):
    """A full disk, a vanished mount: anything can stop a move after some files
    have gone. The transfer then tells the person the files are still in the
    download folder, and that has to be true."""
    import shutil

    src = _torrent(tmp_path, "a.bin", "DATA/b.pak", "c.bin")
    dest_root = tmp_path / "games" / "CUSTOM" / "gra"
    real_move = shutil.move
    calls = []

    def _move_then_break(source, dest, *a, **k):
        calls.append(source)
        if len(calls) == 3:
            # Half a copy on the destination, the original still in place -
            # which is what a copy across bind mounts leaves when it fails.
            with open(dest, "w") as partial:
                partial.write("by")
            raise OSError(28, "No space left on device")
        return real_move(source, dest, *a, **k)

    monkeypatch.setattr(shutil, "move", _move_then_break)

    files = [os.path.join(src, "a.bin"), os.path.join(src, "DATA", "b.pak"),
             os.path.join(src, "c.bin")]
    with pytest.raises(OSError):
        M._move_into_library(files, src, str(dest_root))

    for f in files:
        assert os.path.isfile(f), f"{os.path.basename(f)} nie wrocil do folderu pobierania"
    left = [os.path.join(d, n) for d, _s, names in os.walk(dest_root) for n in names]
    assert left == [], f"w bibliotece zostalo: {left}"
    assert not dest_root.exists(), (
        "w bibliotece zostal pusty folder gry, ktorej nie ma"
    )


def test_nothing_is_written_outside_the_folder_it_belongs_in(tmp_path):
    """A path that climbs out of the destination is refused rather than
    followed. Not reachable through `relpath` today; asserted because the day
    somebody derives the destination differently, there is nothing between this
    function and the file system."""
    src = _torrent(tmp_path, "gra.bin")
    dest_root = tmp_path / "games" / "CUSTOM" / "gra"
    outsider = tmp_path / "poza.bin"
    outsider.write_text("NIE RUSZAC")

    with pytest.raises(ValueError):
        M._move_into_library([str(outsider)], src, str(dest_root))

    assert outsider.read_text() == "NIE RUSZAC"


# ── And the transfer has to say what happened ────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _Result(self._rows)

    async def commit(self):
        return None


class _Factory:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self):
        return self

    async def __aenter__(self):
        return _Db(self._rows)

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def finished(monkeypatch):
    """A transfer that has just reached one hundred per cent."""
    from types import SimpleNamespace

    from handler.database import session as S
    from handler.socket_handler import sio
    from handler.torrent import transmission_handler as TH

    row = SimpleNamespace(id=9, transmission_id=3, info_hash="abc",
                          total_size=1000, created_by_id=3, status="downloading",
                          os="windows")
    monkeypatch.setattr(S, "async_session_factory", _Factory([row]))

    async def _get_torrent(_tid):
        return {"hashString": "abc", "status": 6, "percentDone": 1.0,
                "totalSize": 1000, "downloadedEver": 1000, "rateDownload": 0,
                "eta": 0, "error": 0}

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)

    written: list[dict] = []

    async def _update(_id, values):
        written.append(dict(values))

    monkeypatch.setattr(M, "_update_download", _update)

    async def _emit(_event, _payload=None, **_k):
        return None

    monkeypatch.setattr(sio, "emit", _emit)
    return SimpleNamespace(written=written)


@pytest.mark.asyncio
async def test_a_transfer_whose_files_could_not_be_filed_says_so(finished, monkeypatch):
    """Refusing to overwrite is only half an answer. The other half is telling
    somebody, or the transfer reads as finished, no game appears, and there is
    nothing anywhere to explain the difference - the same silent lie as the
    upload dialog that reported success after refusing every file."""
    async def _no_game(_td):
        # (id gry, zdanie awaryjne, kod powodu, wartosc do kodu)
        return None, "Nie udalo sie zlozyc gry z tego transferu.", "no_game", None

    monkeypatch.setattr(M, "_auto_register_game", _no_game)

    await M._check_downloads()

    said = " ".join(str(w.get("error_msg", "")) for w in finished.written)
    assert said.strip(), (
        f"transfer skonczyl sie bez gry i bez slowa wyjasnienia: {finished.written}"
    )

    # The FINAL state, not "no write ever said complete". Writing "complete"
    # before the long file copy is load-bearing: it takes the row out of the set
    # the monitor polls, which is what stops a ten second tick starting a second
    # registration while the first is still copying. What must be true is where
    # the row ENDS UP.
    final = {}
    for w in finished.written:
        final.update(w)
    assert final.get("status") != "complete", (
        f"transfer konczy jako sukces, chociaz nie powstala z niego zadna gra: {final}"
    )


@pytest.mark.asyncio
async def test_a_transfer_that_did_become_a_game_still_reports_success(finished, monkeypatch):
    """THE LEGAL CASE. The ordinary finish must stay ordinary: complete, with
    the game it became."""
    async def _game(_td):
        return 128, None, None, None

    monkeypatch.setattr(M, "_auto_register_game", _game)

    await M._check_downloads()

    assert any(w.get("status") == "complete" for w in finished.written)
    assert any(w.get("game_id") == 128 for w in finished.written)
    assert not any(w.get("error_msg") for w in finished.written), (
        "udany transfer dostaje komunikat o bledzie"
    )


def test_a_symlink_is_not_carried_into_the_library(tmp_path):
    """The names in a torrent were chosen by whoever made it. A symlink moved
    into the library is a pointer to somewhere else standing behind the
    library's own file server."""
    src = tmp_path / "dl"
    src.mkdir()
    (src / "prawdziwy.bin").write_text("bytes")
    secret = tmp_path / "sekret"
    secret.write_text("NIE DLA NICH")
    try:
        os.symlink(secret, src / "podstawiony.bin")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available here")

    found = M._collect_files(str(src))

    assert [os.path.basename(p) for p in found] == ["prawdziwy.bin"], (
        f"dowiazanie symboliczne z torrenta trafia do biblioteki: {found}"
    )
