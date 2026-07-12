"""Recipient resolution for notification emails.

Different notifications go to different people:
  - recently added        -> every user who can SEE the game/ROM and opted in
  - library sync / request created -> admins (+ any configured alert address)
  - request status change  -> the requester

Emails go out via BCC so recipients never see each other's addresses.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _all_optin_users() -> list:
    """Enabled users with an email who opted in to recently-added mail."""
    from handler.database.users_handler import UsersHandler
    users = await UsersHandler().get_all(limit=100000)
    return [
        u for u in users
        if u.enabled and u.email and getattr(u, "notify_recently_added", True)
    ]


def _dedup(emails: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for e in emails:
        if not e:
            continue
        el = e.strip().lower()
        if el and el not in seen:
            seen.add(el)
            out.append(e.strip())
    return out


async def _extra_admin_addresses() -> list[str]:
    """Configured stand-in addresses for admin-facing mail (Notifications tab
    recipient, or the security-alert recipient)."""
    from handler.config.config_handler import config_handler
    out = []
    for key in ("smtp_notify_to", "alert_smtp_to"):
        v = (await config_handler.get(key) or "").strip()
        if v:
            out.append(v)
    return out


async def admin_recipients() -> list[str]:
    """Emails of every admin user, plus any configured notification/alert
    address. For admin-facing notifications (GOG sync, download, new request)."""
    from handler.database.users_handler import UsersHandler
    from models.user import Role
    users = await UsersHandler().get_all(limit=100000)
    emails = [u.email for u in users if u.enabled and u.email and u.role == Role.ADMIN]
    emails += await _extra_admin_addresses()
    return _dedup(emails)


async def user_recipient(user_id: int | None) -> list[str]:
    """A single user's email (e.g. the requester on a request status change)."""
    if not user_id:
        return []
    from handler.database.users_handler import UsersHandler
    u = await UsersHandler().get_by_id(user_id)
    return [u.email] if (u and u.email) else []


async def recipients_for_library_game(game) -> list[str]:
    """Opted-in users who can actually SEE this library game (per-game deny +
    library visibility respected). Admins always qualify."""
    from handler.database.library_handler import LibraryHandler
    from handler.database.library_registry_handler import library_registry_handler as reg
    from models.user import Role
    lib = LibraryHandler()
    try:
        all_libs = await reg.get_all()
        by_id = {l.id: l for l in all_libs}
        by_slug = {l.slug: l for l in all_libs}
        game_libs = []
        if getattr(game, "source", None) == "gog" and by_slug.get("gog"):
            game_libs.append(by_slug["gog"])
        if getattr(game, "in_default_library", False) and by_slug.get("games"):
            game_libs.append(by_slug["games"])
        for lid in await reg.get_member_library_ids(game.id):
            if lid in by_id:
                game_libs.append(by_id[lid])
    except Exception as e:
        # Fail CLOSED: if we cannot determine the game's libraries we must not
        # guess and broadcast. Raising aborts this send; the scheduled digest
        # leaves its cursor untouched and retries the window on the next tick.
        logger.warning("recipients: library lookup failed for game %s: %s", getattr(game, "id", "?"), e)
        raise

    out: list[str] = []
    for u in await _all_optin_users():
        if u.role == Role.ADMIN:
            out.append(u.email)
            continue
        # Symmetric with recipients_for_rom: a user whose games-library access is
        # revoked (403 on every library route) must not be emailed library games.
        if (u.permissions or {}).get("access_gamesdownloader") is False:
            continue
        if not getattr(game, "is_active", True):
            continue
        try:
            acc = await lib.get_game_access(u.id, game.id)
            if acc and acc.access == "deny":
                continue
        except Exception:
            continue  # fail closed: uncertain per-game access -> do not email
        if not game_libs:
            out.append(u.email)
            continue
        try:
            if any([await reg.user_can_access(u, l) for l in game_libs]):
                out.append(u.email)
        except Exception:
            continue  # fail closed: ACL check failed -> hide, do not broadcast
    return _dedup(out)


async def recipients_for_rom(rom) -> list[str]:
    """Opted-in users for a newly-added ROM. ROMs have no per-ROM access
    control; visibility is the emulation scope, so we include opted-in users
    unless emulation access is explicitly revoked for them (admins always)."""
    from models.user import Role
    out: list[str] = []
    for u in await _all_optin_users():
        if u.role != Role.ADMIN and (u.permissions or {}).get("access_emulation") is False:
            continue
        out.append(u.email)
    return _dedup(out)
