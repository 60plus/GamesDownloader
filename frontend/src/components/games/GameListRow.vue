<!--
  GameListRow - the ONE canonical library list row (cover + info + hero +
  quickfacts + ratings). Used by every list view - Games, GOG, custom libraries
  and collection members - so the same game reads identically everywhere.

  Quickfacts are adaptive: each game shows what it has (download size for GOG
  entries; files + source for library games; language flags whenever present).
  The primary rating shows the GOG mark for GOG-sourced games, a star otherwise.

  Navigation is the host's job: the row emits `open` with the game and each view
  routes it to the right detail page (Games detail, GOG detail, ...).
-->
<template>
  <div class="list-row" @click="openGame">
    <!-- Cover -->
    <div class="list-cover-wrap" @mousemove="onCardMove" @mouseleave="onCardLeave" @mouseenter="onCardEnter">
      <div class="cover-img-wrap">
        <img v-if="game.cover_path || game.cover_url" :src="game.cover_path || game.cover_url" class="list-cover-img" loading="lazy" />
        <div v-else class="list-cover-fallback" />
        <div class="cover-sheen" />
        <div class="cover-overlay" />
        <div v-if="game.download_status === 'completed'" class="list-cover-check" :title="t('detail.available')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
      </div>
    </div>

    <!-- Info (logo when the game has one, otherwise its title) -->
    <div class="list-info">
      <div class="list-title">
        <img v-if="game.logo_path || game.logo_url" :src="game.logo_path || game.logo_url" :alt="game.title" class="list-logo-img" />
        <span v-else>{{ game.title }}</span>
      </div>
      <div class="list-meta">
        <span v-if="game.developer">{{ game.developer }}</span>
        <span v-if="game.release_date">{{ releaseYear(game.release_date) }}</span>
      </div>
      <span v-if="game.owner_username" class="list-owner-badge" :title="'Owner: ' + game.owner_username">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        {{ game.owner_username }}
      </span>
    </div>

    <!-- Hero art + description overlay -->
    <div class="list-hero">
      <img
        v-if="game.background_path || game.background_url || game.cover_path || game.cover_url"
        :src="game.background_path || game.background_url || game.cover_path || game.cover_url || ''"
        :alt="game.title"
        :class="['list-hero-img', listHeroAnimClass]"
        :style="{ animationDelay: (idx * -7) + 's' }"
        loading="lazy"
      />
      <div class="list-hero-overlay" />
      <div v-if="game.description_short || game.description" class="list-hero-desc">
        <p class="list-hero-desc-text">{{ listDescText(game) }}</p>
      </div>
    </div>

    <!-- Quickfacts (adaptive - each game shows what it has) -->
    <div class="list-qf-col">
      <div class="list-qf">
        <div v-if="game.developer" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.developer') }}</span>
          <span class="list-qf-val">{{ game.developer }}</span>
        </div>
        <div v-if="game.publisher && game.publisher !== game.developer" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.publisher') }}</span>
          <span class="list-qf-val">{{ game.publisher }}</span>
        </div>
        <div v-if="(game.genres || []).length" class="list-qf-row">
          <span class="list-qf-label">{{ t('library.genre') }}</span>
          <span class="list-qf-val">
            <span v-for="g in (game.genres || []).slice(0, 3)" :key="g" class="genre-chip">{{ g }}</span>
          </span>
        </div>
        <div v-if="game.os_windows || game.os_mac || game.os_linux" class="list-qf-row">
          <span class="list-qf-label">{{ t('library.platform_label') }}</span>
          <span class="list-qf-val list-qf-os">
            <span v-if="game.os_windows" class="list-os-chip list-os-chip--win" title="Windows">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/></svg>
            </span>
            <span v-if="game.os_mac" class="list-os-chip list-os-chip--mac" title="macOS">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>
            </span>
            <span v-if="game.os_linux" class="list-os-chip list-os-chip--linux" title="Linux">
              <img src="/icons/os-linux.svg" width="14" height="14" alt="Linux" />
            </span>
          </span>
        </div>
        <div v-if="game.release_date" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.released') }}</span>
          <span class="list-qf-val">{{ releaseYear(game.release_date) }}</span>
        </div>
        <div v-if="listDownloadSize(game)" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.size') }}</span>
          <span class="list-qf-val">{{ listDownloadSize(game) }}</span>
        </div>
        <div v-if="langs.length" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.languages') }}</span>
          <span class="list-qf-val list-qf-langs">
            <span v-for="l in langs" :key="l.name" class="list-lang-flag" :title="l.name">
              <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span><span v-else>{{ l.name }}</span>
            </span>
          </span>
        </div>
        <div v-if="game.file_count !== undefined" class="list-qf-row">
          <span class="list-qf-label">{{ t('library.files') }}</span>
          <span class="list-qf-val">{{ t('library.files_available', { count: game.file_count }) }}</span>
        </div>
        <div v-if="game.source" class="list-qf-row">
          <span class="list-qf-label">{{ t('detail.source') }}</span>
          <span class="list-qf-val" :class="game.source === 'gog' ? 'src-gog' : 'src-custom'">{{ game.catalog_origin || String(game.source).toUpperCase() }}</span>
        </div>
      </div>
    </div>

    <!-- Right column: the blended star first, then each source's own mark -->
    <div class="list-right">
      <div v-if="game.rating_agg || game.rating || game.meta_ratings?.rawg || game.meta_ratings?.igdb || game.meta_ratings?.steam" class="list-scores">
        <div v-if="game.rating_agg" class="list-score" title="Rating">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="1"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>
          {{ ratingVal(game.rating_agg).toFixed(1) }}
        </div>
        <div v-if="isGogRating && game.rating" class="list-score" title="GOG Rating">
          <img src="/icons/gog.ico" alt="GOG" class="list-primary-ico" />
          {{ ratingVal(game.rating).toFixed(1) }}
        </div>
        <div v-if="game.meta_ratings?.rawg" class="list-score" title="RAWG">
          <img src="/icons/RAWG.ico" width="20" height="20" alt="RAWG" class="score-ico" />
          {{ Number(game.meta_ratings.rawg).toFixed(1) }}
        </div>
        <div v-if="game.meta_ratings?.igdb" class="list-score" title="IGDB">
          <img src="/icons/igdb.ico" width="20" height="20" alt="IGDB" class="score-ico" />
          {{ Math.round(game.meta_ratings.igdb) }}
        </div>
        <div v-if="game.meta_ratings?.steam" class="list-score" title="Metacritic">
          <img src="/icons/metacritic.svg" width="20" height="20" alt="Metacritic" class="score-ico" />
          {{ Math.round(game.meta_ratings.steam * 10) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { buildLanguageList } from '@/utils/langMap'
import { ratingVal } from '@/utils/rating'
import { useI18n } from '@/i18n'

const props = defineProps<{ game: any; idx?: number; isGog?: boolean }>()
const emit = defineEmits<{ open: [game: any] }>()
const { t } = useI18n()
const themeStore = useThemeStore()

const idx = computed(() => props.idx ?? 0)
const listHeroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `list-hero-img--${themeStore.heroAnimStyle}`
})
// The star always carries the blended score; GOG's own mark sits beside it as
// one more source. Items from the GOG library carry no `source`, so the host
// marks them with the is-gog prop.
const isGogRating = computed(() => props.isGog || props.game?.source === 'gog')
const langs = computed(() => buildLanguageList(props.game?.languages))

