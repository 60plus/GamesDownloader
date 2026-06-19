/**
 * Collections store. Exposes the admin-curated game groupings to the app and,
 * via window.__GD__.stores.collections / window.__GD__.collections, to any
 * theme or plugin - the same way libraries are exposed, so a third-party theme
 * can render the Collections tab and its grid/detail without reaching into GD
 * internals.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/services/api/client'

// The full collection payload exposed to themes/plugins via window.__GD__.collections.
// Every field below is also present on the grid (list) items; get(slug) additionally
// returns `games` (the member LibraryGames) and aggregates languages/genres/playtime
// from them. A theme can render a collection's About + Details entirely from this.
export interface CollectionInfo {
  slug: string
  name: string
  library: string | null      // container library slug (kind 'collections')
  description: string | null         // long description (detail "About")
  description_short: string | null   // short description (list view hero)
  cover_path: string | null          // custom cover (null = auto fan of member covers)
  member_covers: string[]
  member_heroes: string[]
  member_count: number
  rating: number | null              // override, else average of members (0-5)
  rating_auto: boolean               // true when rating is the member average
  start_year: number | null
  end_year: number | null
  // Aggregated from the member games (developers/publishers/sources always; genres,
  // languages and the average Time to Beat are populated on get(slug)).
  developers: string[]
  publishers: string[]
  genres: string[]
  languages: Record<string, string>  // merged member language map (code -> name)
  sources: string[]
  platforms: { windows: boolean; mac: boolean; linux: boolean }
  hltb_main_s: number | null         // average / overridden main-story playtime (seconds)
  hltb_complete_s: number | null     // average / overridden 100% playtime (seconds)
  hltb_auto: boolean                 // true when Time to Beat is the member average
}

export const useCollectionsStore = defineStore('collections', () => {
  const list = ref<CollectionInfo[]>([])
  const loaded = ref(false)

  /** Fetch all collections (the grid payload). Safe to call repeatedly. */
  async function fetch(): Promise<void> {
    try {
      const { data } = await client.get('/collections')
      if (Array.isArray(data)) {
        list.value = data as CollectionInfo[]
        loaded.value = true
      }
    } catch {
      /* not authenticated yet, or no collections - leave list empty */
    }
  }

  function bySlug(slug: string): CollectionInfo | undefined {
    return list.value.find(c => c.slug === slug)
  }

  /** A collection's full detail, including its member games. */
  async function get(slug: string): Promise<any | null> {
    try {
      const { data } = await client.get('/collections/' + slug)
      return data
    } catch {
      return null
    }
  }

  /** The collection slugs a game belongs to (for a detail row / badge). */
  async function forGame(gameId: number | string): Promise<string[]> {
    try {
      const { data } = await client.get('/collections/membership/' + gameId)
      return (data && data.collections) || []
    } catch {
      return []
    }
  }

  /** Frontend route for a collection (nested under its container library), or
   *  the container grid when only a library slug is known. Returns '' if the
   *  collection is not loaded (its container is unknown). */
  function route(slug?: string): string {
    if (!slug) return ''
    const c = bySlug(slug)
    return c && c.library ? `/collections/${c.library}/${c.slug}` : ''
  }

  /** Route for a container library's collection grid. */
  function libraryRoute(librarySlug: string): string {
    return '/collections/' + librarySlug
  }

  return { list, loaded, fetch, bySlug, get, forGame, route, libraryRoute }
})
