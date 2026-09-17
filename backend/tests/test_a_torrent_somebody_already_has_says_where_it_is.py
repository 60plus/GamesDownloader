"""Adding a torrent the server already has says where it is, instead of "already added".

Transmission recognises a torrent by its content, so the same torrent added by a
second account is answered with the first one. The routes have refused that
since 1.0.34 (test_a_torrent_already_in_transmission_is_not_added_twice), with
one sentence for every case: "This torrent is already in Transmission". The
owner asked whether a digit could be added to the torrent to get past it. It
cannot: a digit changes the name, and the daemon does not go by the name.

What the owner approved instead is saying what is actually there:

  on its way     another transfer is fetching it, or filing it right now -
                 "somebody is already downloading this; the game appears when
                 it finishes", or "you are already downloading this" when that
                 transfer is the caller's own;
  in the library the game it became, or a library file a seed was made from -
                 "this game is already in the library: <title>", with the
                 game's id so the dialog can link to it;
  a leftover     nothing here holds it any more: a finished transfer whose game
                 was deleted since. The daemon keeps finished torrents, so that
                 used to block the game from ever being downloaded again. The
                 leftover is taken off the daemon (its data is left alone) and
                 the add is made again.

Two things stay the plain refusal, on purpose:

  - a game or transfer the caller may not see. Naming its title, or promising a
    game that will never appear on their screens, would say what a restricted
    library holds;
  - a torrent held by nothing in the database whose files are NOT in the
    download area. A whole game seeded for somebody's client has no row at all,
    and taking it off the daemon would cut that person's download off.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from models.library import Library, UserLibraryAccess
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.library_torrent import LibraryTorrent
from models.torrent_download import TorrentDownload
from models.user import User

CALLER, SOMEBODY = 3, 7
HASH = "ab" * 20


class _Upload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._at = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._at
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


@pytest_asyncio.fixture
async def server(monkeypatch, tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in (User, LibraryGame, LibraryFile, LibraryTorrent, TorrentDownload,
                      Library, UserLibraryAccess):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        # Both add routes ask whether the Games library is open before anything
        # else (test_a_switched_off_games_library_takes_no_new_games).
        session.add(Library(id=2, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM", enabled=True, visibility="public"))
        await session.commit()
    import importlib

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    for mod in ("decorators.database", "handler.database.library_registry_handler"):
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", maker)

    from endpoints.torrent import torrent_router as R

    torrents = tmp_path / "torrents"
    monkeypatch.setattr(R, "_TORRENT_DIR", str(torrents))
    monkeypatch.setattr(R, "_SEED_DIR", str(tmp_path / "seeds"))

    env = SimpleNamespace(
        R=R, maker=maker, created=[], removed=[], adds=0,
        # What the daemon answers each add with, in turn.
        answers=[],
        # Where the daemon's copy of the held torrent sits.
        held_dir=str(torrents / "some-game"),
        visible=True,
    )

    async def _add(*_a, **_k):
        env.adds += 1
        return dict(env.answers.pop(0)), None

    async def _add_file(path, *_a, **_k):
        # The daemon reads the file it is given, so a second try needs it still there.
        if not os.path.exists(path):
            return None, "torrent file not found"
        return await _add()

    for name in ("add_torrent_url", "add_torrent_metainfo"):
        monkeypatch.setattr(R.transmission_handler, name, _add)
    monkeypatch.setattr(R.transmission_handler, "add_torrent_file", _add_file)

    async def _get(ref):
        return {"hashString": HASH, "downloadDir": env.held_dir, "id": 5}

    async def _remove(ref, *, delete_data=False):
        env.removed.append((ref, delete_data))
        return True

    monkeypatch.setattr(R.transmission_handler, "get_torrent", _get)
    monkeypatch.setattr(R.transmission_handler, "remove_torrent", _remove)

    async def _create(request, title, os_name, download_dir, **kwargs):
        env.created.append(kwargs)
        return SimpleNamespace(
            id=100, title=title, os=os_name, status="downloading", percent_done=0.0,
            total_size=0, rate_download=0, eta=-1, error_msg=None, game_id=None,
            library=None, created_by="gdtest", created_at=None, completed_at=None)

    async def _fits(*_a, **_k):
        return None

    async def _fetched(_url):
        return b"torrent bytes"

    async def _visible(user, game_id):
        if not env.visible:
            raise HTTPException(404, "File not available")

    monkeypatch.setattr(R, "_create_torrent_download", _create)
    monkeypatch.setattr(R, "_refuse_if_it_does_not_fit", _fits)
    monkeypatch.setattr(R, "_fetch_torrent_file", _fetched)
    monkeypatch.setattr(R, "_assert_game_visible", _visible)

    env.request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=CALLER, username="gdtest"),
        scopes={Scope.LIBRARY_UPLOAD}))
    yield env
    await engine.dispose()


DUPLICATE = {"id": 5, "name": "Held", "hashString": HASH, "duplicate": True}
FRESH = {"id": 6, "name": "Held", "hashString": HASH}


async def _add_by_magnet(env):
    return await env.R.add_torrent_url(
        env.request, env.R.AddTorrentByUrl(url=f"magnet:?xt=urn:btih:{HASH}", title="Gra"))


async def _add_by_file(env):
    return await env.R.add_torrent_file(
        env.request, title="Gra", target_os="windows", library=None,
        file=_Upload("gra.torrent", b"torrent bytes"))


WAYS = [_add_by_magnet, _add_by_file]


async def _put(env, *rows):
    async with env.maker() as session:
        for row in rows:
            session.add(row)
        await session.commit()


def _transfer(row_id, *, status, owner=SOMEBODY, game_id=None, library=None):
    return TorrentDownload(
        id=row_id, title="Held", os="windows", download_dir="/d", status=status,
        game_id=game_id, info_hash=HASH, created_by="someone", created_by_id=owner,
        uploaded_by_id=owner, library=library)


def _game(game_id=40, title="Ion Fury"):
    return LibraryGame(id=game_id, title=title, slug=f"g{game_id}", source="custom",
                       is_active=True, published_by=SOMEBODY)


def _refusal(caught):
    return getattr(caught.value, "refusal", {}) or {}


# ── On its way ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("way", WAYS)
@pytest.mark.parametrize("status,game_id", [("downloading", None), ("paused", None),
                                            ("complete", None)])
async def test_somebody_elses_transfer_is_named_as_on_its_way(server, way, status, game_id):
    await _put(server, _transfer(1, status=status, game_id=game_id))
    server.answers = [DUPLICATE]

    with pytest.raises(HTTPException) as caught:
        await way(server)

    assert caught.value.status_code == 409
    assert _refusal(caught).get("code") == "already_downloading", (
        f"trwajacy cudzy transfer ({status}) nadal konczy sie ogolnikiem 'juz jest w Transmission'"
    )
    assert _refusal(caught).get("mine") is False
    assert server.created == [] and server.removed == [], (
        "cudzy trwajacy transfer zostal ruszony albo zapisano na nim drugi wiersz"
    )


@pytest.mark.asyncio
async def test_the_callers_own_transfer_says_it_is_theirs(server):
    await _put(server, _transfer(1, status="downloading", owner=CALLER))
    server.answers = [DUPLICATE]

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_downloading"
    assert _refusal(caught).get("mine") is True


@pytest.mark.asyncio
async def test_a_transfer_bound_for_a_shelf_the_caller_cannot_reach_is_not_described(
        server, monkeypatch):
    """"The game appears when it finishes" is a promise about their screens, and
    that game will never appear on them."""
    await _put(server, _transfer(1, status="downloading", library="kids"))
    server.answers = [DUPLICATE]

    async def _no_such_shelf(user, slug):
        if slug == "kids":
            raise HTTPException(404, f"There is no library called '{slug}'.")

    monkeypatch.setattr(server.R, "_assert_shelf_allowed", _no_such_shelf)

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_added"
    assert server.removed == []


# ── In the library ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("way", WAYS)
async def test_a_finished_transfer_names_the_game_it_became(server, way):
    await _put(server, _game(), _transfer(1, status="complete", game_id=40))
    server.answers = [DUPLICATE]

    with pytest.raises(HTTPException) as caught:
        await way(server)

    refusal = _refusal(caught)
    assert refusal.get("code") == "already_in_library", (
        f"gra z tego torrenta jest w bibliotece, a odmowa tego nie mowi: {refusal!r}"
    )
    assert refusal.get("game_id") == 40 and refusal.get("title") == "Ion Fury", (
        "odmowa nie niesie gry, do ktorej okno moze odeslac"
    )
    assert server.created == [] and server.removed == []


@pytest.mark.asyncio
async def test_a_library_file_being_seeded_names_its_game(server):
    await _put(server, _game(),
               LibraryFile(id=8, library_game_id=40, filename="a.zip",
                           file_path="games/CUSTOM/Ion Fury/a.zip", source="custom",
                           size_bytes=10),
               LibraryTorrent(id=2, file_id=8, info_hash=HASH, status="seeding",
                              created_by="someone"))
    server.answers = [DUPLICATE]
    server.held_dir = "/data/games/CUSTOM/Ion Fury"

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_in_library"
    assert _refusal(caught).get("game_id") == 40
    assert server.removed == [], "zabrano z demona plik, ktory ktos wlasnie pobiera z serwera"


@pytest.mark.asyncio
async def test_a_seed_that_has_finished_seeding_still_names_its_game(server):
    """The hash is the file's content, and the file is in the library whether or
    not a seed of it is still running."""
    await _put(server, _game(),
               LibraryFile(id=8, library_game_id=40, filename="a.zip",
                           file_path="games/CUSTOM/Ion Fury/a.zip", source="custom",
                           size_bytes=10),
               LibraryTorrent(id=2, file_id=8, info_hash=HASH, status="expired",
                              created_by="someone"))
    server.answers = [DUPLICATE]
    server.held_dir = "/data/games/CUSTOM/Ion Fury"

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_in_library"


@pytest.mark.asyncio
async def test_an_unpublished_game_is_not_named(server):
    """An unpublished GOG game is on nobody's shelf, so "it is in the library"
    would send the reader looking for something that is not there."""
    hidden = _game(title="Unpublished")
    hidden.is_active = False
    await _put(server, hidden,
               LibraryFile(id=8, library_game_id=40, filename="a.zip",
                           file_path="GOG/Unpublished/a.zip", source="gog", size_bytes=10),
               LibraryTorrent(id=2, file_id=8, info_hash=HASH, status="seeding",
                              created_by="someone"),
               _transfer(1, status="complete", game_id=40))
    server.answers = [DUPLICATE]
    server.held_dir = "/data/games/GOG/Unpublished"

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_added"
    assert "Unpublished" not in str(_refusal(caught))


@pytest.mark.asyncio
async def test_a_game_the_caller_may_not_see_is_not_named(server):
    await _put(server, _game(title="Secret"), _transfer(1, status="complete", game_id=40))
    server.answers = [DUPLICATE]
    server.visible = False

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    refusal = _refusal(caught)
    assert refusal.get("code") == "already_added"
    assert "Secret" not in str(refusal) and "Secret" not in str(caught.value.detail), (
        "odmowa zdradza tytul gry z biblioteki, ktorej to konto nie widzi"
    )
    assert "game_id" not in refusal
    assert server.removed == [] and server.created == []


# ── A leftover ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("way", WAYS)
async def test_a_leftover_of_a_deleted_game_no_longer_blocks_downloading_it_again(server, way):
    """The finished transfer's game was deleted; the daemon still holds the
    torrent. The owner's case: a game removed and wanted back."""
    await _put(server, _transfer(1, status="complete", game_id=40))   # game 40 is gone
    server.answers = [DUPLICATE, FRESH]

    result = await way(server)

    assert server.removed == [(HASH, False)], (
        "resztka po skonczonym transferze nie zostala zdjeta z demona (albo zdjeta z danymi)"
    )
    assert server.adds == 2, "po zdjeciu resztki torrent nie zostal dodany ponownie"
    assert len(server.created) == 1 and server.created[0].get("info_hash") == HASH
    assert result["id"] == 100