function listDescText(game: any): string {
  const raw = (game.description_short || game.description || '').replace(/<[^>]*>/g, '').trim()
  return raw.length > 260 ? raw.slice(0, 260) + '…' : raw
}
function releaseYear(rd: string): string {
  const m = String(rd).match(/\b(\d{4})\b/)
  return m ? m[1] : String(rd).slice(0, 4)
}
// Download size for the row. GOG catalog entries carry installer sizes (the
// store download); a local game (Games / custom / collection member) sums its
// own files instead - the local size differs from GOG's by nature (local games
// are repacked), and that is expected.
function listDownloadSize(game: any): string {
  let maxBytes = 0
  const inst = game.installers
  if (inst) {
    for (const entries of Object.values(inst) as any[]) {
      if (Array.isArray(entries) && entries.length > 0) {
        const sz = entries[0].total_size || 0
        if (sz > maxBytes) maxBytes = sz
      }
    }
  } else if (Array.isArray(game.files)) {
    maxBytes = game.files
      .filter((f: any) => f.is_available)
      .reduce((sum: number, f: any) => sum + (f.size_bytes || 0), 0)
  }
  if (!maxBytes) return ''
  const gb = maxBytes / 1_073_741_824
  if (gb >= 1) return gb.toFixed(1) + ' GB'
  const mb = maxBytes / 1_048_576
  if (mb >= 1) return mb.toFixed(0) + ' MB'
  return '< 1 MB'
}
function openGame() {
  emit('open', props.game)
}

