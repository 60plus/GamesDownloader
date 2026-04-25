<template>
  <div class="cgl-root" :class="[`cgl-theme--${theme}`, `cgl-view--${view}`]" :style="rootStyle">

    <!-- ══ FULL-BLEED BACKGROUND ══ -->
    <Transition name="cgl-bg">
      <div :key="bgKey" class="cgl-bg-layer">
        <video
          v-if="bgVideo && !videoErr"
          ref="bgVideoEl"
          :src="bgVideo"
          class="cgl-bg-video"
          autoplay muted loop playsinline
          @error="videoErr = true"
          @loadeddata="applyVideoVol"
        />
        <div
          v-else-if="bgImg"
          class="cgl-bg-img"
          :style="{ backgroundImage: `url(${bgImg})` }"
        />
      </div>
    </Transition>
    <!-- Theme-specific bg treatments -->
    <div class="cgl-bg-overlay" />
    <div v-if="theme === 'noir'" class="cgl-noir-grain" />
    <div v-if="theme === 'slick'" class="cgl-slick-lines" />

    <!-- ══ TOP BAR ══ -->
    <div class="cgl-topbar">
      <button class="cgl-back" @click="$emit('back')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        {{ t('couch.systems') }}
      </button>

      <div class="cgl-plat">
        <!-- Platform name logo - /platforms/names/{fs_slug}.svg like gd-pill-name-logo -->
        <div class="cgl-plat-pill">
          <img
            :src="`/platforms/names/${platform.fs_slug}.svg`"
            class="cgl-plat-wheel"
            :alt="platform.name"
            @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLElement).nextElementSibling?.removeAttribute('style')"
          />
          <span class="cgl-plat-name" style="display:none">{{ platform.name }}</span>
        </div>
        <span class="cgl-plat-count">{{ roms.length === 1 ? t('couch.rom_count_1') : t('couch.roms_count', { count: roms.length }) }}</span>
      </div>

      <div class="cgl-topbar-right">
        <!-- Cover size presets (XS/S/M/L/XL) - only meaningful in grid view -->
        <template v-if="view === 'grid'">
          <div class="cgl-sizes">
            <button
              v-for="sz in COVER_SIZES" :key="sz"
              class="cgl-sizebtn" :class="{ active: coverSize === sz }"
              @click="coverSize = sz" :title="sz.toUpperCase()"
            >{{ sz.toUpperCase() }}</button>
          </div>
          <div class="cgl-topbar-sep" />
        </template>
        <button
          class="cgl-viewbtn" :class="{ active: view === 'list' }"
          @click="$emit('setView','list')" title="List">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
            <circle cx="3" cy="6" r="1.2" fill="currentColor"/><circle cx="3" cy="12" r="1.2" fill="currentColor"/><circle cx="3" cy="18" r="1.2" fill="currentColor"/>
          </svg>
        </button>
        <button
          class="cgl-viewbtn" :class="{ active: view === 'grid' }"
          @click="$emit('setView','grid')" title="Grid">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
          </svg>
        </button>
        <span class="cgl-hint"><kbd>↑↓</kbd> {{ t('couch.browse') }} &nbsp;·&nbsp; <kbd>A</kbd> {{ t('couch.launch') }} &nbsp;·&nbsp; <kbd>Start</kbd> / <kbd>M</kbd> {{ t('couch.menu') }} &nbsp;·&nbsp; <kbd>B</kbd> {{ t('couch.back') }}</span>
      </div>
    </div>

    <!-- ══ LOADING ══ -->
    <div v-if="loading" class="cgl-loading">
      <div class="cgl-spinner" />
      <span>{{ t('couch.loading_roms') }}</span>
    </div>

    <!-- ══ LIST VIEW ══ -->
    <div v-else-if="view === 'list'" class="cgl-list-wrap">

      <!-- Left: scrollable game list -->
      <div class="cgl-list" ref="listEl">
        <div
          v-for="(rom, i) in roms"
          :key="rom.id"
          class="cgl-item"
          :class="{ active: i === selIdx }"
          :style="{
            '--item-hero': i === selIdx
              ? `url(${detail?.background_path || rom.background_path || detail?.screenshots?.[0] || rom.cover_path || ''})`
              : (rom.background_path ? `url(${rom.background_path})` : (rom.cover_path ? `url(${rom.cover_path})` : 'none'))
          }"
          :ref="el => { if (i === selIdx) selEl = el as Element | null }"
          @click="onItemClick(i)"
          @dblclick="$emit('launch', rom)"
        >
          <div class="cgl-item-cover" :style="{ aspectRatio: coverAspect(rom) }">
            <img v-if="rom.cover_path" :src="rom.cover_path" :alt="rom.title" loading="lazy" />
            <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".25">
              <rect x="2" y="3" width="20" height="18" rx="2"/>
            </svg>
          </div>
          <div class="cgl-item-text">
            <!-- Wheel / clear logo fills the available space (like cgl-show-wheel) -->
            <img
              v-if="rom.wheel_path"
              :src="rom.wheel_path"
              class="cgl-item-wheel"
              :alt="rom.title"
              @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLElement).nextElementSibling?.removeAttribute('style')"
            />
            <span class="cgl-item-title" :style="rom.wheel_path ? 'display:none' : ''">{{ rom.title }}</span>
            <span v-if="rom.release_year" class="cgl-item-year">{{ rom.release_year }}</span>
          </div>
          <div v-if="i === selIdx" class="cgl-item-bar" />
        </div>
      </div>

      <!-- Right: showcase -->
      <div class="cgl-showcase" v-if="selectedRom">
        <Transition name="cgl-show" mode="out-in">
          <div :key="selectedRom.id" class="cgl-show-inner">

            <!-- Cover -->
            <div class="cgl-show-cover-wrap" :style="{ aspectRatio: coverAspect(selectedRom) }">
              <img
                v-if="selectedRom.cover_path"
                :src="selectedRom.cover_path"
                class="cgl-show-cover"
                :alt="selectedRom.title"
              />
              <div v-else class="cgl-show-cover-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".2"><rect x="2" y="3" width="20" height="18" rx="2"/></svg>
              </div>
            </div>

            <!-- Info column -->
            <div class="cgl-show-info">
              <!-- Wheel/clear logo (same as gd-wheel-logo) or text title fallback -->
              <img
                v-if="selectedRom.wheel_path || detail?.wheel_path"
                :src="(selectedRom.wheel_path || detail?.wheel_path)!"
                class="cgl-show-wheel"
                :alt="selectedRom.title"
                @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLElement).nextElementSibling?.removeAttribute('style')"
              />
              <h2
                class="cgl-show-title"
                :style="(selectedRom.wheel_path || detail?.wheel_path) ? 'display:none' : ''"
              >{{ selectedRom.title }}</h2>

              <!-- Chips row -->
              <div class="cgl-chips">
                <span v-if="selectedRom.release_year" class="cgl-chip">{{ selectedRom.release_year }}</span>
                <span v-for="g in (detail?.genres ?? []).slice(0,3)" :key="g" class="cgl-chip">{{ g }}</span>
                <!-- Developer - show ScreenScraper company logo like gd-meta-company-logo -->
                <span v-if="detail?.developer" class="cgl-chip cgl-chip--dev">
                  <img
                    v-if="detail.developer_ss_id && !devLogoFailed"
                    :src="`https://screenscraper.fr/image.php?companyid=${detail.developer_ss_id}&media=logo-monochrome&maxwidth=110`"
                    class="cgl-company-logo"
                    :title="detail.developer"
                    @error="devLogoFailed = true"
                  />
                  <span v-if="!detail.developer_ss_id || devLogoFailed">{{ detail.developer }}</span>
                </span>
              </div>

              <!-- Stars (ss_score is 0-20) -->
              <div v-if="detail?.ss_score != null" class="cgl-stars">
                <span v-for="s in 5" :key="s" class="cgl-star" :class="{ on: s <= Math.round(detail.ss_score / 4) }">★</span>
                <span class="cgl-rating-num">{{ detail.ss_score }}<span style="opacity:.4">/20</span></span>
              </div>

              <!-- Screenshots strip - click or press X to open fullscreen viewer -->
              <div v-if="detail?.screenshots?.length" class="cgl-shots-wrap">
                <div class="cgl-shots">
                  <img
                    v-for="(s, si) in detail.screenshots.slice(0, 6)"
                    :key="si"
                    :src="s"
                    class="cgl-shot"
                    :alt="`Screenshot ${si+1}`"
                    loading="lazy"
                    @click="shotViewIdx = si"
                  />
                </div>
                <span class="cgl-shots-hint"><kbd>X</kbd> {{ t('couch.view_screenshots') }}</span>
              </div>

              <!-- Description -->
              <p v-if="detail?.description" class="cgl-show-desc">{{ detail.description }}</p>
              <div v-else-if="detailLoading" class="cgl-detail-loading">
                <div class="cgl-mini-spinner" /> {{ t('couch.loading_details') }}
              </div>

              <!-- Launch -->
              <button class="cgl-launch" @click="$emit('launch', selectedRom)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                {{ t('couch.launch') }}
              </button>
            </div>

          </div>
        </Transition>
      </div>
    </div>

    <!-- ══ GRID VIEW - split layout ══ -->
    <div v-else class="cgl-grid-split">

      <!-- Left: scrollable cover grid -->
      <div class="cgl-grid-left" ref="gridEl">
        <div class="cgl-grid">
          <div
            v-for="(rom, i) in roms"
            :key="rom.id"
            class="cgl-gcell"
            :class="{ active: i === selIdx }"
            :ref="el => { if (i === selIdx) selEl = el as Element | null }"
            @click="onItemClick(i)"
            @dblclick="$emit('launch', rom)"
          >
            <div class="cgl-gcover" :style="{ aspectRatio: coverAspect(rom) }">
              <img v-if="rom.cover_path" :src="rom.cover_path" :alt="rom.title" loading="lazy" />
              <div v-else class="cgl-gcover-empty">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".2"><rect x="2" y="3" width="20" height="18" rx="2"/></svg>
              </div>
              <div v-if="rom.video_path" class="cgl-gvideo-dot" />
            </div>
          </div>
        </div>
      </div>

      <!-- Divider -->
      <div class="cgl-grid-divider" />

      <!-- Right: fixed detail panel (no Transition - avoids opacity flicker during detail load) -->
      <div class="cgl-grid-right">
        <div v-if="selectedRom" class="cgl-gright-inner">

            <!-- Wheel / clear logo or text title - centered, full color, ~170px -->
            <div class="cgl-gright-logo-wrap">
              <img
                v-if="selectedRom.wheel_path || detail?.wheel_path"
                :src="(selectedRom.wheel_path || detail?.wheel_path)!"
                class="cgl-gright-wheel"
                :alt="selectedRom.title"
                @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLElement).nextElementSibling?.removeAttribute('style')"
              />
              <h2
                class="cgl-show-title"
                :style="(selectedRom.wheel_path || detail?.wheel_path) ? 'display:none' : ''"
              >{{ selectedRom.title }}</h2>
            </div>

            <!-- Chips - centered -->
            <div class="cgl-chips cgl-gright-chips">
              <span v-if="selectedRom.release_year" class="cgl-chip">{{ selectedRom.release_year }}</span>
              <span v-for="g in (detail?.genres ?? []).slice(0,3)" :key="g" class="cgl-chip">{{ g }}</span>
              <span v-if="detail?.developer" class="cgl-chip cgl-chip--dev">
                <img
                  v-if="detail.developer_ss_id && !devLogoFailed"
                  :src="`https://screenscraper.fr/image.php?companyid=${detail.developer_ss_id}&media=logo-monochrome&maxwidth=110`"
                  class="cgl-company-logo"
                  :title="detail.developer"
                  @error="devLogoFailed = true"
                />
                <span v-if="!detail.developer_ss_id || devLogoFailed">{{ detail.developer }}</span>
              </span>
            </div>

            <!-- Stars - centered -->
            <div v-if="detail?.ss_score != null" class="cgl-stars cgl-gright-center">
              <span v-for="s in 5" :key="s" class="cgl-star" :class="{ on: s <= Math.round(detail.ss_score / 4) }">★</span>
              <span class="cgl-rating-num">{{ detail.ss_score }}<span style="opacity:.4">/20</span></span>
            </div>

            <!-- Time to Beat (HLTB) -->
            <div v-if="detail?.hltb_main_s" class="cgl-hltb cgl-gright-center">
              <span class="cgl-hltb-label">{{ t('couch.time_to_beat') }}</span>
              <span v-if="detail.hltb_main_s" class="cgl-hltb-entry">
                <span class="cgl-hltb-val">{{ fmtHltb(detail.hltb_main_s) }}</span>
                <span class="cgl-hltb-sub">{{ t('couch.main') }}</span>
              </span>
              <span v-if="detail.hltb_extra_s" class="cgl-hltb-entry">
                <span class="cgl-hltb-val">{{ fmtHltb(detail.hltb_extra_s) }}</span>
                <span class="cgl-hltb-sub">{{ t('couch.extra') }}</span>
              </span>
              <span v-if="detail.hltb_complete_s" class="cgl-hltb-entry">
                <span class="cgl-hltb-val">{{ fmtHltb(detail.hltb_complete_s) }}</span>
                <span class="cgl-hltb-sub">100%</span>
              </span>
            </div>

            <!-- Screenshots strip -->
            <div v-if="detail?.screenshots?.length" class="cgl-shots-wrap">
              <div class="cgl-shots">
                <img
                  v-for="(s, si) in detail.screenshots.slice(0, 6)"
                  :key="si" :src="s"
                  class="cgl-shot" :alt="`Screenshot ${si+1}`" loading="lazy"
                  @click="shotViewIdx = si"
                />
              </div>
              <span class="cgl-shots-hint"><kbd>X</kbd> {{ t('couch.view_screenshots') }}</span>
            </div>

            <!-- Description -->
            <p v-if="detail?.description" class="cgl-show-desc">{{ detail.description }}</p>
            <div v-else-if="detailLoading" class="cgl-detail-loading">
              <div class="cgl-mini-spinner" /> {{ t('couch.loading_details') }}
            </div>

            <!-- Launch -->
            <button class="cgl-launch" @click="$emit('launch', selectedRom)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              {{ t('couch.launch') }}
            </button>

          </div>
      </div>

    </div>

    <!-- ══ SCREENSHOT FULLSCREEN VIEWER ══ -->
    <Transition name="cgl-modal">
      <div
        v-if="shotViewIdx >= 0 && detail?.screenshots?.length"
        class="cgl-shot-viewer"
        @click.self="shotViewIdx = -1"
      >
        <button class="cgl-shot-viewer-close" @click="shotViewIdx = -1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
        <button
          class="cgl-shot-viewer-nav cgl-shot-viewer-nav--prev"
          :disabled="shotViewIdx === 0"
          @click="shotViewIdx--"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <img
          :src="detail.screenshots[shotViewIdx]"
          class="cgl-shot-viewer-img"
          :alt="`Screenshot ${shotViewIdx + 1}`"
        />
        <button
          class="cgl-shot-viewer-nav cgl-shot-viewer-nav--next"
          :disabled="shotViewIdx >= detail.screenshots.length - 1"
          @click="shotViewIdx++"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="cgl-shot-viewer-counter">{{ shotViewIdx + 1 }} / {{ detail.screenshots.length }}</div>
      </div>
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from '@/i18n'
import { useCouchNav, navPaused } from '@/composables/useCouchNav'
import { useCouchTheme } from '@/composables/useCouchTheme'
import type { CouchPlatform } from './CouchSystemView.vue'
import client from '@/services/api/client'