@pytest.mark.asyncio
async def test_a_different_torrent_running_does_not_explain_this_one(server):
    """Only the same content holds a torrent. Somebody else fetching some other
    game is no reason to call this one taken."""
    other = _transfer(2, status="downloading")
    other.info_hash = "cd" * 20
    await _put(server, other, _transfer(1, status="complete", game_id=40))   # game 40 is gone
    server.answers = [DUPLICATE, FRESH]

    await _add_by_magnet(server)

    assert server.removed == [(HASH, False)] and len(server.created) == 1


@pytest.mark.asyncio
async def test_a_leftover_that_comes_back_as_a_duplicate_again_is_refused(server):
    await _put(server, _transfer(1, status="error"))
    server.answers = [DUPLICATE, DUPLICATE]

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_added"
    assert server.created == []


@pytest.mark.asyncio
async def test_a_torrent_seeded_from_outside_the_download_area_is_left_alone(server):
    """A whole game seeded for somebody's client: no row anywhere, files in the
    library. Taking it off the daemon cuts their download off."""
    server.answers = [DUPLICATE]
    server.held_dir = "/data/games/CUSTOM/Ion Fury"

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_added"
    assert server.removed == [], "zdjeto z demona torrent spoza katalogu pobieran"
    assert server.adds == 1


