<!--
  CollectionInfo - the About + Details block for a collection detail page.

  Two layouts (the cover grid and the list view want different placements):
    layout="side" - a panel to the RIGHT of the cover grid (like a game detail).
    layout="band" - a full-width horizontal band above the games list; the About
                    text is centred.
  Details mirror the game-detail "gd-dlist" bordered table so the two look alike.
-->
<template>
  <div class="ci" :class="`ci--${layout}`">
    <!-- Band (list view) leads with the collection cover so it reads as a list row. -->
    <div v-if="layout === 'band'" class="ci-cover">
      <div class="ci-cover-box">
        <CollectionCover :cover="detail.cover_path" :covers="detail.member_covers" :name="detail.name" color="var(--pl)" />
      </div>
    </div>
    <!-- Name column (mirrors list-info) so the band's segments line up 1:1 with the game rows. -->
    <div v-if="layout === 'band'" class="ci-name">
      <div class="ci-name-title"><span>{{ detail.name }}</span></div>
      <div class="ci-name-meta">
        <span v-if="detail.member_count != null">{{ detail.member_count === 1 ? t('home.game_count', { count: detail.member_count }) : t('home.game_count_plural', { count: detail.member_count }) }}</span>
        <span v-if="detail.member_count != null && yearRange" class="ci-name-sep" />
        <span v-if="yearRange">{{ yearRange }}</span>
      </div>
    </div>
    <div class="ci-about">
      <div class="ci-label">{{ t('collections.about') }}</div>
      <!-- HTML-aware like the game description (sanitised); plain text + newlines
           still render thanks to white-space: pre-line. -->
      <div v-if="detail.description" class="ci-about-text" v-html="sanitizeHtml(detail.description)"></div>
    </div>
    <div class="ci-details">
      <div class="ci-label">{{ t('detail.details') }}</div>
      <div class="ci-dl">
        <template v-if="detail.developers?.length">
          <span class="ci-dk">{{ t('detail.developer') }}</span>
          <span class="ci-dv">{{ aggList(detail.developers) }}</span>
        </template>
        <template v-if="detail.publishers?.length">
          <span class="ci-dk">{{ t('detail.publisher') }}</span>
          <span class="ci-dv">{{ aggList(detail.publishers) }}</span>
        </template>
        <template v-if="yearRange">
          <span class="ci-dk">{{ t('detail.released') }}</span>
          <span class="ci-dv">{{ yearRange }}</span>
        </template>
        <template v-if="os.windows || os.mac || os.linux">
          <span class="ci-dk">{{ t('library.platform_label') }}</span>
          <span class="ci-dv ci-os">
            <span v-if="os.windows" class="ci-os-chip ci-os-chip--win" title="Windows"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/></svg></span>
            <span v-if="os.mac" class="ci-os-chip ci-os-chip--mac" title="macOS"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg></span>
            <span v-if="os.linux" class="ci-os-chip ci-os-chip--linux" title="Linux"><img src="/icons/os-linux.svg" width="14" height="14" alt="Linux" /></span>
          </span>
        </template>
        <template v-if="langs.length">
          <span class="ci-dk">{{ t('detail.languages') }}</span>
          <span class="ci-dv ci-langs">
            <span v-for="l in langs" :key="l.name" class="ci-lang-flag" :title="l.name">
              <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span><span v-else>{{ l.name }}</span>
            </span>
          </span>
        </template>
        <template v-if="detail.hltb_main_s || detail.hltb_complete_s">
          <span class="ci-dk">{{ t('detail.time_to_beat') }}</span>
          <span class="ci-dv ci-ttb">
            <span v-if="detail.hltb_main_s">{{ t('detail.hltb_main') }} {{ fmtHltb(detail.hltb_main_s) }}</span>
            <span v-if="detail.hltb_complete_s">{{ t('detail.hltb_complete') }} {{ fmtHltb(detail.hltb_complete_s) }}</span>
          </span>
        </template>
        <template v-if="detail.rating != null">
          <span class="ci-dk">{{ t('library.rating') }}</span>
          <span class="ci-dv ci-rating">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            {{ Number(detail.rating).toFixed(1) }}
          </span>
        </template>
        <template v-if="(detail.genres || []).length">
          <span class="ci-dk">{{ t('detail.genres') }}</span>
          <span class="ci-dv ci-tags"><span v-for="g in (detail.genres || []).slice(0, 6)" :key="g" class="ci-genre-chip">{{ g }}</span></span>
        </template>
        <template v-if="detail.sources?.length">
          <span class="ci-dk">{{ t('detail.source') }}</span>
          <span class="ci-dv">{{ detail.sources.join(', ') }}</span>
        </template>
        <span class="ci-dk">{{ t('library.games') }}</span>
        <span class="ci-dv">{{ detail.member_count }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { buildLanguageList } from '@/utils/langMap'
import { sanitizeHtml } from '@/utils/sanitize'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import { useI18n } from '@/i18n'

const props = defineProps<{ detail: any; layout: 'band' | 'side' }>()
const { t } = useI18n()

const os = computed(() => props.detail?.platforms || { windows: false, mac: false, linux: false })
const langs = computed(() => buildLanguageList(props.detail?.languages))
const yearRange = computed(() => {
  const c = props.detail || {}
  if (c.start_year && c.end_year && c.start_year !== c.end_year) return `${c.start_year} - ${c.end_year}`
  return c.start_year ? String(c.start_year) : (c.end_year ? String(c.end_year) : '')
})
function aggList(arr: string[] | undefined): string {
  const a = arr || []
  if (a.length <= 2) return a.join(', ')
  return a.slice(0, 2).join(', ') + ' +' + (a.length - 2)
}
function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600); const m = Math.round((s % 3600) / 60)
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`
}
</script>

<style scoped>
.ci { display: flex; gap: 16px; flex-shrink: 0; min-height: 0; }
.ci-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 10px;
}
.ci-about-text { margin: 0; font-size: 13px; line-height: 1.65; color: var(--text-secondary, #cbd5e1); white-space: pre-line; }

/* ── Details: mirror the game-detail gd-dlist bordered table ───────────────── */
.ci-dl {
  display: grid; grid-template-columns: auto 1fr; gap: 0;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 6px); overflow: hidden;
}
.ci-dk, .ci-dv { padding: 10px 14px; font-size: 13px; }
.ci-dk {
  color: var(--muted); font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px; white-space: nowrap;
  border-right: 1px solid var(--glass-border); border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.04); display: flex; align-items: center;
}
.ci-dv { color: var(--text); border-bottom: 1px solid var(--glass-border); display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.ci-dk:last-of-type { border-bottom: none; }
.ci-dk:last-of-type + .ci-dv { border-bottom: none; }
.ci-os { gap: 4px; }
.ci-os-chip { display: inline-flex; align-items: center; justify-content: center; }
.ci-os-chip--win { color: #60a5fa; }
.ci-os-chip--mac { color: #c4b5fd; }
.ci-os-chip--linux { color: #facc15; }
.ci-langs { gap: 5px; }
.ci-lang-flag { display: inline-flex; align-items: center; font-size: 16px; line-height: 1; }
.ci-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.ci-ttb { flex-direction: column; align-items: flex-start; gap: 1px; }
.ci-rating { gap: 5px; font-weight: 700; }
.ci-genre-chip { padding: 1px 7px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); background: color-mix(in srgb, var(--pl) 14%, transparent); color: var(--pl-light, #a78bfa); }

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
   the fanned cover sits vertically centred instead of pinned to the bottom. */
.ci-cover-box { position: relative; width: 100%; aspect-ratio: 1 / 1; border-radius: var(--radius-sm, 8px); overflow: hidden; }
/* Name column - same box as the rows' list-info (200 + 32 pad + 1 border = 233). */
.ci--band .ci-name {
  width: 200px; flex-shrink: 0; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  text-align: center; gap: var(--space-1, 4px); padding: 10px 16px;
  border-left: 1px solid var(--glass-border);
}
.ci-name-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); overflow: hidden; min-height: 20px; }
.ci-name-title > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ci-name-meta { display: flex; align-items: center; justify-content: center; gap: 6px; flex-wrap: wrap; font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 6px; }
.ci-name-sep::before { content: '·'; }
.ci--band .ci-about { flex: 1; min-width: 0; min-height: 0; padding: 14px 20px; overflow-y: auto; display: flex; flex-direction: column; border-left: 1px solid var(--glass-border); }
.ci--band .ci-about .ci-about-text { text-align: center; flex: 1; }
.ci--band .ci-about .ci-label { text-align: center; }
/* Spans the rows' whole right block - list-qf-col (230) + list-right (120, pinned)
   = 350 (all border-box) - so its left edge sits exactly where the hero ends and
   ci-about ends up the same width as list-hero. Scrolls on its own when facts overflow. */
.ci--band .ci-details { box-sizing: border-box; width: 350px; flex-shrink: 0; min-height: 0; padding: 14px 18px; overflow-y: auto; border-left: 1px solid var(--glass-border); background: rgba(255,255,255,.02); }
/* Match the per-game quickfacts (list-qf) typography so the band's facts and the
   rows' facts read at the same scale (band only; the side panel keeps game-detail size). */
.ci--band .ci-dk { font-size: 9px; padding: 4px 8px; }
.ci--band .ci-dv { font-size: 11px; padding: 4px 8px; }

/* ── layout="side" - panel to the right of the cover grid (grid view) ──────── */
.ci--side { width: 820px; flex-shrink: 0; overflow-y: auto; gap: 18px; padding-bottom: 20px; }
.ci--side .ci-about { flex: 1; min-width: 0; }
.ci--side .ci-details { width: 300px; flex-shrink: 0; }
</style>
