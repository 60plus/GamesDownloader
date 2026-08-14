"""Plugin hook specifications - defines the contract plugins must implement.

Each hookspec is a method signature that plugins can implement.
The plugin manager calls these hooks and collects results.

IMPORTANT: All hook names must be globally unique within the pluggy namespace.
Use prefixes (metadata_, download_, library_, lifecycle_) to avoid collisions.
"""

from __future__ import annotations

from typing import Any

import pluggy

PROJECT_NAME = "gd3"
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class MetadataProviderSpec:
    """Hooks for metadata provider plugins (IGDB, MobyGames, etc.)."""

    @hookspec
    def metadata_provider_name(self) -> str:
        """Return the display name of this metadata provider."""

    @hookspec
    def metadata_provider_id(self) -> str:
        """Return a unique identifier for this provider (e.g. 'igdb')."""

    @hookspec
    def metadata_provider_ratings(self) -> bool:
        """Whether this provider returns numeric 0-10 game ratings (rendered
        and edited as scores under its meta_ratings key). Badge-style
        providers (tiers, statuses) return False. Providers without this
        hook are assumed to return ratings."""

    @hookspec
    def metadata_search_game(self, query: str) -> list[dict[str, Any]]:
        """Search for games by title. Return list of match dicts."""

    @hookspec
    def metadata_get_game(self, provider_game_id: str) -> dict[str, Any] | None:
        """Fetch full metadata for a game by provider-specific ID."""

    @hookspec
    def metadata_get_cover_url(self, provider_game_id: str) -> str | None:
        """Return cover image URL for a game."""

    @hookspec
    def metadata_get_covers(self, query: str) -> list[dict[str, Any]]:
        """Search for cover images by game title.

        Return list of dicts: {url, thumb, type, label, author?}
        - url: full-size image URL
        - thumb: thumbnail URL (can be same as url)
        - type: "static" or "animated"
        - label: display label (e.g. "Game Title - Box Art")
        - author: optional credit string
        """

    @hookspec
    def metadata_get_heroes(self, query: str) -> list[dict[str, Any]]:
        """Search for hero/background/fanart images by game title.

        Same return format as metadata_get_covers.
        """

    @hookspec
    def metadata_get_logos(self, query: str) -> list[dict[str, Any]]:
        """Search for logo/clearlogo images by game title.

        Same return format as metadata_get_covers.
        """

    @hookspec
    def metadata_search_collection(self, query: str) -> list[dict[str, Any]]:
        """Search for collections / franchises / series by name.

        Return list of candidate dicts:
        {provider_id, provider_collection_id, name, snippet?, cover_url?,
         start_year?, end_year?}
        A collection is a grouping of related games (e.g. a franchise). The
        artwork hooks (metadata_get_covers / _heroes / _logos) are reused for
        collection artwork, keyed by the collection name.
        """

    @hookspec
    def metadata_get_collection(self, provider_collection_id: str) -> dict[str, Any] | None:
        """Fetch full metadata for a collection by provider-specific ID.

        Return dict: {provider_id, name, description?, description_short?,
        cover_url?, hero_url?, logo_url?, start_year?, end_year?, rating?,
        source_url?}. `rating` is on a 0-5 scale.
        """


class DownloadProviderSpec:
    """Hooks for download provider plugins (GOG, torrent, etc.)."""

    @hookspec
    def download_provider_name(self) -> str:
        """Return the display name of this download provider."""

    @hookspec
    def download_provider_id(self) -> str:
        """Return a unique identifier (e.g. 'gog', 'torrent')."""

    @hookspec
    def download_can_handle(self, game_id: str) -> bool:
        """Check if this provider can handle downloading the given game."""

    @hookspec
    def download_start(self, game_id: str, destination: str) -> dict[str, Any]:
        """Start a download. Return status dict with at least 'task_id'."""

    @hookspec
    def download_get_status(self, task_id: str) -> dict[str, Any]:
        """Get download progress. Return dict with 'progress', 'status', etc."""


class LibrarySourceSpec:
    """Hooks for library source plugins (local folder, NAS, cloud)."""

    @hookspec
    def library_source_name(self) -> str:
        """Return the display name of this library source."""

    @hookspec
    def library_source_id(self) -> str:
        """Return a unique identifier."""

    @hookspec
    def library_scan(self, path: str) -> list[dict[str, Any]]:
        """Scan a path and return list of discovered games/ROMs."""


