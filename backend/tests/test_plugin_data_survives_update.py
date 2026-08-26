"""Updating a plugin must not destroy what the plugin wrote while it ran.

The installer replaces a plugin's directory wholesale, which is right for code
and fatal for data. RomDownloader kept tens of megabytes of archive.org
listings beside its code and rebuilt every one of them after every update.

These tests build real ZIP archives and run the real installer against a real
temporary filesystem. Nothing is mocked, because the thing under test is what
ends up on disk.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from handler.plugins import install_handler
from plugins import storage


def _zip_plugin(tmp_path: Path, version: str, files: dict[str, str]) -> Path:
    """A plugin archive: plugin.json plus whatever files the version ships."""
    manifest = {
        "id": "gd3-test-plugin",
        "name": "Test Plugin",
        "version": version,
        "author": "tests",
        "type": "rom_source",
        "entry": "plugin.py",
    }
    zip_path = tmp_path / f"plugin-{version}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("plugin.json", json.dumps(manifest))
        for name, body in files.items():
            zf.writestr(name, body)
    return zip_path


@pytest.fixture
def plugin_world(tmp_path, monkeypatch):
    """A plugins directory and a data directory, laid out as in production."""
    plugins_dir = tmp_path / "plugins"
    data_dir = plugins_dir / ".data"
    monkeypatch.setattr(install_handler, "PLUGINS_PATH", str(plugins_dir))
    monkeypatch.setattr(storage, "PLUGIN_DATA_PATH", str(data_dir))
    return plugins_dir, data_dir


def _install(zip_path: Path) -> dict:
    return install_handler._install_plugin_from_zip_sync(zip_path)


# ── the defect this closes ───────────────────────────────────────────────────

def test_a_cache_written_beside_the_code_survives_the_update(plugin_world, tmp_path):
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    # The plugin runs and builds a cache next to itself, the way plugins
    # written before there was anywhere else to put it do.
    cache = plugins_dir / "gd3-test-plugin" / ".cache"
    cache.mkdir()
    (cache / "listing.json").write_text("expensive to fetch")

    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    carried = data_dir / "gd3-test-plugin" / ".cache" / "listing.json"
    assert carried.exists(), "the update destroyed the plugin's cache"
    assert carried.read_text() == "expensive to fetch"


def test_the_new_version_of_the_code_is_the_one_that_ends_up_installed(
    plugin_world, tmp_path
):
    plugins_dir, _ = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))
    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    body = (plugins_dir / "gd3-test-plugin" / "plugin.py").read_text()
    assert body == "VERSION = '1.1.0'"


def test_a_file_the_new_version_dropped_does_not_linger_beside_the_code(
    plugin_world, tmp_path
):
    """Replacing rather than merging is the point: a module the author deleted
    must not stay importable. It is moved aside, not left where it was."""
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {
        "plugin.py": "VERSION = '1.0.0'",
        "helpers.py": "def old(): ...",
    }))
    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    assert not (plugins_dir / "gd3-test-plugin" / "helpers.py").exists()
    assert (data_dir / "gd3-test-plugin" / "helpers.py").exists()


def test_a_file_the_new_version_still_ships_is_overwritten_not_carried(
    plugin_world, tmp_path
):
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))
    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    assert not (data_dir / "gd3-test-plugin" / "plugin.py").exists()
    assert (plugins_dir / "gd3-test-plugin" / "plugin.py").read_text() == "VERSION = '1.1.0'"


def test_bytecode_is_not_dragged_into_the_data_directory(plugin_world, tmp_path):
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    junk = plugins_dir / "gd3-test-plugin" / "__pycache__"
    junk.mkdir()
    (junk / "plugin.cpython-311.pyc").write_bytes(b"\x00")

    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    assert not (data_dir / "gd3-test-plugin" / "__pycache__").exists()


def test_a_first_install_carries_nothing(plugin_world, tmp_path):
    _, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))
    assert not data_dir.exists() or not any(data_dir.rglob("*"))


def test_the_copy_beside_the_code_is_the_newer_one_and_wins(plugin_world, tmp_path):
    """The first version of this assumed the opposite, and the assumption cost
    the whole guarantee.

    A plugin that has not moved over rebuilds its cache beside its code after
    every update. So a name that exists in both places means the plugin is
    still writing beside the code, and that copy is the live one - keeping the
    older copy and letting the newer be deleted brought the original data loss
    back on the second update and every update after it.
    """
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    carried_last_time = data_dir / "gd3-test-plugin" / "state.json"
    carried_last_time.parent.mkdir(parents=True)
    carried_last_time.write_text("from the previous update")
    (plugins_dir / "gd3-test-plugin" / "state.json").write_text("what the plugin just wrote")

    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    assert carried_last_time.read_text() == "what the plugin just wrote"


def test_a_plugin_that_never_migrates_keeps_its_data_across_many_updates(
    plugin_world, tmp_path
):
    """The scenario the whole mechanism exists for, run three times over."""
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    for round_number in range(1, 4):
        # The plugin runs and writes beside its code, as it always has.
        cache = plugins_dir / "gd3-test-plugin" / ".cache"
        cache.mkdir(exist_ok=True)
        (cache / "listing.json").write_text(f"round {round_number}")

        _install(_zip_plugin(tmp_path, f"1.{round_number}.0",
                             {"plugin.py": f"VERSION = '1.{round_number}.0'"}))

        carried = data_dir / "gd3-test-plugin" / ".cache" / "listing.json"
        assert carried.exists(), f"update {round_number} destroyed the cache"
        assert carried.read_text() == f"round {round_number}"


def test_data_inside_a_directory_the_archive_also_ships_survives(plugin_world, tmp_path):
    """The comparison goes all the way down, not just across the top.

    A theme that lets people drop artwork into its own `assets/`, or a plugin
    that seeds one file into `cache/` and fills the rest at runtime, would
    otherwise have the whole directory read as code and deleted."""
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {
        "plugin.py": "VERSION = '1.0.0'",
        "assets/shipped.css": "body{}",
    }))

    added = plugins_dir / "gd3-test-plugin" / "assets" / "downloaded"
    added.mkdir(parents=True)
    (added / "art.png").write_bytes(b"\x89PNG")

    _install(_zip_plugin(tmp_path, "1.1.0", {
        "plugin.py": "VERSION = '1.1.0'",
        "assets/shipped.css": "body{color:red}",
    }))

    assert (data_dir / "gd3-test-plugin" / "assets" / "downloaded" / "art.png").exists()
    # And the shipped file is the new one, not carried anywhere.
    assert (plugins_dir / "gd3-test-plugin" / "assets" / "shipped.css").read_text() == "body{color:red}"
    assert not (data_dir / "gd3-test-plugin" / "assets" / "shipped.css").exists()


def test_a_vendored_dependency_tree_is_never_carried(plugin_world, tmp_path):
    """`vendor/` is not the plugin's data - the installer builds it from the
    incoming requirements.txt. Filing hundreds of megabytes of site-packages
    away as "data" would keep them for good in a directory nothing lists."""
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    vendored = plugins_dir / "gd3-test-plugin" / "vendor" / "httpx"
    vendored.mkdir(parents=True)
    (vendored / "__init__.py").write_text("# a dependency")

    _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))

    assert not (data_dir / "gd3-test-plugin" / "vendor").exists()


def test_a_failed_install_leaves_the_working_plugin_alone(plugin_world, tmp_path, monkeypatch):
    """Built beside the old one and swapped in. The old order deleted first and
    copied second, so a copy that ran out of disk left no plugin at all."""
    import shutil as _shutil

    from handler.plugins import install_handler as handler

    plugins_dir, _ = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))

    real_copytree = _shutil.copytree
    monkeypatch.setattr(
        handler.shutil, "copytree",
        lambda *a, **k: (_ for _ in ()).throw(OSError("No space left on device")),
    )
    with pytest.raises(OSError):
        _install(_zip_plugin(tmp_path, "1.1.0", {"plugin.py": "VERSION = '1.1.0'"}))
    monkeypatch.setattr(handler.shutil, "copytree", real_copytree)

    installed = plugins_dir / "gd3-test-plugin" / "plugin.py"
    assert installed.exists(), "the failed update took the working plugin with it"
    assert installed.read_text() == "VERSION = '1.0.0'"
    assert not list(plugins_dir.glob(".*.installing"))


# ── the data directory itself ────────────────────────────────────────────────

def test_the_data_directory_is_outside_the_tree_the_installer_replaces(
    plugin_world,
):
    plugins_dir, data_dir = plugin_world
    made = storage.plugin_data_dir("gd3-test-plugin")
    assert made.is_dir()
    assert made.parent == data_dir
    # The installer removes PLUGINS_PATH/<id>, so that is the tree the data
    # must stay out of. The plugin volume around it is exactly where it lives.
    assert plugins_dir / "gd3-test-plugin" not in made.parents


def test_the_default_data_path_is_inside_a_volume_every_install_already_mounts():
    """The compose file mounts named subdirectories of /data, not /data itself.
    A new top-level directory would sit in the container's writable layer on
    every existing installation and be lost with the next image. A fix for data
    loss cannot depend on the operator editing their compose file first."""
    from pathlib import Path as _Path

    import config

    assert _Path(config.PLUGIN_DATA_PATH).parent == _Path(config.PLUGINS_PATH)
    assert _Path(config.PLUGIN_DATA_PATH).name.startswith(".")


@pytest.mark.asyncio
async def test_no_scan_of_the_plugin_volume_mistakes_the_data_directory_for_a_plugin(
    plugin_world, tmp_path, monkeypatch
):
    """It sits in the plugin volume, so every listing there has to skip it."""
    from endpoints.settings import plugins_router
    from plugins.manager import plugin_manager

    plugins_dir, data_dir = plugin_world
    monkeypatch.setattr(plugins_router, "PLUGINS_PATH", str(plugins_dir))
    monkeypatch.setattr("plugins.manager.PLUGINS_PATH", str(plugins_dir))

    _install(_zip_plugin(tmp_path, "1.0.0", {
        "plugin.py": "VERSION = '1.0.0'",
        "i18n.json": '{"en": {"k": "v"}}',
    }))
    # Data that looks exactly like a plugin, in the directory beside it.
    stored = storage.plugin_data_dir("gd3-test-plugin")
    (stored / "plugin.json").write_text(json.dumps({
        "id": "gd3-test-plugin", "name": "n", "version": "9", "author": "a",
        "type": "rom_source", "entry": "plugin.py",
    }))
    (stored / "i18n.json").write_text('{"en": {"stolen": "yes"}}')
    # And at the top of the data directory, which is what the i18n merge walks.
    (data_dir / "i18n.json").write_text('{"en": {"stolen": "yes"}}')

    listed = [m["id"] for m in install_handler.list_installed_plugins()]
    assert listed == ["gd3-test-plugin"]
    assert plugin_manager.installed_external_ids() == {"gd3-test-plugin"}
    merged = await plugins_router.get_plugin_i18n()
    assert "stolen" not in json.dumps(merged)
    assert merged["en"]["k"] == "v"   # the real plugin's file still read


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "", "..", ".data", ".x"])
def test_a_plugin_id_that_is_really_a_path_is_refused(plugin_world, bad):
    with pytest.raises(ValueError):
        storage.plugin_data_dir(bad)
    with pytest.raises(ValueError):
        storage.purge_plugin_data(bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", [".", ".data", "..", "a/b", "a\\b", ""])
async def test_uninstalling_refuses_an_id_that_is_not_a_plugin_name(
    plugin_world, tmp_path, bad_id
):
    """`.` resolves to the plugin volume itself and `.data` to every plugin's
    stored data, and the guard that would have caught them ran after the
    delete rather than before it."""
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))
    (storage.plugin_data_dir("gd3-test-plugin") / "cache.json").write_text("precious")

    assert await install_handler.uninstall_plugin(bad_id) is False

    assert (plugins_dir / "gd3-test-plugin" / "plugin.py").exists()
    assert (data_dir / "gd3-test-plugin" / "cache.json").read_text() == "precious"


def test_installing_refuses_an_id_that_is_not_a_plugin_name(plugin_world, tmp_path):
    """A ZIP claiming to be `.data` would take over the shared data directory."""
    for bad_id in (".data", ".", "..", "a/b"):
        manifest = {
            "id": bad_id, "name": "n", "version": "1", "author": "a",
            "type": "rom_source", "entry": "plugin.py",
        }
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("plugin.json", json.dumps(manifest))
            zf.writestr("plugin.py", "x = 1")
        with pytest.raises(ValueError):
            _install(zip_path)


@pytest.mark.asyncio
async def test_uninstalling_takes_the_stored_data_with_it(plugin_world, tmp_path):
    plugins_dir, data_dir = plugin_world
    _install(_zip_plugin(tmp_path, "1.0.0", {"plugin.py": "VERSION = '1.0.0'"}))
    (storage.plugin_data_dir("gd3-test-plugin") / "cache.json").write_text("x")

    assert await install_handler.uninstall_plugin("gd3-test-plugin") is True

    assert not (plugins_dir / "gd3-test-plugin").exists()
    assert not (data_dir / "gd3-test-plugin").exists()


@pytest.mark.asyncio
async def test_uninstalling_something_that_is_not_installed_changes_nothing(
    plugin_world,
):
    _, data_dir = plugin_world
    (storage.plugin_data_dir("other-plugin") / "keep.json").write_text("x")

    assert await install_handler.uninstall_plugin("gd3-test-plugin") is False

    assert (data_dir / "other-plugin" / "keep.json").exists()


def test_purge_reports_whether_there_was_anything_to_purge(plugin_world):
    assert storage.purge_plugin_data("never-stored-anything") is False
    storage.plugin_data_dir("has-data")
    assert storage.purge_plugin_data("has-data") is True
    assert storage.purge_plugin_data("has-data") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["logo", "asset"])
async def test_the_file_routes_refuse_to_serve_out_of_a_dot_directory(
    plugin_world, route, monkeypatch
):
    """Both serve straight off the plugin volume with no authentication, and
    the stored data now lives in that volume under a dot name."""
    from fastapi import HTTPException

    from endpoints.settings import plugins_router

    plugins_dir, data_dir = plugin_world
    monkeypatch.setattr(plugins_router, "PLUGINS_PATH", str(plugins_dir))
    hidden = data_dir / "assets"
    hidden.mkdir(parents=True)
    (hidden / "secret.js").write_text("token = 'leaked'")
    (data_dir / "logo.png").write_bytes(b"\x89PNG")

    with pytest.raises(HTTPException) as caught:
        if route == "logo":
            await plugins_router.get_plugin_logo(".data")
        else:
            await plugins_router.get_plugin_asset(".data", "secret.js")
    assert caught.value.status_code == 400


# ── the contract plugins are told to use ─────────────────────────────────────

def test_plugins_can_reach_the_data_directory_from_plugins_manager():
    """Documented import path. A plugin reads its settings from
    plugins.manager, and its data directory has to be in the same place."""
    from plugins.manager import plugin_data_dir

    assert plugin_data_dir is storage.plugin_data_dir
