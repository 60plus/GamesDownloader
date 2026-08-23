<template>
  <div class="rsl-view">

    <!-- ── Title bar ─────────────────────────────────────────────────────────
         The same header the Retro library gives a platform, so browsing a
         source's ROMs sits visually under the console it belongs to. The info
         comes from the config-stored platform record, which exists for every
         known fs_slug - including the ones this source offers but the library
         does not have yet. ─────────────────────────────────────────────────── -->
    <div
      class="rsl-title-bar"
      :class="{ 'rsl-title-bar--photo': !!headerBgUrl && themeStore.platformPhotoHeader }"
      :style="titleBarStyle"
    >
      <!-- Animated hero background (respects the hero settings) -->
      <div
        v-if="headerBgUrl && themeStore.platformPhotoHeader"
        class="rsl-title-bg"
        :class="themeStore.heroAnim && themeStore.animations ? `rsl-title-bg--${themeStore.heroAnimStyle}` : ''"
        :style="{ backgroundImage: `url(${headerBgUrl})`, '--gd-hero-blur': `${themeStore.heroBlur ?? 14}px` }"
      />
      <div v-if="headerBgUrl && themeStore.platformPhotoHeader" class="rsl-title-photo-overlay" />

      <div class="rsl-title-left">
        <button class="lib-back-btn" @click="router.push(backRoute)" :title="t('romsrc.back_to_platforms', 'Platforms')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('romsrc.back_to_platforms', 'Platforms') }}
        </button>

        <!-- Platform identity: icon top, name wordmark below -->
        <div class="rsl-platform-identity">
          <img
            :src="art.icon"
            class="rsl-platform-icon"
            alt=""
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
          <img
            v-if="!logoError"
            :src="art.name"
            :alt="platformTitle"
            class="rsl-platform-name-logo"
            @error="logoError = true"
          />
          <span v-else class="rsl-platform-name-text">{{ platformTitle }}</span>
          <span class="rsl-count">{{ total }} {{ t('emulation.roms_count', 'ROMs') }}</span>
        </div>
      </div>

      <!-- Center: console photo left, chips + description right -->
      <div v-if="themeStore.platformPhotoHeader" class="rsl-title-center">
        <div v-if="info?.photo_path" class="rsl-console-photo-col">
          <img
            :src="info.photo_path"
            class="rsl-console-photo"
            alt=""
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
        </div>

        <div class="rsl-console-info-col">
          <div v-if="maker || releaseYear || info?.generation" class="rsl-console-meta">
            <span v-if="maker" class="rsl-meta-chip">{{ maker }}</span>
            <span v-if="releaseYear" class="rsl-meta-chip">
              {{ releaseYear }}{{ info?.end_year_platform ? '–' + info.end_year_platform : '' }}
            </span>
            <span v-if="info?.generation" class="rsl-meta-chip">Gen {{ info.generation }}</span>
          </div>
          <div v-if="platformDescription" class="rsl-console-desc-wrap">
            <p class="rsl-console-desc">{{ platformDescription }}</p>
            <a
              v-if="info?.wiki_url"
              :href="info.wiki_url"
              target="_blank" rel="noopener noreferrer"
              class="rsl-wiki-link-inline"
            >
              {{ t('library.wikipedia', 'Wikipedia') }}
            </a>
          </div>
        </div>
      </div>

      <div class="rsl-title-right">
        <!-- Search -->
        <div class="rsl-search-wrap">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="rsl-search-ico"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input v-model="searchInput" class="rsl-search" :placeholder="t('romsrc.search', 'Search ROMs')" />
          <button v-if="searchInput" class="rsl-search-x" @click="searchInput = ''">×</button>
        </div>

        <!-- Collection filter: only when the source has more than one -->
        <select v-if="collectionOptions.length > 1" v-model="collection" class="rsl-select">
          <option value="">{{ t('romsrc.collection_all', 'All collections') }}</option>
          <option v-for="c in collectionOptions" :key="c" :value="c">{{ c }}</option>
        </select>

        <!-- Container filter (only when the platform comes in several) -->
        <select v-if="formatOptions.length > 1" v-model="format" class="rsl-select">
          <option value="">{{ t('romsrc.format_all', 'All formats') }}</option>
          <option v-for="f in formatOptions" :key="f" :value="f">{{ f.toUpperCase() }}</option>
        </select>

        <!-- Release type: retail game, prototype, translation, hack... -->
        <select v-if="kindOptions.length > 1" v-model="kind" class="rsl-select">
          <option value="">{{ t('romsrc.kind_all', 'All release types') }}</option>
          <option v-for="k in kindOptions" :key="k" :value="k">{{ kindLabel(k) }}</option>
        </select>

        <!-- Region filter -->
        <select v-model="region" class="rsl-select">
          <option value="">{{ t('romsrc.region_all', 'All regions') }}</option>
          <option v-for="r in regionOptions" :key="r" :value="r">{{ r }}</option>
        </select>

        <!-- Sort -->
        <select v-model="sort" class="rsl-select">
          <option value="name_asc">{{ t('library.a_to_z', 'A - Z') }}</option>
          <option value="name_desc">{{ t('library.z_to_a', 'Z - A') }}</option>
          <option value="size_desc">{{ t('romsrc.sort_size_desc', 'Largest') }}</option>
          <option value="size_asc">{{ t('romsrc.sort_size_asc', 'Smallest') }}</option>
        </select>

        <!-- Hide what the library already holds. Owned is decided by hash where
             the source published one, so this survives a renamed file. -->
        <button
          class="rsl-chip-btn"
          :class="{ active: hideOwned }"
          :title="t('romsrc.hide_owned', 'Hide what I already have')"
          @click="hideOwned = !hideOwned"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>
            <line v-if="hideOwned" x1="3" y1="21" x2="21" y2="3"/>
          </svg>
          {{ t('romsrc.hide_owned', 'Hide what I already have') }}
        </button>
      </div>
    </div>

    <!-- ── Action bar (selection) ────────────────────────────────────────── -->
    <div v-if="selectableRows.length" class="rsl-action-bar">
      <label class="rsl-check-label">
        <input type="checkbox" :checked="allSelected" @change="toggleAll" />
        <span>{{ t('romsrc.select_all', 'Select all') }}</span>
      </label>
      <span class="rsl-sel-count">{{ selected.size }} {{ t('romsrc.selected', 'selected') }}</span>
      <button
        class="rsl-dl-selected"
        :disabled="!selected.size || bulkBusy"
        @click="downloadSelected"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        {{ t('romsrc.download_selected', 'Download selected') }}
      </button>
    </div>

    <!-- ── States ────────────────────────────────────────────────────────── -->
    <div v-if="loading && !items.length" class="rsl-state"><span class="spinner" /></div>
    <!-- A fresh listing that failed leaves nothing on screen, so it needs its
         own way back: without one the only escape is changing a filter. -->
    <div v-else-if="errMsg" class="rsl-state rsl-state--err">
      <span>{{ errMsg }}</span>
      <button class="rsl-more-retry" @click="reload">{{ t('romsrc.retry', 'Retry') }}</button>
    </div>
    <div v-else-if="!items.length" class="rsl-state">{{ t('romsrc.no_roms', 'No ROMs found.') }}</div>
    <div v-else-if="!shownItems.length" class="rsl-state">{{ t('romsrc.all_owned', 'Everything here is already in your library.') }}</div>

    <!-- ── List ──────────────────────────────────────────────────────────── -->
    <div v-else ref="listEl" class="rsl-list" :class="{ 'rsl-list--loading': loading }">
      <template v-for="e in shownItems" :key="e.id">
      <div class="rsl-row" :class="{ 'rsl-row--owned': isOwned(e) }">
        <!-- checkbox (hidden for owned/in-flight) -->
        <label class="rsl-row-check" v-if="!isOwned(e) && !isBusy(e)">
          <input type="checkbox" :checked="selected.has(e.id)" @change="toggleOne(e.id)" />
        </label>
        <span v-else class="rsl-row-check rsl-row-check--placeholder" />

        <!-- A look at the game before downloading it. One click, one lookup -
             never for the list, which runs to thousands of rows. -->
        <button class="rsl-row-peek" :class="{ open: previewFor === e.id }"
          :title="t('romsrc.preview', 'Look this game up')" @click="togglePreview(e)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>
          </svg>
        </button>

        <!-- title + region + which catalogue it came from -->
        <div class="rsl-row-main">
          <span class="rsl-row-title rsl-row-title--peek" @click="togglePreview(e)">{{ e.title }}</span>
          <span v-if="setName(e)" class="rsl-row-set">{{ setName(e) }}</span>
          <span v-if="e.region" class="rsl-region-badge">{{ e.region }}</span>
          <span v-if="e.collection && collectionOptions.length > 1" class="rsl-coll-badge">
            {{ e.collection }}
          </span>
        </div>

        <!-- size -->
        <span class="rsl-row-size">{{ e.size ? formatBytes(e.size) : '' }}</span>

        <!-- action / state -->
        <div class="rsl-row-action">
          <template v-if="rowState[e.id]?.status === 'downloading'">
            <div class="rsl-prog">
              <div class="rsl-prog-track"><div class="rsl-prog-fill" :style="{ width: (rowState[e.id]?.percent ?? 0) + '%' }" /></div>
              <span class="rsl-prog-pct">{{ Math.round(rowState[e.id]?.percent ?? 0) }}%</span>
            </div>
          </template>
          <span v-else-if="rowState[e.id]?.status === 'queued'" class="rsl-state-chip rsl-state-chip--queued">{{ t('download.queued', 'Queued') }}</span>
          <template v-else-if="rowState[e.id]?.status === 'error'">
            <span class="rsl-state-chip rsl-state-chip--error" :title="rowState[e.id]?.error || undefined">{{ t('romsrc.failed', 'Failed') }}</span>
            <button class="rsl-dl-btn rsl-dl-btn--retry" @click="downloadOne(e)">{{ t('romsrc.retry', 'Retry') }}</button>
          </template>
          <span v-else-if="isOwned(e)" class="rsl-owned-chip">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            {{ t('romsrc.in_library', 'In library') }}
          </span>
          <button v-else class="rsl-dl-btn" @click="downloadOne(e)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {{ t('romsrc.download', 'Download') }}
          </button>
        </div>
      </div>

      <!-- The look itself: opens under its own row, so the list stays put. -->
      <div v-if="previewFor === e.id" class="rsl-peek">
        <div v-if="peekBusyFor(e)" class="rsl-peek-load"><span class="spinner" /></div>
        <template v-else-if="peek(e)?.found">
          <img v-if="peek(e)?.cover_url" :src="peek(e)!.cover_url!" class="rsl-peek-cover" alt="" />
          <div class="rsl-peek-facts">
            <div class="rsl-peek-name">{{ peek(e)?.name }}</div>
            <div class="rsl-peek-line">
              <span v-if="peek(e)?.release_year">{{ peek(e)?.release_year }}</span>
              <span v-if="peek(e)?.developer">{{ peek(e)?.developer }}</span>
              <span v-if="peek(e)?.genres?.length">{{ peek(e)!.genres!.slice(0, 3).join(', ') }}</span>
            </div>
            <p v-if="peek(e)?.summary" class="rsl-peek-sum">{{ peek(e)?.summary }}</p>
            <div class="rsl-peek-src">{{ peek(e)?.source }} - {{ peek(e)?.matched_by }}</div>
          </div>
        </template>
        <div v-else class="rsl-peek-none">
          {{ t('romsrc.preview_none', 'Nothing found for') }} "{{ peek(e)?.query }}"
        </div>
      </div>
      </template>
    </div>

    <!-- ── Endless list: the sentinel pulls the next page into view ────── -->
    <div ref="sentinel" class="rsl-sentinel">
      <span v-if="loading && items.length" class="spinner" />
      <template v-else-if="moreErr && items.length">
        <span class="rsl-more-err">{{ moreErr }}</span>
        <button class="rsl-more-retry" @click="retryMore">
          {{ t('romsrc.retry', 'Retry') }}
        </button>
      </template>
      <span v-else-if="!hasMore && items.length" class="rsl-end">
        {{ total }} {{ t('emulation.roms_count', 'ROMs') }}
      </span>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import romSourceActions, { type RomSourceEntry, type RomSourcePreview } from '@/lib/romSourceActions'