// ── Types ────────────────────────────────────────────────────────────────────
export interface CouchRom {
  id:              number
  slug:            string
  title:           string
  cover_path:      string | null
  cover_type:      string | null
  cover_aspect:    string | null
  background_path: string | null   // fan art / hero image
  wheel_path:      string | null   // clear logo - shows instead of text title
  video_path:      string | null
  release_year:    number | null
  bezel_path:      string | null   // bezel overlay image
}

interface RomDetail {
  description:       string | null
  screenshots:       string[] | null
  background_path:   string | null
  developer:         string | null
  developer_ss_id:   number | null
  publisher_ss_id:   number | null
  genres:            string[] | null
  ss_score:          number | null   // 0-20 scale (ScreenScraper)
  video_path:        string | null
  wheel_path:        string | null   // clear logo / name logo for showcase title
  hltb_main_s:     number | null
  hltb_extra_s:    number | null
  hltb_complete_s: number | null
}

// ── Props / Emits ────────────────────────────────────────────────────────────
const props = defineProps<{
  platform: CouchPlatform
  view:     'list' | 'grid'
}>()

const emit = defineEmits<{
  back:    []
  launch:  [rom: CouchRom]
  menu:    []
  setView: [v: 'list' | 'grid']
}>()

// ── Composables ──────────────────────────────────────────────────────────────
const { t } = useI18n()
const { theme } = useCouchTheme()

