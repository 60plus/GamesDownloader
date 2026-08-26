"""Rom - individual ROM file entry in the emulation library."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from models.base import Base
from utils.text import clamp_text


class Rom(Base):
    __tablename__ = "roms"
    __table_args__ = (
        # Composite index - most ROM list queries filter by platform AND exclude missing files
        Index("ix_roms_platform_missing", "platform_id", "missing_from_fs"),
        # A disc kept as a sheet asks which files are its tracks on every
        # download and every deletion, and that is a lookup by the sheet's name
        # within one platform. Spelled the same way in the startup migration, so
        # a database that was migrated and one created fresh end up identical.
        Index("ix_roms_track_of", "platform_id", "track_of"),
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
    cover_url:       Mapped[str | None] = mapped_column(String(1024), nullable=True)  # original remote source (fallback for notifications when public_base_url unset)
    cover_type:      Mapped[str | None] = mapped_column(String(32),  nullable=True)  # box-2D, box-3D, etc.
    cover_aspect:    Mapped[str | None] = mapped_column(String(10),  nullable=True)  # detected from image, e.g. "3/4"
    # Where the cover came from: "manual" for one a person uploaded or chose by
    # URL, "scrape" for one a provider gave us. A forced re-scrape replaces the
    # second and keeps the first, and until this column existed it had to guess
    # from an empty cover_url - which is also what a ScreenScraper cover leaves
    # behind, because those URLs carry credentials and are never stored. So
    # every ScreenScraper cover looked hand-picked and forcing could not touch
    # any of them, which is most of a ROM library.
    cover_source:    Mapped[str | None] = mapped_column(String(16),  nullable=True)
    background_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshots:     Mapped[list | None] = mapped_column(JSON,        nullable=True)
    support_path:    Mapped[str | None] = mapped_column(String(512), nullable=True)  # cartridge/disc art
    wheel_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # wheel/marquee logo
    bezel_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # bezel overlay art
    steamgrid_path:  Mapped[str | None] = mapped_column(String(512), nullable=True)  # Steam Grid banner
    video_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # video file
    picto_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # SS pictoliste icon

    # Where every other picture came from, by slot: {"background": "manual",
    # "wheel": "scrape"}. The cover has a column of its own above, from when it
    # was the only slot that could tell; one function reads both, so there is
    # still one place that decides.
    #
    # A slot missing from here means we do not know, and not knowing means
    # leaving it alone. That is not the same default the cover uses: the cover
    # column was filled in for every existing row by a migration, so a null
    # there is a genuine "no cover", while this column starts empty on every
    # library that already exists. Reading an absence as "a provider gave us
    # this" would have a forced re-scrape delete every background, wheel and
    # bezel anybody had ever uploaded by hand.
    #
    # So an existing library behaves as it always did until its metadata is
    # cleared, and a slot the scrape has written since is refreshed by a forced
    # pass like the cover is.
    media_source:    Mapped[dict | None] = mapped_column(JSON,       nullable=True)

    # ── Hashes ────────────────────────────────────────────────────────────────
    crc_hash:  Mapped[str | None] = mapped_column(String(16),  nullable=True)
    md5_hash:  Mapped[str | None] = mapped_column(String(32),  nullable=True)
    sha1_hash: Mapped[str | None] = mapped_column(String(40),  nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_identified:  Mapped[bool] = mapped_column(Boolean, default=False)
    missing_from_fs: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Multi-disk sets ───────────────────────────────────────────────────────
    # A game too big for one floppy shipped on several, and dumps keep that: one
    # file per disk, each scanned as its own row. These tie the rows back
    # together so the library shows one game while every disk stays a real entry
    # underneath - the scanner fills them, nothing else writes them.
    #
    # extra_disk is what the listings filter on, exactly as they filter
    # missing_from_fs: it marks every disk of a set except the one that stands
    # for the game. Deriving it once beats a window function in a dozen queries.
    disk_group:  Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    disk_number: Mapped[int | None] = mapped_column(nullable=True)
    extra_disk:  Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Disc tracks ───────────────────────────────────────────────────────────
    # A disc kept as a sheet plus its data files: the fs_name of the sheet this
    # file is a track of, and NULL for everything else. It is deliberately not
    # the disk fields above. A track is not a disk - nobody picks one, it has no
    # number and it must never appear in a disk selector - but it does have to
    # travel with its sheet when the disc is downloaded or deleted, or the sheet
    # arrives as two useless kilobytes and the data is orphaned on disk.
    track_of:    Mapped[str | None] = mapped_column(String(255), nullable=True)

    # What an Amiga game calls the disk it saves to. Titles ask for one by name
    # and refuse anything else - Legion wants "ARCHIWUM" and says so on its
    # title screen - so this cannot be guessed and has to be told to GD.
    save_disk_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ── Notifications ─────────────────────────────────────────────────────────
    # When the "recently added" notification was sent for this ROM. NULL = not
    # yet announced (eligible once it has a cover). Set once to avoid re-spam.
    announced_at:   Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    platform: Mapped["RomPlatform"] = relationship(  # noqa: F821
        "RomPlatform", back_populates="roms",
    )

    # Columns a scraper writes, all of them bounded VARCHARs fed by values no
    # provider promises the length of. ScreenScraper in particular returns a
    # publisher list as one string and a descriptive `joueurs` rather than a
    # number. MySQL rejects the whole statement on an oversized value, so one
    # long publisher would discard the cover, the artwork, the genres and every
    # other field written in the same UPDATE - the failure the library side hit
    # for real. Same guard as LibraryGame._clamp_to_column.
    #
    # Deliberately not here: fs_name, fs_name_no_ext, fs_path and fs_extension
    # belong to the filesystem scan, not to a provider, and the ROM's identity
    # key is (platform_id, fs_name) - trimming one would sever the row from its
    # file on disk. Nor the hashes, which are fixed-width by construction.
    @validates("name", "slug", "developer", "publisher", "player_count", "cover_type")
    def _clamp_to_column(self, key: str, value):
        return clamp_text(value, getattr(self.__table__.c[key].type, "length", None))
