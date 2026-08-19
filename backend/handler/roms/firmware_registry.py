"""Firmware the bundled emulator cores ask for.

Keyed by the EmulatorJS core name the player is launched with (see
``frontend/src/utils/ejsCores.ts``), because that name decides which libretro
core runs and therefore which files it goes looking for.

Every entry comes from the libretro ``.info`` of the core EmulatorJS actually
ships for that name, so the filenames are the ones the core probes for rather
than the ones a BIOS pack happens to use.  A core finds a file by its exact
name; a correct dump under a different name is invisible to it.

Two consequences worth knowing before touching this:

* ``optional`` is not cosmetic.  ``pcsx_rearmed`` marks every PlayStation BIOS
  optional because it falls back to a built-in replacement, which is why PSX
  games run here with no firmware at all.  ``puae`` marks two Kickstarts
  mandatory, and Amiga hard-drive content really will not boot without them.
* A path may carry a directory (``fbneo/neogeo.zip``).  That directory is part
  of where the core looks, so it has to survive into the emulator's
  filesystem.  EmulatorJS flattens whatever ``EJS_biosUrl`` downloads down to a
  bare filename, which is why GD writes firmware into the emulator itself
  instead of handing over a URL.

The checksums are deliberately not here: a ``.info`` does not carry any, so
validating an uploaded file is a separate concern with its own source.
"""

from __future__ import annotations

from typing import NamedTuple


class Firmware(NamedTuple):
    """One file a core looks for, named exactly as the core spells it."""

    path: str
    """Relative to the core's system directory; may contain a directory."""

    desc: str
    """The core's own description, shown when asking a user for the file."""

    optional: bool
    """False means the core cannot run the affected content without it."""


# EmulatorJS core name -> the libretro core it loads.  Kept for provenance: it
# is what makes the table below checkable against libretro's own metadata.
LIBRETRO_CORE: dict[str, str] = {
    "3do":         "opera",
    "amiga":       "puae",
    "arcade":      "fbneo",
    "atari5200":   "a5200",
    "atari7800":   "prosystem",
    "c128":        "vice_x128",
    "c64":         "vice_x64sc",
    "coleco":      "gearcoleco",
    "gb":          "gambatte",
    "gba":         "mgba",
    "jaguar":      "virtualjaguar",
    "lynx":        "handy",
    "n64":         "mupen64plus_next",
    "nds":         "melonds",
    "nes":         "fceumm",
    "pce":         "mednafen_pce",
    "pcfx":        "mednafen_pcfx",
    "psp":         "ppsspp",
    "psx":         "pcsx_rearmed",
    "sega":        "genesis_plus_gx",
    "sega32x":     "picodrive",
    "segaCD":      "genesis_plus_gx",
    "segaGG":      "genesis_plus_gx",
    "segaMD":      "genesis_plus_gx",
    "segaMS":      "smsplus",
    "segaSaturn":  "yabause",
    "snes":        "snes9x",
}


