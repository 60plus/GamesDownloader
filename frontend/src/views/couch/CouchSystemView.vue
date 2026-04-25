<template>
  <div class="csv-root" :class="`csv-theme--${theme}`" :style="platformAccent">

    <!-- ══ FULL BLEED BACKGROUND - fanart/cover img with Ken Burns ══ -->
    <Transition name="csv-bg">
      <div
        :key="current.fs_slug"
        class="csv-bg-layer"
        :style="layerBgStyle"
      >
        <img
          class="csv-bg-img"
          :src="current.cover_path || `/platforms/fanart/${current.fs_slug}.webp`"
          :alt="current.name"
          @error="($event.target as HTMLImageElement).style.display='none'"
        />
      </div>
    </Transition>
    <!-- Blur + gradient overlays -->
    <div class="csv-bg-overlay" />
    <div class="csv-bg-vignette" />
    <!-- Theme-specific overlays -->
    <div v-if="theme === 'noir'" class="csv-noir-grain" />
    <div v-if="theme === 'slick'" class="csv-slick-lines" />

    <!-- ══ HEADER - theme logo + nav hint ══ -->
    <div class="csv-header">
      <div class="csv-header-left">
        <img src="/GDLOGO.png" class="csv-logo" alt="GD" @error="($event.target as HTMLImageElement).style.display='none'" />
      </div>
      <div class="csv-header-right">
        <span class="csv-nav-hint">
          <kbd>← →</kbd> {{ t('couch.navigate') }} &nbsp;·&nbsp; <kbd>A</kbd> {{ t('couch.nav_select') }} &nbsp;·&nbsp; <kbd>Start</kbd> / <kbd>M</kbd> {{ t('couch.nav_menu') }} &nbsp;·&nbsp; <kbd>B</kbd> {{ t('couch.nav_exit') }}
        </span>
      </div>
    </div>

    <!-- ══ CAROUSEL ══ -->
    <div class="csv-carousel-area" ref="carouselEl">
      <div
        class="csv-carousel-track"
        :style="{ transform: `translateX(calc(-${systemIndex * CARD_STEP}px + 50vw - ${CARD_W / 2}px))` }"
      >
        <div
          v-for="(plat, i) in platforms"
          :key="plat.fs_slug"
          class="csv-plat-card"
          :class="{
            'csv-plat-card--active':   i === systemIndex,
            'csv-plat-card--adj1':     Math.abs(i - systemIndex) === 1,
            'csv-plat-card--adj2':     Math.abs(i - systemIndex) === 2,
            'csv-plat-card--far':      Math.abs(i - systemIndex) >= 3,
          }"
          :style="{
            left: `${i * CARD_STEP}px`,
            '--plat-color': plat.system_color ? `#${plat.system_color}` : 'var(--csv-accent)',
          }"
          @click="onCardClick(i)"
        >
          <!-- Console photo background with Ken Burns (desynchronized per card) -->
          <div
            v-if="plat.photo_path"
            class="csv-card-photo"
            :style="{ backgroundImage: `url(${plat.photo_path})`, animationDelay: `${-(i * 7.3 % 30)}s` }"
          />
          <!-- Hero gradient overlay (always present) -->
          <div class="csv-card-hero-overlay" />

          <!-- Platform wheel logo (icon moved to bottom bar) -->
          <div v-if="plat.wheel_path" class="csv-card-logo-wrap">
            <img
              :src="plat.wheel_path"
              class="csv-card-wheel"
              :alt="plat.name"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
          </div>

          <!-- Platform name + meta -->
          <div class="csv-card-info">
            <div class="csv-card-name-wrap">
              <img
                :src="`/platforms/names/${plat.fs_slug}.svg`"
                :alt="plat.name"
                class="csv-card-name-logo"
                @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLElement).nextElementSibling?.removeAttribute('style')"
              />
              <span class="csv-card-name" style="display:none">{{ plat.name }}</span>
            </div>
            <div v-if="i === systemIndex && plat.release_year_platform" class="csv-card-meta">
              <span>{{ plat.release_year_platform }}</span>
            </div>
          </div>

          <!-- ROM count badge on active -->
          <div v-if="i === systemIndex" class="csv-card-count">
            {{ plat.rom_count === 1 ? t('couch.rom_count_1') : t('couch.roms_count', { count: plat.rom_count }) }}
          </div>
        </div>
      </div>
    </div>

    <!-- ══ BOTTOM INFO BAR ══ -->
    <div class="csv-bottom">
      <div class="csv-bottom-left">
        <!-- Platform icon - centered above description -->
        <img
          v-if="current.wheel_path || true"
          :key="'icon-' + current.fs_slug"
          :src="`/platforms/icons/${current.fs_slug}.png`"
          class="csv-bottom-icon"
          :alt="current.name"
          @error="($event.target as HTMLImageElement).style.display='none'"
        />
        <!-- Platform description (scrolls if too long) - :key forces reset on platform change -->
        <div v-if="platformDescription" class="csv-desc-outer" :key="'desc-' + current.fs_slug">
          <div class="csv-desc">{{ platformDescription }}</div>
        </div>
      </div>
      <div class="csv-bottom-right">
        <!-- System number indicator -->
        <div class="csv-sys-indicator">
          <div
            v-for="(_, i) in Math.min(platforms.length, 12)"
            :key="i"
            class="csv-sys-dot"
            :class="{ active: i === Math.min(systemIndex, 11) }"
          />
        </div>
        <div class="csv-sys-label">{{ systemIndex + 1 }} / {{ platforms.length }}</div>
      </div>
    </div>

    <!-- Arrow navigation hints -->
    <button class="csv-arrow csv-arrow--left"  @click="go(-1)" :disabled="systemIndex === 0">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <button class="csv-arrow csv-arrow--right" @click="go(1)"  :disabled="systemIndex === platforms.length - 1">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
    </button>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { useCouchNav } from '@/composables/useCouchNav'
