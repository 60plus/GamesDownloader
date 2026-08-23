<template>
  <div class="library-view">

    <!-- ── Clear All Metadata dialog ─────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showClearDialog" class="gd-confirm-overlay" @click.self="showClearDialog = false">
        <div class="gd-confirm-box gd-confirm-box--danger">
          <div class="gd-confirm-icon gd-confirm-icon--danger">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/>
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </div>
          <div class="gd-confirm-title">{{ t('library.clear_confirm_title') }}</div>
          <div class="gd-confirm-body">{{ t('catalog.clear_confirm_body') }}</div>
          <div class="gd-confirm-actions">
            <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="showClearDialog = false">{{ t('common.cancel') }}</button>
            <button class="gd-confirm-btn gd-confirm-btn--danger" :disabled="clearing" @click="clearMetadata">
              {{ clearing ? t('library.clearing') : t('library.clear_all') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Sync store: pull the listing, then optionally scrape its metadata -->
    <Teleport to="body">
      <div v-if="showSyncDialog" class="gd-confirm-overlay" @click.self="showSyncDialog = false">
        <div class="gd-confirm-box">
          <div class="gd-confirm-title">{{ t('catalog.sync_title') }}</div>
          <label class="cs-syncopt">
            <input type="checkbox" v-model="syncAutoMeta" />
            <span>
              <span class="cs-syncopt-t">{{ t('library.sync_auto_meta') }}</span>
              <small class="cs-syncopt-d">{{ t('catalog.sync_auto_meta_desc') }}</small>
            </span>
          </label>
          <label class="cs-syncopt" :class="{ 'cs-syncopt--off': !syncAutoMeta }">
            <input type="checkbox" v-model="syncOverwrite" :disabled="!syncAutoMeta" />
            <span>
              <span class="cs-syncopt-t">{{ t('library.sync_overwrite') }}</span>
              <small class="cs-syncopt-d">{{ t('catalog.sync_overwrite_desc') }}</small>
            </span>
          </label>
          <div class="gd-confirm-actions">
            <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="showSyncDialog = false">{{ t('common.cancel') }}</button>
            <button class="gd-confirm-btn gd-confirm-btn--primary" :disabled="syncing" @click="confirmSync">{{ t('library.start_sync') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Title bar ─────────────────────────────────────────────────────── -->
    <div class="title-bar">
      <div class="title-left">
        <button class="lib-back-btn" @click="router.push('/')" :title="t('library.back_to_libraries')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('library.libraries') }}
        </button>
        <div class="title-ico"><LibraryIcon :icon="lib?.icon" :size="34" /></div>
        <div>
          <h1 class="title-text">{{ libName }}</h1>
          <p class="title-sub">{{ displayed.length }} {{ t('library.games') }}</p>
        </div>
      </div>

      <div class="title-right">
        <!-- Sync (admin) -->
        <button
          v-if="isAdmin && catalogId"
          class="sync-btn"
          :class="{ 'sync-btn--running': syncing }"
          :disabled="syncing"
          :title="t('library.sync')"
          @click="showSyncDialog = true"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ spin: syncing }">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          {{ syncing ? t('library.syncing') : t('library.sync') }}
        </button>

        <!-- Clear all metadata (admin) -->
        <button
          v-if="isAdmin && catalogId"
          class="clear-meta-btn"
          :disabled="clearing || syncing"
          :title="t('library.clear_all_metadata')"
          @click="showClearDialog = true"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6M14 11v6"/>
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
          </svg>
          {{ t('library.clear_metadata') }}
        </button>

        <!-- Sort -->
        <select v-model="sortBy" class="sort-select">
          <option value="title">{{ t('library.a_to_z') }}</option>
          <option value="title_desc">{{ t('library.z_to_a') }}</option>
          <option value="release">{{ t('library.newest') }}</option>
          <option value="release_asc">{{ t('library.oldest') }}</option>
          <option value="rating">{{ t('library.top_rated') }}</option>
          <option value="recent">{{ t('library.recent') }}</option>
        </select>

        <!-- Filter: owned (= downloaded from this store) -->
        <button class="filter-btn" :class="{ active: filterOwned }" @click="filterOwned = !filterOwned" :title="t('library.show_owned')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {{ t('library.owned') }}
        </button>

        <!-- Cover size (cover mode only) -->
        <div v-if="viewMode === 'cover'" class="size-group" :title="t('library.cover_size')">
          <button
            v-for="sz in coverSizes"
            :key="sz.id"
            class="size-btn"
            :class="{ active: currentCoverSize === sz.id }"
            @click="currentCoverSize = sz.id"
          >{{ sz.label }}</button>
        </div>

        <!-- View toggle -->
        <div class="view-toggle">
          <button :class="{ active: viewMode === 'cover' }" @click="viewMode = 'cover'" :title="t('library.cover_grid')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          </button>
          <button :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'" :title="t('library.list_view')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
          </button>
        </div>
      </div>
    </div>

    <p v-if="errMsg" class="cs-err">{{ errMsg }}</p>

    <!-- ── States ────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="state-empty"><p>{{ t('common.loading') }}</p></div>
    <div v-else-if="!displayed.length" class="state-empty">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
        <rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="7.5" cy="12" r="1.5"/><circle cx="16.5" cy="12" r="1.5"/>
      </svg>
      <p>{{ entries.length ? t('library.no_games') : t('catalog.empty') }}</p>
    </div>

    <!-- ── Main (grid/list + alphabet) ───────────────────────────────────── -->
    <div v-else class="library-main">
      <div class="grid-scroll" ref="gridScrollEl">

        <!-- Cover grid -->
        <div
          v-if="viewMode === 'cover'"
          class="cover-grid"
          :style="{ '--cover-min': coverSizeMap[currentCoverSize] + 'px' }"
        >
          <button
            v-for="(e, idx) in visibleEntries"
            :key="e.id"
            class="cover-wrap"
            :data-alpha-idx="idx"
            @click="open(e)"
          >
            <div class="cover-img-wrap">
              <img v-if="art(e)" :src="art(e)!" :alt="e.title" class="cover-img" loading="lazy" />
              <div v-else class="cover-fallback">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.25"><rect x="2" y="6" width="20" height="12" rx="2"/></svg>
              </div>
              <div class="cover-sheen" />
              <div v-if="e.downloaded" class="badge badge--owned">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                {{ t('library.owned') }}
              </div>
            </div>
            <div class="cover-title">{{ e.title }}</div>
            <div v-if="e.subtitle" class="cover-sub">{{ e.subtitle }}</div>
            <div v-if="scoreOf(e).length" class="cover-scores">
              <div v-for="s in scoreOf(e)" :key="s.key" class="cover-score">
                <svg v-if="s.key === 'star'" width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color:#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                <img v-else :src="s.icon" width="24" height="24" :alt="s.key" class="score-ico" />
                {{ s.val }}
              </div>
            </div>
          </button>
        </div>

        <!-- List view (shared GameListRow, like GOG) -->
        <div v-else class="list-view">
          <GameListRow
            v-for="(row, idx) in rows"
            :key="row.id"
            :game="row"
            :idx="idx"
            @open="open"
          />
        </div>

        <!-- Sentinel: nearing the viewport mounts the next batch. -->
        <div ref="listSentinel" class="load-sentinel" aria-hidden="true"></div>

      </div>

      <!-- Alphabet -->
      <nav class="alpha-nav">
        <button
          v-for="letter in alphaLetters"
          :key="letter"
          class="alpha-btn"
          :class="{ available: availableLetters.has(letter), active: activeLetter === letter }"
          @click="scrollToLetter(letter)"
        >{{ letter }}</button>
      </nav>
    </div>

  </div>
</template>

<script setup lang="ts">
/**
 * A plugin catalogue's shelf, dressed like a first-class library: title bar with
 * the store's icon, sort, an "owned" filter (downloaded listings), cover-size and
 * grid/list toggles, and admin sync + clear-metadata - the same controls the GOG
 * library has, so a store reads as a store, not a stripped-down grid.
 *
 * Clicking an offer opens the shared catalogue detail page, where the build is
 * picked and pulled.
 */
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useIncrementalList } from '@/composables/useIncrementalList'
import { useRoute, useRouter } from 'vue-router'
import catalogActions, { type CatalogEntry } from '@/lib/catalogActions'
import { useLibrariesStore } from '@/stores/libraries'
import { useAuthStore } from '@/stores/auth'
import LibraryIcon from '@/components/common/LibraryIcon.vue'
import GameListRow from '@/components/games/GameListRow.vue'
import { ratingVal } from '@/utils/rating'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const libs = useLibrariesStore()
const auth = useAuthStore()

const slug = computed(() => (route.params.slug as string) || '')
const lib = computed(() => libs.bySlug(slug.value))
const libName = computed(() => lib.value?.name || slug.value)
const catalogId = computed(() => lib.value?.catalog_id || '')
const isAdmin = computed(() => auth.user?.role === 'admin')

const entries = ref<CatalogEntry[]>([])
const loading = ref(true)
const syncing = ref(false)
const errMsg = ref('')

// ── View prefs (persisted, store-specific keys) ─────────────────────────────
const viewMode = ref<'cover' | 'list'>((localStorage.getItem('pcstore_view_mode') as 'cover' | 'list') || 'cover')
watch(viewMode, v => localStorage.setItem('pcstore_view_mode', v))
const sortBy = ref(localStorage.getItem('pcstore_sort_by') || 'title')
watch(sortBy, v => localStorage.setItem('pcstore_sort_by', v))
const filterOwned = ref(false)
const currentCoverSize = ref(localStorage.getItem('pcstore_card_size') || 'm')
watch(currentCoverSize, v => localStorage.setItem('pcstore_card_size', v))

const coverSizes = [
  { id: 'xs', label: 'XS' }, { id: 's', label: 'S' }, { id: 'm', label: 'M' },
  { id: 'l', label: 'L' }, { id: 'xl', label: 'XL' }, { id: 'xxl', label: 'XXL' },
]
const coverSizeMap: Record<string, number> = { xs: 115, s: 145, m: 175, l: 215, xl: 265, xxl: 310 }

// ── Clear metadata ──────────────────────────────────────────────────────────
const showClearDialog = ref(false)
const showSyncDialog = ref(false)
const syncAutoMeta = ref(true)
const syncOverwrite = ref(false)
const clearing = ref(false)

function art(e: CatalogEntry): string | null {
  return (e.cover_path as string) || (e.icon_path as string) || null
}

/** Per-source score chips for a cover card: the listing's own mark as a star,
 *  then each external source on its own scale, matching the GOG cover card. */
function scoreOf(e: CatalogEntry): { key: string; val: string; icon?: string }[] {
  const out: { key: string; val: string; icon?: string }[] = []
  const mr = (e.meta_ratings as Record<string, number>) || {}
  const rating = Number(e.rating) || 0
  if (rating > 0) out.push({ key: 'star', val: ratingVal(rating).toFixed(1) })
  if (mr.rawg) out.push({ key: 'rawg', val: Number(mr.rawg).toFixed(1), icon: '/icons/RAWG.ico' })
  if (mr.igdb) out.push({ key: 'igdb', val: String(Math.round(mr.igdb)), icon: '/icons/igdb.ico' })
  if (mr.steam) out.push({ key: 'steam', val: String(Math.round(mr.steam * 10)), icon: '/icons/metacritic.svg' })
  return out
}

// ── Displayed (filter + sort) ───────────────────────────────────────────────
const displayed = computed(() => {
  let list = [...entries.value]
  if (filterOwned.value) list = list.filter(e => e.downloaded)
  const rd = (e: CatalogEntry) => String((e.release_date as string) || '')
  switch (sortBy.value) {
    case 'title':       list.sort((a, b) => a.title.localeCompare(b.title)); break
    case 'title_desc':  list.sort((a, b) => b.title.localeCompare(a.title)); break
    case 'release':     list.sort((a, b) => rd(b).localeCompare(rd(a))); break
    case 'release_asc': list.sort((a, b) => rd(a).localeCompare(rd(b))); break
    case 'rating':      list.sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0)); break
    case 'recent':      list.sort((a, b) => b.id - a.id); break
  }
  return list
})