class LibraryCatalogSpec:
    """Hooks for catalogue plugins: a listing of games the server COULD hold.

    A library source scans a path for files that are already here. A catalogue
    is the opposite - it describes what is available elsewhere, so the library
    it feeds is a storefront (see the `is_store` flag on a library) rather than
    a shelf. GOG is the built-in example; a plugin can add others.

    The plugin only describes; it never writes. Core owns the upsert, downloads
    the artwork through the SSRF guard and stores it locally, and decides
    membership - so a catalogue cannot smuggle a hot-linked CDN image into the
    UI or a row past the guards.

    ``library_catalog_fetch`` is called in a worker thread, so blocking HTTP is
    fine and expected. Fetch failures should be reported per entry rather than
    raised: one dead repository must not cost the other seventy-six.
    """

    @hookspec
    def library_catalog_name(self) -> str:
        """Display name of this catalogue (e.g. 'GitHub PC Ports')."""

    @hookspec
    def library_catalog_id(self) -> str:
        """Stable identifier, used as the catalogue key in the database."""

    @hookspec
    def library_catalog_library(self) -> dict[str, Any]:
        """Optional: the store library this catalogue lives in, so an admin does
        not hand-make it (and cannot: a store is a plugin's to create, never a
        user's). Core upserts a library from what is returned and marks it a
        store fed by this catalogue. Any key may be omitted:

            slug           str - stable route slug (default: from the id)
            name           str - display name (default: the catalogue name)
            icon           str - icon path or URL
            color          str - accent colour
            storage_folder str - folder under data/games for downloaded builds
                                 (default: the name). Downloaded games show in
                                 the Games library; only their files live here.

        Return nothing to let core pick every default from the id and name.
        """

    @hookspec
    def library_catalog_fetch(self) -> list[dict[str, Any]]:
        """Return the whole catalogue. One dict per entry:

            external_id  str   - stable identity inside this catalogue, and the
                                 key an entry is matched on across syncs. Use
                                 something that survives a rename (a repository
                                 path, not a title).
            title        str   - display name. For a catalogue of ports this is
                                 the game, not the project: people look for
                                 "Mario Kart 64", not "SpaghettiKart".
            subtitle     str   - optional qualifier shown under the title. What
                                 tells two builds of one game apart, so it is
                                 worth setting whenever a catalogue can offer
                                 more than one of something.
            catalog_title str  - optional: the name before any parsing. Kept as
                                 a fallback for metadata lookups.
            category     str   - optional grouping; core stores it as a tag.
            icon_url     str   - optional artwork URL. Core downloads it.
            description  str   - optional summary.
            homepage     str   - optional link shown on the detail page.
            available    bool  - False when the entry cannot be offered right
                                 now (repository gone, no usable release).
            unavailable_reason str - why, shown to the admin. Required when
                                 available is False, or the entry is silently
                                 wrong instead of visibly broken.
            release      dict  - optional, and omitted when nothing is
                                 downloadable yet:
                                   tag           str
                                   published_at  ISO-8601 str
                                   prerelease    bool
                                   assets        list of dicts:
                                       name, size (int bytes), url,
                                       os   ('windows'|'mac'|'linux'|'all'),
                                       arch (optional, free-form),
                                       digest (optional checksum)

        An entry missing external_id or title is skipped and logged, not
        guessed at.
        """


