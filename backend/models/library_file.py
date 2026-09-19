"""LibraryFile - a downloadable file attached to a LibraryGame."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

# What a file of a game can be: the game itself, a DLC, an extra (a manual, a
# soundtrack, wallpapers) or a mod. Every screen groups and labels files by
# these four, so a value outside them is not stored - it used to be, from any
# upload form, and every screen then drew it as a DLC.
FILE_TYPES = ("game", "dlc", "extra", "mod")

# Other names for the same four: the folders a scan meets (extras/, bonus/,
# mods/) and what GOG calls its extras.
_FILE_TYPE_ALIASES = {"extras": "extra", "bonus": "extra", "mods": "mod"}


def file_type_of(value: str | None) -> str | None:
    """The kind *value* names, or None when it names none of the four."""
    name = (value or "").strip().lower()
    name = _FILE_TYPE_ALIASES.get(name, name)
    return name if name in FILE_TYPES else None


class LibraryFile(Base):
    __tablename__ = "library_files"

    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )

    # ── File info ─────────────────────────────────────────────────────────────
    filename:     Mapped[str]       = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Classification ────────────────────────────────────────────────────────
    file_type: Mapped[str]       = mapped_column(String(16),  default="game")  # FILE_TYPES
    os:        Mapped[str]       = mapped_column(String(16),  default="all")   # windows|mac|linux|all
    language:  Mapped[str | None] = mapped_column(String(8),  nullable=True)
    version:   Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Storage ───────────────────────────────────────────────────────────────
    size_bytes:   Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Relative to GD_BASE_PATH - e.g. "games/GOG/Witcher 3/windows/setup.exe"
    file_path:    Mapped[str]        = mapped_column(String(1024))
    checksum_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Source ────────────────────────────────────────────────────────────────
    source:       Mapped[str]  = mapped_column(String(16), default="custom")  # gog|custom
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Written by the packer when it bundles a platform's loose files into one
    # archive, so "this game is packaged" is a fact on the row rather than a
    # guess from the file name - a .zip somebody uploaded is a game, not a
    # package. Per row, so a game packaged for Windows and left loose for Linux
    # reads correctly. Nothing else writes it, and the row is deleted with the
    # file it describes, so it cannot drift the way a hand-set flag does.
    is_archive:   Mapped[bool] = mapped_column(Boolean, default=False)

    # The account that brought THIS file in, which is not always the account
    # that owns the game it hangs off. A catalogue entry downloaded a second
    # time deliberately reuses the game the first account created, because it is
    # the same game - and until this column existed the quota, being a sum over
    # owned games, charged the second person's gigabytes to the first.
    #
    # Nullable, and the sum falls back to the game's owner when it is not set.
    # Every row that predates this therefore counts exactly as it did before,
    # which a NOT NULL default of anybody would not have managed.
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    game: Mapped[LibraryGame] = relationship("LibraryGame", back_populates="files")


# Avoid circular import - resolve forward ref
from models.library_game import LibraryGame  # noqa: E402
