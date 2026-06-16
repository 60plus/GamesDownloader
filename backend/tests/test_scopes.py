"""Unit tests for role -> scope mapping and permission overrides (handler.auth.scopes)."""
from __future__ import annotations

from handler.auth.scopes import (
    USER_SCOPES,
    Scope,
    apply_permission_overrides,
    scopes_for_role,
)
from models.user import Role


def test_user_role_has_read_not_admin():
    scopes = scopes_for_role(Role.USER)
    assert Scope.LIBRARY_READ in scopes
    assert Scope.LIBRARY_ADMIN not in scopes


def test_admin_role_is_superset_of_user():
    admin = scopes_for_role(Role.ADMIN)
    assert USER_SCOPES <= admin
    assert Scope.LIBRARY_ADMIN in admin


def test_permission_override_revokes_library_access():
    base = scopes_for_role(Role.USER)
    out = apply_permission_overrides({"access_gamesdownloader": False}, base)
    assert Scope.LIBRARY_READ not in out
    assert Scope.LIBRARY_DOWNLOAD not in out


def test_permission_override_grants_upload():
    base = scopes_for_role(Role.USER)
    assert Scope.LIBRARY_UPLOAD not in base
    out = apply_permission_overrides({"upload": True}, base)
    assert Scope.LIBRARY_UPLOAD in out


def test_no_overrides_returns_base_unchanged():
    base = scopes_for_role(Role.EDITOR)
    assert apply_permission_overrides(None, base) == set(base)
    assert apply_permission_overrides({}, base) == set(base)
