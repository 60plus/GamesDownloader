// ROM source actions for the built-in themes AND plugin themes.
//
// A ROM source is a remote catalogue of ROMs (archive.org, Myrient, ...) that a
// plugin describes. Unlike a library catalogue it is browsed live and lazily:
// there can be tens of thousands of ROMs, so nothing is pre-synced. A theme asks
// for the sources, drills into a platform, lists ROMs (paginated), and downloads
// a single one into roms/<platform>/, where the scan + scrape pipeline picks it
// up. Exposed as `window.__GD__.romSources` (see main.ts) so every theme brings
// its own layout and calls this for the data.
//
// Progress arrives over socket.io as "romsource:download_*" events (subscribe
// via __GD__.events.on), keyed on the job id returned by download().

import client from "../services/api/client";

export interface RomSource {
  id: string;
  name: string;
  plugin_id?: string | null;
  /** Display name of the owning plugin (e.g. "RomDownloader"). A theme heads
   * the source view with this and keeps `name` as the catalogue detail. */
  plugin_name?: string | null;
  /** URL of the icon the owning plugin ships (its icon_asset, else its logo). */
  icon?: string | null;
  /** Full URL to the source's tile art, served from the plugin's assets/. */
  tile_bg?: string | null;
  requires_auth?: boolean;
  /** False when the source needs credentials it does not yet have. */
  configured?: boolean;
}

export interface RomSourcePlatform {
  fs_slug: string;
  display: string;
  count?: number | null;
}

export interface RomSourceEntry {
  id: string;
  title: string;
  filename: string;
  region?: string | null;
  size?: number | null;
  /** Which catalogue the entry came from, when the source merges several. */
  collection?: string | null;
  /** Container the ROM arrives in (chd, zip, iso, ...), lower-case. */
  format?: string | null;
  /** What sort of release this is: retail, prototype, demo, hack, ... */
  kind?: string | null;
  /** Hashes of the ROM itself, when the source can vouch for them. Absent for
   * an entry that arrives inside an archive, where the source can only hash the
   * wrapper. */
  crc?: string | null;
  md5?: string | null;
  sha1?: string | null;
  /** True when a ROM with this hash (or filename) is already in the library. */
  owned: boolean;
}

export interface RomSourceListing {
  items: RomSourceEntry[];
  total: number;
  page: number;
  /** Every catalogue available for this platform (the filter's options).
   * Empty or one entry means the source has nothing to filter by. */
  collections?: string[];
  /** Same, for the container formats the platform is offered in. */
  formats?: string[];
  /** Same, for the release types (retail, prototype, translation, ...). */
  kinds?: string[];
}

export interface ListRomsOpts {
  page?: number;
  pageSize?: number;
  query?: string;
  region?: string;
  sort?: string;
  /** Show only entries from this catalogue (a value from `collections`). */
  collection?: string;
  /** Show only entries in this container (a value from `formats`). */
  format?: string;
  /** Show only entries of this release type (a value from `kinds`). */
  kind?: string;
}

/** Every ROM source the installed plugins registered. */
export async function list(): Promise<RomSource[]> {
  const { data } = await client.get("/rom-sources");
  return Array.isArray(data) ? (data as RomSource[]) : [];
}

/** The platforms one source offers (already filtered to slugs GD recognizes). */
export async function platforms(sourceId: string): Promise<RomSourcePlatform[]> {
  const { data } = await client.get(
    `/rom-sources/${encodeURIComponent(sourceId)}/platforms`,
    { timeout: 120000 },
  );
  return Array.isArray(data) ? (data as RomSourcePlatform[]) : [];
}

/** The key a preview belongs to: the game, not the row.
 *
 * Regional variants of one game all clean down to the same phrase, so a theme
 * that caches on this looks a game up once however many rows carry it.
 */
export function previewKey(
  fsSlug: string,
  entry: Pick<RomSourceEntry, "title" | "filename">,
): string {
  let base = (entry.title || entry.filename || "").trim();
  if (!entry.title && base.includes(".")) base = base.replace(/\.[^.]+$/, "");
  return `${fsSlug}:${base.replace(/\s*[([][^()[\]]*[)\]]/g, "").trim().toLowerCase()}`;
}

export interface RomSourcePreview {
  /** False when no provider recognised the game; `query` says what was asked. */
  found: boolean;
  /** The phrase the row was looked up by, tags stripped. Shown when nothing hit. */
  query: string;
  /** Which provider answered ("screenscraper" | "igdb"), null when none did. */
  source: string | null;
  /** "hash" when the entry carried one, otherwise "name". */
  matched_by?: string;
  name?: string | null;
  summary?: string | null;
  developer?: string | null;
  publisher?: string | null;
  genres?: string[];
  release_year?: number | string | null;
  /** Already proxied - a scraper URL carries the account in its query string. */
  cover_url?: string | null;
}

/** Look ONE browsing row up: cover, year, developer.
 *
 * Costs a scraper call, so it is meant for a row the user asked about - never
 * for a listing. Pass the entry straight through: its hashes identify the game
 * exactly where it has them, its filename and size where it does not.
 */
