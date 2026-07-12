"""Recently-added email newsletter (Tautulli / Plex style).

Instead of one email per game the moment it is scraped, the additions are
collected and mailed as a single rich digest on a schedule the admin picks in
Settings -> Notifications (off / immediate / daily at HH:MM / weekly). This
avoids inbox spam on a bulk import while still giving people a nice "here's
what's new" mail.

Design notes:
  * The digest is EMAIL only. Discord / webhook stay immediate per item (they
    are cheap and people expect them live) - see recently_added.py.
  * Content is per-recipient: each opted-in user only sees the games/ROMs they
    can actually access (per-game deny + library ACL), so the mail is built and
    sent individually, not BCC'd.
  * Covers render at their NATURAL aspect (`<img>` with a width and automatic
    height), so a landscape ROM banner is shown wide and a portrait box stays
    tall - no letterbox, no portrait frame forced on a horizontal image. When a
    ROM records `cover_aspect` we use it to switch the card to a top-cover
    layout for landscape art.
  * The window of "what's new" is driven by the same `announced_at` column the
    immediate path stamps, so an item enters the digest once it has a cover
    (i.e. after metadata is scraped) and never twice.

State lives entirely in the config table (no new DB column):
  smtp_recently_added_mode      off | immediate | daily | weekly
  smtp_recently_added_time      "HH:MM" (server local time)
  smtp_recently_added_weekday   0-6 (Mon=0), for weekly
  smtp_recently_added_last_sent ISO-8601 UTC - internal cursor
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from handler.notifications.recently_added import (
    _base_url,
    _resolve_cover,
    _server_name,
    _strip_md_links,
)

logger = logging.getLogger(__name__)

# Section accent colours (match the Discord sidebar colours in recently_added).
_SECTION_COLORS = {
    "Games": "#2d9cdb",
    "GOG":   "#8e44ad",
    "ROMs":  "#e67e22",
}
_SECTION_ORDER = ("Games", "GOG", "ROMs")

_CHECK_INTERVAL_S = 300      # loop wakes every 5 min to see if a slot is due
_INITIAL_SLEEP_S = 120

# The served static root (SPA build) = <backend>/static; platform assets live
# under it (names-png = rasterised name wordmarks, icons = console icons).
_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")

# fs_slug -> the slug the name-logo asset is filed under (mirrors the frontend
# NAME_LOGO_SLUG map in utils/platformMap.ts).
_NAME_LOGO_SLUG = {
    "sfc": "snes", "snesna": "snes", "famicom": "nes", "megadrive": "genesis",
    "megacdjp": "megacd", "saturnjp": "saturn", "neogeocdjp": "neogeocd",
}


def _platform_image_url(base: str, fs_slug: str | None) -> str | None:
    """Public URL for the platform's NAME wordmark (preferred), falling back to
    the console icon, else None (caller shows text). Existence is checked on the
    served static dir so a missing asset never emits a broken <img>."""
    if not (base and fs_slug):
        return None
    b = base.rstrip("/")
    logo_slug = _NAME_LOGO_SLUG.get(fs_slug, fs_slug)
    if os.path.isfile(os.path.join(_STATIC_DIR, "platforms", "names-png", f"{logo_slug}.png")):
        return f"{b}/platforms/names-png/{logo_slug}.png"
    if os.path.isfile(os.path.join(_STATIC_DIR, "platforms", "icons", f"{fs_slug}.png")):
        return f"{b}/platforms/icons/{fs_slug}.png"
    return None


# ── Rating helper ────────────────────────────────────────────────────────────

def _stars(raw: float | None) -> int:
    """Best-effort normalise a rating of unknown scale (0-5, 0-10 or 0-100) to a
    0-5 star count. Returns 0 when there is nothing meaningful to show."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0
    if v <= 0:
        return 0
    if v <= 5:
        s = v
    elif v <= 10:
        s = v / 2.0
    elif v <= 100:
        s = v / 20.0
    else:
        return 0
    return max(0, min(5, round(s)))


def _year_of(value) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value) if value > 0 else ""
    if isinstance(value, str):
        # GogGame.release_date is a string (e.g. "2006-05-30" or "2006").
        m = re.search(r"(19|20)\d{2}", value)
        return m.group(0) if m else ""
    year = getattr(value, "year", None)
    return str(year) if year else ""


