"""Animated-cover detection.

Covers picked from SteamGridDB can be animated (multi-frame .webp / .gif).
The frontend needs to know which ones are so a theme can pause the animation
until hover (Steam-style). Detection happens once, when the file lands on
disk; the flag is stored in cover_animated next to cover_path.

cover_animated is nullable on purpose: None means "not checked / inherit",
which lets the LibraryGame -> GogGame metadata fallback work the same way it
does for cover_path itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from config import GD_BASE_PATH
except ImportError:
    GD_BASE_PATH = "/data"

logger = logging.getLogger(__name__)

# Only these containers can hold animation frames; anything else is static
# without opening the file.
_ANIMATABLE_EXTS = {".webp", ".gif", ".png", ".apng"}


def resource_url_to_fs_path(url: str | None) -> Path | None:
    """Map a served '/resources/...' URL (optionally with a ?v= cache-buster)
    to its path on disk. Returns None for empty or external URLs."""
    if not url or not url.startswith("/resources/"):
        return None
    rel = url.split("?", 1)[0][len("/resources/"):]
    return Path(GD_BASE_PATH) / "resources" / rel


def is_animated_image(fs_path: Path | str | None) -> bool:
    """True when the image file has more than one frame (animated webp/gif/apng)."""
    if not fs_path:
        return False
    p = Path(fs_path)
    if not p.is_file() or p.suffix.lower() not in _ANIMATABLE_EXTS:
        return False
    try:
        from PIL import Image
        with Image.open(p) as img:
            return bool(getattr(img, "is_animated", False))
    except Exception as exc:
        logger.debug("Animated-image check failed for %s: %s", p, exc)
        return False


def detect_cover_animated(url: str | None) -> bool | None:
    """cover_animated value for a cover URL: None when the cover is unset
    (unknown / inherit), True/False after checking the local file."""
    if not url:
        return None
    return is_animated_image(resource_url_to_fs_path(url))


async def backfill_cover_animated() -> None:
    """One-shot startup pass: flag pre-existing animated covers saved before
    the cover_animated column existed. Only rows whose cover extension can
    animate are opened, so the pass is cheap even on large libraries."""
    from sqlalchemy import or_, select

    from handler.database.session import async_session_factory
    from models.collection import Collection
    from models.gog_game import GogGame
    from models.library_game import LibraryGame

    updated = 0
    for model in (LibraryGame, GogGame, Collection):
        try:
            async with async_session_factory() as session:
                stmt = select(model).where(
                    model.cover_animated.is_(None),
                    model.cover_path.is_not(None),
                    or_(*[model.cover_path.like(f"%{ext}%") for ext in (".webp", ".gif", ".png")]),
                )
                rows = (await session.execute(stmt)).scalars().all()
                for row in rows:
                    row.cover_animated = is_animated_image(
                        resource_url_to_fs_path(row.cover_path)
                    )
                    updated += 1
                await session.commit()
        except Exception as exc:
            logger.warning("cover_animated backfill failed for %s: %s", model.__tablename__, exc)
    if updated:
        logger.info("cover_animated backfill: checked %d cover(s)", updated)