// ── State ────────────────────────────────────────────────────────────────────
// ── Cover size presets ────────────────────────────────────────────────────────
const COVER_SIZES  = ['xs', 's', 'm', 'l'] as const
const SIZE_PX: Record<string, number> = { xs: 210, s: 260, m: 320, l: 390 }
const LS_SIZE_KEY  = 'gd3_couch_cover_size'
const coverSize    = ref<string>(localStorage.getItem(LS_SIZE_KEY) ?? 'm')
watch(coverSize, v => localStorage.setItem(LS_SIZE_KEY, v))

const roms         = ref<CouchRom[]>([])
const loading      = ref(true)
const selIdx       = ref(0)
const selEl        = ref<Element | null>(null)
const listEl       = ref<HTMLElement>()
const gridEl       = ref<HTMLElement>()
const videoErr     = ref(false)
const bgVideoEl    = ref<HTMLVideoElement>()
function applyVideoVol() {
  const el = bgVideoEl.value
  if (!el) return
  const wantMuted = localStorage.getItem('gd3_couch_video_muted') !== '0'
  const vol = parseInt(localStorage.getItem('gd3_couch_video_vol') || '50', 10) / 100
  el.volume = Math.max(0, Math.min(1, vol))
  // Unmute only works after user interaction - try, catch if blocked
  if (!wantMuted && el.muted) {
    el.muted = false
    el.play().catch(() => { el.muted = true })  // fallback: keep muted if autoplay policy blocks
  } else if (wantMuted) {
    el.muted = true
  }
}
// Listen for CouchMenu changes (custom events, same page)
window.addEventListener('gd-video-vol-change', applyVideoVol)
window.addEventListener('gd-cover-size-change', (e: Event) => {
  const sz = (e as CustomEvent).detail
  if (sz && coverSize.value !== sz) coverSize.value = sz
})
const shotViewIdx  = ref(-1)      // screenshot fullscreen viewer (-1 = closed)
const devLogoFailed = ref(false)  // ScreenScraper developer logo failed to load

// Lazy-loaded ROM detail (description, screenshots, video, etc.)
const detail        = ref<RomDetail | null>(null)
const detailLoading = ref(false)
const detailCache   = new Map<number, RomDetail>()

// Reset per-game UI flags when selection changes
watch(selIdx, () => { devLogoFailed.value = false; shotViewIdx.value = -1 })

// ── Computed ─────────────────────────────────────────────────────────────────
const selectedRom = computed(() => roms.value[selIdx.value] ?? null)

