"""A magnet that does not fit is refused, at the first moment anyone can tell.

THE OWNER SETTLED THE SHAPE: "myslalem ze jak jest za duzy to poprostu go nie
przyjmie". A .torrent already behaves that way - the file carries its own size,
so the route weighs it and answers 413 before anything moves. A magnet cannot:
it is a hash, and the totals arrive from peers minutes later. The earliest
refusal available is therefore the tick on which the size becomes known, and
that is where this happens.

WHY REMOVING HERE IS NOT THE DELETION THIS FILE IS FORBIDDEN TO DO. An earlier
version cancelled over-quota transfers with `delete_data=True` and was reverted
for three reasons. The shape here answers all three:
  * "an ordinary upload could condemn a transfer that was legal when it
    started" - the weighing happens ONCE, on the tick the size arrives, and
    never again. Nothing that was admitted is reconsidered later.
  * "`transmission_id` is session-scoped and can point at a DIFFERENT torrent
    after the daemon restarts" - this is the real danger and it is why nothing
    is deleted unless `info_hash` matches what the daemon reports. The column
    was written by both queue routes and read by nothing at all until now.
  * "hours of transfer thrown away" - by construction this is the first tick
    that could tell, so what is on the disk is at most one poll interval of a
    transfer the account was never allowed to have.

AND THE MEASUREMENT MUST NOT SPEND THE ONE CHANCE. `_over_quota` used to answer
False on any failure, while the same tick wrote `total_size` and closed the
latch for good - so a single failed lookup lifted the limit permanently and
said nothing above DEBUG. "Could not tell" is now its own answer and the tick
asks again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

OURS = "abc123def456"
SOMEBODY_ELSES = "999999999999"


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
def world(monkeypatch):
    """A magnet whose size has just landed, and a daemon that answers."""
    from handler.database import session as S
    from handler.socket_handler import sio
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    row = SimpleNamespace(
        id=4,
        transmission_id=2,
        info_hash=OURS,
        total_size=0,          # nothing knew the size until this tick
        created_by_id=3,
        status="downloading",
    )
    monkeypatch.setattr(S, "async_session_factory", _Factory([row]))

    daemon = SimpleNamespace(hash=OURS, downloaded=12_000_000)

    async def _get_torrent(_tid):
        return {
            "hashString":     daemon.hash,
            "status":         4,
            "percentDone":    0.0002,
            "totalSize":      56_373_525_225,     # 52.5 GB
            "downloadedEver": daemon.downloaded,
            "rateDownload":   25_000_000,
            "eta":            1400,
            "error":          0,
        }

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)

    removed: list[dict] = []

    async def _remove(tid, *, delete_data=False):
        removed.append({"id": tid, "delete_data": delete_data})
        return True

    monkeypatch.setattr(TH.transmission_handler, "remove_torrent", _remove)

    paused: list[int] = []

    async def _pause(tid):
        paused.append(tid)
        return True

    monkeypatch.setattr(TH.transmission_handler, "pause_torrent", _pause)

    written: list[dict] = []

    async def _update(_id, values):
        written.append(dict(values))

    monkeypatch.setattr(M, "_update_download", _update)

    said: list[tuple] = []

    async def _emit(event, payload=None, **_k):
        said.append((event, payload))

    monkeypatch.setattr(sio, "emit", _emit)

    # The verdict itself has its own tests below; here it is the answer that
    # matters, not how it was reached.
    async def _over(_td, _size):
        return True

    monkeypatch.setattr(M, "_over_quota", _over)

    # Nothing else holds this torrent here. The other case is
    # test_a_torrent_another_row_holds_is_left_to_it.py.
    async def _nobody_else(_td):
        return False

    monkeypatch.setattr(M, "held_by_another", _nobody_else)

    return SimpleNamespace(module=M, row=row, daemon=daemon, removed=removed,
                           paused=paused, written=written, said=said)


# ── The refusal ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_it_is_taken_off_the_daemon_with_what_it_had_started_fetching(world):
    await world.module._check_downloads()

    # By its hash: the one identity the monitor has confirmed (1.0.34 audit,
    # finding #1). The number 2 on the row is only what the daemon called it once.
    assert world.removed == [{"id": OURS, "delete_data": True}], (
        "transfer ponad limit nie zostal odrzucony - a wlasciciel prosil, zeby "
        f"go po prostu nie przyjmowac; zamiast tego: {world.removed or 'nic'}"
    )


@pytest.mark.asyncio
async def test_the_row_records_why_so_the_account_can_find_out(world):
    await world.module._check_downloads()

    said = " ".join(str(w.get("error_msg", "")) for w in world.written)
    assert "quota" in said.lower() or "limit" in said.lower(), (
        f"wiersz nie mowi, dlaczego transfer zniknal: {world.written}"
    )
    # Both figures, so the account can tell whether to free one game or twenty.
    assert "GB" in said or "MB" in said or "B" in said, (
        f"powod podany w surowych bajtach: {said}"
    )

    # AND IT MUST NOT BE WRITTEN AS "removed". This assertion said exactly that
    # for a few hours, and it was wrong: the listing hides "removed", because
    # that is what the cancel route writes when a PERSON dismisses a transfer.
    # So the one row whose entire purpose is to explain itself was the one row
    # nobody could see, and the account was back to watching a download vanish
    # without a word. The two meanings no longer share a word - see
    # REFUSED_STATUS next to the code that writes it.
    from endpoints.torrent.torrent_router import DISMISSED_STATUS

    stany = [w.get("status") for w in world.written if "status" in w]
    assert stany, f"stan wiersza nie zostal w ogole zapisany: {world.written}"
    assert DISMISSED_STATUS not in stany, (
        f"odmowa zapisuje sie jako zdjeta z listy, wiec zniknie razem z "
        f"powodem: {world.written}"
    )


@pytest.mark.asyncio
async def test_the_owner_is_told_rather_than_everybody(world):
    await world.module._check_downloads()

    events = [e for e, _ in world.said]
    assert events, "nikt nie zostal powiadomiony o odmowie"
    shouted = [e for e, p in world.said if p is None]
    assert not shouted


# ── The interlock that makes deleting safe at all ────────────────────────────

@pytest.mark.asyncio
async def test_a_torrent_that_is_not_ours_is_not_touched_at_all(world):
    """`transmission_id` is a number the daemon reuses across restarts, and two
    rows on the live install already share id 1.

    This assertion got STRICTER while the rest of this file was being written,
    and the change is worth recording. It first said the transfer had to be
    paused instead of removed - the cautious half of the refusal. That is still
    wrong: if the daemon is holding a different torrent under this number, then
    pausing by the number stops A STRANGER'S transfer. Not ours means hands off,
    not gently. The monitor now leaves the row alone and says so in the log.
    """
    world.daemon.hash = SOMEBODY_ELSES

    await world.module._check_downloads()

    assert world.removed == [], (
        "skasowano torrent, ktorego tozsamosci nie potwierdzono - to droga do "
        "skasowania cudzych danych po restarcie demona"
    )
    assert world.paused == [], (
        "wstrzymano torrent, ktory nalezy do kogos innego, bo demon przydzielil "
        "ten numer ponownie"
    )
    assert not world.written, (
        f"zapisano cos do wiersza na podstawie CUDZEGO transferu: {world.written}"
    )


@pytest.mark.asyncio
async def test_nothing_is_deleted_when_the_row_never_recorded_a_hash(world):
    """A row queued before the hash was stored cannot be identified, so it gets
    the cautious half of the rule rather than the destructive one."""
    world.row.info_hash = None

    await world.module._check_downloads()

    assert world.removed == []
    assert world.paused == [2]


# ── After a daemon restart the number names somebody else ────────────────────

def _renumbered(world, monkeypatch):
    """A daemon that restarted since this row was written: the row's number 2
    now belongs to a stranger's torrent, and this one is found only by its hash.
    Returns every reference the tick asked the daemon about."""
    from handler.torrent import transmission_handler as TH

    asked: list[object] = []

    async def _get_torrent(ref):
        asked.append(ref)
        return {
            "hashString":     OURS if ref == OURS else SOMEBODY_ELSES,
            "status":         4,
            "percentDone":    0.0002,
            "totalSize":      56_373_525_225,
            "downloadedEver": world.daemon.downloaded,
            "rateDownload":   25_000_000,
            "eta":            1400,
            "error":          0,
        }

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)
    return asked


@pytest.mark.asyncio
async def test_the_tick_finds_this_torrent_by_its_own_hash(world, monkeypatch):
    """1.0.34 audit, finding #1. Asked by the number after a restart, the daemon
    answered about the stranger, the identity check left this row alone, and the
    transfer went unwatched and unweighed for good."""
    asked = _renumbered(world, monkeypatch)

    await world.module._check_downloads()

    assert asked == [OURS], (
        f"monitor pyta demona po numerze sprzed restartu: {asked}"
    )


@pytest.mark.asyncio
async def test_a_refusal_after_a_restart_removes_this_torrent_and_not_the_one_under_its_old_number(world, monkeypatch):
    """The hole the first fix for finding #1 opened in this file. Once the tick
    finds the torrent by its hash, the identity check confirms the HASH and says
    nothing about the number on the row - so removing by that number, with the
    data, took the stranger's transfer and its files off the disk."""
    _renumbered(world, monkeypatch)

    await world.module._check_downloads()

    assert world.removed == [{"id": OURS, "delete_data": True}], (
        "odmowa usunela z demona torrent po numerze sprzed restartu - razem z "
        f"danymi kogos innego: {world.removed}"
    )


