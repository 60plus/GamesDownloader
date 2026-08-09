"""LibraryGame - published game available in GamesDownloader library."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from models.base import Base
from utils.ratings import normalize_star_5

if TYPE_CHECKING:
    # SQLAlchemy resolves the relationship via the string name "LibraryFile";
    # this import only feeds static analysers (ruff F821, mypy) so the type
    # annotation `Mapped[list["LibraryFile"]]` resolves without a runtime
    # circular import.
    from models.library_file import LibraryFile  # noqa: F401


class LibraryGame(Base):
    __tablename__ = "library_games"

    # ── Source ────────────────────────────────────────────────────────────────
    # gog_game_id set → game was published from GOG library
    # gog_game_id None + source="custom" → manually added / scanned from CUSTOM folder
    gog_game_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("gog_games.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    source: Mapped[str] = mapped_column(String(16), default="custom")  # "gog" | "custom"

    # A game downloaded from a plugin catalogue remembers where it came from. The
    # store and its catalog_entries are the plugin's to own and are deleted when
    # it is uninstalled, but the game stays in the Games library - so a reinstall
    # can re-link its fresh entry to this game by (catalog_id, external_id)
    # instead of offering a second download of something already here. NULL for
    # GOG games and hand-added ones.
    catalog_id:          Mapped[str | None] = mapped_column(String(64),  nullable=True)
    catalog_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    title: Mapped[str]       = mapped_column(String(255), index=True)
    slug:  Mapped[str]       = mapped_column(String(255), unique=True, index=True)
    # A qualifier shown under the title, not a description. It exists because a
    # catalogue can offer two builds of one game - "Mario Kart 64" by way of
    # SpaghettiKart and by way of the recompilation - and without it the two are
    # indistinguishable on a shelf. description_short is the game's tagline and
    # gets filled by the metadata scraper, so it cannot double as this.
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    description:       Mapped[str | None] = mapped_column(Text,         nullable=True)
    description_short: Mapped[str | None] = mapped_column(String(512),  nullable=True)
    developer:         Mapped[str | None] = mapped_column(String(255),  nullable=True)
    publisher:         Mapped[str | None] = mapped_column(String(255),  nullable=True)
    release_date:      Mapped[date | None] = mapped_column(Date,        nullable=True)

    # ── Media ─────────────────────────────────────────────────────────────────
    cover_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)
    # True = multi-frame cover (animated webp/gif). Nullable so a NULL falls
    # back to the linked GogGame the same way cover_path does.
    cover_animated:  Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    background_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_path:       Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon_path:       Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Classification ────────────────────────────────────────────────────────
    genres:   Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags:     Mapped[list | None] = mapped_column(JSON, nullable=True)
    features: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Ratings ───────────────────────────────────────────────────────────────
    rating:       Mapped[float | None]      = mapped_column(nullable=True)
    meta_ratings: Mapped[dict | None]       = mapped_column(JSON, nullable=True)

    # ── OS support ────────────────────────────────────────────────────────────
    os_windows: Mapped[bool] = mapped_column(Boolean, default=False)
    os_mac:     Mapped[bool] = mapped_column(Boolean, default=False)
    os_linux:   Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Extra info ────────────────────────────────────────────────────────────
    languages:    Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    screenshots:  Mapped[list | None] = mapped_column(JSON, nullable=True)
    videos:       Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Local trailer copy served from /resources (downloaded or uploaded);
    # players prefer it over the external providers in `videos`.
    video_path:   Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── HLTB ──────────────────────────────────────────────────────────────────
    hltb_main_s:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_complete_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Visibility ────────────────────────────────────────────────────────────
    is_active:    Mapped[bool]      = mapped_column(Boolean, default=True)
    # Whether the game appears in the built-in "games" library. Unchecked in
    # Edit Metadata > Details when an admin wants it only in custom collections.
    in_default_library: Mapped[bool] = mapped_column(Boolean, default=True)
    published_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # ── Notifications ─────────────────────────────────────────────────────────
    # When the "recently added to the library" notification was sent for this
    # game. NULL = not yet announced (eligible for the one-shot auto-announce
    # once the game has a cover). Set once so re-scrapes/edits never re-spam.
    announced_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    files: Mapped[list[LibraryFile]] = relationship(
        "LibraryFile", back_populates="game", cascade="all, delete-orphan",
        lazy="selectin",
    )

    @validates("rating")
    def _normalize_rating(self, _key: str, value):
        """Keep the 0-5 star invariant no matter which writer sets it.

        The editor apply, the scrape derive, the catalogue push and the GOG
        adopt all assign here, and they do not all arrive on the same scale - a
        0-10 RAWG value (rawg*2 from the metadata search) once landed verbatim
        and rendered as 8.8 out of 5. Normalising at the column is the single
        place every write passes through; see utils.ratings.normalize_star_5.
        Note SQLAlchemy does not run validators on load, so a row written before
        this guard keeps its stored value until it is written again.
        """
        return normalize_star_5(value)
