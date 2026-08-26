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
    """Parsing (and now decrypting) happens after the `with` closes, so the
    pooled connection is not held for the length of it.

    Read from the parse tree rather than by counting characters around the
    call: a wrapper around the parse used to move it past a fixed-width window
    and fail this on a change that kept it exactly where it belongs."""
    import ast
    import textwrap

    source = inspect.getsource(get_plugin_config)
    # The connection is still borrowed from the pool by a context manager. The
    # first version of this test asserted that by searching for the literal
    # text, and rewriting it as a parse-tree check quietly dropped the check
    # altogether: a body that opened the connection and never closed it passed.
    # The pool holds two, so that would wedge every plugin after two reads.
    assert "with _sync_engine().connect()" in source

    tree = ast.parse(textwrap.dedent(source))
    inside_with = {
        node
        for stmt in ast.walk(tree)
        if isinstance(stmt, ast.With)
        for body_stmt in stmt.body
        for node in ast.walk(body_stmt)
    }
    parses = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "loads"
    ]
    assert parses, "the helper no longer parses the stored config"
    for node in parses:
        assert node not in inside_with, "the JSON is parsed while the connection is held"


def test_the_loader_imports_the_submodule_it_actually_uses():
    """Every plugin is loaded through `importlib.util.spec_from_file_location`,
    and `import importlib` does not make `importlib.util` available.

    Verified in a clean interpreter: `import importlib; hasattr(importlib,
    "util")` is False. It has worked here only because something else in the
    import graph pulls that submodule in first, which is luck rather than a
    decision. If that ever stops, every plugin fails at load, each failure is
    caught and logged separately, and the server comes up looking healthy with
    no plugins at all.

    Asserted on the parse tree rather than the text, because the contract being
    checked is literally the presence of that import statement.
    """
    import ast
    from pathlib import Path

    import plugins.manager as manager_module

    tree = ast.parse(Path(manager_module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "importlib.util" in imported, (
        "plugins/manager.py must import importlib.util itself"
    )


def test_the_contract_plugins_depend_on_is_unchanged():
    """Name, arity, and errors swallowed. Every installed plugin calls this."""
    signature = inspect.signature(get_plugin_config)
    assert list(signature.parameters) == ["plugin_id"]
    source = inspect.getsource(get_plugin_config)
    assert "except Exception:" in source
    assert source.rstrip().endswith("return {}")
