"""LibraryGame - published game available in GamesDownloader library."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

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

    # ── Identity ──────────────────────────────────────────────────────────────
    title: Mapped[str]       = mapped_column(String(255), index=True)
    slug:  Mapped[str]       = mapped_column(String(255), unique=True, index=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    description:       Mapped[str | None] = mapped_column(Text,         nullable=True)
    description_short: Mapped[str | None] = mapped_column(String(512),  nullable=True)
    developer:         Mapped[str | None] = mapped_column(String(255),  nullable=True)
    publisher:         Mapped[str | None] = mapped_column(String(255),  nullable=True)
    release_date:      Mapped[date | None] = mapped_column(Date,        nullable=True)

    # ── Media ─────────────────────────────────────────────────────────────────
    cover_path:      Mapped[str | None] = mapped_column(String(512), nullable=True)
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

    # ── HLTB ──────────────────────────────────────────────────────────────────
    hltb_main_s:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_complete_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Visibility ────────────────────────────────────────────────────────────
    is_active:    Mapped[bool]      = mapped_column(Boolean, default=True)
    published_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    files: Mapped[list[LibraryFile]] = relationship(
        "LibraryFile", back_populates="game", cascade="all, delete-orphan",
        lazy="selectin",
    )
