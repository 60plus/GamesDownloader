"""ROM platform mapping table.

Maps filesystem slug (folder name) to display name, IGDB platform ID,
ScreenScraper system ID, and LaunchBox platform name.

Based on ROMM's platform list, extended for GamesDownloader.
"""

from __future__ import annotations

import re

# fs_slug → { name, igdb_id, ss_id, launchbox_name, cover_aspect }
# cover_aspect: aspect ratio for box art in library grid
#   "3/4"   = portrait tall (default - N64, GC, Wii, PS, Xbox, DS, modern)
#   "16/11" = old horizontal cases (SNES, SFC, Famicom, NES JP, PCE, Neo Geo)
#   "4/3"   = landscape (Genesis US/EU, Master System, Saturn, Dreamcast)
#   "1/1"   = square (Game Boy, Game Gear, Atari 2600)
PLATFORM_MAP: dict[str, dict] = {
    # ── Nintendo ──────────────────────────────────────────────────────────────
    "nes":          {"name": "Nintendo Entertainment System", "igdb_id": 18,  "ss_id": 3,   "launchbox_name": "Nintendo Entertainment System",       "cover_aspect": "3/4"},
    "famicom":      {"name": "Famicom",                       "igdb_id": 99,  "ss_id": 3,   "launchbox_name": "Nintendo Entertainment System",       "cover_aspect": "16/11"},
    "snes":         {"name": "Super Nintendo",                "igdb_id": 19,  "ss_id": 4,   "launchbox_name": "Super Nintendo Entertainment System", "cover_aspect": "16/11"},
    "snesna":       {"name": "Super Nintendo",                "igdb_id": 19,  "ss_id": 4,   "launchbox_name": "Super Nintendo Entertainment System", "cover_aspect": "16/11"},
    "sfc":          {"name": "Super Famicom",                 "igdb_id": 58,  "ss_id": 4,   "launchbox_name": "Super Nintendo Entertainment System", "cover_aspect": "16/11"},
    "n64":          {"name": "Nintendo 64",                   "igdb_id": 4,   "ss_id": 14,  "launchbox_name": "Nintendo 64",                         "cover_aspect": "3/4"},
    "n64dd":        {"name": "Nintendo 64DD",                 "igdb_id": 176, "ss_id": 122, "launchbox_name": "Nintendo 64DD",                       "cover_aspect": "3/4"},
    "gb":           {"name": "Game Boy",                      "igdb_id": 33,  "ss_id": 9,   "launchbox_name": "Nintendo Game Boy",                   "cover_aspect": "1/1"},
    "gbc":          {"name": "Game Boy Color",                "igdb_id": 22,  "ss_id": 10,  "launchbox_name": "Nintendo Game Boy Color",             "cover_aspect": "1/1"},
    "gba":          {"name": "Game Boy Advance",              "igdb_id": 24,  "ss_id": 12,  "launchbox_name": "Nintendo Game Boy Advance",           "cover_aspect": "3/4"},
    "nds":          {"name": "Nintendo DS",                   "igdb_id": 20,  "ss_id": 15,  "launchbox_name": "Nintendo DS",                         "cover_aspect": "3/4"},
    "n3ds":         {"name": "Nintendo 3DS",                  "igdb_id": 37,  "ss_id": 17,  "launchbox_name": "Nintendo 3DS",                        "cover_aspect": "3/4"},
    "gc":           {"name": "GameCube",                      "igdb_id": 21,  "ss_id": 13,  "launchbox_name": "Nintendo GameCube",                   "cover_aspect": "3/4"},
    "wii":          {"name": "Nintendo Wii",                  "igdb_id": 5,   "ss_id": 16,  "launchbox_name": "Nintendo Wii",                        "cover_aspect": "3/4"},
    "wiiu":         {"name": "Nintendo Wii U",                "igdb_id": 41,  "ss_id": 18,  "launchbox_name": "Nintendo Wii U",                      "cover_aspect": "3/4"},
    "switch":       {"name": "Nintendo Switch",               "igdb_id": 130, "ss_id": 225, "launchbox_name": "Nintendo Switch",                     "cover_aspect": "3/4"},
    "switch-2":     {"name": "Nintendo Switch 2",             "igdb_id": 508, "ss_id": 296, "launchbox_name": "Nintendo Switch 2",                    "cover_aspect": "3/4"},
    "fds":          {"name": "Famicom Disk System",           "igdb_id": 51,  "ss_id": 106, "launchbox_name": "Nintendo Famicom Disk System",        "cover_aspect": "16/11"},
    "virtualboy":   {"name": "Virtual Boy",                   "igdb_id": 39,  "ss_id": 11,  "launchbox_name": "Nintendo Virtual Boy",                "cover_aspect": "3/4"},
    "pokemini":     {"name": "Pokemon Mini",                  "igdb_id": 166, "ss_id": 211, "launchbox_name": "Nintendo Pokemon Mini",               "cover_aspect": "1/1"},
    "satellaview":  {"name": "Satellaview",                   "igdb_id": 53,  "ss_id": 107, "launchbox_name": "Super Nintendo Entertainment System", "cover_aspect": "16/11"},
    # ── Sega ──────────────────────────────────────────────────────────────────
    "mastersystem": {"name": "Sega Master System",            "igdb_id": 64,  "ss_id": 2,   "launchbox_name": "Sega Master System"},
    "genesis":      {"name": "Sega Genesis / Mega Drive",     "igdb_id": 29,  "ss_id": 1,   "launchbox_name": "Sega Genesis"},
    "megadrive":    {"name": "Sega Mega Drive",               "igdb_id": 29,  "ss_id": 1,   "launchbox_name": "Sega Mega Drive"},
    "megadrivejp":  {"name": "Sega Mega Drive (Japan)",       "igdb_id": 29,  "ss_id": 1,   "launchbox_name": "Sega Mega Drive"},
    "sega32x":      {"name": "Sega 32X",                      "igdb_id": 30,  "ss_id": 19,  "launchbox_name": "Sega 32X"},
    "sega32xjp":    {"name": "Sega 32X (Japan)",              "igdb_id": 30,  "ss_id": 19,  "launchbox_name": "Sega 32X"},
    "sega32xna":    {"name": "Sega 32X (NA)",                 "igdb_id": 30,  "ss_id": 19,  "launchbox_name": "Sega 32X"},
    "segacd":       {"name": "Sega CD / Mega CD",             "igdb_id": 78,  "ss_id": 20,  "launchbox_name": "Sega CD"},
    "megacd":       {"name": "Sega Mega CD",                  "igdb_id": 78,  "ss_id": 20,  "launchbox_name": "Sega Mega CD"},
    "megacdjp":     {"name": "Sega Mega CD (Japan)",          "igdb_id": 78,  "ss_id": 20,  "launchbox_name": "Sega Mega CD"},
    "saturn":       {"name": "Sega Saturn",                   "igdb_id": 32,  "ss_id": 22,  "launchbox_name": "Sega Saturn"},
    "saturnjp":     {"name": "Sega Saturn (Japan)",           "igdb_id": 32,  "ss_id": 22,  "launchbox_name": "Sega Saturn"},
    "dreamcast":    {"name": "Sega Dreamcast",                "igdb_id": 23,  "ss_id": 23,  "launchbox_name": "Sega Dreamcast"},
    "gamegear":     {"name": "Sega Game Gear",                "igdb_id": 35,  "ss_id": 21,  "launchbox_name": "Sega Game Gear"},
    "sg-1000":      {"name": "Sega SG-1000",                  "igdb_id": 84,  "ss_id": 109, "launchbox_name": "Sega SG-1000"},
    "mark3":        {"name": "Sega Mark III",                 "igdb_id": 64,  "ss_id": 2,   "launchbox_name": "Sega Master System"},
    # ── Sony ──────────────────────────────────────────────────────────────────
    "psx":          {"name": "PlayStation",                   "igdb_id": 7,   "ss_id": 57,  "launchbox_name": "Sony Playstation"},
    "ps2":          {"name": "PlayStation 2",                 "igdb_id": 8,   "ss_id": 58,  "launchbox_name": "Sony Playstation 2"},
    "ps3":          {"name": "PlayStation 3",                 "igdb_id": 9,   "ss_id": 59,  "launchbox_name": "Sony Playstation 3"},
    "ps4":          {"name": "PlayStation 4",                 "igdb_id": 48,  "ss_id": 60,  "launchbox_name": "Sony Playstation 4"},
    "ps5":          {"name": "PlayStation 5",                 "igdb_id": 167, "ss_id": 284, "launchbox_name": "Sony Playstation 5"},
    "psp":          {"name": "PlayStation Portable",          "igdb_id": 38,  "ss_id": 61,  "launchbox_name": "Sony PSP"},
    "psvita":       {"name": "PlayStation Vita",              "igdb_id": 46,  "ss_id": 62,  "launchbox_name": "Sony Playstation Vita"},
    # ── Microsoft ─────────────────────────────────────────────────────────────
    "xbox":         {"name": "Xbox",                          "igdb_id": 11,  "ss_id": 32,  "launchbox_name": "Microsoft Xbox"},
    "xbox360":      {"name": "Xbox 360",                      "igdb_id": 12,  "ss_id": 33,  "launchbox_name": "Microsoft Xbox 360"},
    "xboxone":      {"name": "Xbox One",                      "igdb_id": 49,  "ss_id": 34,  "launchbox_name": "Microsoft Xbox One"},
    "series-x-s":   {"name": "Xbox Series X/S",              "igdb_id": 169, "ss_id": None, "launchbox_name": "Microsoft Xbox Series X"},
    # ── SNK ───────────────────────────────────────────────────────────────────
    "neogeo":       {"name": "Neo Geo",                       "igdb_id": 80,  "ss_id": 142, "launchbox_name": "SNK Neo Geo AES"},
    "neogeocd":     {"name": "Neo Geo CD",                    "igdb_id": 136, "ss_id": 70,  "launchbox_name": "SNK Neo Geo CD"},
    "neogeocdjp":   {"name": "Neo Geo CD (Japan)",            "igdb_id": 136, "ss_id": 70,  "launchbox_name": "SNK Neo Geo CD"},
    "ngp":          {"name": "Neo Geo Pocket",                "igdb_id": 119, "ss_id": 25,  "launchbox_name": "SNK Neo Geo Pocket"},
    "ngpc":         {"name": "Neo Geo Pocket Color",          "igdb_id": 120, "ss_id": 82,  "launchbox_name": "SNK Neo Geo Pocket Color"},
    # ── Arcade ────────────────────────────────────────────────────────────────
    "arcade":       {"name": "Arcade",                        "igdb_id": 52,  "ss_id": 75,  "launchbox_name": "Arcade"},
    "mame":         {"name": "MAME",                          "igdb_id": 52,  "ss_id": 75,  "launchbox_name": "Arcade"},
    "fbneo":        {"name": "FinalBurn Neo",                 "igdb_id": 52,  "ss_id": 75,  "launchbox_name": "Arcade"},
    "fba":          {"name": "FinalBurn Alpha",               "igdb_id": 52,  "ss_id": 75,  "launchbox_name": "Arcade"},
    "cps":          {"name": "Capcom Play System",            "igdb_id": 52,  "ss_id": 6,   "launchbox_name": "Arcade"},
    "cps1":         {"name": "CPS-1",                         "igdb_id": 52,  "ss_id": 6,   "launchbox_name": "Arcade"},
    "cps2":         {"name": "CPS-2",                         "igdb_id": 52,  "ss_id": 7,   "launchbox_name": "Arcade"},
    "cps3":         {"name": "CPS-3",                         "igdb_id": 52,  "ss_id": 8,   "launchbox_name": "Arcade"},
    "naomi":        {"name": "Sega NAOMI",                    "igdb_id": 52,  "ss_id": 56,  "launchbox_name": "Sega NAOMI"},
    "naomi2":       {"name": "Sega NAOMI 2",                  "igdb_id": 52,  "ss_id": 56,  "launchbox_name": "Sega NAOMI 2"},
    "atomiswave":   {"name": "Atomiswave",                    "igdb_id": 52,  "ss_id": 53,  "launchbox_name": "Sammy Atomiswave"},
    # ── PC ────────────────────────────────────────────────────────────────────
    "dos":          {"name": "MS-DOS",                        "igdb_id": 13,  "ss_id": 135, "launchbox_name": "MS-DOS"},
    "pc":           {"name": "PC",                            "igdb_id": 6,   "ss_id": 138, "launchbox_name": "Windows"},
    "pcarcade":     {"name": "PC (Arcade)",                   "igdb_id": 6,   "ss_id": 138, "launchbox_name": "Windows"},
    "scummvm":      {"name": "ScummVM",                       "igdb_id": 13,  "ss_id": 123, "launchbox_name": "ScummVM"},
    # ── Atari ─────────────────────────────────────────────────────────────────
    "atari2600":    {"name": "Atari 2600",                    "igdb_id": 59,  "ss_id": 26,  "launchbox_name": "Atari 2600"},  # SS 26 = Atari 2600 (correct per SS website)
    "atari5200":    {"name": "Atari 5200",                    "igdb_id": 66,  "ss_id": 40,  "launchbox_name": "Atari 5200"},
    "atari7800":    {"name": "Atari 7800",                    "igdb_id": 60,  "ss_id": 41,  "launchbox_name": "Atari 7800"},
    "atarilynx":    {"name": "Atari Lynx",                    "igdb_id": 61,  "ss_id": 28,  "launchbox_name": "Atari Lynx"},
    "atarijaguar":  {"name": "Atari Jaguar",                  "igdb_id": 62,  "ss_id": 29,  "launchbox_name": "Atari Jaguar"},
    "atarijaguarcd":{"name": "Atari Jaguar CD",               "igdb_id": 62,  "ss_id": 171, "launchbox_name": "Atari Jaguar CD"},
    "atari800":     {"name": "Atari 800",                     "igdb_id": 65,  "ss_id": 43,  "launchbox_name": "Atari 800"},
    "atarist":      {"name": "Atari ST",                      "igdb_id": 63,  "ss_id": 42,  "launchbox_name": "Atari ST"},
    "atarixe":      {"name": "Atari XE",                      "igdb_id": 65,  "ss_id": 43,  "launchbox_name": "Atari XE Game System"},
    # ── Commodore ─────────────────────────────────────────────────────────────
    "c64":          {"name": "Commodore 64",                  "igdb_id": 15,  "ss_id": 66,  "launchbox_name": "Commodore 64"},
    "amiga":        {"name": "Amiga",                         "igdb_id": 16,  "ss_id": 64,  "launchbox_name": "Commodore Amiga"},
    "amiga1200":    {"name": "Amiga 1200",                    "igdb_id": 16,  "ss_id": 64,  "launchbox_name": "Commodore Amiga"},
    "amiga600":     {"name": "Amiga 600",                     "igdb_id": 16,  "ss_id": 64,  "launchbox_name": "Commodore Amiga"},
    "amigacd32":    {"name": "Amiga CD32",                    "igdb_id": 114, "ss_id": 130, "launchbox_name": "Commodore Amiga CD32"},
    # ── NEC / PC Engine ───────────────────────────────────────────────────────
    "pcengine":     {"name": "PC Engine / TurboGrafx-16",     "igdb_id": 86,  "ss_id": 31,  "launchbox_name": "NEC TurboGrafx-16"},
    "pcenginecd":   {"name": "PC Engine CD",                  "igdb_id": 87,  "ss_id": 114, "launchbox_name": "NEC TurboGrafx-CD"},
    "tg16":         {"name": "TurboGrafx-16",                 "igdb_id": 86,  "ss_id": 31,  "launchbox_name": "NEC TurboGrafx-16"},
    "tg-cd":        {"name": "TurboGrafx CD",                 "igdb_id": 87,  "ss_id": 114, "launchbox_name": "NEC TurboGrafx-CD"},
    "pcfx":         {"name": "PC-FX",                         "igdb_id": 274, "ss_id": 72,  "launchbox_name": "NEC PC-FX"},
    "pc88":         {"name": "NEC PC-8800",                   "igdb_id": 125, "ss_id": 94,  "launchbox_name": "NEC PC-8801"},
    "pc98":         {"name": "NEC PC-9800",                   "igdb_id": 149, "ss_id": 95,  "launchbox_name": "NEC PC-9801"},
    # ── Misc handheld / classic ───────────────────────────────────────────────
    "wonderswan":   {"name": "WonderSwan",                    "igdb_id": 57,  "ss_id": 45,  "launchbox_name": "Bandai WonderSwan"},
    "wonderswancolor":{"name": "WonderSwan Color",            "igdb_id": 123, "ss_id": 46,  "launchbox_name": "Bandai WonderSwan Color"},
    "colecovision": {"name": "ColecoVision",                  "igdb_id": 68,  "ss_id": 48,  "launchbox_name": "Coleco ColecoVision"},
    "intellivision":{"name": "Intellivision",                 "igdb_id": 67,  "ss_id": 115, "launchbox_name": "Mattel Intellivision"},
    "3do":          {"name": "3DO Interactive Multiplayer",   "igdb_id": 50,  "ss_id": 29,  "launchbox_name": "3DO Interactive Multiplayer"},
    "cdimono1":     {"name": "Philips CD-i",                  "igdb_id": 117, "ss_id": 133, "launchbox_name": "Philips CD-i"},
    "vectrex":      {"name": "Vectrex",                       "igdb_id": 70,  "ss_id": 102, "launchbox_name": "GCE Vectrex"},
    "channelf":     {"name": "Fairchild Channel F",           "igdb_id": 127, "ss_id": 80,  "launchbox_name": "Fairchild Channel F"},
    "supervision":  {"name": "Watara Supervision",            "igdb_id": None,"ss_id": 207, "launchbox_name": "Watara Supervision"},
    "gamegear":     {"name": "Sega Game Gear",                "igdb_id": 35,  "ss_id": 21,  "launchbox_name": "Sega Game Gear"},
    # ── ZX / Spectrum ─────────────────────────────────────────────────────────
    "zxspectrum":   {"name": "ZX Spectrum",                   "igdb_id": 26,  "ss_id": 76,  "launchbox_name": "Sinclair ZX Spectrum"},
    "zx81":         {"name": "ZX81",                          "igdb_id": 26,  "ss_id": 77,  "launchbox_name": "Sinclair ZX81"},
    # ── Common hyphenated slug aliases ───────────────────────────────────────────
    "super-nintendo":       {"name": "Super Nintendo",            "igdb_id": 19,  "ss_id": 4,   "launchbox_name": "Super Nintendo Entertainment System"},
    "sega-mega-drive":      {"name": "Sega Mega Drive",           "igdb_id": 29,  "ss_id": 1,   "launchbox_name": "Sega Mega Drive"},
    "sega-genesis":         {"name": "Sega Genesis",              "igdb_id": 29,  "ss_id": 1,   "launchbox_name": "Sega Genesis"},
    "nintendo-64":          {"name": "Nintendo 64",               "igdb_id": 4,   "ss_id": 14,  "launchbox_name": "Nintendo 64"},
    "game-boy":             {"name": "Game Boy",                  "igdb_id": 33,  "ss_id": 9,   "launchbox_name": "Nintendo Game Boy"},
    "game-boy-color":       {"name": "Game Boy Color",            "igdb_id": 22,  "ss_id": 10,  "launchbox_name": "Nintendo Game Boy Color"},
    "game-boy-advance":     {"name": "Game Boy Advance",          "igdb_id": 24,  "ss_id": 12,  "launchbox_name": "Nintendo Game Boy Advance"},
    "nintendo-ds":          {"name": "Nintendo DS",               "igdb_id": 20,  "ss_id": 15,  "launchbox_name": "Nintendo DS"},
    "nintendo-3ds":         {"name": "Nintendo 3DS",              "igdb_id": 37,  "ss_id": 17,  "launchbox_name": "Nintendo 3DS"},
    "playstation":          {"name": "PlayStation",               "igdb_id": 7,   "ss_id": 57,  "launchbox_name": "Sony Playstation"},
    "playstation-2":        {"name": "PlayStation 2",             "igdb_id": 8,   "ss_id": 58,  "launchbox_name": "Sony Playstation 2"},
    "playstation-portable": {"name": "PlayStation Portable",      "igdb_id": 38,  "ss_id": 61,  "launchbox_name": "Sony PSP"},
    "sega-saturn":          {"name": "Sega Saturn",               "igdb_id": 32,  "ss_id": 22,  "launchbox_name": "Sega Saturn"},
    "sega-dreamcast":       {"name": "Sega Dreamcast",            "igdb_id": 23,  "ss_id": 23,  "launchbox_name": "Sega Dreamcast"},
    "nintendo-gamecube":    {"name": "Nintendo GameCube",         "igdb_id": 21,  "ss_id": 13,  "launchbox_name": "Nintendo GameCube"},
    "nintendo-wii":         {"name": "Nintendo Wii",              "igdb_id": 5,   "ss_id": 116, "launchbox_name": "Nintendo Wii"},
    "sega-game-gear":       {"name": "Sega Game Gear",            "igdb_id": 35,  "ss_id": 21,  "launchbox_name": "Sega Game Gear"},
    "neo-geo":              {"name": "Neo Geo",                   "igdb_id": 80,  "ss_id": 27,  "launchbox_name": "SNK Neo Geo AES"},
    "atari-2600":           {"name": "Atari 2600",                "igdb_id": 59,  "ss_id": 26,  "launchbox_name": "Atari 2600"},
    "ms-dos":               {"name": "MS-DOS",                    "igdb_id": 13,  "ss_id": 135, "launchbox_name": "MS-DOS"},
}


