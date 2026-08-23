<template>
  <div class="library-view">
    <!-- ── Title bar (same chrome as the Games library) ────────────────────── -->
    <div class="title-bar">
      <div class="title-left">
        <button class="lib-back-btn" @click="goBack" :title="backLabel">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ backLabel }}
        </button>

        <!-- Grid mode: the Collections index icon. Detail mode: the collection's stacked cover. -->
        <div v-if="mode === 'detail' && detail" class="title-coll-cover">
          <CollectionCover :cover="detail.cover_path" :covers="detail.member_covers" :name="detail.name" color="var(--pl)" />
        </div>
        <LibraryIcon
          v-else
          :icon="indexIcon" :color="indexColor" :size="48"
          class="title-ico-svg"
          :style="{ filter: 'drop-shadow(0 0 8px ' + indexColor + '88)' }"
        />

        <div>
          <h1 class="title-text">{{ mode === 'detail' ? (detail?.name || '') : collectionsLabel }}</h1>
          <p class="title-sub">{{ subtitle }}</p>
        </div>
      </div>

      <div class="title-right">
        <!-- New collection (admin, grid mode) -->
        <button v-if="mode === 'grid' && isAdmin" class="coll-edit-btn" @click="openCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {{ t('collections.create') }}
        </button>

        <!-- Edit (admin, detail mode) -->
        <button v-if="mode === 'detail' && detail && isAdmin" class="coll-edit-btn" @click="showEdit = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('collections.edit') }}
        </button>

        <!-- Sort -->
        <select v-model="sortBy" class="sort-select">
          <template v-if="mode === 'grid'">
            <option value="title">{{ t('library.a_to_z') }}</option>
            <option value="title_desc">{{ t('library.z_to_a') }}</option>
            <option value="newest">{{ t('library.newest') }}</option>
            <option value="oldest">{{ t('library.oldest') }}</option>
            <option value="games">{{ t('collections.sort_most_games') }}</option>
            <option value="games_asc">{{ t('collections.sort_fewest_games') }}</option>
          </template>
          <template v-else>
            <option value="title">{{ t('library.a_to_z') }}</option>
            <option value="title_desc">{{ t('library.z_to_a') }}</option>
            <option value="release">{{ t('library.newest') }}</option>
            <option value="release_asc">{{ t('library.oldest') }}</option>
            <option value="rating">{{ t('library.top_rated') }}</option>
          </template>
        </select>

        <!-- Cover size (cover mode only) -->
        <div v-if="viewMode === 'cover'" class="size-group" :title="t('library.cover_size')">
          <button v-for="sz in coverSizes" :key="sz.id" class="size-btn" :class="{ active: currentCoverSize === sz.id }" @click="currentCoverSize = sz.id">{{ sz.label }}</button>
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

    <!-- ── List view: About + Details band as a fixed header (outside the scroll,
         so the games clip cleanly beneath it instead of sliding under it). ───── -->
    <CollectionInfo v-if="mode === 'detail' && detail && viewMode === 'list'" :detail="detail" layout="band" />

    <!-- ── Loading ─────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="state-empty">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin" style="opacity:.3"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
    </div>

    <!-- ── Empty ───────────────────────────────────────────────────────────── -->
    <div v-else-if="missing" class="state-empty">
      <p>{{ t('collections.not_found') }}</p>
    </div>

    <div v-else-if="!items.length" class="state-empty">
      <p>{{ mode === 'detail' ? t('collections.no_games') : t('collections.empty') }}</p>
    </div>

    <!-- ── Main (grid + alpha sidebar) ─────────────────────────────────────── -->
    <div v-else class="library-main">
      <div class="grid-scroll" ref="gridScrollEl">
        <!-- COVER GRID -->
        <div v-if="viewMode === 'cover'" class="cover-grid"
             :style="mode === 'detail' ? { gridTemplateColumns: `repeat(${detailCols}, minmax(0, 1fr))` } : { '--cover-min': coverSizeMap[currentCoverSize] + 'px' }">
          <div v-for="(it, idx) in visibleItems" :key="it._key" class="cover-wrap" :data-alpha-idx="idx" @click="openItem(it)">
            <div class="cover-img-wrap" :class="{ 'cover-img-wrap--coll': mode === 'grid' }"
                 :style="mode === 'grid' && it.cover_path && collCoverRatios[it._key] ? { aspectRatio: String(collCoverRatios[it._key]) } : undefined">
              <!-- Collection tile: a custom cover keeps its own aspect ratio
                   (landscape / portrait / square); otherwise the fanned member
                   covers fill a square. Member game (detail): plain cover. -->
              <template v-if="mode === 'grid'">
                <img v-if="it.cover_path" :src="it.cover_path" :alt="it.title" class="cover-img" loading="lazy" @load="onCollCoverLoad($event, it._key)" />
                <CollectionCover v-else :covers="it.member_covers" :name="it.title" color="var(--pl)" />
              </template>
              <template v-else>
                <img v-if="it.cover_path" :src="it.cover_path" :alt="it.title" class="cover-img" loading="lazy" />
                <div v-else class="cover-fallback">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.25"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                </div>
              </template>
              <div v-if="mode === 'grid'" class="badge badge--count">{{ it.member_count }}</div>
              <div class="cover-overlay"><div class="overlay-title">{{ it.title }}</div></div>
            </div>
            <div class="cover-title">{{ it.title }}</div>
            <div class="cover-scores">
              <span v-if="mode === 'grid'" class="cover-sub">{{ it.member_count === 1 ? t('home.game_count', { count: it.member_count }) : t('home.game_count_plural', { count: it.member_count }) }}</span>
              <span v-if="mode === 'grid' && it.years" class="cover-sub">{{ it.years }}</span>
              <span v-if="mode === 'detail' && it.year" class="cover-sub">{{ it.year }}</span>
              <span v-if="mode === 'detail' && it.rating" class="cover-score"><svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color:#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>{{ Number(it.rating).toFixed(1) }}</span>
            </div>
          </div>
        </div>

        <!-- LIST VIEW (mirrors the games library list-row) -->
        <div v-else class="list-view">
          <template v-for="(it, idx) in visibleItems" :key="it._key">
          <!-- Member games: the exact Games-library row (shared component).
               A GOG-sourced member opens in the GOG library, others in Games. -->
          <GameListRow v-if="mode === 'detail'" :game="it" :idx="idx" @open="openMember" />
          <!-- Collection tiles: fan cover + aggregated facts -->
          <div v-else class="list-row" @click="openItem(it)">
            <div class="list-cover-wrap">
              <div class="cover-img-wrap cover-img-wrap--coll">
                <CollectionCover :cover="it.cover_path" :covers="it.member_covers" :name="it.title" color="var(--pl)" />
              </div>
            </div>
            <div class="list-info">
              <div class="list-title">
                <img v-if="it.logo_path" :src="it.logo_path" :alt="it.title" class="list-coll-logo" />
                <span v-else>{{ it.title }}</span>
              </div>
              <div class="list-meta"><span v-if="it.years">{{ it.years }}</span></div>
            </div>
            <div class="list-hero">
              <img v-if="heroOf(it)" :src="heroOf(it) || ''" :alt="it.title" :class="['list-hero-img', listHeroAnimClass]" loading="lazy" />
              <div class="list-hero-overlay" />
              <div v-if="descText(it)" class="list-hero-desc"><p class="list-hero-desc-text">{{ descText(it) }}</p></div>
            </div>
            <!-- Same Details table as the collection-detail band/side (shared
                 component) so the aggregated facts read identically and the wide
                 value column wraps long studio names cleanly. -->
            <div class="list-details">
              <CollectionDetails :detail="it" compact />
            </div>
          </div>
          </template>
        </div>

        <!-- Sentinel: nearing the viewport mounts the next batch. -->
        <div ref="listSentinel" class="load-sentinel" aria-hidden="true"></div>
      </div>

      <!-- Cover/grid view: About + Details as a side panel (like a game detail) -->
      <CollectionInfo v-if="mode === 'detail' && detail && viewMode === 'cover'" :detail="detail" layout="side" />

      <!-- Alphabet sidebar (collection grid only; detail uses the info panel/band) -->
      <div v-if="mode === 'grid'" class="alpha-nav">
        <button v-for="letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ#'.split('')" :key="letter" class="alpha-btn"
                :class="{ available: availableLetters.has(letter), active: activeLetter === letter }" @click="scrollToLetter(letter)">{{ letter }}</button>
      </div>
    </div>

    <!-- ── Admin metadata editor ───────────────────────────────────────────── -->
    <Teleport to="body">
      <CollectionMetadataPanel
        v-if="showEdit && detail"
        :collection="detail"
        @close="showEdit = false"
        @updated="onCollectionUpdated"
        @deleted="onCollectionDeleted"
      />
    </Teleport>

    <!-- ── Quick create (admin) ────────────────────────────────────────────── -->
    <div v-if="showCreate" class="cc-create-overlay" @click.self="showCreate = false">
      <div class="cc-create-modal" @click.stop>
        <div class="cc-create-title">{{ t('collections.create') }}</div>
        <input ref="createInput" v-model="newName" class="cc-create-input" :placeholder="t('collections.field_name')" @keydown.enter="createCollection" />
        <div v-if="createError" class="cc-create-err">{{ createError }}</div>
        <div class="cc-create-actions">
          <button class="cc-create-cancel" @click="showCreate = false">{{ t('common.cancel') }}</button>
          <button class="cc-create-ok" :disabled="creating || !newName.trim()" @click="createCollection">{{ t('collections.create_btn') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useIncrementalList } from '@/composables/useIncrementalList'
import { useRoute, useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useLibrariesStore } from '@/stores/libraries'
import { useCollectionsStore } from '@/stores/collections'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import LibraryIcon from '@/components/common/LibraryIcon.vue'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import CollectionMetadataPanel from '@/components/collections/CollectionMetadataPanel.vue'
import CollectionInfo from '@/components/collections/CollectionInfo.vue'
import CollectionDetails from '@/components/collections/CollectionDetails.vue'
import GameListRow from '@/components/games/GameListRow.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const libs = useLibrariesStore()
const collectionsStore = useCollectionsStore()
const auth = useAuthStore()
const themeStore = useThemeStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
// Match the Games/GOG list-hero motion (Ken Burns / drift / pulse, theme-driven).
const listHeroAnimClass = computed(() => 'list-hero-img--' + ((themeStore as any).heroAnimStyle || 'kenburns'))

const mode = computed<'grid' | 'detail'>(() => (route.params.slug ? 'detail' : 'grid'))
// The container library this view belongs to (/collections/:lib[/:slug]).
const container = computed(() => String(route.params.lib || ''))

const collections = ref<any[]>([])
const detail = ref<any | null>(null)
const loading = ref(false)
// A slug that names nothing. Distinct from a collection that exists and has no
// games yet: both left `detail` null, so the page told the reader "this
// collection has no games yet" about a collection that was never there.
const missing = ref(false)
const activeLetter = ref('')
const gridScrollEl = ref<HTMLElement>()

// A custom collection cover keeps its natural aspect ratio in the grid (clamped
// to a sane portrait..landscape range); the auto-fan of member covers stays square.
const collCoverRatios = ref<Record<string, number>>({})
function onCollCoverLoad(e: Event, key: string) {
  const img = e.target as HTMLImageElement
  if (img.naturalWidth && img.naturalHeight) {
    collCoverRatios.value[key] = Math.min(1.8, Math.max(0.62, img.naturalWidth / img.naturalHeight))
  }
}

const viewMode = ref<'cover' | 'list'>((localStorage.getItem('collections_view_mode') as 'cover' | 'list') || 'cover')
watch(viewMode, v => localStorage.setItem('collections_view_mode', v))
const sortBy = ref(localStorage.getItem('collections_sort_by') || 'title')
watch(sortBy, v => localStorage.setItem('collections_sort_by', v))

const coverSizes = [
  { id: 'xs', label: 'XS' }, { id: 's', label: 'S' }, { id: 'm', label: 'M' },
  { id: 'l', label: 'L' }, { id: 'xl', label: 'XL' }, { id: 'xxl', label: 'XXL' },
]
const currentCoverSize = ref(localStorage.getItem('collections-card-size') || 'xxl')
watch(currentCoverSize, v => localStorage.setItem('collections-card-size', v))
const coverSizeMap: Record<string, number> = { xs: 115, s: 145, m: 175, l: 215, xl: 265, xxl: 310 }

const indexLib = computed(() => libs.bySlug(container.value))
const indexIcon = computed(() => indexLib.value?.icon ?? 'builtin:layers')
const indexColor = computed(() => indexLib.value?.color ?? '#8b5cf6')

const collectionsLabel = computed(() => libs.label(container.value))
const backLabel = computed(() => (mode.value === 'detail' ? collectionsLabel.value : t('library.libraries')))

function yearRange(c: any): string {
  if (c.start_year && c.end_year && c.start_year !== c.end_year) return `${c.start_year} - ${c.end_year}`
  return c.start_year ? String(c.start_year) : (c.end_year ? String(c.end_year) : '')
}

// Normalised item list for the active mode.
const items = computed<any[]>(() => {
  if (mode.value === 'grid') {
    const list = collections.value.map(c => ({
      ...c, _key: 'c-' + c.slug, title: c.name, years: yearRange(c),
    }))
    return sortItems(list)
  }
  const games = (detail.value?.games || []).map((g: any) => ({
    ...g, _key: 'g-' + g.id, title: g.title,
    year: g.release_date ? String(g.release_date).slice(0, 4) : '',
    file_count: (g.files || []).filter((f: any) => f.is_available).length,
  }))
  return sortItems(games)
})

// Render tiles / members in batches that grow on scroll; visibleItems is a
// prefix of items, so the alphabet-jump indices still line up.
const { visible: visibleItems, ensure: ensureVisible, sentinel: listSentinel } =
  useIncrementalList(items)

function sortItems(list: any[]): any[] {
  const l = [...list]
  switch (sortBy.value) {
    case 'title':       l.sort((a, b) => a.title.localeCompare(b.title)); break
    case 'title_desc':  l.sort((a, b) => b.title.localeCompare(a.title)); break
    case 'games':       l.sort((a, b) => (b.member_count || 0) - (a.member_count || 0)); break
    case 'games_asc':   l.sort((a, b) => (a.member_count || 0) - (b.member_count || 0)); break
    case 'rating':      l.sort((a, b) => (b.rating || 0) - (a.rating || 0)); break
    case 'release':     l.sort((a, b) => (b.release_date || '').localeCompare(a.release_date || '')); break
    case 'release_asc': l.sort((a, b) => (a.release_date || '').localeCompare(b.release_date || '')); break
    case 'newest':      l.sort((a, b) => (b.end_year || b.start_year || 0) - (a.end_year || a.start_year || 0)); break
    case 'oldest':      l.sort((a, b) => (a.start_year || a.end_year || 9999) - (b.start_year || b.end_year || 9999)); break
  }
  return l
}

const subtitle = computed(() => {
  if (mode.value === 'grid') {
    const n = collections.value.length
    return n === 1 ? t('collections.count', { count: n }) : t('collections.count_plural', { count: n })
  }
  if (!detail.value) return ''
  const n = detail.value.games?.length || 0
  const parts = [n === 1 ? t('home.game_count', { count: n }) : t('home.game_count_plural', { count: n })]
  const yr = yearRange(detail.value)
  if (yr) parts.push(yr)
  if (detail.value.rating != null) parts.push('★ ' + Number(detail.value.rating).toFixed(1))
  return parts.join('  ·  ')
})

const availableLetters = computed(() => {
  const set = new Set<string>()
  for (const it of items.value) {
    const c = (it.title || '').replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    set.add(/[A-Z]/.test(c) ? c : '#')
  }
  return set
})

async function scrollToLetter(letter: string) {
  const idx = items.value.findIndex(it => {
    const first = (it.title || '').replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    return letter === '#' ? !/[A-Z]/.test(first) : first === letter
  })
  if (idx === -1) return
  activeLetter.value = letter
  ensureVisible(idx)
  await nextTick()
  const sel = viewMode.value === 'list' ? '.cl-row' : '.cover-wrap'
  const card = gridScrollEl.value?.querySelectorAll(sel)[idx] as HTMLElement | undefined
  card?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// Hero background for a list row: a RANDOM member's art for a collection (stable
// per collection for the view's lifetime), the game's own background otherwise.
const _heroPick = new Map<string, string>()
function heroOf(it: any): string | null {
  if (mode.value === 'grid') {
    const pool: string[] = (it.member_heroes && it.member_heroes.length) ? it.member_heroes : (it.member_covers || [])
    if (!pool.length) return null
    if (!_heroPick.has(it.slug)) _heroPick.set(it.slug, pool[Math.floor(Math.random() * pool.length)])
    return _heroPick.get(it.slug) || pool[0]
  }
  return it.background_path || it.cover_path || null
}
// List view shows the SHORT description. Collections use ONLY the short one (the
// long one is reserved for the detail "About"); member games fall back to long.
function descText(it: any): string {
  const raw = mode.value === 'grid'
    ? String(it.description_short || '')
    : String(it.description_short || it.description || '')
  const clean = raw.replace(/<[^>]*>/g, '').trim()
  return clean.length > 260 ? clean.slice(0, 260) + '…' : clean
}

// Detail cover grid: cover size sets the COLUMN COUNT (not the layout width).
// One step smaller than the libraries (XXL=5 …) so the About panel gets more room.
const detailColMap: Record<string, number> = { xxl: 5, xl: 6, l: 7, m: 8, s: 9, xs: 10 }
const detailCols = computed(() => detailColMap[currentCoverSize.value] ?? 5)

function goBack() {
  if (mode.value === 'detail') router.push({ name: 'collections-lib', params: { lib: container.value } })
  else router.push('/')
}

function openItem(it: any) {
  if (mode.value === 'grid') { router.push({ name: 'collection-detail', params: { lib: container.value, slug: it.slug } }); return }
  openMember(it)
}
// Members are ALWAYS local library games (GOG catalog games live on GOG's servers
// and can't be collected), so a member opens in its local library by LibraryGame
// id - never the GOG catalog, even when it was originally downloaded from GOG.
function openMember(g: any) {
  router.push({ name: 'games-detail', params: { id: g.id } })
}

async function loadGrid() {
  loading.value = true
  missing.value = false
  // The router's visibility guard catches /lib/<unknown> and sends it to the
  // games library; it does not watch /collections/, which is why a typo here
  // used to be drawn as a heading above an empty shelf. Give the same answer as
  // the neighbouring route rather than inventing a second way of saying no.
  // Fail open while the registry is silent: an empty shelf is a better guess
  // than telling someone their own library is gone.
  if (!libs.loaded) await libs.fetch()
  if (libs.libraries.length > 0 && !libs.has(container.value)) {
    loading.value = false
    router.replace({ name: 'games-library' })
    return
  }
  try {
    const { data } = await client.get('/collections', { params: { library: container.value } })
    collections.value = Array.isArray(data) ? data : []
  } catch { collections.value = [] } finally { loading.value = false }
}

async function loadDetail() {
  loading.value = true
  missing.value = false
  detail.value = null
  try {
    const { data } = await client.get('/collections/' + route.params.slug)
    detail.value = data
  } catch (e: any) {
    detail.value = null
    // Only a 404 means the slug names nothing. A dropped connection or a 500 is
    // not the reader's typo and must not be reported as one.
    missing.value = e?.response?.status === 404
  } finally { loading.value = false }
}

function reload() {
  if (mode.value === 'detail') loadDetail()
  else loadGrid()
}

// ── Admin edit panel ──────────────────────────────────────────────────────────
const showEdit = ref(false)
// Silent refresh that does NOT null `detail` first (loadDetail does), so the
// open editor stays mounted when it emits an update (e.g. after a cover upload).
async function refreshDetail() {
  try {
    const { data } = await client.get('/collections/' + route.params.slug)
    detail.value = data
  } catch { /* keep current */ }
}
function onCollectionUpdated() {
  refreshDetail()           // refresh this page (without unmounting the editor)
  collectionsStore.fetch()  // refresh the app-wide list (nav / chips / grid)
  libs.fetch()              // index library label / visibility may have changed
}
function onCollectionDeleted() {
  showEdit.value = false
  collectionsStore.fetch()
  libs.fetch()
  router.push({ name: 'collections-lib', params: { lib: container.value } })
}

// ── Quick create (admin) ──────────────────────────────────────────────────────
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)
const createError = ref('')
const createInput = ref<HTMLInputElement>()
function openCreate() {
  newName.value = ''
  createError.value = ''
  showCreate.value = true
  nextTick(() => createInput.value?.focus())
}
async function createCollection() {
  const name = newName.value.trim()
  if (!name || creating.value) return
  creating.value = true; createError.value = ''
  try {
    const { data } = await client.post('/collections', { name, library: container.value })
    showCreate.value = false
    await Promise.all([collectionsStore.fetch(), libs.fetch()])
    router.push({ name: 'collection-detail', params: { lib: container.value, slug: data.slug } })
  } catch (err: any) {
    createError.value = err?.response?.data?.detail || 'Failed'
  } finally {
    creating.value = false
  }
}

onMounted(() => { if (!libs.loaded) libs.fetch(); reload() })
watch(() => route.fullPath, () => { if (route.name === 'collections-lib' || route.name === 'collection-detail') reload() })
</script>

<style scoped>
.library-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 20px 28px; gap: var(--space-4, 16px); }