# ── The legal case: this must still get through ──────────────────────────────

@pytest.mark.asyncio
async def test_a_transfer_that_fits_is_not_touched(world, monkeypatch):
    """The gate has to let the ordinary case past. A transfer within the
    allowance is neither removed nor paused, and goes on reporting progress."""
    async def _fits(_td, _size):
        return False

    monkeypatch.setattr(world.module, "_over_quota", _fits)

    await world.module._check_downloads()

    assert world.removed == [] and world.paused == []
    assert any(e == "torrent:download_progress" for e, _ in world.said), (
        "transfer miesczacy sie w limicie przestal raportowac postep"
    )


@pytest.mark.asyncio
async def test_a_magnet_with_no_size_yet_is_left_alone(world, monkeypatch):
    """Every magnet looks like this on its first tick. Refusing on it would
    refuse them all."""
    from handler.torrent import transmission_handler as TH

    async def _no_size(_tid):
        return {"hashString": OURS, "status": 4, "percentDone": 0.0,
                "totalSize": 0, "downloadedEver": 0, "rateDownload": 0,
                "eta": -1, "error": 0}

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _no_size)

    await world.module._check_downloads()

    assert world.removed == [] and world.paused == []


# ── The one chance must not be spent on a failed measurement ─────────────────

@pytest.mark.asyncio
async def test_a_weighing_that_could_not_be_done_is_asked_again(world, monkeypatch):
    """The latch is the stored size. Writing it after a lookup that failed
    lifted the limit for good, and left only a DEBUG line behind."""
    async def _cannot_tell(_td, _size):
        return None

    monkeypatch.setattr(world.module, "_over_quota", _cannot_tell)

    await world.module._check_downloads()

    assert world.removed == [] and world.paused == []
    wrote_size = [w for w in world.written if "total_size" in w]
    assert not wrote_size, (
        "nieudany pomiar zapisal rozmiar, czyli zamknal jedyna okazje do "
        f"zwazenia tego transferu: {wrote_size}"
    )