// Cover hover effects (tilt / shine / glow), gated by the user's theme prefs.
function onCardEnter(e: MouseEvent) {
  if (!themeStore.cardGlow) return
  ;(e.currentTarget as HTMLElement).querySelector<HTMLElement>('.cover-img-wrap')?.classList.add('glow-active')
}
function onCardMove(e: MouseEvent) {
  if (!themeStore.cardTilt && !themeStore.cardShine) return
  const el = e.currentTarget as HTMLElement
  const imgWrap = el.querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return
  const rect = imgWrap.getBoundingClientRect()
  if (themeStore.cardTilt) {
    const cx = rect.width / 2, cy = rect.height / 2
    const dx = e.clientX - rect.left - cx, dy = e.clientY - rect.top - cy
    const ry = (dx / cx) * 8, rx = -(dy / cy) * 5
    const zoom = themeStore.cardZoom ? 'scale3d(1.03,1.03,1.03)' : ''
    imgWrap.style.transform = `perspective(600px) rotateX(${rx}deg) rotateY(${ry}deg) ${zoom}`
  }
  const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
  if (sheen && themeStore.cardShine) {
    const mx = ((e.clientX - rect.left) / rect.width * 100).toFixed(1)
    const my = ((e.clientY - rect.top) / rect.height * 100).toFixed(1)
    sheen.style.opacity = '1'
    sheen.style.background = `radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%)`
  }
}
function onCardLeave(e: MouseEvent) {
  const imgWrap = (e.currentTarget as HTMLElement).querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return
  imgWrap.style.transform = ''
  imgWrap.classList.remove('glow-active')
  const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
  if (sheen) sheen.style.opacity = '0'
}
</script>

<style scoped>
.list-row {
  display: flex; align-items: stretch; gap: 0;
  padding: 0; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  cursor: pointer; transition: all var(--transition); overflow: hidden;
  /* min- (not fixed) height: a quick-facts column taller than the row (e.g.
     dozens of language flags) grows the row instead of getting clipped. */
  min-height: 260px;
}
.list-row:hover { background: var(--glass-highlight); border-color: color-mix(in srgb, var(--pl) 30%, transparent); }

.list-cover-wrap { flex-shrink: 0; width: 200px; padding: 10px; box-sizing: border-box; }
.list-cover-wrap .cover-img-wrap {
  /* 100% of the (stretched) row height, so the cover fills grown rows too;
     at the 260px minimum this equals the old fixed 240px. */
  width: 100%; height: 100%; border-radius: var(--radius-sm, 8px); overflow: hidden;
  background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 6px 24px rgba(0,0,0,0.45); position: relative;
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.2s ease;
  transform-style: preserve-3d;
}
.list-cover-wrap .cover-img-wrap::after {
  content: ''; position: absolute; inset: -1px; border-radius: inherit;
  border: 1px solid #14b8a6; box-shadow: 0 0 24px rgba(20,184,166,.3);
  opacity: 0; transition: opacity var(--transition); pointer-events: none; z-index: 2;
}
.list-cover-wrap .cover-img-wrap.glow-active::after { opacity: 1; }
.cover-sheen { position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity 0.3s; z-index: 3; }
.cover-overlay {
  position: absolute; inset: 0; z-index: 5;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.2) 50%, transparent 100%);
  opacity: 0; transition: opacity .18s;
}
.list-cover-wrap:hover .cover-overlay { opacity: 1; }
.list-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.list-cover-fallback { width: 100%; height: 100%; background: var(--bg3); }
.list-cover-check {
  position: absolute; bottom: 8px; right: 8px; z-index: 6;
  width: 24px; height: 24px; border-radius: 50%;
  background: #22c55e; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(34,197,94,.5);
}
.list-logo-img {
  max-height: 36px; max-width: 180px; width: auto;
  object-fit: contain; object-position: center;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,.5));
}
.list-owner-badge {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  padding: 2px 10px; border-radius: 10px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  font-size: var(--fs-xs, 10px); font-weight: 600; color: var(--muted);
  white-space: nowrap; margin-top: 2px;
}