/* ── Title bar (mirrors GamesLibrary) ─────────────────────────────────────── */
.title-bar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-3, 12px); flex-shrink: 0; padding: 14px 20px;
  position: relative; z-index: 10;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid var(--glass-border); border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
}
.title-left { display: flex; align-items: center; gap: var(--space-3, 12px); }
.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 10px; border-radius: var(--radius-sm); font-family: inherit;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: 12px; font-weight: 600; cursor: pointer;
  transition: all var(--transition);
}
.lib-back-btn:hover { border-color: var(--pl); color: var(--pl-light); }
.title-ico-svg { flex-shrink: 0; }
.title-coll-cover {
  width: 40px; height: 54px; flex-shrink: 0; border-radius: 6px; overflow: hidden;
  border: 1px solid var(--glass-border); box-shadow: 0 4px 14px rgba(0,0,0,.45);
}
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }
.title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }

.coll-edit-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm); font-family: inherit;
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 45%, transparent);
  color: var(--pl-light); font-size: 12px; font-weight: 700; cursor: pointer;
  transition: all var(--transition);
}
.coll-edit-btn:hover { background: color-mix(in srgb, var(--pl) 28%, transparent); border-color: var(--pl); color: #fff; }

/* ── Quick create modal ───────────────────────────────────────────────────── */
.cc-create-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.cc-create-modal {
  width: 90vw; max-width: 420px;
  background: var(--glass-bg, rgba(15,10,30,.9)); border: 1px solid var(--glass-border);
  border-radius: 16px; padding: 22px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent), 0 24px 60px rgba(0,0,0,.6);
  display: flex; flex-direction: column; gap: 14px;
}
.cc-create-title { font-size: 16px; font-weight: 700; color: var(--text); }
.cc-create-input {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 14px; font-family: inherit;
  padding: 11px 14px; outline: none; transition: border-color .15s;
}
.cc-create-input:focus { border-color: var(--pl); }
.cc-create-err { font-size: 12px; color: #f87171; margin-top: -6px; }
.cc-create-actions { display: flex; justify-content: flex-end; gap: 10px; }
.cc-create-cancel {
  padding: 9px 18px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all .15s;
}
.cc-create-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cc-create-ok {
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); font-size: 13px; font-weight: 700; font-family: inherit; cursor: pointer; transition: all .15s;
}
.cc-create-ok:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.cc-create-ok:disabled { opacity: .45; cursor: not-allowed; }

