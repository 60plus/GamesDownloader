<template>
  <!-- Classic layout: center panel shows "select a game" - games are in the sidebar -->
  <div v-if="isClassic" class="classic-placeholder">
    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.12">
      <rect x="2" y="6" width="20" height="12" rx="2"/>
      <circle cx="7.5" cy="12" r="1.5"/><circle cx="16.5" cy="12" r="1.5"/>
    </svg>
    <p>{{ t('library.select_game') }}</p>
  </div>

  <div v-else class="library-view">

    <!-- ── Sync dialog ────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showSyncDialog" class="sync-dialog-overlay" @click.self="showSyncDialog = false">
        <div class="sync-dialog">
          <div class="sync-dialog-header">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('library.sync_gog_title') }}
          </div>
          <div class="sync-dialog-body">
            <label class="sync-opt-row">
              <div class="sync-opt-check-wrap">
                <input type="checkbox" v-model="syncAutoScrape" class="sync-check" />
                <div class="sync-opt-checkmark" :class="{ checked: syncAutoScrape }">
                  <svg v-if="syncAutoScrape" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
              </div>
              <div>
                <div class="sync-opt-title">{{ t('library.sync_auto_meta') }}</div>
                <div class="sync-opt-desc">{{ t('library.sync_auto_meta_desc') }}</div>
              </div>
            </label>
            <label class="sync-opt-row" :class="{ 'sync-opt-row--disabled': !syncAutoScrape }" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--glass-border);">
              <div class="sync-opt-check-wrap">
                <input type="checkbox" v-model="syncForceRescrape" class="sync-check" :disabled="!syncAutoScrape" />
                <div class="sync-opt-checkmark" :class="{ checked: syncForceRescrape && syncAutoScrape, disabled: !syncAutoScrape }">
                  <svg v-if="syncForceRescrape && syncAutoScrape" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
              </div>
              <div>
                <div class="sync-opt-title">{{ t('library.sync_overwrite') }}</div>
                <div class="sync-opt-desc">{{ t('library.sync_overwrite_desc') }}</div>
              </div>
            </label>
          </div>
          <div class="sync-dialog-footer">
            <button class="sync-dlg-cancel" @click="showSyncDialog = false">{{ t('common.cancel') }}</button>
            <button class="sync-dlg-ok" @click="confirmSync">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              {{ t('library.start_sync') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Clear All Metadata dialog ─────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showClearAllDialog" class="gd-confirm-overlay" @click.self="showClearAllDialog = false">
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
          <div class="gd-confirm-body">
            {{ t('library.clear_confirm_body') }}
          </div>
          <div class="gd-confirm-actions">
            <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="showClearAllDialog = false">{{ t('common.cancel') }}</button>
            <button class="gd-confirm-btn gd-confirm-btn--danger" :disabled="clearingAll" @click="clearAllMetadata">
              {{ clearingAll ? t('library.clearing') : t('library.clear_all') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Metadata Edit Panel ────────────────────────────────────────────── -->
    <Teleport to="body">
      <LibraryMetadataPanel
        v-if="metadataGame"
        :game="(metadataGame as any)"
        api-prefix="/gog/library/games"
        @close="metadataGame = null"
        @saved="onMetadataSaved"
      />
    </Teleport>

    <!-- ── Title bar ──────────────────────────────────────────────────────── -->
    <div class="title-bar">
      <div class="title-left">
        <button class="lib-back-btn" @click="router.push('/')" :title="t('library.back_to_libraries')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('library.libraries') }}
        </button>
        <img src="/icons/gog.ico" class="title-ico" alt="GOG" />
        <div>
          <h1 class="title-text">{{ t('nav.gog_library') }}</h1>
          <p class="title-sub">{{ displayedGames.length }} {{ t('library.games') }}</p>
        </div>
      </div>

      <div class="title-right">
        <!-- Sync -->
        <div class="sync-wrap">
          <button class="sync-btn" :class="{ 'sync-btn--running': syncing }" @click="openSyncDialog" :disabled="syncing" :title="t('library.sync_gog_title')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ 'spin': syncing }">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ syncing ? t('library.syncing') : t('library.sync') }}
          </button>
          <span v-if="syncMsg && !syncing" class="sync-msg">{{ syncMsg }}</span>
        </div>

        <!-- Clear All Metadata -->
        <button
          class="clear-meta-btn"
          :disabled="clearingAll || syncing"
          :title="t('library.clear_all_metadata')"
          @click="showClearAllDialog = true"
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
          <option value="purchased">{{ t('library.recent') }}</option>
        </select>

        <!-- Filter: owned -->
        <button class="filter-btn" :class="{ active: filterOwned }" @click="filterOwned = !filterOwned" :title="t('library.show_owned')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {{ t('library.owned') }}
        </button>

        <!-- Cover size selector (cover mode only) -->
        <div v-if="viewMode === 'cover'" class="size-group" :title="t('library.cover_size')">
          <button
            v-for="sz in coverSizes"
            :key="sz.id"
            class="size-btn"
            :class="{ active: currentCoverSize === sz.id }"
            @click="setCoverSize(sz.id)"
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

    <!-- ── Empty state ─────────────────────────────────────────────────────── -->
    <div v-if="!displayedGames.length" class="state-empty">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
        <rect x="2" y="6" width="20" height="12" rx="2"/>
        <circle cx="7.5" cy="12" r="1.5"/>
        <circle cx="16.5" cy="12" r="1.5"/>
      </svg>
      <p>{{ t('library.no_games') }}</p>
    </div>

    <!-- ── MAIN AREA (grid + alpha sidebar) ───────────────────────────────── -->
    <div v-else class="library-main">

      <!-- Scrollable grid area -->
      <div class="grid-scroll" ref="gridScrollEl">

        <!-- ── COVER GRID ──────────────────────────────────────────────────── -->
        <div
          v-if="viewMode === 'cover'"
          class="cover-grid"
          :style="{ '--cover-min': coverSizeMap[currentCoverSize] + 'px' }"
        >
          <div
            v-for="(game, idx) in displayedGames"
            :key="game.id"
            class="cover-wrap"
            :data-alpha-idx="idx"
            @click="openGame(game)"
            @mousemove="onCardMove($event)"
            @mouseleave="onCardLeave($event)"
            @mouseenter="onCardEnter($event)"
          >
            <div class="cover-img-wrap">
              <img
                v-if="game.cover_url || game.cover_path"
                :src="coverSrc(game)"
                :alt="game.title"
                class="cover-img"
                loading="lazy"
              />
              <div v-else class="cover-fallback">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.25">
                  <rect x="2" y="6" width="20" height="12" rx="2"/>
                </svg>
              </div>

              <!-- Sheen overlay (specular) -->
              <div class="cover-sheen" />

              <!-- Status badge -->
              <div v-if="game.download_status === 'completed'" class="badge badge--owned">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                OWNED
              </div>
              <div v-else-if="game.download_status === 'downloading'" class="badge badge--dl">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v10m0 0l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.561 21H19.44a2 2 0 0 0 1.94-1.515L22 17"/></svg>
              </div>

              <!-- Hover overlay -->
              <div class="cover-overlay">
                <div class="overlay-title">{{ game.title }}</div>
              </div>
            </div>

            <div class="cover-title">{{ game.title }}</div>
            <div v-if="game.owner_username" class="cover-owner" :title="'Owner: ' + game.owner_username">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              {{ game.owner_username }}
            </div>
            <div class="cover-scores">
              <!-- Star = the blended score; GOG's own mark keeps its icon and
                   moves in with the other per-source badges below. -->
              <div v-if="game.rating_agg" class="cover-score" title="Rating">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color:#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                {{ ratingVal(game.rating_agg).toFixed(1) }}
              </div>
              <div v-if="game.rating" class="cover-score cover-score--gog" title="GOG Rating">
                <img src="/icons/gog.ico" width="24" height="24" alt="GOG" class="score-ico" />
                {{ ratingVal(game.rating).toFixed(1) }}
              </div>
              <div v-if="game.meta_ratings?.rawg" class="cover-score cover-score--ext" title="RAWG Rating">
                <img src="/icons/RAWG.ico" width="24" height="24" alt="RAWG" class="score-ico" />
                {{ (game.meta_ratings.rawg).toFixed(1) }}
              </div>
              <div v-if="game.meta_ratings?.igdb" class="cover-score cover-score--ext" title="IGDB Rating">
                <img src="/icons/igdb.ico" width="24" height="24" alt="IGDB" class="score-ico" />
                {{ Math.round(game.meta_ratings.igdb) }}
              </div>
              <div v-if="game.meta_ratings?.steam" class="cover-score cover-score--ext" title="Metacritic">
                <img src="/icons/metacritic.svg" width="24" height="24" alt="Metacritic" class="score-ico" />
                {{ Math.round(game.meta_ratings.steam * 10) }}
              </div>
            </div>
          </div>
        </div>

        <!-- ── LIST VIEW ───────────────────────────────────────────────────── -->
        <div v-else class="list-view">
          <GameListRow
            v-for="(game, idx) in gogRows"
            :key="game.id"
            :game="game"
            :idx="idx"
            is-gog
            @open="openGame"
          />
        </div>

      </div><!-- /grid-scroll -->

      <!-- ── Alphabet sidebar ──────────────────────────────────────────── -->
      <nav class="alpha-nav">
        <button
          v-for="letter in alphaLetters"
          :key="letter"
          class="alpha-btn"
          :class="{ available: availableLetters.has(letter), active: activeLetter === letter }"
          @click="scrollToLetter(letter)"
        >{{ letter }}</button>
      </nav>

    </div><!-- /library-main -->

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { storeToRefs } from 'pinia'
import client from '@/services/api/client'
import libraryActions from '@/lib/libraryActions'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import GameListRow from '@/components/games/GameListRow.vue'
import { useI18n } from '@/i18n'
import { ratingVal } from '@/utils/rating'

const { t } = useI18n()

interface Game {
  id: number
  gog_id: number
  title: string
  cover_url?: string
  cover_path?: string
  logo_url?: string
  logo_path?: string
  background_url?: string
  background_path?: string
  download_status?: string
  rating?: number
  rating_agg?: number   // blended 0-5 score - the one shown as the star
  meta_ratings?: { rawg?: number; igdb?: number; steam?: number }
  release_date?: string
  developer?: string
  publisher?: string
  description?: string
  description_short?: string
  genres?: string[]
  tags?: string[]
  os_windows?: boolean
  os_mac?: boolean
  os_linux?: boolean
  languages?: Record<string, string>
  installers?: Record<string, { language: string; name: string; total_size: number }[]>
  owner_user_id?: number | null
  owner_username?: string | null
}

const router     = useRouter()
const route      = useRoute()
const themeStore = useThemeStore()
const { cardTilt, cardShine, cardZoom, cardGlow, cardLift, coverSize: storedCoverSize } = storeToRefs(themeStore)
const isClassic  = computed(() => themeStore.currentLayout === 'classic')

const viewMode    = ref<'cover' | 'list'>(
  (localStorage.getItem('gog_view_mode') as 'cover' | 'list') || 'cover'
)
watch(viewMode, (v) => localStorage.setItem('gog_view_mode', v))
const sortBy      = ref(localStorage.getItem('gog_sort_by') || 'title')
watch(sortBy, v => localStorage.setItem('gog_sort_by', v))
const filterOwned = ref(false)
const games       = ref<Game[]>([])
const loading     = ref(false)
const syncing     = ref(false)
const syncMsg     = ref('')
const gridScrollEl = ref<HTMLElement | null>(null)
const activeLetter = ref('')

// ── Cover size ─────────────────────────────────────────────────────────────
const coverSizes = [
  { id: 'xs',  label: 'XS'  },
  { id: 's',   label: 'S'   },
  { id: 'm',   label: 'M'   },
  { id: 'l',   label: 'L'   },
  { id: 'xl',  label: 'XL'  },
  { id: 'xxl', label: 'XXL' },
]
const coverSizeMap: Record<string, number> = { xs: 115, s: 145, m: 175, l: 215, xl: 265, xxl: 310 }
const currentCoverSize = ref(localStorage.getItem('gog-lib-card-size') || 'm')
watch(currentCoverSize, v => localStorage.setItem('gog-lib-card-size', v))
function setCoverSize(id: string) { currentCoverSize.value = id }

// ── Search ─────────────────────────────────────────────────────────────────
const searchQuery = ref('')

// Sync searchQuery ↔ route.query.q (shared with navbar search)
watch(() => route.query.q, (q) => {
  const val = (Array.isArray(q) ? q[0] : q) || ''
  if (searchQuery.value !== val) searchQuery.value = val
}, { immediate: true })
watch(searchQuery, (q) => {
  const cur = (Array.isArray(route.query.q) ? route.query.q[0] : route.query.q) || ''
  if (q !== cur) router.replace({ query: { ...route.query, q: q || undefined } })
})

// ── Sync dialog ────────────────────────────────────────────────────────────
const showSyncDialog    = ref(false)
const syncAutoScrape    = ref(true)
const syncForceRescrape = ref(false)

// ── Metadata panel ─────────────────────────────────────────────────────────
const metadataGame = ref<Game | null>(null)

// ── Clear all metadata ──────────────────────────────────────────────────────
const showClearAllDialog = ref(false)
const clearingAll        = ref(false)

// ── Alphabet ───────────────────────────────────────────────────────────────
const alphaLetters = ['#', 'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']

const availableLetters = computed(() => {
  const set = new Set<string>()
  for (const g of displayedGames.value) {
    const t = g.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    set.add(/[A-Z]/.test(t) ? t : '#')
  }
  return set
})

function scrollToLetter(letter: string) {
  const games = displayedGames.value
  const idx = games.findIndex(g => {
    const first = g.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    return letter === '#' ? !/[A-Z]/.test(first) : first === letter
  })
  if (idx === -1) return
  activeLetter.value = letter
  const gridEl = gridScrollEl.value
  if (!gridEl) return
  // Cover grid uses .cover-wrap; list view uses .list-row
  const selector = viewMode.value === 'list' ? '.list-row' : '.cover-wrap'
  const cards = gridEl.querySelectorAll(selector)
  const card = cards[idx] as HTMLElement
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Card effects ───────────────────────────────────────────────────────────
function onCardEnter(e: MouseEvent) {
  const wrap = e.currentTarget as HTMLElement
  if (cardGlow.value) {
    wrap.querySelector<HTMLElement>('.cover-img-wrap')?.classList.add('glow-active')
  }
}

function onCardMove(e: MouseEvent) {
  const wrap = e.currentTarget as HTMLElement
  const imgWrap = wrap.querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return

  const rect  = imgWrap.getBoundingClientRect()
  const cx    = rect.width  / 2
  const cy    = rect.height / 2
  const dx    = e.clientX - rect.left - cx
  const dy    = e.clientY - rect.top  - cy

  let transform = ''

  if (cardTilt.value) {
    const ry =  (dx / cx) * 8
    const rx = -(dy / cy) * 5
    const scale = cardZoom.value ? 1.04 : (cardLift.value ? 1.01 : 1)
    transform = `perspective(600px) rotateX(${rx}deg) rotateY(${ry}deg) scale3d(${scale},${scale},${scale})`
  } else if (cardLift.value) {
    transform = `translateY(calc(-4px * var(--hover-lift, 1)))`
  } else if (cardZoom.value) {
    transform = `scale(1.04)`
  }

  if (transform) imgWrap.style.transform = transform

  if (cardShine.value) {
    const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
    if (sheen) {
      const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
      const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
      sheen.style.opacity = '1'
      sheen.style.background = `radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%)`
    }
  }
}

function onCardLeave(e: MouseEvent) {
  const wrap = e.currentTarget as HTMLElement
  const imgWrap = wrap.querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return
  imgWrap.style.transform = ''
  imgWrap.classList.remove('glow-active')
  const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
  if (sheen) sheen.style.opacity = '0'
}

// ── Helpers ────────────────────────────────────────────────────────────────
// Mirror of backend _fix_gog_url - strips deprecated GOG CDN formatter suffixes
// that cause HTTP 400: _product_card, _product_tile_256, _aw, _logo2x, _logo
const _GOG_SUFFIX_RE = /_(product_card|product_tile_\d+|aw|logo2x|logo)(v2[^.]*)?(?=\.(jpg|png|webp)$)/i

function coverSrc(game: Game): string {
  if (game.cover_path) return game.cover_path
  const url = game.cover_url || ''
  if (!url) return ''
  // Strip deprecated GOG CDN suffixes (e.g. _product_card.jpg → .jpg)
  const fixed = url.replace(_GOG_SUFFIX_RE, '')
  // If still no file extension, append .jpg
  if (!/\.\w{2,5}(\?|$)/.test(fixed)) return fixed + '.jpg'
  return fixed
}

// ── Data loading ───────────────────────────────────────────────────────────
async function loadGames() {
  loading.value = true
  try {
    const { data } = await client.get('/gog/library/games')
    games.value = data
  } catch { /* ignore */ } finally {
    loading.value = false
  }
}

function openSyncDialog() {
  if (syncing.value) return
  showSyncDialog.value = true
}

// ── Sync polling ─────────────────────────────────────────────────────────────
// Extracted so it can be started both from confirmSync() and from onMounted
// (to reconnect to a sync that was running before a page refresh).
function startSyncPoller() {
  const poll = setInterval(async () => {
    try {
      const data = await libraryActions.gogSyncStatus()
      if (data.running) {
        syncMsg.value = data.phase === 'adopt'
          ? 'Adding downloaded games…'
          : data.phase === 'scrape'
            ? 'Fetching metadata…'
            : `Synced ${data.synced} games…`
      } else {
        clearInterval(poll)
        syncing.value = false
        const adopted = data.adopted || 0
        syncMsg.value = data.error
          ? `Error: ${data.error}`
          : adopted > 0
            ? `Done - ${data.synced} games, ${adopted} added to library`
            : `Done - ${data.synced} games`
        await loadGames()
        setTimeout(() => { syncMsg.value = '' }, 4000)
      }
    } catch { clearInterval(poll); syncing.value = false }
  }, 1500)
}

async function confirmSync() {
  showSyncDialog.value = false
  if (syncing.value) return
  syncing.value = true
  syncMsg.value = 'Syncing…'
  try {
    await libraryActions.gogSync({ autoScrape: syncAutoScrape.value, forceRescrape: syncForceRescrape.value })
    startSyncPoller()
  } catch (e: any) {
    syncMsg.value = e?.response?.data?.detail || 'Sync failed'
    syncing.value = false
  }
}

async function clearAllMetadata() {
  clearingAll.value = true
  try {
    await libraryActions.gogClearMetadata()
    await loadGames()
  } catch { /* ignore */ } finally {
    clearingAll.value = false
    showClearAllDialog.value = false
  }
}

function openMetadata(game: Game) { metadataGame.value = game }

function onMetadataSaved(updated: Partial<Game>) {
  if (metadataGame.value) {
    const idx = games.value.findIndex(g => g.id === metadataGame.value!.id)
    if (idx !== -1) Object.assign(games.value[idx], updated)
  }
  metadataGame.value = null
}

onMounted(async () => {
  // Reconnect to a sync that was already running before this page load
  try {
    const { data } = await client.get('/gog/library/sync/status')
    if (data.running) {
      syncing.value = true
      syncMsg.value = data.phase === 'adopt' ? 'Adding downloaded games…'
        : data.phase === 'scrape' ? 'Fetching metadata…'
        : `Synced ${data.synced} games…`
      startSyncPoller()
    }
  } catch { /* ignore - sync status is best-effort */ }
  await loadGames()
})

const displayedGames = computed(() => {
  let list = [...games.value]
  if (filterOwned.value) list = list.filter(g => g.download_status === 'completed')
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(g =>
      g.title.toLowerCase().includes(q) ||
      (g.developer || '').toLowerCase().includes(q) ||
      (g.genres || []).some(genre => genre.toLowerCase().includes(q))
    )
  }
  switch (sortBy.value) {
    case 'title':       list.sort((a, b) => a.title.localeCompare(b.title)); break
    case 'title_desc':  list.sort((a, b) => b.title.localeCompare(a.title)); break
    case 'release':     list.sort((a, b) => (b.release_date || '').localeCompare(a.release_date || '')); break
    case 'release_asc': list.sort((a, b) => (a.release_date || '').localeCompare(b.release_date || '')); break
    case 'rating':      list.sort((a, b) => (b.rating_agg || 0) - (a.rating_agg || 0)); break
    case 'purchased':   list.sort((a, b) => b.id - a.id); break
  }
  return list
})

// The list view uses the shared GameListRow; normalise the GOG cover (strip CDN
// suffixes) into cover_path so the component renders it directly.
const gogRows = computed(() => displayedGames.value.map((g: any) => ({ ...g, cover_path: coverSrc(g) })))

function openGame(game: Game) {
  router.push({ name: 'game-detail', params: { id: game.id } })
}
</script>

<style scoped>
/* ── Clear All Metadata button ────────────────────────────────────────────── */
.clear-meta-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid rgba(239,68,68,.35); background: rgba(239,68,68,.08);
  color: #f87171; font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.clear-meta-btn:not(:disabled):hover { border-color: rgba(239,68,68,.7); background: rgba(239,68,68,.15); color: #fca5a5; }
.clear-meta-btn:disabled { opacity: .45; cursor: not-allowed; }

/* ── Confirm dialog (shared danger pattern) ───────────────────────────────── */
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
.gd-confirm-body strong { color: var(--text); }
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
.gd-confirm-btn--danger:not(:disabled):hover { background: rgba(239,68,68,.3); border-color: rgba(239,68,68,.7); color: #fca5a5; }

.sync-wrap { display: flex; align-items: center; gap: var(--space-2, 8px); }
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
.sync-msg { font-size: var(--fs-sm, 12px); color: var(--muted); }
.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

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
.title-ico { width: 60px; height: 60px; object-fit: contain; border-radius: var(--radius-sm, 8px); filter: drop-shadow(0 0 8px var(--pglow2)); }
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }
.title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }

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

/* Cover size selector */
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

/* ── Empty state ──────────────────────────────────────────────────────────── */
.state-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-3, 12px); color: var(--muted); font-size: var(--fs-md, 14px);
}

