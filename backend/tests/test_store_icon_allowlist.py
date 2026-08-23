"""The store-icon allowlist read a config key that nothing ever writes.

`config_handler.get("plugin_store_sources")` always returned None - the only
other occurrence of that name in the repository is a `__tablename__`. So the
allowlist was permanently just GitHub: a self-hosted store installed fine,
because that path reads the `PluginStoreSource` table, while every icon it
served came back 400 "Icon host not in store sources allowlist".

The dead key also silently disabled the guard underneath it. `_skip_dns` was
set to `hostname in allowed_hosts`, evaluated after the code had already
returned 400 for anything not in that set - so it was always True and the
private-network check below it was unreachable.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from endpoints.settings import plugins_router

ROOT = pathlib.Path(__file__).resolve().parent.parent
# A read of the key, not a mention of it: the name still appears in the
# __tablename__ it belongs to, and in the prose explaining why it is gone.
READS_THE_KEY = re.compile(r"""config_handler\.get\(\s*["']plugin_store_sources""")


def test_nothing_reads_the_config_key_nothing_writes():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if path.parent.name == "tests":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), 1):
            if READS_THE_KEY.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == [], f"config key nothing writes is read at: {offenders}"


def test_the_allowlist_is_built_from_the_store_source_table():
    source = inspect.getsource(plugins_router.store_icon_hosts)
    assert "PluginStoreSource" in source
    assert "github.com" in source


def test_the_icon_route_no_longer_carries_an_always_true_dns_bypass():
    source = inspect.getsource(plugins_router.proxy_store_icon)
    assert "_skip_dns" not in source
    assert "assert_fetch_allowed" in source