.sort-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px;
  font-weight: 600; padding: 6px 10px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.sort-select:hover { border-color: var(--pl); }
.sort-select option { background: var(--bg2); }

.size-group { display: flex; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.size-btn {
  padding: 5px 9px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); font-size: 11px; font-weight: 700; cursor: pointer;
  transition: all var(--transition); font-family: inherit;
}
.size-btn + .size-btn { border-left: 1px solid var(--glass-border); }
.size-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.size-btn.active { background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light); }

.view-toggle { display: flex; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.view-toggle button {
  padding: 6px 10px; background: rgba(255,255,255,.06); border: none; color: var(--muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all var(--transition);
}
.view-toggle button:hover { background: rgba(255,255,255,.1); color: var(--text); }
.view-toggle button.active { background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light); }
.view-toggle button + button { border-left: 1px solid var(--glass-border); }

.state-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--muted); font-size: 14px; }
.spin { animation: spin .8s linear infinite; }

/* ── Main + grid (mirrors GamesLibrary) ───────────────────────────────────── */
.library-main { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.grid-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; padding-right: 8px; min-width: 0; }

.cover-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--cover-min,175px), 1fr)); gap: var(--space-4, 16px); padding-bottom: 20px; align-items: start; }
/* Detail view sets a FIXED column count inline (repeat(N, 1fr) with a literal N -
   a CSS var in repeat() is invalid and breaks the grid). */
