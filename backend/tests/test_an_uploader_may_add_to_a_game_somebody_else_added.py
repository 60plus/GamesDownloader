"""An uploader may add files to a game somebody else added - and take them out again.

THE OWNER'S DECISIONS, 2026-09-17, asked one at a time:

  1. "uploader rowniez powinien miec mozliwosc dodania dlc czy extras do gry
     dodanej przez kogos innego" - and every type of file, not only DLC and
     extras. Until then only the game's owner or an administrator could add a
     file, and an uploader who answered "yes, add it to the existing game" got a
     403 after sending the whole file (1.0.34 audit, #13).
  2. The account that added a file removes it itself; an administrator can take
     such files over "jak gre", the way a game is taken over.
  3. The owner of the game may still delete it, files from other accounts and
     all, "bo bez gry dlc czy extras sa bezuzyteczne" - and the question before
     it says how many of those go.

What had made the old rule necessary is answered already: a file is charged to
the account that brought it in, so adding to somebody else's game costs the
adder. Two things stay closed, and are tested here beside the legal cases:

  - which games may be named: the ones the caller can SEE. Everything else
    answers 404, like a game that does not exist - the 403 there used to confirm
    ids in libraries hidden from the caller (1.0.34 audit, #7);
  - writing over a file somebody else is charged for. Adding is allowed;
    replacing their bytes with yours is not.

And one thing the same title needed: two entries called "Doom" used to share one
folder on the disk. The older one keeps the plain name; a newer one gets its
slug beside the title.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from models.library import Library, LibraryMembership, UserLibraryAccess
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.user_game_access import UserGameAccess

ADMIN_ID, ALICE, BOB = 1, 3, 7
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.LIBRARY_READ}
ADMIN = UPLOADER | {Scope.LIBRARY_ADMIN}


def _account(uid, *, admin=False):
    from models.user import Role
    return SimpleNamespace(id=uid, username=f"u{uid}", role=Role.ADMIN if admin else Role.UPLOADER)


def _request(uid, scopes=UPLOADER, *, admin=False):
    return SimpleNamespace(state=SimpleNamespace(user=_account(uid, admin=admin), scopes=scopes))


@pytest_asyncio.fixture
async def shelf(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        from models.rom import Rom
        from models.rom_platform import RomPlatform
        for table in (Library, LibraryGame, LibraryFile, LibraryMembership, UserLibraryAccess,
                      UserGameAccess, RomPlatform, Rom):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(Library(id=2, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM", enabled=True, visibility="public"))
        session.add(Library(id=9, slug="kids", name="Kids", kind="custom_lib",
                            storage_folder="kids", enabled=True, visibility="restricted"))
        # Alice's game: her installer, Bob's DLC and extras, and a file from
        # before files carried an account (it counts against the game's owner).
        session.add(LibraryGame(id=40, title="Ion Fury", slug="ion-fury", source="custom",
                                is_active=True, in_default_library=True, published_by=ALICE))
        for fid, path, size, by in (
            (1, "games/CUSTOM/Ion Fury/windows/setup.exe", 100, ALICE),
            (2, "games/CUSTOM/Ion Fury/dlc/aftershock.exe", 50, BOB),
            (3, "games/CUSTOM/Ion Fury/extra/manual.pdf", 5, BOB),
            (4, "games/CUSTOM/Ion Fury/windows/old.zip", 7, None),
        ):
            session.add(LibraryFile(id=fid, library_game_id=40, filename=path.rsplit("/", 1)[1],
                                    file_path=path, source="custom", size_bytes=size,
                                    published_by=by))
        # Two different games with one title, on the same shelf.
        session.add(LibraryGame(id=41, title="Doom", slug="doom", source="custom",
                                is_active=True, in_default_library=True, published_by=ALICE))
        session.add(LibraryGame(id=42, title="Doom", slug="doom-1", source="custom",
                                is_active=True, in_default_library=True, published_by=BOB))
        # A game in a restricted library Bob is not on.
        session.add(LibraryGame(id=50, title="Hidden", slug="hidden", source="custom",
                                is_active=True, in_default_library=False, published_by=ALICE))
        session.add(LibraryMembership(library_game_id=50, library_id=9))
        await session.commit()

    import importlib

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    for mod in ("decorators.database", "handler.library.visibility",
                "handler.database.library_registry_handler",
                "handler.database.library_handler", "handler.library.quota"):
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", maker)

    async def _rows():
        from sqlalchemy import select
        async with maker() as s:
            files = {f.id: f for f in (await s.execute(select(LibraryFile))).scalars()}
            games = {g.id: g for g in (await s.execute(select(LibraryGame))).scalars()}
        return files, games

    yield SimpleNamespace(maker=maker, rows=_rows)
    await engine.dispose()


# ── Adding ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_uploader_may_open_somebody_elses_game_to_upload(shelf):
    from endpoints.library.upload_router import _game_open_to_upload

    game = await _game_open_to_upload(_request(BOB), 40)
    assert game.id == 40, "uploader nie moze dodac pliku do gry dodanej przez kogos innego"


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,scopes,admin", [(BOB, UPLOADER, False), (ADMIN_ID, ADMIN, True)])
async def test_a_game_the_caller_cannot_see_answers_like_one_that_is_not_there(
        shelf, uid, scopes, admin):
    """An administrator sees the restricted library, so only Bob is refused.
    Asked for both, because a 404 for everybody would pass for Bob too."""
    from endpoints.library.upload_router import _game_open_to_upload

    if admin:
        assert (await _game_open_to_upload(_request(uid, scopes, admin=True), 50)).id == 50
        return
    with pytest.raises(HTTPException) as refusal:
        await _game_open_to_upload(_request(uid, scopes), 50)
    assert refusal.value.status_code == 404, (
        "wgranie do gry z ukrytej biblioteki odpowiada inaczej niz do gry, ktorej nie ma"
    )
    with pytest.raises(HTTPException) as missing:
        await _game_open_to_upload(_request(uid, scopes), 999)
    assert missing.value.detail == refusal.value.detail


@pytest.mark.asyncio
async def test_an_account_without_the_upload_right_is_refused(shelf):
    from endpoints.library.upload_router import _game_open_to_upload

    with pytest.raises(HTTPException) as refusal:
        await _game_open_to_upload(_request(BOB, {Scope.LIBRARY_READ}), 40)
    assert refusal.value.status_code == 403


@pytest.mark.asyncio
async def test_deleting_a_game_the_caller_cannot_see_answers_404_not_403(shelf):
    from endpoints.library.library_router import delete_library_game

    with pytest.raises(HTTPException) as hidden:
        await delete_library_game.__wrapped__(_request(BOB), 50)
    assert hidden.value.status_code == 404
    with pytest.raises(HTTPException) as visible:
        await delete_library_game.__wrapped__(_request(BOB), 40)
    assert visible.value.status_code == 403, "gra widoczna, ale cudza - nadal nie do usuniecia"


# ── Replacing ────────────────────────────────────────────────────────────────

def _game(owner):
    return SimpleNamespace(id=40, published_by=owner)


def _file(by):
    return SimpleNamespace(published_by=by)


@pytest.mark.parametrize("scopes,uid,game_owner,row,allowed", [
    (UPLOADER, BOB,   ALICE, _file(ALICE), False),   # her installer
    (UPLOADER, BOB,   ALICE, _file(None),  False),   # a file that counts against her
    (UPLOADER, BOB,   ALICE, None,         False),   # on the disk with no row: hers
    (UPLOADER, BOB,   ALICE, _file(BOB),   True),    # his own DLC
    (UPLOADER, BOB,   BOB,   None,         True),    # untracked, in his own game
    (UPLOADER, ALICE, ALICE, _file(BOB),   False),   # the owner does not replace his DLC either
    (ADMIN,    ADMIN_ID, ALICE, _file(BOB), True),
    ({Scope.LIBRARY_READ}, BOB, BOB, _file(BOB), False),
])
def test_who_may_replace_a_file_that_is_already_there(scopes, uid, game_owner, row, allowed):
    from handler.library.ownership import can_replace_file

    assert can_replace_file(scopes, uid, _game(game_owner), row) is allowed


@pytest.mark.asyncio
async def test_writing_over_somebody_elses_file_is_refused(shelf, tmp_path, monkeypatch):
    from endpoints.library import upload_router as U

    monkeypatch.setattr("config.BASE_PATH", str(tmp_path))
    target = tmp_path / "games/CUSTOM/Ion Fury/windows/setup.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"alice")
    _files, games = await shelf.rows()

    with pytest.raises(HTTPException) as refusal:
        await U._refuse_replacing_another_accounts_file(
            games[40], target, scopes=UPLOADER, user_id=BOB)
    assert refusal.value.status_code == 403

    # His own file is his to replace, and a name nobody has used replaces nothing.
    own = tmp_path / "games/CUSTOM/Ion Fury/dlc/aftershock.exe"
    own.parent.mkdir(parents=True)
    own.write_bytes(b"bob")
    await U._refuse_replacing_another_accounts_file(games[40], own, scopes=UPLOADER, user_id=BOB)
    await U._refuse_replacing_another_accounts_file(
        games[40], tmp_path / "games/CUSTOM/Ion Fury/new.bin", scopes=UPLOADER, user_id=BOB)


class _Upload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        data, self._data = self._data, b""
        return data


@pytest.mark.asyncio
async def test_the_file_route_refuses_to_write_over_somebody_elses_file(shelf, tmp_path, monkeypatch):
    """Run through the route, not only the helper: the helper being right is no
    use if the route stops asking it."""
    from endpoints.library import upload_router as U

    monkeypatch.setattr("config.BASE_PATH", str(tmp_path))
    monkeypatch.setattr(U, "GAMES_PATH", str(tmp_path / "games"))
    target = tmp_path / "games/CUSTOM/Ion Fury/windows/setup.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"alice")

    with pytest.raises(HTTPException) as refusal:
        await U.upload_game_file.__wrapped__(
            _request(BOB), 40, file=_Upload("setup.exe", b"bob's bytes"),
            os_platform="windows", file_type="game", language=None, version=None,
            overwrite=True)
    assert refusal.value.status_code == 403, (
        "uploader nadpisal instalator wlascicielki gry swoim plikiem"
    )
    assert target.read_bytes() == b"alice"
    assert not list(target.parent.glob("*.part")), "zaczeto zapis przed odmowa"


def test_both_upload_routes_guard_a_replacement_and_the_catalogue_does_not():
    """Two accounts fetching the same catalogue entry replace the same build on
    purpose (`_finalize_upload`), so only the manual routes carry the guard."""
    import io
    import pathlib
    import re

    backend = pathlib.Path(__file__).resolve().parent.parent
    upload = io.open(backend / "endpoints/library/upload_router.py", encoding="utf-8").read()

    def fn(head):
        at = upload.index(head)
        nxt = re.search(r"\n(?=[@A-Za-z_#])", upload[at + len(head):])
        return upload[at:at + len(head) + nxt.start()] if nxt else upload[at:]

    file_route = fn("async def upload_game_file(")
    assert "_refuse_replacing_another_accounts_file(" in file_route
    assert file_route.index("_refuse_replacing_another_accounts_file(") < file_route.index("open(part_path"), (
        "sprawdzenie cudzego pliku jest po zapisie"
    )
    assert "replace_guard=(game," in fn("async def upload_game_file_from_url(")
    job = fn("async def _url_upload_job(")
    assert job.count("_refuse_replacing_another_accounts_file(") == 2, (
        "zadanie URL nie sprawdza cudzego pliku po nazwie podanej przez serwer"
    )
    plugins = io.open(backend / "endpoints/settings/plugins_router.py", encoding="utf-8").read()
    assert "replace_guard" not in plugins


# ── Taking your own out again ────────────────────────────────────────────────

@pytest.fixture
def no_disk(monkeypatch):
    from endpoints.library import library_router as L

    taken = []

    def _delete(files):
        taken.extend(f.id for f in files)
        return len(files)

    monkeypatch.setattr(L, "_delete_files_on_disk", _delete)
    return taken


@pytest.mark.asyncio
async def test_an_uploader_takes_out_their_own_files_and_the_game_stays(shelf, no_disk):
    from endpoints.library.library_router import remove_my_files
    from handler.library import quota

    assert await quota.used_bytes(BOB) == 55
    out = await remove_my_files.__wrapped__(_request(BOB), 40)

    files, games = await shelf.rows()
    assert sorted(no_disk) == [2, 3], "usunieto nie te pliki z dysku"
    assert 2 not in files and 3 not in files, "wiersze plikow boba zostaly"
    assert 1 in files and 4 in files, "zabrano pliki wlascicielki gry"
    assert 40 in games, "zabrano cala cudza gre"
    assert out["removed"] == 2
    assert await quota.used_bytes(BOB) == 0, "limit boba nie wrocil"


@pytest.mark.asyncio
async def test_the_owner_taking_out_their_files_takes_the_unnamed_ones_too(shelf, no_disk):
    """A file with no account on it counts against the game's owner, so it is
    hers - the same sentence the bar sums with."""
    from endpoints.library.library_router import remove_my_files

    await remove_my_files.__wrapped__(_request(ALICE), 40)
    assert sorted(no_disk) == [1, 4]


@pytest.mark.asyncio
async def test_taking_files_out_of_a_game_the_caller_cannot_see_answers_404(shelf, no_disk):
    from endpoints.library.library_router import remove_my_files

    with pytest.raises(HTTPException) as refusal:
        await remove_my_files.__wrapped__(_request(BOB), 50)
    assert refusal.value.status_code == 404
    assert no_disk == []


# ── An administrator takes such files over ───────────────────────────────────

@pytest.mark.asyncio
async def test_an_administrator_takes_over_the_files_an_uploader_added(shelf):
    from endpoints.library.library_router import ClaimBody, claim_library_games
    from handler.library import quota

    out = await claim_library_games.__wrapped__(
        _request(ADMIN_ID, ADMIN, admin=True), ClaimBody(game_ids=[40], from_user_id=BOB))

    files, games = await shelf.rows()
    assert files[2].published_by == ADMIN_ID and files[3].published_by == ADMIN_ID, (
        "pliki boba w cudzej grze nie przeszly na admina"
    )
    assert files[1].published_by == ALICE and files[4].published_by is None, (
        "przejecie ruszylo pliki, ktore nie byly boba"
    )
    assert games[40].published_by == ALICE, "przejeto cala gre zamiast plikow boba"
    assert out["claimed"] == 1 and out["skipped"] == 0
    assert await quota.used_bytes(BOB) == 0


@pytest.mark.asyncio
async def test_a_game_the_account_added_nothing_to_is_still_skipped(shelf):
    from endpoints.library.library_router import ClaimBody, claim_library_games

    out = await claim_library_games.__wrapped__(
        _request(ADMIN_ID, ADMIN, admin=True), ClaimBody(game_ids=[41], from_user_id=BOB))
    _files, games = await shelf.rows()
    assert out["skipped"] == 1 and games[41].published_by == ALICE


# ── The list says what a deletion takes ──────────────────────────────────────

@pytest.mark.asyncio
async def test_the_owners_row_says_how_many_files_other_accounts_added(shelf):
    from handler.library import quota

    alice = {g["id"]: g for g in await quota.owned_games(ALICE) if g["kind"] == "game"}
    assert alice[40]["can_delete"] is True
    assert alice[40]["others_file_count"] == 2, (
        "wiersz wlascicielki nie mowi, ile cudzych plikow zniknie z gra"
    )
    bob = {g["id"]: g for g in await quota.owned_games(BOB) if g["kind"] == "game"}
    assert bob[40]["can_delete"] is False and bob[40]["file_count"] == 2
    assert bob[40]["others_file_count"] == 0


# ── One title, two folders ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_older_of_two_games_with_one_title_keeps_the_plain_folder(shelf):
    from endpoints.library.upload_router import _folder_title_for

    _files, games = await shelf.rows()
    assert await _folder_title_for(games[41]) == "Doom"
    assert await _folder_title_for(games[42]) == "Doom [doom-1]", (
        "dwa wpisy o tym samym tytule dziela jeden folder na dysku"
    )
    assert await _folder_title_for(games[40]) == "Ion Fury"


@pytest.mark.asyncio
async def test_the_same_title_on_another_shelf_is_another_folder_already(shelf):
    from endpoints.library.upload_router import _folder_title_for

    async with shelf.maker() as session:
        session.add(LibraryGame(id=60, title="Doom", slug="doom-2", source="custom",
                                is_active=True, in_default_library=False, published_by=BOB))
        session.add(LibraryMembership(library_game_id=60, library_id=9))
        await session.commit()
    _files, games = await shelf.rows()
    assert await _folder_title_for(games[60]) == "Doom"


def test_every_manual_upload_names_the_folder_that_way():
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    upload = io.open(backend / "endpoints/library/upload_router.py", encoding="utf-8").read()
    at = upload.index("async def upload_game_file(")
    assert "_dest_dir_for(\n            await _folder_title_for(game)" in upload[at:at + 1500].replace("\r\n", "\n")
    at = upload.index("async def queue_url_download(")
    assert "storage_title or await _folder_title_for(game)" in upload[at:at + 3000]
