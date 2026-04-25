"""Platform metadata from EmulationStation-format XMLs.

Parses POMOC/SYSTEM/metadata-global XMLs bundled in backend/data/platform_metadata/.
Provides accent colour, colour palette, and multi-language descriptions per platform.

Loaded once on first access, then cached in memory.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "platform_metadata"

# Language attribute in XML  →  short key returned in API
_LANG_MAP: dict[str, str] = {
    "de_DE": "de",
    "es_ES": "es",
    "fr_FR": "fr",
    "it_IT": "it",
    "nl_NL": "nl",
    "pl_PL": "pl",
    "pt_BR": "pt",
    "ru_RU": "ru",
    "ja_JP": "ja",
    "ko_KR": "ko",
    "zh_CN": "zh_CN",
    "zh_TW": "zh_TW",
    "sv_SE": "sv",
    "ro_RO": "ro",
    "ca_ES": "ca",
}

# Hyphenated aliases that have no XML → resolve to canonical slug
_ALIASES: dict[str, str] = {
    "super-nintendo":       "snes",
    "sega-mega-drive":      "megadrive",
    "sega-genesis":         "genesis",
    "nintendo-64":          "n64",
    "game-boy":             "gb",
    "game-boy-color":       "gbc",
    "game-boy-advance":     "gba",
    "nintendo-ds":          "nds",
    "nintendo-3ds":         "n3ds",
    "playstation":          "psx",
    "playstation-2":        "ps2",
    "playstation-portable": "psp",
    "sega-saturn":          "saturn",
    "sega-dreamcast":       "dreamcast",
    "nintendo-gamecube":    "gc",
    "nintendo-wii":         "wii",
    "sega-game-gear":       "gamegear",
    "neo-geo":              "neogeo",
    "atari-2600":           "atari2600",
    "ms-dos":               "dos",
}


def _parse_xml(path: Path) -> dict:
    root = ET.parse(path).getroot()

    # Top-level variables
    vars_el = root.find("variables")
    top: dict[str, str] = {}
    if vars_el is not None:
        for child in vars_el:
            if child.text:
                top[child.tag] = child.text.strip()

    # Multi-language descriptions (default EN from top-level systemDescription)
    descriptions: dict[str, str] = {}
    if top.get("systemDescription"):
        descriptions["en"] = top["systemDescription"]

    for lang_el in root.findall("language"):
        lang_attr = lang_el.get("name", "")
        lang_key = _LANG_MAP.get(lang_attr, lang_attr)
        desc_el = lang_el.find("variables/systemDescription")
        if desc_el is not None and desc_el.text:
            descriptions[lang_key] = desc_el.text.strip()

    palette = [
        top.get("systemColorPalette1", ""),
        top.get("systemColorPalette2", ""),
        top.get("systemColorPalette3", ""),
        top.get("systemColorPalette4", ""),
    ]

    return {
        "name":          top.get("systemName", ""),
        "color":         top.get("systemColor", ""),
        "palette":       [p for p in palette if p],
        "manufacturer":  top.get("systemManufacturer", ""),
        "release_year":  top.get("systemReleaseYear", ""),
        "hardware_type": top.get("systemHardwareType", ""),
        "cover_size":    top.get("systemCoverSize", ""),
        "descriptions":  descriptions,
    }


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not _DATA_DIR.exists():
        return result
    for xml_path in sorted(_DATA_DIR.glob("*.xml")):
        slug = xml_path.stem
        try:
            result[slug] = _parse_xml(xml_path)
        except Exception:
            pass
    # Expand aliases so every fs_slug in PLATFORM_MAP gets an entry
    for alias, canonical in _ALIASES.items():
        if canonical in result and alias not in result:
            result[alias] = result[canonical]
    return result


def get_all() -> dict[str, dict]:
    """Return metadata for all platforms keyed by fs_slug."""
    return _load_all()


def get(fs_slug: str) -> dict | None:
    """Return metadata for a single fs_slug, or None if not found."""
    slug = _ALIASES.get(fs_slug, fs_slug)
    return _load_all().get(slug)
