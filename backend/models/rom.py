"""Rom - individual ROM file entry in the emulation library."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Rom(Base):
    __tablename__ = "roms"
    __table_args__ = (
        # Composite index - most ROM list queries filter by platform AND exclude missing files
        Index("ix_roms_platform_missing", "platform_id", "missing_from_fs"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Platform ───────────────────────────────────────────────────────────────
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rom_platforms.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Filesystem ────────────────────────────────────────────────────────────
    fs_name:       Mapped[str] = mapped_column(String(512))        # original filename
    fs_name_no_ext: Mapped[str] = mapped_column(String(512))       # filename without extension
    fs_extension:  Mapped[str] = mapped_column(String(32))         # e.g. "z64", "sfc"
    fs_path:       Mapped[str] = mapped_column(String(1024))       # full directory path
    fs_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    # ── Identity ──────────────────────────────────────────────────────────────
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)  # scraped title
    slug: Mapped[str | None] = mapped_column(String(512), nullable=True)  # url-safe

    # ── Metadata ──────────────────────────────────────────────────────────────
    summary:      Mapped[str | None] = mapped_column(Text,         nullable=True)
    developer:       Mapped[str | None] = mapped_column(String(255),  nullable=True)
    developer_ss_id: Mapped[int | None] = mapped_column(Integer,      nullable=True)
    publisher:       Mapped[str | None] = mapped_column(String(255),  nullable=True)
    publisher_ss_id: Mapped[int | None] = mapped_column(Integer,      nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer,      nullable=True)
    genres:       Mapped[list | None] = mapped_column(JSON,        nullable=True)
    regions:      Mapped[list | None] = mapped_column(JSON,        nullable=True)
    languages:    Mapped[list | None] = mapped_column(JSON,        nullable=True)
    tags:         Mapped[list | None] = mapped_column(JSON,        nullable=True)
    rating:            Mapped[float | None] = mapped_column(Float,      nullable=True)
    ss_score:          Mapped[float | None] = mapped_column(Float,      nullable=True)  # SS raw score 0-20
    igdb_rating:       Mapped[float | None] = mapped_column(Float,      nullable=True)  # IGDB 0-100
    lb_rating:         Mapped[float | None] = mapped_column(Float,      nullable=True)  # LaunchBox 0-10
    plugin_ratings:    Mapped[dict | None]  = mapped_column(JSON,       nullable=True)  # {provider_id: {name, rating, logo_url}}
    player_count:      Mapped[str | None] = mapped_column(String(50),   nullable=True)
    alternative_names: Mapped[list | None] = mapped_column(JSON,        nullable=True)
    franchises:        Mapped[list | None] = mapped_column(JSON,        nullable=True)

    # ── External scraper IDs ──────────────────────────────────────────────────
    igdb_id:      Mapped[int | None] = mapped_column(Integer,      nullable=True)
    ss_id:        Mapped[str | None] = mapped_column(String(100),  nullable=True)  # ScreenScraper
    launchbox_id: Mapped[str | None] = mapped_column(String(100),  nullable=True)
    hltb_id:          Mapped[int | None] = mapped_column(Integer,    nullable=True)
    hltb_main_s:      Mapped[int | None] = mapped_column(Integer,    nullable=True)  # main story in seconds
    hltb_extra_s:     Mapped[int | None] = mapped_column(Integer,    nullable=True)  # main+extra in seconds
    hltb_complete_s:  Mapped[int | None] = mapped_column(Integer,    nullable=True)  # completionist in seconds

    # Raw scraper payloads (kept for re-processing without re-scraping)
    igdb_metadata:      Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ss_metadata:        Mapped[dict | None] = mapped_column(JSON, nullable=True)
    launchbox_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Media ─────────────────────────────────────────────────────────────────
    cover_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)
    cover_type:      Mapped[str | None] = mapped_column(String(32),  nullable=True)  # box-2D, box-3D, etc.
    cover_aspect:    Mapped[str | None] = mapped_column(String(10),  nullable=True)  # detected from image, e.g. "3/4"
    background_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshots:     Mapped[list | None] = mapped_column(JSON,        nullable=True)
    support_path:    Mapped[str | None] = mapped_column(String(512), nullable=True)  # cartridge/disc art
    wheel_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # wheel/marquee logo
    bezel_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # bezel overlay art
    steamgrid_path:  Mapped[str | None] = mapped_column(String(512), nullable=True)  # Steam Grid banner
    video_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # video file
    picto_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # SS pictoliste icon

    # ── Hashes ────────────────────────────────────────────────────────────────
    crc_hash:  Mapped[str | None] = mapped_column(String(16),  nullable=True)
    md5_hash:  Mapped[str | None] = mapped_column(String(32),  nullable=True)
    sha1_hash: Mapped[str | None] = mapped_column(String(40),  nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_identified:  Mapped[bool] = mapped_column(Boolean, default=False)
    missing_from_fs: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    platform: Mapped["RomPlatform"] = relationship(  # noqa: F821
        "RomPlatform", back_populates="roms",
    )
