"""The IP allowlist has to actually block something.

`_BYPASS_PREFIXES` used to end with "/", and every path in existence starts
with "/", so the prefix test matched everything and the middleware returned at
its first line. The allowlist let the whole internet through while Settings and
the wiki both described it as an access control, and the code below that line
was unreachable.

Nothing caught it because nothing asserted the negative: that an ordinary API
path does NOT bypass.
"""
from __future__ import annotations

import pytest

from middleware.ip_allowlist import _BYPASS_EXACT, _BYPASS_PREFIXES, _ip_allowed


def _omija(path: str) -> bool:
    """The middleware's own gate, kept in step with dispatch()."""
    return path in _BYPASS_EXACT or any(path.startswith(p) for p in _BYPASS_PREFIXES)


@pytest.mark.parametrize("path", [
    "/api/library/games",
    "/api/library/games/1/files",
    "/api/users",
    "/api/settings/security",
    "/api/roms/1/play/start",
    "/api/collections/moje",
    "/games/1",
    "/cokolwiek",
])
def test_zwykla_sciezka_nie_omija_allowlisty(path: str) -> None:
    assert not _omija(path), f"{path} omija allowliste - kontrola nic nie robi"


@pytest.mark.parametrize("path", [
    "/",                    # SPA shell: let a blocked visitor see the app say no
    "/index.html",
    "/api/health",          # so a health check never depends on the allowlist
    "/api/setup",           # so nobody locks themselves out before configuring
    "/assets/index-abc.js",
    "/resources/library/1/cover/cover.jpg",
    "/favicon.ico",
])
def test_wyjatki_dalej_omijaja(path: str) -> None:
    assert _omija(path), f"{path} powinien omijac allowliste"


def test_zaden_prefiks_nie_pasuje_do_wszystkiego() -> None:
    """The shape of the original bug, stated directly."""
    for p in _BYPASS_PREFIXES:
        assert p not in ("", "/"), f"prefiks {p!r} pasuje do kazdej sciezki"
        assert p.startswith("/"), f"prefiks {p!r} nie jest sciezka"
        assert len(p) > 1, f"prefiks {p!r} jest za krotki, zeby cokolwiek znaczyc"


def test_petla_zwrotna_zawsze_wpuszczona() -> None:
    """Documented behaviour: the box can always talk to itself."""
    assert _ip_allowed("127.0.0.1", [])
    assert _ip_allowed("::1", [])


def test_nieznany_adres_odrzucony_gdy_lista_niepusta() -> None:
    import ipaddress
    siec = [ipaddress.ip_network("192.168.0.0/24")]
    assert _ip_allowed("192.168.0.40", siec)
    assert not _ip_allowed("203.0.113.7", siec)
    assert not _ip_allowed("nie-adres", siec)
