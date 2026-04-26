<template>
  <div class="home-view">

    <!-- ══ Global search results (only when navbar query is active) ════════ -->
    <template v-if="searchActive">
      <section class="home-search-section">
        <div class="home-section-head">
          <span class="home-section-title">{{ t('home.search_results_for', { q: searchQuery }) }}</span>
          <span class="home-section-count">
            {{ searchLoading ? t('common.loading') : t('home.search_total', { count: searchTotal }) }}
          </span>
        </div>

        <!-- Empty results -->
        <div
          v-if="!searchLoading && searchTotal === 0"
          class="home-search-empty"
        >
          <p>{{ t('home.search_no_results', { q: searchQuery }) }}</p>
        </div>

        <!-- Emulation hits -->
        <div v-if="searchResults.emulation.length" class="home-search-group">
          <div class="home-search-group-head">
            <button class="home-section-title home-section-link" @click="router.push('/emulation')">
              {{ t('home.search_emulation', { count: searchResults.emulation.length }) }}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <div class="home-recent-scroll">
            <div
              v-for="rom in searchResults.emulation"
              :key="'emu-' + rom.id"
              class="emu-recent-item"
              @click="openEmuRom(rom as any)"
            >
              <div class="emu-recent-img-wrap" :style="{ aspectRatio: searchRomAspect(rom) }">
                <img v-if="rom.cover_path" :src="rom.cover_path" :alt="rom.name" class="home-recent-img" loading="lazy" />
                <div v-else class="home-recent-fallback emu-recent-fallback">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.3">
                    <rect x="2" y="6" width="20" height="14" rx="2"/>
                    <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
                    <path d="M6 10h4M8 8v4M14 11h4"/>
                  </svg>
                </div>
                <div class="home-recent-overlay"><span class="home-recent-overlay-title">{{ rom.name }}</span></div>
              </div>
              <div class="emu-recent-platform">
                <img
                  v-if="rom.platform_fs_slug"
                  :src="`/platforms/names/${rom.platform_fs_slug}.svg`"
                  :alt="rom.platform_name || ''"
                  class="emu-recent-platform-logo"
                  @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLImageElement).nextElementSibling?.removeAttribute('style')"
                />
                <span class="emu-recent-platform-text" :style="rom.platform_fs_slug ? 'display:none' : ''">
                  {{ rom.platform_name || '' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- GOG hits (admin only) -->
        <div v-if="searchResults.gog.length" class="home-search-group">
          <div class="home-search-group-head">
            <button class="home-section-title home-section-link" @click="router.push('/library')">
              {{ t('home.search_gog', { count: searchResults.gog.length }) }}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <div class="home-recent-scroll">
            <div v-for="game in searchResults.gog" :key="'gog-' + game.id" class="home-recent-cover" @click="openGogGame(game as any)">
              <div class="home-recent-img-wrap">
                <img v-if="gogCoverSrc(game as any)" :src="gogCoverSrc(game as any)" :alt="game.title" class="home-recent-img" loading="lazy" />
                <div v-else class="home-recent-fallback" />
                <div class="home-recent-overlay"><span class="home-recent-overlay-title">{{ game.title }}</span></div>
              </div>
              <div class="home-recent-title">{{ game.title }}</div>
            </div>
          </div>
        </div>

        <!-- Library hits -->
        <div v-if="searchResults.library.length" class="home-search-group">
          <div class="home-search-group-head">
            <button class="home-section-title home-section-link" @click="router.push('/games')">
              {{ t('home.search_games', { count: searchResults.library.length }) }}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <div class="home-recent-scroll">
            <div v-for="game in searchResults.library" :key="'lib-' + game.id" class="home-recent-cover" @click="openGame(game as any)">
              <div class="home-recent-img-wrap">
                <img v-if="game.cover_path" :src="game.cover_path" :alt="game.title" class="home-recent-img" loading="lazy" />
                <div v-else class="home-recent-fallback" />
                <div class="home-recent-overlay"><span class="home-recent-overlay-title">{{ game.title }}</span></div>
              </div>
              <div class="home-recent-title">{{ game.title }}</div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- ── Library cards ──────────────────────────────────────────────────── -->
    <section v-show="!searchActive" class="home-libs">
      <div class="home-section-head">
        <span class="home-section-title">{{ t('home.your_libraries') }}</span>
        <span class="home-section-count">{{ t('home.games_total', { count: totalGames }) }}</span>
      </div>
      <div class="home-lib-cards">

        <!-- GOG Library (admin only) -->
        <div v-if="isAdmin" class="home-lib-card" @click="router.push('/library')">
          <!-- Left: big cover -->
          <div class="home-lib-card-cover">
            <img v-if="gogLib.firstCover" :src="gogLib.firstCover" class="home-lib-card-cover-img" />
            <div v-else class="home-lib-card-cover-empty">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.25">
                <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
              </svg>
            </div>
            <div class="home-lib-card-cover-overlay" />
            <div class="home-lib-card-info">
              <div class="home-lib-card-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
                </svg>
              </div>
              <span class="home-lib-card-name">{{ t('home.gog_library') }}</span>
              <span class="home-lib-card-count">{{ gogLib.count === 1 ? t('home.game_count', { count: gogLib.count }) : t('home.game_count_plural', { count: gogLib.count }) }}</span>
            </div>
          </div>
          <!-- Right: hero art (background_path) with Ken Burns -->
          <div class="home-lib-card-hero">
            <img v-if="gogLib.firstHero" :src="gogLib.firstHero"
                 :class="['home-lib-hero-bg', heroAnimClass]"
                 :style="heroStyle(0)" />
            <div class="home-lib-hero-overlay" />
            <div class="home-lib-hero-fade" />
          </div>
        </div>

        <!-- Games Library -->
        <div class="home-lib-card" @click="router.push('/games')">
          <!-- Left: big cover -->
          <div class="home-lib-card-cover">
            <img v-if="customLib.firstCover" :src="customLib.firstCover" class="home-lib-card-cover-img" />
            <div v-else class="home-lib-card-cover-empty">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.25">
                <rect x="2" y="7" width="20" height="15" rx="2"/>
                <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
              </svg>
            </div>
            <div class="home-lib-card-cover-overlay" />
            <div class="home-lib-card-info">
              <div class="home-lib-card-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="7" width="20" height="15" rx="2"/>
                  <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
                  <line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/>
                </svg>
              </div>
              <span class="home-lib-card-name">{{ t('home.games_library') }}</span>
              <span class="home-lib-card-count">{{ customLib.count === 1 ? t('home.game_count', { count: customLib.count }) : t('home.game_count_plural', { count: customLib.count }) }}</span>
            </div>
          </div>
          <!-- Right: hero art (background_path) with Ken Burns -->
          <div class="home-lib-card-hero">
            <img v-if="customLib.firstHero" :src="customLib.firstHero"
                 :class="['home-lib-hero-bg', heroAnimClass]"
                 :style="heroStyle(-15)" />
            <div class="home-lib-hero-overlay" />
            <div class="home-lib-hero-fade" />
          </div>
        </div>

        <!-- Emulation Library -->
        <div class="home-lib-card" @click="router.push('/emulation')">
          <div class="home-lib-card-cover">
            <img v-if="emulationLib.platformFsSlug" :src="`/platforms/icons/${emulationLib.platformFsSlug}.png`" class="home-lib-card-cover-img home-lib-card-cover-img--icon" />
            <div v-else class="home-lib-card-cover-empty">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.25">
                <rect x="2" y="6" width="20" height="14" rx="2"/>
                <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
                <path d="M6 10h4M8 8v4M14 11h4"/>
              </svg>
            </div>
            <div class="home-lib-card-cover-overlay" />
            <div class="home-lib-card-info">
              <div class="home-lib-card-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="6" width="20" height="14" rx="2"/>
                  <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
                  <path d="M6 10h4M8 8v4M14 11h4"/>
                </svg>
              </div>
              <span class="home-lib-card-name">{{ t('home.emulation_library') }}</span>
              <span class="home-lib-card-count">
                {{ emulationLib.totalRoms === 1 ? t('home.rom_count', { count: emulationLib.totalRoms }) : t('home.rom_count_plural', { count: emulationLib.totalRoms }) }}
                <span v-if="emulationLib.platformCount"> · {{ emulationLib.platformCount === 1 ? t('home.platform_count', { count: emulationLib.platformCount }) : t('home.platform_count_plural', { count: emulationLib.platformCount }) }}</span>
              </span>
            </div>
          </div>
          <div class="home-lib-card-hero">
            <img v-if="emulationLib.firstHero" :src="emulationLib.firstHero"
                 :class="['home-lib-hero-bg', heroAnimClass]"
                 :style="heroStyle(-30)" />
            <div v-else class="home-lib-hero-empty" />
            <div class="home-lib-hero-overlay" />
            <div class="home-lib-hero-fade" />
          </div>
        </div>

        <!-- Couch Mode -->
        <div class="home-lib-card home-lib-card--couch" @click="router.push('/couch')">
          <div class="home-lib-card-cover home-lib-card-cover--couch">
            <div class="home-couch-bg-stars" />
            <div class="home-couch-cover-content">
              <img
                v-if="couchPlatformSlug"
                :src="`/platforms/names/${couchPlatformSlug}.svg`"
                class="home-couch-platform-name"
                @error="($event.target as HTMLImageElement).style.display='none'"
              />
              <img
                v-if="couchPlatformSlug"
                :src="`/platforms/icons/${couchPlatformSlug}.png`"
                class="home-couch-platform-icon"
                @error="($event.target as HTMLImageElement).style.display='none'"
              />
            </div>
            <div class="home-lib-card-cover-overlay" />
            <div class="home-lib-card-info">
              <div class="home-lib-card-icon home-lib-card-icon--couch">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
              </div>
              <span class="home-lib-card-name">{{ t('home.couch_mode') }}</span>
              <span class="home-lib-card-count">{{ t('home.couch_sub') }}</span>
            </div>
          </div>
          <div class="home-lib-card-hero home-lib-card-hero--couch">
            <img
              v-if="couchPlatformSlug"
              :src="`/platforms/fanart/${couchPlatformSlug}.webp`"
              :class="['home-lib-hero-bg', heroAnimClass]"
              :style="heroStyle(-45)"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
            <div class="home-lib-hero-overlay" />
            <div class="home-lib-hero-fade" />
          </div>
        </div>

      </div>
    </section>

    <!-- ── Recently Added rows ────────────────────────────────────────────── -->

    <section v-if="!searchActive && isAdmin && gogLib.recent.length" class="home-recent-section">
      <div class="home-section-head">
        <button class="home-section-title home-section-link" @click="router.push('/library')">
          {{ t('home.recently_added_gog') }}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="home-row-nav">
          <button class="home-nav-btn" @click="scrollRow('gog', 'left')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg></button>
          <button class="home-nav-btn" @click="scrollRow('gog', 'right')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
      </div>
      <div class="home-recent-scroll" :ref="(el: any) => { if (el) rowRefs['gog'] = el }">
        <div v-for="game in gogLib.recent" :key="game.id" class="home-recent-cover" @click="openGogGame(game)">
          <div class="home-recent-img-wrap">
            <img v-if="gogCoverSrc(game)" :src="gogCoverSrc(game)" :alt="game.title" class="home-recent-img" loading="lazy" />
            <div v-else class="home-recent-fallback" />
            <div class="home-recent-overlay"><span class="home-recent-overlay-title">{{ game.title }}</span></div>
          </div>
          <div class="home-recent-title">{{ game.title }}</div>
        </div>
      </div>
    </section>

    <section v-if="!searchActive && customLib.recent.length" class="home-recent-section">
      <div class="home-section-head">
        <button class="home-section-title home-section-link" @click="router.push('/games')">
          {{ t('home.recently_added_games') }}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="home-row-nav">
          <button class="home-nav-btn" @click="scrollRow('custom', 'left')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg></button>
          <button class="home-nav-btn" @click="scrollRow('custom', 'right')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
      </div>
      <div class="home-recent-scroll" :ref="(el: any) => { if (el) rowRefs['custom'] = el }">
        <div v-for="game in customLib.recent" :key="game.id" class="home-recent-cover" @click="openGame(game)">
          <div class="home-recent-img-wrap">
            <img v-if="game.cover_path" :src="game.cover_path" :alt="game.title" class="home-recent-img" loading="lazy" />
            <div v-else class="home-recent-fallback" />
            <div class="home-recent-overlay"><span class="home-recent-overlay-title">{{ game.title }}</span></div>
          </div>
          <div class="home-recent-title">{{ game.title }}</div>
        </div>
      </div>
    </section>

    <!-- ── Recently Added - Emulation Library ────────────────────────────── -->
    <section v-if="!searchActive && emuRecent.length" class="home-recent-section">
      <div class="home-section-head">
        <button class="home-section-title home-section-link" @click="router.push('/emulation')">
          {{ t('home.recently_added_emu') }}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="home-row-nav">
          <button class="home-nav-btn" @click="scrollRow('emu', 'left')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg></button>
          <button class="home-nav-btn" @click="scrollRow('emu', 'right')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
      </div>
      <div class="home-recent-scroll" :ref="(el: any) => { if (el) rowRefs['emu'] = el }">
        <div
          v-for="rom in emuRecent"
          :key="rom.id"
          class="emu-recent-item"
          @click="openEmuRom(rom)"
        >
          <!-- Cover - natural aspect ratio per platform -->
          <div class="emu-recent-img-wrap" :style="{ aspectRatio: romAspect(rom) }">
            <img v-if="rom.cover_path" :src="rom.cover_path" :alt="rom.name" class="home-recent-img" loading="lazy" />
            <div v-else class="home-recent-fallback emu-recent-fallback">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.3">
                <rect x="2" y="6" width="20" height="14" rx="2"/>
                <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
                <path d="M6 10h4M8 8v4M14 11h4"/>
              </svg>
            </div>
            <div class="home-recent-overlay">
              <span class="home-recent-overlay-title">{{ rom.name }}</span>
            </div>
          </div>
          <!-- Platform name logo (or text fallback) -->
          <div class="emu-recent-platform">
            <img
              v-if="rom.platform_fs_slug"
              :src="`/platforms/names/${rom.platform_fs_slug}.svg`"
              :alt="rom.platform_name || ''"
              class="emu-recent-platform-logo"
              @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLImageElement).nextElementSibling?.removeAttribute('style')"
            />
            <span class="emu-recent-platform-text" :style="rom.platform_fs_slug ? 'display:none' : ''">
              {{ rom.platform_name || '' }}
            </span>
          </div>
        </div>
      </div>
    </section>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, type CSSProperties } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface LibGame  { id: number; title: string; slug: string; source: string; cover_path: string | null; background_path: string | null }
