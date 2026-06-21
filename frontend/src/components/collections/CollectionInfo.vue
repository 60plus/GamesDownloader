<!--
  CollectionInfo - the About + Details block for a collection detail page.

  Two layouts (the cover grid and the list view want different placements):
    layout="side" - a panel to the RIGHT of the cover grid (like a game detail).
    layout="band" - a full-width horizontal band above the games list. The About
                    sits over the collection hero (obeying the theme hero motion
                    settings); the centred text auto-scrolls when it overflows.
  Details are rendered by the shared <CollectionDetails> (the same table the
  browse rows use) so every surface reads identically.
-->
<template>
  <div class="ci" :class="`ci--${layout}`">
    <!-- Band (list view) leads with the collection cover so it reads as a list row. -->
    <div v-if="layout === 'band'" class="ci-cover">
      <div class="ci-cover-box">
        <CollectionCover :cover="detail.cover_path" :covers="detail.member_covers" :name="detail.name" color="var(--pl)" />
      </div>
    </div>
    <!-- Name column (mirrors list-info): logo/name -> years -> games -> owner, each on its own line. -->
    <div v-if="layout === 'band'" class="ci-name">
      <div class="ci-name-title">
        <img v-if="detail.logo_path" :src="detail.logo_path" :alt="detail.name" class="ci-name-logo" />
        <span v-else>{{ detail.name }}</span>
      </div>
      <div class="ci-name-meta">
        <span v-if="yearRange">{{ yearRange }}</span>
        <span v-if="detail.member_count != null">{{ detail.member_count === 1 ? t('home.game_count', { count: detail.member_count }) : t('home.game_count_plural', { count: detail.member_count }) }}</span>
      </div>
      <span v-if="detail.owner_username" class="ci-owner-badge" :title="'Owner: ' + detail.owner_username">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        {{ detail.owner_username }}
      </span>
    </div>
    <!-- Side (grid view): the collection cover sits above the framed About / Details. -->
    <div v-if="layout === 'side'" class="ci-side-cover">
      <div class="ci-side-cover-box">
        <CollectionCover :cover="detail.cover_path" :covers="detail.member_covers" :name="detail.name" color="var(--pl)" />
      </div>
    </div>
    <div class="ci-about">
      <!-- Band: the collection hero behind the About, with theme motion. -->
      <template v-if="layout === 'band' && bandHero">
        <img :src="bandHero" :alt="detail.name" :class="['ci-about-hero', heroAnimClass]" />
        <div class="ci-about-hero-shade" />
      </template>
      <div class="ci-label">{{ t('collections.about') }}</div>
      <!-- HTML-aware like the game description (sanitised). In the band the inner
           block auto-scrolls when the text is taller than the panel (no scrollbar). -->
      <div v-if="detail.description" class="ci-about-text" ref="aboutWrapEl">
        <div class="ci-about-text-inner" ref="aboutInnerEl" :class="{ 'is-autoscroll': autoScroll }" :style="autoScrollVars" v-html="sanitizeHtml(detail.description)"></div>
      </div>
    </div>
    <div class="ci-details">
      <div class="ci-label">{{ t('detail.details') }}</div>
      <CollectionDetails :detail="detail" :compact="layout === 'band'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { sanitizeHtml } from '@/utils/sanitize'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import CollectionDetails from '@/components/collections/CollectionDetails.vue'
import { useThemeStore } from '@/stores/theme'
import { useI18n } from '@/i18n'

const props = defineProps<{ detail: any; layout: 'band' | 'side' }>()
const { t } = useI18n()
const themeStore = useThemeStore()

const yearRange = computed(() => {
  const c = props.detail || {}
  if (c.start_year && c.end_year && c.start_year !== c.end_year) return `${c.start_year} - ${c.end_year}`
  return c.start_year ? String(c.start_year) : (c.end_year ? String(c.end_year) : '')
})

// Hero for the band About: the collection's own hero, else a member's.
const bandHero = computed(() => props.layout === 'band'
  ? (props.detail?.hero_path || props.detail?.member_heroes?.[0] || '')
  : '')