// Render in batches that grow on scroll; visibleEntries is a prefix of
// displayed, so the alphabet-jump indices still line up.
const { visible: visibleEntries, ensure: ensureVisible, sentinel: listSentinel } =
  useIncrementalList(displayed)

/** Map a listing onto the shape GameListRow reads. A listing is not a game, so
 *  the row synthesises what the component keys on: a "completed" status paints
 *  the owned check, per-OS booleans come from the offered builds, and the
 *  listing's own rating rides in as the star (rating_agg). */
const rows = computed(() => visibleEntries.value.map((e) => {
  const assets = (e.assets as Array<Record<string, unknown>>) || []
  const os = (k: string) => assets.some(a => {
    const v = String(a.os || '').toLowerCase()
    return v.includes(k) || v === 'all'
  })
  return {
    ...e,
    rating_agg: Number(e.rating) || undefined,
    download_status: e.downloaded ? 'completed' : undefined,
    os_windows: os('win'),
    os_mac: os('mac') || assets.some(a => ['osx', 'darwin'].includes(String(a.os || '').toLowerCase())),
    os_linux: os('lin'),
  }
}))

function open(e: CatalogEntry) {
  router.push(`/lib/${encodeURIComponent(slug.value)}/entry/${e.id}`)
}

// ── Alphabet ────────────────────────────────────────────────────────────────
const gridScrollEl = ref<HTMLElement | null>(null)
const activeLetter = ref('')
const alphaLetters = ['#', 'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']
const availableLetters = computed(() => {
  const set = new Set<string>()
  for (const e of displayed.value) {
    const c = e.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    set.add(/[A-Z]/.test(c) ? c : '#')
  }
  return set
})
async function scrollToLetter(letter: string) {
  const idx = displayed.value.findIndex(e => {
    const c = e.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    return letter === '#' ? !/[A-Z]/.test(c) : c === letter
  })
  if (idx === -1) return
  activeLetter.value = letter
  ensureVisible(idx)
  await nextTick()
  const el = gridScrollEl.value
  if (!el) return
  const sel = viewMode.value === 'list' ? '.list-row' : '.cover-wrap'
  const card = el.querySelectorAll(sel)[idx] as HTMLElement
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Data ────────────────────────────────────────────────────────────────────
async function load() {
  if (!catalogId.value) { entries.value = []; loading.value = false; return }
  loading.value = true
  errMsg.value = ''
  try {
    entries.value = await catalogActions.listEntries(catalogId.value)
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || String(e)
    entries.value = []
  } finally {
    loading.value = false
  }
}

async function confirmSync() {
  if (syncing.value || !catalogId.value) return
  syncing.value = true
  errMsg.value = ''
  showSyncDialog.value = false
  try {
    // Phase 1: pull the listing into the store (creates it the first time).
    await catalogActions.sync(catalogId.value)
    await load()
    // Phase 2 (optional): scrape the listings' metadata. Its failure - a missing
    // RAWG/IGDB source most often - is surfaced, not swallowed: the sync worked,
    // but the admin needs to know why nothing got dressed.
    if (syncAutoMeta.value) {
      await catalogActions.scrapeMetadata(catalogId.value, { onlyMissing: !syncOverwrite.value })
      await load()
    }
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || t('library.sync_failed')
  } finally {
    syncing.value = false
  }
}

async function clearMetadata() {
  if (clearing.value || !catalogId.value) return
  clearing.value = true
  try {
    await catalogActions.clearMetadata(catalogId.value)
    await load()
  } catch { /* ignore */ } finally {
    clearing.value = false
    showClearDialog.value = false
  }
}

onMounted(async () => {
  if (!libs.loaded) await libs.fetch()
  await load()
})
// The store is reachable from the library switcher, so the slug can change
// without this component being torn down.
watch(() => [slug.value, catalogId.value].join('|'), () => load())
</script>

<style scoped>
/* ── The whole title bar, its controls and the confirm dialog are copied byte
     for byte from GogLibrary.vue so a store reads as the same kind of thing as
     the GOG library, not a near-miss. The only store-specific additions are the
     framed icon tile (the library icon is a glyph, not GOG's own logo art) and
     the cover-card/score/alpha rules below the toggle. Keep them in step with
     GogLibrary if that ever changes. ── */

.library-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 20px 28px;
  gap: var(--space-4, 16px);
}

