/**
 * Everything a catalogue listing needs to describe itself, minus how it looks.
 *
 * Two pages show the same listing: the store page Modern reaches, and the one
 * Classic swaps in because its catalogue list sits beside the page rather than
 * above it. They must stay two components - a skin is allowed to lay a page out
 * its own way - but the reading of the entry underneath was written twice, so
 * a field added to one of them quietly went missing on the other.
 *
 * The layout each page keeps for itself: its hero, its cover, its screenshot
 * strip, and the parts of `load()` that reset those (hence `onLoaded`).
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'
import { useLibrariesStore } from '@/stores/libraries'
import { resolveDetailRows } from '@/themes/index'
import { buildLanguageList } from '@/utils/langMap'
import { ratingVal } from '@/utils/rating'
import { reqOs as reqOsFrom, reqRows as reqRowsFrom } from '@/utils/requirements'
import { formatBytes } from '@/utils/format'
import { useI18n } from '@/i18n'

export interface EntryAsset { name: string; os?: string; size?: number; arch?: string | null }

/** One row of GET /plugins/library/catalog-entries/{id}. Everything past `id`
 *  and `title` is optional: an entry that was never scraped carries little more
 *  than its name. */
export interface CatalogEntry {
  id: number
  title: string
  subtitle?: string | null
  catalog_title?: string | null
  category?: string | null
  homepage?: string | null
  cover_path?: string | null
  background_path?: string | null
  logo_path?: string | null
  screenshots?: string[] | null
  description?: string | null
  developer?: string | null
  publisher?: string | null
  release_date?: string | null
  rating?: number | null
  genres?: string[] | null
  meta_ratings?: Record<string, number> | null
  languages?: Record<string, string> | null
  requirements?: Record<string, unknown> | null
  hltb_main_s?: number | null
  hltb_complete_s?: number | null
  available?: boolean
  unavailable_reason?: string | null
  assets?: EntryAsset[] | null
  release_tag?: string | null
  released_at?: string | null
  is_prerelease?: boolean
  /** Server-side folder a download lands in. Shown, never chosen. */
  save_root?: string | null
  downloaded?: boolean
  library_game_id?: number | null
  meta_source?: string | null
  meta_search_term?: string | null
  meta_matched_title?: string | null
  meta_confidence?: string | null
}

/** Collapse a build's free-form os string onto the few chips we can draw. */
export function osKey(os?: string | null): string {
  const k = String(os || '').toLowerCase()
  if (!k) return ''
  if (k.includes('win')) return 'windows'
  if (k.includes('mac') || k.includes('osx') || k.includes('darwin')) return 'mac'
  if (k.includes('linux')) return 'linux'
  return k
}

export function osLabel(os: string): string {
  if (os === 'windows') return 'Windows'
  if (os === 'mac') return 'macOS'
  if (os === 'linux') return 'Linux'
  return os
}

export function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

