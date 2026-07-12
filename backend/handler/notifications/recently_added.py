"""Rich "recently added to the library" notifications (Tautulli / Plex style).

One card per game/ROM: a clickable title linking to its detail page, the short
description, a large aspect-preserving cover image, "View Details" links and a
timestamp - delivered to Discord (rich embed) and optionally email.

Two triggers:
  * automatic - fired once per item, the first time it has a cover (i.e. after
    metadata is scraped), guarded by the ``announced_at`` column so a re-scrape
    or an edit never re-announces, and burst-capped so a bulk import can't flood.
  * manual - the "(re)send notification" button in the metadata editor calls the
    ``/announce`` endpoints with ``force=True``, which bypasses both guards.

Kept separate from webhook_handler (the low-level Discord/webhook sender) so the
resolution logic (public URLs, detail links, server name, dedupe) lives in one
place and both library games and ROMs share it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sidebar colour per source, so the card reads at a glance.
_SOURCE_COLORS = {
    "gog":     0x8E44AD,   # GOG purple
    "custom":  0x2D9CDB,   # blue
    "torrent": 0x27AE60,   # green
    "rom":     0xE67E22,   # emulation orange
}
_DEFAULT_COLOR = 0x7C3AED

# Burst guard: at most _BURST_CAP automatic cards per _BURST_WINDOW_S seconds.
# A one-off bulk import (fresh library scan + scrape-all) would otherwise send
# hundreds of messages; beyond the cap we suppress + log. Manual sends bypass it.
_BURST_WINDOW_S = 60.0
_BURST_CAP = 20
_burst = {"start": 0.0, "count": 0, "suppressed": 0}

# Keep references to fire-and-forget tasks so they are not garbage-collected
# before they run (see audit note on bare asyncio.create_task).
_tasks: set[asyncio.Task] = set()


def _auto_allowed() -> bool:
    """Rate-limit automatic announcements to avoid flooding on a bulk import."""
    now = time.monotonic()
    if now - _burst["start"] > _BURST_WINDOW_S:
        if _burst["suppressed"]:
            logger.info(
                "recently-added: suppressed %d automatic announcement(s) to avoid a flood",
                _burst["suppressed"],
            )
        _burst["start"] = now
        _burst["count"] = 0
        _burst["suppressed"] = 0
    if _burst["count"] >= _BURST_CAP:
        _burst["suppressed"] += 1
        return False
    _burst["count"] += 1
    return True


def _public_url(base: str, path: str | None) -> str | None:
    """Turn a stored root-relative path into an absolute URL using public_base_url.

    Already-absolute http(s) values pass through as-is. A root-relative path
    needs public_base_url so Discord's server can fetch it; without a base we
    return None rather than an unreachable relative URL. Used for detail links.
    """
    if not path:
        return None
    p = path.strip()
    if p.startswith(("http://", "https://")):
        return p
    if not base:
        return None
    return base.rstrip("/") + "/" + p.lstrip("/")


# Query-string / userinfo markers that mean the URL carries a secret. Such a
# URL must NEVER be handed to a third party: Discord (and generic webhooks)
# fetch embed images server-side, which would leak the credential. ScreenScraper
# media URLs, for instance, embed the dev password AND the account password.
_CRED_MARKERS = (
    "password=", "passwd=", "pwd=", "sspassword=", "devpassword=",
    "apikey=", "api_key=", "api-key=", "key=", "access_token=", "token=",
    "secret=", "sig=", "signature=", "auth=", "hash=", "sessionid=", "session=",
)


def _is_leaky_url(url: str) -> bool:
    """True if the URL embeds credentials/secrets and must not be sent out.

    Webhooks and Discord fetch embed images server-side, so a credential in the
    URL would leak to the third party. Rejected URLs fall back to serving the
    local copy via public_base_url (see _resolve_cover)."""
    u = (url or "").lower()
    authority = u.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:                       # https://user:pass@host/...
        return True
    if any(m in u for m in _CRED_MARKERS):
        return True
    if "screenscraper.fr" in authority:        # media API always authenticated
        return True
    return False


def _strip_md_links(text: str) -> str:
    """Neutralise Discord masked-link markdown `[label](url)` in scraped text so
    a description can't smuggle a clickable link into the embed - keep the label,
    drop the target."""
    import re
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")


def _resolve_cover(base: str, local_path: str | None, remote_url: str | None = None) -> str | None:
    """Pick a publicly-fetchable, credential-free cover URL for the notification.

    Order (matches the user's intent):
      1. If the stored cover is already an absolute http(s) URL, use it.
      2. Else, if public_base_url is set, serve the local copy from there
         (media is downloaded to the server and served locally - rule: local).
      3. Else fall back to the original remote URL the art came from (e.g. GOG's
         public CDN) so the image still shows without a public base.
    URLs that carry credentials (e.g. ScreenScraper's authenticated media API,
    the usual source for ROM box art) are rejected - they would leak secrets to
    Discord - so such ROM covers need public_base_url set to serve locally.
    """
    lp = (local_path or "").strip()
    if lp.startswith(("http://", "https://")):
        return None if _is_leaky_url(lp) else lp
    if base and lp:
        return base.rstrip("/") + "/" + lp.lstrip("/")
    ru = (remote_url or "").strip()
    if ru.startswith(("http://", "https://")) and not _is_leaky_url(ru):
        return ru
    return None


async def _server_name(base: str) -> str:
    from handler.config.config_handler import config_handler
    name = (await config_handler.get("server_name") or "").strip()
    if name:
        return name
    if base:
        host = urlparse(base).hostname or ""
        if host:
            return host
    return "GamesDownloader"


async def _base_url() -> str:
    from handler.config.config_handler import config_handler
    return (await config_handler.get("public_base_url") or "").strip().rstrip("/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _claim(model, row_id: int) -> bool:
    """Atomically stamp announced_at only if it is still NULL. Returns True iff
    THIS call set it - used to claim before delivering (so two concurrent
    triggers can't double-send) and to suppress burst-capped items."""
    from sqlalchemy import update
    from handler.database.session import async_session_factory
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session_factory() as session:
        async with session.begin():
            res = await session.execute(
                update(model)
                .where(model.id == row_id, model.announced_at.is_(None))
                .values(announced_at=now)
            )
    return (res.rowcount or 0) == 1


async def _email_mode() -> str:
    """Recently-added email delivery mode: off | immediate | daily | weekly.
    daily/weekly are handled by the digest scheduler (handler.notifications.
    digest); only 'immediate' sends per item from the announce path."""
    from handler.config.config_handler import config_handler
    return (await config_handler.get("smtp_recently_added_mode") or "off").strip().lower()


async def _delivery_configured() -> bool:
    """True if at least one channel is set up to record/deliver an 'added'
    notification. An auto-announce checks this first so it does not consume the
    one-shot when nothing would happen. For email, ANY non-off mode counts: even
    a daily/weekly digest needs announced_at stamped now so the item enters the
    next newsletter window (the send itself happens later)."""
    from handler.config.config_handler import config_handler
    if (await config_handler.get_bool("webhook_enabled")
            and (await config_handler.get("webhook_url") or "").strip()
            and await config_handler.get_bool("webhook_notify_added", default=True)):
        return True
    if (await _email_mode()) != "off":
        host = (await config_handler.get("smtp_host") or "").strip()
        from_addr = (await config_handler.get("smtp_from_address") or "").strip()
        if host and from_addr:   # recipients are opted-in users, resolved at send time
            return True
    return False


async def _maybe_email_now(kind: str, obj_id: int, *, force: bool) -> None:
    """Immediate single-item email, ONLY in 'immediate' mode. In daily/weekly the
    digest scheduler owns email, so neither the auto path nor a manual resend
    sends an off-cycle mail (that would duplicate the item in the next digest,
    since both select it by announced_at). 'off' sends nothing. Discord/webhook
    still fire immediately via _deliver regardless of this."""
    if (await _email_mode()) == "immediate":
        from handler.notifications.digest import send_single_item
        await send_single_item(kind, obj_id)


async def _deliver(
    *,
    source: str,
    title: str,
    description: str,
    detail_url: str | None,
    cover_url: str | None,
    server_name: str,
) -> None:
    """Send the resolved card to Discord / webhook (immediate, per item).

    Email is handled separately: 'immediate' mode and the manual resend button
    send a single-item card right away (handler.notifications.digest.
    send_single_item); daily/weekly modes collect items into a scheduled
    newsletter instead."""
    from handler.notifications.webhook_handler import notify_if_configured

    color = _SOURCE_COLORS.get(source, _DEFAULT_COLOR)
    # Scraped/plugin text may contain masked-link markdown - strip it so a
    # description can't smuggle a clickable link into the embed.
    description = _strip_md_links(description or "")
    ph = {"title": title, "source": source, "server": server_name, "description": description}

    # "View Details" links to the game's own page in this library (the truth of
    # where it lives) - not to any external store. Omitted when public_base_url
    # is unset (no absolute link can be built).
    fields = (
        [{"name": "View Details", "value": f"[Open in {server_name}]({detail_url})", "inline": False}]
        if detail_url else None
    )

    # Webhook / Discord (notify_if_configured swallows its own errors; it also
    # sets allowed_mentions so a crafted title can never ping the server).
    await notify_if_configured(
        "added",
        title=title,
        description=description,
        title_url=detail_url,
        image_url=cover_url,
        timestamp=_now_iso(),
        content=f"({server_name}) {title} was recently added.",
        fields=fields,
        color=color,
        tpl_title_key="tpl_added_title",
        tpl_body_key="tpl_added_body",
        tpl_content_key="tpl_added_content",
        placeholders=ph,
    )


# ── Library games (custom / torrent / GOG-published) ────────────────────────────

async def announce_library_game(game_id: int, *, force: bool = False) -> bool:
    """Announce a library game as recently added. Returns True if a card was sent.

    Automatic (force=False): skipped if already announced, if it has no cover
    yet, or if the burst cap is hit. Manual (force=True) bypasses all three.
    """
    try:
        from handler.database.session import async_session_factory
        from models.gog_game import GogGame
        from models.library_game import LibraryGame

        base = await _base_url()

        async with async_session_factory() as session:
            game = await session.get(LibraryGame, game_id)
            if game is None:
                return False
            if game.announced_at is not None and not force:
                return False

            title = (game.title or "").strip() or "New game"
            source = (game.source or "custom").strip() or "custom"
            cover_path = game.cover_path
            cover_remote = None
            description = game.description_short or ""
            # GOG-published rows inherit media/description from the linked GogGame.
            if game.gog_game_id:
                gog = await session.get(GogGame, game.gog_game_id)
                if gog is not None:
                    cover_path = cover_path or gog.cover_path
                    cover_remote = gog.cover_url  # original CDN link (fallback)
                    description = description or (gog.description_short or "")

        cover_url = _resolve_cover(base, cover_path, cover_remote)
        if not cover_url and not force:
            return False   # not ready; leave announced_at NULL for a later scrape
        # Auto path: don't consume the one-shot if no channel would deliver.
        if not force and not await _delivery_configured():
            return False
        if not force and not _auto_allowed():
            await _claim(LibraryGame, game_id)   # burst-capped: suppress, don't re-announce later
            return False
        # Claim before delivering so two concurrent triggers can't double-send.
        if not force and not await _claim(LibraryGame, game_id):
            return False

        detail_url = (base + f"/games/{game_id}") if base else None
        server = await _server_name(base)
        await _deliver(
            source=source, title=title, description=description[:400],
            detail_url=detail_url, cover_url=cover_url, server_name=server,
        )
        await _maybe_email_now("game", game_id, force=force)
        if force:
            await _claim(LibraryGame, game_id)   # mark so the auto path won't duplicate later
        logger.info("recently-added: announced library game id=%s '%s'", game_id, title)
        return True
    except Exception as e:
        logger.warning("recently-added: library game id=%s failed: %s", game_id, e)
        return False


# ── ROMs (emulation) ────────────────────────────────────────────────────────────

async def announce_rom(rom_id: int, *, force: bool = False) -> bool:
    """Announce a ROM as recently added. Landscape box art (e.g. Genesis 4/3) is
    sent as Discord's big image, which preserves aspect ratio - no portrait
    letterbox. Returns True if a card was sent."""
    try:
        from handler.database.session import async_session_factory
        from models.rom import Rom
        from models.rom_platform import RomPlatform

        base = await _base_url()

        async with async_session_factory() as session:
            rom = await session.get(Rom, rom_id)
            if rom is None:
                return False
            if rom.announced_at is not None and not force:
                return False
            title = (rom.name or rom.fs_name_no_ext or "").strip() or "New ROM"
            cover_path = rom.cover_path
            cover_remote = rom.cover_url  # original scrape source (fallback)
            description = rom.summary or ""
            platform_slug = None
            platform_name = None
            if rom.platform_id:
                plat = await session.get(RomPlatform, rom.platform_id)
                if plat is not None:
                    platform_slug = getattr(plat, "slug", None) or getattr(plat, "fs_slug", None)
                    platform_name = getattr(plat, "name", None)

        cover_url = _resolve_cover(base, cover_path, cover_remote)
        if not cover_url and not force:
            return False   # not ready; leave announced_at NULL for a later scrape
        if not force and not await _delivery_configured():
            return False
        if not force and not _auto_allowed():
            await _claim(Rom, rom_id)   # burst-capped: suppress, don't re-announce later
            return False
        if not force and not await _claim(Rom, rom_id):
            return False

        detail_url = (
            base + f"/emulation/{platform_slug}/{rom_id}" if (base and platform_slug) else None
        )
        server = await _server_name(base)
        desc = description[:400]
        if platform_name and not desc:
            desc = platform_name
        await _deliver(
            source="rom", title=title, description=desc,
            detail_url=detail_url, cover_url=cover_url, server_name=server,
        )
        await _maybe_email_now("rom", rom_id, force=force)
        if force:
            await _claim(Rom, rom_id)   # mark so the auto path won't duplicate later
        logger.info("recently-added: announced ROM id=%s '%s'", rom_id, title)
        return True
    except Exception as e:
        logger.warning("recently-added: ROM id=%s failed: %s", rom_id, e)
        return False


# ── Fire-and-forget schedulers (for hot paths that must not block) ──────────────

def _schedule(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    except RuntimeError:
        # No running loop (called from a sync/non-async context) - run it.
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.warning("recently-added: standalone run failed: %s", e)


def schedule_library_game(game_id: int, *, force: bool = False) -> None:
    """Non-blocking auto-announce for a library game."""
    _schedule(announce_library_game(game_id, force=force))


def schedule_rom(rom_id: int, *, force: bool = False) -> None:
    """Non-blocking auto-announce for a ROM."""
    _schedule(announce_rom(rom_id, force=force))
