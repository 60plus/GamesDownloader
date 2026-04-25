<template>
  <div class="emu-library">

    <!-- Title bar -->
    <div
      class="emu-title-bar"
      :class="{ 'emu-title-bar--photo': !!headerBgUrl && themeStore.platformPhotoHeader }"
      :style="titleBarStyle"
    >
      <!-- Animated hero background (respects hero settings) -->
      <div
        v-if="headerBgUrl && themeStore.platformPhotoHeader"
        class="emu-title-bg"
        :class="themeStore.heroAnim && themeStore.animations ? `emu-title-bg--${themeStore.heroAnimStyle}` : ''"
        :style="{ backgroundImage: `url(${headerBgUrl})`, '--gd-hero-blur': `${themeStore.heroBlur ?? 14}px` }"
      />
      <!-- Photo dimming overlay -->
      <div v-if="headerBgUrl && themeStore.platformPhotoHeader" class="emu-title-photo-overlay" />

      <div class="emu-title-left" style="position:relative;z-index:1">
        <button class="emu-back-btn" @click="router.push({ name: 'emulation-home' })">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>

        <!-- Platform identity: icon top, name logo below -->
        <div class="emu-platform-identity">
          <img
            v-if="platform"
            :src="`/platforms/icons/${platform.fs_slug}.png`"
            :alt="platform?.name"
            class="emu-platform-icon"
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
          <template v-if="platform">
            <img
              v-if="nameLogo && !logoError"
              :src="nameLogo"
              :alt="platform.name"
              class="emu-platform-name-logo"
              @error="logoError = true"
            />
            <span v-else class="emu-platform-name-text">{{ platform.name }}</span>
          </template>
          <span v-else class="emu-platform-name-text">{{ slugToTitle(platformSlug) }}</span>
          <span class="emu-platform-count">{{ total }} {{ t('emulation.roms_count') }}</span>
        </div>
      </div>

      <!-- Center: photo left + info right (absolutely centered on screen) -->
      <div v-if="themeStore.platformPhotoHeader" class="emu-title-center">
        <!-- Left: console photo -->
        <div class="emu-console-photo-col">
          <img
            v-if="platform?.photo_path"
            :src="platform.photo_path"
            class="emu-console-photo"
            alt=""
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
          <div v-else-if="platform && !platform.photo_path" class="emu-console-placeholder">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".18">
              <rect x="2" y="6" width="20" height="14" rx="3"/>
              <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
              <path d="M6 10h4M8 8v4M14 11h4"/><path d="M8 6V4M16 6V4" stroke-width="1.5"/>
            </svg>
            <span class="emu-console-placeholder-text">{{ t('library.click_platform_info') }}</span>
          </div>
        </div>

        <!-- Right: chips + description -->
        <div class="emu-console-info-col">
          <div v-if="platform?.manufacturer || platform?.release_year_platform || platform?.generation" class="emu-console-meta">
            <span v-if="platform.manufacturer" class="emu-meta-chip">{{ platform.manufacturer }}</span>
            <span v-if="platform.release_year_platform" class="emu-meta-chip">
              {{ platform.release_year_platform }}{{ platform.end_year_platform ? '–' + platform.end_year_platform : '' }}
            </span>
            <span v-if="platform.generation" class="emu-meta-chip">Gen {{ platform.generation }}</span>
          </div>
          <div v-if="platformDescription || platform?.description" class="emu-console-desc-wrap">
            <p class="emu-console-desc">{{ platformDescription || platform?.description }}</p>
            <a
              v-if="platform?.wiki_url"
              :href="platform.wiki_url"
              target="_blank" rel="noopener noreferrer"
              class="emu-wiki-link-inline"
            >
              {{ t('library.wikipedia') }}
            </a>
          </div>
        </div>
      </div>

      <!-- Controls -->
      <div class="emu-title-right" style="position:relative;z-index:1">
        <!-- Request a ROM -->
        <button class="emu-action-btn emu-action-btn--request" @click="requestDialogOpen = true" style="position:relative">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
          {{ t('library.request') }}
          <span v-if="reqBadge > 0" class="emu-req-notify-dot">{{ reqBadge > 99 ? '99+' : reqBadge }}</span>
        </button>

        <!-- Sort -->
        <select v-model="sortBy" class="emu-sort-select" @change="onSortChange">
          <option value="name_asc">{{ t('library.a_to_z') }}</option>
          <option value="name_desc">{{ t('library.z_to_a') }}</option>
          <option value="year_desc">{{ t('library.year_desc') }}</option>
          <option value="year_asc">{{ t('library.year_asc') }}</option>
        </select>

        <!-- Cover size -->
        <div class="emu-size-group">
          <button
            v-for="sz in coverSizes"
            :key="sz.id"
            class="emu-size-btn"
            :class="{ active: currentSize === sz.id }"
            @click="currentSize = sz.id"
          >{{ sz.label }}</button>
        </div>

        <!-- Cover type selector (admin) -->
        <div v-if="isAdmin" class="emu-size-group" :title="t('library.cover_type_title')">
          <button
            v-for="ct in ['box-2D','box-3D']"
            :key="ct"
            class="emu-size-btn"
            :class="{ active: coverTypePreset === ct }"
            @click="setCoverType(ct)"
          >{{ ct === 'box-2D' ? '2D' : '3D' }}</button>
        </div>

        <!-- Admin actions -->
        <button v-if="isAdmin" class="emu-action-btn" @click="triggerScrape" :disabled="scraping">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          {{ scraping ? t('library.scanning') : t('detail.scrape') }}
        </button>
        <button v-if="isAdmin" class="emu-action-btn" @click="triggerScan" :disabled="scanning">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ 'spin': scanning }">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          {{ scanning ? t('library.scanning') : t('library.scan') }}
        </button>
        <button v-if="isAdmin" class="emu-action-btn" @click="fetchPlatformInfo" :disabled="fetchingInfo">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/>
          </svg>
          {{ fetchingInfo ? t('library.fetching') : t('library.platform_info') }}
        </button>
        <button v-if="isAdmin" class="emu-action-btn emu-action-btn--danger" :disabled="clearingAll" @click="onClearPlatformMetadata">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
          {{ clearingAll ? t('library.clearing') : t('library.clear_all') }}
        </button>
      </div>
    </div>

    <!-- Platform description panel (shown when Photo Header is OFF) -->
    <div v-if="(platformDescription || platform?.description) && !themeStore.platformPhotoHeader" class="emu-platform-info">
      <p class="emu-platform-desc">{{ platformDescription || platform?.description }}</p>
      <a v-if="platform?.wiki_url" :href="platform.wiki_url" target="_blank" rel="noopener noreferrer" class="emu-wiki-link">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
        {{ t('library.wikipedia') }}
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="opacity:.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </a>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="emu-loading"><span class="spinner" /></div>

    <!-- Empty -->
    <div v-else-if="!roms.length && !searchQuery" class="emu-empty">
      <p>{{ t('library.no_roms') }}</p>
      <p class="emu-empty-sub">{{ t('library.add_roms_path', { platform: platformSlug }) }}</p>
    </div>
    <div v-else-if="!roms.length && searchQuery" class="emu-empty">
      <p>{{ t('library.no_results', { query: searchQuery }) }}</p>
    </div>

    <!-- ROM grid -->
    <div
      v-else
      class="emu-cover-grid"
      :style="{ '--cover-min': sizeMap[currentSize] + 'px' }"
    >
      <div
        v-for="rom in roms"
        :key="rom.id"
        class="emu-cover-wrap"
        @click="router.push({ name: 'emulation-detail', params: { platform: platformSlug, id: rom.id } })"
        @mouseenter="onCardEnter"
        @mousemove="onCardMove"
        @mouseleave="onCardLeave"
      >
        <div class="emu-cover-img-wrap" :style="{ aspectRatio: rom.cover_type === 'box-3D' ? '16/9' : (rom.cover_aspect || platform?.cover_aspect || '3/4') }">
          <img
            v-if="rom.cover_path"
            :src="rom.cover_path"
            :alt="rom.name"
            class="emu-cover-img"
            loading="lazy"
          />
          <div v-else class="emu-cover-fallback">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <rect x="2" y="6" width="20" height="14" rx="2"/>
              <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
              <path d="M6 10h4M8 8v4M14 11h4"/>
            </svg>
          </div>

          <!-- Badges -->
          <div v-if="rom.regions?.[0] || rom.release_year" class="emu-cover-badges">
            <span v-if="rom.regions?.[0]" class="emu-badge">{{ rom.regions[0].toUpperCase() }}</span>
          </div>

          <!-- Sheen -->
          <div class="emu-cover-sheen" />

          <!-- Hover overlay -->
          <div class="emu-cover-overlay">
            <span class="emu-overlay-title">{{ rom.name }}</span>
            <div v-if="rom.genres?.length" class="emu-overlay-meta">{{ rom.genres[0] }}</div>
          </div>
        </div>

        <div class="emu-cover-title">{{ rom.name }}</div>
        <div v-if="rom.release_year || rom.rating" class="emu-cover-meta">
          <span v-if="rom.release_year" class="emu-cover-year">{{ rom.release_year }}</span>
          <span v-if="rom.rating" class="emu-cover-rating">★ {{ rom.rating.toFixed(1) }}</span>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > limit" class="emu-pagination">
      <button class="emu-page-btn" :disabled="offset === 0" @click="prevPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        {{ t('library.prev') }}
      </button>
      <span class="emu-page-info">{{ offset + 1 }}–{{ Math.min(offset + limit, total) }} of {{ total }}</span>
      <button class="emu-page-btn" :disabled="offset + limit >= total" @click="nextPage">
        {{ t('library.next') }}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    </div>

    <div v-if="actionMsg" class="emu-action-msg">{{ actionMsg }}</div>

  </div>

  <GameRequestDialog
    :visible="requestDialogOpen"
    default-platform="roms"
    @close="requestDialogOpen = false; refreshReqBadge()"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useDialog } from '@/composables/useDialog'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const { gdConfirm } = useDialog()
