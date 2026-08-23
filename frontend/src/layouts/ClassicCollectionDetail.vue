<!--
  ClassicCollectionDetail - a collection-detail pane for the CLASSIC theme.

  Reuses the exact visual skeleton of ClassicGameDetail (cover hero, member
  strip, three info cards, About section) so a collection reads like a game
  detail, only populated from collection data:

    * Cover hero        -> CollectionCover (fanned member covers) + title +
                           rating + year-range chip.
    * "Screenshots" strip-> the member game covers (portrait tiles), clicking a
                           tile emits 'open-game' so the host can open it.
    * Card 1            -> Developer & Publisher (+ genres + source).
    * Card 2            -> Languages & Platform (flags + OS icons).
    * Card 3            -> Collection facts (released / time-to-beat / rating /
                           game count).
    * About             -> long description (HTML, sanitised).

  Admin gets Edit (CollectionMetadataPanel) and Delete on the cover overlay.

  The scoped CSS for the shared visual skeleton is copied verbatim from
  ClassicGameDetail.vue so the look stays byte-identical; the only deliberate
  deviation is .shot-item, made portrait (3:4) for covers instead of the
  landscape (16:9) screenshot tiles - the strip height is unchanged.
-->
<template>
  <div class="cd-wrap">

    <!-- Loading -->
    <div v-if="loading" class="cd-loading">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="cd-spin" style="opacity:.4">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </div>

    <!-- Collection content -->
    <template v-else-if="detail">

      <!-- ── COVER HERO ─────────────────────────────────────────────────────── -->
      <div class="cover-hero">

        <!-- Blurred backdrop from a random member hero - identical to the game
             detail hero (same animation/blur, obeys the same theme settings). -->
        <template v-if="heroBg && themeStore.classicHero">
          <div class="hero-bg">
            <div class="hero-bg-inner" :class="heroAnimClass" :style="{ ...heroBgStyle, filter: `blur(${themeStore.heroBlur}px) saturate(.6) brightness(.4)` }" />
            <div class="hero-bg-overlay" />
          </div>
          <div class="hero-vignette" />
        </template>

        <!-- Fanned member covers + action overlay (no tilt/sheen - the fan is its
             own composite visual) -->
        <div class="cover-wrap">
          <div class="cc-cover-box">
            <CollectionCover
              :cover="detail.cover_path"
              :covers="detail.member_covers"
              :name="detail.name"
              color="var(--pl)"
            />
          </div>
          <!-- Hover overlay: Edit + Delete (admin only) -->
          <div v-if="isAdmin" class="cover-overlay">
            <button class="cov-btn" @click="editOpen = true" :title="t('detail.edit_metadata')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </button>
            <button class="cov-btn cov-btn--danger" :disabled="deleting" @click="onDelete" :title="t('collections.delete')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
            </button>
          </div>
        </div>

        <!-- Clearlogo / text title fallback (same pattern as the game detail) -->
        <img
          v-if="detail.logo_path && !logoFailed"
          :src="detail.logo_path"
          :alt="detail.name"
          class="coll-logo"
          @error="logoFailed = true"
        />
        <div v-else class="game-title">{{ detail.name }}</div>

        <!-- Rating row (below title, above chips) -->
        <div v-if="detail.rating != null" class="cover-ratings">
          <div class="crating">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            <span>{{ Number(detail.rating).toFixed(1) }}<small>/5</small></span>
          </div>
        </div>

        <!-- Meta chips: year range -->
        <div class="meta-chips">
          <div v-if="yearRange" class="chip">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span>{{ yearRange }}</span>
          </div>
        </div>
      </div>

      <!-- ── MEMBER STRIP: the collection's games as portrait cover tiles ──────── -->
      <div v-if="detail.games?.length" class="shots-wrap">

        <!-- Prev arrow -->
        <button class="shots-nav" :disabled="slideIdx === 0" @click="slideTo(slideIdx - 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>

        <div class="shots-strip" :class="{ 'shots-strip--center': (detail.games?.length || 0) < 6 }" ref="stripEl">
          <div
            v-for="(g, i) in detail.games"
            :key="g.id ?? i"
            class="shot-item"
            :title="g.title"
            @click="emit('open-game', g)"
          >
            <img v-if="g.cover_path" :src="g.cover_path" class="shot-thumb-img" loading="lazy"
              @error="(e) => (e.target as HTMLImageElement).parentElement!.style.display='none'" />
            <div v-else class="shot-thumb-img shot-thumb-img--dark" />
          </div>
        </div>

        <!-- Next arrow -->
        <button class="shots-nav" :disabled="totalSlides <= 6 || slideIdx >= totalSlides - 6" @click="slideTo(slideIdx + 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>

      </div>

      <!-- ── INFO CARDS ──────────────────────────────────────────────────────── -->
      <div class="info-cards">

        <!-- Card 1: Developer & Publisher (+ genres + source) -->
        <div class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            <span>{{ t('detail.developer') }} &amp; {{ t('detail.publisher') }}</span>
          </div>
          <div class="icard-row"><span class="icard-label">{{ t('detail.developer') }}: </span><span class="icard-val">{{ aggList(detail.developers) }}</span></div>
          <div class="icard-row"><span class="icard-label">{{ t('detail.publisher') }}: </span><span class="icard-val">{{ aggList(detail.publishers) }}</span></div>
          <template v-if="detail.genres?.length">
            <div class="icard-head" style="margin-top:10px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
              <span>{{ t('detail.genres') }}</span>
            </div>
            <div class="genre-tags">
              <span v-for="g in detail.genres" :key="g" class="genre-tag">{{ g }}</span>
            </div>
          </template>
          <div v-if="detail.sources?.length" class="icard-row" style="margin-top:10px"><span class="icard-label">{{ t('detail.source') }}: </span><span class="icard-val">{{ detail.sources.join(', ') }}</span></div>
        </div>

        <!-- Card 2: Languages & Platform -->
        <div class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span>{{ t('detail.languages') }}</span>
          </div>
          <div class="icard-row" style="margin-bottom:4px"><span class="icard-label">{{ t('detail.languages') }}: </span></div>
          <div v-if="languageFlags.length" class="lang-flags">
            <span v-for="l in languageFlags" :key="l.name" class="lang-flag-em" :title="l.name">
              <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span>
              <span v-else>{{ l.name }}</span>
            </span>
          </div>
          <div v-else class="icard-row"><span class="icard-val">-</span></div>
          <div class="icard-row" style="margin-top:6px">
            <span class="icard-label">{{ t('library.platform_label') }}: </span>
            <div class="os-icons">
              <span class="os-icon" :class="{ active: platforms.windows }" title="Windows">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.75L11,11.91V5.21L20,3M3,13L9,13.09V19.9L3,18.75V13M20,13.25V22L11,20.5V13.09L20,13.25Z"/></svg>
              </span>
              <span class="os-icon" :class="{ active: platforms.mac }" title="macOS">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.78 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5M13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z"/></svg>
              </span>
              <span class="os-icon" :class="{ active: platforms.linux }" title="Linux">
                <img src="/icons/os-linux.svg" class="os-icon-linux" alt="Linux" />
              </span>
            </div>
          </div>
        </div>

        <!-- Card 3: Collection facts -->
        <div class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
            <span>{{ t('detail.collection') }}</span>
          </div>
          <div v-if="yearRange" class="icard-row"><span class="icard-label">{{ t('detail.released') }}: </span><span class="icard-val">{{ yearRange }}</span></div>
          <div v-if="detail.rating != null" class="icard-row">
            <span class="icard-label">{{ t('library.rating') }}: </span>
            <span class="icard-val icard-rating">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
              {{ Number(detail.rating).toFixed(1) }}<small>/5</small>
            </span>
          </div>
          <div class="icard-row"><span class="icard-label">{{ t('library.games') }}: </span><span class="icard-val">{{ detail.member_count }}</span></div>
          <template v-if="detail.hltb_main_s || detail.hltb_complete_s">
            <div class="icard-head" style="margin-top:12px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span>{{ t('detail.time_to_beat') }}</span>
            </div>
            <div v-if="detail.hltb_main_s" class="icard-row">
              <span class="icard-label">{{ t('detail.hltb_main') }} </span>
              <span class="icard-val">{{ Math.round((detail.hltb_main_s || 0) / 3600) }}h {{ Math.round(((detail.hltb_main_s || 0) % 3600) / 60) }}m</span>
            </div>
            <div v-if="detail.hltb_complete_s" class="icard-row">
              <span class="icard-label">{{ t('detail.hltb_complete') }} </span>
              <span class="icard-val">{{ Math.round((detail.hltb_complete_s || 0) / 3600) }}h {{ Math.round(((detail.hltb_complete_s || 0) % 3600) / 60) }}m</span>
            </div>
          </template>
        </div>

      </div>

      <!-- ── ABOUT ───────────────────────────────────────────────────────────── -->
      <div v-if="detail.description" class="desc-section">
        <div class="section-head">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
          <span>{{ t('detail.about') }}</span>
        </div>
        <div class="desc-body" v-html="sanitizeHtml(detail.description)" />
      </div>

    </template>

    <!-- ── EDIT PANEL ───────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <CollectionMetadataPanel
        v-if="editOpen && detail"
        :collection="detail"
        @close="editOpen = false"
        @updated="onUpdated"
        @deleted="onDeleted"
      />
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import client from '@/services/api/client'
import { buildLanguageList } from '@/utils/langMap'
import { sanitizeHtml } from '@/utils/sanitize'
import { useCollectionsStore } from '@/stores/collections'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import CollectionMetadataPanel from '@/components/collections/CollectionMetadataPanel.vue'

