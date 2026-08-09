// Plugin catalogue (store) actions for the built-in themes AND plugin themes.
//
// A catalogue is what the server COULD hold: a plugin syncs a list of offers
// (PC Ports and the like) and each one becomes a real game only when somebody
// pulls a build. Vapor spoke to these endpoints directly, which is why the
// store worked in exactly one theme out of four - every other theme rendered
// the store's shelf as an ordinary library and listed the handful of games
// already downloaded from it, with no way to reach the catalogue at all.
//
// These helpers own the endpoint shapes once, the way libraryActions does for
// add-content. Exposed to plugins as `window.__GD__.catalog` (see main.ts), so
// a theme brings its own layout and calls this for the data.

import client from "../services/api/client";

export interface CatalogEntry {
  id: number;
  title: string;
  subtitle?: string | null;
  cover_path?: string | null;
  icon_path?: string | null;
  /** True once a build has been pulled: the offer is now a game. */
  downloaded?: boolean;
  /** The game it became, when it has become one. */
  library_game_id?: number | null;
  /** What can be pulled, per OS. */
  sources?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** Everything a catalogue is offering. */
export async function listEntries(catalogId: string): Promise<CatalogEntry[]> {
  const { data } = await client.get(
    `/plugins/library/catalogs/${encodeURIComponent(catalogId)}/entries`,
  );
  return Array.isArray(data) ? (data as CatalogEntry[]) : [];
}

/** How many offers a catalogue holds, without pulling any of them. For a card
 * that shows only the number - listEntries would serialise every entry whole. */
export async function countEntries(catalogId: string): Promise<number> {
  const { data } = await client.get(
    `/plugins/library/catalogs/${encodeURIComponent(catalogId)}/entries/count`,
  );
  return Number((data as { count?: number })?.count) || 0;
}

/** One offer, with the detail the store page shows. */
export async function getEntry(entryId: number): Promise<CatalogEntry> {
  const { data } = await client.get(`/plugins/library/catalog-entries/${entryId}`);
  return data as CatalogEntry;
}

/** Pull builds onto the server. `assets` names the files to fetch; omitting it
 * lets the server take the entry's default. The offer becomes a game in the
 * Games library, exactly as a GOG download does. */
export async function download(
  entryId: number,
  opts: { assets?: string[] } = {},
): Promise<unknown> {
  const { data } = await client.post(
    `/plugins/library/catalog-entries/${entryId}/download`,
    opts.assets ? { assets: opts.assets } : {},
  );
  return data;
}

/** Re-read the catalogue from its source. Admin only, server-side. */
export async function sync(catalogId: string): Promise<unknown> {
  const { data } = await client.post(
    `/plugins/library/catalogs/${encodeURIComponent(catalogId)}/sync`,
    {},
  );
  return data;
}

/** Every catalogue the installed plugins registered. */
export async function listCatalogs(): Promise<Array<Record<string, unknown>>> {
  const { data } = await client.get("/plugins/library/catalogs");
  return Array.isArray(data) ? data : [];
}

/** Wipe every listing's scraped metadata in one store. The catalogue's own
 * facts (titles, builds) stay; only what a scrape derived is cleared, ready to
 * be re-fetched. Admin only, server-side. */
export async function clearMetadata(catalogId: string): Promise<{ cleared: number }> {
  const { data } = await client.post(
    `/plugins/library/catalogs/${encodeURIComponent(catalogId)}/clear-metadata`,
    {},
  );
  return data as { cleared: number };
}

export default { listEntries, countEntries, getEntry, download, sync, listCatalogs, clearMetadata };