/* ── Main area (grid + alpha nav) ─────────────────────────────────────────── */
.library-main {
  flex: 1;
  display: flex;
  gap: 0;
  overflow: hidden;
  min-height: 0;
}

.grid-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  padding-right: 8px;
  min-width: 0;
}

/* ── Cover grid ───────────────────────────────────────────────────────────── */
.cover-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cover-min, 175px), 1fr));
  gap: var(--space-4, 16px);
  padding-bottom: 20px;
}

.cover-wrap {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cover-img-wrap {
  position: relative;
  border-radius: var(--radius-sm);
  overflow: hidden;
  aspect-ratio: 3/4;
  background: var(--bg2);
  border: 1px solid var(--glass-border);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.2s ease, border-color 0.2s ease;
  transform-style: preserve-3d;
}
/* Glow ring */
.cover-img-wrap::after {
  content: '';
  position: absolute; inset: -1px;
  border-radius: inherit;
  border: 1px solid var(--pl);
  box-shadow: 0 0 24px var(--pglow2), inset 0 0 16px rgba(0,0,0,.1);
  opacity: 0;
  transition: opacity var(--transition);
  pointer-events: none; z-index: 2;
}
.cover-img-wrap.glow-active::after { opacity: var(--card-glow, 1); }

.cover-sheen {
  position: absolute; inset: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s;
  z-index: 3;
}

.cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-fallback {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
}

.badge {
  position: absolute; top: 6px; right: 6px; z-index: 4;
  display: flex; align-items: center; gap: 3px;
  padding: 2px 6px; border-radius: var(--radius-xs, 4px);
  font-size: 9px; font-weight: 700; letter-spacing: .5px;
}
.badge--owned { background: rgba(74,222,128,.15); color: #4ade80; border: 1px solid rgba(74,222,128,.3); }
.badge--dl    { background: rgba(124,58,237,.15); color: var(--pl-light); border: 1px solid var(--glass-border); }

.cover-overlay {
  position: absolute; inset: 0; z-index: 5;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.2) 50%, transparent 100%);
  display: flex; flex-direction: column; justify-content: flex-end;
  padding: 10px; opacity: 0; transition: opacity .18s;
}
.cover-wrap:hover .cover-overlay { opacity: 1; }
.overlay-title {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-bottom: 6px;
}
.overlay-actions { display: flex; gap: 5px; }
.ov-btn {
  width: 28px; height: 28px; border-radius: 6px;
  background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.2);
  color: #fff; display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s;
}
.ov-btn:hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); }