interface GogGame  { id: number; title: string; slug: string; cover_path: string | null; cover_url: string | null; background_path: string | null }
interface EmuRom   {
  id: number; name: string
  cover_path: string | null; cover_type: string | null; cover_aspect: string | null
  platform_slug: string | null; platform_fs_slug: string | null
  platform_name: string | null; platform_cover_aspect: string
}

// Same suffix-stripping regex as GogLibrary - cleans up deprecated GOG CDN formatters
const _GOG_SUFFIX_RE = /(_product_card|_logo2x?|_icon|_square_icon|_196|_200|_bg_crop_\d+x\d+)(\.\w+)?$/i
function gogCoverSrc(game: GogGame): string {
  if (game.cover_path) return game.cover_path
  const url = game.cover_url || ''
  if (!url) return ''
  const fixed = url.replace(_GOG_SUFFIX_RE, '')
  if (!/\.\w{2,5}(\?|$)/.test(fixed)) return fixed + '.jpg'
  return fixed
}

const router     = useRouter()
const route      = useRoute()
const auth       = useAuthStore()
const themeStore = useThemeStore()

// Animation class - same logic as GamesGameDetail hero
const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `home-lib-hero-bg--${themeStore.heroAnimStyle}`
})

// Per-card hero inline styles - stagger animation phase + reactive blur.
// Negative delay = card appears to be mid-animation from the start (no initial pause).
// Offsets are ~1/3 of the longest animation cycle (kenburns = 44 s → ~15 s apart).
function heroStyle(delayS: number): CSSProperties {
  return {
    '--gd-hero-blur': `${themeStore.heroBlur ?? 14}px`,
    animationDelay: `${delayS}s`,
  } as CSSProperties
}
const rowRefs  = ref<Record<string, HTMLElement>>({})