/* ── Title bar ────────────────────────────────────────────────────────────── */
.title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3, 12px);
  flex-shrink: 0;
  padding: 14px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
}
.title-left { display: flex; align-items: center; gap: var(--space-3, 12px); }
.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
  cursor: pointer; font-family: inherit; transition: all var(--transition);
  margin-right: 4px; flex-shrink: 0;
}
.lib-back-btn:hover { color: var(--text); background: rgba(255,255,255,.1); }
/* A framed tile so a glyph icon fills the same 60px footprint GOG's logo art
   occupies - without it a thin folder outline floated in empty space. */
.title-ico {
  width: 60px; height: 60px; flex-shrink: 0;
  display: grid; place-items: center;
  border-radius: var(--radius-sm, 8px);
  background: color-mix(in srgb, var(--pl) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 26%, transparent);
  color: var(--pl-light, var(--pl));
  filter: drop-shadow(0 0 8px var(--pglow2));
}
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }
.title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }

.sync-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.sync-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.sync-btn:disabled { opacity: .6; cursor: not-allowed; }
.sync-btn--running { border-color: var(--pl); color: var(--pl-light); }
.spin { animation: spin .8s linear infinite; }

.clear-meta-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid rgba(239,68,68,.35); background: rgba(239,68,68,.08);
  color: #f87171; font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.clear-meta-btn:not(:disabled):hover { border-color: rgba(239,68,68,.7); background: rgba(239,68,68,.15); color: #fca5a5; }