import { useThemeStore } from '@/stores/theme'
import { getPlatformAssets } from '@/utils/platformMap'
import { usePlatformMetaStore } from '@/stores/platformMeta'
import GameRequestDialog from '@/components/GameRequestDialog.vue'
import { useRequestNotify } from '@/composables/useRequestNotify'

const route      = useRoute()
const router     = useRouter()
const auth       = useAuthStore()
const themeStore = useThemeStore()
const platformMeta = usePlatformMetaStore()

const isAdmin = computed(() => auth.user?.role === 'admin')
const requestDialogOpen = ref(false)
const { totalBadge: reqBadge, refresh: refreshReqBadge } = useRequestNotify()
const platformSlug = computed(() => route.params.platform as string)

interface PlatformInfo {
  id: number; slug: string; fs_slug: string; name: string; rom_count: number; cover_path: string | null
  cover_aspect: string | null
  photo_path: string | null; icon_path: string | null; bezel_path: string | null
  description: string | null; wiki_url: string | null
  manufacturer: string | null
  release_year_platform: number | null; end_year_platform: number | null
  generation: number | null
}
interface Rom {
  id: number; name: string; fs_name_no_ext: string; fs_extension: string
  cover_path: string | null; cover_type: string | null; cover_aspect: string | null
  genres: string[] | null; regions: string[] | null
  release_year: number | null; rating: number | null; is_identified: boolean
}