const libGames  = ref<LibGame[]>([])   // /library/games  (custom/shared)
const gogGames  = ref<GogGame[]>([])   // /gog/library/games
const emuRecent = ref<EmuRom[]>([])    // /roms/recent

const isAdmin    = computed(() => auth.user?.role === 'admin')
const totalGames = computed(() => libGames.value.length + gogGames.value.length)

// ── Build lib data ────────────────────────────────────────────────────────────

function buildLib<T extends { id: number; cover_path?: string | null; cover_url?: string | null; background_path?: string | null }>(games: T[]) {
  // Pick one game that has a cover - hero comes from the SAME game
  const withCover = games.filter(g => g.cover_path)
  const shuffled  = [...withCover].sort(() => Math.random() - 0.5)
  const picked    = shuffled[0] ?? null

  const firstCover = picked?.cover_path ?? null
  // Hero: background_path of the same game; fall back to its cover if no background
  const firstHero  = picked ? (picked.background_path ?? picked.cover_path ?? null) : null

  return {
    count: games.length,
    firstCover,
    firstHero,
    recent: [...games].sort((a, b) => b.id - a.id).slice(0, 24) as (T & { title: string })[],
  }
}

const gogLib    = computed(() => buildLib(gogGames.value))
const customLib = computed(() => buildLib(libGames.value))

