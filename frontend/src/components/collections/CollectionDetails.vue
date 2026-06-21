<!--
  CollectionDetails - the bordered "Details" table for a collection (developer,
  publisher, released, platform, languages, time-to-beat, rating, genres, source,
  games). Mirrors the game-detail "gd-dlist".

  Shared by the detail panel (CollectionInfo band/side) AND the browse list rows
  (CollectionsView) so the same aggregated facts render identically everywhere -
  the value column is wide enough that long aggregated studio names wrap cleanly
  instead of being cut mid-word.

  compact: tighter typography for the list contexts (detail band + browse rows);
  the cover-grid side panel uses the roomier default.
-->
<template>
  <div class="cd" :class="{ 'cd--compact': compact }">
    <template v-if="detail.developers?.length">
      <span class="cd-k">{{ t('detail.developer') }}</span>
      <span class="cd-v cd-v--names">{{ aggList(detail.developers) }}</span>
    </template>
    <template v-if="detail.publishers?.length">
      <span class="cd-k">{{ t('detail.publisher') }}</span>
      <span class="cd-v cd-v--names">{{ aggList(detail.publishers) }}</span>
    </template>
    <template v-if="yearRange">
      <span class="cd-k">{{ t('detail.released') }}</span>
      <span class="cd-v">{{ yearRange }}</span>
    </template>
    <template v-if="os.windows || os.mac || os.linux">
      <span class="cd-k">{{ t('library.platform_label') }}</span>
      <span class="cd-v cd-os">
        <span v-if="os.windows" class="cd-os-chip cd-os-chip--win" title="Windows"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/></svg></span>
        <span v-if="os.mac" class="cd-os-chip cd-os-chip--mac" title="macOS"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg></span>
        <span v-if="os.linux" class="cd-os-chip cd-os-chip--linux" title="Linux"><img src="/icons/os-linux.svg" width="14" height="14" alt="Linux" /></span>
      </span>
    </template>
    <template v-if="langs.length">
      <span class="cd-k">{{ t('detail.languages') }}</span>
      <span class="cd-v cd-langs">
        <span v-for="l in langs" :key="l.name" class="cd-lang-flag" :title="l.name">
          <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span><span v-else>{{ l.name }}</span>
        </span>
      </span>
    </template>
    <template v-if="detail.hltb_main_s || detail.hltb_complete_s">
      <span class="cd-k">{{ t('detail.time_to_beat') }}</span>
      <span class="cd-v cd-ttb">
        <span v-if="detail.hltb_main_s">{{ t('detail.hltb_main') }} {{ fmtHltb(detail.hltb_main_s) }}</span>
        <span v-if="detail.hltb_complete_s">{{ t('detail.hltb_complete') }} {{ fmtHltb(detail.hltb_complete_s) }}</span>
      </span>
    </template>
    <template v-if="detail.rating != null">
      <span class="cd-k">{{ t('library.rating') }}</span>
      <span class="cd-v cd-rating">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        {{ Number(detail.rating).toFixed(1) }}
      </span>
    </template>
    <template v-if="(detail.genres || []).length">
      <span class="cd-k">{{ t('detail.genres') }}</span>
      <span class="cd-v cd-tags"><span v-for="g in (detail.genres || []).slice(0, 6)" :key="g" class="cd-genre-chip">{{ g }}</span></span>
    </template>
    <template v-if="detail.sources?.length">
      <span class="cd-k">{{ t('detail.source') }}</span>
      <span class="cd-v">{{ detail.sources.join(', ') }}</span>
    </template>
    <span class="cd-k">{{ t('library.games') }}</span>
    <span class="cd-v">{{ detail.member_count }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { buildLanguageList } from '@/utils/langMap'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ detail: any; compact?: boolean }>(), { compact: false })
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
/* Bordered two-column table - mirrors the game-detail gd-dlist. */
.cd {
  display: grid; grid-template-columns: auto 1fr; gap: 0; width: 100%;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 6px); overflow: hidden;
}
.cd-k, .cd-v { padding: 10px 14px; font-size: 13px; }
.cd-k {
  color: var(--muted); font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px; white-space: nowrap;
  border-right: 1px solid var(--glass-border); border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.04); display: flex; align-items: center;
}
.cd-v { color: var(--text); border-bottom: 1px solid var(--glass-border); display: flex; flex-wrap: wrap; align-items: center; justify-content: center; text-align: center; gap: 4px; }
.cd-k:last-of-type { border-bottom: none; }
.cd-k:last-of-type + .cd-v { border-bottom: none; }
/* Developer/publisher are aggregated from members (often long studio names);
   clamp to 2 lines so a wide value cell wraps them cleanly without pushing the
   lower facts out. Wide column = no mid-word breaks. */
.cd-v--names { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: break-word; }
.cd-os { gap: 4px; }
.cd-os-chip { display: inline-flex; align-items: center; justify-content: center; }
.cd-os-chip--win { color: #60a5fa; }
.cd-os-chip--mac { color: #c4b5fd; }
.cd-os-chip--linux { color: #facc15; }
.cd-langs { gap: 5px; }
.cd-lang-flag { display: inline-flex; align-items: center; font-size: 16px; line-height: 1; }
.cd-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.cd-ttb { flex-direction: column; align-items: center; gap: 1px; }
.cd-rating { gap: 5px; font-weight: 700; }
.cd-genre-chip { padding: 1px 7px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); background: color-mix(in srgb, var(--pl) 14%, transparent); color: var(--pl-light, #a78bfa); }

/* Compact typography for the list contexts (detail band + browse rows). */
.cd--compact .cd-k { font-size: 9px; padding: 4px 8px; }
.cd--compact .cd-v { font-size: 11px; padding: 4px 8px; }
</style>