class RomSourceSpec:
    """Hooks for ROM source plugins: a live, browsable listing of ROMs a
    remote source offers for download into roms/<platform>/.

    Unlike a library catalogue (pre-synced into a storefront), a ROM source is
    browsed live and lazily: there can be tens of thousands of ROMs behind a
    source, so nothing is pre-fetched into the database. The plugin lists on
    demand (paginated) and resolves a single-file download when the user picks
    an entry; core owns the download (through the SSRF and size guards), the
    write into roms/<fs_slug>/, and the scan + scrape that follow. Downloaded
    ROMs are ordinary Rom rows - a source never owns a persistent shelf.

    The listing and resolve hooks may block on HTTP; they are called in a worker
    thread. Any credential a source needs is the plugin's own concern: it reads
    its stored config (declared as a `config_schema` in plugin.json, with
    `password`-type fields for secrets) and returns ready-to-use request headers
    from rom_source_resolve_download, so secrets never leave the backend.
    """

    @hookspec
    def rom_source_id(self) -> str:
        """Stable identifier for this source (e.g. 'archive-hearto')."""

    @hookspec
    def rom_source_name(self) -> str:
        """Display name of this source (e.g. 'Internet Archive - 1G1R')."""

    @hookspec
    def rom_source_meta(self) -> dict[str, Any]:
        """Optional presentation and state. Any key may be omitted:

            tile_asset    str  - plugin assets/ path for the source tile art,
                                 served via /api/plugins/{id}/assets/{path}.
            icon_asset    str  - plugin assets/ path for a small icon shown next
                                 to the source. Defaults to the plugin's own
                                 logo.png/logo.svg when omitted; a theme heads
                                 the source with it instead of a generic glyph.
            requires_auth bool - whether the source needs configured credentials
                                 before it can list or download.
            configured    bool - whether the plugin currently has what it needs
                                 (e.g. credentials present). When False and
                                 requires_auth is True, core shows the source as
                                 "configure to enable" and refuses listing.
        """

    @hookspec
    def rom_source_platforms(self) -> list[dict[str, Any]]:
        """Platforms this source offers. One dict per platform:

            fs_slug  str - GD canonical platform folder slug. Must exist in
                          PLATFORM_MAP; an unmapped slug is dropped and logged by
                          core, never guessed into a random folder. The plugin
                          owns the mapping from the source's own platform naming
                          to this slug.
            display  str - optional label override (default: the PLATFORM_MAP
                          name).
            count    int - optional number of ROMs available, if known cheaply.
        """

    @hookspec
    def rom_source_list(
        self,
        fs_slug: str,
        page: int,
        page_size: int,
        query: str | None,
        region: str | None,
        sort: str | None,
        collection: str | None,
        fmt: str | None,
        kind: str | None,
    ) -> dict[str, Any]:
        """Live, paginated listing of ROMs for one platform. Return:

            items  list of dicts, one per ROM:
                id        str - stable entry id within this source, passed back
                               to rom_source_resolve_download.
                title     str - display title. Core strips the region tag for
                               display and shows region as a badge.
                filename  str - the canonical on-disk filename (No-Intro name,
                               extension included) the ROM will be saved as.
                region    str - optional region code (USA/Europe/Japan/World..).
                size      int - optional size in bytes.
                crc       str - optional CRC32 hash (No-Intro DAT).
                md5       str - optional MD5 hash.
                sha1      str - optional SHA1 hash.
                collection str - optional label of the catalogue this entry came
                               from. A source that merges several catalogues (the
                               same platform offered by more than one upstream
                               set) stamps each entry so the user can tell them
                               apart and filter.
                format    str - optional container the ROM arrives in (chd, zip,
                               iso, ...). Core derives it from the filename when
                               omitted, so a source only sets it when the
                               extension would lie.
                kind      str - optional sort of release: retail, prototype,
                               demo, beta, sample, unlicensed, bootleg, hack,
                               translation, aftermarket, homebrew, bios. Only the
                               source can tell, since it lives in the naming
                               convention of the set it came from.
            total  int - total entries matching query (for pagination).
            collections  list[str] - optional, every collection label available
                               for this platform, whatever page is being asked
                               for. Core passes it to the theme as the filter's
                               options; omit it for a single-catalogue source.
            formats  list[str] - optional, same idea for the format filter.
            kinds  list[str] - optional, same idea for the release-type filter.

        `collection`, `fmt` and `kind`, when set, are filters: return only
        entries from that catalogue / in that container / of that release type.
        All are passed by keyword and only to a plugin that declares them, so an
        older signature keeps working.
        Hashes, when present, let core mark an entry already owned before any
        download. Called in a worker thread; blocking HTTP is fine.
        """

    @hookspec
    def rom_source_resolve_download(self, entry_id: str) -> dict[str, Any]:
        """Resolve one entry to a concrete, authenticated single-file download:

            url       str - direct URL to the one ROM file (never a whole
                           multi-GB archive).
            filename  str - canonical on-disk filename (extension included).
            fs_slug   str - target platform slug (validated against PLATFORM_MAP).
            headers   dict[str, str] - optional request headers carrying the
                           source's auth (e.g. Authorization). Core attaches them
                           to the guarded download and never logs them.
            cookies   dict[str, str] - optional cookies carrying the source's
                           auth. Prefer this over a Cookie header: core puts them
                           in the request's cookie jar, which - unlike a Cookie
                           header - survives the redirect archive.org uses to hand
                           a download to a datanode. A Cookie header is accepted
                           and folded into the jar for convenience.

        Called in a worker thread; may perform blocking HTTP (e.g. to mint a
        short-lived member URL).
        """


class LifecycleSpec:
    """Hooks for lifecycle events."""

    @hookspec
    def lifecycle_on_game_added(self, game: dict[str, Any]) -> None:
        """Called when a new game is added to the library."""

    @hookspec
    def lifecycle_on_download_complete(self, game: dict[str, Any], path: str) -> None:
        """Called when a download finishes."""

    @hookspec
    def lifecycle_on_play_start(self, game: dict[str, Any]) -> None:
        """Called when a user launches a game or ROM (the in-browser player
        opens). `game` carries at least id/title/source."""

    @hookspec
    def lifecycle_on_play_end(self, game: dict[str, Any], seconds: int) -> None:
        """Called when a play session ends. `seconds` is the elapsed play time."""

    @hookspec
    def lifecycle_on_startup(self) -> None:
        """Called when the application starts."""

    @hookspec
    def lifecycle_on_shutdown(self) -> None:
        """Called when the application shuts down."""


class FrontendProviderSpec:
    """Hooks for frontend/theme plugins that inject CSS, routes, or themes."""

    @hookspec
    def frontend_get_theme(self) -> dict[str, Any] | None:
        """Return theme definition dict (colors, fonts, etc.)."""

    @hookspec
    def frontend_get_css(self) -> str | None:
        """Return CSS string to inject into the frontend."""

    @hookspec
    def frontend_get_js(self) -> str | None:
        """Return JavaScript string to execute in the frontend on load."""

    @hookspec
    def frontend_get_routes(self) -> list[dict[str, Any]] | None:
        """Return custom route definitions [{path, label, icon}]."""


class WidgetSpec:
    """Hooks for dashboard widget plugins."""

    @hookspec
    def widget_get_cards(self) -> list[dict[str, Any]] | None:
        """Return widget card definitions for the dashboard."""
