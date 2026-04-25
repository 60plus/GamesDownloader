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


class LifecycleSpec:
    """Hooks for lifecycle events."""

    @hookspec
    def lifecycle_on_game_added(self, game: dict[str, Any]) -> None:
        """Called when a new game is added to the library."""

    @hookspec
    def lifecycle_on_download_complete(self, game: dict[str, Any], path: str) -> None:
        """Called when a download finishes."""

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