import { useSocketStore } from '@/stores/socket'
import { useThemeStore } from '@/stores/theme'
import { usePlatformMetaStore } from '@/stores/platformMeta'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { formatBytes as _formatBytes } from '@/utils/format'
const formatBytes = (b: number | null | undefined): string => _formatBytes(b, '')

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const socketStore = useSocketStore()
const themeStore = useThemeStore()
const platformMeta = usePlatformMetaStore()

const sourceId = computed(() => String(route.params.sourceId || ''))
const fsSlug = computed(() => String(route.params.fsSlug || ''))
const art = computed(() => romSourceActions.platformArt(fsSlug.value))
const backRoute = computed(() => romSourceActions.route(sourceId.value))

// ── Platform header ─────────────────────────────────────────────────────────
// The console this source is being browsed for. Read from the config-stored
// platform record rather than the DB one, because a source offers platforms the
// library may not hold a single ROM for yet.
interface PlatformInfo {
  photo_path?: string | null
  description?: string | null
  wiki_url?: string | null
  manufacturer?: string | null
  release_year_platform?: string | null
  end_year_platform?: string | null
  generation?: string | null
}
const info = ref<PlatformInfo | null>(null)
const logoError = ref(false)

// Same monotonic guard the listing uses: a platform switch while this call is
// in flight must not let the old console's photo and chips land on the new
// one's header, which would leave the header describing a different machine
// from the title and the list under it.
let infoSeq = 0