const props = defineProps<{ slug: string; lib: string; refreshTick?: number }>()
const emit = defineEmits<{
  (e: 'open-game', game: any): void
  (e: 'changed'): void
}>()

const store = useCollectionsStore()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const { gdConfirm } = useDialog()
const { t } = useI18n()

const isAdmin = computed(() => authStore.user?.role === 'admin')

const detail   = ref<any>(null)
const heroBg   = ref('')   // collection hero (else a random member hero) backdrop
const logoFailed = ref(false)
const loading  = ref(false)
const editOpen = ref(false)
const deleting = ref(false)

// ── Member strip navigation (same mechanism as ClassicGameDetail, no video) ──
const stripEl     = ref<HTMLElement | null>(null)
const slideIdx    = ref(0)
const totalSlides = computed(() => detail.value?.games?.length || 0)

function slideTo(idx: number) {
  const max = Math.max(0, totalSlides.value - 6)
  slideIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = stripEl.value
    if (!el) return
    const child = el.children[slideIdx.value] as HTMLElement | undefined
    if (child) el.scrollTo({ left: child.offsetLeft, behavior: 'smooth' })
  })
}

// ── Derived data (mirrors CollectionInfo's logic) ───────────────────────────
const yearRange = computed(() => {
  const c = detail.value || {}
  if (c.start_year && c.end_year && c.start_year !== c.end_year) return `${c.start_year} - ${c.end_year}`
  return c.start_year ? String(c.start_year) : (c.end_year ? String(c.end_year) : '')
})