const rootStyle = computed(() => {
  const style: Record<string, string> = {
    '--cgl-cover-min': `${SIZE_PX[coverSize.value] ?? 210}px`,
  }
  // In grid view the left panel fills ~78% of screen; push the overlay gradient endpoint
  // to match so covers stay readable behind the dark overlay
  if (props.view === 'grid') style['--cgl-list-w'] = '50%'
  const col = props.platform.system_color
  if (col) style['--cgl-accent'] = `#${col}`
  return style
})

// Background: prefers video > detail background > cover
const bgKey   = computed(() => selectedRom.value?.id ?? 'none')
const bgVideo = computed(() => detail.value?.video_path ?? selectedRom.value?.video_path ?? null)
const bgImg   = computed(() => {
  const d = detail.value
  const r = selectedRom.value
  return d?.background_path
    ?? (d?.screenshots?.[0] ?? null)
    ?? r?.cover_path
    ?? props.platform.photo_path
    ?? null
})

// ── ROM list loading ──────────────────────────────────────────────────────────
async function loadRoms() {
  loading.value = true
  try {
    const { data } = await client.get('/roms', {
      params: { platform_slug: props.platform.slug, limit: 500, offset: 0 }
    })
    roms.value = ((data.items ?? data) as any[]).map((r: any) => ({
      id:           r.id,
      slug:         r.slug,
      title:        r.name || r.title || r.fs_name_no_ext || '?',
      cover_path:      r.cover_path      ?? null,
      cover_type:      r.cover_type      ?? null,
      cover_aspect:    r.cover_aspect    ?? null,
      background_path: r.background_path ?? null,
      wheel_path:      r.wheel_path      ?? null,
      video_path:      r.video_path      ?? null,
      release_year:    r.release_year    ?? null,
      bezel_path:      r.bezel_path      ?? null,
    }))
    selIdx.value = 0
  } catch (e) {
    console.error('[CouchGamelist] Failed to load ROMs:', e)
  } finally {
    loading.value = false
  }
}

// ── ROM detail lazy-load ──────────────────────────────────────────────────────
let detailTimer = 0

