"""The torrent monitor was raising on every tick, and had been since March.

    download_monitor error: 'TransmissionHandler' object has no attribute 'STATUS'

`STATUS` is a module constant in `transmission_handler`. `torrent_router` imports
it as one. `seed_monitor` reads it off the singleton instead, which is an
AttributeError every time a transfer is in progress - so the last statement of
every tick threw, and `download_monitor_loop` swallowed it, logged a warning, and
slept ten seconds to do it again.

WHAT IT COST, on a live install, for six months and in the released 1.0.33:
  * `torrent:download_progress` was NEVER emitted. Nothing anywhere could show a
    torrent moving, which is one half of "I cannot see whether it is downloading".
  * The raise leaves `_check_downloads` altogether, so every row AFTER the first
    still-downloading one is skipped for that tick: not weighed against the
    quota, not completed, not registered. With one transfer running, nothing
    else can finish.

WHY ELEVEN TESTS DID NOT NOTICE. Every existing test of this file reads the
source and asserts that some text appears in it. The text was all present and
correct; the attribute simply does not exist at run time. So this one RUNS a
tick, with a fake daemon and a fake session, and asserts on what came out.
The rule this file exists to keep: a monitor is tested by ticking it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

DOWNLOADING = 4          # Transmission's own status code


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
    """Stands in for `async_session_factory`, which is called and then entered."""

    def __init__(self, rows):
        self._rows = rows

    def __call__(self):
        return self

    async def __aenter__(self):
        return _Db(self._rows)

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def tick(monkeypatch):
    """One transfer at half way, a daemon that answers, and a recorder."""
    from handler.database import session as S
    from handler.socket_handler import sio
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    row = SimpleNamespace(
        id=11,
        transmission_id=7,
        # Already known, so the once-only quota weighing is not what is under
        # test here; it has its own file.
        total_size=1000,
        created_by_id=3,
        status="downloading",
    )
    monkeypatch.setattr(S, "async_session_factory", _Factory([row]))

    async def _get_torrent(_tid):
        return {
            "status": DOWNLOADING,
            "percentDone": 0.5,
            "totalSize": 1000,
            "rateDownload": 4096,
            "eta": 60,
            "error": 0,
        }

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)

    written: list[dict] = []

    async def _update(_id, values):
        written.append(dict(values))

    monkeypatch.setattr(M, "_update_download", _update)

    said: list[tuple] = []

    async def _emit(event, payload=None, **kwargs):
        said.append((event, payload))

    monkeypatch.setattr(sio, "emit", _emit)

    return SimpleNamespace(module=M, row=row, written=written, said=said)


@pytest.mark.asyncio
async def test_a_tick_over_a_running_transfer_does_not_raise(tick):
    """The whole of the failure, in one line: it threw, every ten seconds."""
    await tick.module._check_downloads()


@pytest.mark.asyncio
async def test_the_tick_says_the_transfer_moved(tick):
    """The progress event is the only thing that tells a screen a torrent is
    alive. It was never sent once."""
    await tick.module._check_downloads()

    progress = [p for event, p in tick.said if event == "torrent:download_progress"]
    assert progress, (
        "takt nie wyslal zdarzenia o postepie, wiec zaden ekran nie ma skad "
        "wiedziec, ze torrent sie rusza"
    )
    assert progress[0]["percent"] == 50.0
    assert progress[0]["id"] == 11


@pytest.mark.asyncio
async def test_the_progress_names_the_state_in_words(tick):
    """The field exists to carry Transmission's numeric code as something a
    person can read. Reading the table off the singleton instead of the module
    is exactly what raised."""
    await tick.module._check_downloads()

    progress = [p for event, p in tick.said if event == "torrent:download_progress"]
    assert progress[0]["status"] == "downloading", (
        "stan transferu nie jest tlumaczony na slowo - a to jedyny powod, dla "
        "ktorego to pole istnieje"
    )


@pytest.mark.asyncio
async def test_a_second_transfer_is_still_reached(tick, monkeypatch):
    """The raise left the whole loop, not just the row it happened on.

    Two rows, and the first one is the ordinary in-progress case that used to
    throw. If it throws, the second is never looked at: never weighed, never
    completed, never registered. That is the part of this bug that is not
    cosmetic.
    """
    from handler.database import session as S

    second = SimpleNamespace(
        id=12, transmission_id=8, total_size=1000, created_by_id=3,
        status="downloading",
    )
    monkeypatch.setattr(S, "async_session_factory", _Factory([tick.row, second]))

    await tick.module._check_downloads()

    reached = {p["id"] for event, p in tick.said if event == "torrent:download_progress"}
    assert reached == {11, 12}, (
        f"takt nie dotarl do wszystkich transferow, obsluzyl tylko {reached}"
    )
