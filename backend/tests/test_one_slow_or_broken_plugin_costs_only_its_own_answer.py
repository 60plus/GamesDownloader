"""One slow or broken metadata plugin costs only its own answer.

Two findings of the 1.0.34 audit, left for 1.0.35:

  #15  /roms/search asked every plugin in ONE pluggy call. Pluggy stops at the
       first plugin that raises and throws away what the others had already
       answered, so a broken TheGamesDB emptied the PPE.pl and ProtonDB chips
       too - while the comment beside it said the opposite. And nothing put a
       limit on how long a plugin could take.
  #14  Everywhere else the metadata hooks were called straight on the event
       loop: the ROM editor's all-media, the per-ROM scrape, the cover, hero,
       logo and screenshot searches, the collection art. The plugins go to the
       network synchronously, and uvicorn runs one worker, so one slow upstream
       stalled every page, socket event and transfer on the server.

`plugin_manager.call_each(hook_name, **kwargs)` asks each plugin on its own
thread, with its own time limit, and keeps whatever the others answered when one
of them raises or runs out of time. Every metadata hook call goes through it; a
test here walks the backend for any that do not.

A plugin that runs out of time is not stopped - a thread cannot be - it is only
no longer waited for. The shipped plugins give up on their own after 15-20 s.
"""

from __future__ import annotations

import asyncio
import io
import pathlib
import re
import time

import pluggy
import pytest

from plugins.hookspecs import PROJECT_NAME

hookimpl = pluggy.HookimplMarker(PROJECT_NAME)
BACKEND = pathlib.Path(__file__).resolve().parent.parent


class _Good:
    def __init__(self, name):
        self.name = name

    @hookimpl
    def metadata_search_game(self, query):
        return [{"provider_id": self.name, "title": query}]


class _Broken:
    @hookimpl
    def metadata_search_game(self, query):
        raise RuntimeError("upstream said 503")


class _Slow:
    def __init__(self, seconds):
        self.seconds = seconds

    @hookimpl
    def metadata_search_game(self, query):
        time.sleep(self.seconds)
        return [{"provider_id": "slow", "title": query}]


class _Silent:
    @hookimpl
    def metadata_search_game(self, query):
        return None


def _manager(*plugins):
    from plugins.manager import PluginManager

    pm = PluginManager()
    for p in plugins:
        pm.register(p)
    return pm


@pytest.mark.asyncio
async def test_a_plugin_that_raises_costs_only_its_own_results():
    pm = _manager(_Good("a"), _Broken(), _Good("b"))
    out = await pm.call_each("metadata_search_game", query="Doom")
    assert sorted(r[0]["provider_id"] for r in out) == ["a", "b"], (
        "jedna wtyczka, ktora rzucila, skasowala wyniki pozostalych"
    )


@pytest.mark.asyncio
async def test_a_plugin_that_takes_too_long_is_not_waited_for():
    pm = _manager(_Good("a"), _Slow(3.0))
    started = time.monotonic()
    out = await pm.call_each("metadata_search_game", query="Doom", timeout=0.3)
    assert time.monotonic() - started < 2.0, "zapytanie czekalo na wtyczke bez limitu czasu"
    assert [r[0]["provider_id"] for r in out] == ["a"]


@pytest.mark.asyncio
async def test_the_server_keeps_working_while_a_plugin_is_slow():
    """Off the event loop: something else scheduled meanwhile gets to finish first."""
    pm = _manager(_Slow(0.4))
    order = []

    async def _other_request():
        await asyncio.sleep(0.05)
        order.append("other request")

    other = asyncio.create_task(_other_request())
    await pm.call_each("metadata_search_game", query="Doom", timeout=5)
    order.append("plugins")
    await other
    assert order == ["other request", "plugins"], (
        "wolna wtyczka zablokowala petle zdarzen - reszta serwera czekala"
    )


@pytest.mark.asyncio
async def test_plugins_are_asked_side_by_side_not_one_after_another():
    pm = _manager(_Slow(0.4), _Slow(0.4), _Slow(0.4))
    started = time.monotonic()
    out = await pm.call_each("metadata_search_game", query="Doom", timeout=5)
    assert len(out) == 3
    assert time.monotonic() - started < 1.0


@pytest.mark.asyncio
async def test_the_answers_come_in_the_order_pluggy_gives_them():
    """Callers match results to providers by what is inside them, but a caller
    that reads the first answer should get the same one as before."""
    pm = _manager(_Good("a"), _Good("b"), _Good("c"), _Silent())
    direct = [r for r in pm.hook.metadata_search_game(query="Doom")]
    out = await pm.call_each("metadata_search_game", query="Doom")
    assert out == direct


@pytest.mark.asyncio
async def test_a_hook_nobody_implements_answers_nothing():
    pm = _manager(_Good("a"))
    assert await pm.call_each("metadata_get_logos", query="Doom") == []
    assert await pm.call_each("no_such_hook", query="Doom") == []


def test_no_metadata_hook_is_called_on_the_event_loop_any_more():
    """Walks the backend. A direct call is `plugin_manager.hook.metadata_...(`
    or a hook fetched with `getattr(plugin_manager.hook, ...)`."""
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "manager.py":
            continue
        text = io.open(path, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r"\.hook\.metadata_\w+|getattr\(plugin_manager\.hook", text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{path.relative_to(BACKEND)}:{line}")
    assert not offenders, f"hooki metadanych wolane wprost, na petli zdarzen: {offenders}"