@pytest.mark.asyncio
async def test_the_verdict_says_could_not_tell_rather_than_it_fits(monkeypatch):
    """`_over_quota` answered False for "no idea" and False for "it fits", and
    the caller could not tell the two apart."""
    from handler.torrent import seed_monitor as M

    class _Boom:
        def __getattr__(self, _name):
            raise RuntimeError("baza nie odpowiada")

    monkeypatch.setattr("handler.database.users_handler.UsersHandler", _Boom)

    verdict = await M._over_quota(SimpleNamespace(id=1, created_by_id=3), 10)
    assert verdict is None, (
        "nieudany odczyt nadal udaje odpowiedz 'miesci sie', wiec limit znika "
        "po cichu"
    )


@pytest.mark.asyncio
async def test_no_limit_in_force_is_a_real_answer_not_a_failure(monkeypatch):
    """"This account has no limit" is a decided yes, and must not be confused
    with "the lookup broke"."""
    from handler.torrent import seed_monitor as M

    class _Users:
        async def get_by_id(self, _uid):
            return SimpleNamespace(id=3, username="gdtest")

    monkeypatch.setattr("handler.database.users_handler.UsersHandler", _Users)

    async def _no_limit(_user):
        return 0

    monkeypatch.setattr("handler.library.quota.limit_for", _no_limit)

    verdict = await M._over_quota(SimpleNamespace(id=1, created_by_id=3), 10**12)
    assert verdict is False, "konto bez limitu zostalo potraktowane jak awaria"


# ── A refusal the daemon did not accept is not a refusal ─────────────────────

@pytest.mark.asyncio
async def test_a_pause_the_daemon_refused_does_not_mark_the_row_paused(world, monkeypatch):
    """The row leaving "downloading" is what takes it out of the only set that
    is ever weighed. Marking it on the strength of a call whose answer was
    never read means the database says stopped while the bytes keep coming, for
    ever, with nothing left to notice."""
    from handler.torrent import transmission_handler as TH

    # A row queued before the hash was recorded: it still follows its number,
    # and because its identity cannot be confirmed it gets the cautious half of
    # the refusal rather than the destructive one.
    #
    # This used to force the same branch with a MISMATCHED hash, and that stopped
    # working the moment the monitor learned to leave a torrent that is not ours
    # alone entirely - the test went green while reaching none of the code it
    # was about. An empty test, passing.
    world.row.info_hash = None

    async def _refused(_tid):
        return False

    monkeypatch.setattr(TH.transmission_handler, "pause_torrent", _refused)

    await world.module._check_downloads()

    assert not any(w.get("status") == "paused" for w in world.written), (
        "wiersz oznaczony jako wstrzymany, chociaz demon pauzy nie przyjal"
    )
    assert not any("total_size" in w for w in world.written), (
        "zapisano rozmiar, wiec przy nastepnym takcie nikt juz nie sprobuje "
        "wstrzymac tego transferu"
    )