export function useCatalogEntry(opts: { onLoaded?: (entry: CatalogEntry | null) => void } = {}) {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const librariesStore = useLibrariesStore()

  const fmtSize = (b: number | null | undefined) => formatBytes(b, '')

  const entry         = ref<CatalogEntry | null>(null)
  const loading       = ref(true)
  const showDownload  = ref(false)
  const showMetaPanel = ref(false)
  const scraping      = ref(false)
  const coverFailed   = ref(false)

  const isAdmin = computed(() => auth.user?.role === 'admin')

  const assets      = computed<EntryAsset[]>(() => entry.value?.assets || [])
  const screenshots = computed<string[]>(() => entry.value?.screenshots || [])
  const entryLangs  = computed(() => buildLanguageList(entry.value?.languages))

  // release_date is free-form on an entry (a catalogue may store "2019" or a
  // full ISO date), so the year is matched rather than sliced off the front.
  const releaseYear = computed(() => (String(entry.value?.release_date || '').match(/(\d{4})/) || [])[1] || '')

  // The library's REAL display name, from the registry. Title-casing the slug
  // only ever produced "Pc Ports". The de-slugified form survives as the last
  // resort for a registry that has not loaded yet.
  const storeName = computed(() => {
    const slug = String(route.params.slug || '')
    if (!slug) return t('nav.store')
    const lib = librariesStore.bySlug(slug)
    if (lib) return librariesStore.label(lib)
    return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  })

  // Rows contributed by plugins via window.__GD__.registerDetailRow.
  const pluginRows = computed(() => (entry.value ? resolveDetailRows(entry.value as unknown as Record<string, unknown>, 'games') : []))
  // PluginDetailValue requires a non-null game object; an entry is always the
  // thing being described, so an empty object only ever stands in pre-load.
  const pluginGame = computed<Record<string, unknown>>(() => (entry.value || {}) as unknown as Record<string, unknown>)

  // The catalogue's own page for this listing, named by its host so the button
  // carries no label that would need translating.
  const homepageHost = computed(() => {
    const url = entry.value?.homepage
    if (!url) return ''
    try { return new URL(url).hostname.replace(/^www\./, '') } catch { return '' }
  })

  // ── Platforms ───────────────────────────────────────────────────────────────

  const assetOses = computed(() => {
    const seen: string[] = []
    for (const a of assets.value) {
      const k = osKey(a.os)
      if (k && !seen.includes(k)) seen.push(k)
    }
    const order = ['windows', 'mac', 'linux']
    return [...order.filter(o => seen.includes(o)), ...seen.filter(o => !order.includes(o))]
  })

  /** Builds grouped under the platform they are for, the way a GOG game lists
   *  its installers. A build marked for every platform - the catalogue's "all" -
   *  gets its own group rather than being repeated under each one, which is how
   *  it lands on disk too: in the title folder, not under an os. */
  const buildsByOs = computed(() => {
    const groups = new Map<string, EntryAsset[]>()
    for (const a of assets.value) {
      const k = osKey(a.os) || 'all'
      if (!groups.has(k)) groups.set(k, [])
      groups.get(k)!.push(a)
    }
    const order = ['windows', 'mac', 'linux', 'all']
    const keys = [
      ...order.filter(o => groups.has(o)),
      ...Array.from(groups.keys()).filter(o => !order.includes(o)),
    ]
    return keys.map(os => ({
      os,
      label: os === 'all' ? t('detail.dl_any_os') : osLabel(os),
      entries: groups.get(os)!,
    }))
  })

  // ── Ratings ─────────────────────────────────────────────────────────────────

  const externalRatings = computed(() => ({
    rawg:  entry.value?.meta_ratings?.['rawg']  ?? undefined,
    igdb:  entry.value?.meta_ratings?.['igdb']  ?? undefined,
    steam: entry.value?.meta_ratings?.['steam'] ?? undefined,
  }))

  // meta_ratings is keyed by provider id ("ppe"), which is not what the provider
  // calls itself ("PPE.pl"). Ask the plugins for their own names and fall back to
  // the shouted id when the list cannot be read.
  const providerNames = ref<Record<string, string>>({})

  const pluginRatings = computed(() => {
    const out: { id: string; name: string; rating: number; logo: string }[] = []
    for (const [k, v] of Object.entries(entry.value?.meta_ratings || {})) {
      if (k === 'rawg' || k === 'igdb' || k === 'steam') continue
      if (!ratingVal(v)) continue
      out.push({
        id: k,
        name: providerNames.value[k] || k.toUpperCase(),
        rating: ratingVal(v),
        logo: `/api/plugins/${k}-metadata/logo`,
      })
    }
    return out
  })

  const hasRatings = computed(() =>
    ratingVal(entry.value?.rating) > 0
    || !!externalRatings.value.rawg
    || !!externalRatings.value.igdb
    || !!externalRatings.value.steam
    || pluginRatings.value.length > 0,
  )

  async function loadProviderNames() {
    try {
      const { data } = await client.get('/plugins/metadata/providers')
      if (!Array.isArray(data)) return
      const out: Record<string, string> = {}
      for (const p of data) if (p?.id && p?.name) out[p.id] = p.name
      providerNames.value = out
    } catch { /* no read access to plugins: the id stands in */ }
  }

  function hideImg(e: Event) {
    (e.target as HTMLImageElement).style.display = 'none'
  }

  // ── Facts ───────────────────────────────────────────────────────────────────

  const hasMatchRows = computed(() => !!(
    entry.value?.meta_source || entry.value?.meta_matched_title || entry.value?.meta_search_term
  ))

  const totalSize = computed(() => {
    const bytes = assets.value.reduce((n, a) => n + (a.size ?? 0), 0)
    return bytes ? fmtSize(bytes) : ''
  })

  // Wider than the game page's set: a catalogue's requirements blob routinely
  // carries os/storage/directx, and dropping them here would lose data the
  // listing actually has.
  const reqRows = computed((): [string, string][] => reqRowsFrom(entry.value?.requirements))
  const reqOs   = computed(() => reqOsFrom(entry.value?.requirements))

  // ── Load / actions ──────────────────────────────────────────────────────────

  async function load() {
    loading.value = true
    try {
      const { data } = await client.get(`/plugins/library/catalog-entries/${route.params.id}`)
      entry.value = data
      coverFailed.value = false
    } catch { entry.value = null }
    finally { loading.value = false }
    opts.onLoaded?.(entry.value)
  }

  /** The save already pushed the new presentation onto the downloaded game
   *  server-side; this only brings the page itself back in step. */
  async function onMetadataSaved() {
    showMetaPanel.value = false
    await load()
  }

  async function refreshMeta() {
    if (!entry.value || scraping.value) return
    scraping.value = true
    try { await client.post(`/plugins/library/catalog-entries/${entry.value.id}/scrape-metadata`); await load() }
    catch { /* ignore */ }
    finally { scraping.value = false }
  }

  function goBack() {
    if (window.history.length > 1) router.back()
    else router.push(`/lib/${route.params.slug}`)
  }

  onMounted(() => {
    load()
    loadProviderNames()
    // The registry carries this store's display name; a deep link can land here
    // before anything else has fetched it.
    if (!librariesStore.loaded) librariesStore.fetch()
  })

  // Moving between two offers keeps the page mounted and only swaps the route
  // parameter, so loading once on mount left every pick showing whichever entry
  // happened to open first. Classic reaches the page that way for its whole
  // catalogue, since its list sits beside the page rather than above it.
  watch(() => route.params.id, (id, prev) => { if (id && id !== prev) load() })

  return {
    entry, loading, showDownload, showMetaPanel, scraping, coverFailed,
    isAdmin, assets, screenshots, entryLangs, releaseYear, storeName,
    pluginRows, pluginGame, homepageHost,
    assetOses, buildsByOs,
    externalRatings, providerNames, pluginRatings, hasRatings,
    hasMatchRows, totalSize, reqRows, reqOs,
    fmtSize, hideImg, load, onMetadataSaved, refreshMeta, goBack,
  }
}
