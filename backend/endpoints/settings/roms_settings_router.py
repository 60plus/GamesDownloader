"""ROM library settings endpoints.

Prefix: /api/settings/roms
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from config import ROMS_PATH
from config import config_manager
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.filesystem import rom_scanner
from handler.roms import rom_source_handler

router = APIRouter(prefix="/api/settings/roms", tags=["settings-roms"])


# ── General settings ──────────────────────────────────────────────────────────

class RomSettingsBody(BaseModel):
    library_path: str | None = None
    auto_scan_on_start: bool = False
    launchbox_enabled: bool = True
    max_rom_bytes: int = 0
    hash_max_bytes: int = 0


@protected_route(router.get, "", scopes=[Scopes.SETTINGS_READ])
async def get_rom_settings(request: Request) -> dict:
    cfg = config_manager.get_section("roms")
    return {
        "library_path":       cfg.get("library_path") or ROMS_PATH,
        "auto_scan_on_start": cfg.get("auto_scan_on_start", False),
        "launchbox_enabled":  cfg.get("launchbox_enabled", True),
        # The ceiling actually enforced, not the stored key: unset means the
        # built-in default, and a screen showing a different number from the one
        # the download obeys would be worse than showing nothing.
        "max_rom_bytes":      rom_source_handler.max_rom_bytes(),
        # Same reasoning: report the ceiling the scan actually obeys.
        "hash_max_bytes":     rom_scanner.hash_ceiling_bytes(),
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
    })
    config_manager.save_section("roms", cfg)
    return {"ok": True}


# ── Scrape presets (per platform) ─────────────────────────────────────────────

class ScrapePresetEntry(BaseModel):
    cover_type: str = "box-2D"
    region:     str = "wor"
    extras:     list[str] = []


class ScrapePresetsBody(BaseModel):
    presets: dict[str, ScrapePresetEntry]


@protected_route(router.get, "/scrape-presets", scopes=[Scopes.SETTINGS_READ])
async def get_scrape_presets(request: Request) -> dict:
    """Return all per-platform scrape presets keyed by fs_slug."""
    return config_manager.get_section("rom_scrape_presets") or {}


@protected_route(router.post, "/scrape-presets", scopes=[Scopes.SETTINGS_WRITE])
async def save_scrape_presets(request: Request, body: ScrapePresetsBody) -> dict:
    """Save per-platform scrape presets."""
    data = {k: v.model_dump() for k, v in body.presets.items()}
    config_manager.save_section("rom_scrape_presets", data)
    return {"ok": True}


@protected_route(router.get, "/scrape-presets/{fs_slug}", scopes=[Scopes.SETTINGS_READ])
async def get_platform_preset(request: Request, fs_slug: str) -> dict:
    """Return scrape preset for a single platform (fallback to defaults)."""
    all_presets = config_manager.get_section("rom_scrape_presets") or {}
    return all_presets.get(fs_slug, {
        "cover_type": "box-2D",
        "region":     "wor",
        "extras":     [],
    })