async function loadDetail(rom: CouchRom) {
  if (!rom) return
  const cached = detailCache.get(rom.id)
  if (cached) { detail.value = cached; videoErr.value = false; return }

  detailLoading.value = true
  videoErr.value = false
  try {
    const { data } = await client.get(`/roms/${rom.id}`)
    const d: RomDetail = {
      description:     data.summary || null,
      screenshots:     Array.isArray(data.screenshots) && data.screenshots.length ? data.screenshots : null,
      background_path: data.background_path || null,
      developer:         data.developer         || null,
      developer_ss_id:   data.developer_ss_id   ?? null,
      publisher_ss_id:   data.publisher_ss_id   ?? null,
      genres:            Array.isArray(data.genres) && data.genres.length ? data.genres : null,
      ss_score:          data.ss_score          ?? null,
      video_path:        data.video_path        ?? null,
      wheel_path:        data.wheel_path        || null,
      hltb_main_s:     data.hltb_main_s     ?? null,
      hltb_extra_s:    data.hltb_extra_s    ?? null,
      hltb_complete_s: data.hltb_complete_s ?? null,
    }
    detailCache.set(rom.id, d)
    detail.value = d
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// Debounce detail fetch - don't spam API while scrolling fast
watch(selectedRom, (rom) => {
  clearTimeout(detailTimer)
  detail.value = rom ? (detailCache.get(rom.id) ?? null) : null
  if (rom) detailTimer = window.setTimeout(() => loadDetail(rom), 300)
}, { immediate: true })

// Scroll selected item into view
watch(selIdx, () => {
  nextTick(() => selEl.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
})

// ── HLTB time formatter (seconds → "Xh" string) ──────────────────────────────
function fmtHltb(s: number | null): string {
  if (!s) return ''
  const h = Math.round(s / 3600)
  return h < 1 ? '<1h' : `${h}h`
}

// ── Cover aspect ratio ────────────────────────────────────────────────────────
function coverAspect(rom: CouchRom): string {
  if (rom.cover_type === 'box-3D') return '16/9'
  return rom.cover_aspect || props.platform.cover_aspect || '3/4'
}

// ── Interaction ──────────────────────────────────────────────────────────────
function onItemClick(i: number) {
  if (i === selIdx.value) emit('launch', roms.value[i])
  else selIdx.value = i
}

// Compute visible grid columns dynamically from left panel width + cover size
const gridCols = computed(() => {
  const w = gridEl.value?.clientWidth ?? (window.innerWidth - 440)
  const colW = (SIZE_PX[coverSize.value] ?? 210) + 12
  return Math.max(1, Math.floor((w - 32) / colW))
})

useCouchNav({
  up: () => {
    if (shotViewIdx.value >= 0) return
    if (props.view === 'list') { if (selIdx.value > 0) selIdx.value-- }
    else { if (selIdx.value >= gridCols.value) selIdx.value -= gridCols.value }
  },
  down: () => {
    if (shotViewIdx.value >= 0) return
    if (props.view === 'list') { if (selIdx.value < roms.value.length - 1) selIdx.value++ }
    else { if (selIdx.value + gridCols.value < roms.value.length) selIdx.value += gridCols.value }
  },
  left: () => {
    if (shotViewIdx.value >= 0) { if (shotViewIdx.value > 0) shotViewIdx.value--; return }
    if (props.view === 'grid' && selIdx.value > 0) selIdx.value--
    else if (props.view === 'list') emit('back')
  },
  right: () => {
    if (shotViewIdx.value >= 0) {
      const shots = detail.value?.screenshots
      if (shots && shotViewIdx.value < shots.length - 1) shotViewIdx.value++
      return
    }
    if (props.view === 'grid' && selIdx.value < roms.value.length - 1) selIdx.value++
  },
  confirm: () => {
    if (shotViewIdx.value >= 0) return
    if (selectedRom.value) emit('launch', selectedRom.value)
  },
  back: () => {
    if (shotViewIdx.value >= 0) { shotViewIdx.value = -1; return }
    emit('back')
  },
  menu: () => emit('menu'),
  x: () => {
    if (shotViewIdx.value >= 0) return
    if (detail.value?.screenshots?.length) shotViewIdx.value = 0
  },
})

onMounted(loadRoms)
</script>

<style scoped>
/* ── Root ── */
.cgl-root {
  position: fixed; inset: 0; z-index: 100;
  display: flex; flex-direction: column;
  overflow: hidden; user-select: none;
  --cgl-accent: #7c3aed;
  --cgl-font: 'Segoe UI', system-ui, sans-serif;
  --cgl-list-w: 34%;
  --cgl-card-bg: rgba(0,0,0,.55);
  --cgl-list-item-active: rgba(255,255,255,.10);
}

/* ── Per-theme variables ── */
.cgl-theme--noir {
  --cgl-accent: #c9a84c;
  --cgl-font: Georgia, 'Times New Roman', serif;
  --cgl-card-bg: rgba(16, 10, 2, .78);
  --cgl-list-item-active: rgba(201,168,76,.12);
}
.cgl-theme--aura {
  --cgl-font: 'Segoe UI', system-ui, sans-serif;
  --cgl-card-bg: rgba(4, 2, 18, .6);
  --cgl-list-item-active: rgba(124,58,237,.18);
}
.cgl-theme--slick {
  --cgl-accent: #cc0000;
  --cgl-font: 'Arial Narrow', Arial, sans-serif;
  --cgl-card-bg: rgba(0,0,0,.82);
  --cgl-list-item-active: rgba(204,0,0,.12);
}

/* ── Background ── */
.cgl-bg-layer {
  position: absolute; inset: 0; z-index: 0;
}
.cgl-bg-video {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; transform: scale(1.04);
  pointer-events: none;
}
.cgl-bg-img {
  position: absolute; inset: -4%; width: 108%; height: 108%;
  background-size: cover; background-position: center;
}
/* Per-theme bg filter - Aura is vivid and bright, Noir cinematic, Slick near-dark */
.cgl-theme--noir  .cgl-bg-video,
.cgl-theme--noir  .cgl-bg-img { filter: blur(16px) brightness(.48) saturate(.55) sepia(.55); }
.cgl-theme--aura  .cgl-bg-video,
.cgl-theme--aura  .cgl-bg-img { filter: blur(18px) brightness(.72) saturate(2.2); }
.cgl-theme--slick .cgl-bg-video,
.cgl-theme--slick .cgl-bg-img { filter: blur(30px) brightness(.28) saturate(.3) contrast(1.1); }

/* Ken Burns on static bg image */
@keyframes cgl-kenburns {
  0%   { transform: scale(1.06) translate(0%,   0%); }
  33%  { transform: scale(1.13) translate(-3%,  -1.5%); }
  66%  { transform: scale(1.10) translate(2%,   1%); }
  100% { transform: scale(1.06) translate(0%,   0%); }
}
.cgl-bg-img {
  animation: cgl-kenburns 44s ease-in-out infinite;
  will-change: transform;
}

.cgl-bg-enter-active, .cgl-bg-leave-active { transition: opacity .55s ease; }
.cgl-bg-enter-from, .cgl-bg-leave-to { opacity: 0; }

/* Background overlay - much more subtle than before */
.cgl-bg-overlay {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
}
/* Noir: warm dark, strong left gradient, lighter right so art shows on bg */
.cgl-theme--noir  .cgl-bg-overlay {
  background:
    linear-gradient(to right, rgba(14,8,0,.96) 0%, rgba(14,8,0,.60) var(--cgl-list-w), rgba(6,3,0,.20) 100%),
    linear-gradient(to bottom, rgba(0,0,0,.30) 0%, transparent 30%, rgba(0,0,0,.50) 100%);
}
/* Aura: minimal overlay - let the vibrant art breathe. Platform color tint left only */
.cgl-theme--aura  .cgl-bg-overlay {
  background:
    linear-gradient(to right, rgba(3,1,15,.95) 0%, rgba(3,1,15,.60) var(--cgl-list-w), rgba(0,0,5,.08) 100%),
    linear-gradient(to bottom, rgba(0,0,0,.15) 0%, transparent 25%, rgba(0,0,0,.30) 100%);
}
/* Slick: harsh dark, art barely shows through */
.cgl-theme--slick .cgl-bg-overlay {
  background:
    linear-gradient(to right, rgba(0,0,0,.98) 0%, rgba(0,0,0,.80) var(--cgl-list-w), rgba(0,0,0,.50) 100%),
    linear-gradient(to bottom, rgba(0,0,0,.40) 0%, rgba(0,0,0,.20) 60%, rgba(0,0,0,.75) 100%);
}

/* Noir grain */
.cgl-noir-grain {
  position: absolute; inset: 0; z-index: 2; pointer-events: none;
  opacity: .05;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 200px 200px; mix-blend-mode: overlay;
}
/* Slick scanlines */
.cgl-slick-lines {
  position: absolute; inset: 0; z-index: 2; pointer-events: none; opacity: .5;
  background: repeating-linear-gradient(to bottom, transparent 0, transparent 3px, rgba(0,0,0,.1) 3px, rgba(0,0,0,.1) 4px);
}

/* ── Top bar ── */
.cgl-topbar {
  position: relative; z-index: 10; flex-shrink: 0;
  display: flex; align-items: center; gap: var(--space-4, 16px);
  padding: 14px 24px;
  background: transparent;
}
/* List view only: match cgl-list panel style */
.cgl-view--list .cgl-topbar { background: var(--cgl-card-bg); }
.cgl-view--list.cgl-theme--aura .cgl-topbar { backdrop-filter: blur(20px) saturate(1.6); }
.cgl-view--list.cgl-theme--noir .cgl-topbar { backdrop-filter: blur(12px) saturate(1.1); }
.cgl-back {
  display: flex; align-items: center; gap: 5px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
  color: rgba(255,255,255,.7); border-radius: 7px; padding: 5px 12px;
  font-size: var(--fs-sm, 12px); font-weight: 600; cursor: pointer; transition: all .15s;
  white-space: nowrap; flex-shrink: 0;
}
.cgl-back:hover { background: rgba(255,255,255,.16); color: #fff; }

.cgl-plat { display: flex; align-items: center; gap: 10px; flex: 1; }

/* Platform pill - wraps wheel logo or text name like gd-pill-name-logo */
.cgl-plat-pill {
  display: flex; align-items: center;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
  border-radius: 20px; padding: 5px 14px 5px 10px;
  backdrop-filter: blur(8px);
}
.cgl-plat-wheel {
  height: 22px; max-width: 130px; width: auto;
  object-fit: contain; filter: brightness(1.15) drop-shadow(0 1px 4px rgba(0,0,0,.5));
  display: block;
}
.cgl-plat-name { font-size: var(--fs-md, 14px); font-weight: 800; color: #fff; font-family: var(--cgl-font); letter-spacing: .01em; }
.cgl-plat-count { font-size: 11px; color: rgba(255,255,255,.35); }

.cgl-topbar-right { display: flex; align-items: center; gap: var(--space-2, 8px); margin-left: auto; }

/* Cover size presets */
.cgl-sizes { display: flex; gap: 2px; }
.cgl-sizebtn {
  padding: 3px 6px; border-radius: var(--radius-xs, 4px); font-size: 9px; font-weight: 700;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08);
  color: rgba(255,255,255,.35); cursor: pointer; letter-spacing: .04em; transition: all .12s;
}
.cgl-sizebtn:hover { background: rgba(255,255,255,.12); color: rgba(255,255,255,.7); }
.cgl-sizebtn.active { background: var(--cgl-accent); border-color: var(--cgl-accent); color: #fff; }
.cgl-topbar-sep { width: 1px; height: 20px; background: rgba(255,255,255,.1); margin: 0 4px; }

.cgl-viewbtn {
  width: 30px; height: 30px; border-radius: 6px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.4); cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.cgl-viewbtn.active { background: var(--cgl-accent); border-color: var(--cgl-accent); color: #fff; }
.cgl-hint { font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.25); white-space: nowrap; }
.cgl-hint kbd {
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14);
  border-radius: 3px; padding: 1px 4px; font-size: 9px; font-family: inherit;
}

/* ── Loading ── */
.cgl-loading {
  position: relative; z-index: 10; flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  color: rgba(255,255,255,.4); font-size: 13px;
}
.cgl-spinner {
  width: 36px; height: 36px; border-radius: 50%;
  border: 3px solid rgba(255,255,255,.1); border-top-color: var(--cgl-accent);
  animation: cgl-spin .8s linear infinite;
}
@keyframes cgl-spin { to { transform: rotate(360deg); } }

/* ══ LIST VIEW ══ */
.cgl-list-wrap {
  position: relative; z-index: 10; flex: 1;
  display: flex; overflow: hidden;
}

/* ── Game list ── */
.cgl-list {
  width: var(--cgl-list-w); flex-shrink: 0;
  overflow-y: auto; padding: 8px 0 24px;
  scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.1) transparent;
  background: var(--cgl-card-bg);
  border-right: 1px solid rgba(255,255,255,.06);
}
/* Aura: frosted glass list panel */
.cgl-theme--aura .cgl-list {
  backdrop-filter: blur(20px) saturate(1.6);
  border-right-color: rgba(255,255,255,.10);
}
/* Noir: warm glass */
.cgl-theme--noir .cgl-list {
  backdrop-filter: blur(12px) saturate(1.1);
  border-right: 1px solid rgba(201,168,76,.12);
}
/* Slick: solid panel, no blur - hard edge */
.cgl-theme--slick .cgl-list {
  backdrop-filter: none;
  border-right: 2px solid rgba(204,0,0,.4);
}
.cgl-list::-webkit-scrollbar { width: 3px; }
.cgl-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 2px; }

.cgl-item {
  display: flex; align-items: center; gap: 14px;
  padding: 8px 16px 8px 12px; cursor: pointer; position: relative; overflow: hidden;
  transition: transform .15s ease, box-shadow .15s ease;
}
.cgl-item.active {
  transform: translateY(-2px) scale(1.01);
  box-shadow: 0 6px 20px rgba(0,0,0,.45);
  z-index: 1;
}
/* ── Hero background: blurred art fills the FULL item (always visible) ── */
.cgl-item::before {
  content: ''; position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: var(--item-hero, none) center / cover no-repeat;
  filter: blur(4px) brightness(.48) saturate(1.7);
  opacity: .6;
  transform: scale(1.08);
  /* no opacity/filter transition - prevents visual pop when switching items */
}
/* Ken Burns animation ONLY on active item; inactive stays static */
.cgl-item.active::before {
  animation: cgl-item-kb 28s ease-in-out infinite;
}
@keyframes cgl-item-kb {
  0%   { transform: scale(1.08) translate(0%,    0%); }
  33%  { transform: scale(1.14) translate(-1.8%, -.9%); }
  66%  { transform: scale(1.11) translate(1.2%,  .6%); }
  100% { transform: scale(1.08) translate(0%,    0%); }
}
/* Dark left gradient - keeps box art cover readable (same for all items) */
.cgl-item::after {
  content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: linear-gradient(to right,
    rgba(0,0,0,.85) 0%,
    rgba(0,0,0,.65) 130px,
    rgba(0,0,0,.12) 260px,
    rgba(0,0,0,.04) 100%
  );
}
.cgl-item-bar {
  position: absolute; left: 0; top: 0; bottom: 0; width: 3px; z-index: 3;
  background: var(--cgl-accent); border-radius: 0 2px 2px 0;
}
.cgl-item-cover {
  width: 150px; flex-shrink: 0; border-radius: 6px; overflow: hidden;
  background: rgba(255,255,255,.05); display: flex; align-items: center; justify-content: center;
}
.cgl-item-cover img { width: 100%; height: 100%; object-fit: contain; display: block; }

/* Item text area: centered content, sits above hero pseudo-elements */
.cgl-item-text {
  flex: 1; min-width: 0; align-self: stretch;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-2, 8px); text-align: center;
  position: relative; z-index: 2;
}
.cgl-item-cover { position: relative; z-index: 2; }

/* Wheel / clear logo - fills the available width of the text area */
.cgl-item-wheel {
  width: 85%; height: auto;
  max-height: 90px;
  object-fit: contain; object-position: center;
  filter: drop-shadow(0 2px 14px rgba(0,0,0,.85)) brightness(1.1);
  display: block;
}
.cgl-theme--noir  .cgl-item-wheel { filter: drop-shadow(0 1px 10px rgba(201,168,76,.4)) drop-shadow(0 0 20px rgba(0,0,0,.9)); }
.cgl-theme--slick .cgl-item-wheel { filter: drop-shadow(0 0 8px rgba(204,0,0,.45)) drop-shadow(0 2px 12px rgba(0,0,0,.95)); }

.cgl-item-title {
  display: block; font-size: var(--fs-sm, 12px); font-weight: 700; color: rgba(255,255,255,.9);
  white-space: normal; text-align: center; line-height: 1.35;
  font-family: var(--cgl-font);
}
.cgl-item.active .cgl-item-title { color: #fff; }
.cgl-item-year { display: block; font-size: 11px; color: rgba(255,255,255,.45); }
.cgl-theme--slick .cgl-item-title { text-transform: uppercase; font-size: var(--fs-xs, 10px); letter-spacing: .04em; }

/* ── Showcase (right side in list view) ── */
.cgl-showcase {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  display: flex; align-items: center;        /* vertically center the showcase */
  padding: 20px 48px 32px;
  scrollbar-width: none;
}
.cgl-showcase::-webkit-scrollbar { display: none; }

.cgl-show-inner {
  display: flex; gap: 44px; width: 100%;
  align-items: center;
}

/* Cover wrapper - big and prominent */
.cgl-show-cover-wrap {
  flex-shrink: 0; width: clamp(200px, 26vw, 360px);
}
/* Per-theme cover frame */
.cgl-theme--aura .cgl-show-cover-wrap {
  filter: drop-shadow(0 0 40px var(--cgl-accent, #7c3aed))
          drop-shadow(0 20px 48px rgba(0,0,0,.8));
}
.cgl-theme--noir .cgl-show-cover-wrap {
  filter: drop-shadow(0 0 2px rgba(201,168,76,.6))
          drop-shadow(0 20px 40px rgba(0,0,0,.9));
}
.cgl-theme--slick .cgl-show-cover-wrap {
  filter: drop-shadow(0 0 12px rgba(204,0,0,.5))
          drop-shadow(0 16px 32px rgba(0,0,0,.9));
}

.cgl-show-cover {
  width: 100%; display: block;
  object-fit: contain; max-height: 75vh;
}
.cgl-theme--aura  .cgl-show-cover { border-radius: 10px; }
.cgl-theme--noir  .cgl-show-cover {
  border-radius: 2px;
  outline: 1px solid rgba(201,168,76,.35);
}
.cgl-theme--slick .cgl-show-cover {
  border-radius: 0;
  outline: 2px solid rgba(204,0,0,.7);
}
.cgl-show-cover-empty {
  width: 100%; aspect-ratio: 3/4;
  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08);
  display: flex; align-items: center; justify-content: center;
}

.cgl-show-info {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; gap: var(--space-4, 16px);
}

/* Wheel / clear logo displayed instead of text title */
.cgl-show-wheel {
  max-height: clamp(52px, 8vw, 100px);
  max-width: 100%;
  object-fit: contain;
  object-position: left center;
  filter: drop-shadow(0 2px 14px rgba(0,0,0,.8));
  display: block;
}
.cgl-theme--noir  .cgl-show-wheel { filter: drop-shadow(0 2px 12px rgba(201,168,76,.4)) drop-shadow(0 0 20px rgba(0,0,0,.8)); }
.cgl-theme--slick .cgl-show-wheel { filter: drop-shadow(0 0 8px rgba(204,0,0,.5)) drop-shadow(0 2px 12px rgba(0,0,0,.9)); }

.cgl-show-title {
  font-size: clamp(22px, 3vw, 40px); font-weight: 900; color: #fff;
  font-family: var(--cgl-font); line-height: 1.1; margin: 0;
  text-shadow: 0 2px 20px rgba(0,0,0,.7);
}
.cgl-theme--aura  .cgl-show-title {
  background: linear-gradient(135deg, #fff 60%, var(--cgl-accent, #a78bfa));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.cgl-theme--slick .cgl-show-title {
  text-transform: uppercase; letter-spacing: .06em; font-size: clamp(18px, 2.4vw, 32px);
  -webkit-text-fill-color: unset; color: #fff;
}
.cgl-theme--noir .cgl-show-title {
  font-style: italic; letter-spacing: .02em;
  color: #f5e8cc;
  -webkit-text-fill-color: unset;
}

/* Accent line below title (Slick & Noir) */
.cgl-theme--slick .cgl-show-title::after,
.cgl-theme--noir  .cgl-show-title::after {
  content: ''; display: block; height: 2px; width: 40px;
  margin-top: 10px; background: var(--cgl-accent);
}

/* Chips */
/* align-items:center so regular chip text sits at the vertical mid-point of the taller dev chip */
.cgl-chips { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; align-items: center; }
.cgl-chip {
  font-size: 11px; font-weight: 600; letter-spacing: .04em;
  padding: 3px 11px; border-radius: 20px;
  background: rgba(255,255,255,.1); color: rgba(255,255,255,.7);
  /* no border */
}
.cgl-theme--noir  .cgl-chip { border-radius: 2px; background: rgba(201,168,76,.1); color: rgba(220,190,120,.75); }
.cgl-theme--slick .cgl-chip { border-radius: 0; color: rgba(255,255,255,.6); text-transform: uppercase; font-size: var(--fs-xs, 10px); }
/* cgl-chip--dev overrides defined lower (with logo support) */

/* Stars */
.cgl-stars { display: flex; align-items: center; gap: 3px; }
.cgl-star { font-size: var(--fs-xl, 18px); color: rgba(255,255,255,.18); line-height: 1; }
.cgl-star.on { color: #fbbf24; }
.cgl-rating-num { font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.4); margin-left: 5px; }

/* Description */
.cgl-show-desc {
  font-size: 13px; color: rgba(255,255,255,.55); line-height: 1.8;
  display: -webkit-box; -webkit-line-clamp: 7; -webkit-box-orient: vertical;
  overflow: hidden; margin: 0;
}
.cgl-theme--noir  .cgl-show-desc { color: rgba(220,195,140,.58); font-size: var(--fs-md, 14px); line-height: 1.9; }
.cgl-theme--slick .cgl-show-desc { color: rgba(200,200,200,.45); font-size: var(--fs-sm, 12px); letter-spacing: .01em; }

.cgl-detail-loading {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.3);
}
.cgl-mini-spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.1); border-top-color: var(--cgl-accent);
  animation: cgl-spin .6s linear infinite; flex-shrink: 0;
}

/* Screenshots strip */
.cgl-shots {
  display: flex; gap: 10px;
}
.cgl-shot {
  height: 180px; aspect-ratio: 16/9; object-fit: cover;
  border-radius: 5px; border: 1px solid rgba(255,255,255,.1);
  box-shadow: 0 4px 16px rgba(0,0,0,.5);
  cursor: pointer; transition: transform .15s, box-shadow .15s;
}
.cgl-shot:hover { transform: scale(1.06); box-shadow: 0 8px 24px rgba(0,0,0,.6); }
.cgl-theme--slick .cgl-shot { border-radius: 0; }

/* ── Showcase transition ── */
.cgl-show-enter-active { transition: opacity .3s ease, transform .3s ease; }
.cgl-show-leave-active { transition: opacity .15s ease; }
.cgl-show-enter-from { opacity: 0; transform: translateY(12px); }
.cgl-show-leave-to   { opacity: 0; }

/* ══ GRID VIEW - split layout ══ */
.cgl-grid-split {
  flex: 1; display: flex; min-height: 0; overflow: hidden;
  position: relative; z-index: 10;  /* must be above cgl-bg-layer (z:0) and cgl-bg-overlay (z:1) */
}
.cgl-grid-left {
  /* No background - cgl-bg-overlay (z:1) shows through at the same opacity as list view left side */
  width: 50%; flex-shrink: 0;
  overflow-y: auto; padding: 20px 16px 24px;
  scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.1) transparent;
}
.cgl-grid-left::-webkit-scrollbar { width: 3px; }
.cgl-grid-left::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); }

