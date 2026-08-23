"""Changing a password has to end the sessions opened with the old one.

An admin forcing a reset is the containment action for a compromised account.
It updated the hash and returned, leaving every session alive, so a stolen
refresh token kept minting access tokens for its full window. The one button an
operator has for this did nothing.

The self-service reset in `endpoints/auth.py` already did it correctly, which
is what makes the omission in the other two paths a bug rather than a policy.
"""
from __future__ import annotations

import ast
import pathlib

KORZEN = pathlib.Path(__file__).resolve().parent.parent


def _cialo(sciezka: str, nazwa: str) -> str:
    """Source of one function, so the assertions read against real code."""
    drzewo = ast.parse((KORZEN / sciezka).read_text(encoding="utf-8"))
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)) and w.name == nazwa:
            return ast.unparse(w)
    raise AssertionError(f"nie ma {nazwa} w {sciezka}")


def test_wymuszony_reset_przez_admina_konczy_sesje():
    src = _cialo("endpoints/users.py", "admin_reset_password")
    assert "revoke_all_for_user" in src, (
        "reset hasla przez admina nie konczy sesji - skradziony token dalej dziala")


def test_zmiana_wlasnego_hasla_konczy_pozostale_sesje():
    src = _cialo("endpoints/users.py", "change_password")
    assert "revoke_all_for_user" in src, "zmiana wlasnego hasla nie konczy innych sesji"


def test_zmiana_wlasnego_hasla_nie_wylogowuje_biezacej_przegladarki():
    """Signing somebody out for changing their own password punishes the right
    action, so this path spares the caller's own session and only that one."""
    src = _cialo("endpoints/users.py", "change_password")
    assert "keep_access_jti" in src and "token_jti" in src


def test_reset_przez_admina_nie_oszczedza_zadnej_sesji():
    """The target is somebody else and all of their sessions are suspect."""
    src = _cialo("endpoints/users.py", "admin_reset_password")
    assert "keep_access_jti" not in src, (
        "reset przez admina nie ma nikogo oszczedzac - to akcja ratunkowa")


def test_samoobslugowy_reset_dalej_to_robi():
    """The path that was already correct, so a refactor cannot quietly drop it."""
    src = _cialo("endpoints/auth.py", "reset_password")
    assert "revoke_all_for_user" in src


def test_wyjatek_sesji_dociera_do_zapytania():
    """`keep_access_jti` has to reach the WHERE clause, not just the signature."""
    src = _cialo("handler/database/session_handler.py", "revoke_all_for_user")
    bez_spacji = src.replace(" ", "")
    assert "keep_access_jti" in src, "brak parametru"
    assert "UserSession.access_jti!=keep_access_jti" in bez_spacji, (
        "parametr istnieje, ale nic nie zaweza nim zapytania")
