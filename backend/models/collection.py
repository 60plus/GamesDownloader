"""Collections - admin-curated groupings of related games (e.g. a franchise).

A Collection is a game-like entity (its own cover / description / year range /
rating) that groups several LibraryGames through `collection_membership` (M:N).

It is distinct from a *library*:
  - A game stays in its home library (GOG / Games) AND may belong to several
    collections - membership is purely additive, never moves the game.
  - Each collection lives inside a *container* library (a `libraries` row with
    kind "collections"; see models/library.py). Containers are user-created and
    deletable - there is no permanent built-in. `library_id` is that container.

v1 is manual / admin-curated. Covers default to an auto-stack of member covers
(rendered client-side) when `cover_path` is NULL.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Collection(Base):
    __tablename__ = "collections"

    # Parent container library (a `libraries` row with kind "collections").
    # ondelete CASCADE so deleting a container removes its collections; the app
    # also deletes them explicitly (the column is added by an ALTER that does not
    # create the FK on pre-existing tables).
    library_id:  Mapped[int | None] = mapped_column(
        Integer, ForeignKey("libraries.id", ondelete="CASCADE"), index=True, nullable=True,
    )

    slug:        Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name:        Mapped[str] = mapped_column(String(255), index=True)
    # Two descriptions, like a game: the long one shows in the detail "About"
    # section, the short one in the container's list-view hero overlay.
    description:       Mapped[str | None] = mapped_column(Text, nullable=True)
    description_short: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Custom uploaded / scraped cover. When NULL the UI renders an auto-stack of
    # the member covers (newest -> oldest).
    cover_path:  Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Manual overrides. When NULL the API serves values derived from members:
    #   start_year / end_year       -> min / max member release year
    #   rating                      -> average member rating, normalised to 0-5
    #   hltb_main_s / hltb_complete_s -> average member playtime (seconds)
    start_year:      Mapped[int | None]   = mapped_column(Integer, nullable=True)
    end_year:        Mapped[int | None]   = mapped_column(Integer, nullable=True)
    rating:          Mapped[float | None] = mapped_column(Float, nullable=True)
    hltb_main_s:     Mapped[int | None]   = mapped_column(Integer, nullable=True)
    hltb_complete_s: Mapped[int | None]   = mapped_column(Integer, nullable=True)

    sort_order:  Mapped[int] = mapped_column(Integer, default=0)
    created_by:  Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class CollectionMembership(Base):
    __tablename__ = "collection_membership"
    __table_args__ = (
        UniqueConstraint("collection_id", "library_game_id", name="uq_collection_game"),
    )

    collection_id:   Mapped[int] = mapped_column(
        Integer, ForeignKey("collections.id", ondelete="CASCADE"), index=True,
    )
    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )
