"""ROM library settings endpoints.

Prefix: /api/settings/roms
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from config import ROMS_PATH
from config import config_manager
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.filesystem import rom_scanner
from handler.filesystem.rom_paths import make_platform_folders, roms_library_path
from handler.metadata import scrape_presets
from handler.roms import rom_source_handler

router = APIRouter(prefix="/api/settings/roms", tags=["settings-roms"])


# ── General settings ──────────────────────────────────────────────────────────

class RomSettingsBody(BaseModel):
    library_path: str | None = None
    auto_scan_on_start: bool = False
    launchbox_enabled: bool = True
    max_rom_bytes: int = 0
    hash_max_bytes: int = 0
    scan_interval_hours: int = 0


def _library_missing() -> bool:
    return not os.path.isdir(roms_library_path(config_manager))


@protected_route(router.get, "", scopes=[Scopes.SETTINGS_READ])
async def get_rom_settings(request: Request) -> dict:
    cfg = config_manager.get_section("roms")
    return {
        "library_path":       cfg.get("library_path") or ROMS_PATH,
        # A library that is not there - a typo, a disk not mounted into the
        # container - gets no platform folders, and the screen says so.
        "library_path_missing": await asyncio.to_thread(_library_missing),
        "auto_scan_on_start": cfg.get("auto_scan_on_start", False),
        "launchbox_enabled":  cfg.get("launchbox_enabled", True),
        # The ceiling actually enforced, not the stored key: unset means the
        # built-in default, and a screen showing a different number from the one
        # the download obeys would be worse than showing nothing.
        "max_rom_bytes":      rom_source_handler.max_rom_bytes(),
        # Same reasoning: report the ceiling the scan actually obeys.
        "hash_max_bytes":     rom_scanner.hash_ceiling_bytes(),
        # 0 means the scheduled scan is off, which is the default.
        "scan_interval_hours": rom_scanner.resolve_scan_interval_hours(
            cfg.get("scan_interval_hours")),
    }


@protected_route(router.post, "", scopes=[Scopes.SETTINGS_WRITE])
async def save_rom_settings(request: Request, body: RomSettingsBody) -> dict:
    # Merge, never replace. save_section() overwrites the whole section, so
    # writing a fixed set of keys here drops every other key the section holds.
    # That is exactly how a hand-set max_rom_bytes used to disappear on the
    # first save from this screen.
    cfg = dict(config_manager.get_section("roms"))
    cfg.update({
        "library_path":       body.library_path or ROMS_PATH,
        "auto_scan_on_start": body.auto_scan_on_start,
        "launchbox_enabled":  body.launchbox_enabled,
        # 0 means "no override": fall back to the built-in ceiling.
        "max_rom_bytes":      max(body.max_rom_bytes, 0),
        # 0 here means something else: no ceiling at all, hash everything.
        "hash_max_bytes":     max(body.hash_max_bytes, 0),
        # Anything that is not a whole positive number of hours is
        # read as off: a scan started by a typo is a scan nobody asked
        # for, and it walks every platform.
        "scan_interval_hours": rom_scanner.resolve_scan_interval_hours(
            body.scan_interval_hours),
    })
    config_manager.save_section("roms", cfg)
    # The platform folders, now rather than at the next restart, so a library
    # just moved is ready to fill over FTP. Saved either way: the path may be a
    # disk about to be mounted.
    root = roms_library_path(config_manager)
    out = await asyncio.to_thread(
        make_platform_folders, root, create_root=root == ROMS_PATH)
    return {"ok": True, "library_path_missing": not out["root_exists"]}


# ── Scrape presets (per platform) ─────────────────────────────────────────────

class ScrapePresetEntry(BaseModel):
    cover_type: str = "box-2D"
    region:     str = "wor"
    # The default, not an empty list: the platform page posts a preset with only
    # a cover type for a platform nobody has set up, and that must not cost the
    # platform its screenshots.
    extras:     list[str] = Field(default_factory=lambda: list(scrape_presets.DEFAULT_MEDIA))


class ScrapePresetsBody(BaseModel):
    presets: dict[str, ScrapePresetEntry]


@protected_route(router.get, "/scrape-presets", scopes=[Scopes.SETTINGS_READ])
async def get_scrape_presets(request: Request) -> dict:
    """Every platform's preset keyed by fs_slug, as the scrape will read it."""
    stored = config_manager.get_section("rom_scrape_presets") or {}
    return {slug: scrape_presets.as_shown(p) for slug, p in stored.items() if isinstance(p, dict)}


@protected_route(router.post, "/scrape-presets", scopes=[Scopes.SETTINGS_WRITE])
async def save_scrape_presets(request: Request, body: ScrapePresetsBody) -> dict:
    """Save per-platform scrape presets."""
    data = {k: scrape_presets.as_saved(v.model_dump()) for k, v in body.presets.items()}
    config_manager.save_section("rom_scrape_presets", data)
    return {"ok": True}


@protected_route(router.get, "/scrape-presets/{fs_slug}", scopes=[Scopes.SETTINGS_READ])
async def get_platform_preset(request: Request, fs_slug: str) -> dict:
    """One platform's preset, or the default for a platform nobody set up."""
    all_presets = config_manager.get_section("rom_scrape_presets") or {}
    return scrape_presets.as_shown(all_presets.get(fs_slug))