def _first(seq) -> str:
    if isinstance(seq, (list, tuple)) and seq:
        return str(seq[0])
    return ""


def _is_landscape(aspect: str | None) -> bool:
    """cover_aspect is stored as "w/h" (e.g. "3/4" portrait, "4/3" landscape)."""
    if not aspect:
        return False
    try:
        w, h = aspect.split("/", 1)
        return float(w) > float(h) * 1.05
    except (ValueError, ZeroDivisionError):
        return False


# ── Card building ────────────────────────────────────────────────────────────

async def _card_from_game(session, game, base: str) -> dict:
    from models.gog_game import GogGame

    title = (game.title or "").strip() or "New game"
    source = (game.source or "custom").strip() or "custom"
    cover_path = game.cover_path
    cover_remote = None
    description = game.description_short or game.description or ""
    # GOG-published rows keep their metadata on the linked GogGame, so fall back
    # to it for the fields the LibraryGame row leaves empty (date, rating...).
    release_date = game.release_date
    rating = game.rating
    genres = game.genres
    if game.gog_game_id:
        gog = await session.get(GogGame, game.gog_game_id)
        if gog is not None:
            cover_path = cover_path or gog.cover_path
            cover_remote = gog.cover_url
            description = description or (gog.description_short or "")
            release_date = release_date or gog.release_date
            if rating is None:
                rating = gog.rating
            genres = genres or gog.genres

    is_gog = source == "gog"
    return {
        "section":    "GOG" if is_gog else "Games",
        "title":      title,
        "description": _strip_md_links(description)[:160],
        "cover_url":  _resolve_cover(base, cover_path, cover_remote),
        "detail_url": (base + f"/games/{game.id}") if base else None,
        "year":       _year_of(release_date),
        "genre":      _first(genres),
        "source_label": "GOG" if is_gog else "Game",
        # GOG source badge is shown as the GOG icon instead of text.
        "source_icon": (base.rstrip("/") + "/icons/gog.png") if (is_gog and base) else None,
        "stars":      _stars(rating),
        "landscape":  False,
        "_key":       f"game:{game.id}",   # stable identity for recipient grouping
    }


async def _card_from_rom(session, rom, base: str) -> dict:
    from models.rom_platform import RomPlatform

    title = (rom.name or rom.fs_name_no_ext or "").strip() or "New ROM"
    platform_slug = None       # long slug for the detail URL (/emulation/<slug>/<id>)
    platform_fs_slug = None    # short folder slug that keys the logo PNG (snes, n64...)
    platform_name = None
    if rom.platform_id:
        plat = await session.get(RomPlatform, rom.platform_id)
        if plat is not None:
            platform_slug = getattr(plat, "slug", None) or getattr(plat, "fs_slug", None)
            platform_fs_slug = getattr(plat, "fs_slug", None)
            platform_name = getattr(plat, "name", None)

    raw_rating = rom.rating or rom.igdb_rating
    if not raw_rating and rom.lb_rating:
        raw_rating = rom.lb_rating * 10.0
    description = rom.summary or ""

    return {
        "section":    "ROMs",
        "title":      title,
        "description": _strip_md_links(description)[:160],
        "cover_url":  _resolve_cover(base, rom.cover_path, rom.cover_url),
        "detail_url": (base + f"/emulation/{platform_slug}/{rom.id}") if (base and platform_slug) else None,
        "year":       _year_of(rom.release_year),
        "genre":      _first(rom.genres),
        "source_label": platform_name or "ROM",
        # Platform shown as its NAME wordmark (falls back to console icon, then
        # to the text badge) - resolved against the served static dir.
        "platform_logo": _platform_image_url(base, platform_fs_slug),
        "stars":      _stars(raw_rating),
        "landscape":  _is_landscape(rom.cover_aspect),
        "_key":       f"rom:{rom.id}",   # stable identity for recipient grouping
    }


# ── HTML rendering (email-safe: tables + inline styles) ──────────────────────