async function loadPlatformInfo() {
  const seq = ++infoSeq
  info.value = null
  logoError.value = false
  if (!fsSlug.value) return
  platformMeta.fetchIfNeeded()
  try {
    const { data } = await client.get(`/roms/platforms/${encodeURIComponent(fsSlug.value)}/stored-info`)
    if (seq !== infoSeq) return
    info.value = data
  } catch {
    // header art is an enhancement - the list stands on its own without it
  }
}

/** "super-famicom" -> "Super Famicom", for when the wordmark is missing. */
const platformTitle = computed(() =>
  platformMeta.meta[fsSlug.value]?.name
  || fsSlug.value.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
)
const headerBgUrl = computed(() => info.value?.photo_path || art.value.fanart)
// The scraped record wins where it exists, but a platform is only scraped once
// somebody asks for it - the bundled EmulationStation metadata covers the rest,
// so the header carries the hardware facts for every platform a source offers.
const maker = computed(() =>
  info.value?.manufacturer || platformMeta.meta[fsSlug.value]?.manufacturer || '',
)
const releaseYear = computed(() =>
  info.value?.release_year_platform || platformMeta.meta[fsSlug.value]?.release_year || '',
)
const titleBarStyle = computed(() => {
  const c = platformMeta.getColor(fsSlug.value)
  return c ? { '--platform-color': `#${c}` } : {}
})
// Same priority the Retro library uses: EmulationStation XML in the user's
// language, then the scraped Wikipedia text, then the English XML.
const platformDescription = computed(() => {
  const lang = localStorage.getItem('gd3_locale') || 'en'
  const d = platformMeta.meta[fsSlug.value]?.descriptions
  return d?.[lang] || info.value?.description || d?.['en'] || ''
})

