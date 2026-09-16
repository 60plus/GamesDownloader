"""A seed is found by its own hash, and a restart cannot make it somebody else's.

Found by the adversarial review of the second 1.0.34 fix round: the fault of
finding #1, in the one loop that had not moved over. `_check_seeds` asked the
daemon about each seeding library file by the `transmission_id` stored when the
seed was made. The daemon numbers its torrents from 1 again after every restart,
so after a deploy that number can belong to an uploader's running download:

  * once that download had uploaded as much as the seed's file weighs, the loop
    took it off the daemon as a finished seed - the uploader's transfer gone, its
    row lost for good, and the real seed left running with no row at all;
  * a number that named nothing marked a healthy seed as failed, and so did a
    single moment when the daemon did not answer.

And `held_by_another` counts a seed only while its row says "seeding", so a status
written from the wrong torrent misled that answer in both directions.

So the loop asks by the hash, checks that the daemon answered about this seed,
leaves the row alone while the daemon is unreachable, and does not take a
finished seed off the daemon while a live transfer is fetching the same torrent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

SEED = "5eed" * 10
STRANGER = "ab" * 20
FILE_SIZE = 30_000_000


@pytest.fixture
def seeds(monkeypatch):
    from handler.database import session as S
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    row = SimpleNamespace(id=1, transmission_id=6, info_hash=SEED, file_size=FILE_SIZE,
                          torrent_path=None, status="seeding")
    state = SimpleNamespace(
        asked=[], removed=[], statuses=[], available=True, transfer_holds=False,
        # What the daemon holds after a restart: this seed under its hash, and an
        # uploader's download under the number the seed row still remembers.
        daemon={
            SEED: {"hashString": SEED, "uploadedEver": 1_000},
            6: {"hashString": STRANGER, "uploadedEver": 90_000_000},
        },
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [row]

    class _Db:
        async def execute(self, *_a, **_k):
            return _Result()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    async def _get(ref):
        state.asked.append(ref)
        return state.daemon.get(ref)

    async def _remove(ref, *, delete_data=False):
        state.removed.append((ref, delete_data))
        return True

    async def _available():
        return state.available

    async def _status(seed_id, status):
        state.statuses.append((seed_id, status))

    async def _holds(_info_hash, **_k):
        return state.transfer_holds

    monkeypatch.setattr(S, "async_session_factory", _Factory())
    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get)
    monkeypatch.setattr(TH.transmission_handler, "remove_torrent", _remove)
    monkeypatch.setattr(TH.transmission_handler, "is_available", _available)
    monkeypatch.setattr(M, "_update_seed_status", _status)
    monkeypatch.setattr(M, "_live_transfer_holds", _holds, raising=False)
    return SimpleNamespace(M=M, row=row, state=state)


# ── After a restart ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_seed_is_asked_about_by_its_own_hash(seeds):
    await seeds.M._check_seeds()

    assert seeds.state.asked == [SEED], (
        f"petla seedow pyta demona po numerze sprzed restartu: {seeds.state.asked}"
    )


@pytest.mark.asyncio
async def test_a_download_now_under_the_seeds_old_number_is_not_taken_off_the_daemon(seeds):
    await seeds.M._check_seeds()

    assert seeds.state.removed == [], (
        "petla seedow zdjela z demona cudze pobieranie, ktore po restarcie dostalo "
        f"numer seeda: {seeds.state.removed}"
    )
    assert seeds.state.statuses == [], (
        f"stan seeda zapisany na podstawie cudzego torrentu: {seeds.state.statuses}"
    )


@pytest.mark.asyncio
async def test_an_answer_about_a_different_torrent_is_not_acted_on(seeds):
    seeds.state.daemon[SEED] = {"hashString": STRANGER, "uploadedEver": 90_000_000}

    await seeds.M._check_seeds()

    assert seeds.state.removed == [] and seeds.state.statuses == []


@pytest.mark.asyncio
async def test_a_daemon_that_does_not_answer_does_not_fail_the_seed(seeds):
    """"Not holding it" and "did not answer" arrive identically, and only the
    first is a lost seed. Written as failed, nothing ever brings it back."""
    seeds.state.daemon = {}
    seeds.state.available = False

    await seeds.M._check_seeds()

    assert seeds.state.statuses == [], (
        "chwila bez odpowiedzi demona oznaczyla zdrowego seeda jako bledny na zawsze"
    )


@pytest.mark.asyncio
async def test_a_finished_seed_a_live_transfer_is_fetching_is_left_in_the_daemon(seeds):
    """The seed's torrent is the same torrent as somebody's download of that
    file. The seed row is done; the torrent is theirs to finish."""
    seeds.state.daemon[SEED]["uploadedEver"] = FILE_SIZE
    seeds.state.transfer_holds = True

    await seeds.M._check_seeds()

    assert seeds.state.removed == [], (
        "zakonczony seed zdjal z demona torrent, ktory pobiera zywy transfer"
    )
    assert seeds.state.statuses == [(1, "expired")]


# ── What must keep working ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_seed_that_has_given_its_copy_is_still_taken_off(seeds):
    """THE LEGAL CASE: one full copy uploaded, then the seed stops."""
    seeds.state.daemon[SEED]["uploadedEver"] = FILE_SIZE

    await seeds.M._check_seeds()

    assert seeds.state.removed == [(SEED, False)]
    assert seeds.state.statuses == [(1, "expired")]


@pytest.mark.asyncio
async def test_a_seed_the_daemon_no_longer_holds_is_marked_failed(seeds):
    """THE LEGAL CASE for the error: the daemon answers, and this seed is gone."""
    seeds.state.daemon = {}

    await seeds.M._check_seeds()

    assert seeds.state.statuses == [(1, "error")]


@pytest.mark.asyncio
async def test_a_seed_from_before_hashes_were_recorded_still_goes_by_its_number(seeds):
    """THE LEGAL CASE for old rows: the number is all they have."""
    seeds.row.info_hash = None
    seeds.state.daemon[6] = {"hashString": STRANGER, "uploadedEver": 1_000}

    await seeds.M._check_seeds()

    assert seeds.state.asked == [6]
    assert seeds.state.removed == [] and seeds.state.statuses == []