// ── Emulation Library ─────────────────────────────────────────────────────────

const emulationLib = ref({
  totalRoms:     0,
  platformCount: 0,
  platformFsSlug: null as string | null,   // for /platforms/icons/{fs_slug}.png
  firstHero:     null as string | null,
})

async function fetchEmulationSummary() {
  try {
    const [summaryRes, recentRes] = await Promise.allSettled([
      client.get('/roms/summary'),
      client.get('/roms/recent', { params: { limit: 24 } }),
    ])
    if (summaryRes.status === 'fulfilled') {
      const data = summaryRes.value.data
      emulationLib.value = {
        totalRoms:      data.total_roms      ?? 0,
        platformCount:  data.platform_count  ?? 0,
        platformFsSlug: data.sample_fs_slug  ?? null,
        firstHero:      data.sample_hero     ?? null,
      }
    }
    if (recentRes.status === 'fulfilled') {
      emuRecent.value = recentRes.value.data as EmuRom[]
    }
  } catch {
    // Emulation not set up yet - silently ignore
  }
}

// Random platform slug for Couch Mode card (from available emu platforms)
const couchPlatformSlug = computed(() => {
  // Prefer a random platform from recent ROMs, fallback to summary sample
  const slugs = [...new Set(emuRecent.value.map(r => r.platform_fs_slug).filter(Boolean))]
  if (slugs.length) return slugs[Math.floor(Math.random() * slugs.length)]
  return emulationLib.value.platformFsSlug
})