// Same motion as a game hero - obeys the theme's hero / animations settings.
const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `ci-about-hero--${themeStore.heroAnimStyle}`
})

// Auto-scroll the About when it is taller than the band panel (no scrollbar).
const aboutWrapEl = ref<HTMLElement | null>(null)
const aboutInnerEl = ref<HTMLElement | null>(null)
const autoScroll = ref(false)
const autoScrollVars = ref<Record<string, string>>({})
function measureAutoScroll() {
  const wrap = aboutWrapEl.value, inner = aboutInnerEl.value
  if (!wrap || !inner) { autoScroll.value = false; return }
  // Overflow beyond the box (even a single line) is scrolled smoothly, never cut.
  const dist = inner.scrollHeight - wrap.clientHeight
  if (dist > 4) {
    autoScroll.value = true
    autoScrollVars.value = {
      '--ci-scroll-dist': dist + 'px',
      // Constant, gentle speed so a one-line overflow glides instead of jumping.
      '--ci-scroll-dur': Math.max(9, Math.round(dist / 12)) + 's',
    }
  } else {
    autoScroll.value = false
  }
}
function onResize() { nextTick(measureAutoScroll) }
onMounted(() => { nextTick(measureAutoScroll); window.addEventListener('resize', onResize) })
onUnmounted(() => window.removeEventListener('resize', onResize))
watch(() => [props.detail?.description, props.layout, props.detail?.slug], () => nextTick(measureAutoScroll))
</script>

<style scoped>
.ci { display: flex; gap: 16px; flex-shrink: 0; min-height: 0; }
.ci-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 10px;
}
.ci-about-text { margin: 0; font-size: 13px; line-height: 1.65; color: var(--text-secondary, #cbd5e1); white-space: pre-line; }

/* ── layout="band" - a list-row-styled header (cover | About | Details) ─────── */
.ci--band {
  align-self: stretch; height: 260px;
  /* Fixed header outside the scroll (rows clip cleanly below it). The right inset
     matches the rows' (grid-scroll padding-right 8px + 6px scrollbar gutter = 14px)
     so the band's segments line up 1:1 with the rows while the band itself spans
     the full width like the title bar. */
  padding-right: 14px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid var(--glass-border); border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2); gap: 0; overflow: hidden;
}
.ci--band .ci-cover { width: 200px; flex-shrink: 0; padding: 10px; box-sizing: border-box; display: flex; align-items: center; }
/* Square box (matches the square collection tiles the fan is calibrated for) so
   the fanned cover sits vertically centred instead of pinned to the bottom. A
   subtle backing frames a contained custom cover of any aspect ratio. */
.ci-cover-box { position: relative; width: 100%; aspect-ratio: 1 / 1; border-radius: var(--radius-sm, 8px); overflow: hidden; background: rgba(0,0,0,.18); }
/* Name column - same box as the rows' list-info (200 + 32 pad + 1 border = 233). */
.ci--band .ci-name {
  width: 200px; flex-shrink: 0; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  text-align: center; gap: var(--space-1, 4px); padding: 10px 16px;
  border-left: 1px solid var(--glass-border);
}
.ci-name-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); overflow: hidden; min-height: 20px; }
.ci-name-title > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ci-name-meta { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 6px; }
.ci-name-logo { max-height: 34px; max-width: 160px; width: auto; object-fit: contain; filter: drop-shadow(0 1px 4px rgba(0,0,0,.5)); }
.ci-owner-badge { display: inline-flex; align-items: center; gap: var(--space-1, 4px); padding: 2px 10px; border-radius: 10px; background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); font-size: var(--fs-xs, 10px); font-weight: 600; color: var(--muted); white-space: nowrap; margin-top: 4px; }