.clear-meta-btn:disabled { opacity: .45; cursor: not-allowed; }

.sort-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px;
  font-weight: 600; padding: 6px 10px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.sort-select:hover { border-color: var(--pl); }
.sort-select option { background: var(--bg2); }

.filter-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.filter-btn:hover { border-color: var(--pl); color: var(--text); }
.filter-btn.active { background: var(--pl-dim); border-color: var(--pl); color: var(--pl-light); }

.size-group {
  display: flex;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.size-btn {
  padding: 5px 9px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.size-btn + .size-btn { border-left: 1px solid var(--glass-border); }
.size-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.size-btn.active { background: var(--pl-dim); color: var(--pl-light); }

.view-toggle {
  display: flex; border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); overflow: hidden;
}
.view-toggle button {
  padding: 6px 10px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--transition);
}
.view-toggle button:hover { background: rgba(255,255,255,.1); color: var(--text); }
.view-toggle button.active { background: var(--pl-dim); color: var(--pl-light); }
.view-toggle button + button { border-left: 1px solid var(--glass-border); }

.cs-err { flex-shrink: 0; margin: 0; font-size: var(--fs-sm, 12px); color: #ff8b8b; }

/* ── Empty state ──────────────────────────────────────────────────────────── */
.state-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-3, 12px); color: var(--muted); font-size: var(--fs-md, 14px);
}
.state-empty p { margin: 0; }