/** Determine aspect-ratio string for a ROM cover. */
function romAspect(rom: EmuRom): string {
  if (rom.cover_type === 'box-3D') return '16/9'
  return rom.cover_aspect || rom.platform_cover_aspect || '3/4'
}

// ── Fetch ────────────────────────────────────────────────────────────────────

async function fetchAll() {
  // All in parallel
  fetchEmulationSummary()
  const [libRes, gogRes] = await Promise.allSettled([
    client.get('/library/games', { params: { limit: '500' } }),
    isAdmin.value ? client.get('/gog/library/games') : Promise.resolve({ data: [] }),
  ])
  if (libRes.status === 'fulfilled') {
    libGames.value = (libRes.value.data.items as any[]).map((g: any) => ({
      id: g.id, title: g.title, slug: g.slug,
      source: g.source,
      cover_path:      g.cover_path      ?? null,
      background_path: g.background_path ?? null,
    }))
  }
  if (gogRes.status === 'fulfilled') {
    const raw = gogRes.value.data
    gogGames.value = (Array.isArray(raw) ? raw : raw.items ?? []).map((g: any) => ({
      id: g.id, title: g.title, slug: g.slug,
      cover_path:      g.cover_path      ?? null,
      cover_url:       g.cover_url       ?? null,
      background_path: g.background_path ?? null,
    }))
  }
}

// ── Navigation ───────────────────────────────────────────────────────────────

function openGame(game: LibGame) {
  router.push({ name: 'games-detail', params: { id: game.id } })
}
function openGogGame(game: GogGame) {
  router.push({ name: 'game-detail', params: { id: game.id } })
}
function openEmuRom(rom: EmuRom) {
  if (rom.platform_slug)
    router.push({ name: 'emulation-detail', params: { platform: rom.platform_slug, id: rom.id } })
}

function scrollRow(key: string, dir: 'left' | 'right') {
  const el = rowRefs.value[key]
  if (el) el.scrollBy({ left: dir === 'right' ? 420 : -420, behavior: 'smooth' })
}

// ── Global search ─────────────────────────────────────────────────────────────
// Driven by the navbar input - the layout component writes the active query
// into route.query.q. We mirror it here, debounce, and call /api/search/global
// which returns three buckets (emulation / gog / library). When a query is
// active the normal "Recently Added" rows are hidden so the search results
// take over the whole view.
const searchQuery = computed(() => {
  const q = route.query.q
  return (Array.isArray(q) ? q[0] : q) || ''
})
const searchActive = computed(() => searchQuery.value.trim().length >= 2)

interface SearchResults {
  emulation: Array<{
    id: number; name: string; cover_path: string | null;
    cover_type: string | null; cover_aspect: string | null;
    platform_slug: string | null; platform_fs_slug: string | null;
    platform_name: string | null; platform_cover_aspect: string;
  }>
  gog:     Array<{ id: number; title: string; slug: string; cover_path: string | null; cover_url: string | null }>
  library: Array<{ id: number; title: string; slug: string; cover_path: string | null }>
}

const searchResults = ref<SearchResults>({ emulation: [], gog: [], library: [] })
const searchLoading = ref(false)
const searchTotal   = computed(() =>
  searchResults.value.emulation.length +
  searchResults.value.gog.length +
  searchResults.value.library.length,
)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchAbort:  AbortController | null = null

function searchRomAspect(rom: SearchResults['emulation'][number]): string {
  if (rom.cover_type === 'box-3D') return '16/9'
  return rom.cover_aspect || rom.platform_cover_aspect || '3/4'
}

