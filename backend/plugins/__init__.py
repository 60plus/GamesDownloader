"""GamesDownloaderV3 plugin system - built on pluggy.

Plugins can:
  - Add new metadata providers (IGDB, MobyGames, custom)
  - Add new download providers (GOG, Steam, torrent, custom)
  - Add new library sources (local folders, cloud storage)
  - Hook into lifecycle events (game added, download complete, etc.)

Plugins are Python packages placed in PLUGINS_PATH or installed as pip packages
with the entry point group "gd3".

Example plugin:
    # my_plugin.py
    import gd3_hookspecs as hookspecs

    class MyMetadataProvider:
        @hookspecs.hookimpl
        def get_metadata(self, title: str) -> dict:
            return {"title": title, "source": "my_provider"}
"""
