"""A transfer still on its way counts against the quota it will land on.

Found by the 1.0.34 audit (#2) and put to the owner, who said yes: every check
weighed ONE incoming transfer against the bytes that had already landed. A
torrent adds nothing to that sum until its game is filed, hours later, so an
account with a 10 GB allowance and nothing stored could queue five 9 GB
torrents one after another. Each saw 0 used and 9 GB coming, each fitted, and
the server fetched 45 GB for a 10 GB account.

So the bytes a transfer is bringing count from the moment its size is known:

  in flight     a torrent that is downloading, paused, or finished and still
                being filed (virus scanned and copied, which takes minutes).
                The same "not landed" the handover to an administrator uses,
                spelled once in torrent_ownership.
  not counted   a finished one that became a game (its files count instead),
                one that was refused or failed, one somebody dismissed.

Every door that admits bytes asks the new total, and a transfer being weighed
leaves ITSELF out of it - resuming a paused 9 GB torrent is not a second 9 GB.

The "My uploads" bar keeps showing what has landed: its figure must agree with
the list of games under it, and a transfer is not a game yet.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.torrent_download import TorrentDownload
from models.user import User

GB = 1024 ** 3
UPLOADER, BYSTANDER = 3, 7
LIMIT = 20 * GB

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        from models.library import Library, LibraryMembership
        from models.rom import Rom
        from models.rom_added_file import RomAddedFile
        from models.rom_platform import RomPlatform
        for table in (User, LibraryGame, LibraryFile, TorrentDownload,
                      RomPlatform, Rom, RomAddedFile, Library, LibraryMembership):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)

    async with maker() as session:
        # A game the uploader already has on the shelf: 1 GB landed.
        session.add(LibraryGame(id=99, title="Landed", slug="landed", source="custom",
                                is_active=True, published_by=UPLOADER))
        session.add(LibraryFile(id=1, library_game_id=99, filename="a.zip",
                                file_path="games/CUSTOM/Landed/a.zip", source="custom",
                                size_bytes=1 * GB, published_by=UPLOADER))
        for row_id, status, owner, game_id, size in (
            (1, "downloading", UPLOADER,  None, 9 * GB),
            (2, "paused",      UPLOADER,  None, 2 * GB),
            # Finished and still being filed: not a game yet.
            (3, "complete",    UPLOADER,  None, 3 * GB),
            # Finished and filed: its bytes are the 1 GB of files above.
            (4, "complete",    UPLOADER,  99,   1 * GB),
            (5, "error",       UPLOADER,  None, 7 * GB),
            (6, "removed",     UPLOADER,  None, 11 * GB),
            (7, "downloading", BYSTANDER, None, 13 * GB),
            # Queued before transfers recorded an account. `== None` is
            # `IS NULL` in SQL, so asking for "no account" would find it.
            (9, "downloading", None,      None, 17 * GB),
        ):
            session.add(TorrentDownload(
                id=row_id, title=f"gra {row_id}", os="windows",
                download_dir=f"/d/{row_id}", status=status, game_id=game_id,
                total_size=size, created_by="gdtest", created_by_id=owner,
                uploaded_by_id=owner,
            ))
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.fixture
def limited(monkeypatch):
    """Every account has the same allowance, so the figures below are exact."""
    async def _limit(_user):
        return LIMIT

    monkeypatch.setattr("handler.library.quota.limit_for", _limit)

    class _Users:
        async def get_by_id(self, uid):
            return SimpleNamespace(id=uid, username="gdtest")

    monkeypatch.setattr("handler.database.users_handler.UsersHandler", _Users)


# ── The sum ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_what_is_on_its_way_is_added_up(db):
    from handler.library import quota

    assert await quota.in_flight_bytes(UPLOADER) == (9 + 2 + 3) * GB, (
        "suma transferow w drodze liczy zle: powinny wejsc pobierany, wstrzymany "
        "i skonczony w trakcie wkladania; nie powinny: wlozony do biblioteki, "
        "odrzucony, odrzucony przez czlowieka ani cudzy"
    )


@pytest.mark.asyncio
async def test_a_transfer_being_weighed_leaves_itself_out(db):
    from handler.library import quota

    assert await quota.in_flight_bytes(UPLOADER, except_torrent_id=1) == (2 + 3) * GB


@pytest.mark.asyncio
async def test_nobody_is_charged_for_nothing(db):
    from handler.library import quota

    assert await quota.in_flight_bytes(None) == 0


@pytest.mark.asyncio
async def test_what_is_spoken_for_is_what_landed_plus_what_is_coming(db):
    from handler.library import quota

    assert await quota.used_bytes(UPLOADER) == 1 * GB, "pasek ma dalej pokazywac to, co wyladowalo"
    assert await quota.committed_bytes(UPLOADER) == (1 + 9 + 2 + 3) * GB


def test_the_handover_and_the_quota_read_one_definition_of_not_landed():
    """Two copies of "which transfers are still coming" would disagree the day
    one of them changes - the handover learned about "complete without a game"
    a release after it was first written."""
    ownership = io.open(BACKEND / "handler" / "torrent" / "torrent_ownership.py",
                        encoding="utf-8").read()
    quota_src = io.open(BACKEND / "handler" / "library" / "quota.py", encoding="utf-8").read()
    handover = ownership[ownership.index("async def hand_running_torrents_to("):]
    assert "not_landed()" in handover
    assert "not_landed()" in quota_src


# ── Every door asks it ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_second_torrent_file_that_does_not_fit_beside_the_first_is_refused(
        db, limited, monkeypatch):
    """The owner's example, in the audit's numbers: 1 GB landed and 14 GB on
    its way leave 5 GB of a 20 GB allowance, so a 9 GB .torrent is refused
    before anything downloads."""
    from endpoints.torrent import torrent_router as R

    monkeypatch.setattr("handler.torrent.torrent_size.total_bytes", lambda _c: 9 * GB)
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=UPLOADER)))

    with pytest.raises(HTTPException) as refusal:
        await R._refuse_if_it_does_not_fit(request, b"torrent")

    assert refusal.value.status_code == 413
    assert refusal.value.refusal["room"] == 5 * GB, (
        "odmowa podaje miejsce bez transferow w drodze"
    )


@pytest.mark.asyncio
async def test_a_torrent_file_that_fits_beside_the_others_goes_through(db, limited, monkeypatch):
    from endpoints.torrent import torrent_router as R

    monkeypatch.setattr("handler.torrent.torrent_size.total_bytes", lambda _c: 5 * GB)
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=UPLOADER)))

    assert await R._refuse_if_it_does_not_fit(request, b"torrent") == 5 * GB, (
        "zmieszczony .torrent nie zwraca swojego rozmiaru, wiec wiersz nie dostanie "
        "go od razu i drugi .torrent dodany chwile pozniej go nie zobaczy"
    )


@pytest.mark.asyncio
async def test_a_magnet_is_weighed_against_the_others_but_not_itself(db, limited):
    """Row 1 is 9 GB; the others on their way are 5 GB and 1 GB has landed.
    Counting itself would make 24 GB of a 20 GB allowance and refuse a transfer
    that fits - the resume button asks this very question about a paused row
    whose size is already stored."""
    from handler.torrent import seed_monitor as M

    row = SimpleNamespace(id=1, created_by_id=UPLOADER, total_size=9 * GB)
    assert await M._over_quota(row, 9 * GB) is False, (
        "transfer zostal policzony dwa razy: raz jako w drodze, raz jako wazony"
    )


@pytest.mark.asyncio
async def test_a_magnet_that_does_not_fit_beside_the_others_is_over(db, limited):
    from handler.torrent import seed_monitor as M

    row = SimpleNamespace(id=8, created_by_id=UPLOADER, total_size=0)
    assert await M._over_quota(row, 9 * GB) is True, (
        "magnet 9 GB przeszedl, choc w drodze jest juz 14 GB, a wyladowal 1 GB z 20 GB"
    )


@pytest.mark.asyncio
async def test_the_refusal_message_counts_the_same_room(db, limited):
    from handler.torrent import seed_monitor as M

    row = SimpleNamespace(id=8, created_by_id=UPLOADER)
    assert await M._room_left(row) == 5 * GB


@pytest.mark.asyncio
async def test_background_fetches_get_a_ceiling_that_leaves_room_for_the_torrents(db, limited):
    """URL uploads, plugin catalogue downloads and ROM downloads all take their
    ceiling from here."""
    from handler.library import quota

    user = SimpleNamespace(id=UPLOADER)
    assert await quota.ceiling_for(user, 100 * GB) == 5 * GB


def _function(source: str, head: str) -> str:
    """From `head` to the next top-level statement. A signature's closing
    `) -> dict:` starts with a bracket, so it does not end the slice."""
    at = source.index(head)
    nxt = re.search(r"\n(?=[@A-Za-z_#])", source[at + len(head):])
    return source[at:at + len(head) + (nxt.start() if nxt else len(source))]


def test_a_file_upload_asks_the_total_with_transfers_on_their_way():
    source = io.open(BACKEND / "endpoints" / "library" / "upload_router.py", encoding="utf-8").read()
    route = _function(source, "async def upload_game_file(")
    # Through the reservation since the uploads running side by side learned to
    # see each other (test_uploads_running_side_by_side_see_each_other); it
    # reads what landed with `committed_bytes`.
    assert "quota.reservation_for(" in route, (
        "wgranie pliku liczy miejsce bez transferow w drodze"
    )
    quota_src = io.open(BACKEND / "handler" / "library" / "quota.py", encoding="utf-8").read()
    landed = _function(quota_src, "class Reservation:")
    assert "await committed_bytes(self.user_id, with_writing=False)" in landed


@pytest.mark.asyncio
async def test_the_row_keeps_the_size_it_was_given(db):
    from sqlalchemy import select

    from endpoints.torrent import torrent_router as R

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=UPLOADER, username="gdtest"),
        scopes={Scope.LIBRARY_UPLOAD}))
    td = await R._create_torrent_download(
        request, "Gra", "windows", "/d/new", transmission_id=41, info_hash="ab" * 20,
        total_size=4 * GB)
    magnet = await R._create_torrent_download(
        request, "Magnet", "windows", "/d/mag", transmission_id=42, info_hash="cd" * 20)

    async with db() as session:
        rows = {r.id: r for r in (await session.execute(select(TorrentDownload))).scalars()}
    assert rows[td.id].total_size == 4 * GB, "wiersz .torrent nie ma rozmiaru, ktory trasa juz znala"
    assert rows[magnet.id].total_size == 0, (
        "magnet dostal rozmiar, ktorego nikt nie zna - monitor uzna, ze juz go zwazyl"
    )


def test_a_torrent_file_row_is_written_with_its_size():
    """The monitor writes the size on its first tick, ten seconds later. A second
    .torrent added inside those ten seconds would not see the first."""
    source = io.open(BACKEND / "endpoints" / "torrent" / "torrent_router.py", encoding="utf-8").read()
    for route in ("async def add_torrent_file(", "async def add_torrent_url("):
        body = _function(source, route)
        assert re.search(r"total_size=\w+", body), f"{route} nie zapisuje rozmiaru na wierszu"


def test_no_door_that_admits_bytes_asks_only_what_has_landed():
    """`used_bytes` is what landed. It is right for the bar and wrong at every
    door: each door below admits bytes, and asking only what landed is the gap.
    New doors are caught here too."""
    allowed = {
        # The "My uploads" bar and the two admin views of it: a figure that has
        # to agree with the list of games drawn under it.
        BACKEND / "endpoints" / "library" / "library_router.py",
        # Where the sum and the total are defined.
        BACKEND / "handler" / "library" / "quota.py",
    }
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path in allowed:
            continue
        text = io.open(path, encoding="utf-8", errors="ignore").read()
        if re.search(r"\bused_bytes\(", text):
            offenders.append(str(path.relative_to(BACKEND)))
    assert not offenders, f"te miejsca wpuszczaja bajty, liczac tylko to, co wyladowalo: {offenders}"

    quota_src = io.open(BACKEND / "handler" / "library" / "quota.py", encoding="utf-8").read()
    assert "committed_bytes(" in _function(quota_src, "async def ceiling_for(")