const PAGE_SIZE = 60
const items = ref<RomSourceEntry[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const errMsg = ref('')
// A page that failed while appending, reported beside the sentinel so the rows
// already on screen survive it. Separate from errMsg, which owns the whole view.
const moreErr = ref('')

const searchInput = ref('')
const query = ref('')
const region = ref('')
const sort = ref('name_asc')
// Which catalogue to show, when the source stands in front of several. The
// options come from the listing itself, so a single-catalogue source never
// renders the filter at all.
const collection = ref('')
const collectionOptions = ref<string[]>([])
// Container filter (chd / zip / iso ...): the same game often exists in two
// containers, and one of them is a quarter of the size.
const format = ref('')
const formatOptions = ref<string[]>([])
// Release type (retail / prototype / translation / hack ...): big sets mix a
// finished game with its prototypes, demos and fan patches.
const kind = ref('')
const kindOptions = ref<string[]>([])
function kindLabel(k: string): string {
  return t(`romsrc.kind_${k}`, k.charAt(0).toUpperCase() + k.slice(1))
}
// A look at one game, fetched only when a row is opened and then kept for the
// session. Keyed by the game rather than the row, so opening "Sonic (USA)" and
// then "Sonic (Europe)" costs one lookup, not two.
const previewFor = ref('')
// Busy per game, not one flag for the view: two rows opened in quick succession
// are two lookups in flight, and a single flag would let the first to answer
// declare the second one finished - flashing "nothing found" over a row whose
// own lookup is still running.
const peekBusyKeys = reactive<Set<string>>(new Set())
const peeks = reactive<Record<string, RomSourcePreview>>({})

function peekKey(e: RomSourceEntry): string {
  return romSourceActions.previewKey(fsSlug.value, e)
}
function peek(e: RomSourceEntry) {
  return peeks[peekKey(e)]
}
function peekBusyFor(e: RomSourceEntry): boolean {
  return peekBusyKeys.has(peekKey(e))
}
async function togglePreview(e: RomSourceEntry) {
  if (previewFor.value === e.id) { previewFor.value = ''; return }
  previewFor.value = e.id
  const key = peekKey(e)
  if (peeks[key] || peekBusyKeys.has(key)) return
  peekBusyKeys.add(key)
  try {
    peeks[key] = await romSourceActions.previewEntry(fsSlug.value, e)
  } catch {
    peeks[key] = { found: false, query: '', source: null }
  } finally {
    peekBusyKeys.delete(key)
  }
}

// Rows already in the library are hidden on request rather than dropped
// server-side, so the count keeps meaning "what the source has".
const hideOwned = ref(localStorage.getItem('romsrc-hide-owned') === '1')
watch(hideOwned, v => localStorage.setItem('romsrc-hide-owned', v ? '1' : '0'))

// Region options accumulate from what the listing actually returns (the source
// filters by exact region), so the dropdown only ever offers real choices.
const regionsSeen = reactive<Set<string>>(new Set())
const regionOptions = computed(() => Array.from(regionsSeen).sort())

const hasMore = computed(() => items.value.length < total.value)
const shownItems = computed(() =>
  hideOwned.value ? items.value.filter(e => !isOwned(e)) : items.value,
)

// Per-row transient state: queued -> downloading -> (owned | error). Keyed on
// the entry id (the source's member URL), which is also the download job's
// entry_id in the progress events.
interface RowState { status: 'queued' | 'downloading' | 'error'; percent?: number; error?: string }
const rowState = reactive<Record<string, RowState>>({})

// Per-row watchdog: a live download emits progress ~1/s, so 90s of silence means
// the backend job is gone (a mid-download container restart, the routine deploy
// case) with no terminal event coming - flip the row to error so it never hangs
// "downloading"/"queued" with no way to retry. Re-armed on every progress tick;
// cleared on complete/error/unmount. Mirrors the download tray's watchdog.
const rowTimers = new Map<string, ReturnType<typeof setTimeout>>()
function armRowWatchdog(id: string) {
  const ex = rowTimers.get(id); if (ex) clearTimeout(ex)
  rowTimers.set(id, setTimeout(() => {
    rowTimers.delete(id)
    const s = rowState[id]?.status
    if (s === 'queued' || s === 'downloading') rowState[id] = { status: 'error', error: t('romsrc.timed_out', 'Timed out') }
  }, 90000))
}
function clearRowWatchdog(id: string) {
  const ex = rowTimers.get(id); if (ex) { clearTimeout(ex); rowTimers.delete(id) }
}

// Locally-downloaded this session (so a row flips to "In library" at once,
// before the next listing fetch reflects it).
const ownedNow = reactive<Set<string>>(new Set())

const selected = reactive<Set<string>>(new Set())
const bulkBusy = ref(false)

function isOwned(e: RomSourceEntry): boolean {
  return e.owned || ownedNow.has(e.id)
}
function isBusy(e: RomSourceEntry): boolean {
  const s = rowState[e.id]?.status
  return s === 'queued' || s === 'downloading'
}

// Arcade sources show a real title but keep the emulator's set name on disk, and
// sibling revisions can share a title. Shown only when neither name can be read
// off the other, so an ordinary row (where the file IS the title, give or take a
// region tag) stays clean.
function setName(e: RomSourceEntry): string {
  const stem = (e.filename || '').replace(/\.[^.]+$/, '')
  const title = (e.title || '').toLowerCase()
  const low = stem.toLowerCase()
  if (!stem || !title || title.includes(low) || low.includes(title)) return ''
  return stem
}

const selectableRows = computed(() => items.value.filter(e => !isOwned(e) && !isBusy(e)))
const allSelected = computed(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(e => selected.has(e.id)),
)

function toggleOne(id: string) {
  if (selected.has(id)) selected.delete(id)
  else selected.add(id)
}
function toggleAll() {
  if (allSelected.value) selectableRows.value.forEach(e => selected.delete(e.id))
  else selectableRows.value.forEach(e => selected.add(e.id))
}


// Monotonic guard: search / region / sort / page can each fire load() while a
// prior one is still in flight, and responses can arrive out of order - only the
// latest issued request is allowed to write items/total, so a slow older result
// never overwrites a newer filter/sort.
let loadSeq = 0
// One list, grown as the user scrolls: `load()` starts it over, `loadMore()`
// appends the next page. A source can hold tens of thousands of ROMs, so pages
// are still fetched one at a time; only the pager is gone.
async function load(append = false) {
  const seq = ++loadSeq
  loading.value = true
  errMsg.value = ''
  try {
    const res = await romSourceActions.listRoms(sourceId.value, fsSlug.value, {
      page: page.value, pageSize: PAGE_SIZE,
      query: query.value, region: region.value, sort: sort.value,
      collection: collection.value, format: format.value, kind: kind.value,
    })
    if (seq !== loadSeq) return
    const batch = res.items || []
    items.value = append ? items.value.concat(batch) : batch
    total.value = res.total || 0
    // The source reports every catalogue and format it has for this platform,
    // so the options survive a filtered listing instead of collapsing to the
    // one currently selected.
    collectionOptions.value = res.collections || []
    formatOptions.value = res.formats || []
    kindOptions.value = res.kinds || []
    for (const it of batch) if (it.region) regionsSeen.add(it.region)
  } catch (e: any) {
    if (seq !== loadSeq) return
    const msg = e?.response?.data?.detail || String(e)
    if (append) {
      // A page that failed on the way in must not take the hundreds of rows
      // already on screen with it: errMsg wins over the list branch, and with
      // the list gone there is nothing left to scroll to ask for it again.
      // Report it beside the sentinel and leave the list where it is.
      moreErr.value = msg
    } else {
      errMsg.value = msg
      items.value = []
      total.value = 0
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function reload() {
  page.value = 1
  selected.clear()
  moreErr.value = ''
  load(false)
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  // A page that just failed must not be retried by every scroll tick; the user
  // asks for it again through the retry button beside the sentinel.
  if (moreErr.value) return
  page.value += 1
  await load(true)
}

// Ask for the page that failed once more. `page` was already advanced onto it,
// so this repeats that page rather than skipping over it.
async function retryMore() {
  moreErr.value = ''
  await load(true)
}

// Pull pages until the list is long enough to scroll, or the source runs out.
//
// Scrolling is the only thing that asks for the next page, so a list that does
// not overflow its own box can never ask for one. That is reachable two ways: a
// page whose rows are nearly all owned while "hide what I already have" is on,
// and a window tall enough that 60 rows do not fill it. Either way the user sees
// a short list with no way to reach the rest.
async function fillViewport() {
  for (let guard = 0; guard < 20; guard++) {
    await nextTick()
    const el = listEl.value
    // No list element means an error, empty or all-owned state is showing:
    // nothing to fill, and nothing that could scroll.
    if (!el || !hasMore.value || loading.value || moreErr.value) return
    if (el.scrollHeight > el.clientHeight + 8) return
    const before = items.value.length
    await loadMore()
    if (items.value.length === before) return
  }
}

watch([hideOwned, shownItems], () => { fillViewport() })

// Search is server-side; debounce the input into `query` and reset to page 1.
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (v) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { query.value = v.trim(); reload() }, 350)
})
// True while the fsSlug watcher is clearing the filters. Those clears would
// otherwise each look like the user changing a filter and queue a reload of
// their own, on top of the one the platform switch already does.
let switchingPlatform = false

watch([region, sort, collection, format, kind], () => {
  if (switchingPlatform) return
  reload()
})
// Platform changed under us (switcher): reset and reload. The collection filter
// goes too - a catalogue that carried the old platform need not carry this one.
watch(fsSlug, async () => {
  switchingPlatform = true
  query.value = ''; searchInput.value = ''
  collection.value = ''; collectionOptions.value = []
  format.value = ''; formatOptions.value = []
  kind.value = ''; kindOptions.value = []
  // The region goes with them. Its options accumulate from what a listing
  // returned, so a region carried over from the last platform can filter the
  // new one down to nothing and read as "this platform is empty".
  region.value = ''; regionsSeen.clear()
  // Let the filter watcher see the cleared values and skip, then reload once.
  await nextTick()
  switchingPlatform = false
  loadPlatformInfo()
  reload()
})

async function downloadOne(e: RomSourceEntry) {
  if (isOwned(e) || isBusy(e)) return
  rowState[e.id] = { status: 'queued' }
  armRowWatchdog(e.id)
  selected.delete(e.id)
  try {
    const res = await romSourceActions.download(sourceId.value, e.id)
    if (res.skipped?.length && !res.queued?.length) {
      const reason = String(res.skipped[0]?.reason || '')
      // "already downloading" is benign - leave it queued; anything else is a
      // real refusal, so surface it on the row.
      if (!reason.includes('already')) rowState[e.id] = { status: 'error', error: reason }
    }
  } catch (err: any) {
    rowState[e.id] = { status: 'error', error: err?.response?.data?.detail || String(err) }
  }
}

async function downloadSelected() {
  const ids = Array.from(selected)
  if (!ids.length || bulkBusy.value) return
  bulkBusy.value = true
  ids.forEach(id => { rowState[id] = { status: 'queued' }; armRowWatchdog(id) })
  selected.clear()
  try {
    const res = await romSourceActions.download(sourceId.value, ids)
    for (const sk of res.skipped || []) {
      const id = String((sk as any).entry_id || '')
      const reason = String((sk as any).reason || '')
      if (id && !reason.includes('already')) rowState[id] = { status: 'error', error: reason }
    }
  } catch (err: any) {
    ids.forEach(id => { rowState[id] = { status: 'error', error: err?.response?.data?.detail || String(err) } })
  } finally {
    bulkBusy.value = false
  }
}

// Follow romsource:download_* keyed on entry_id (the row id).
let unsub: (() => void) | null = null
function onRomEvent(event: string, data: Record<string, unknown>) {
  const id = String(data.entry_id || '')
  if (!id) return
  if (event === 'complete') {
    clearRowWatchdog(id)
    delete rowState[id]
    ownedNow.add(id)
  } else if (event === 'error') {
    clearRowWatchdog(id)
    rowState[id] = { status: 'error', error: String(data.error || '') }
  } else {
    const pct = Number(data.percent)
    rowState[id] = { status: 'downloading', percent: pct >= 0 ? pct : 0 }
    armRowWatchdog(id)
  }
}

// The sentinel sits under the last row: when it scrolls into view the next page
// is fetched and appended, which is what replaced the pager.
const sentinel = ref<HTMLElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

// ...but the sentinel only fires when the page itself scrolls, and here the list
// is usually the scrolling element, with the sentinel parked below it in plain
// view - permanently "visible", so its state never changed and nothing was ever
// appended. Watching the scroll position of whatever actually scrolled covers
// every layout. Capture phase, because scroll events do not bubble.
function onAnyScroll(e: Event) {
  const node = (e.target === document ? document.scrollingElement : e.target) as HTMLElement | null
  if (!node || typeof node.scrollTop !== 'number') return
  // Capture phase sees every scroll on the page, so check this is OUR list (or
  // an ancestor scrolling it) before pulling a page. Classic keeps its library
  // sidebar mounted beside this view, and scrolling that unrelated list would
  // otherwise fetch page after page of a source the user is not even touching.
  const list = listEl.value
  if (!list) return
  if (node !== list && !node.contains(list)) return
  if (node.scrollTop + node.clientHeight >= node.scrollHeight - 600) loadMore()
}

onMounted(() => {
  load()
  loadPlatformInfo()
  try { unsub = socketStore.onRomSource(onRomEvent) } catch { /* socket not ready */ }
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(
      entries => { if (entries.some(e => e.isIntersecting)) loadMore() },
      { rootMargin: '400px' },
    )
    if (sentinel.value) observer.observe(sentinel.value)
  }
  window.addEventListener('scroll', onAnyScroll, true)
})
onUnmounted(() => {
  if (observer) { observer.disconnect(); observer = null }
  window.removeEventListener('scroll', onAnyScroll, true)
  if (unsub) { unsub(); unsub = null }
  if (searchTimer) clearTimeout(searchTimer)
  rowTimers.forEach(t => clearTimeout(t)); rowTimers.clear()
})
</script>