const platform   = ref<PlatformInfo | null>(null)
const roms       = ref<Rom[]>([])
const loading    = ref(true)
const total     = ref(0)
const limit     = ref(100)
const offset    = ref(0)
const scanning     = ref(false)
const scraping     = ref(false)
const fetchingInfo = ref(false)
const clearingAll  = ref(false)
const actionMsg    = ref('')
const logoError = ref(false)
const sortBy    = ref(localStorage.getItem('emu_lib_sort') || 'name_asc')
watch(sortBy, v => localStorage.setItem('emu_lib_sort', v))

// Cover size
const coverSizes = [
  { id: 'xs', label: 'XS' },
  { id: 's',  label: 'S'  },
  { id: 'm',  label: 'M'  },
  { id: 'l',  label: 'L'  },
  { id: 'xl', label: 'XL' },
]
const sizeMap: Record<string, number> = { xs: 115, s: 145, m: 175, l: 215, xl: 265 }
const lsKey = computed(() => `emu-lib-card-size-${platformSlug.value}`)
const currentSize = ref(localStorage.getItem(lsKey.value) || 'm')
watch(currentSize, v => localStorage.setItem(lsKey.value, v))

// Name logo via platformMap
const nameLogo = computed(() => {
  if (!platform.value?.fs_slug) return ''
  return getPlatformAssets(platform.value.fs_slug).nameLogo ?? ''
})