.cgl-grid-divider {
  width: 1px; flex-shrink: 0;
  background: rgba(255,255,255,.09);
  margin: 12px 0;
}

.cgl-grid-right {
  /* other 50% minus divider - video shows through (no background) */
  flex: 1; min-width: 0;
  display: flex; align-items: center;
  overflow-y: auto; padding: 24px 40px;
  scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.1) transparent;
}
.cgl-grid-right::-webkit-scrollbar { width: 3px; }
.cgl-grid-right::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); }

.cgl-gright-inner {
  width: 100%;
  display: flex; flex-direction: column; gap: var(--space-4, 16px);
  align-items: center;
}
/* Logo wrap - centers the wheel or title */
.cgl-gright-logo-wrap {
  width: 100%; display: flex; justify-content: center; align-items: center;
  min-height: 80px;
}
.cgl-gright-wheel {
  max-height: 170px; max-width: 100%; object-fit: contain;
  /* no filter - show actual logo colors */
}
/* Chips + stars + hltb centered in grid right panel */
.cgl-gright-chips { justify-content: center; }
.cgl-gright-center { justify-content: center; }

/* Time to Beat */
.cgl-hltb {
  display: flex; align-items: baseline; gap: var(--space-4, 16px); flex-wrap: wrap;
}
.cgl-hltb-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: rgba(255,255,255,.35); margin-right: 4px;
}
.cgl-hltb-entry {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.cgl-hltb-val {
  font-size: var(--fs-lg, 16px); font-weight: 700; color: rgba(255,255,255,.9);
}
.cgl-hltb-sub {
  font-size: 9px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: rgba(255,255,255,.35);
}

.cgl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cgl-cover-min, 210px), 1fr));
  gap: var(--space-3, 12px); align-content: start;
}