async function runSearch(q: string) {
  if (searchAbort) searchAbort.abort()
  searchAbort = new AbortController()
  searchLoading.value = true
  try {
    const { data } = await client.get('/search/global', {
      params: { q, limit: 50 },
      signal: searchAbort.signal,
    })
    searchResults.value = {
      emulation: data.emulation ?? [],
      gog:       data.gog       ?? [],
      library:   data.library   ?? [],
    }
  } catch (e: any) {
    if (e?.name === 'CanceledError' || e?.name === 'AbortError') return
    searchResults.value = { emulation: [], gog: [], library: [] }
  } finally {
    searchLoading.value = false
  }
}

watch(searchQuery, (q) => {
  if (searchTimer) clearTimeout(searchTimer)
  const trimmed = q.trim()
  if (trimmed.length < 2) {
    searchResults.value = { emulation: [], gog: [], library: [] }
    searchLoading.value = false
    if (searchAbort) searchAbort.abort()
    return
  }
  searchTimer = setTimeout(() => runSearch(trimmed), 280)
}, { immediate: true })

onMounted(fetchAll)
</script>

<style scoped>
/* ── Layout ────────────────────────────────────────────────────────────────── */
.home-view {
  padding: 28px 28px 48px;
  display: flex; flex-direction: column; gap: var(--space-10, 40px);
  min-height: 100%;
}
.home-admin-row { display: flex; align-items: center; gap: 10px; }
.home-section-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 18px;
}
.home-section-title { font-size: 19px; font-weight: 700; color: var(--text); }
.home-section-link {
  display: inline-flex; align-items: center; gap: 5px;
  cursor: pointer; background: none; border: none; font-family: inherit;
  padding: 0; transition: color var(--transition);
}
.home-section-link:hover { color: var(--pl); }
.home-section-count { font-size: var(--fs-sm, 12px); color: var(--muted); }

/* ── Library cards ─────────────────────────────────────────────────────────── */
.home-lib-cards { display: flex; flex-wrap: wrap; gap: var(--space-5, 20px); }

.home-lib-card {
  display: flex;
  width: 550px;
  height: 248px;
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,.08);
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
  flex-shrink: 0;
}
.home-lib-card:hover {
  transform: scale(1.016) translateY(-3px);
  box-shadow: 0 20px 64px rgba(0,0,0,.7);
  border-color: color-mix(in srgb, var(--pl) 55%, transparent);
}

/* ── Left cover ──────────────────────────────────────────────────────────── */
.home-lib-card-cover {
  width: 175px;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
  background: rgba(0,0,0,.4);
}
.home-lib-card-cover-img {
  width: 100%; height: 100%; object-fit: cover;
  display: block;
  transition: transform .4s ease;
}
.home-lib-card:hover .home-lib-card-cover-img { transform: scale(1.06); }
/* Platform icon (square PNG) - center it, don't stretch */
.home-lib-card-cover-img--icon {
  object-fit: contain;
  padding: 18px;
  background: rgba(0,0,0,.35);
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.6));
}
.home-lib-card-cover-empty {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--pl) 6%, transparent);
}

/* Dark gradient overlay at bottom of cover */
.home-lib-card-cover-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(
    to bottom,
    transparent 30%,
    color-mix(in srgb, var(--bg) 70%, transparent) 60%,
    color-mix(in srgb, var(--bg) 95%, transparent) 100%
  );
}