export async function previewEntry(
  fsSlug: string,
  entry: Pick<RomSourceEntry, "title" | "filename" | "size" | "crc" | "md5" | "sha1">,
): Promise<RomSourcePreview> {
  const { data } = await client.get("/rom-sources/preview", {
    params: {
      fs_slug: fsSlug,
      title: entry.title || undefined,
      filename: entry.filename || undefined,
      size: entry.size || undefined,
      crc: entry.crc || undefined,
      md5: entry.md5 || undefined,
      sha1: entry.sha1 || undefined,
    },
    timeout: 30000,
  });
  return data as RomSourcePreview;
}

/** A live, paginated page of ROMs for one platform, each stamped with owned. */
export async function listRoms(
  sourceId: string,
  fsSlug: string,
  opts: ListRomsOpts = {},
): Promise<RomSourceListing> {
  const { data } = await client.get(
    `/rom-sources/${encodeURIComponent(sourceId)}/platforms/${encodeURIComponent(fsSlug)}/roms`,
    {
      params: {
        page: opts.page ?? 1,
        page_size: opts.pageSize ?? 60,
        query: opts.query || undefined,
        region: opts.region || undefined,
        sort: opts.sort || undefined,
        collection: opts.collection || undefined,
        fmt: opts.format || undefined,
        kind: opts.kind || undefined,
      },
      // A source browses live: a cold set spread over dozens of upstream items
      // takes longer than the client's default patience, and timing out mid-warm
      // leaves the user with an error instead of a list.
      timeout: 120000,
    },
  );
  return data as RomSourceListing;
}

/** Queue one or more entries for download into roms/<platform>/. Progress
 * arrives on "romsource:download_*" (via __GD__.events). Returns the accepted
 * jobs plus anything skipped (already downloading, unresolvable). */
export async function download(
  sourceId: string,
  entryIds: string | string[],
  opts: { force?: boolean } = {},
): Promise<{ queued: Array<Record<string, unknown>>; skipped: Array<Record<string, unknown>> }> {
  const ids = Array.isArray(entryIds) ? entryIds : [entryIds];
  const { data } = await client.post(
    `/rom-sources/${encodeURIComponent(sourceId)}/download`,
    { entry_ids: ids.map(String), force: !!opts.force },
  );
  return data as { queued: Array<Record<string, unknown>>; skipped: Array<Record<string, unknown>> };
}

/** General primitive: download one ROM by direct URL into roms/<fsSlug>/, then
 * scan + scrape. For plugins that have a URL rather than a full source adapter.
 * Public fetch (SSRF-guarded); an authenticated source uses its own download
 * path where credentials stay server-side. */
export async function importRom(
  url: string,
  fsSlug: string,
  filename: string,
): Promise<Record<string, unknown>> {
  const { data } = await client.post("/rom-sources/import", {
    url: (url || "").trim(),
    fs_slug: fsSlug,
    filename,
  });
  return data as Record<string, unknown>;
}

/** Canonical in-app route for a source's platform grid, or (with fsSlug) its ROM
 * list. A theme navigates here instead of hardcoding the path, so the layout of
 * the URLs stays owned by the core - the same contract as __GD__.collections.route. */
export function route(sourceId: string, fsSlug?: string): string {
  const base = `/rom-sources/${encodeURIComponent(sourceId)}`;
  return fsSlug ? `${base}/${encodeURIComponent(fsSlug)}` : base;
}

/** The built-in per-platform console art GD serves (icon, name wordmark, fanart
 * backdrop) for an fs_slug. A theme rendering a source's platform grid reuses the
 * same art the Retro grid uses, without hardcoding the path convention. */
export function platformArt(fsSlug: string): { icon: string; name: string; fanart: string } {
  const s = encodeURIComponent(fsSlug);
  return {
    icon: `/platforms/icons/${s}.png`,
    name: `/platforms/names/${s}.svg`,
    fanart: `/platforms/fanart/${s}.webp`,
  };
}

/** Drop a source's cached listings so the next one is fetched again. */
export async function refreshSource(sourceId: string): Promise<{ refreshed: boolean; reason?: string }> {
  const { data } = await client.post(`/rom-sources/${encodeURIComponent(sourceId)}/refresh`);
  return data as { refreshed: boolean; reason?: string };
}

/** Stop writing but keep what is on disk; resume() carries on from there. */
export async function pauseJob(jobId: number): Promise<void> {
  await client.post(`/rom-sources/downloads/${jobId}/pause`);
}

/** Carry on from the end of the .part file. */
export async function resumeJob(jobId: number): Promise<void> {
  await client.post(`/rom-sources/downloads/${jobId}/resume`);
}

/** Run a failed or cancelled download again. */
export async function retryJob(jobId: number): Promise<void> {
  await client.post(`/rom-sources/downloads/${jobId}/retry`);
}

/** Stop and delete a running download, or drop a finished one from the list. */
export async function cancelJob(jobId: number): Promise<void> {
  await client.delete(`/rom-sources/downloads/${jobId}`);
}

/** Jobs the server still knows about, so a reloaded page finds them again. */
export async function listJobs(): Promise<Array<Record<string, unknown>>> {
  const { data } = await client.get("/rom-sources/downloads");
  return (data?.jobs || []) as Array<Record<string, unknown>>;
}

/** The `window.__GD__.roms` namespace (general ROM primitives). */
export const romActions = { import: importRom };

export default {
  list, platforms, listRoms, download, route, platformArt,
  previewEntry, previewKey,
  pauseJob, resumeJob, retryJob, cancelJob, listJobs, refreshSource,
};