_BG = "#0e1116"
_CARD_BG = "#191f27"
_CARD_BORDER = "#2a323c"
_TXT = "#eef2f6"
_MUTED = "#8a97a6"
_SUB = "#c3ccd4"
_CHIP_BG = "#252c34"
_ACCENT = "#e0a34a"


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


def _chip(text: str, *, color: str = _SUB, bg: str = _CHIP_BG) -> str:
    if not text:
        return ""
    return (f'<span style="display:inline-block;font-size:11px;color:{color};'
            f'background:{bg};border-radius:4px;padding:2px 8px;margin:0 6px 4px 0;">'
            f'{_esc(text)}</span>')


def _stars_html(n: int) -> str:
    if n <= 0:
        return ""
    filled = "&#9733;" * n
    empty = "&#9734;" * (5 - n)
    return (f'<span style="font-size:12px;color:{_ACCENT};letter-spacing:1px;'
            f'white-space:nowrap;">{filled}<span style="color:#4a5560;">{empty}</span></span>')


def _cover_placeholder(width: int, height: int, label: str, color: str) -> str:
    return (f'<div style="width:{width}px;height:{height}px;background:{color};'
            f'border-radius:6px;color:#ffffff;font-size:12px;font-weight:500;'
            f'text-align:center;line-height:1.25;padding:8px;box-sizing:border-box;'
            f'overflow:hidden;">{_esc(label[:40])}</div>')


def _icon_img(url: str, alt: str, height: int) -> str:
    return (f'<img src="{_esc(url)}" alt="{_esc(alt)}" height="{height}" '
            f'style="height:{height}px;width:auto;display:inline-block;'
            f'vertical-align:middle;border:0;margin:0 6px 4px 0;">')


def _source_badge(card: dict) -> str:
    """The source marker: ROM platform logo, GOG icon, else a coloured text chip."""
    if card.get("platform_logo"):
        return _icon_img(card["platform_logo"], card.get("source_label", ""), 20)
    if card.get("source_icon"):
        return _icon_img(card["source_icon"], card.get("source_label", "GOG"), 16)
    return _chip(card.get("source_label", ""),
                 color="#0e1116", bg=_SECTION_COLORS.get(card["section"], _ACCENT))


def _meta_row(card: dict) -> str:
    chips = _chip(card.get("year", "")) + _chip(card.get("genre", "")) + _source_badge(card)
    stars = _stars_html(card.get("stars", 0))
    stars_wrap = f'<span style="margin-left:2px;vertical-align:middle;">{stars}</span>' if stars else ""
    return f'<div style="margin-top:9px;">{chips}{stars_wrap}</div>'


def _card_html(card: dict) -> str:
    title = _esc(card["title"])
    url = card.get("detail_url")
    title_html = (f'<a href="{_esc(url)}" style="color:{_TXT};text-decoration:none;">{title}</a>'
                  if url else f'<span style="color:{_TXT};">{title}</span>')
    desc = card.get("description") or ""
    desc_html = (f'<div style="font-size:12px;color:{_SUB};margin-top:6px;line-height:1.5;">'
                 f'{_esc(desc)}</div>') if desc else ""
    section_color = _SECTION_COLORS.get(card["section"], _ACCENT)
    cover = card.get("cover_url")

    if card.get("landscape"):
        # Landscape art: full-width banner on top, text below - keeps its own
        # aspect (natural height), no portrait letterbox.
        if cover:
            img = (f'<img src="{_esc(cover)}" alt="" width="100%" '
                   f'style="display:block;width:100%;height:auto;border-radius:8px 8px 0 0;">')
        else:
            img = (f'<div style="width:100%;height:150px;background:{section_color};'
                   f'border-radius:8px 8px 0 0;color:#fff;font-size:14px;font-weight:500;'
                   f'text-align:center;line-height:150px;">{title}</div>')
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
               style="background:{_CARD_BG};border:1px solid {_CARD_BORDER};
                      border-radius:10px;overflow:hidden;margin:0;height:100%;">
          <tr><td>{img}</td></tr>
          <tr><td style="padding:10px 12px;">
            <div style="font-size:15px;font-weight:500;">{title_html}</div>
            {desc_html}{_meta_row(card)}
          </td></tr>
        </table>"""

    # Portrait: left thumbnail (fixed width, natural height) + text on the right.
    if cover:
        img = (f'<img src="{_esc(cover)}" alt="" width="64" '
               f'style="display:block;width:64px;height:auto;border-radius:6px;">')
    else:
        img = _cover_placeholder(64, 90, card["title"], section_color)
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
           style="background:{_CARD_BG};border:1px solid {_CARD_BORDER};
                  border-radius:10px;margin:0;height:100%;">
      <tr>
        <td width="64" valign="top" style="padding:10px 0 10px 10px;">{img}</td>
        <td valign="top" style="padding:10px 12px;">
          <div style="font-size:15px;font-weight:500;">{title_html}</div>
          {desc_html}{_meta_row(card)}
        </td>
      </tr>
    </table>"""


