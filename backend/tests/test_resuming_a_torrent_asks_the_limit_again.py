"""Resume was a one-click, permanent exemption from the upload quota.

MEASURED ON THE LIVE INSTALL, and it is how the owner ran into this. gdtest has
a 4 GB allowance. A 52.5 GB magnet was queued, the monitor weighed it the moment
the metadata arrived and stopped it, writing the reason onto the row. Nobody saw
that, because the only screen showing torrent transfers is the administrator's.
The owner, as administrator, pressed Resume. From that instant the limit could
never apply to that transfer again:

  * the monitor weighs a transfer exactly ONCE, on the tick its size arrives,
    and the stored size is what records that it has been asked;
  * Resume was already past that, so nothing weighed it a second time;
  * `POST /api/torrents/downloads/4/resume` in the access log, and the transfer
    running at 37 per cent of 52.5 GB on a 4 GB account.

So the question has to be asked here as well. This is the one moment a stopped
transfer is deliberately let go again, and it is the only place left that can
ask. Refusing on "could not tell" rather than allowing is on purpose: allowing
is exactly the silent permanent bypass this file exists to close, and a refusal
here is a retry, not a loss.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

TOO_BIG = 56_373_525_225


@pytest.fixture
def route(monkeypatch):
    from endpoints.torrent import torrent_router as R

    row = SimpleNamespace(
        id=4, transmission_id=2, info_hash="abc", total_size=TOO_BIG,
        created_by_id=3, status="paused",
        error_msg="Refused: this torrent is larger than ...",
    )

    async def _row(_dl_id):
        return row

    monkeypatch.setattr(R, "_download_or_404", _row)

    started: list[int] = []

    async def _resume(tid):
        started.append(tid)
        return True

    monkeypatch.setattr(R.transmission_handler, "resume_torrent", _resume)

    written: list[dict] = []

    async def _status(dl_id, status, **kwargs):
        written.append({"id": dl_id, "status": status, **kwargs})

    monkeypatch.setattr(R, "_set_download_status", _status)

    # The route is behind `protected_route`, which is left in the path on
    # purpose: a caller without the scope must never reach the weighing at all.
    from handler.auth.scopes import Scope

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="60plus"),
        scopes={Scope.LIBRARY_ADMIN, Scope.LIBRARY_UPLOAD}))

    # Nothing else holds this torrent here. The other case is
    # test_a_torrent_another_row_holds_is_left_to_it.py.
    from handler.torrent import seed_monitor as M

    async def _nobody_else(_td):
        return False

    monkeypatch.setattr(M, "held_by_another", _nobody_else)

    return SimpleNamespace(module=R, row=row, started=started, written=written,
                           request=request)


def _answer(monkeypatch, verdict):
    """What the weighing says when it is asked. None means it could not tell."""
    from handler.torrent import seed_monitor as M

    async def _over(_td, _size):
        return verdict

    monkeypatch.setattr(M, "_over_quota", _over)


@pytest.mark.asyncio
async def test_a_transfer_that_still_does_not_fit_is_not_let_go_again(route, monkeypatch):
    _answer(monkeypatch, True)

    with pytest.raises(HTTPException) as refusal:
        await route.module.resume_download(route.request, 4)

    assert refusal.value.status_code == 413
    assert route.started == [], (
        "demon zostal wznowiony mimo przekroczonego limitu - jedno klikniecie "
        "zdejmuje limit z tego transferu na zawsze"
    )


@pytest.mark.asyncio
async def test_the_refusal_says_what_is_in_the_way(route, monkeypatch):
    """An administrator who cannot see why will press it again."""
    _answer(monkeypatch, True)

    with pytest.raises(HTTPException) as refusal:
        await route.module.resume_download(route.request, 4)

    powod = str(refusal.value.detail).lower()
    assert "quota" in powod or "limit" in powod


@pytest.mark.asyncio
async def test_a_transfer_that_now_fits_carries_on(route, monkeypatch):
    """THE LEGAL CASE. Freeing space and pressing Resume has to work, or the
    gate is a wall: an account whose transfer was stopped would have no way
    back even after deleting half its library."""
    _answer(monkeypatch, False)

    out = await route.module.resume_download(route.request, 4)

    assert out["status"] == "downloading"
    # By the hash, not the daemon's per-session number (1.0.34 audit, finding #1).
    assert route.started == [route.row.info_hash]
    assert any(w["status"] == "downloading" for w in route.written)


@pytest.mark.asyncio
async def test_resuming_clears_the_reason_it_was_stopped(route, monkeypatch):
    """The live row still carries "Refused: this torrent is larger ..." while
    downloading at full speed, because Resume only ever wrote the status. A
    message that outlives what it describes is the same lie as a count of
    zero uploads on a screen that refused four files."""
    _answer(monkeypatch, False)

    await route.module.resume_download(route.request, 4)

    # The key has to be WRITTEN and empty. Asking `w.get("error_msg")` passes
    # when the key was never touched at all, which is the bug - this assertion
    # went green against the unfixed route the first time it ran.
    cleared = [w for w in route.written if "error_msg" in w and not w["error_msg"]]
    assert cleared, (
        f"wiersz nadal tlumaczy, ze zostal zatrzymany, chociaz wlasnie ruszyl: "
        f"{route.written}"
    )


@pytest.mark.asyncio
async def test_a_limit_that_could_not_be_checked_is_not_taken_for_a_yes(route, monkeypatch):
    """"Could not tell" is where the original hole was. Letting it through here
    would put the same hole back in the one place left that can ask."""
    _answer(monkeypatch, None)

    with pytest.raises(HTTPException) as refusal:
        await route.module.resume_download(route.request, 4)

    assert refusal.value.status_code == 503
    assert route.started == []


@pytest.mark.asyncio
async def test_an_account_with_no_limit_is_not_stopped_by_this(route, monkeypatch):
    """THE OTHER LEGAL CASE. Most installs have no quota set at all, and every
    resume on them must go through untouched."""
    from handler.torrent import seed_monitor as M

    class _Users:
        async def get_by_id(self, _uid):
            return SimpleNamespace(id=3, username="gdtest")

    monkeypatch.setattr("handler.database.users_handler.UsersHandler", _Users)

    async def _no_limit(_user):
        return 0

    monkeypatch.setattr("handler.library.quota.limit_for", _no_limit)
    # The real weighing runs here, deliberately: this asserts the whole path
    # answers "fine" rather than that a stub does.
    assert await M._over_quota(route.row, TOO_BIG) is False

    out = await route.module.resume_download(route.request, 4)
    assert out["status"] == "downloading"
    # By the hash, not the daemon's per-session number (1.0.34 audit, finding #1).
    assert route.started == [route.row.info_hash]