@pytest.mark.asyncio
async def test_a_look_alike_folder_is_not_the_download_area(server):
    """`/data/downloads/torrents-old` starts with the same letters as the
    download area and is not inside it."""
    server.answers = [DUPLICATE]
    server.held_dir = server.R._TORRENT_DIR + "-old/x"

    with pytest.raises(HTTPException):
        await _add_by_magnet(server)

    assert server.removed == []


@pytest.mark.asyncio
async def test_a_daemon_that_does_not_take_the_leftover_off_is_not_added_again(server, monkeypatch):
    await _put(server, _transfer(1, status="removed"))
    server.answers = [DUPLICATE, FRESH]

    async def _refuse(ref, *, delete_data=False):
        return False

    monkeypatch.setattr(server.R.transmission_handler, "remove_torrent", _refuse)

    with pytest.raises(HTTPException) as caught:
        await _add_by_magnet(server)

    assert _refusal(caught).get("code") == "already_added"
    assert server.adds == 1 and server.created == []


# ── On screen ────────────────────────────────────────────────────────────────
# Read from the source, as the other frontend tests here are: the frontend has
# no test runner of its own.

import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import re  # noqa: E402

FRONT = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"


def _front(rel: str) -> str:
    path = FRONT / "src" / rel
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


def _between(source: str, start: str, end_pattern: str) -> str:
    at = source.index(start)
    nxt = re.search(end_pattern, source[at + len(start):])
    return source[at:at + len(start) + (nxt.start() if nxt else len(source))]