const platforms = computed(() => detail.value?.platforms || { windows: false, mac: false, linux: false })
const languageFlags = computed(() => buildLanguageList(detail.value?.languages))

// Hero backdrop - same logic/animation as ClassicGameDetail so it obeys the same
// theme settings (hero blur, hero animation style, global animations toggle).
const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `cd-hero--${themeStore.heroAnimStyle}`
})
const heroBgStyle = computed(() => heroBg.value ? { backgroundImage: `url("${heroBg.value}")` } : {})

function aggList(arr: string[] | undefined): string {
  const a = arr || []
  if (!a.length) return '-'
  if (a.length <= 2) return a.join(', ')
  return a.slice(0, 2).join(', ') + ' +' + (a.length - 2)
}

// ── Load ─────────────────────────────────────────────────────────────────────
async function load() {
  if (!props.slug) return
  loading.value = true
  slideIdx.value = 0
  detail.value = null
  try {
    detail.value = await store.get(props.slug)
    logoFailed.value = false
    // The collection's own (scraped/uploaded) hero wins; without one, fall back
    // to a random member hero like before.
    const heroes: string[] = detail.value?.member_heroes || []
    heroBg.value = detail.value?.hero_path
      || (heroes.length ? heroes[Math.floor(Math.random() * heroes.length)] : '')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.slug, props.refreshTick], load)