/** Convert URL slug to readable title: "super-famicom" -> "Super Famicom" */
function slugToTitle(s: string): string {
  return s.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// Search driven by navbar (route.query.q)
const searchQuery = computed(() => {
  const q = route.query.q
  return (Array.isArray(q) ? q[0] : q) || ''
})

let searchTimer: ReturnType<typeof setTimeout> | null = null

// Cover type preset (per platform, admin-settable)
const coverTypePreset = ref('box-2D')

// ── Data fetching ──────────────────────────────────────────────────────────────

async function fetchPlatform() {
  logoError.value = false
  try {
    const { data } = await client.get(`/roms/platforms/${platformSlug.value}`)
    platform.value = data
  } catch {
    // Platform not in DB - go back home
    router.replace({ name: 'emulation-home' })
    return
  }
  // Load scrape preset for cover type indicator
  try {
    const { data } = await client.get(`/settings/roms/scrape-presets/${platform.value?.fs_slug || platformSlug.value}`)
    coverTypePreset.value = data.cover_type || 'box-2D'
  } catch { /* ignore */ }
}

async function setCoverType(ct: string) {
  if (!platform.value) return
  coverTypePreset.value = ct
  try {
    // Read all presets, update this platform's entry, save back
    const { data: all } = await client.get('/settings/roms/scrape-presets')
    const updated = { ...all, [platform.value.fs_slug]: { ...(all[platform.value.fs_slug] || {}), cover_type: ct } }
    await client.post('/settings/roms/scrape-presets', { presets: updated })
    actionMsg.value = `Cover preset set to ${ct} - re-scrape to apply`
    setTimeout(() => { actionMsg.value = '' }, 3500)
  } catch (e: any) {
    actionMsg.value = e?.response?.data?.detail || 'Failed to save preset'
  }
}

async function fetchRoms() {
  loading.value = true
  try {
    const { data } = await client.get('/roms', {
      params: {
        platform_slug: platformSlug.value,
        search:        searchQuery.value || undefined,
        sort:          sortBy.value,
        limit:         limit.value,
        offset:        offset.value,
      },
    })
    roms.value  = data.items
    total.value = data.total
  } catch {
    roms.value  = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ── Watchers ──────────────────────────────────────────────────────────────────

watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { offset.value = 0; fetchRoms() }, 280)
})

watch(platformSlug, async () => {
  offset.value = 0
  await fetchPlatform()
  fetchRoms()
})

function onSortChange() {
  offset.value = 0
  fetchRoms()
}

// ── Pagination ────────────────────────────────────────────────────────────────