import { useCouchTheme } from '@/composables/useCouchTheme'
import { usePlatformMetaStore } from '@/stores/platformMeta'
import client from '@/services/api/client'

export interface CouchPlatform {
  id:                   number
  slug:                 string
  fs_slug:              string
  name:                 string
  rom_count:            number
  cover_path:           string | null
  cover_aspect:         string | null
  photo_path:           string | null
  system_color:         string | null
  description:          string | null
  manufacturer:         string | null
  release_year_platform: number | null
  generation:           number | null
  wheel_path:           string | null
}

const props = defineProps<{ platforms: CouchPlatform[]; modelValue: number }>()
const emit  = defineEmits<{ 'update:modelValue': [n: number]; select: [p: CouchPlatform]; menu: [] }>()

const { t } = useI18n()
const { theme } = useCouchTheme()
const platformMeta = usePlatformMetaStore()

// Load XML metadata once
onMounted(() => { platformMeta.fetchIfNeeded() })

const CARD_W    = 340
const CARD_STEP = 360

const systemIndex = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const current = computed(() => props.platforms[systemIndex.value] ?? {} as CouchPlatform)

// Locale-aware description: XML(user lang) > Wiki(DB) > XML(English)
const platformDescription = computed(() => {
  const fs = current.value.fs_slug
  if (!fs) return ''
  const lang = localStorage.getItem('gd3_locale') || 'en'
  const d = platformMeta.meta[fs]?.descriptions
  const xmlLocal = d?.[lang] || ''
  const wiki = current.value.description || ''
  const xmlEn = d?.['en'] || ''
  return xmlLocal || wiki || xmlEn
})

// Gradient fallback shown on the layer when the img fails to load
const layerBgStyle = computed(() => {
  const p = current.value
  const col = p.system_color
    ? `#${p.system_color}`
    : `hsl(${slugHue(p.fs_slug ?? '')}, 60%, 28%)`
  return { background: `radial-gradient(ellipse at 35% 55%, ${col} 0%, #070510 70%)` }
})

// Map a slug string to a hue value 0-360 deterministically
function slugHue(slug: string): number {
  let h = 0
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) & 0xffff
  return h % 360
}

const platformAccent = computed(() => {
  const col = current.value.system_color
  return col ? { '--csv-platform-color': `#${col}` } : {}
})

function go(dir: number) {
  const next = systemIndex.value + dir
  if (next < 0 || next >= props.platforms.length) return
  systemIndex.value = next
}

function onCardClick(i: number) {
  if (i === systemIndex.value) {
    emit('select', current.value)
  } else {
    systemIndex.value = i
  }
}

// Lazy-load platform details (photo, description, manufacturer) for adjacent platforms
const loaded = new Set<string>()