def _cards_grid(cards: list[dict]) -> str:
    """Two cards per row (Tautulli-style), email-safe via a 2-column table."""
    rows = ""
    for i in range(0, len(cards), 2):
        left = _card_html(cards[i])
        if i + 1 < len(cards):
            right = (f'<td width="50%" valign="top" style="padding:0 0 10px 5px;">'
                     f'{_card_html(cards[i + 1])}</td>')
        else:
            right = '<td width="50%" style="padding:0 0 10px 5px;">&nbsp;</td>'
        rows += (f'<tr><td width="50%" valign="top" style="padding:0 5px 10px 0;">{left}</td>'
                 f'{right}</tr>')
    return (f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
            f'{rows}</table>')


def render_email(cards: list[dict], *, server_name: str, base: str,
                 subtitle: str = "") -> str:
    """Build the full digest HTML for one recipient from their visible cards."""
    n = len(cards)
    by_section: dict[str, list[dict]] = {}
    for c in cards:
        by_section.setdefault(c["section"], []).append(c)

    sections_html = ""
    for name in _SECTION_ORDER:
        group = by_section.get(name)
        if not group:
            continue
        color = _SECTION_COLORS.get(name, _ACCENT)
        cards_html = _cards_grid(group)
        sections_html += f"""
        <tr><td style="padding:20px 16px 0;">
          <div style="font-size:12px;letter-spacing:1.5px;text-transform:uppercase;
                      color:{color};font-weight:500;padding-bottom:10px;">{_esc(name)}
            <span style="color:{_MUTED};">&nbsp;&middot;&nbsp;{len(group)}</span></div>
          {cards_html}
        </td></tr>"""

    manage = (f'<a href="{_esc(base + "/profile")}" style="color:#6ea8ea;text-decoration:none;">'
              f'Manage preferences</a>') if base else "Manage preferences in your profile"
    sub = _esc(subtitle) if subtitle else f"{n} new item{'s' if n != 1 else ''}"

    # Brand: the GD logo (served publicly from the SPA static dir) when we have a
    # public base URL, else the server name in small caps.
    if base:
        header_brand = (f'<img src="{_esc(base.rstrip("/"))}/GDLOGO.png" alt="{_esc(server_name)}" '
                        f'width="150" style="display:block;margin:0 auto;height:auto;max-width:62%;border:0;">')
    else:
        header_brand = (f'<div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;'
                        f'color:{_MUTED};">{_esc(server_name)}</div>')

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recently added</title></head>
<body style="margin:0;padding:0;background:{_BG};">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:{_BG};font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
    <tr><td align="center" style="padding:28px 12px;">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;width:100%;background:#12171e;border:1px solid {_CARD_BORDER};
                    border-radius:14px;overflow:hidden;">

        <tr><td style="padding:26px 20px 6px;text-align:center;">
          {header_brand}
          <div style="font-size:24px;font-weight:500;color:{_TXT};margin-top:10px;">Recently added</div>
          <div style="font-size:13px;color:{_ACCENT};margin-top:6px;">{sub}</div>
        </td></tr>

        {sections_html}

        <tr><td style="padding:22px 20px;text-align:center;border-top:1px solid #222a32;margin-top:12px;">
          <div style="font-size:12px;color:{_MUTED};">Sent by
            <span style="color:{_SUB};">{_esc(server_name)}</span></div>
          <div style="font-size:12px;color:#5f6b76;margin-top:6px;">
            You get these because "recently added" email is on. {manage}</div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""