function nextPage() {
  offset.value += limit.value
  fetchRoms()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function prevPage() {
  offset.value = Math.max(0, offset.value - limit.value)
  fetchRoms()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── Admin actions ─────────────────────────────────────────────────────────────

async function triggerScan() {
  scanning.value = true; actionMsg.value = ''
  try {
    await client.post('/roms/scan')
    actionMsg.value = 'Scanning ROMs…'
    const poll = setInterval(async () => {
      try {
        const { data } = await client.get('/roms/scan/status')
        if (!data.running) {
          clearInterval(poll)
          await fetchPlatform(); await fetchRoms()
          actionMsg.value = ''
          scanning.value = false
        }
      } catch { /* ignore */ }
    }, 2000)
  } catch (e: any) {
    actionMsg.value = e?.response?.data?.detail || 'Scan failed'
    scanning.value = false
  }
}

async function triggerScrape() {
  scraping.value = true; actionMsg.value = ''
  try {
    const { data } = await client.post(`/roms/platforms/${platformSlug.value}/scrape`)
    actionMsg.value = `Scraping ${data.queued} ROMs in background…`
    setTimeout(() => { actionMsg.value = '' }, 4000)
  } catch (e: any) {
    actionMsg.value = e?.response?.data?.detail || 'Scrape failed'
  } finally {
    scraping.value = false
  }
}

async function fetchPlatformInfo() {
  fetchingInfo.value = true; actionMsg.value = ''
  try {
    await client.post(`/roms/platforms/${platformSlug.value}/scrape-platform`)
    actionMsg.value = 'Fetching platform info in background… reload in a few seconds.'
    setTimeout(async () => { await fetchPlatform(); actionMsg.value = '' }, 5000)
  } catch (e: any) {
    actionMsg.value = e?.response?.data?.detail || 'Fetch failed'
  } finally {
    fetchingInfo.value = false
  }
}

async function onClearPlatformMetadata() {
  if (!await gdConfirm(`Clear all scraped metadata for ${platform.value?.name || 'this platform'}? File info and hashes are preserved.`, { danger: true })) return
  clearingAll.value = true; actionMsg.value = ''
  try {
    const { data } = await client.post(`/roms/platforms/${platformSlug.value}/clear-metadata`)
    actionMsg.value = `Cleared metadata for ${data.cleared} ROM(s).`
    await fetchRoms()
    setTimeout(() => { actionMsg.value = '' }, 4000)
  } catch (e: any) {
    actionMsg.value = e?.response?.data?.detail || 'Clear failed'
  } finally {
    clearingAll.value = false
  }
}

// ── Card hover (tilt / shine) ─────────────────────────────────────────────────

function onCardEnter(e: MouseEvent) {
  if (!themeStore.cardGlow) return
  const wrap = (e.currentTarget as HTMLElement).querySelector<HTMLElement>('.emu-cover-img-wrap')
  wrap?.classList.add('glow-active')
}

function onCardMove(e: MouseEvent) {
  if (!themeStore.cardTilt && !themeStore.cardShine) return
  const el = e.currentTarget as HTMLElement
  const imgWrap = el.querySelector<HTMLElement>('.emu-cover-img-wrap')
  if (!imgWrap) return
  const rect = imgWrap.getBoundingClientRect()
  if (themeStore.cardTilt) {
    const cx = rect.width / 2, cy = rect.height / 2
    const dx = e.clientX - rect.left - cx, dy = e.clientY - rect.top - cy
    const ry = (dx / cx) * 8, rx = -(dy / cy) * 5
    const zoom = themeStore.cardZoom ? 'scale3d(1.03,1.03,1.03)' : ''
    imgWrap.style.transform = `perspective(600px) rotateX(${rx}deg) rotateY(${ry}deg) ${zoom}`
  }
  const sheen = imgWrap.querySelector<HTMLElement>('.emu-cover-sheen')
  if (sheen && themeStore.cardShine) {
    const mx = ((e.clientX - rect.left) / rect.width * 100).toFixed(1)
    const my = ((e.clientY - rect.top) / rect.height * 100).toFixed(1)
    sheen.style.opacity = '1'
    sheen.style.background = `radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%)`
  }
}

function onCardLeave(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const imgWrap = el.querySelector<HTMLElement>('.emu-cover-img-wrap')
  if (!imgWrap) return
  imgWrap.style.transform = ''
  imgWrap.classList.remove('glow-active')
  const sheen = imgWrap.querySelector<HTMLElement>('.emu-cover-sheen')
  if (sheen) sheen.style.opacity = '0'
}

// ── Init ──────────────────────────────────────────────────────────────────────

// POMOC accent color for this platform
const platformColor = computed(() => {
  const fs = platform.value?.fs_slug
  return fs ? platformMeta.getColor(fs) : ''
})

// Fan art fallback background (POMOC WEBP)
const fanartUrl = computed(() =>
  platform.value?.fs_slug ? `/platforms/fanart/${platform.value.fs_slug}.webp` : ''
)
const headerBgUrl = computed(() =>
  platform.value?.photo_path || fanartUrl.value
)

// Platform description priority: XML in user lang > Wikipedia (DB) > XML in English
const xmlDescLocal = computed(() => {
  const fs = platform.value?.fs_slug
  if (!fs) return ''
  const lang = localStorage.getItem('gd3_locale') || 'en'
  const d = platformMeta.meta[fs]?.descriptions
  return d?.[lang] || ''
})
const xmlDescEn = computed(() => {
  const fs = platform.value?.fs_slug
  if (!fs) return ''
  const d = platformMeta.meta[fs]?.descriptions
  return d?.['en'] || ''
})
const platformDescription = computed(() =>
  xmlDescLocal.value || platform.value?.description || xmlDescEn.value || ''
)

const titleBarStyle = computed(() => {
  return platformColor.value ? { '--platform-color': `#${platformColor.value}` } : {}
})

onMounted(async () => {
  platformMeta.fetchIfNeeded()
  await fetchPlatform()
  fetchRoms()
  refreshReqBadge()
})
</script>

<style scoped>
.emu-library {
  display: flex; flex-direction: column; gap: var(--space-5, 20px);
  padding: 24px 32px; min-height: 100%;
}

/* ── Title bar ────────────────────────────────────────────────────────────── */
.emu-title-bar {
  position: relative; overflow: hidden;
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: var(--space-4, 16px); flex-wrap: wrap;
  padding: 16px 20px;
  /* Lock the bar to its natural XS height so it never compresses or grows when
     cover size changes. 170px = 120px platform icon + 2×16px padding + margin-top:4px on title-right. */
  flex-shrink: 0;
  min-height: 170px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid color-mix(in srgb, var(--platform-color, transparent) 40%, var(--glass-border));
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
  /* When photo present, use it as background */
  background-size: cover;
  background-position: center;
  transition: background-image 0.4s ease;
}
/* Hero background - respects hero blur + animation settings */
.emu-title-bg {
  position: absolute; inset: -20px; z-index: 0;
  background-size: cover; background-position: center;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(110%) brightness(.55);
  transform-origin: center; transform: scale(1.06);
  will-change: transform;
}
.emu-title-bg--kenburns { animation: etb-kenburns 44s ease-in-out infinite; }
.emu-title-bg--drift    { animation: etb-drift 28s ease-in-out infinite alternate; }
.emu-title-bg--pulse    { animation: etb-pulse 10s ease-in-out infinite; }
@keyframes etb-kenburns { 0%,100% { transform: scale(1.06) translateX(0%); } 50% { transform: scale(1.14) translateX(-3%); } }
@keyframes etb-drift    { 0% { transform: scale(1.1) translateX(0%); } 100% { transform: scale(1.1) translateX(-5%); } }
@keyframes etb-pulse    { 0%,100% { transform: scale(1.04); } 50% { transform: scale(1.12); } }

.emu-title-photo-overlay {
  position: absolute; inset: 0; z-index: 0;
  background: linear-gradient(135deg, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.45) 60%, rgba(0,0,0,0.62) 100%);
}
.emu-title-bar--photo {
  border-color: rgba(255,255,255,.14);
  box-shadow: 0 4px 32px rgba(0,0,0,0.5);
}
.emu-title-left  { display: flex; align-items: flex-start; gap: var(--space-4, 16px); position: relative; z-index: 1; }
.emu-title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; padding-top: 4px; position: relative; z-index: 1; }

