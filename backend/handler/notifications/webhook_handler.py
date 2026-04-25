"""
Webhook notification sender - Discord rich embeds and generic JSON.

Discord webhooks always return 204 No Content on success.
Generic webhooks are expected to return 200 or 204.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OK_STATUSES = (200, 204)


async def _resolve_template(
    tpl_key: str, default: str, placeholders: dict[str, str]
) -> str:
    """Load a template from config, apply placeholders, fallback to default."""
    try:
        from handler.config.config_handler import config_handler as _cfg
        tpl = (await _cfg.get(f"webhook_{tpl_key}") or "").strip()
    except Exception:
        tpl = ""
    text = tpl if tpl else default
    for k, v in placeholders.items():
        text = text.replace(f"{{{k}}}", v)
    return text


async def notify_if_configured(
    event: str,
    title: str,
    description: str,
    *,
    cover_url: str | None = None,
    fields: list[dict[str, Any]] | None = None,
    color: int = 0x7C3AED,
    tpl_title_key: str = "",
    tpl_body_key: str = "",
    placeholders: dict[str, str] | None = None,
) -> None:
    """Send a webhook notification if webhooks are enabled and event is configured.

    Args:
        event:         "sync" | "download" | "request" (matches webhook_notify_<event> DB key)
        title:         Notification title (default, used if no template)
        description:   Notification body text (default, used if no template)
        cover_url:     Optional cover image URL (used as Discord embed thumbnail)
        fields:        Optional Discord embed fields list
        color:         Discord embed sidebar color (hex int)
        tpl_title_key: Config key for title template (e.g. "tpl_request_new_title")
        tpl_body_key:  Config key for body template (e.g. "tpl_request_new_body")
        placeholders:  Dict of {placeholder: value} for template substitution
    """
    try:
        from handler.config.config_handler import config_handler

        if not await config_handler.get_bool("webhook_enabled"):
            return

        url = (await config_handler.get("webhook_url") or "").strip()
        if not url:
            return

        notify_key = f"webhook_notify_{event}"
        if not await config_handler.get_bool(notify_key, default=True):
            return

        # Apply message templates if configured
        ph = placeholders or {}
        if tpl_title_key:
            title = await _resolve_template(tpl_title_key, title, ph)
        elif ph:
            for k, v in ph.items():
                title = title.replace(f"{{{k}}}", v)
        if tpl_body_key:
            description = await _resolve_template(tpl_body_key, description, ph)
        elif ph:
            for k, v in ph.items():
                description = description.replace(f"{{{k}}}", v)

        wtype = (await config_handler.get("webhook_type") or "generic").strip()
        include_cover = await config_handler.get_bool("webhook_include_cover", default=True)

        if wtype == "discord":
            await send_discord(
                url,
                title=title,
                description=description,
                color=color,
                thumbnail_url=cover_url if include_cover else None,
                fields=fields,
            )
        else:
            await send_generic(url, title, description, cover_url=cover_url)

    except Exception as e:
        logger.warning("Webhook notification failed (event=%s): %s", event, e)


async def send_generic(
    url: str,
    title: str,
    message: str,
    *,
    cover_url: str | None = None,
    source: str = "GamesDownloader",
) -> None:
    """POST a simple JSON payload to the webhook URL."""
    payload = {
        "title":     title,
        "message":   message,
        "cover_url": cover_url or "",
        "source":    source,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code not in _OK_STATUSES:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")


async def send_discord(
    url: str,
    title: str,
    description: str,
    *,
    color: int = 0x7C3AED,
    thumbnail_url: str | None = None,
    fields: list[dict[str, Any]] | None = None,
    footer_text: str = "GamesDownloader",
) -> None:
    """POST a Discord rich embed to the webhook URL.

    Discord always responds with 204 No Content on success.
    Raises RuntimeError on failure so callers can propagate to the user.
    """
    embed: dict[str, Any] = {
        "title":       title,
        "description": description,
        "color":       color,
        "footer":      {"text": footer_text},
    }
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}
    if fields:
        embed["fields"] = fields

    payload: dict[str, Any] = {
        "embeds": [embed],
        "username": "GamesDownloader",
    }
    # Attach custom avatar if configured in Settings > Notifications
    try:
        from handler.config.config_handler import config_handler as _cfg
        avatar = (await _cfg.get("webhook_avatar_url") or "").strip()
        if avatar:
            payload["avatar_url"] = avatar
    except Exception:
        pass
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if resp.status_code not in _OK_STATUSES:
        # Discord returns JSON error body on failure
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(f"Discord responded with HTTP {resp.status_code}: {detail}")