def slug_from_fs_slug(fs_slug: str) -> str:
    """Convert filesystem slug to URL-safe slug.

    Uses the IGDB/common naming convention where possible.
    Falls back to slugifying the display name.
    """
    info = PLATFORM_MAP.get(fs_slug)
    if info:
        # Derive slug from display name
        name = info["name"]
    else:
        name = fs_slug

    # Slugify: lowercase, replace non-alnum with hyphens, collapse hyphens
    slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    return slug


def get_igdb_id(fs_slug: str) -> int | None:
    return PLATFORM_MAP.get(fs_slug, {}).get("igdb_id")


def get_ss_id(fs_slug: str) -> int | None:
    return PLATFORM_MAP.get(fs_slug, {}).get("ss_id")


def get_launchbox_name(fs_slug: str) -> str | None:
    return PLATFORM_MAP.get(fs_slug, {}).get("launchbox_name")


# ── Cover aspect ratio per platform (like RomM's "Cover style") ──────────────
# Determines box art proportions in library grid.
# Default is "3/4" (portrait tall) for platforms not listed here.
_COVER_ASPECT: dict[str, str] = {
    # 16/11 - old horizontal cases (SNES, Famicom, PCE, Neo Geo, TG16)
    "snes": "16/11", "snesna": "16/11", "sfc": "16/11", "super-nintendo": "16/11",
    "famicom": "16/11", "fds": "16/11", "satellaview": "16/11",
    "pcengine": "16/11", "pcenginecd": "16/11", "tg16": "16/11", "tg-cd": "16/11",
    "neogeo": "16/11", "neo-geo": "16/11",
    # 4/3 - landscape boxes (Genesis/MD US/EU, Master System, Saturn, Dreamcast, Mega CD)
    "genesis": "4/3", "megadrive": "4/3", "megadrivejp": "16/11",
    "sega-mega-drive": "4/3", "sega-genesis": "4/3",
    "mastersystem": "4/3", "mark3": "16/11",
    "sega32x": "4/3", "sega32xjp": "4/3", "sega32xna": "4/3",
    "segacd": "4/3", "megacd": "4/3", "megacdjp": "4/3",
    "saturn": "4/3", "saturnjp": "4/3", "sega-saturn": "4/3",
    "dreamcast": "4/3", "sega-dreamcast": "4/3",
    # 1/1 - square (Game Boy, Game Gear, Atari 2600, handhelds)
    "gb": "1/1", "gbc": "1/1", "game-boy": "1/1", "game-boy-color": "1/1",
    "gamegear": "1/1", "sega-game-gear": "1/1",
    "atari2600": "1/1", "atari-2600": "1/1",
    "pokemini": "1/1", "ngp": "1/1", "ngpc": "1/1",
    "wonderswan": "1/1", "wonderswancolor": "1/1",
    "supervision": "1/1",
    # 3/4 - portrait (everything else: N64, GC, Wii, PS, Xbox, DS, GBA, modern)
    # This is the default, so not listed here.
}