/* Center: absolutely centered on screen - horizontal layout */
.emu-title-center {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  z-index: 1; pointer-events: none;
  display: flex; flex-direction: row; align-items: center; gap: 18px;
  max-width: 660px; width: max-content;
}
.emu-title-center > * { pointer-events: auto; }

/* Left column: photo */
.emu-console-photo-col {
  flex-shrink: 0; display: flex; align-items: center; justify-content: center;
}
.emu-console-photo {
  max-height: 110px; max-width: 200px; object-fit: contain;
  filter: drop-shadow(0 4px 20px rgba(0,0,0,0.75));
  transition: transform .3s ease;
}
.emu-console-photo:hover { transform: scale(1.04); }

/* Right column: chips + description + wiki */
.emu-console-info-col {
  display: flex; flex-direction: column; gap: 7px; min-width: 0;
}
.emu-console-meta {
  display: flex; gap: 5px; flex-wrap: wrap;
}
.emu-console-desc-wrap { position: relative; }
.emu-console-desc {
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.72); line-height: 1.6; margin: 0;
  display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical;
  overflow: hidden; max-width: 380px;
}
.emu-wiki-link-inline {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: var(--fs-xs, 10px); font-weight: 700; color: rgba(255,255,255,.5);
  text-decoration: none; letter-spacing: .4px; margin-top: 2px;
  transition: color var(--transition), opacity var(--transition);
}
.emu-wiki-link-inline:hover { color: var(--pl-light); opacity: 1; }