async function loadPlatformDetails(slug: string, fsSlug: string) {
  if (!slug || loaded.has(slug)) return
  loaded.add(slug)
  try {
    const { data } = await client.get(`/roms/platforms/${slug}`)
    const idx = props.platforms.findIndex(p => p.fs_slug === fsSlug)
    if (idx === -1) return
    const p = props.platforms[idx]
    p.photo_path            = data.photo_path           ?? p.photo_path
    p.description           = data.description          ?? p.description
    p.manufacturer          = data.manufacturer         ?? p.manufacturer
    p.release_year_platform = data.release_year_platform ?? p.release_year_platform
    p.generation            = data.generation           ?? p.generation
    // wheel from name logo
    if (data.name_logo_path) p.wheel_path = data.name_logo_path
  } catch { /* silent */ }
}

watch(systemIndex, (idx) => {
  // Load current + adjacent platforms
  for (let d = -1; d <= 1; d++) {
    const i = idx + d
    if (i >= 0 && i < props.platforms.length) {
      const p = props.platforms[i]
      loadPlatformDetails(p.slug, p.fs_slug)
    }
  }
}, { immediate: true })

// Keyboard/gamepad navigation
useCouchNav({
  left:    () => go(-1),
  right:   () => go(1),
  confirm: () => emit('select', current.value),
  menu:    () => emit('menu'),
})
</script>

<style scoped>
.csv-root {
  position: fixed; inset: 0; z-index: 100;
  display: flex; flex-direction: column;
  overflow: hidden; user-select: none;
  --csv-accent: #7c3aed;
}

/* ── Themes ── */
.csv-theme--noir  {
  --csv-accent: #c9a84c;
  --csv-font: Georgia, 'Times New Roman', serif;
  --csv-card-bg: rgba(18, 12, 4, .82);
  --csv-card-border: rgba(201,168,76,.25);
}
.csv-theme--aura  {
  --csv-accent: var(--csv-platform-color, #7c3aed);
  --csv-font: 'Segoe UI', system-ui, sans-serif;
  --csv-card-bg: rgba(8, 4, 24, .55);
  --csv-card-border: rgba(255,255,255,.08);
}
.csv-theme--slick {
  --csv-accent: #cc0000;
  --csv-font: 'Arial Narrow', 'Arial', sans-serif;
  --csv-card-bg: rgba(4, 0, 0, .85);
  --csv-card-border: rgba(204,0,0,.2);
}

/* ── Background ── */
@keyframes csv-kenburns {
  0%   { transform: scale(1.06) translate(0%,    0%); }
  33%  { transform: scale(1.13) translate(-3%,  -1.5%); }
  66%  { transform: scale(1.10) translate(2%,    1%); }
  100% { transform: scale(1.06) translate(0%,    0%); }
}
/* Layer: gradient fallback shown when img fails */
.csv-bg-layer {
  position: absolute; inset: 0; overflow: hidden;
}
/* Actual fanart/cover image with Ken Burns */
.csv-bg-img {
  position: absolute; inset: -10px;
  width: calc(100% + 20px); height: calc(100% + 20px);
  object-fit: cover; object-position: center;
  animation: csv-kenburns 44s ease-in-out infinite;
  will-change: transform;
  transform-origin: center center;
}
/* Per-theme blur/tint on the background image */
.csv-theme--noir  .csv-bg-img { filter: blur(10px) brightness(.55) saturate(.8) sepia(.3); }
.csv-theme--aura  .csv-bg-img { filter: blur(8px)  brightness(.65) saturate(1.8); }
.csv-theme--slick .csv-bg-img { filter: blur(12px) brightness(.48) saturate(.5); }

.csv-bg-enter-active, .csv-bg-leave-active { transition: opacity .6s ease; }
.csv-bg-enter-from, .csv-bg-leave-to { opacity: 0; }

.csv-bg-overlay {
  position: absolute; inset: 0;
}
.csv-theme--noir  .csv-bg-overlay {
  background: linear-gradient(to bottom,
    rgba(20,10,0,.4) 0%, rgba(10,6,0,.65) 50%, rgba(5,3,0,.92) 100%);
}
.csv-theme--aura  .csv-bg-overlay {
  background: linear-gradient(to bottom,
    rgba(0,0,20,.3) 0%, rgba(0,0,15,.55) 50%, rgba(0,0,8,.88) 100%);
}
.csv-theme--slick .csv-bg-overlay {
  background: linear-gradient(to bottom,
    rgba(0,0,0,.5) 0%, rgba(0,0,0,.7) 50%, rgba(0,0,0,.95) 100%);
}

.csv-bg-vignette {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 50% 50%, transparent 35%, rgba(0,0,0,.75) 100%);
}

/* Noir film grain overlay */
.csv-noir-grain {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  opacity: .04;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-size: 256px 256px;
  mix-blend-mode: overlay;
}