# EmulatorJS core name -> every firmware file that core declares.
FIRMWARE: dict[str, tuple[Firmware, ...]] = {
    # opera (13 files)
    "3do": (
        Firmware("panafz1.bin", "panafz1.bin (Panasonic FZ-1 BIOS)", True),
        Firmware("panafz10.bin", "panafz10.bin (Panasonic FZ-10 BIOS)", True),
        Firmware("panafz10-norsa.bin", "panafz10-norsa.bin (Panasonic FZ-10 BIOS [Encryption Check Disabled])", True),
        Firmware("panafz10e-anvil.bin", "panafz10e-anvil.bin (Panasonic FZ-10E ANVIL BIOS)", True),
        Firmware("panafz10e-anvil-norsa.bin", "panafz10e-anvil-norsa.bin (Panasonic FZ-10E ANVIL BIOS [Encryption Check Disabled])", True),
        Firmware("goldstar.bin", "goldstar.bin (Goldstar GDO-101M BIOS)", True),
        Firmware("sanyotry.bin", "sanyotry.bin (Sanyo Try IMP-21J BIOS)", True),
        Firmware("3do_arcade_saot.bin", "3do_arcade_saot.bin (Shootout At Old Tucson BIOS)", True),
        Firmware("panafz1-kanji.bin", "panafz1-kanji.bin (Panasonic FZ-1 Kanji Font ROM)", True),
        Firmware("panafz10ja-anvil-kanji.bin", "panafz10ja-anvil-kanji.bin (Panasonic FZ-10JA Kanji Font ROM)", True),
        Firmware("panafz1j.bin", "panafz1j.bin (Panasonic FZ-1J BIOS)", True),
        Firmware("panafz1j-norsa.bin", "panafz1j-norsa.bin (Panasonic FZ-1J BIOS [Encryption Check Disabled])", True),
        Firmware("panafz1j-kanji.bin", "panafz1j-kanji.bin (Panasonic FZ-1J Kanji Font ROM)", True),
    ),
    # puae (12 files - 4 mandatory)
    "amiga": (
        Firmware("kick33180.A500", "kick33180.A500 | amiga-os-120.rom (A500-A2000 KS v1.2 rev 33.180)", True),
        Firmware("kick34005.A500", "kick34005.A500 | amiga-os-130.rom (A500-A2000-CDTV KS v1.3 rev 34.005)", False),
        Firmware("kick37175.A500", "kick37175.A500 | amiga-os-204.rom (A500+ KS v2.04 rev 37.175)", True),
        Firmware("kick37350.A600", "kick37350.A600 | amiga-os-205-a600.rom (A600 KS v2.05 rev 37.350)", True),
        Firmware("kick40063.A600", "kick40063.A600 | amiga-os-310-a600.rom (A600-A2000 KS v3.1 rev 40.063)", True),
        Firmware("kick39106.A1200", "kick39106.A1200 | amiga-os-300-a1200.rom (A1200 KS v3.0 rev 39.106)", True),
        Firmware("kick40068.A1200", "kick40068.A1200 | amiga-os-310-a1200.rom (A1200 KS v3.1 rev 40.068)", False),
        Firmware("kick39106.A4000", "kick39106.A4000 | amiga-os-300-a4000.rom (A4000 KS v3.0 rev 39.106)", True),
        Firmware("kick40068.A4000", "kick40068.A4000 | amiga-os-310-a4000.rom (A4000 KS v3.1 rev 40.068)", True),
        Firmware("kick34005.CDTV", "kick34005.CDTV | amiga-os-130-cdtv-ext.rom (CDTV extended ROM v1.0)", True),
        Firmware("kick40060.CD32", "kick40060.CD32 | amiga-os-310-cd32.rom (CD32 KS v3.1 rev 40.060)", False),
        Firmware("kick40060.CD32.ext", "kick40060.CD32.ext | amiga-os-310-cd32-ext.rom (CD32 extended ROM rev 40.060)", False),
    ),
    # fbneo (23 files)
    "arcade": (
        Firmware("fbneo/neogeo.zip", "fbneo/neogeo.zip (Neo Geo BIOS)", True),
        Firmware("fbneo/neocdz.zip", "fbneo/neocdz.zip (Neo Geo CDZ System BIOS)", True),
        Firmware("fbneo/decocass.zip", "fbneo/decocass.zip (DECO Cassette System BIOS)", True),
        Firmware("fbneo/isgsm.zip", "fbneo/isgsm.zip (ISG Selection Master Type 2006 System BIOS)", True),
        Firmware("fbneo/midssio.zip", "fbneo/midssio.zip (Midway SSIO Sound Board Internal ROM)", True),
        Firmware("fbneo/nmk004.zip", "fbneo/nmk004.zip (NMK004 Internal ROM)", True),
        Firmware("fbneo/pgm.zip", "fbneo/pgm.zip (PGM System BIOS)", True),
        Firmware("fbneo/skns.zip", "fbneo/skns.zip (Super Kaneko Nova System BIOS)", True),
        Firmware("fbneo/ym2608.zip", "fbneo/ym2608.zip (YM2608 Internal ROM)", True),
        Firmware("fbneo/cchip.zip", "fbneo/cchip.zip (C-Chip Internal ROM)", True),
        Firmware("fbneo/bubsys.zip", "fbneo/bubsys.zip (Bubble System BIOS)", True),
        Firmware("fbneo/namcoc69.zip", "fbneo/namcoc69.zip (Namco C69 BIOS)", True),
        Firmware("fbneo/namcoc70.zip", "fbneo/namcoc70.zip (Namco C70 BIOS)", True),
        Firmware("fbneo/namcoc75.zip", "fbneo/namcoc75.zip (Namco C75 BIOS)", True),
        Firmware("fbneo/coleco.zip", "fbneo/coleco.zip (ColecoVision System BIOS)", True),
        Firmware("fbneo/fdsbios.zip", "fbneo/fdsbios.zip (FDS System BIOS)", True),
        Firmware("fbneo/msx.zip", "fbneo/msx.zip (MSX1 System BIOS)", True),
        Firmware("fbneo/ngp.zip", "fbneo/ngp.zip (NeoGeo Pocket BIOS)", True),
        Firmware("fbneo/spectrum.zip", "fbneo/spectrum.zip (ZX Spectrum BIOS)", True),
        Firmware("fbneo/spec128.zip", "fbneo/spec128.zip (ZX Spectrum 128 BIOS)", True),
        Firmware("fbneo/spec1282a.zip", "fbneo/spec1282a.zip (ZX Spectrum 128 +2a BIOS)", True),
        Firmware("fbneo/channelf.zip", "fbneo/channelf.zip (Fairchild Channel F BIOS)", True),
        Firmware("fbneo/hiscore.dat", "fbneo/hiscore.dat (High Score support database)", True),
    ),
    # a5200 (1 file)
    "atari5200": (
        Firmware("5200.rom", "5200.rom (5200 BIOS)", True),
    ),
    # prosystem (1 file)
    "atari7800": (
        Firmware("7800 BIOS (U).rom", "7800 BIOS (U).rom (7800 BIOS)", True),
    ),
    # vice_x128 (5 files)
    "c128": (
        Firmware("vice/JiffyDOS_C128.bin", "vice/JiffyDOS_C128.bin (JiffyDOS C128 Kernal)", True),
        Firmware("vice/JiffyDOS_C64.bin", "vice/JiffyDOS_C64.bin (JiffyDOS C64 Kernal)", True),
        Firmware("vice/JiffyDOS_1541-II.bin", "vice/JiffyDOS_1541-II.bin (JiffyDOS 1541 drive BIOS)", True),
        Firmware("vice/JiffyDOS_1571_repl310654.bin", "vice/JiffyDOS_1571_repl310654.bin (JiffyDOS 1571 drive BIOS)", True),
        Firmware("vice/JiffyDOS_1581.bin", "vice/JiffyDOS_1581.bin (JiffyDOS 1581 drive BIOS)", True),
    ),
    # vice_x64sc (4 files)
    "c64": (
        Firmware("vice/JiffyDOS_C64.bin", "vice/JiffyDOS_C64.bin (JiffyDOS C64 Kernal)", True),
        Firmware("vice/JiffyDOS_1541-II.bin", "vice/JiffyDOS_1541-II.bin (JiffyDOS 1541 drive BIOS)", True),
        Firmware("vice/JiffyDOS_1571_repl310654.bin", "vice/JiffyDOS_1571_repl310654.bin (JiffyDOS 1571 drive BIOS)", True),
        Firmware("vice/JiffyDOS_1581.bin", "vice/JiffyDOS_1581.bin (JiffyDOS 1581 drive BIOS)", True),
    ),
    # gearcoleco (1 file - 1 mandatory)
    "coleco": (
        Firmware("colecovision.rom", "colecovision.rom (ColecoVision BIOS)", False),
    ),
    # gambatte (2 files)
    "gb": (
        Firmware("gb_bios.bin", "gb_bios.bin (Game Boy BIOS)", True),
        Firmware("gbc_bios.bin", "gbc_bios.bin (Game Boy Color BIOS)", True),
    ),
    # mgba (4 files)
    "gba": (
        Firmware("gba_bios.bin", "gba_bios.bin (Game Boy Advance BIOS)", True),
        Firmware("gb_bios.bin", "gb_bios.bin (Game Boy BIOS)", True),
        Firmware("gbc_bios.bin", "gbc_bios.bin (Game Boy Color BIOS)", True),
        Firmware("sgb_bios.bin", "sgb_bios.bin (Super Game Boy BIOS)", True),
    ),
    # virtualjaguar (2 files)
    "jaguar": (
        Firmware("[BIOS] Atari Jaguar CD (World).j64", "[BIOS] Atari Jaguar CD (World).j64 (Jaguar CD BIOS, retail - optional override)", True),
        Firmware("[BIOS] Atari Jaguar Developer CD (World).j64", "[BIOS] Atari Jaguar Developer CD (World).j64 (Jaguar CD BIOS, developer - optional override)", True),
    ),
    # handy (1 file)
    "lynx": (
        Firmware("lynxboot.img", "lynxboot.img (Lynx Boot Image)", True),
    ),
    # mupen64plus_next (1 file)
    "n64": (
        Firmware("Mupen64plus/IPL.n64", "Mupen64plus/IPL.n64 (64DD BIOS)", True),
    ),
    # melonds (8 files)
    "nds": (
        Firmware("firmware.bin", "firmware.bin (NDS Firmware)", True),
        Firmware("bios7.bin", "bios7.bin (ARM7 BIOS)", True),
        Firmware("bios9.bin", "bios9.bin (ARM9 BIOS)", True),
        Firmware("dsi_firmware.bin", "dsi_firmware.bin (DSi Firmware)", True),
        Firmware("dsi_bios7.bin", "dsi_bios7.bin (DSi ARM7 BIOS)", True),
        Firmware("dsi_bios9.bin", "dsi_bios9.bin (DSi ARM9 BIOS)", True),
        Firmware("dsi_nand.bin", "dsi_nand.bin (DSi NAND)", True),
        Firmware("dsi_sd_card.bin", "dsi_sd_card.bin (DSi SD card)", True),
    ),
    # fceumm (3 files)
    "nes": (
        Firmware("disksys.rom", "disksys.rom (Family Computer Disk System BIOS)", True),
        Firmware("nes.pal", "nes.pal (custom NES Palette)", True),
        Firmware("gamegenie.nes", "gamegenie.nes (Game Genie add-on cartridge)", True),
    ),
    # mednafen_pce (4 files)
    "pce": (
        Firmware("syscard3.pce", "syscard3.pce (Super CD-ROM2 System V3.xx)", True),
        Firmware("syscard2.pce", "syscard2.pce (CD-ROM System V2.xx)", True),
        Firmware("syscard1.pce", "syscard1.pce (CD-ROM System V1.xx)", True),
        Firmware("gexpress.pce", "gexpress.pce (Game Express CD Card)", True),
    ),
    # mednafen_pcfx (1 file - 1 mandatory)
    "pcfx": (
        Firmware("pcfx.rom", "pcfx.rom (PC-FX BIOS v1.00 - 2 Sep 1994)", False),
    ),
    # ppsspp (1 file - 1 mandatory)
    "psp": (
        Firmware("PPSSPP/ppge_atlas.zim", "ppge_atlas.zim (PPSSPP Data ROM)", False),
    ),
    # pcsx_rearmed (4 files)
    "psx": (
        Firmware("scph5500.bin", "scph5500.bin (PS1 JP BIOS)", True),
        Firmware("scph5501.bin", "scph5501.bin (PS1 US BIOS)", True),
        Firmware("scph5502.bin", "scph5502.bin (PS1 EU BIOS)", True),
        Firmware("psxonpsp660.bin", "psxonpsp660.bin (PSP PSX Emu BIOS)", True),
    ),
    # genesis_plus_gx (12 files)
    "sega": (
        Firmware("bios_MD.bin", "bios_MD.bin (Mega Drive startup ROM)", True),
        Firmware("bios_CD_E.bin", "bios_CD_E.bin (MegaCD EU BIOS)", True),
        Firmware("bios_CD_U.bin", "bios_CD_U.bin (SegaCD US BIOS)", True),
        Firmware("bios_CD_J.bin", "bios_CD_J.bin (MegaCD JP BIOS)", True),
        Firmware("bios_E.sms", "bios_E.sms (MasterSystem EU BIOS)", True),
        Firmware("bios_U.sms", "bios_U.sms (MasterSystem US BIOS)", True),
        Firmware("bios_J.sms", "bios_J.sms (MasterSystem JP BIOS)", True),
        Firmware("bios.gg", "bios.gg (GameGear BIOS)", True),
        Firmware("sk.bin", "sk.bin (Sonic & Knuckles ROM)", True),
        Firmware("sk2chip.bin", "sk2chip.bin (Sonic & Knuckles UPMEM ROM)", True),
        Firmware("areplay.bin", "areplay.bin (Action Replay ROM)", True),
        Firmware("ggenie.bin", "ggenie.bin (Game Genie ROM)", True),
    ),
    # picodrive (3 files)
    "sega32x": (
        Firmware("bios_CD_E.bin", "bios_CD_E.bin (MegaCD EU BIOS)", True),
        Firmware("bios_CD_U.bin", "bios_CD_U.bin (SegaCD US BIOS)", True),
        Firmware("bios_CD_J.bin", "bios_CD_J.bin (MegaCD JP BIOS)", True),
    ),
    # genesis_plus_gx (12 files)
    "segaCD": (
        Firmware("bios_MD.bin", "bios_MD.bin (Mega Drive startup ROM)", True),
        Firmware("bios_CD_E.bin", "bios_CD_E.bin (MegaCD EU BIOS)", True),
        Firmware("bios_CD_U.bin", "bios_CD_U.bin (SegaCD US BIOS)", True),
        Firmware("bios_CD_J.bin", "bios_CD_J.bin (MegaCD JP BIOS)", True),
        Firmware("bios_E.sms", "bios_E.sms (MasterSystem EU BIOS)", True),
        Firmware("bios_U.sms", "bios_U.sms (MasterSystem US BIOS)", True),
        Firmware("bios_J.sms", "bios_J.sms (MasterSystem JP BIOS)", True),
        Firmware("bios.gg", "bios.gg (GameGear BIOS)", True),
        Firmware("sk.bin", "sk.bin (Sonic & Knuckles ROM)", True),
        Firmware("sk2chip.bin", "sk2chip.bin (Sonic & Knuckles UPMEM ROM)", True),
        Firmware("areplay.bin", "areplay.bin (Action Replay ROM)", True),
        Firmware("ggenie.bin", "ggenie.bin (Game Genie ROM)", True),
    ),
    # genesis_plus_gx (12 files)
    "segaGG": (
        Firmware("bios_MD.bin", "bios_MD.bin (Mega Drive startup ROM)", True),
        Firmware("bios_CD_E.bin", "bios_CD_E.bin (MegaCD EU BIOS)", True),
        Firmware("bios_CD_U.bin", "bios_CD_U.bin (SegaCD US BIOS)", True),
        Firmware("bios_CD_J.bin", "bios_CD_J.bin (MegaCD JP BIOS)", True),
        Firmware("bios_E.sms", "bios_E.sms (MasterSystem EU BIOS)", True),
        Firmware("bios_U.sms", "bios_U.sms (MasterSystem US BIOS)", True),
        Firmware("bios_J.sms", "bios_J.sms (MasterSystem JP BIOS)", True),
        Firmware("bios.gg", "bios.gg (GameGear BIOS)", True),
        Firmware("sk.bin", "sk.bin (Sonic & Knuckles ROM)", True),
        Firmware("sk2chip.bin", "sk2chip.bin (Sonic & Knuckles UPMEM ROM)", True),
        Firmware("areplay.bin", "areplay.bin (Action Replay ROM)", True),
        Firmware("ggenie.bin", "ggenie.bin (Game Genie ROM)", True),
    ),
    # genesis_plus_gx (12 files)
    "segaMD": (
        Firmware("bios_MD.bin", "bios_MD.bin (Mega Drive startup ROM)", True),
        Firmware("bios_CD_E.bin", "bios_CD_E.bin (MegaCD EU BIOS)", True),
        Firmware("bios_CD_U.bin", "bios_CD_U.bin (SegaCD US BIOS)", True),
        Firmware("bios_CD_J.bin", "bios_CD_J.bin (MegaCD JP BIOS)", True),
        Firmware("bios_E.sms", "bios_E.sms (MasterSystem EU BIOS)", True),
        Firmware("bios_U.sms", "bios_U.sms (MasterSystem US BIOS)", True),
        Firmware("bios_J.sms", "bios_J.sms (MasterSystem JP BIOS)", True),
        Firmware("bios.gg", "bios.gg (GameGear BIOS)", True),
        Firmware("sk.bin", "sk.bin (Sonic & Knuckles ROM)", True),
        Firmware("sk2chip.bin", "sk2chip.bin (Sonic & Knuckles UPMEM ROM)", True),
        Firmware("areplay.bin", "areplay.bin (Action Replay ROM)", True),
        Firmware("ggenie.bin", "ggenie.bin (Game Genie ROM)", True),
    ),
    # smsplus (2 files)
    "segaMS": (
        Firmware("bios.sms", "bios.sms (Master System BIOS)", True),
        Firmware("BIOS.col", "BIOS.col (Colecovision BIOS)", True),
    ),
    # yabause (1 file)
    "segaSaturn": (
        Firmware("saturn_bios.bin", "saturn_bios.bin (Saturn BIOS)", True),
    ),
    # snes9x (2 files)
    "snes": (
        Firmware("BS-X.bin", "BS-X.bin (BS-X - Sore wa Namae o Nusumareta Machi no Monogatari (Japan) (Rev 1))", True),
        Firmware("STBIOS.bin", "STBIOS.bin (Sufami Turbo (Japan))", True),
    ),
}


def for_core(ejs_core: str) -> tuple[Firmware, ...]:
    """Every firmware file *ejs_core* declares, mandatory or not."""
    return FIRMWARE.get(ejs_core, ())


def required_for_core(ejs_core: str) -> tuple[Firmware, ...]:
    """Only the files without which the core cannot run its content."""
    return tuple(f for f in for_core(ejs_core) if not f.optional)


def known_paths(ejs_core: str) -> frozenset[str]:
    """The paths *ejs_core* accepts, for rejecting an upload named anything else."""
    return frozenset(f.path for f in for_core(ejs_core))