def get_cover_aspect(fs_slug: str) -> str:
    """Return the cover aspect ratio string for a platform."""
    return _COVER_ASPECT.get(fs_slug, "3/4")


# ── HLTB platform name mapping ────────────────────────────────────────────────
_HLTB_PLATFORM: dict[str, str] = {
    "nes":          "NES",
    "famicom":      "NES",
    "snes":         "Super Nintendo",
    "snesna":       "Super Nintendo",
    "sfc":          "Super Nintendo",
    "n64":          "Nintendo 64",
    "n64dd":        "Nintendo 64",
    "gb":           "Game Boy",
    "gbc":          "Game Boy Color",
    "gba":          "Game Boy Advance",
    "nds":          "Nintendo DS",
    "n3ds":         "Nintendo 3DS",
    "gc":           "Nintendo GameCube",
    "wii":          "Wii",
    "wiiu":         "Wii U",
    "switch":       "Nintendo Switch",
    "switch-2":     "Nintendo Switch 2",
    "virtualboy":   "Virtual Boy",
    "mastersystem": "Sega Master System",
    "mark3":        "Sega Master System",
    "genesis":      "Sega Mega Drive/Genesis",
    "megadrive":    "Sega Mega Drive/Genesis",
    "megadrivejp":  "Sega Mega Drive/Genesis",
    "sega32x":      "Sega 32X",
    "sega32xjp":    "Sega 32X",
    "sega32xna":    "Sega 32X",
    "segacd":       "Sega CD",
    "megacd":       "Sega CD",
    "megacdjp":     "Sega CD",
    "saturn":       "Sega Saturn",
    "saturnjp":     "Sega Saturn",
    "dreamcast":    "Dreamcast",
    "gamegear":     "Sega Game Gear",
    "psx":          "PlayStation",
    "ps2":          "PlayStation 2",
    "ps3":          "PlayStation 3",
    "ps4":          "PlayStation 4",
    "ps5":          "PlayStation 5",
    "psp":          "PlayStation Portable",
    "psvita":       "PlayStation Vita",
    "xbox":         "Xbox",
    "xbox360":      "Xbox 360",
    "xboxone":      "Xbox One",
    "series-x-s":   "Xbox Series X/S",
    "neogeo":       "Neo Geo",
    "neogeocd":     "Neo Geo CD",
    "ngp":          "Neo Geo Pocket",
    "ngpc":         "Neo Geo Pocket",
    "arcade":       "Arcade",
    "mame":         "Arcade",
    "fbneo":        "Arcade",
    "fba":          "Arcade",
    "cps":          "Arcade",
    "cps1":         "Arcade",
    "cps2":         "Arcade",
    "cps3":         "Arcade",
    "dos":          "PC",
    "pc":           "PC",
    "atari2600":    "Atari 2600",
    "atari5200":    "Atari 5200",
    "atari7800":    "Atari 7800",
    "atarilynx":    "Atari Lynx",
    "atarijaguar":  "Atari Jaguar",
    "atarijaguarcd":"Atari Jaguar CD",
    "atari800":     "Atari 8-bit Family",
    "atarist":      "Atari ST",
    "c64":          "Commodore 64",
    "amiga":        "Amiga",
    "amiga1200":    "Amiga",
    "amiga600":     "Amiga",
    "amigacd32":    "Amiga CD32",
    "turbografx16": "TurboGrafx-16",
    "turbografxcd": "TurboGrafx-CD",
    "tg-cd":        "TurboGrafx-CD",
    "pcengine":     "TurboGrafx-16",
    "wonderswan":   "WonderSwan",
    "wonderswancolor": "WonderSwan",
}


def get_hltb_name(fs_slug: str) -> str | None:
    """Return the HLTB platform name for a given fs_slug, or None if unknown."""
    return _HLTB_PLATFORM.get(fs_slug)
