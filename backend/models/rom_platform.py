"""RomPlatform - console/platform entry in the ROM library."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class RomPlatform(Base):
    __tablename__ = "rom_platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Slugs ──────────────────────────────────────────────────────────────────
    # fs_slug  = the folder name under /data/games/roms/  (e.g. "n64")
    # slug     = normalised internal slug                  (e.g. "nintendo-64")
    fs_slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    slug:    Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name:    Mapped[str] = mapped_column(String(255))

    # User override for display name
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── External scraper IDs ───────────────────────────────────────────────────
    igdb_id:      Mapped[int | None] = mapped_column(Integer,     nullable=True)
    ss_id:        Mapped[int | None] = mapped_column(Integer,     nullable=True)  # ScreenScraper
    launchbox_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Media ──────────────────────────────────────────────────────────────────
    # cover_path = a sample cover grabbed from one of the platform's ROMs (for home card)
    cover_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Flags ──────────────────────────────────────────────────────────────────
    is_identified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    roms: Mapped[list["Rom"]] = relationship(  # noqa: F821
        "Rom", back_populates="platform", lazy="noload",
    )
