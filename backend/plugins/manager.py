"""Plugin manager - discovers, loads, and manages plugins.

Plugins are loaded from:
  1. Built-in plugins (in plugins/builtin/)
  2. External plugins in PLUGINS_PATH directory
  3. Installed pip packages with entry point group "gd3"
"""

from __future__ import annotations

# The submodule, explicitly. `import importlib` does not bring `importlib.util`
# with it, and every plugin here is loaded through
# `importlib.util.spec_from_file_location`. It has worked so far only because
# something else in the import graph happens to pull that submodule in first.
# The day it stops doing so, each plugin fails at load, the failure is caught
# per plugin and logged, and the application comes up looking healthy with no
# plugins at all.
import importlib.util
import json
import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import pluggy

from config import PLUGINS_PATH
from plugins.hookspecs import (
    PROJECT_NAME,
    DownloadProviderSpec,
    FirmwareSourceSpec,
    FrontendProviderSpec,
    LibraryCatalogSpec,
    LibrarySourceSpec,
    LifecycleSpec,
    MetadataProviderSpec,
    RomSourceSpec,
    WidgetSpec,
)

from plugins.config_crypto import decrypt_secrets

# Re-exported so a plugin finds its settings and its data directory in the same
# place: `from plugins.manager import get_plugin_config, plugin_data_dir`.
from plugins.storage import plugin_data_dir  # noqa: F401

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self) -> None:
        self._pm = pluggy.PluginManager(PROJECT_NAME)
        self._pm.add_hookspecs(MetadataProviderSpec)
        self._pm.add_hookspecs(DownloadProviderSpec)
        self._pm.add_hookspecs(LibrarySourceSpec)
        self._pm.add_hookspecs(LibraryCatalogSpec)
        self._pm.add_hookspecs(RomSourceSpec)
        self._pm.add_hookspecs(LifecycleSpec)
        self._pm.add_hookspecs(FrontendProviderSpec)
        self._pm.add_hookspecs(WidgetSpec)
        self._pm.add_hookspecs(FirmwareSourceSpec)

        # Mapping of plugin_id -> plugin instance for targeted load/unload
        self._instances: dict[str, Any] = {}

    def discover_and_load(self) -> None:
        """Load all plugins from configured sources."""
        self._load_builtin()
        self._load_external()
        self._load_setuptools()
        logger.info("Loaded %d plugins", len(self.list_plugins()))

    def _load_builtin(self) -> None:
        """Load built-in plugins from plugins/builtin/."""
        builtin_dir = Path(__file__).parent / "builtin"
        if not builtin_dir.exists():
            return
        for path in builtin_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"gd3_builtin_{path.stem}", str(path)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "Plugin"):
                    self._pm.register(module.Plugin())
                    logger.info("Loaded built-in plugin: %s", path.stem)
            except Exception:
                logger.exception("Failed to load built-in plugin: %s", path.stem)

    def _load_external(self) -> None:
        """Load plugins from PLUGINS_PATH, respecting plugin.json manifests."""
        plugins_dir = Path(PLUGINS_PATH)
        if not plugins_dir.exists():
            return
        if str(plugins_dir) not in sys.path:
            sys.path.append(str(plugins_dir))  # append, not insert - don't shadow stdlib

        for plugin_dir in sorted(plugins_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue

            plugin_id = plugin_dir.name

            # Read manifest if available
            manifest = self._read_manifest(plugin_dir)

            # Determine the entry file (validate against path traversal)
            if manifest:
                entry = manifest.get("entry", "plugin.py")
            else:
                entry = "plugin.py"

            # Block path traversal in entry field
            if ".." in entry or "/" in entry or "\\" in entry:
                logger.warning("Plugin '%s' has unsafe entry path: %s - skipping", plugin_id, entry)
                continue

            entry_path = plugin_dir / entry
            if not entry_path.exists():
                continue

            # Ensure resolved path is inside plugin dir
            try:
                entry_path.resolve().relative_to(plugin_dir.resolve())
            except ValueError:
                logger.warning("Plugin '%s' entry resolves outside plugin dir - skipping", plugin_id)
                continue

            # Check if plugin is disabled (DB state loaded at startup)
            if plugin_id in self._disabled_ids:
                logger.info("Skipping disabled plugin: %s", plugin_id)
                continue

            # Add vendor path to sys.path if it exists
            vendor_dir = plugin_dir / "vendor"
            if vendor_dir.is_dir() and str(vendor_dir) not in sys.path:
                sys.path.append(str(vendor_dir))

            try:
                mod_name = f"gd3_ext_{plugin_id}"
                spec = importlib.util.spec_from_file_location(
                    mod_name, str(entry_path)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "Plugin"):
                    instance = module.Plugin()
                    self._pm.register(instance)
                    self._instances[plugin_id] = instance
                    logger.info("Loaded external plugin: %s", plugin_id)
            except Exception:
                logger.exception("Failed to load plugin: %s", plugin_id)

    def _load_setuptools(self) -> None:
        """Disabled - setuptools entry points are a supply chain risk.
        Plugins must be installed via ZIP upload, not pip packages."""
        # self._pm.load_setuptools_entrypoints(PROJECT_NAME)
        pass

    @staticmethod
    def _read_manifest(plugin_dir: Path) -> dict | None:
        """Read plugin.json from a plugin directory. Return None if missing/invalid."""
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    @property
    def _disabled_ids(self) -> set[str]:
        """Return set of plugin IDs that are disabled in the DB.

        Uses a synchronous query via the sync engine so it can be called
        during startup before any async event loop is guaranteed.
        Falls back to an empty set if the table doesn't exist yet.
        """
        if not hasattr(self, "_disabled_cache"):
            self._disabled_cache: set[str] = set()
            try:
                from config import SYNC_DATABASE_URL
                from sqlalchemy import create_engine, text

                engine = create_engine(SYNC_DATABASE_URL)
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT plugin_id FROM plugin_configs "
                            "WHERE enabled = 0"
                        )
                    ).fetchall()
                    self._disabled_cache = {r[0] for r in rows}
                engine.dispose()
            except Exception:
                # Table may not exist yet on first run
                pass
        return self._disabled_cache

    def _invalidate_disabled_cache(self) -> None:
        """Clear the disabled-IDs cache so next access re-queries the DB."""
        if hasattr(self, "_disabled_cache"):
            del self._disabled_cache

    # ── Dynamic load/unload ──────────────────────────────────────────────────

    def load_single(self, plugin_id: str) -> None:
        """Load a single plugin by ID at runtime.

        Skips if already loaded. Adds vendor path to sys.path if present.
        """
        if plugin_id in self._instances:
            logger.info("Plugin '%s' already loaded, skipping", plugin_id)
            return

        plugin_dir = Path(PLUGINS_PATH) / plugin_id
        if not plugin_dir.is_dir():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        manifest = self._read_manifest(plugin_dir)
        entry = "plugin.py"
        if manifest:
            entry = manifest.get("entry", "plugin.py")

        entry_path = plugin_dir / entry
        if not entry_path.exists():
            raise FileNotFoundError(f"Plugin entry file not found: {entry_path}")

        # Add vendor path
        vendor_dir = plugin_dir / "vendor"
        if vendor_dir.is_dir() and str(vendor_dir) not in sys.path:
            sys.path.append(str(vendor_dir))

        # Add plugins dir to path
        plugins_dir_str = str(Path(PLUGINS_PATH))
        if plugins_dir_str not in sys.path:
            sys.path.append(plugins_dir_str)

        mod_name = f"gd3_ext_{plugin_id}"
        # Remove old module from sys.modules to allow reload
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        spec = importlib.util.spec_from_file_location(mod_name, str(entry_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "Plugin"):
            raise AttributeError(
                f"Plugin module '{plugin_id}' does not export a 'Plugin' class"
            )

        instance = module.Plugin()
        self._pm.register(instance)
        self._instances[plugin_id] = instance
        self._invalidate_disabled_cache()
        logger.info("Dynamically loaded plugin: %s", plugin_id)

    def unload_single(self, plugin_id: str) -> None:
        """Unload a single plugin by ID at runtime."""
        instance = self._instances.pop(plugin_id, None)
        if instance is None:
            logger.info("Plugin '%s' not loaded, nothing to unload", plugin_id)
            return
        try:
            self._pm.unregister(instance)
        except Exception:
            logger.exception("Error unregistering plugin '%s'", plugin_id)
        self._invalidate_disabled_cache()
        logger.info("Unloaded plugin: %s", plugin_id)

    # ── Query methods ────────────────────────────────────────────────────────

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return list of loaded plugin info dicts."""
        plugins = []
        for plugin in self._pm.get_plugins():
            name = getattr(plugin, "__class__", type(plugin)).__name__
            plugins.append({
                "name": name,
                "module": type(plugin).__module__,
            })
        return plugins

    def get_metadata_providers(self) -> list[str]:
        """Return IDs of all loaded metadata providers."""
        results = self._pm.hook.metadata_provider_id()
        return [r for r in results if r]

    def get_plugin_instances(self) -> list[Any]:
        """Return the registered plugin instances - lets callers probe
        per-plugin optional hooks (a global hook call loses the pairing
        between plugins and their results)."""
        return list(self._pm.get_plugins())

    def get_instance(self, plugin_id: str) -> Any | None:
        """The loaded instance for a plugin id, or None if it is not loaded."""
        return self._instances.get(plugin_id)

    def id_for_instance(self, inst: Any) -> str | None:
        """The plugin id a loaded instance was registered under, or None.

        The reverse of get_instance, used when a store is created so it can
        record which plugin owns it without the plugin having to name itself.
        """
        for pid, other in self._instances.items():
            if other is inst:
                return pid
        return None

    def manifest_for(self, plugin_id: str) -> dict[str, Any] | None:
        """The on-disk plugin.json of an installed plugin, or None.

        Lets a feature that only holds a plugin id present the plugin the way
        the user knows it (its manifest name and logo) instead of echoing the
        raw id back into the UI.
        """
        if not plugin_id or "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
            return None
        return self._read_manifest(Path(PLUGINS_PATH) / plugin_id)

    def installed_external_ids(self) -> set[str]:
        """Ids of external plugins present on disk - installed, loaded or not.

        A disabled plugin is still installed (its directory stays); an
        uninstalled one is gone. The catalogue-store reconciler removes a store
        exactly when its owning plugin is not in this set. Empty when the plugin
        directory is missing or empty, which the reconciler reads as "the plugin
        volume is unavailable" (an unmounted bind-mount, a DB restored before the
        plugin files were copied) and stands down rather than treat every
        catalogue as uninstalled.
        """
        plugins_dir = Path(PLUGINS_PATH)
        if not plugins_dir.exists():
            return set()
        return {
            d.name for d in plugins_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        }

    def all_external_plugins_loaded(self) -> bool:
        """True only when at least one external plugin is on disk and every one
        of them is loaded. False for a missing/empty directory or any
        disabled/failed plugin. The reconciler leans on this only for the legacy
        path (stores that predate the plugin_id column): a plugin_id-tagged store
        is judged by whether its owner is installed, which needs no load check.
        """
        installed = self.installed_external_ids()
        if not installed:
            return False
        return all(pid in self._instances for pid in installed)

    def get_download_providers(self) -> list[str]:
        """Return IDs of all loaded download providers."""
        results = self._pm.hook.download_provider_id()
        return [r for r in results if r]

    @property
    def hook(self):
        """Direct access to the pluggy hook caller."""
        return self._pm.hook

    def register(self, plugin: Any) -> None:
        """Manually register a plugin instance."""
        self._pm.register(plugin)

    def unregister(self, plugin: Any) -> None:
        """Unregister a plugin instance."""
        self._pm.unregister(plugin)


# Singleton instance
plugin_manager = PluginManager()


@lru_cache(maxsize=1)
def _sync_engine():
    """The one synchronous engine the plugin helpers share.

    `get_plugin_config` used to build an engine per call, which meant a TCP
    connect, an authentication handshake and a full MySQL dialect
    initialisation for a single SELECT - and RomDownloader asks three or more
    times per listing page. The `dispose()` at the end was also unreachable
    whenever a config was found, because the `return` sat inside the `with`.

    Small pool on purpose: it lives alongside the async pool (20 + 10) and the
    two together have to stay well under the server's connection limit.
    `pool_recycle` matters more than usual now that connections are kept rather
    than torn down after every call - an idle one must not outlive MySQL's
    wait_timeout. Building the engine never connects, so caching the object is
    safe even if the database is down at the time.
    """
    from sqlalchemy import create_engine

    from config import SYNC_DATABASE_URL

    return create_engine(
        SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=2,
        max_overflow=3,
    )


def get_plugin_config(plugin_id: str) -> dict:
    """Read plugin config from DB (synchronous helper for plugins).

    Returns the parsed config dict, or empty dict if not found.
    Plugins call this to read their own settings:
        from plugins.manager import get_plugin_config
        cfg = get_plugin_config("my-plugin")
        api_key = cfg.get("api_key", "")
    """
    import json as _json
    try:
        from sqlalchemy import text
        with _sync_engine().connect() as conn:
            row = conn.execute(
                text("SELECT config_json FROM plugin_configs WHERE plugin_id = :pid"),
                {"pid": plugin_id},
            ).fetchone()
        # Parsing happens after the connection is back in the pool. The
        # credentials among these are stored encrypted; the plugin gets them
        # the way it always did, in the clear, and never learns the difference.
        if row and row[0]:
            return decrypt_secrets(_json.loads(row[0]))
    except Exception:
        pass
    return {}