<style scoped>
.rsl-view {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  padding: 20px 28px; gap: var(--space-4, 16px);
}

/* ── Title bar ────────────────────────────────────────────────────────────
   Deliberately the same furniture as the Retro library's platform header, down
   to the hero settings it honours, so the two views read as one place. */
.rsl-title-bar {
  position: relative; overflow: hidden;
  display: flex; align-items: flex-start; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-3, 12px); flex-shrink: 0;
  padding: 16px 20px;
  /* Locked to its natural height so it neither compresses nor grows with the
     controls: 170px = 120px platform icon + 2x16px padding + 4px offset. */
  min-height: 170px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid color-mix(in srgb, var(--platform-color, transparent) 40%, var(--glass-border));
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
  background-size: cover; background-position: center;
  transition: background-image .4s ease;
}
.rsl-title-bar--photo {
  border-color: rgba(255,255,255,.14);
  box-shadow: 0 4px 32px rgba(0,0,0,0.5);
}
/* Hero background - respects the hero blur + animation settings */
.rsl-title-bg {
  position: absolute; inset: -20px; z-index: 0;
  background-size: cover; background-position: center;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(110%) brightness(.55);
  transform-origin: center; transform: scale(1.06);
  will-change: transform;
}
.rsl-title-bg--kenburns { animation: rsl-kenburns 44s ease-in-out infinite; }
.rsl-title-bg--drift    { animation: rsl-drift 28s ease-in-out infinite alternate; }
.rsl-title-bg--pulse    { animation: rsl-pulse 10s ease-in-out infinite; }
@keyframes rsl-kenburns { 0%,100% { transform: scale(1.06) translateX(0%); } 50% { transform: scale(1.14) translateX(-3%); } }
@keyframes rsl-drift    { 0% { transform: scale(1.1) translateX(0%); } 100% { transform: scale(1.1) translateX(-5%); } }
@keyframes rsl-pulse    { 0%,100% { transform: scale(1.04); } 50% { transform: scale(1.12); } }

