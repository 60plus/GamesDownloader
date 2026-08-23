"""Transmission's control port must not open itself.

`_write_transmission_json` hardcoded "0.0.0.0" while authentication and the
whitelist both default to off. The container's first run writes 127.0.0.1, so
the socket was thrown open the first time an admin saved this screen - and
saving it to change the seed ratio did that just as thoroughly as saving it to
change anything about RPC.

Unauthenticated Transmission RPC accepts `torrent-add` with a `download-dir` of
the caller's choosing, so an open socket writes files anywhere the container can
reach. The port was also published by docker-compose by default, while the
Dockerfile comment claimed the opposite.
"""
from __future__ import annotations

import pathlib

import pytest

from endpoints.settings.transmission_router import _DEFAULTS, _rpc_bind_address

KORZEN = pathlib.Path(__file__).resolve().parent.parent.parent


def test_domyslnie_petla_zwrotna():
    assert _rpc_bind_address(dict(_DEFAULTS)) == "127.0.0.1"


def test_zapis_niezwiazanego_ustawienia_nie_otwiera_gniazda():
    """The actual bug: saving the seed ratio widened the socket."""
    ustawienia = {**_DEFAULTS, "ratio_limit": 4.0, "speed_limit_up": 500}
    assert _rpc_bind_address(ustawienia) == "127.0.0.1"


def test_samo_wystawienie_bez_hasla_nie_wystarcza():
    """Opening it demands a lock. Refusing is the whole point."""
    assert _rpc_bind_address({**_DEFAULTS, "rpc_expose": True}) == "127.0.0.1"


def test_wystawienie_z_autoryzacja_otwiera():
    ustawienia = {**_DEFAULTS, "rpc_expose": True, "rpc_auth_enabled": True,
                  "rpc_username": "admin"}
    assert _rpc_bind_address(ustawienia) == "0.0.0.0"


def test_sama_autoryzacja_nie_wystawia():
    """Turning on a password is not a request to publish the port."""
    assert _rpc_bind_address({**_DEFAULTS, "rpc_auth_enabled": True}) == "127.0.0.1"


def _zapisz(tmp_path, monkeypatch, ustawienia) -> dict:
    """Run the real writer against a temporary settings.json and read it back.

    It writes with `open()` and swallows its own exceptions, so pointing the
    module constant at a real file is the only way to be sure something was
    written rather than quietly skipped.
    """
    import json

    from endpoints.settings import transmission_router as TR

    cel = tmp_path / "transmission" / "settings.json"
    monkeypatch.setattr(TR, "_TR_CFG_PATH", str(cel))
    TR._write_transmission_json(ustawienia)
    assert cel.is_file(), "writer nic nie zapisal"
    return json.loads(cel.read_text(encoding="utf-8"))


def test_wystawiony_port_zawsze_dostaje_biala_liste(tmp_path, monkeypatch):
    cfg = _zapisz(tmp_path, monkeypatch, {
        **_DEFAULTS, "rpc_expose": True, "rpc_auth_enabled": True, "rpc_username": "a",
    })
    assert cfg["rpc-bind-address"] == "0.0.0.0"
    assert cfg["rpc-authentication-required"] is True
    assert cfg["rpc-whitelist-enabled"] is True, (
        "otwarty port bez bialej listy - dokladnie to, czego unikamy")


def test_zapisany_plik_domyslnie_stoi_na_petli_zwrotnej(tmp_path, monkeypatch):
    """The end-to-end shape of the bug: default settings, written out."""
    cfg = _zapisz(tmp_path, monkeypatch, dict(_DEFAULTS))
    assert cfg["rpc-bind-address"] == "127.0.0.1"


def test_biala_lista_na_petli_zwrotnej_nie_jest_wymuszana(tmp_path, monkeypatch):
    """Forcing it there would lock out an instance whose list omits 127.0.0.1."""
    cfg = _zapisz(tmp_path, monkeypatch, dict(_DEFAULTS))
    assert cfg["rpc-whitelist-enabled"] is False


def _compose() -> str:
    """docker-compose.yml, or a skip.

    These two run against the repository. The same suite also runs inside the
    built container, where only `backend/` is copied in, so the file genuinely
    is not there and skipping is the honest answer rather than a failure. The
    CI job checks out the repo, so they do run where it counts.
    """
    plik = KORZEN / "docker-compose.yml"
    if not plik.is_file():
        pytest.skip("docker-compose.yml nie jest kopiowany do obrazu")
    return plik.read_text(encoding="utf-8")


def test_compose_nie_publikuje_portu_sterowania():
    """The three descriptions of this port used to disagree with each other."""
    aktywne = [l for l in _compose().splitlines()
               if "9091" in l and not l.strip().startswith("#")]
    assert not aktywne, f"compose dalej publikuje port RPC: {aktywne}"


def test_peer_port_dalej_publikowany():
    """Removing the wrong one would stop every torrent from seeding."""
    aktywne = [l for l in _compose().splitlines()
               if "51413" in l and not l.strip().startswith("#")]
    assert len(aktywne) >= 2, "peer port musi zostac wystawiony, TCP i UDP"


def test_znacznik_wystawienia_powstaje_i_znika(tmp_path, monkeypatch):
    """The entrypoint reads a file, because it starts the daemon before this
    application exists and cannot ask the database anything."""
    from endpoints.settings import transmission_router as TR

    cel = tmp_path / "transmission" / "settings.json"
    monkeypatch.setattr(TR, "_TR_CFG_PATH", str(cel))
    znacznik = tmp_path / "transmission" / "rpc-exposed"

    TR._write_transmission_json({**_DEFAULTS, "rpc_expose": True,
                                 "rpc_auth_enabled": True, "rpc_username": "a"})
    assert znacznik.is_file(), "otwarty port nie zostawil znacznika"

    TR._write_transmission_json(dict(_DEFAULTS))
    assert not znacznik.exists(), (
        "znacznik przetrwal zamkniecie portu - entrypoint zostawilby go otwartym")