// ── Edit / delete ──────────────────────────────────────────────────────────
async function onUpdated() {
  await load()
  emit('changed')
}

function onDeleted() {
  editOpen.value = false
  emit('changed')
}

async function onDelete() {
  if (!detail.value || deleting.value) return
  const ok = await gdConfirm(
    t('collections.delete_confirm', { name: detail.value.name }),
    { title: t('collections.delete'), danger: true, confirmText: t('common.delete'), cancelText: t('common.cancel') },
  )
  if (!ok) return
  deleting.value = true
  try {
    await client.delete('/collections/' + props.slug)
    emit('changed')
  } catch {
    deleting.value = false
  }
}
</script>

<style scoped>
.cd-wrap {
  display: flex; flex-direction: column;
  flex: 1; overflow-y: auto; overflow-x: hidden;
  /* Reserve scrollbar gutter so width stays constant when content overflows. */
  scrollbar-gutter: stable;
}

/* Loading */
.cd-loading { flex: 1; display: flex; align-items: center; justify-content: center; }
.cd-spin { animation: cd-spin-anim 1s linear infinite; }

/* ── COVER HERO ────────────────────────────────────────────────────────────── */
.cover-hero {
  display: flex; flex-direction: column; align-items: center;
  padding: 28px 20px 20px; flex-shrink: 0;
  position: relative; overflow: hidden;
}
/* Member-hero backdrop - copied verbatim from ClassicGameDetail so it animates
   and dims identically and obeys the same theme settings. */
.hero-vignette {
  position: absolute; top: 0; left: 0; right: 0; height: 100%;
  background: transparent; pointer-events: none; z-index: 2;
}
.hero-bg { position: absolute; inset: 0; z-index: 0; overflow: hidden; }
.hero-bg-inner {
  position: absolute; inset: -10%;
  background-size: cover; background-position: center center;
  transform-origin: center center; transform: scale(1.06); will-change: transform;
}

.cd-hero--kenburns { animation: cd-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.cd-hero--drift { animation: cd-drift calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate; }
.cd-hero--pulse { animation: cd-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
[data-animations="false"] .cd-hero--kenburns,
[data-animations="false"] .cd-hero--drift,
[data-animations="false"] .cd-hero--pulse { animation: none; }
.hero-bg-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to bottom,
    color-mix(in srgb, var(--bg) 15%, transparent) 0%,
    color-mix(in srgb, var(--bg) 50%, transparent) 40%,
    color-mix(in srgb, var(--bg) 85%, transparent) 72%,
    var(--bg) 100%);
}

/* Cover wrap + overlay */
.cover-wrap { position: relative; z-index: 3; transform-style: preserve-3d; }

/* Elements BELOW cover-wrap in DOM flow are non-positioned -> keep them above
   any future hero background. */
.coll-logo, .game-title, .cover-ratings, .meta-chips { position: relative; z-index: 4; }

/* Collection clearlogo (transparent, same footprint as the game logo) */
.coll-logo {
  max-width: 320px;
  max-height: 110px;
  width: auto;
  height: auto;
  object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.8));
  margin-top: 18px;
}

/* Collection cover box - same footprint as a game cover (2:3 portrait) so the
   fanned member-cover composite occupies exactly the cover slot. */