def render_text(cards: list[dict], *, server_name: str) -> str:
    """Plain-text alternative body. An HTML-only mail scores worse with spam
    filters (Gmail especially), so every digest ships a text/plain part too."""
    by_section: dict[str, list[dict]] = {}
    for c in cards:
        by_section.setdefault(c["section"], []).append(c)
    lines = [f"{server_name} - Recently added", ""]
    for name in _SECTION_ORDER:
        group = by_section.get(name)
        if not group:
            continue
        lines.append(f"{name} ({len(group)}):")
        for c in group:
            bits = [c["title"]]
            if c.get("year"):
                bits.append(c["year"])
            if c.get("source_label") and c["section"] == "ROMs":
                bits.append(c["source_label"])
            lines.append("  - " + " - ".join(bits))
        lines.append("")
    lines.append('You get these because "recently added" email is on.')
    return "\n".join(lines)


# ── Sending ──────────────────────────────────────────────────────────────────

async def _smtp_config() -> dict | None:
    from handler.config.config_handler import config_handler
    host = (await config_handler.get("smtp_host") or "").strip()
    from_addr = (await config_handler.get("smtp_from_address") or "").strip()
    if not (host and from_addr):
        return None
    try:
        port = int((await config_handler.get("smtp_port")) or "587")
    except (TypeError, ValueError):
        port = 587
    return {
        "host": host, "port": port,
        "user": await config_handler.get("smtp_username") or "",
        "password": await config_handler.get("smtp_password") or "",
        "from_addr": from_addr,
        "tls_mode": "starttls" if await config_handler.get_bool("smtp_use_tls", default=True) else "none",
    }


async def _send_one(cfg: dict, to_addr: str, subject: str, html: str,
                    bcc: list[str] | None = None, text: str | None = None) -> None:
    from handler.email.smtp_sender import send_email
    subject = subject.replace("\r", " ").replace("\n", " ")
    await send_email(
        cfg["host"], cfg["port"], cfg["user"], cfg["password"],
        cfg["from_addr"], to_addr, subject, html, cfg["tls_mode"], bcc=bcc,
        body_text=text,
    )


def _subject_for(cards: list[dict], server_name: str) -> str:
    if len(cards) == 1:
        return f"{server_name}: {cards[0]['title']} added"
    titles = ", ".join(c["title"] for c in cards[:2])
    extra = len(cards) - 2
    if extra > 0:
        titles += f" +{extra} more"
    return f"{server_name}: {len(cards)} new - {titles}"


async def send_single_item(kind: str, obj_id: int) -> bool:
    """Immediate / manual path: build one pretty card and email everyone who can
    see the item (BCC). Used for mode='immediate' and the manual resend button."""
    try:
        from handler.database.session import async_session_factory
        cfg = await _smtp_config()
        if not cfg:
            return False
        base = await _base_url()
        server = await _server_name(base)
        async with async_session_factory() as session:
            if kind == "rom":
                from models.rom import Rom
                obj = await session.get(Rom, obj_id)
                if obj is None:
                    return False
                card = await _card_from_rom(session, obj, base)
            else:
                from models.library_game import LibraryGame
                obj = await session.get(LibraryGame, obj_id)
                if obj is None:
                    return False
                card = await _card_from_game(session, obj, base)

        # An item with no resolvable cover is not a "ready" card - skip the email
        # rather than send an empty title-only one (matches the digest gate).
        if not card.get("cover_url"):
            logger.info("recently-added: skip single-item email for %s id=%s (no cover art)", kind, obj_id)
            return False

        from handler.notifications.recipients import (
            recipients_for_library_game, recipients_for_rom,
        )
        recips = (await recipients_for_rom(obj)) if kind == "rom" else (await recipients_for_library_game(obj))
        recips = [r for r in recips if r]
        # Catch-all "Notification recipient" also gets recently-added mail.
        from handler.config.config_handler import config_handler
        notify_to = (await config_handler.get("smtp_notify_to") or "").strip()
        if notify_to and notify_to not in recips:
            recips.append(notify_to)
        if not recips:
            return False
        html = render_email([card], server_name=server, base=base,
                             subtitle=f"{card['title']} was just added")
        subject = _subject_for([card], server)
        await _send_one(cfg, cfg["from_addr"], subject, html, bcc=recips,
                        text=render_text([card], server_name=server))
        logger.info("recently-added: single-item email sent for %s id=%s to %d recipient(s)",
                    kind, obj_id, len(recips))
        return True
    except Exception as e:
        logger.warning("recently-added: single-item email failed for %s id=%s: %s", kind, obj_id, e)
        return False


