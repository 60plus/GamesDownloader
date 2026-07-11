"""Lifecycle event dispatch for plugins.

Builds a stable, plain-dict payload from a LibraryGame ORM row (or an existing
dict) and fires the matching pluggy hook. Kept out of the routers so every
add / publish / torrent / play path emits the same shape.

A misbehaving plugin must NEVER break a library write or a play launch, so every
hook call is isolated - errors are swallowed and logged. The hooks are sync and
expected to be quick; a plugin that needs heavy work should offload it itself
(e.g. a background thread), exactly like the metadata hooks.

When no plugin implements a hook, the pluggy call returns an empty list with
effectively zero cost, so these are safe to fire unconditionally.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def game_payload(game: Any) -> dict[str, Any]:
    """Minimal, stable dict passed to lifecycle hooks. A plugin fetches anything
    more via the API using `id`. Accepts an ORM row or a dict."""
    if isinstance(game, dict):
        return game
    return {
        "id": getattr(game, "id", None),
        "title": getattr(game, "title", None),
        "source": getattr(game, "source", None),
        "slug": getattr(game, "slug", None),
        "gog_game_id": getattr(game, "gog_game_id", None),
    }


def game_added(game: Any) -> None:
    """A game row was created in the library. Fires the plugin lifecycle hook
    (the raw "row added" event a plugin may react to).

    The user-facing "recently added" card is NOT sent here: at creation time the
    row is usually still bare (no cover/description). That notification is driven
    from the post-scrape / publish points via handler.notifications.recently_added
    so the card carries real art - see announce_library_game()."""
    payload = game_payload(game)
    from plugins.manager import plugin_manager
    try:
        plugin_manager.hook.lifecycle_on_game_added(game=payload)
    except Exception:
        logger.exception("lifecycle_on_game_added hook failed")


def download_complete(game: Any, path: str) -> None:
    """Fire lifecycle_on_download_complete after a download finishes."""
    from plugins.manager import plugin_manager
    try:
        plugin_manager.hook.lifecycle_on_download_complete(game=game_payload(game), path=path)
    except Exception:
        logger.exception("lifecycle_on_download_complete hook failed")


def play_start(game: Any) -> None:
    """Fire lifecycle_on_play_start when a game/ROM launches."""
    from plugins.manager import plugin_manager
    try:
        plugin_manager.hook.lifecycle_on_play_start(game=game_payload(game))
    except Exception:
        logger.exception("lifecycle_on_play_start hook failed")


def play_end(game: Any, seconds: int) -> None:
    """Fire lifecycle_on_play_end when a play session ends."""
    from plugins.manager import plugin_manager
    try:
        plugin_manager.hook.lifecycle_on_play_end(game=game_payload(game), seconds=int(seconds or 0))
    except Exception:
        logger.exception("lifecycle_on_play_end hook failed")