/* Slick scanlines */
.csv-slick-lines {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0px, transparent 3px,
    rgba(0,0,0,.12) 3px, rgba(0,0,0,.12) 4px
  );
  opacity: .6;
}

/* ── Header ── */
.csv-header {
  position: relative; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 32px; flex-shrink: 0;
}
.csv-logo { height: 32px; opacity: .6; }
.csv-nav-hint { font-size: 11px; color: rgba(255,255,255,.35); letter-spacing: .08em; }
.csv-nav-hint kbd {
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-xs, 4px); padding: 1px 5px; font-size: var(--fs-xs, 10px); font-family: inherit;
}

/* ── Carousel ── */
.csv-carousel-area {
  position: relative; z-index: 10; flex: 1;
  display: flex; align-items: center;
  overflow: hidden; perspective: 1200px;
}

.csv-carousel-track {
  position: absolute;
  height: 100%; display: flex; align-items: center;
  transition: transform .45s cubic-bezier(.25,.46,.45,.94);
}

.csv-plat-card {
  position: absolute; top: 50%; transform-origin: center center;
  width: 340px; min-height: 420px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-5, 20px); padding: 32px 24px;
  cursor: pointer; overflow: hidden;
  transition: transform .45s cubic-bezier(.25,.46,.45,.94), opacity .45s ease, filter .45s ease;
  transform: translateY(-50%) scale(1);
  background: var(--csv-card-bg, rgba(0,0,0,.5));
  backdrop-filter: blur(14px) saturate(1.2);
  border: 1px solid var(--csv-card-border, rgba(255,255,255,.08));
}

/* Console hardware photo inside the card - Ken Burns animation */
.csv-card-photo {
  position: absolute; inset: -8%; z-index: 0;
  background-size: cover; background-position: center;
  opacity: 0.45; transition: opacity .4s ease;
  animation: csv-kb 32s ease-in-out infinite;
  will-change: transform;
}
.csv-plat-card--active .csv-card-photo { opacity: 0.6; }
@keyframes csv-kb {
  0%   { transform: scale(1.0) translate(0%, 0%); }
  33%  { transform: scale(1.08) translate(-2%, -1%); }
  66%  { transform: scale(1.04) translate(1.5%, 1%); }
  100% { transform: scale(1.0) translate(0%, 0%); }
}

/* Hero gradient overlay - darkens bottom for readability */
.csv-card-hero-overlay {
  position: absolute; inset: 0; z-index: 1;
  background: linear-gradient(
    160deg,
    rgba(0,0,0,.05) 0%,
    rgba(0,0,0,.15) 35%,
    rgba(0,0,0,.80) 100%
  );
}
.csv-theme--noir .csv-card-hero-overlay {
  background: linear-gradient(160deg, rgba(10,6,0,.1) 0%, rgba(10,6,0,.25) 35%, rgba(5,3,0,.88) 100%);
}
.csv-theme--slick .csv-card-hero-overlay {
  background: linear-gradient(160deg, rgba(0,0,0,.2) 0%, rgba(0,0,0,.4) 35%, rgba(0,0,0,.92) 100%);
}

/* Keep card content above photo & overlay */
.csv-card-logo-wrap,
.csv-card-info,
.csv-card-count {
  position: relative; z-index: 2;
}
/* Per-theme card shape */
.csv-theme--noir  .csv-plat-card { border-radius: 6px; }
.csv-theme--aura  .csv-plat-card { border-radius: 20px; }
.csv-theme--slick .csv-plat-card { border-radius: 2px; }

/* Active card */
.csv-plat-card--active {
  transform: translateY(-50%) scale(1.0) !important;
  opacity: 1 !important;
  border-color: var(--plat-color, var(--csv-accent));
  filter: none !important;
}
.csv-theme--noir .csv-plat-card--active {
  box-shadow:
    0 0 0 1px var(--csv-accent),
    0 2px 40px rgba(0,0,0,.8),
    0 0 60px rgba(201,168,76,.15) inset;
}
.csv-theme--aura .csv-plat-card--active {
  box-shadow:
    0 0 0 1px var(--plat-color, var(--csv-accent)),
    0 0 60px rgba(0,0,0,.6),
    0 0 40px var(--plat-color, var(--csv-accent)) inset;
}
.csv-theme--slick .csv-plat-card--active {
  box-shadow:
    0 0 0 2px var(--csv-accent),
    0 0 30px rgba(204,0,0,.3),
    inset 0 0 20px rgba(204,0,0,.08);
}
/* Adjacent cards */
.csv-plat-card--adj1 {
  transform: translateY(-50%) scale(.75) !important;
  opacity: .5 !important; filter: brightness(.7);
}
.csv-plat-card--adj2 {
  transform: translateY(-50%) scale(.6) !important;
  opacity: .25 !important; filter: brightness(.5);
}
.csv-plat-card--far {
  transform: translateY(-50%) scale(.5) !important;
  opacity: 0 !important; pointer-events: none;
}