async def build_and_send_digest(*, window_start: datetime, window_end: datetime) -> int:
    """Collect items announced in (window_start, window_end], group per recipient
    by what they can access, and send each a personalised digest. Returns the
    number of emails sent."""
    from handler.database.session import async_session_factory
    from handler.notifications.recipients import (
        recipients_for_library_game, recipients_for_rom,
    )
    from models.library_game import LibraryGame
    from models.rom import Rom
    from sqlalchemy import select

    cfg = await _smtp_config()
    if not cfg:
        return 0
    base = await _base_url()
    server = await _server_name(base)

    ws = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    we = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    items: list[tuple[str, object, dict]] = []
    async with async_session_factory() as session:
        games = (await session.execute(
            select(LibraryGame)
            .where(LibraryGame.announced_at.isnot(None),
                   LibraryGame.announced_at > ws, LibraryGame.announced_at <= we,
                   LibraryGame.is_active.is_(True))
            .order_by(LibraryGame.announced_at.desc())
        )).scalars().all()
        roms = (await session.execute(
            select(Rom)
            .where(Rom.announced_at.isnot(None),
                   Rom.announced_at > ws, Rom.announced_at <= we)
            .order_by(Rom.announced_at.desc())
        )).scalars().all()
        # Only announce items that resolve to real cover art. A recently-added
        # card without a cover is broken, and a coverless row that still carries
        # an announced_at (a one-off backfill, a manual force-send, or a
        # removed/orphaned entry that was never hard-deleted) must not leak into
        # the newsletter - this mirrors the auto-announce contract, which also
        # requires a resolvable cover before it will announce.
        for g in games:
            card = await _card_from_game(session, g, base)
            if card.get("cover_url"):
                items.append(("game", g, card))
        for r in roms:
            card = await _card_from_rom(session, r, base)
            if card.get("cover_url"):
                items.append(("rom", r, card))

    if not items:
        return 0

    per_email: dict[str, list[dict]] = {}
    for kind, obj, card in items:
        recips = (await recipients_for_rom(obj)) if kind == "rom" else (await recipients_for_library_game(obj))
        for e in recips:
            if e:
                per_email.setdefault(e, []).append(card)

    # The "Notification recipient" (smtp_notify_to) is an optional catch-all that
    # receives the full digest regardless of per-game access - a mailbox that
    # sees everything that was added.
    from handler.config.config_handler import config_handler
    notify_to = (await config_handler.get("smtp_notify_to") or "").strip()
    if notify_to:
        per_email[notify_to] = [card for _, _, card in items]

    # Group recipients who receive the SAME content and send each group ONE
    # message with all of them BCC'd - a single sendmail call, like Tautulli.
    # Sending N separate identical mails (one sendmail each) makes relays/Gmail
    # treat the later ones as duplicates and drop them, so only the first lands.
    # Signature is the set of underlying item identities (NOT the rendered URLs,
    # which collapse to "" when public_base_url is unset and could merge two
    # same-titled but differently-visible games into one message).
    groups: dict[tuple, dict] = {}
    for email, cards in per_email.items():
        sig = tuple(sorted(c.get("_key") or c["title"] for c in cards))
        g = groups.setdefault(sig, {"cards": cards, "emails": []})
        g["emails"].append(email)

    sent = 0
    failures = 0
    for idx, g in enumerate(groups.values()):
        emails = list(dict.fromkeys(g["emails"]))
        cards = g["cards"]
        try:
            if idx:
                await asyncio.sleep(0.5)   # pace groups so the relay doesn't throttle a burst
            html = render_email(cards, server_name=server, base=base)
            # from_addr is the visible To placeholder; the real audience is BCC.
            await _send_one(cfg, cfg["from_addr"], _subject_for(cards, server), html,
                            bcc=emails, text=render_text(cards, server_name=server))
            sent += len(emails)
        except Exception as e:
            failures += 1
            logger.warning("recently-added digest: send to %s failed: %s", emails, e)
    logger.info("recently-added digest: %d item(s) -> %d recipient(s) in %d message(s)",
                len(items), sent, len(groups))
    # Surface failure so the caller does NOT advance the cursor past items that
    # were never delivered - the window is retried on the next tick instead.
    if failures:
        raise RuntimeError(f"recently-added digest: {failures} of {len(groups)} message group(s) failed")
    return sent


