"""Where a plugin keeps data that has to outlive its own code.

Installing a plugin replaces its directory wholesale - the old one is removed
and the archive is copied in its place. Anything the plugin wrote next to its
code goes with it, so a plugin that caches its work loses that cache every time
it is updated. RomDownloader kept a listing cache there and rebuilt tens of
megabytes of archive.org listings after every update, which is the same thing
as losing the data.

So data lives here instead, in its own directory per plugin, outside the tree
the installer replaces. Plugins reach it through `plugin_data_dir`:

    from plugins.manager import plugin_data_dir
    cache = plugin_data_dir("my-plugin") / "listings"

The directory survives updates, disabling and re-enabling. It is removed only
when the plugin itself is uninstalled.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import PLUGIN_DATA_PATH

logger = logging.getLogger(__name__)

# Never carried across an update.
#
# Bytecode and tool caches are rebuilt on their own, and moving them would park
# stale copies in the data directory for good.
#
# `vendor` is there for a sharper reason. It is not the plugin's; the installer
# builds it with `pip install --target` whenever the incoming archive ships a
# requirements.txt. A version that drops its requirements no longer has one in
# the incoming tree, so without this line the whole site-packages tree - often
# hundreds of megabytes of third-party code - would be filed away as "data" and
# kept forever, in a directory nothing lists and only uninstalling clears.
_NOT_WORTH_CARRYING = {
    "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache", ".git", "vendor",
}

#: Suffix for the half-moved copy, so a move that dies partway cannot be
#: mistaken for the finished article on the next update.
_STAGED = ".gd-incoming"


def valid_plugin_id(plugin_id: str) -> bool:
    """Whether this is a name we are willing to turn into a directory.

    One rule, one place. Every site that builds a path from a plugin id used to
    carry its own copy of it, and they disagreed: the copies rejected `/`, `\\`
    and `..` but not a leading dot, which stopped being harmless the moment
    this module put a dot directory in the plugin volume. `DELETE` with an id
    of `.` resolves to the volume itself, and `.data` to the shared data root.
    """
    if not plugin_id or plugin_id.startswith("."):
        return False
    return "/" not in plugin_id and "\\" not in plugin_id and ".." not in plugin_id


def _checked_id(plugin_id: str) -> str:
    """`valid_plugin_id`, for callers that would rather not check."""
    if not valid_plugin_id(plugin_id):
        raise ValueError(f"Invalid plugin id: {plugin_id!r}")
    return plugin_id


def plugin_data_dir(plugin_id: str) -> Path:
    """This plugin's own directory for runtime data, created on first use."""
    path = Path(PLUGIN_DATA_PATH) / _checked_id(plugin_id)
    _warn_if_ephemeral(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _warn_if_ephemeral(path: Path) -> None:
    """Say so, once, if this directory will not survive the next image.

    The default sits inside the plugin volume precisely so it does survive, but
    both the plugin path and this one can be pointed elsewhere by environment
    variable, and a path with no mount behind it lives in the container's
    writable layer and disappears on the next `up -d`. Saves and firmware each
    learned that the hard way; the check they added exists to be reused.
    """
    if getattr(_warn_if_ephemeral, "_said", False):
        return
    try:
        from utils.volume_check import is_ephemeral
        if is_ephemeral(path):
            _warn_if_ephemeral._said = True  # type: ignore[attr-defined]
            logger.error(
                "Plugin data at %s is not on a mounted volume, so everything "
                "plugins store there is lost the next time the container is "
                "recreated. Add a volume for it, or point GD_PLUGIN_DATA_PATH "
                "at one.", path,
            )
    except Exception:
        pass


def purge_plugin_data(plugin_id: str) -> bool:
    """Delete everything the plugin stored. Returns False if it stored nothing.

    For uninstalling only. An update must never reach this: the whole point of
    the directory is that it is the one thing an update leaves alone.
    """
    path = Path(PLUGIN_DATA_PATH) / _checked_id(plugin_id)
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    logger.info("Removed stored data for plugin '%s'", plugin_id)
    return True


def carry_data_across_update(plugin_id: str, installed: Path, incoming: Path) -> list[str]:
    """Move a plugin's runtime files out of the way before its update wipes them.

    `installed` is the version on disk about to be replaced, `incoming` the
    extracted new one. Anything in `installed` that the new version does not
    ship is not code - the plugin wrote it while it ran - so it is moved into
    the plugin's data directory instead of being deleted with the rest.

    This is what makes the guarantee hold for plugins that never asked for it,
    including ones written before there was anywhere else to put their data.
    A plugin that has already moved to `plugin_data_dir` carries nothing,
    because its data is not in the plugin directory to begin with.

    Two things it has to get right, and got wrong at first:

    * **The comparison goes all the way down.** A plugin that keeps its cache
      inside a directory the archive also ships - `assets/`, or a `cache/` with
      one seeded file in it - would otherwise have that whole directory
      classified as code and deleted with the old version.
    * **A name already in the data directory does not mean the copy beside the
      code is stale.** It usually means the opposite: the plugin has not moved
      over, it rebuilt its cache after the last update, and what sits beside
      the code is the live copy. So the newer one wins, and it is staged before
      the older is removed, rather than deleted first and moved second.

    Returns the paths carried, relative to the plugin directory, for the log.
    """
    if not installed.is_dir():
        return []

    destination = Path(PLUGIN_DATA_PATH) / _checked_id(plugin_id)
    carried: list[str] = []
    _carry_tree(installed, incoming, destination, "", carried)

    if carried:
        _warn_if_ephemeral(destination)
        logger.info(
            "Plugin '%s': kept %d item(s) across the update (moved to %s): %s",
            plugin_id, len(carried), destination,
            ", ".join(carried[:10]) + (", ..." if len(carried) > 10 else ""),
        )
    return carried


def _carry_tree(
    installed: Path, incoming: Path, destination: Path, prefix: str, carried: list[str]
) -> None:
    """One directory level of the comparison, recursing where both sides agree."""
    try:
        entries = sorted(installed.iterdir())
    except OSError as exc:
        logger.warning("Could not read %s while carrying plugin data: %s", installed, exc)
        return

    for entry in entries:
        if entry.name in _NOT_WORTH_CARRYING:
            continue
        counterpart = incoming / entry.name
        relative = f"{prefix}{entry.name}"

        # Both sides have a directory of this name: the archive ships some of
        # what is in here, and the plugin may have written the rest. Look
        # inside rather than judging the whole subtree by its name.
        if entry.is_dir() and not entry.is_symlink() and counterpart.is_dir():
            _carry_tree(entry, counterpart, destination / entry.name, relative + "/", carried)
            continue

        if counterpart.exists():
            continue  # the new version ships this - it is code, not data

        _move_aside(entry, destination / entry.name, relative, carried)


def _move_aside(entry: Path, target: Path, relative: str, carried: list[str]) -> None:
    """Move one entry into the data directory, newest copy winning.

    Staged first, then swapped. A move that fails halfway leaves a `.gd-incoming`
    name that the next update overwrites, rather than a truncated tree sitting
    where the good copy used to be and blocking every future carry.
    """
    staged = target.with_name(target.name + _STAGED)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _remove(staged)
        shutil.move(str(entry), str(staged))
        _remove(target)
        staged.rename(target)
        carried.append(relative)
    except OSError as exc:
        # Better to lose one file than to abandon the update half done.
        logger.warning(
            "Could not carry '%s' across the update: %s", relative, exc
        )


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)