.csv-card-logo-wrap {
  display: flex; align-items: center; justify-content: center;
}
.csv-card-wheel {
  max-width: 200px; max-height: 140px;
  object-fit: contain; filter: drop-shadow(0 0 16px rgba(255,255,255,.15));
}
/* Platform icon - centered above the description in the bottom bar */
.csv-bottom-icon {
  display: block; margin: 0 auto 10px;
  width: 350px; height: auto; object-fit: contain;
  filter: drop-shadow(0 0 12px rgba(255,255,255,.2));
  opacity: 0.7;
}

.csv-card-info { text-align: center; flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }

/* Platform name: SVG logo preferred, text fallback */
.csv-card-name-wrap {
  display: flex; align-items: center; justify-content: center;
  min-height: 60px;
}
.csv-card-name-logo {
  width: 280px; height: auto;
  max-height: 60px;
  object-fit: contain;
  filter: drop-shadow(0 2px 10px rgba(0,0,0,.9)) brightness(1.15);
}
.csv-plat-card--active .csv-card-name-logo {
  width: 300px;
  max-height: 70px;
}
.csv-card-name {
  font-size: 20px; font-weight: 800; color: #fff;
  font-family: var(--csv-font, system-ui);
  text-shadow: 0 2px 8px rgba(0,0,0,.5);
  letter-spacing: -.01em;
}
.csv-theme--slick .csv-card-name {
  text-transform: uppercase; letter-spacing: .05em; font-size: 17px;
}
.csv-theme--noir .csv-card-name {
  letter-spacing: .03em; font-size: var(--fs-xl, 18px); font-style: italic;
}
.csv-card-meta {
  margin-top: 6px; display: flex; gap: 10px; justify-content: center;
  font-size: 11px; color: rgba(255,255,255,.45); letter-spacing: .06em; text-transform: uppercase;
}

.csv-card-count {
  background: var(--plat-color, var(--csv-accent));
  color: #fff; font-size: 11px; font-weight: 800;
  padding: 4px 14px; border-radius: 20px; letter-spacing: .06em;
  text-shadow: none;
}

/* ── Bottom bar ── */
.csv-bottom {
  position: relative; z-index: 10;
  display: flex; align-items: flex-end; justify-content: space-between;
  padding: 20px 40px 32px;
}
/* Scrolling description - 6 visible lines */
.csv-desc-outer {
  max-width: 540px; height: 130px; overflow: hidden; position: relative;
}
.csv-desc-outer::after {
  content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 30px;
  background: linear-gradient(to top, rgba(0,0,0,.75), transparent);
  pointer-events: none;
}
.csv-desc {
  font-size: 13px; color: rgba(255,255,255,.55);
  line-height: 1.65;
  animation: csv-desc-scroll 22s ease-in-out 2s infinite alternate;
  will-change: transform;
}
@keyframes csv-desc-scroll {
  0%,  15% { transform: translateY(0); }
  85%, 100% { transform: translateY(calc(-100% + 130px)); }
}
.csv-sys-indicator { display: flex; gap: 5px; justify-content: flex-end; margin-bottom: 4px; }
.csv-sys-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,.2); transition: all .3s;
}
.csv-sys-dot.active { background: var(--csv-accent); width: 18px; border-radius: 3px; }
.csv-sys-label { font-size: 11px; color: rgba(255,255,255,.3); text-align: right; }

/* ── Arrow buttons ── */
.csv-arrow {
  position: absolute; top: 50%; transform: translateY(-50%);
  z-index: 20; background: rgba(0,0,0,.4); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.6); border-radius: 50%; width: 52px; height: 52px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .2s;
}
.csv-arrow:hover:not(:disabled) { background: rgba(0,0,0,.7); color: #fff; border-color: var(--csv-accent); }
.csv-arrow:disabled { opacity: .15; cursor: default; }
.csv-arrow--left  { left: 20px; }
.csv-arrow--right { right: 20px; }
</style>