/* ── Main area (grid + alpha nav) ─────────────────────────────────────────── */
.library-main { flex: 1; display: flex; gap: 0; overflow: hidden; min-height: 0; }
.grid-scroll {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  scrollbar-gutter: stable; padding-right: 8px; min-width: 0;
}
.alpha-nav {
  flex: none; width: 26px; display: flex; flex-direction: column; align-items: center;
  gap: 1px; padding: 4px 2px; overflow: hidden;
}
.alpha-btn {
  font-size: .64rem; font-weight: 700; line-height: 1; cursor: pointer;
  padding: 1px 3px; border-radius: 4px; border: none; background: none;
  color: var(--muted); opacity: .3;
}
.alpha-btn.available { opacity: 1; color: var(--text); }
.alpha-btn.active { color: var(--pl-light, var(--pl)); }
.alpha-btn:not(.available) { pointer-events: none; }

/* ── Cover grid ───────────────────────────────────────────────────────────── */
.cover-grid {
  display: grid; gap: var(--space-4, 16px);
  grid-template-columns: repeat(auto-fill, minmax(var(--cover-min, 175px), 1fr));
}
.cover-wrap {
  display: flex; flex-direction: column; gap: 6px;
  padding: 0; border: none; background: none; cursor: pointer; text-align: left;
}
.cover-img-wrap {
  position: relative; aspect-ratio: 3 / 4; border-radius: var(--radius-sm, 8px); overflow: hidden;
  background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 6px 24px rgba(0,0,0,0.45);
  transition: transform .35s cubic-bezier(.23,1,.32,1), border-color var(--transition);
}
.cover-wrap:hover .cover-img-wrap {
  transform: translateY(-4px);
  border-color: color-mix(in srgb, var(--pl) 45%, transparent);
}
.cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-fallback { width: 100%; height: 100%; display: grid; place-items: center; color: var(--muted); opacity: .5; }
.cover-sheen {
  position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .3s;
  background: radial-gradient(ellipse at 50% 0%, rgba(255,255,255,.18) 0%, transparent 60%);
}
.cover-wrap:hover .cover-sheen { opacity: 1; }
.badge--owned {
  position: absolute; left: 7px; bottom: 7px;
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 999px;
  font-size: .66rem; font-weight: 700; letter-spacing: .02em; color: var(--text);
  background: color-mix(in srgb, var(--pl) 40%, rgba(0,0,0,.55));
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  backdrop-filter: blur(3px);
}
.cover-title {
  font-size: var(--fs-sm, 13px); font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cover-sub {
  font-size: 11px; color: var(--muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cover-scores { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 1px; }
.cover-score { display: flex; align-items: center; gap: 3px; font-size: 13px; font-weight: 700; color: var(--text); }
.cover-score .score-ico { width: 24px; height: 24px; image-rendering: pixelated; opacity: .85; }

/* ── List view ────────────────────────────────────────────────────────────── */
.list-view { display: flex; flex-direction: column; gap: var(--space-3, 12px); }

/* ── Confirm dialog (shared danger pattern, matching GogLibrary) ───────────── */
.gd-confirm-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.55); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
}
.gd-confirm-box {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); padding: 32px 28px 24px;
  max-width: 420px; width: 90%; box-shadow: 0 24px 64px rgba(0,0,0,.5);
  display: flex; flex-direction: column; align-items: center; gap: var(--space-3, 12px); text-align: center;
}
.gd-confirm-box--danger { border-color: rgba(239,68,68,.35); }
.gd-confirm-icon {
  width: 52px; height: 52px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
}
.gd-confirm-icon--danger { background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.3); color: #f87171; }
.gd-confirm-title { font-size: 17px; font-weight: 700; color: var(--text); }
.gd-confirm-body  { font-size: 13px; color: var(--muted); line-height: 1.6; }
.gd-confirm-actions { display: flex; gap: 10px; margin-top: 8px; }
.gd-confirm-btn {
  padding: 8px 20px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 600; font-family: inherit; cursor: pointer; transition: all var(--transition);
  border: 1px solid transparent;
}
.gd-confirm-btn:disabled { opacity: .5; cursor: not-allowed; }
.gd-confirm-btn--ghost   { background: rgba(255,255,255,.06); border-color: var(--glass-border); color: var(--muted); }
.gd-confirm-btn--ghost:hover { color: var(--text); border-color: rgba(255,255,255,.25); }
.gd-confirm-btn--danger  { background: rgba(239,68,68,.2); border-color: rgba(239,68,68,.45); color: #f87171; }
.gd-confirm-btn--primary { background: color-mix(in srgb, var(--pl, #6366f1) 20%, transparent); border-color: color-mix(in srgb, var(--pl, #6366f1) 45%, transparent); color: var(--pl, #a5b4fc); }
.cs-syncopt { display: flex; gap: 10px; align-items: flex-start; padding: 9px 2px; cursor: pointer; text-align: left; }
.cs-syncopt input { margin-top: 3px; flex: none; }
.cs-syncopt--off { opacity: .5; }
.cs-syncopt-t { display: block; font-weight: 600; font-size: .92rem; }
.cs-syncopt-d { display: block; opacity: .7; font-size: .8rem; margin-top: 2px; line-height: 1.35; }
.gd-confirm-btn--danger:not(:disabled):hover { background: rgba(239,68,68,.3); border-color: rgba(239,68,68,.7); color: #fca5a5; }
</style>
