"""Plugins read their config often, so it must not cost a new connection pool.

`get_plugin_config` is a documented plugin-facing helper - it is in the plugin
template's README and in the wiki - and it built a whole SQLAlchemy engine
inside the function for a single SELECT. Each call paid a TCP connect, an
authentication handshake and a full MySQL dialect initialisation, and
RomDownloader asks three or more times per listing page.

The `engine.dispose()` meant to clean that up was unreachable whenever a config
was actually found, because the `return` sat inside the `with`.

The contract must not move: same name, one argument, a dict back, and every
error swallowed into an empty dict. A plugin that raised here would take the
page with it.
"""
from __future__ import annotations

import inspect

from plugins.manager import _sync_engine, get_plugin_config


def test_the_engine_is_built_once_and_shared():
    _sync_engine.cache_clear()
    first = _sync_engine()
    second = _sync_engine()
    assert first is second
    assert _sync_engine.cache_info().misses == 1


def test_building_the_engine_does_not_connect():
    """Which is why caching it is safe even when the database is down: the
    connection happens on .connect(), not on create_engine."""
    _sync_engine.cache_clear()
    engine = _sync_engine()
    assert engine.pool.checkedout() == 0


def test_the_pool_is_small_and_recycles():
    """It lives beside the async pool, and the two together have to stay well
    under the server's connection limit. Now that connections are kept rather
    than torn down after every call, an idle one must not outlive MySQL's
    wait_timeout."""
    _sync_engine.cache_clear()
    engine = _sync_engine()
    assert engine.pool.size() == 2
    assert engine.pool._recycle == 1800


def test_the_dead_dispose_is_gone():
    source = inspect.getsource(get_plugin_config)
    assert "dispose()" not in source
    assert "create_engine" not in source


def test_the_connection_goes_back_before_the_json_is_parsed():
    source = inspect.getsource(get_plugin_config)
    with_line = source.index("with _sync_engine().connect()")
    parse_line = source.index("_json.loads")
    # The parse sits outside the with-block, i.e. at a shallower indent than
    # the statements inside it.
    tail = source[parse_line - 60:parse_line]
    assert "        if row and row[0]:" in tail or "\n        if row" in tail
    assert with_line < parse_line


def test_the_contract_plugins_depend_on_is_unchanged():
    """Name, arity, and errors swallowed. Every installed plugin calls this."""
    signature = inspect.signature(get_plugin_config)
    assert list(signature.parameters) == ["plugin_id"]
    source = inspect.getsource(get_plugin_config)
    assert "except Exception:" in source
    assert source.rstrip().endswith("return {}")