.cc-cover-box {
  position: relative;
  /* Square footprint (the fan is calibrated for squares) and larger than a game
     cover; no frame/glow so only the fanned member covers read. */
  width: var(--cd-cover-h, 525px);
  height: var(--cd-cover-h, 525px);
  max-width: 100%;
  border-radius: 14px;
  overflow: hidden;
}

/* Cover action overlay (edit + delete) */
.cover-overlay {
  position: absolute; inset: 0; border-radius: 14px;
  background: linear-gradient(180deg, transparent 40%, rgba(0,0,0,.75) 100%);
  display: flex; align-items: flex-end; justify-content: center;
  gap: 10px; padding-bottom: 16px;
  opacity: 0; transition: opacity .2s;
}
.cover-wrap:hover .cover-overlay { opacity: 1; }
.cov-btn {
  width: 38px; height: 38px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 55%, transparent); border: 1px solid color-mix(in srgb, var(--pl-light) 60%, transparent);
  color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .15s, transform .15s;
}
.cov-btn:hover { background: color-mix(in srgb, var(--pl) 85%, transparent); transform: scale(1.1); }
.cov-btn--danger { background: rgba(220,38,38,.45) !important; border-color: rgba(239,68,68,.6) !important; }
.cov-btn--danger:hover { background: rgba(220,38,38,.8) !important; }

/* Title */
.game-title {
  margin-top: 18px;
  font-family: 'Rajdhani', var(--font); font-size: 34px; font-weight: 700; letter-spacing: .5px;
  text-align: center; line-height: 1.1; position: relative; z-index: 3;
  color: var(--text); text-shadow: 0 2px 20px var(--pglow);
}

/* Ratings row (below title) */
.cover-ratings {
  display: flex; flex-wrap: wrap; justify-content: center;
  gap: 10px; margin-top: 10px; z-index: 3; position: relative;
}
.crating {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.crating small { color: var(--muted); font-size: 11px; font-weight: 400; }

/* Meta chips */
.meta-chips {
  display: flex; flex-wrap: wrap; justify-content: center;
  gap: 5px; margin-top: 8px; z-index: 3; position: relative;
}
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 12px; border-radius: 20px; font-size: 13px;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  color: var(--muted); white-space: nowrap; backdrop-filter: blur(8px);
}
.chip span { color: var(--text); }

/* ── MEMBER STRIP - identical mechanism to ClassicGameDetail's shots strip ── */
.shots-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 20px 10px;
  background: linear-gradient(145deg, var(--glass-highlight) 0%, rgba(0,0,0,.5) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border); border-top: 1px solid color-mix(in srgb, var(--pl-light) 30%, transparent);
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.03);
  padding: 10px 8px;
}
.shots-nav {
  flex-shrink: 0;
  width: 28px; height: 28px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid var(--glass-border);
  color: rgba(255,255,255,.7);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.shots-nav:hover:not(:disabled) { background: var(--pglow); color: #fff; }
.shots-nav:disabled { opacity: .25; cursor: default; }
.shots-strip {
  flex: 1;
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.shots-strip::-webkit-scrollbar { display: none; }
/* Centre the tiles when they don't fill the strip (no scrolling needed). */
.shots-strip--center { justify-content: center; }
/* Portrait cover tiles (the only deliberate deviation from the reference):
   each tile is 3:4 so member COVERS show without cropping. Width is derived
   from the strip WIDTH (6 tiles per view, 5 gaps x 6px) and height follows
   via aspect-ratio - never from the image's intrinsic size, so animated
   covers with larger native dimensions render the same as static ones. */
.shot-item {
  flex: 0 0 calc((100% - 30px) / 6);
  aspect-ratio: 3/4;
  border-radius: 7px;
  overflow: hidden;
  cursor: pointer;
  scroll-snap-align: start;
  border: 2px solid transparent;
  box-shadow: 0 4px 12px rgba(0,0,0,.5);
  transition: border-color .2s, box-shadow .2s;
  position: relative;
}
.shot-item:hover {
  border-color: var(--pl);
  box-shadow: 0 0 0 1px var(--pl), 0 6px 20px var(--pglow);
}
.shot-thumb-img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.shot-thumb-img--dark {
  background: rgba(0,0,0,.5);
}

/* ── INFO CARDS ──────────────────────────────────────────────────────────── */
.info-cards {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 10px; padding: 0 20px 14px; flex-shrink: 0;
}
.icard {
  border-radius: 14px; padding: 14px 16px;
  background: linear-gradient(145deg, var(--pl-dim) 0%, rgba(0,0,0,.7) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%)); -webkit-backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border); border-top: 1px solid color-mix(in srgb, var(--pl-light) 40%, transparent);
  box-shadow: 0 8px 24px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.04);
}
.icard-head {
  display: flex; align-items: center; gap: 6px;
  font-family: 'Rajdhani', var(--font); font-size: 13px; font-weight: 700;
  letter-spacing: 1.5px; color: var(--pl-light); text-transform: uppercase;
  margin-bottom: 10px; border-bottom: 1px solid var(--glass-border); padding-bottom: 8px;
}
.icard-row { font-size: 13px; margin-bottom: 5px; line-height: 1.5; }
.icard-label { color: var(--muted); }
.icard-val { color: var(--text); }
.icard-rating { display: inline-flex; align-items: center; gap: 4px; font-weight: 700; }
.icard-rating small { color: var(--muted); font-weight: 400; font-size: 11px; }