/* Info overlaid on cover bottom */
.home-lib-card-info {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 14px 14px 14px;
  display: flex; flex-direction: column; gap: 5px;
  z-index: 2;
}
.home-lib-card-icon {
  width: 28px; height: 28px; border-radius: 7px;
  background: color-mix(in srgb, var(--pl) 25%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light, #a78bfa);
  margin-bottom: 2px;
}
.home-lib-card-name {
  font-size: 15px; font-weight: 700; color: #fff;
  line-height: 1.2; text-shadow: 0 1px 6px rgba(0,0,0,.7);
}
.home-lib-card-count {
  font-size: 11px; font-weight: 500;
  background: rgba(255,255,255,.15); color: rgba(255,255,255,.85);
  padding: 2px 9px; border-radius: 20px;
  display: inline-block; width: fit-content;
  backdrop-filter: blur(4px);
}

/* ── Right hero - Ken Burns animated bg (same cover as left) ───────────────── */
.home-lib-card-hero {
  flex: 1; overflow: hidden; position: relative; background: var(--bg, #080414);
}

/* Cover art - SAME filter variables as GamesGameDetail .gd-hero-bg */
.home-lib-hero-bg {
  position: absolute;
  width: calc(100% + 40px); height: calc(100% + 40px);
  top: -20px; left: -20px;
  object-fit: cover;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(120%) brightness(.48);
  transform-origin: center center;
  transform: scale(1.06);
  z-index: 0;
  pointer-events: none;
  will-change: transform;
}
.home-lib-card:hover .home-lib-hero-bg { animation-play-state: paused; }

/* Animation classes - same durations / keyframes as game detail */
.home-lib-hero-bg--kenburns {
  animation: home-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.home-lib-hero-bg--drift {
  animation: home-drift calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate;
}
.home-lib-hero-bg--pulse {
  animation: home-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}

@keyframes home-kenburns {
  0%   { transform: scale(1.06) translateX(0%);  }
  50%  { transform: scale(1.13) translateX(-3%); }
  100% { transform: scale(1.06) translateX(0%);  }
}
@keyframes home-drift {
  0%   { transform: scale(1.1) translateX(0%);  }
  50%  { transform: scale(1.1) translateX(-5%); }
  100% { transform: scale(1.1) translateX(0%);  }
}
@keyframes home-pulse {
  0%   { transform: scale(1.04); }
  50%  { transform: scale(1.11); }
  100% { transform: scale(1.04); }
}

/* CSS-level animation disable - mirrors [data-animations="false"] guard in game detail views */
[data-animations="false"] .home-lib-hero-bg--kenburns,
[data-animations="false"] .home-lib-hero-bg--drift,
[data-animations="false"] .home-lib-hero-bg--pulse { animation: none; }

/* Skin-colour glow + dark bottom — March 30 style */
.home-lib-hero-overlay {
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse at 70% 40%, color-mix(in srgb, var(--pl) 22%, transparent) 0%, transparent 65%),
    linear-gradient(to bottom, rgba(0,0,0,.1) 0%, rgba(0,0,0,.35) 100%);
  z-index: 1;
  pointer-events: none;
}

/* Fade from cover panel into hero - seamless continuation */
.home-lib-hero-fade {
  position: absolute; top: 0; left: 0; width: 80px; height: 100%;
  background: linear-gradient(to right, var(--bg, #080414) 0%, color-mix(in srgb, var(--bg) 40%, transparent) 60%, transparent 100%);
  pointer-events: none; z-index: 2;
}

/* ── Recently Added rows ───────────────────────────────────────────────────── */
.home-recent-section { display: flex; flex-direction: column; }
.home-row-nav { display: flex; gap: 6px; }
.home-nav-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 7px;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: var(--text); cursor: pointer; transition: background var(--transition);
}
.home-nav-btn:hover { background: rgba(255,255,255,.14); }

.home-recent-scroll {
  display: flex; gap: var(--space-3, 12px); overflow-x: auto; padding-bottom: 8px;
  scroll-behavior: smooth; scrollbar-width: none;
}
.home-recent-scroll::-webkit-scrollbar { display: none; }

.home-recent-cover { flex: 0 0 auto; width: 128px; cursor: pointer; }
.home-recent-img-wrap {
  width: 128px; height: 182px; border-radius: var(--radius-sm, 8px); overflow: hidden;
  position: relative; background: rgba(255,255,255,.05);
  transition: box-shadow .2s, transform .2s;
}
.home-recent-cover:hover .home-recent-img-wrap {
  box-shadow: 0 8px 28px rgba(0,0,0,.6); transform: translateY(-2px);
}
.home-recent-img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s; }
.home-recent-cover:hover .home-recent-img { transform: scale(1.06); }
.home-recent-fallback { width: 100%; height: 100%; background: rgba(255,255,255,.04); }
.home-recent-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, transparent 50%);
  display: flex; align-items: flex-end; padding: var(--space-2, 8px);
  opacity: 0; transition: opacity .2s;
}
.home-recent-cover:hover .home-recent-overlay { opacity: 1; }
.home-recent-overlay-title {
  font-size: var(--fs-xs, 10px); font-weight: 600; color: #fff; line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.home-recent-title {
  font-size: 11px; color: var(--muted); margin-top: 6px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── Emulation recently added ──────────────────────────────────────────────── */
.emu-recent-item {
  flex: 0 0 auto;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Cover - width is fixed, height adapts to aspect-ratio */
.emu-recent-img-wrap {
  width: 120px;
  /* aspect-ratio set via inline style per ROM */
  border-radius: var(--radius-sm, 8px);
  overflow: hidden;
  position: relative;
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: 0 4px 14px rgba(0,0,0,.45);
  transition: box-shadow .2s, transform .2s;
}
.emu-recent-item:hover .emu-recent-img-wrap {
  box-shadow: 0 8px 28px rgba(0,0,0,.6);
  transform: translateY(-2px);
}
.emu-recent-fallback {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%;
}

/* Platform name logo row */
.emu-recent-platform {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 18px;
}
.emu-recent-platform-logo {
  max-width: 100%;
  max-height: 16px;
  object-fit: contain;
  filter: brightness(0.75);
}
.emu-recent-platform-text {
  font-size: var(--fs-xs, 10px);
  color: var(--muted);
  font-weight: 600;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

/* ── Global search results (Home navbar driven) ───────────────────────────── */
.home-search-section {
  display: flex; flex-direction: column; gap: var(--space-7, 28px);
}
.home-search-empty {
  padding: 40px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  text-align: center;
  color: var(--muted);
  font-size: var(--fs-md, 14px);
}
.home-search-group { display: flex; flex-direction: column; }
.home-search-group-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 12px;
}

/* ── Couch Mode card ───────────────────────────────────────────────────────── */
.home-lib-card--couch {
  border-color: color-mix(in srgb, var(--pl) 18%, transparent);
}
.home-lib-card--couch:hover {
  border-color: color-mix(in srgb, var(--pl) 65%, transparent);
  box-shadow: 0 20px 64px color-mix(in srgb, var(--pl) 25%, transparent);
}

/* Cover side - dark with stars */
.home-lib-card-cover--couch {
  background: var(--bg, #060410);
  overflow: hidden;
}
.home-couch-bg-stars {
  position: absolute; inset: 0; pointer-events: none;
  background-image:
    radial-gradient(1px 1px at 15% 25%, rgba(255,255,255,.55) 0, transparent 0),
    radial-gradient(1px 1px at 40% 60%, rgba(255,255,255,.35) 0, transparent 0),
    radial-gradient(1.5px 1.5px at 70% 20%, rgba(255,255,255,.5) 0, transparent 0),
    radial-gradient(1px 1px at 80% 75%, rgba(255,255,255,.3) 0, transparent 0),
    radial-gradient(1px 1px at 55% 45%, rgba(255,255,255,.4) 0, transparent 0),
    radial-gradient(1px 1px at 25% 80%, rgba(255,255,255,.45) 0, transparent 0);
  background-size: 120px 120px;
  animation: home-couch-stars 20s linear infinite;
}
@keyframes home-couch-stars {
  to { background-position: 120px 120px; }
}
.home-couch-cover-content {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-2, 8px); z-index: 1; padding: var(--space-4, 16px);
}
.home-couch-platform-name {
  max-width: 80%; max-height: 24px; object-fit: contain;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,.6)) brightness(1.2);
}
.home-couch-platform-icon {
  max-width: 70%; max-height: 50%; object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.5));
}
@keyframes home-couch-pulse {
  0%, 100% { opacity: .6; filter: drop-shadow(0 0 14px color-mix(in srgb, var(--pl) 40%, transparent)); }
  50%       { opacity: .9; filter: drop-shadow(0 0 28px color-mix(in srgb, var(--pl) 70%, transparent)); }
}