# ── Scheduling ───────────────────────────────────────────────────────────────

def _parse_hhmm(s: str) -> tuple[int, int]:
    try:
        hh, mm = (s or "09:00").split(":", 1)
        return max(0, min(23, int(hh))), max(0, min(59, int(mm)))
    except (ValueError, AttributeError):
        return 9, 0


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def check_and_send_digest() -> bool:
    """Called on a timer. Sends the digest when the configured daily/weekly slot
    has just passed and it hasn't been sent for that slot yet. Returns True if a
    digest went out."""
    from handler.config.config_handler import config_handler

    mode = (await config_handler.get("smtp_recently_added_mode") or "off").strip().lower()
    if mode not in ("daily", "weekly"):
        return False

    now_local = datetime.now().astimezone()          # aware, system tz
    now_utc = now_local.astimezone(timezone.utc)
    hh, mm = _parse_hhmm(await config_handler.get("smtp_recently_added_time") or "09:00")
    slot_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if mode == "weekly":
        try:
            weekday = int(await config_handler.get("smtp_recently_added_weekday") or "0")
        except (TypeError, ValueError):
            weekday = 0
        if now_local.weekday() != weekday:
            return False

    if now_local < slot_local:
        return False   # today's slot not reached yet

    last_sent = _parse_iso(await config_handler.get("smtp_recently_added_last_sent") or "")

    # First run ever: initialise the cursor and skip, so we never dump the whole
    # back-catalogue as one giant first newsletter.
    if last_sent is None:
        await config_handler.set("smtp_recently_added_last_sent", now_utc.isoformat())
        return False

    # At most one digest per local day. Guards the case where the admin raises
    # the configured time later the same day (slot_local moves forward but the
    # cursor stays), which would otherwise fire a second digest.
    if last_sent.astimezone().date() == now_local.date():
        return False

    if last_sent >= slot_local:
        return False   # already sent for this slot

    try:
        await build_and_send_digest(window_start=last_sent, window_end=now_utc)
        await config_handler.set("smtp_recently_added_last_sent", now_utc.isoformat())
        return True
    except Exception as e:
        logger.warning("recently-added digest: scheduled send failed: %s", e)
        return False


async def send_now(days: int = 7) -> int:
    """Send a digest immediately for the last `days` days, ignoring the schedule.
    Used by the 'Send digest now' test button. Advances the cursor."""
    from handler.config.config_handler import config_handler
    now_utc = datetime.now(timezone.utc)
    # Clamp the window start back to the real cursor if it is older than `days`,
    # so manually sending never advances the cursor past items that were never
    # digested (which would drop them from every future scheduled digest).
    last_sent = _parse_iso(await config_handler.get("smtp_recently_added_last_sent") or "")
    default_start = now_utc - timedelta(days=days)
    window_start = min(default_start, last_sent) if last_sent else default_start
    sent = await build_and_send_digest(window_start=window_start, window_end=now_utc)
    await config_handler.set("smtp_recently_added_last_sent", now_utc.isoformat())
    return sent


async def digest_loop() -> None:
    """Background task: check every few minutes whether a digest slot is due."""
    await asyncio.sleep(_INITIAL_SLEEP_S)
    while True:
        try:
            await check_and_send_digest()
        except Exception as e:
            logger.warning("recently-added digest loop error: %s", e)
        await asyncio.sleep(_CHECK_INTERVAL_S)