/* Genre tags */
.genre-tags { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); padding: 2px 0; }
.genre-tag {
  display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  color: var(--muted); white-space: nowrap;
}

/* Language flags - flag-icons sprite, name on :title tooltip. */
.lang-flags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.lang-flag-em {
  display: inline-flex; align-items: center;
  font-size: var(--fs-xl, 18px); line-height: 1; cursor: default;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,.5));
  transition: transform .15s;
}
.lang-flag-em .fi {
  width: 1.4em; height: 1em;
  border-radius: 2px;
}
.lang-flag-em:hover { transform: scale(1.3); }

/* OS icons */
.os-icons { display: flex; gap: var(--space-2, 8px); margin-top: 5px; align-items: center; }
.os-icon { color: var(--pglow2); transition: color .2s; display: flex; align-items: center; }
.os-icon.active { color: var(--pl-light); filter: drop-shadow(0 0 4px color-mix(in srgb, var(--pl-light) 60%, transparent)); }
.os-icon-linux { width: 40px; height: 40px; opacity: .25; filter: invert(1) sepia(1) saturate(0) brightness(.6); transition: opacity .2s, filter .2s; }
.os-icon.active .os-icon-linux { opacity: .9; filter: invert(1) sepia(1) saturate(3) hue-rotate(220deg) brightness(1.1); }

/* ── ABOUT ────────────────────────────────────────────────────────────────── */
.desc-section {
  padding: 0 20px 28px; flex-shrink: 0;
  max-width: 900px;      /* readable line length even on wide screens */
  width: 100%;
  margin-left: auto; margin-right: auto;
  box-sizing: border-box;
}
.section-head {
  display: flex; align-items: center; gap: 7px;
  font-family: 'Rajdhani', var(--font); font-size: var(--fs-md, 14px); font-weight: 700;
  letter-spacing: 1.5px; color: var(--muted); text-transform: uppercase;
  margin-bottom: 10px; border-bottom: 1px solid var(--glass-border); padding-bottom: 8px;
}
.desc-body { font-size: 13px; line-height: 1.8; color: var(--muted); }
.desc-body :deep(h1),.desc-body :deep(h2),.desc-body :deep(h3) { font-family: 'Rajdhani', var(--font); color: var(--text); margin: 10px 0 4px; font-size: var(--fs-md, 14px); }
.desc-body :deep(p) { margin-bottom: 8px; }
.desc-body :deep(ul),.desc-body :deep(ol) { margin: 6px 0 8px 18px; }
.desc-body :deep(li) { margin-bottom: 3px; }
.desc-body :deep(a) { color: var(--pl); text-decoration: none; }
.desc-body :deep(strong),.desc-body :deep(b) { color: var(--text); }
</style>