.emu-console-placeholder {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--muted);
}
.emu-console-placeholder-text {
  font-size: 11px; opacity: .45; text-align: center; max-width: 140px; line-height: 1.4;
}

/* ── Platform info panel ──────────────────────────────────────────────────── */
.emu-platform-info {
  padding: 14px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
}
.emu-platform-meta {
  display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; margin-bottom: 10px;
}
.emu-meta-chip {
  padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700;
  background: color-mix(in srgb, var(--pl) 14%, transparent);
  color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 28%, transparent);
  letter-spacing: .3px;
}
.emu-platform-desc {
  font-size: 13px; color: var(--muted); line-height: 1.65; margin: 0;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}
.emu-wiki-link {
  display: inline-flex; align-items: center; gap: 5px; margin-top: 8px;
  font-size: 11px; font-weight: 600; color: var(--pl-light); opacity: .75;
  text-decoration: none; letter-spacing: .3px;
  transition: opacity var(--transition);
}
.emu-wiki-link:hover { opacity: 1; }

.emu-back-btn {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px); flex-shrink: 0; margin-top: 4px;
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all var(--transition);
}
.emu-back-btn:hover { border-color: var(--pl); color: var(--text); }

/* Vertical platform identity block */
.emu-platform-identity {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
}
.emu-platform-icon {
  width: 120px; height: 120px; object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.5));
}
.emu-platform-name-logo {
  max-width: 260px; max-height: 44px;
  object-fit: contain;
  filter: drop-shadow(0 1px 8px rgba(0,0,0,.6)) brightness(1.15);
}
.emu-platform-name-text {
  font-size: var(--fs-2xl, 22px); font-weight: 800; color: var(--text); line-height: 1.1;
}
.emu-platform-count { font-size: 11px; color: var(--muted); }

/* Sort & size */
.emu-sort-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: var(--fs-sm, 12px);
  font-weight: 600; padding: 6px 10px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.emu-sort-select:hover { border-color: var(--pl); }
.emu-sort-select option { background: var(--bg2); }

.emu-size-group {
  display: flex; border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); overflow: hidden;
}
.emu-size-btn {
  padding: 5px 9px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.emu-size-btn + .emu-size-btn { border-left: 1px solid var(--glass-border); }
.emu-size-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.emu-size-btn.active { background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light); }

.emu-action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.emu-action-btn:hover:not(:disabled) { border-color: var(--pl); color: var(--text); }
.emu-action-btn:disabled             { opacity: .5; cursor: not-allowed; }
.emu-action-btn--danger { color: #f87171; border-color: rgba(239,68,68,.35); }
.emu-action-btn--danger:hover:not(:disabled) { border-color: #f87171; color: #fca5a5; background: rgba(239,68,68,.1); }
.emu-action-btn--request:hover:not(:disabled) { border-color: var(--pl); color: var(--pl-light); background: rgba(124,58,237,.1); }
.emu-req-notify-dot {
  position: absolute; top: -5px; right: -5px;
  min-width: 17px; height: 17px; border-radius: 9px;
  background: #ef4444; color: #fff; font-size: 9px; font-weight: 800;
  display: flex; align-items: center; justify-content: center; padding: 0 4px;
  pointer-events: none; border: 2px solid var(--bg, #0f0f1a);
}

/* ── Loading / empty ──────────────────────────────────────────────────────── */
.emu-loading { display: flex; align-items: center; justify-content: center; padding: 80px; }
.emu-empty   { display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px); padding: 60px; color: var(--muted); text-align: center; }
.emu-empty-sub { font-size: var(--fs-sm, 12px); }
.emu-empty-sub code { background: rgba(255,255,255,.07); padding: 2px 6px; border-radius: var(--radius-xs, 4px); font-size: 11px; }

/* ── Cover grid ───────────────────────────────────────────────────────────── */
.emu-cover-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cover-min, 175px), 1fr));
  gap: var(--space-4, 16px);
  padding-bottom: 20px;
}