def test_the_sentence_says_whose_transfer_it_is():
    fn = _between(_front("lib/transferError.ts"), "export function describeAddRefusal",
                  r"\nexport function")
    case = _between(fn, "case 'already_downloading':", r"\n\s+case '")
    assert "r.mine" in case, "zdanie nie odroznia wlasnego transferu od cudzego"
    assert "torrent.add_err_already_downloading_yours" in case
    assert "torrent.add_err_already_downloading'" in case


def test_the_sentence_names_the_game():
    fn = _between(_front("lib/transferError.ts"), "export function describeAddRefusal",
                  r"\nexport function")
    case = _between(fn, "case 'already_in_library':", r"\n\s+case '")
    assert "torrent.add_err_already_in_library" in case and "title" in case


def test_the_game_to_link_to_is_read_off_the_refusal():
    source = _front("lib/transferError.ts")
    fn = _between(source, "export function addRefusalGame", r"\nexport function")
    assert "'already_in_library'" in fn, "odnosnik powstaje dla odmowy, ktora nie dotyczy gry"
    assert "game_id" in fn


def test_the_themes_are_handed_the_link_too():
    """The entry itself, not the name: a comment beside it says the name too."""
    main = _front("main.ts")
    utils = main[main.index("utils: {"):]
    utils = utils[:utils.index("\n  },")]
    assert re.search(r"^\s*addRefusalGame,\s*$", utils, re.M), (
        "Vapor i NEON HORIZON nie dostaja gry do odnosnika"
    )


def test_the_core_dialog_offers_to_open_the_game():
    view = _front("views/games/GamesLibrary.vue")
    submit = _between(view, "async function submitTorrent()", r"\n(async )?function |\n// ")
    assert "addRefusalGame(e)" in submit, "okno nie zapamietuje gry z odmowy"
    at_try = submit.index("try {")
    assert "tErrorGame.value = null" in submit[:at_try], (
        "odnosnik z poprzedniej odmowy zostaje przy nastepnej probie"
    )
    assert re.search(r'v-if="tErrorGame"[^>]*>', view), "brak przycisku otwierajacego gre"
    assert "openExistingGame" in view and "torrent.open_existing_game" in view
    opener = _between(view, "function openExistingGame(", r"\n(async )?function ")
    assert "games-detail" in opener, "przycisk nie prowadzi do strony gry"


KEYS = ["torrent.add_err_already_downloading_yours", "torrent.open_existing_game"]


@pytest.mark.parametrize("lang", ["en", "de", "es", "fr", "it", "pl", "pt", "ru"])
def test_every_language_can_say_it(lang):
    path = (FRONT / "src" / "i18n" / "en.json" if lang == "en"
            else FRONT / "public" / "i18n" / f"{lang}.json")
    if not path.is_file():
        pytest.skip("frontend tree not present")
    strings = json.load(io.open(path, encoding="utf-8"))
    for key in KEYS:
        assert strings.get(key), f"{lang}: brak {key}"
    assert "{title}" in strings.get("torrent.add_err_already_in_library", ""), (
        f"{lang}: zdanie o grze w bibliotece gubi jej tytul"
    )
