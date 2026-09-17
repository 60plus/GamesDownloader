"""Taking away the upload permission does not stop a running torrent. It hands
it over.

THE OWNER DECIDED BOTH HALVES, after watching a demotion do nothing:
"zmienilem uprawnienia z uploader na user a torrent dalej sie pobiera" - and,
asked what should happen, chose to leave the transfer running and "przepisac na
admina tak jak przy przejeciu gry".

WHY NOT STOP IT. The same question was settled for ROM downloads earlier in this
release, and the answer there was that losing a permission is not a reason to
destroy work already in progress. Stopping a torrent that is twenty gigabytes in
would be exactly that, and Transmission has no way to give those hours back.

WHY HAND IT OVER RATHER THAN LEAVE IT. A transfer still belonging to an account
that may no longer upload is an account still spending an allowance it no longer
has, on a game it will own when the transfer lands. Handing it to the
administrator who took the permission away settles all three at once: the bytes
leave the demoted account's quota, the finished game belongs to somebody who may
have it, and the transfer stays visible to the one person who can now act on it.

WHAT A CLAIM DOES NOT TOUCH, and this is the half that is easy to lose: who
brought it in. `claim_writes` in handler/library/ownership.py returns exactly one
field for that reason, with the whole point of the function being the fields it
leaves alone. A torrent row had nowhere to keep that, because the account that
queued it was also its owner and one column said both. So it gets a second one,
the same way `library_games.uploaded_by` was added when a game first needed to
answer both questions.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.torrent_download import TorrentDownload
from models.user import User

UPLOADER, ADMIN, BYSTANDER = 3, 1, 7


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        # The two tables this row points at have to exist first: a foreign key
        # takes its column type from the one it references, and without them
        # `game_id` compiles to no type at all.
        for table in (User, LibraryGame, LibraryFile, TorrentDownload):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        for row_id, status, owner, game_id in (
            (1, "downloading", UPLOADER,  None),
            (2, "paused",      UPLOADER,  None),
            (3, "complete",    UPLOADER,  99),
            (4, "downloading", BYSTANDER, None),
            # Finished downloading and still being filed: virus-scanned, then
            # copied between bind mounts, which takes minutes. Not a game yet.
            (5, "complete",    UPLOADER,  None),
        ):
            session.add(TorrentDownload(
                id=row_id, title=f"gra {row_id}", os="windows",
                download_dir=f"/d/{row_id}", status=status, game_id=game_id,
                created_by="gdtest", created_by_id=owner, uploaded_by_id=owner,
            ))
        await session.commit()

    async with maker() as session:
        yield session
    await engine.dispose()


async def _rows(session):
    return {r.id: r for r in (await session.execute(select(TorrentDownload))).scalars()}


@pytest.mark.asyncio
async def test_a_running_transfer_is_handed_to_the_administrator(db):
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    moved = await hand_running_torrents_to(UPLOADER, ADMIN, session=db)

    rows = await _rows(db)
    assert rows[1].created_by_id == ADMIN, (
        "trwajacy transfer nadal nalezy do konta, ktore juz nie moze wgrywac, "
        "wiec zajmuje jego limit i skonczy jako jego gra"
    )
    assert rows[2].created_by_id == ADMIN, "wstrzymany transfer tez trzeba przejac"
    assert moved == 3


@pytest.mark.asyncio
async def test_a_transfer_still_being_filed_is_handed_over_too(db):
    """"complete" is written before the game is, so a transfer being virus
    scanned and copied reads as finished for minutes without being a game. Left
    out of the handover, its game was filed under the account that had just lost
    the right to upload."""
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    await hand_running_torrents_to(UPLOADER, ADMIN, session=db)

    rows = await _rows(db)
    assert rows[5].created_by_id == ADMIN, (
        "transfer w trakcie wkladania do biblioteki zostal przy koncie, ktore "
        "wlasnie stracilo prawo wgrywania - jego gra trafi do tego konta"
    )
    assert rows[5].uploaded_by_id == UPLOADER


@pytest.mark.asyncio
async def test_who_brought_it_in_is_not_rewritten(db):
    """The half a claim is careful not to touch. Losing it would erase the
    uploader from the game the transfer becomes."""
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    await hand_running_torrents_to(UPLOADER, ADMIN, session=db)

    rows = await _rows(db)
    assert rows[1].uploaded_by_id == UPLOADER, (
        "przejecie skasowalo slad po tym, kto ten transfer wniosl"
    )
    assert rows[1].created_by == "gdtest", (
        "nazwa konta, ktore zaczelo transfer, zostala nadpisana"
    )


@pytest.mark.asyncio
async def test_a_finished_transfer_is_left_alone(db):
    """It is already a game, and a game has its own claim - with its own audit
    trail and its own route. Reaching in here would be a second way to do the
    same thing, disagreeing with the first the day one of them changes."""
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    await hand_running_torrents_to(UPLOADER, ADMIN, session=db)

    rows = await _rows(db)
    assert rows[3].created_by_id == UPLOADER, (
        "zakonczony transfer zostal przejety tedy, zamiast przez przejecie gry"
    )


@pytest.mark.asyncio
async def test_nobody_else_is_touched(db):
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    await hand_running_torrents_to(UPLOADER, ADMIN, session=db)

    rows = await _rows(db)
    assert rows[4].created_by_id == BYSTANDER


@pytest.mark.asyncio
async def test_a_claim_with_no_claimant_is_refused(db):
    """Blanking the owner would not be a claim. `claim_writes` refuses the same
    thing for the same reason: an unowned transfer belongs to nobody, here and
    in the quota, so the bytes would simply stop counting anywhere."""
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    with pytest.raises(ValueError):
        await hand_running_torrents_to(UPLOADER, None, session=db)

    rows = await _rows(db)
    assert rows[1].created_by_id == UPLOADER


# ── When it happens ──────────────────────────────────────────────────────────

def _account(role, **perms):
    return SimpleNamespace(id=UPLOADER, role=role, enabled=True, permissions=perms)


def test_losing_the_upload_permission_is_what_triggers_it():
    from endpoints.users import lost_upload

    assert lost_upload(_account("uploader"), _account("user")) is True, (
        "degradacja uploadera do zwyklego konta nie liczy sie jako utrata "
        "prawa do wgrywania"
    )


def test_a_revoked_chip_counts_even_though_the_role_did_not_change():
    """`_PERM_REVOKE` takes the scope away without touching the role, which is
    the whole reason role-reading rules drift from scope-gated routes."""
    from endpoints.users import lost_upload

    assert lost_upload(_account("uploader"), _account("uploader", upload=False)) is True


def test_an_account_that_keeps_the_permission_is_not_disturbed():
    """THE LEGAL CASE, and a specific one: raising somebody's quota by a
    gigabyte decides nothing about who owns a transfer. The socket rule next
    door already had to learn this - it used to compare the permissions
    dictionary whole and kicked a live connection over a changed allowance."""
    from endpoints.users import lost_upload

    before = _account("uploader", upload_quota_bytes=1)
    after = _account("uploader", upload_quota_bytes=2)
    assert lost_upload(before, after) is False, (
        "podniesienie limitu przepisuje cudze transfery na admina"
    )
    assert lost_upload(_account("user"), _account("uploader")) is False, (
        "awans na uploadera liczy sie jako utrata uprawnienia"
    )


def test_switching_an_account_off_counts_as_losing_it():
    """A disabled account cannot upload anything, whatever its role says."""
    from endpoints.users import lost_upload

    on = _account("uploader")
    off = _account("uploader")
    off.enabled = False
    assert lost_upload(on, off) is True


# ── Deleting the account ─────────────────────────────────────────────────────

@pytest.fixture
def deleting(monkeypatch):
    """`delete_user` as the route runs it, with the account store and the
    socket layer replaced. Every call is recorded in order."""
    from endpoints import users as U
    from handler import socket_handler
    from handler.torrent import torrent_ownership as T

    calls: list = []

    async def _get(user_id):
        return SimpleNamespace(id=user_id, username="gdtest")

    async def _delete(user):
        calls.append(("delete", user.id))

    async def _drop(user_id):
        calls.append(("drop", user_id))

    async def _hand(previous_owner_id, admin_id, **_k):
        calls.append(("hand", previous_owner_id, admin_id))
        return 1

    monkeypatch.setattr(U._users_db, "get_by_id", _get)
    monkeypatch.setattr(U._users_db, "delete", _delete)
    monkeypatch.setattr(socket_handler, "drop_sockets_for_user", _drop)
    monkeypatch.setattr(T, "hand_running_torrents_to", _hand)

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ADMIN), scopes=set()))
    return SimpleNamespace(module=U, calls=calls, request=request, torrents=T)


@pytest.mark.asyncio
async def test_deleting_an_account_hands_its_transfers_over(deleting):
    """The strongest way of taking the right to upload away did not do what the
    weaker ones do. The transfer ran on under an id that no longer exists, and
    when it landed its game was filed under that id - or the insert failed on
    the foreign key after the row had already been written "complete", so it
    read as a success with no game and no message."""
    await deleting.module.delete_user.__wrapped__(deleting.request, UPLOADER)

    assert ("hand", UPLOADER, ADMIN) in deleting.calls, (
        "usuniecie konta zostawia jego torrenty przy koncie, ktorego juz nie ma"
    )
    assert deleting.calls.index(("hand", UPLOADER, ADMIN)) < deleting.calls.index(
        ("delete", UPLOADER)), "transfery przekazane dopiero po zniknieciu konta"


@pytest.mark.asyncio
async def test_an_account_is_deleted_even_if_the_handover_fails(deleting, monkeypatch):
    """Deleting the account is what was asked for. A handover that cannot be
    done is logged, as it is when a permission is taken away."""
    async def _broken(*_a, **_k):
        raise RuntimeError("baza nie odpowiada")

    monkeypatch.setattr(deleting.torrents, "hand_running_torrents_to", _broken)

    await deleting.module.delete_user.__wrapped__(deleting.request, UPLOADER)

    assert ("delete", UPLOADER) in deleting.calls
    assert ("drop", UPLOADER) in deleting.calls
