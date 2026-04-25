/**
 * Mapping from ROM platform fs_slug to EmulatorJS core name.
 * A null value means the platform is not supported by EmulatorJS.
 */
export const EJS_CORES: Record<string, string | null> = {
  // ── Nintendo ──────────────────────────────────────────────────────────────
  nes:          'nes',
  famicom:      'nes',
  fds:          'nes',
  snes:         'snes',
  snesna:       'snes',
  sfc:          'snes',
  satellaview:  'snes',
  n64:          'n64',
  n64dd:        'n64',
  gb:           'gb',
  gbc:          'gb',
  gba:          'gba',
  nds:          'nds',
  virtualboy:   'vb',
  pokemini:     'pokemini',
  // ── Sega ──────────────────────────────────────────────────────────────────
  genesis:      'segaMD',
  megadrive:    'segaMD',
  megadrivejp:  'segaMD',
  segacd:       'segaCD',
  megacd:       'segaCD',
  megacdjp:     'segaCD',
  sega32x:      'sega32x',
  sega32xjp:    'sega32x',
  sega32xna:    'sega32x',
  mastersystem: 'segaMS',
  mark3:        'segaMS',
  gamegear:     'segaGG',
  saturn:       'segaSaturn',
  saturnjp:     'segaSaturn',
  'sg-1000':    'segaMS',
  // ── Sony ──────────────────────────────────────────────────────────────────
  psx:          'psx',
  psp:          'psp',
  // ── Atari ─────────────────────────────────────────────────────────────────
  atari2600:    'atari2600',
  atari5200:    'atari5200',
  atari7800:    'atari7800',
  atarilynx:    'lynx',
  atarijaguar:  'jaguar',
  atarist:      null,          // not supported
  atarixe:      'atari5200',
  atari800:     'atari5200',
  // ── NEC ───────────────────────────────────────────────────────────────────
  pcengine:     'pce',
  tg16:         'pce',
  'tg-cd':      'pce',
  pcenginecd:   'pce',
  // ── SNK ───────────────────────────────────────────────────────────────────
  neogeo:       'mame2003',
  neogeocd:     'mame2003',
  ngp:          'ngp',
  ngpc:         'ngp',
  // ── Bandai ────────────────────────────────────────────────────────────────
  wonderswan:   'ws',
  wonderswancolor: 'ws',
  // ── 3DO ───────────────────────────────────────────────────────────────────
  cdimono1:     null,
  '3do':        '3do',
  // ── Commodore ─────────────────────────────────────────────────────────────
  c64:          'c64',
  amiga:        'amiga',
  amiga1200:    'amiga',
  amiga600:     'amiga',
  amigacd32:    'amiga',
  // ── Arcade ────────────────────────────────────────────────────────────────
  arcade:       'arcade',
  fbneo:        'arcade',
  fba:          'arcade',
  mame:         'mame2003',
  // ── Other ─────────────────────────────────────────────────────────────────
  colecovision: 'coleco',
  channelf:     'o2em',
  intellivision: 'freeintv',
  vectrex:      'vecx',
  // Not supported by EmulatorJS
  gc:           null,
  wii:          null,
  wiiu:         null,
  switch:       null,
  'switch-2':   null,
  ps2:          null,
  ps3:          null,
  ps4:          null,
  psvita:       null,
  n3ds:         null,
  xbox:         null,
  xbox360:      null,
  xboxone:      null,
  dreamcast:    null,
}

/**
 * Get the EmulatorJS core for a given platform fs_slug.
 * Returns null if the platform is not supported.
 */
export function getEjsCore(fsSlug: string): string | null {
  return EJS_CORES[fsSlug] ?? null
}

/**
 * Whether a platform is playable in the browser.
 */
export function isPlayable(fsSlug: string): boolean {
  return getEjsCore(fsSlug) !== null
}