.rsl-title-photo-overlay {
  position: absolute; inset: 0; z-index: 0;
  background: linear-gradient(135deg, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.45) 60%, rgba(0,0,0,0.62) 100%);
}

.rsl-title-left  { display: flex; align-items: flex-start; gap: var(--space-4, 16px); position: relative; z-index: 1; }
.rsl-title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; justify-content: flex-end; max-width: 42%; position: relative; z-index: 1; }
.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
  cursor: pointer; font-family: inherit; transition: all var(--transition); flex-shrink: 0;
  margin-top: 4px;
}
.lib-back-btn:hover { color: var(--text); background: rgba(255,255,255,.1); }

/* Platform identity: icon, wordmark, count */
.rsl-platform-identity { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.rsl-platform-icon {
  width: 120px; height: 120px; object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.5));
}
.rsl-platform-name-logo {
  max-width: 260px; max-height: 44px; object-fit: contain;
  filter: drop-shadow(0 1px 8px rgba(0,0,0,.6)) brightness(1.15);
}
.rsl-platform-name-text {
  font-size: var(--fs-2xl, 22px); font-weight: 800; color: var(--text); line-height: 1.1;
}
.rsl-count { font-size: 11px; color: var(--muted); }

/* Center: console photo left, facts right - absolutely centred on the bar */
.rsl-title-center {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  z-index: 1; pointer-events: none;
  display: flex; flex-direction: row; align-items: center; gap: 18px;
  max-width: 560px; width: max-content;
}
.rsl-title-center > * { pointer-events: auto; }
.rsl-console-photo-col { flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.rsl-console-photo {
  max-height: 110px; max-width: 200px; object-fit: contain;
  filter: drop-shadow(0 4px 20px rgba(0,0,0,0.75));
  transition: transform .3s ease;
}
.rsl-console-photo:hover { transform: scale(1.04); }
.rsl-console-info-col { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.rsl-console-meta { display: flex; gap: 5px; flex-wrap: wrap; }
.rsl-meta-chip {
  padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700;
  background: color-mix(in srgb, var(--pl) 14%, transparent);
  color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 28%, transparent);
  letter-spacing: .3px;
}
.rsl-console-desc-wrap { position: relative; }
.rsl-console-desc {
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.72); line-height: 1.6; margin: 0;
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical;
  overflow: hidden; max-width: 340px;
}
.rsl-wiki-link-inline {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: var(--fs-xs, 10px); font-weight: 700; color: rgba(255,255,255,.5);
  text-decoration: none; letter-spacing: .4px; margin-top: 2px;
  transition: color var(--transition), opacity var(--transition);
}
.rsl-wiki-link-inline:hover { color: var(--pl-light); opacity: 1; }

