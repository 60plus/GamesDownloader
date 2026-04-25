"""Permission scopes for role-based access control.

Each scope represents a specific permission. Routes declare required scopes
via @protected_route. Users get scopes based on their role; the permissions
JSON field on User can add or revoke individual scopes.
"""

from __future__ import annotations

import enum

from models.user import Role


class Scope(str, enum.Enum):
    # ── GOG Library (admin-only) ──────────────────────────────────────────────
    GOG_READ     = "gog.read"
    GOG_WRITE    = "gog.write"
    GOG_DOWNLOAD = "gog.download"

    # ── GamesDownloader Library ───────────────────────────────────────────────
    LIBRARY_READ     = "library.read"      # browse + download
    LIBRARY_DOWNLOAD = "library.download"  # stream files from server
    LIBRARY_WRITE    = "library.write"     # edit metadata
    LIBRARY_UPLOAD   = "library.upload"    # upload game files
    LIBRARY_ADMIN    = "library.admin"     # publish from GOG, manage files, stats

    # ── ROMs / Emulation (future) ─────────────────────────────────────────────
    ROMS_READ      = "roms.read"
    ROMS_WRITE     = "roms.write"
    PLATFORMS_READ = "platforms.read"
    PLATFORMS_WRITE = "platforms.write"

    # ── Users ─────────────────────────────────────────────────────────────────
    USERS_READ  = "users.read"
    USERS_WRITE = "users.write"

    # ── Game requests ─────────────────────────────────────────────────────────
    REQUESTS_READ  = "requests.read"
    REQUESTS_WRITE = "requests.write"

    # ── Downloads (job queue) ─────────────────────────────────────────────────
    DOWNLOADS_READ  = "downloads.read"
    DOWNLOADS_WRITE = "downloads.write"

    # ── Settings / admin ──────────────────────────────────────────────────────
    SETTINGS_READ  = "settings.read"
    SETTINGS_WRITE = "settings.write"

    # ── Plugins ───────────────────────────────────────────────────────────────
    PLUGINS_READ  = "plugins.read"
    PLUGINS_WRITE = "plugins.write"


# ── Base role → scope mapping ─────────────────────────────────────────────────

USER_SCOPES: frozenset[Scope] = frozenset({
    Scope.LIBRARY_READ,
    Scope.LIBRARY_DOWNLOAD,
    Scope.ROMS_READ,
    Scope.PLATFORMS_READ,
    Scope.REQUESTS_READ,
    Scope.PLUGINS_READ,
})

EDITOR_SCOPES: frozenset[Scope] = USER_SCOPES | frozenset({
    Scope.LIBRARY_WRITE,
    Scope.REQUESTS_WRITE,
})

UPLOADER_SCOPES: frozenset[Scope] = EDITOR_SCOPES | frozenset({
    Scope.LIBRARY_UPLOAD,
})

ADMIN_SCOPES: frozenset[Scope] = UPLOADER_SCOPES | frozenset({
    Scope.GOG_READ,
    Scope.GOG_WRITE,
    Scope.GOG_DOWNLOAD,
    Scope.LIBRARY_ADMIN,
    Scope.ROMS_WRITE,
    Scope.PLATFORMS_WRITE,
    Scope.DOWNLOADS_READ,
    Scope.DOWNLOADS_WRITE,
    Scope.USERS_READ,
    Scope.USERS_WRITE,
    Scope.SETTINGS_READ,
    Scope.SETTINGS_WRITE,
    Scope.PLUGINS_WRITE,
})

_ROLE_SCOPES: dict[Role, frozenset[Scope]] = {
    Role.USER:     USER_SCOPES,
    Role.EDITOR:   EDITOR_SCOPES,
    Role.UPLOADER: UPLOADER_SCOPES,
    Role.ADMIN:    ADMIN_SCOPES,
}


def scopes_for_role(role: Role) -> frozenset[Scope]:
    return _ROLE_SCOPES.get(role, USER_SCOPES)


# ── Permission JSON override → scope adjustments ──────────────────────────────
# Each key in user.permissions can be True (grant) or False (revoke).

_PERM_REVOKE: dict[str, frozenset[Scope]] = {
    "access_gamesdownloader": frozenset({
        Scope.LIBRARY_READ,
        Scope.LIBRARY_DOWNLOAD,
        Scope.LIBRARY_WRITE,
        Scope.LIBRARY_UPLOAD,
        Scope.LIBRARY_ADMIN,
    }),
    "access_emulation": frozenset({
        Scope.ROMS_READ,
        Scope.ROMS_WRITE,
        Scope.PLATFORMS_READ,
        Scope.PLATFORMS_WRITE,
    }),
    "edit_metadata": frozenset({Scope.LIBRARY_WRITE, Scope.GOG_WRITE}),
    "upload":        frozenset({Scope.LIBRARY_UPLOAD}),
}

_PERM_GRANT: dict[str, frozenset[Scope]] = {
    "access_gamesdownloader": frozenset({Scope.LIBRARY_READ, Scope.LIBRARY_DOWNLOAD}),
    "access_emulation":       frozenset({Scope.ROMS_READ, Scope.PLATFORMS_READ}),
    "edit_metadata":          frozenset({Scope.LIBRARY_WRITE}),
    "upload":                 frozenset({Scope.LIBRARY_UPLOAD}),
}


def apply_permission_overrides(
    permissions: dict | None,
    base_scopes: frozenset[Scope],
) -> set[Scope]:
    """Apply user.permissions JSON overrides to base role scopes."""
    scopes = set(base_scopes)
    if not permissions:
        return scopes
    for key, value in permissions.items():
        if value is False and key in _PERM_REVOKE:
            scopes -= _PERM_REVOKE[key]
        elif value is True and key in _PERM_GRANT:
            scopes |= _PERM_GRANT[key]
    return scopes