.home-lib-card-icon--couch {
  background: color-mix(in srgb, var(--pl) 25%, transparent);
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light, #a78bfa);
}

/* Hero side */
.home-lib-card-hero--couch {
  background: linear-gradient(135deg,
    var(--bg, #0a0418) 0%,
    var(--bg2, #150830) 50%,
    var(--bg3, #0c0520) 100%);
  position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
.home-couch-hero-stars {
  position: absolute; inset: 0; pointer-events: none;
  background-image:
    radial-gradient(1px 1px at 8%  15%, rgba(255,255,255,.5) 0, transparent 0),
    radial-gradient(1px 1px at 35% 70%, rgba(255,255,255,.3) 0, transparent 0),
    radial-gradient(1.5px 1.5px at 65% 30%, rgba(255,255,255,.45) 0, transparent 0),
    radial-gradient(1px 1px at 88% 55%, rgba(255,255,255,.35) 0, transparent 0),
    radial-gradient(1px 1px at 50% 85%, rgba(255,255,255,.4) 0, transparent 0),
    radial-gradient(1px 1px at 20% 45%, rgba(255,255,255,.3) 0, transparent 0),
    radial-gradient(1px 1px at 75% 90%, rgba(255,255,255,.25) 0, transparent 0),
    radial-gradient(1px 1px at 92% 10%, rgba(255,255,255,.5) 0, transparent 0);
  background-size: 200px 200px;
  animation: home-couch-stars 30s linear infinite;
  opacity: .7;
}
.home-lib-hero-overlay--couch {
  background:
    radial-gradient(ellipse at 70% 40%, color-mix(in srgb, var(--pl) 30%, transparent) 0%, transparent 65%),
    linear-gradient(to bottom, rgba(0,0,0,.1) 0%, rgba(0,0,0,.3) 100%);
}

</style>
