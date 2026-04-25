"""GOG game model - synced from GOG manifest + scraped metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class GogGame(Base):
    __tablename__ = "gog_games"
    __table_args__ = (
        Index("ix_gog_games_title", "title"),
    )

    gog_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # Owner: NULL = admin's library, INT = specific user's library
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512))

    # Basic metadata (from getFilteredProducts list sync)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    genres: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float | None] = mapped_column(nullable=True)

    # Extended metadata (from GOG API v1/v2 scrape)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)           # full HTML description
    description_short: Mapped[str | None] = mapped_column(Text, nullable=True)     # short plain text
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)           # system requirements {minimum, recommended, per-OS}
    features: Mapped[list | None] = mapped_column(JSON, nullable=True)             # ["Achievements", "Cloud Saves", ...]
    languages: Mapped[dict | None] = mapped_column(JSON, nullable=True)            # {text: [...], audio: [...]}
    videos: Mapped[list | None] = mapped_column(JSON, nullable=True)               # [{provider, video_id}, ...]

    # OS support
    os_windows: Mapped[bool] = mapped_column(default=False)
    os_mac: Mapped[bool] = mapped_column(default=False)
    os_linux: Mapped[bool] = mapped_column(default=False)

    # Media - remote URLs
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    background_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshots: Mapped[list | None] = mapped_column(JSON, nullable=True)          # list of image URLs

    # Media - local paths (downloaded, relative to RESOURCES_PATH)
    cover_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    background_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    icon_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)      # transparent logo from SteamGridDB
    logo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Download / manifest info
    installers: Mapped[dict | None] = mapped_column(JSON, nullable=True)           # {os: [{language, name, size}]}
    extras: Mapped[list | None] = mapped_column(JSON, nullable=True)               # [{name, type}, ...]
    dlcs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Library status
    is_downloaded: Mapped[bool] = mapped_column(default=False)
    download_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # External ratings cache (populated lazily when detail page is first viewed)
    # Format: {"rawg": float | null, "igdb": float | null}
    meta_ratings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # HLTB
    hltb_main_s:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_complete_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Scrape tracking
    scraped: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