.cover-wrap { cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.cover-img-wrap {
  position: relative; border-radius: var(--radius-sm); overflow: hidden;
  aspect-ratio: 3/4; background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transition: transform .25s cubic-bezier(.23,1,.32,1), box-shadow .2s ease, border-color .2s ease;
}
/* Collection tiles are square so the fanned covers fit without clipping. */
.cover-img-wrap--coll { aspect-ratio: 1 / 1; }
.cover-wrap:hover .cover-img-wrap { transform: translateY(-4px); box-shadow: 0 14px 40px rgba(0,0,0,.6); border-color: color-mix(in srgb, var(--pl) 50%, transparent); }
.cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.badge {
  position: absolute; top: 6px; right: 6px; z-index: 4;
  padding: 2px 7px; border-radius: var(--radius-xs, 4px); font-size: 10px; font-weight: 800;
}
.badge--count { background: color-mix(in srgb, var(--pl) 80%, #000); color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.5); }
.cover-overlay {
  position: absolute; inset: 0; z-index: 5;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.2) 50%, transparent 100%);
  display: flex; flex-direction: column; justify-content: flex-end; padding: 10px; opacity: 0; transition: opacity .18s;
}
.cover-wrap:hover .cover-overlay { opacity: 1; }
.overlay-title { font-size: 12px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cover-title { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cover-scores { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cover-sub { font-size: 11px; color: var(--muted); }
.cover-score { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); }

/* ── Alpha sidebar ────────────────────────────────────────────────────────── */
.alpha-nav { width: 22px; flex-shrink: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; padding: 6px 0; user-select: none; }
.alpha-btn {
  width: 20px; height: 18px; display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; color: rgba(255,255,255,.18);
  background: none; border: none; border-radius: 4px; cursor: pointer; transition: all .12s; font-family: inherit; padding: 0; line-height: 1;
}
.alpha-btn.available { color: var(--muted); }
.alpha-btn.available:hover { color: var(--text); background: rgba(255,255,255,.06); }
.alpha-btn.active { color: var(--pl-light); background: color-mix(in srgb, var(--pl) 18%, transparent); }

/* ── List view (mirrors the games library) ────────────────────────────────── */
.list-view { display: flex; flex-direction: column; gap: var(--space-2, 8px); padding-bottom: 20px; }
.list-row {
  display: flex; align-items: stretch; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  cursor: pointer; transition: all var(--transition); overflow: hidden;
  /* min- (not fixed) height - also styles the member GameListRow root in the
     detail list view, where a tall quick-facts column must grow the row. */
  min-height: 240px;
}
.list-row:hover { background: var(--glass-highlight, rgba(255,255,255,.05)); border-color: color-mix(in srgb, var(--pl) 30%, transparent); }
.list-cover-wrap { flex-shrink: 0; width: 200px; padding: 10px; box-sizing: border-box; display: flex; align-items: center; }
.list-cover-wrap .cover-img-wrap { width: 100%; height: 100%; }
.list-cover-wrap .cover-img-wrap--coll { height: 180px; aspect-ratio: auto; }
.list-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.list-cover-fallback { width: 100%; height: 100%; background: var(--bg3, rgba(255,255,255,.04)); }

.list-info {
  flex-shrink: 0; width: 190px; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: center;
  text-align: center; align-items: center; gap: var(--space-1, 4px);
  padding: 10px 16px; border-left: 1px solid var(--glass-border);
}
.list-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); overflow: hidden; }
.list-title > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.list-coll-logo { max-height: 40px; max-width: 170px; width: auto; object-fit: contain; filter: drop-shadow(0 1px 4px rgba(0,0,0,.5)); }
.list-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 6px; }
.meta-sep::before { content: '·'; }