/* Band About: hero behind, centred auto-scrolling text over it. */
.ci--band .ci-about { position: relative; flex: 1; min-width: 0; min-height: 0; padding: 14px 20px; overflow: hidden; display: flex; flex-direction: column; border-left: 1px solid var(--glass-border); }
.ci-about-hero { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; filter: brightness(.30); z-index: 0; }
.ci-about-hero-shade { position: absolute; inset: 0; background: linear-gradient(to right, rgba(0,0,0,.5) 0%, rgba(0,0,0,.2) 50%, rgba(0,0,0,.5) 100%); z-index: 0; }
.ci--band .ci-about .ci-label { position: relative; z-index: 1; text-align: center; }
.ci--band .ci-about .ci-about-text { position: relative; z-index: 1; flex: 1; min-height: 0; overflow: hidden; text-align: center; }
.ci-about-text-inner.is-autoscroll { animation: ci-about-autoscroll var(--ci-scroll-dur, 18s) ease-in-out infinite alternate; }
@keyframes ci-about-autoscroll { 0%, 12% { transform: translateY(0); } 88%, 100% { transform: translateY(calc(-1 * var(--ci-scroll-dist, 0px))); } }
/* Hero motion - mirrors the game list-row hero, gated by the theme settings. */
.ci-about-hero--kenburns { animation: ci-about-kb calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.ci-about-hero--drift { animation: ci-about-drift calc(30s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.ci-about-hero--pulse { animation: ci-about-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
@keyframes ci-about-kb { 0% { transform: scale(1.05) translateX(0); } 50% { transform: scale(1.12) translateX(-3%); } 100% { transform: scale(1.05) translateX(0); } }
@keyframes ci-about-drift { 0% { transform: translateX(0) scale(1.04); } 50% { transform: translateX(-4%) scale(1.04); } 100% { transform: translateX(0) scale(1.04); } }
@keyframes ci-about-pulse { 0%,100% { transform: scale(1.02); } 50% { transform: scale(1.08); } }
[data-animations="false"] .ci-about-hero--kenburns,
[data-animations="false"] .ci-about-hero--drift,
[data-animations="false"] .ci-about-hero--pulse { animation: none; }

/* Spans the rows' whole right block - list-qf-col (230) + list-right (120, pinned)
   = 350 (all border-box) - so its left edge sits exactly where the hero ends and
   ci-about ends up the same width as list-hero. */
.ci--band .ci-details { box-sizing: border-box; width: 350px; flex-shrink: 0; min-height: 0; padding: 14px 18px; display: flex; flex-direction: column; justify-content: center; border-left: 1px solid var(--glass-border); background: rgba(255,255,255,.02); }

/* ── layout="side" - a fixed, full-height vertical panel beside the cover grid:
   collection cover, then the About and Details in theme-accent framed boxes. The
   panel itself never scrolls (only the cover grid does); the About auto-scrolls
   when it is taller than the space it gets. ───────────────────────────────── */
.ci--side { width: 430px; flex-shrink: 0; align-self: stretch; min-height: 0; display: flex; flex-direction: column; gap: 14px; overflow: hidden; }
/* Cover section: full-width themed frame with the cover centred inside. */
.ci-side-cover { flex-shrink: 0; display: flex; justify-content: center; padding: 12px; border-radius: var(--radius-sm, 8px); background: var(--glass-bg); border: 1px solid color-mix(in srgb, var(--pl) 22%, var(--glass-border)); }
.ci-side-cover-box { position: relative; width: 100%; max-width: 300px; aspect-ratio: 1 / 1; border-radius: var(--radius-sm, 8px); overflow: hidden; background: rgba(0,0,0,.18); }
/* About: themed frame, takes the remaining height, auto-scrolls when it overflows. */
.ci--side .ci-about { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--glass-bg); border: 1px solid color-mix(in srgb, var(--pl) 22%, var(--glass-border)); border-radius: var(--radius-sm, 8px); padding: 14px 16px; }
.ci--side .ci-about .ci-about-text { flex: 1; min-height: 0; overflow: hidden; }
.ci--side .ci-details { flex-shrink: 0; width: 100%; }
.ci--side :deep(.cd) { border-color: color-mix(in srgb, var(--pl) 22%, var(--glass-border)); }
</style>