.cover-title {
  font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cover-owner {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  font-size: var(--fs-xs, 10px); font-weight: 600; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
/* Multi-source scores below cover card */
.cover-scores { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cover-score {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  font-size: 11px; color: var(--muted);
}
.score-ico { image-rendering: pixelated; opacity: .85; flex-shrink: 0; }

/* ── Alphabet sidebar ─────────────────────────────────────────────────────── */
.alpha-nav {
  width: 22px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  padding: 6px 0;
  user-select: none;
}
.alpha-btn {
  width: 20px;
  height: 18px;
  display: flex; align-items: center; justify-content: center;
  font-size: var(--fs-xs, 10px); font-weight: 700;
  color: rgba(255,255,255,.18);
  background: none; border: none;
  border-radius: var(--radius-xs, 4px);
  cursor: pointer;
  transition: all .12s;
  font-family: inherit;
  padding: 0;
  line-height: 1;
}
.alpha-btn.available {
  color: var(--muted);
}
.alpha-btn.available:hover {
  color: var(--text);
  background: rgba(255,255,255,.06);
}
.alpha-btn.active {
  color: var(--pl-light);
  background: var(--pl-dim);
}

/* ── Search bar ───────────────────────────────────────────────────────────── */
.search-wrap {
  position: relative; display: flex; align-items: center;
}
.search-icon {
  position: absolute; left: 9px; pointer-events: none;
  color: var(--muted); flex-shrink: 0;
}
.search-input {
  width: 200px; padding: 6px 30px 6px 30px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px;
  font-family: inherit; outline: none; transition: all var(--transition);
}
.search-input::placeholder { color: var(--muted); }
.search-input:focus { border-color: var(--pl); background: rgba(255,255,255,.09); width: 260px; }
.search-clear {
  position: absolute; right: 8px;
  background: none; border: none; color: var(--muted);
  cursor: pointer; padding: 2px; display: flex; align-items: center;
  transition: color var(--transition);
}
.search-clear:hover { color: var(--text); }

/* ── List view ────────────────────────────────────────────────────────────── */
.list-view { display: flex; flex-direction: column; gap: var(--space-2, 8px); padding-bottom: 20px; }
/* ── Sync dialog ──────────────────────────────────────────────────────────── */
.sync-dialog-overlay {
  position: fixed; inset: 0; z-index: 7000;
  background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  animation: sd-fade .15s ease;
}
@keyframes sd-fade { from { opacity: 0; } to { opacity: 1; } }
.sync-dialog {
  width: 420px; background: var(--bg2);
  border: 1px solid var(--glass-border); border-radius: var(--radius);
  box-shadow: 0 24px 60px rgba(0,0,0,.6); overflow: hidden;
  animation: sd-pop .18s cubic-bezier(.23,1,.32,1);
}
@keyframes sd-pop { from { transform: scale(.95); opacity: 0; } to { transform: none; opacity: 1; } }
.sync-dialog-header {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 18px 20px;
  font-size: 15px; font-weight: 700; color: var(--text);
  border-bottom: 1px solid var(--glass-border);
}
.sync-dialog-body { padding: var(--space-5, 20px); }
.sync-opt-row { display: flex; align-items: flex-start; gap: var(--space-3, 12px); cursor: pointer; }
.sync-opt-check-wrap { position: relative; flex-shrink: 0; margin-top: 2px; }
.sync-opt-check-wrap input[type="checkbox"] { position: absolute; opacity: 0; width: 0; height: 0; }
.sync-opt-checkmark {
  width: 18px; height: 18px; border-radius: 5px;
  border: 2px solid var(--glass-border); background: rgba(255,255,255,.06);
  display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.sync-opt-checkmark.checked { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); }
.sync-opt-title { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); margin-bottom: 4px; }
.sync-opt-desc  { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }
.sync-opt-row--disabled { opacity: .45; }
.sync-opt-checkmark.disabled { opacity: .5; cursor: not-allowed; }
.sync-dialog-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 10px;
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
}
.sync-dlg-cancel {
  padding: 8px 18px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.sync-dlg-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.sync-dlg-ok {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 20px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 12px var(--pglow2);
}
.sync-dlg-ok:hover { background: var(--pl-light); }

/* ── Classic placeholder ─────────────────────────────────────────────────── */
.classic-placeholder {
  flex: 1; height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-3, 12px); color: var(--muted); font-size: 13px;
  font-weight: 600; letter-spacing: .3px;
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .title-bar { padding: 10px 12px; gap: var(--space-2, 8px); }
  .title-ico { width: 36px; height: 36px; }
  .title-text { font-size: 15px; }
  .title-right { gap: 6px; }
  .sort-select { font-size: 11px; padding: 4px 6px; }
  .size-group { display: none; }
  .cover-grid { gap: 10px; --cover-min: 120px; }
}
</style>