.list-hero { flex: 1; min-width: 0; overflow: hidden; position: relative; border-left: 1px solid var(--glass-border); }
.list-hero-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; filter: brightness(.30); }
/* Hero motion - mirrors the Games/GOG list view (theme-driven). */
.list-hero-img--kenburns { animation: c-list-kb calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.list-hero-img--drift { animation: c-list-drift calc(30s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.list-hero-img--pulse { animation: c-list-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
@keyframes c-list-kb { 0% { transform: scale(1.05) translateX(0); } 50% { transform: scale(1.12) translateX(-3%); } 100% { transform: scale(1.05) translateX(0); } }
@keyframes c-list-drift { 0% { transform: translateX(0) scale(1.04); } 50% { transform: translateX(-4%) scale(1.04); } 100% { transform: translateX(0) scale(1.04); } }
@keyframes c-list-pulse { 0%,100% { transform: scale(1.02); } 50% { transform: scale(1.08); } }
[data-animations="false"] .list-hero-img--kenburns,
[data-animations="false"] .list-hero-img--drift,
[data-animations="false"] .list-hero-img--pulse { animation: none; }
.list-hero-overlay { position: absolute; inset: 0; background: linear-gradient(to right, rgba(0,0,0,.5) 0%, rgba(0,0,0,.2) 50%, rgba(0,0,0,.5) 100%); }
.list-hero-desc { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 16px 24px; z-index: 2; }
.list-hero-desc-text {
  margin: 0; font-size: var(--fs-sm, 12px); line-height: 1.7; color: rgba(255,255,255,.82);
  text-align: center; display: -webkit-box; -webkit-line-clamp: 7; -webkit-box-orient: vertical; overflow: hidden;
  text-shadow: 0 1px 4px rgba(0,0,0,.6);
}

.genre-chip { padding: 1px 7px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); background: color-mix(in srgb, var(--pl) 14%, transparent); color: var(--pl-light, #a78bfa); }
/* Right block - the shared Details table. Width 350 (= old quickfacts 230 +
   rating 120) gives the value column enough room that aggregated studio names
   wrap cleanly instead of being cut mid-word. */
.list-details {
  box-sizing: border-box; width: 350px; flex-shrink: 0;
  border-left: 1px solid var(--glass-border); padding: 12px 14px;
  display: flex; align-items: center; justify-content: center;
}
.src-gog { color: #a78bfa !important; }
.src-custom { color: #2dd4bf !important; }

</style>