.rsl-search-wrap { position: relative; }
.rsl-search-ico { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); color: var(--muted); pointer-events: none; }
.rsl-search {
  width: 200px; max-width: 40vw; padding: 6px 24px 6px 28px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--text); font-size: 13px; font-family: inherit; outline: none;
  transition: border-color var(--transition);
}
.rsl-search:focus { border-color: var(--pl); }
.rsl-search-x {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--muted); font-size: 16px; cursor: pointer; line-height: 1;
}
.rsl-select {
  height: 32px; padding: 0 26px 0 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-family: inherit; cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
  transition: border-color var(--transition), color var(--transition);
}
.rsl-select:hover { border-color: var(--pl); color: var(--text); }
.rsl-select option { background: var(--bg-card, #12101a); color: var(--text); }
.rsl-chip-btn {
  display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px;
  border-radius: var(--radius-sm); border: 1px solid var(--glass-border);
  background: var(--glass-bg); color: var(--muted);
  font-size: var(--fs-sm, 12px); font-family: inherit; cursor: pointer; white-space: nowrap;
  transition: border-color var(--transition), color var(--transition), background var(--transition);
}
.rsl-chip-btn:hover { border-color: var(--pl); color: var(--text); }
.rsl-more-err { font-size: var(--fs-sm, 12px); color: var(--danger, #ff6b6b); }
.rsl-more-retry {
  margin-left: 10px; height: 26px; padding: 0 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--text); font-size: var(--fs-sm, 12px); font-family: inherit; cursor: pointer;
}
.rsl-more-retry:hover { border-color: var(--pl); }
.rsl-chip-btn.active {
  border-color: var(--pl); color: var(--text);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
}

/* ── Action bar ─────────────────────────────────────────────────────────── */
.rsl-action-bar {
  display: flex; align-items: center; gap: var(--space-3, 12px); flex-shrink: 0;
  padding: 8px 14px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.03); border: 1px solid var(--glass-border);
}
.rsl-check-label { display: inline-flex; align-items: center; gap: 7px; font-size: var(--fs-sm, 12px); color: var(--muted); cursor: pointer; }
.rsl-check-label input, .rsl-row-check input { accent-color: var(--pl); cursor: pointer; }
.rsl-sel-count { font-size: var(--fs-sm, 12px); color: var(--muted); }
.rsl-dl-selected {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--pl); background: var(--pl-dim); color: var(--pl-light);
  font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit; cursor: pointer;
  transition: all var(--transition);
}
.rsl-dl-selected:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 28%, transparent); }
.rsl-dl-selected:disabled { opacity: .45; cursor: not-allowed; }

/* ── States ─────────────────────────────────────────────────────────────── */
.rsl-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: var(--fs-md, 14px); padding: 60px;
}
.rsl-state--err { color: #ff8b8b; }
.spinner {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.15); border-top-color: var(--pl-light);
  animation: spin .8s linear infinite; display: inline-block;
}