.cgl-gcell { cursor: pointer; display: flex; flex-direction: column; gap: 5px; transition: transform .15s; }
.cgl-gcell:hover { transform: scale(1.04); }
.cgl-gcell.active { transform: scale(1.06); }

.cgl-gcover {
  border-radius: 6px; overflow: hidden;
  background: rgba(255,255,255,.07); position: relative;
  box-shadow: 0 4px 14px rgba(0,0,0,.5);
  border: 2px solid transparent; transition: border-color .15s, box-shadow .15s;
}
.cgl-gcell.active .cgl-gcover {
  border-color: var(--cgl-accent);
  box-shadow: 0 0 0 1px var(--cgl-accent), 0 8px 28px rgba(0,0,0,.7);
}
.cgl-theme--noir  .cgl-gcover { border-radius: 3px; }
.cgl-theme--slick .cgl-gcover { border-radius: 0; }

.cgl-gcover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cgl-gcover-empty { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.cgl-gvideo-dot {
  position: absolute; top: 5px; right: 5px;
  width: 6px; height: 6px; border-radius: 50%; background: var(--cgl-accent);
  box-shadow: 0 0 5px var(--cgl-accent);
}
.cgl-gtitle {
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.5); text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-family: var(--cgl-font);
}
.cgl-gcell.active .cgl-gtitle { color: #fff; font-weight: 600; }

/* (hint bar and modal removed - grid view is now split layout) */

/* ── Developer company logo (ScreenScraper, like gd-meta-company-logo) ── */
.cgl-company-logo {
  max-height: 48px; max-width: 140px; object-fit: contain;
  filter: invert(1) brightness(1.4); opacity: .85;
  display: block;
}
/* cgl-chip--dev is bigger than a regular chip - logo or text, prominent; no border */
.cgl-chip--dev {
  font-size: 13px; letter-spacing: .03em;
  padding: 7px 18px;
  display: flex; align-items: center;
  background: rgba(0,0,0,.35);
  border: none;
  color: var(--cgl-accent);
}

/* ── Screenshot viewer ── */
.cgl-shot-viewer {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.92); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.cgl-shot-viewer-img {
  max-width: 90vw; max-height: 85vh; object-fit: contain;
  border-radius: 6px; box-shadow: 0 0 60px rgba(0,0,0,.8);
  animation: cgl-shot-pop .2s ease;
}
@keyframes cgl-shot-pop { from { transform: scale(.94); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.cgl-shot-viewer-close {
  position: absolute; top: 20px; right: 20px;
  width: 38px; height: 38px; border-radius: 50%;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.15);
  color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.cgl-shot-viewer-close:hover { background: rgba(255,255,255,.22); }
.cgl-shot-viewer-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 52px; height: 52px; border-radius: 50%;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.15);
  color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.cgl-shot-viewer-nav:hover:not(:disabled) { background: rgba(255,255,255,.22); }
.cgl-shot-viewer-nav:disabled { opacity: .2; cursor: default; }
.cgl-shot-viewer-nav--prev { left: 20px; }
.cgl-shot-viewer-nav--next { right: 20px; }
.cgl-shot-viewer-counter {
  position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.4); letter-spacing: .08em;
}

/* Screenshots strip wrap + hint */
.cgl-shots-wrap { display: flex; flex-direction: column; gap: 6px; }
.cgl-shots-hint {
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.28); letter-spacing: .04em; display: flex; align-items: center; gap: var(--space-1, 4px);
}
.cgl-shots-hint kbd {
  background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.14);
  border-radius: 3px; padding: 1px 5px; font-size: 9px; font-family: inherit; color: rgba(255,255,255,.5);
}

/* ── Launch button ── */
.cgl-launch {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  background: var(--cgl-accent); color: #fff; border: none;
  padding: 10px 24px; font-size: var(--fs-md, 14px); font-weight: 700;
  cursor: pointer; transition: all .18s; flex-shrink: 0;
  letter-spacing: .03em; align-self: flex-start;
  box-shadow: 0 6px 24px rgba(0,0,0,.5), 0 0 0 0 var(--cgl-accent);
}
.cgl-theme--aura  .cgl-launch { border-radius: 10px; }
.cgl-theme--noir  .cgl-launch { border-radius: 3px; }
.cgl-theme--slick .cgl-launch { border-radius: 0; letter-spacing: .1em; text-transform: uppercase; font-size: var(--fs-sm, 12px); }
.cgl-launch:hover {
  filter: brightness(1.15);
  box-shadow: 0 8px 32px rgba(0,0,0,.6), 0 0 20px var(--cgl-accent);
  transform: translateY(-1px);
}
.cgl-launch--sm { padding: 7px 18px; font-size: var(--fs-sm, 12px); }
</style>
