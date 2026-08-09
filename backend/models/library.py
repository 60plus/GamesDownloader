"""Library registry - data-driven library definitions and game membership.

Replaces the hard-coded set of libraries (GOG / Games / Emulation) with rows in
a `libraries` table so libraries can be enabled/disabled, reordered and (for
collections) user-created. Built-in libraries are seeded on startup and cannot
be deleted, only toggled.

- Built-in "system" libraries (kind "gog", "emulation") derive their games
  implicitly from `library_games.source` / the separate `roms` table; they are
  not membership-driven.
- "games" (custom) and user-created "custom_lib" libraries hold LibraryGames via
  the `library_membership` join table (a game can belong to several).

The word "collection(s)" is NOT used here for user libraries - it belongs to the
separate Collections feature (game groupings, see models/collection.py). The
built-in "collections" index library (kind "collections") is the nav entry that
lists those collections.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Library(Base):
    __tablename__ = "libraries"

    slug:       Mapped[str]  = mapped_column(String(64), unique=True, index=True)
    name:       Mapped[str]  = mapped_column(String(128))
    # "gog" | "custom" | "emulation" | "couch" | "custom_lib" | "collections"
    #   custom_lib  = user-created separate library (e.g. "Kids games")
    #   collections = built-in index library listing Collections (groupings)
    kind:       Mapped[str]  = mapped_column(String(16))
    icon:       Mapped[str | None] = mapped_column(String(512), nullable=True)
    color:      Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled:    Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int]  = mapped_column(Integer, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Relative folder under GAMES_PATH for folder-backed collections (e.g. "CUSTOM").
    storage_folder: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    # Per-user access: "public" (everyone who passes the RBAC scope) or
    # "restricted" (only users on the UserLibraryAccess allowlist, plus admins).
    # Only meaningful for gog / custom / collection libraries.
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    # A storefront rather than a shelf: it lists what the server COULD hold, not
    # what it does. GOG is one; a catalogue of GitHub-hosted ports is another.
    # Themes group these under "Store" instead of alongside the real libraries.
    is_store:   Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether games landing in this library also join the default Games library.
    # Off means the library is a world of its own - its games stay out of the
    # home rails, the genre tiles and the trailer pool. That is right for a shelf
    # of emulators and wrong for a shelf of games, so it is a per-library choice
    # rather than the blanket False that folder scans used to apply.
    adds_to_default_library: Mapped[bool] = mapped_column(Boolean, default=False)
    # The plugin catalogue this store lists, when it is a plugin-backed store.
    # A store library shows its catalog_entries rather than LibraryGames: the
    # entries are the listing, and a download turns one into a game elsewhere
    # (the Games library). NULL for GOG (its store is wired in code) and for
    # every ordinary shelf.
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LibraryMembership(Base):
    __tablename__ = "library_membership"
    __table_args__ = (
        UniqueConstraint("library_id", "library_game_id", name="uq_library_game"),
    )

    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id", ondelete="CASCADE"), index=True,
    )
    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )


class UserLibraryAccess(Base):
    """Allowlist for "restricted" libraries: a row grants `user_id` access to
    `library_id`. Admins bypass this entirely. Only used when a library's
    visibility is "restricted"."""

    __tablename__ = "user_library_access"
    __table_args__ = (
        UniqueConstraint("user_id", "library_id", name="uq_user_library"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id", ondelete="CASCADE"), index=True,
    )