/* ── List ───────────────────────────────────────────────────────────────── */
.rsl-list {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  scrollbar-gutter: stable; padding-right: 6px;
  display: flex; flex-direction: column; gap: 3px;
  transition: opacity .15s;
}
.rsl-list--loading { opacity: .55; pointer-events: none; }
.rsl-row {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 9px 14px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.03); border: 1px solid transparent;
  transition: background var(--transition), border-color var(--transition);
}
.rsl-row:hover { background: rgba(255,255,255,.06); border-color: var(--glass-border); }
.rsl-row--owned { opacity: .72; }
.rsl-row-check { display: inline-flex; align-items: center; width: 18px; flex-shrink: 0; }
.rsl-row-check--placeholder { width: 18px; }
.rsl-row-main { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; }
.rsl-row-title {
  font-size: 13px; font-weight: 500; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Look-up affordance: quiet until hovered, lit while its panel is open. */
.rsl-row-peek {
  flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px;
  background: transparent; color: var(--text-muted, #8a8f98); cursor: pointer;
  opacity: .55; transition: opacity .15s, color .15s, background .15s;
}
.rsl-row:hover .rsl-row-peek { opacity: 1; }
.rsl-row-peek:hover,
.rsl-row-peek.open {
  opacity: 1; color: var(--pl-light, var(--pl));
  background: color-mix(in srgb, var(--pl) 16%, transparent);
}
.rsl-row-title--peek { cursor: pointer; }
.rsl-row-title--peek:hover { color: var(--pl-light, var(--pl)); }

/* The panel itself: a strip under its own row, so the list never jumps. */
.rsl-peek {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 12px 16px 14px 46px;
  background: color-mix(in srgb, var(--pl) 6%, transparent);
  border-bottom: 1px solid var(--border, rgba(255,255,255,.07));
}
.rsl-peek-load { padding: 6px 0; }
.rsl-peek-cover {
  width: 78px; border-radius: 6px; flex-shrink: 0;
  box-shadow: 0 2px 10px rgba(0,0,0,.35);
}
.rsl-peek-facts { min-width: 0; }
.rsl-peek-name { font-size: 15px; font-weight: 700; color: var(--text); }
.rsl-peek-line {
  display: flex; flex-wrap: wrap; gap: 10px; margin-top: 3px;
  font-size: 12px; color: var(--text-muted, #8a8f98);
}
.rsl-peek-sum {
  margin: 7px 0 0; font-size: 12.5px; line-height: 1.45; color: var(--text-dim, #b6bcc6);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.rsl-peek-src {
  margin-top: 6px; font-size: 10px; letter-spacing: .04em; text-transform: uppercase;
  color: var(--text-muted, #8a8f98); opacity: .7;
}
.rsl-peek-none { font-size: 12.5px; color: var(--text-muted, #8a8f98); }

/* The emulator's set name, next to a title it cannot be guessed from. */
.rsl-row-set {
  flex-shrink: 0; font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--fs-xs, 10px); color: var(--text-muted, #8a8f98); opacity: .75;
}
.rsl-region-badge {
  flex-shrink: 0; font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .3px;
  padding: 2px 7px; border-radius: 999px;
  color: var(--pl-light, var(--pl));
  background: color-mix(in srgb, var(--pl) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 30%, transparent);
}
/* Which catalogue a row came from: quieter than the region badge, since it only
   tells sets apart and is hidden entirely for a single-catalogue source. */
.rsl-coll-badge {
  flex-shrink: 0; font-size: var(--fs-xs, 10px); font-weight: 600;
  padding: 2px 7px; border-radius: 999px;
  color: var(--muted); background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.08);
  max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rsl-row-size { font-size: 11px; color: var(--muted); flex-shrink: 0; width: 68px; text-align: right; }
.rsl-row-action { flex-shrink: 0; display: flex; align-items: center; gap: 8px; min-width: 118px; justify-content: flex-end; }

.rsl-dl-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.rsl-dl-btn:hover { border-color: var(--pl); color: var(--pl-light); background: var(--pl-dim); }
.rsl-dl-btn--retry { color: #fca5a5; border-color: rgba(239,68,68,.35); }

.rsl-owned-chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-sm, 12px); font-weight: 600; color: #22c55e;
}
.rsl-state-chip { font-size: var(--fs-sm, 12px); font-weight: 600; }
.rsl-state-chip--queued { color: var(--muted); }
.rsl-state-chip--error { color: #f87171; cursor: help; }

.rsl-prog { display: flex; align-items: center; gap: 7px; width: 118px; }
.rsl-prog-track { flex: 1; height: 4px; border-radius: 2px; background: rgba(255,255,255,.08); overflow: hidden; }
.rsl-prog-fill { height: 100%; background: linear-gradient(90deg, var(--pl), var(--pl-light, var(--pl))); transition: width .3s ease; }
.rsl-prog-pct { font-size: 11px; color: var(--pl-light, var(--pl)); font-weight: 600; width: 34px; text-align: right; }

/* ── Endless list ───────────────────────────────────────────────────────── */
.rsl-sentinel {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  flex-shrink: 0; padding: 10px 0 4px; min-height: 26px;
}
.rsl-end { font-size: var(--fs-xs, 10px); color: var(--muted); letter-spacing: .3px; }
.rsl-chip-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 11px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 500;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.rsl-chip-btn:hover { color: var(--text); background: rgba(255,255,255,.09); }
.rsl-chip-btn.active {
  color: var(--pl-light, var(--pl));
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  border-color: color-mix(in srgb, var(--pl) 35%, transparent);
}

/* ── Narrow screens ────────────────────────────────────────────────────────
   The centred console panel has nowhere to go once the controls wrap, so it
   steps aside and the bar shrinks back to identity plus filters. */
@media (max-width: 1100px) {
  .rsl-title-center { display: none; }
  .rsl-title-right { max-width: none; }
}
@media (max-width: 600px) {
  .rsl-title-bar { min-height: 0; padding: 10px 12px; gap: var(--space-2, 8px); }
  .rsl-platform-icon { width: 56px; height: 56px; }
  .rsl-platform-name-logo { max-height: 28px; max-width: 170px; }
}
</style>
