/**
 * Library registry store. Fetches the data-driven list of libraries from
 * /api/libraries (filtered server-side by the user's RBAC scopes) so the
 * navbar, home page and themes can render libraries dynamically instead of
 * hard-coding GOG / Games / Emulation. Exposed to plugins via
 * window.__GD__.stores.libraries.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/services/api/client'
import { useThemeStore } from '@/stores/theme'
import i18n from '@/i18n'

// Built-in libraries map to fixed GD routes; collections live at /lib/:slug.
const _BUILTIN_ROUTE: Record<string, string> = {
  gog: '/library', games: '/games', emulation: '/emulation', couch: '/couch',
}
// Built-in display names come from the UI translations (collections use their name).
const _BUILTIN_LABEL_KEY: Record<string, string> = {
  gog: 'nav.gog_library', games: 'nav.games_library', emulation: 'nav.emulation', couch: 'couch.title',
}

export interface LibraryInfo {
  slug: string
  name: string
  kind: string            // "gog" | "custom" | "emulation" | "collection"
  icon: string | null
  color: string | null
  enabled: boolean
  sort_order: number
  is_builtin: boolean
  storage_folder: string | null
}

export const useLibrariesStore = defineStore('libraries', () => {
  const libraries = ref<LibraryInfo[]>([])
  const loaded = ref(false)

  async function fetch(): Promise<void> {
    try {
      const { data } = await client.get('/libraries')
      if (Array.isArray(data)) {
        libraries.value = data as LibraryInfo[]
        loaded.value = true
      }
    } catch {
      /* not authenticated yet, or endpoint unavailable - leave list empty */
    }
  }

  /**
   * Effective per-user display position for a library. The user's manual order
   * (theme store) wins; libraries the user has not ordered fall back after them,
   * by the admin sort_order. Used as the flexbox `order` everywhere.
   */
  function orderIndex(slug: string): number {
    const ord = useThemeStore().getLibraryOrder()
    const i = ord.indexOf(slug)
    if (i >= 0) return i
    return 1000 + (bySlug(slug)?.sort_order ?? 999)
  }

  /** Enabled libraries the user can see, in the effective per-user order. */
  const enabled = computed(() =>
    [...libraries.value]
      .filter(l => l.enabled)
      .sort((a, b) => orderIndex(a.slug) - orderIndex(b.slug)),
  )

  /**
   * Libraries the user actually wants to see: enabled minus the ones this user
   * has personally hidden from their home/nav. This is the list themes should
   * iterate (exposed to plugins via __GD__.stores.libraries().visible).
   */
  const visible = computed(() => {
    const ts = useThemeStore()
    return enabled.value.filter(l => !ts.isLibraryHidden(l.slug))
  })

  function bySlug(slug: string): LibraryInfo | undefined {
    return libraries.value.find(l => l.slug === slug)
  }

  /** True when a library with this slug exists and is enabled+visible. */
  function has(slug: string): boolean {
    return libraries.value.some(l => l.slug === slug && l.enabled)
  }

  /** True when the current user has hidden this library from their own view. */
  function isHidden(slug: string): boolean {
    return useThemeStore().isLibraryHidden(slug)
  }

  // ── Theme/plugin helpers (let any theme render libraries data-driven) ───────

  /** Frontend route path for a library's list view (collections -> /lib/:slug). */
  function route(slugOrLib: string | LibraryInfo): string {
    const slug = typeof slugOrLib === 'string' ? slugOrLib : slugOrLib.slug
    return _BUILTIN_ROUTE[slug] ?? ('/lib/' + slug)
  }

  /** Localised display label (built-in libraries use the UI translations). */
  function label(slugOrLib: string | LibraryInfo): string {
    const slug = typeof slugOrLib === 'string' ? slugOrLib : slugOrLib.slug
    const lib = typeof slugOrLib === 'string' ? bySlug(slug) : slugOrLib
    const key = _BUILTIN_LABEL_KEY[slug]
    return key ? i18n.t(key, lib?.name || slug) : (lib?.name || slug)
  }

  /**
   * The library slug a list-route path belongs to, or null when the path is not
   * a library list route (e.g. a detail page). Lets a theme decide which of its
   * library views to render and which library to fetch.
   */
  function slugForPath(path: string): string | null {
    if (path === '/library') return 'gog'
    if (path === '/games') return 'games'
    if (path === '/couch') return 'couch'
    if (path === '/emulation') return 'emulation'
    if (/^\/emulation\/[^/]+$/.test(path)) return 'emulation'  // platform ROM list
    const m = path.match(/^\/lib\/([^/]+)$/)
    return m ? m[1] : null
  }

  return {
    libraries, loaded, fetch, enabled, visible, bySlug, has, isHidden, orderIndex,
    route, label, slugForPath,
  }
})