.list-info {
  flex-shrink: 0; width: 200px; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: center;
  text-align: center; align-items: center; gap: var(--space-1, 4px);
  padding: 10px 16px; border-left: 1px solid var(--glass-border);
}
.list-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); overflow: hidden; min-height: 20px; }
.list-title > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.list-meta { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 6px; }
.meta-sep::before { content: '·'; margin-right: 6px; }

.list-hero { flex: 1; min-width: 0; overflow: hidden; position: relative; border-left: 1px solid var(--glass-border); }
.list-hero-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; filter: brightness(.30); }
.list-hero-overlay { position: absolute; inset: 0; background: linear-gradient(to right, rgba(0,0,0,.5) 0%, rgba(0,0,0,.2) 50%, rgba(0,0,0,.5) 100%); }
.list-hero-desc { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 16px 24px; z-index: 2; }
.list-hero-desc-text {
  margin: 0; font-size: var(--fs-sm, 12px); line-height: 1.7; color: rgba(255,255,255,.8);
  text-align: center; display: -webkit-box; -webkit-line-clamp: 7; -webkit-box-orient: vertical; overflow: hidden;
  text-shadow: 0 1px 4px rgba(0,0,0,.6);
}
.list-hero-img--kenburns { animation: list-kb calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.list-hero-img--drift { animation: list-drift calc(30s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.list-hero-img--pulse { animation: list-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
@keyframes list-kb { 0% { transform: scale(1.05) translateX(0); } 50% { transform: scale(1.12) translateX(-3%); } 100% { transform: scale(1.05) translateX(0); } }
@keyframes list-drift { 0% { transform: translateX(0) scale(1.04); } 50% { transform: translateX(-4%) scale(1.04); } 100% { transform: translateX(0) scale(1.04); } }
@keyframes list-pulse { 0%,100% { transform: scale(1.02); } 50% { transform: scale(1.08); } }
[data-animations="false"] .list-hero-img--kenburns,
[data-animations="false"] .list-hero-img--drift,
[data-animations="false"] .list-hero-img--pulse { animation: none; }
.genre-chip { padding: 1px 7px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); background: color-mix(in srgb, var(--pl) 14%, transparent); color: var(--pl-light, #a78bfa); }

/* Wide enough that many language flags and long studio names fit without
   wrapping into a tall, clipped block. Hero (flex) absorbs the extra width. */
.list-qf-col { flex-shrink: 0; width: 300px; border-left: 1px solid var(--glass-border); padding: 10px 12px; display: flex; align-items: center; justify-content: center; }
.list-qf { display: flex; flex-direction: column; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; width: 100%; }
.list-qf-row { display: flex; align-items: center; border-bottom: 1px solid var(--glass-border); min-height: 26px; }
.list-qf-row:last-child { border-bottom: none; }
.list-qf-label { flex-shrink: 0; width: 88px; padding: 4px 8px; font-size: 9px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; border-right: 1px solid var(--glass-border); background: rgba(255,255,255,.04); white-space: nowrap; line-height: 1.3; display: flex; align-items: center; align-self: stretch; }
.list-qf-val { flex: 1; padding: 4px 8px; font-size: 11px; color: var(--text); line-height: 1.3; display: flex; flex-wrap: wrap; gap: 3px; align-items: center; justify-content: center; text-align: center; }
.list-qf-os { gap: var(--space-1, 4px); }
.list-os-chip { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 5px; background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); }
.list-os-chip--win { color: #60a5fa; }
.list-os-chip--mac { color: #c4b5fd; }
.list-os-chip--linux { color: #facc15; }
.list-qf-langs { gap: 5px; }
.list-lang-flag { display: inline-flex; align-items: center; font-size: 15px; line-height: 1; }
.list-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.src-gog { color: #a78bfa !important; }
.src-custom { color: #2dd4bf !important; }

.list-right { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; flex-shrink: 0; width: 120px; box-sizing: border-box; border-left: 1px solid var(--glass-border); padding: 10px 16px; }
.list-scores { display: flex; flex-direction: column; gap: var(--space-2, 8px); align-items: center; }
.list-score { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: 15px; font-weight: 700; color: var(--text); white-space: nowrap; }
.list-score .score-ico { width: 42px; height: 42px; image-rendering: pixelated; opacity: .85; }
.list-score .list-primary-ico { width: 24px; height: 24px; image-rendering: pixelated; opacity: .9; }
.list-score svg { width: 24px; height: 24px; }
</style>