.emu-cover-wrap { cursor: pointer; display: flex; flex-direction: column; gap: 6px; }

.emu-cover-img-wrap {
  position: relative; border-radius: var(--radius-sm); overflow: hidden;
  aspect-ratio: 3/4; background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.2s, border-color 0.2s;
  transform-style: preserve-3d;
}
/* Glow ring on hover */
.emu-cover-img-wrap::after {
  content: ''; position: absolute; inset: -1px; border-radius: inherit;
  border: 1px solid var(--pl);
  box-shadow: 0 0 24px color-mix(in srgb, var(--pl) 35%, transparent), inset 0 0 16px rgba(0,0,0,.1);
  opacity: 0; transition: opacity var(--transition); pointer-events: none; z-index: 2;
}
.emu-cover-img-wrap.glow-active::after { opacity: 1; }

.emu-cover-sheen {
  position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity 0.3s; z-index: 3;
}
.emu-cover-img   { width: 100%; height: 100%; object-fit: cover; display: block; }
.emu-cover-fallback {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.12);
}

/* Badges */
.emu-cover-badges { position: absolute; top: 6px; left: 6px; display: flex; gap: 3px; z-index: 4; }
.emu-badge {
  padding: 2px 5px; border-radius: 3px;
  background: rgba(0,0,0,.55); color: rgba(255,255,255,.7);
  font-size: 9px; font-weight: 700; letter-spacing: .3px;
}

/* Hover overlay */
.emu-cover-overlay {
  position: absolute; inset: 0; z-index: 5;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.2) 50%, transparent 100%);
  display: flex; flex-direction: column; justify-content: flex-end; padding: 10px;
  opacity: 0; transition: opacity .18s;
}
.emu-cover-wrap:hover .emu-cover-overlay { opacity: 1; }
.emu-overlay-title {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px;
}
.emu-overlay-meta { font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.6); }

/* Card labels below cover */
.emu-cover-title {
  font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 2px;
}
.emu-cover-meta  { display: flex; gap: 6px; align-items: center; padding: 0 2px; }
.emu-cover-year  { font-size: var(--fs-xs, 10px); color: var(--muted); }
.emu-cover-rating { font-size: var(--fs-xs, 10px); color: #fbbf24; }

/* ── Pagination ───────────────────────────────────────────────────────────── */
.emu-pagination {
  display: flex; align-items: center; justify-content: center; gap: 14px; padding: 12px 0;
}
.emu-page-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.emu-page-btn:hover:not(:disabled) { border-color: var(--pl); color: var(--text); }
.emu-page-btn:disabled { opacity: .4; cursor: not-allowed; }
.emu-page-info { font-size: var(--fs-sm, 12px); color: var(--muted); }

.emu-action-msg { font-size: var(--fs-sm, 12px); color: var(--muted); text-align: center; padding: var(--space-1, 4px); }

.spinner {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.15); border-top-color: var(--pl-light);
  animation: spin .8s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spin { animation: spin .8s linear infinite; }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .emu-title-bar { padding: 10px 12px; gap: var(--space-2, 8px); }
  .emu-plat-logo { max-height: 28px; }
  .emu-plat-name { font-size: 15px; }
  .emu-size-group { display: none; }
  .emu-cover-grid { gap: 10px; }
}
</style>
