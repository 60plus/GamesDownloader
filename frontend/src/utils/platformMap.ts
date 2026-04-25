/**
 * Maps ROM platform fs_slug to frontend asset paths.
 *
 * icon     → /platforms/icons/{fs_slug}.png   (controller image)
 * nameLogo → /platforms/names/{fs_slug}.svg   (stylised name logo)
 *
 * Falls back gracefully when assets don't exist.
 */

export interface PlatformAssets {
  icon:     string | null
  nameLogo: string | null
  name:     string
}

/** Known fs_slug → display name (used as fallback if logo is missing) */
const DISPLAY_NAMES: Record<string, string> = {
  nes:          'Nintendo Entertainment System',
  famicom:      'Famicom',
  snes:         'Super Nintendo',
  snesna:       'Super Nintendo',
  sfc:          'Super Famicom',
  n64:          'Nintendo 64',
  n64dd:        'Nintendo 64DD',
  gb:           'Game Boy',
  gbc:          'Game Boy Color',
  gba:          'Game Boy Advance',
  nds:          'Nintendo DS',
  n3ds:         'Nintendo 3DS',
  gc:           'GameCube',
  wii:          'Nintendo Wii',
  wiiu:         'Nintendo Wii U',
  switch:       'Nintendo Switch',
  'switch-2':   'Nintendo Switch 2',
  fds:          'Famicom Disk System',
  virtualboy:   'Virtual Boy',
  mastersystem: 'Sega Master System',
  genesis:      'Sega Genesis',
  megadrive:    'Sega Mega Drive',
  sega32x:      'Sega 32X',
  segacd:       'Sega CD',
  megacd:       'Sega Mega CD',
  saturn:       'Sega Saturn',
  dreamcast:    'Sega Dreamcast',
  gamegear:     'Sega Game Gear',
  'sg-1000':    'Sega SG-1000',
  psx:          'PlayStation',
  ps2:          'PlayStation 2',
  ps3:          'PlayStation 3',
  ps4:          'PlayStation 4',
  ps5:          'PlayStation 5',
  psp:          'PlayStation Portable',
  psvita:       'PlayStation Vita',
  xbox:         'Xbox',
  xbox360:      'Xbox 360',
  xboxone:      'Xbox One',
  'series-x-s': 'Xbox Series X/S',
  neogeo:       'Neo Geo',
  neogeocd:     'Neo Geo CD',
  ngp:          'Neo Geo Pocket',
  ngpc:         'Neo Geo Pocket Color',
  arcade:       'Arcade',
  mame:         'MAME',
  fbneo:        'FinalBurn Neo',
  cps1:         'CPS-1',
  cps2:         'CPS-2',
  dos:          'MS-DOS',
  pc:           'PC',
  scummvm:      'ScummVM',
  atari2600:    'Atari 2600',
  atari5200:    'Atari 5200',
  atari7800:    'Atari 7800',
  atarilynx:    'Atari Lynx',
  atarijaguar:  'Atari Jaguar',
  atari800:     'Atari 800',
  atarist:      'Atari ST',
  c64:          'Commodore 64',
  amiga:        'Amiga',
  amiga1200:    'Amiga 1200',
  amiga600:     'Amiga 600',
  amigacd32:    'Amiga CD32',
  pcengine:     'PC Engine',
  tg16:         'TurboGrafx-16',
  wonderswan:   'WonderSwan',
  wonderswancolor: 'WonderSwan Color',
  colecovision: 'ColecoVision',
  intellivision:'Intellivision',
  '3do':        '3DO',
  zxspectrum:   'ZX Spectrum',
  vectrex:      'Vectrex',
  mark3:        'Sega Mark III',
  naomi:        'Sega NAOMI',
}

/** Override name logo slug when the folder name differs from the preferred logo */
const NAME_LOGO_SLUG: Record<string, string> = {
  sfc:        'snes',
  snesna:     'snes',
  famicom:    'nes',
  megadrive:  'genesis',
  megacdjp:   'megacd',
  saturnjp:   'saturn',
  neogeocdjp: 'neogeocd',
}

/**
 * Return asset paths for a given fs_slug.
 * The caller should handle the case where `icon` or `nameLogo` is null.
 */
export function getPlatformAssets(fsSlug: string | undefined | null): PlatformAssets {
  if (!fsSlug) return { icon: null, nameLogo: null, name: '?' }
  const icon        = `/platforms/icons/${fsSlug}.png`
  const logoSlug    = NAME_LOGO_SLUG[fsSlug] ?? fsSlug
  const nameLogo    = `/platforms/names/${logoSlug}.svg`
  const name        = DISPLAY_NAMES[fsSlug] ?? fsSlug.toUpperCase()

  return { icon, nameLogo, name }
}
