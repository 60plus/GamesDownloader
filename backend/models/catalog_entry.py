"""What a catalogue plugin offers, and what came of it.

One row per catalogue entry. It outlives the LibraryGame it points at: an entry
whose repository has gone quiet, or whose newest release turned out to be a
prerelease, still belongs in the catalogue as something the admin can see and
reason about. Dropping it would make the sync look like it silently lost
entries.

The downloadable builds live here as JSON rather than as rows. Nothing queries
inside them - they are read whole when the detail page or the downloader asks
what is on offer - and they are replaced wholesale on every sync, which a child
table would turn into a delete-and-reinsert dance for no gain. Once a build is
actually downloaded it becomes a LibraryFile, and that is a row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CatalogEntry(Base):
    __tablename__ = "catalog_entries"
    __table_args__ = (
        UniqueConstraint("catalog_id", "external_id", name="uq_catalog_entry"),
    )

    # Which catalogue this came from (the plugin's library_catalog_id).
    catalog_id:  Mapped[str] = mapped_column(String(64), index=True)
    # Identity within that catalogue. Matched on across syncs, so it has to
    # survive a retitle - a repository path rather than a display name.
    external_id: Mapped[str] = mapped_column(String(255))

    # The published row, once there is one. SET NULL rather than CASCADE: an
    # admin deleting the game should leave the catalogue entry standing, ready
    # to be published again, not quietly erase the offer.
    library_game_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # What this sync wrote onto the game. Kept so the next one can tell "the
    # admin renamed it" from "the catalogue renamed it" and leave a manual edit
    # standing instead of stamping over it every few hours.
    title:    Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The name exactly as the catalogue gave it, before any parsing. The
    # metadata search falls back to this when the parsed name matches nothing.
    catalog_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Remembered so a re-sync can tell "same artwork" from "new artwork" and
    # skip the download. Seventy-seven icons an hour is not a rate limit
    # problem, it is a politeness one.
    icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # The icon downloaded to /resources and served locally, for the store view.
    # icon_url is the remote source kept for change detection; this is the copy
    # a page renders, because no page in GD hot-links a CDN. A catalogue entry
    # is not a game, so its artwork lives here rather than on a LibraryGame that
    # only exists once the entry is downloaded.
    icon_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Newest release seen. Tags are not versions in the wild - "continuous",
    # "latest" and "ci-dev-build" all occur - so released_at plus the asset
    # digests, not the tag, decide whether something is new.
    release_tag:   Mapped[str | None] = mapped_column(String(128), nullable=True)
    released_at:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_prerelease: Mapped[bool] = mapped_column(Boolean, default=False)
    assets:        Mapped[list | None] = mapped_column(JSON, nullable=True)

    # False when the entry cannot be offered right now. The reason is shown to
    # the admin, because "77 entries, 4 unavailable" is a useful sync result and
    # "73 entries" is a mystery.
    available:          Mapped[bool] = mapped_column(Boolean, default=True)
    unavailable_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Metadata pass ─────────────────────────────────────────────────────────
    # Deliberately separate from the sync. Matching a port to the game it is a
    # port OF is guesswork that gets things wrong, so what it decided has to be
    # inspectable and correctable afterwards - which a plain "scraped: yes" flag
    # would not allow.

    # Set when the pass has run, whether or not it found anything. That is what
    # makes the pass resumable: a run picks up the entries with no timestamp
    # rather than starting the whole catalogue again.
    meta_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # An admin's replacement for the search phrase. Some entries name a game no
    # database lists under that name, and a few name no real game at all. This
    # is the override, and it survives a re-sync because it is the one field
    # here the catalogue never writes.
    meta_search_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Which source answered, and what it thought this was. Recorded so a wrong
    # match is visible from the list - "Goemon 64 matched Doom 64" reads as an
    # error at a glance, where a filled-in description just looks like data.
    meta_source:        Mapped[str | None] = mapped_column(String(32), nullable=True)
    meta_matched_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "high" when the name matched on its own, "low" when the console had to
    # carry it. Low is not wrong, it is worth a second look.
    meta_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ── Scraped presentation ──────────────────────────────────────────────────
    # What the metadata pass found, held ON the entry - the GogGame equivalent.
    # The store and the entry detail read these so a listing looks like a game
    # before it is downloaded, and a download copies them onto the new game
    # instead of scraping again. cover_path is the real 3:4 cover; icon_path
    # above stays as the catalogue's square badge and the fallback.
    cover_path:   Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Hero (wide background) and transparent logo, so the storefront's hero
    # carousel and spotlight banner have art to show - without them the tile
    # block stretches to full width and the covers balloon.
    background_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_path:       Mapped[str | None] = mapped_column(String(512), nullable=True)
    description:  Mapped[str | None] = mapped_column(Text,        nullable=True)
    developer:    Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher:    Mapped[str | None] = mapped_column(String(255), nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32),  nullable=True)
    rating:       Mapped[float | None] = mapped_column(nullable=True)
    genres:       Mapped[list | None] = mapped_column(JSON,       nullable=True)
    # The rest of the GogGame-equivalent presentation, so the entry detail reads
    # as full as a GOG game before anything is downloaded (the house rule: all
    # scraped media is stored locally, so screenshots are local paths, not CDN).
    screenshots:  Mapped[list | None] = mapped_column(JSON,       nullable=True)
    # {rawg, igdb, steam(=metacritic 0-10)} plus any plugin scraper scores, the
    # same shape the GOG detail's capsule reads.
    meta_ratings: Mapped[dict | None] = mapped_column(JSON,       nullable=True)
    # {code: name} supported languages, rendered as flags like the GOG detail.
    languages:    Mapped[dict | None] = mapped_column(JSON,       nullable=True)
    # System requirements, in the {minimum, recommended} shape the theme reads.
    requirements: Mapped[dict | None] = mapped_column(JSON,       nullable=True)
    # HowLongToBeat times in seconds, for the "Time to beat" row.
    hltb_main_s:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_complete_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
