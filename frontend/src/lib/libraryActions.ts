// Unified, library-aware "add content" actions for the built-in themes AND
// plugin themes. Every theme used to re-implement create-game / upload-file /
// upload-from-url / add-torrent / scan with raw `api.post(...)` calls, so a
// change like "target the current custom library" had to be duplicated in four
// places (and torrent targeting would have been three more). These helpers own
// the endpoint shapes and the library-targeting rules once; themes keep their
// own dialogs but call this API.
//
// Exposed to plugins as `window.__GD__.library` (see main.ts). The functions
// use the shared axios client (with its Bearer interceptor), so they work the
// same whether called from core or from a compiled plugin bundle.
//
// The URL-upload and torrent flows run server-side and report progress over
// socket.io; these helpers return the job/download record and the caller wires
// up its own listeners (core via the socket store, plugins via __GD__.events).

import client from "../services/api/client";
import { useDialog } from "../composables/useDialog";
import { useI18n } from "../i18n";

const { t } = useI18n();

/** Normalize a library slug for targeting: "", "games" and null all mean the
 * built-in Games library, expressed as `undefined` so it is omitted. */
function _target(library?: string | null): string | undefined {
  const s = (library || "").trim();
  return s && s !== "games" ? s : undefined;
}

export interface CreateGameOpts {
  title: string;
  /** Target library slug; "games"/empty/null => built-in Games library. */
  library?: string | null;
  slug?: string;
  description?: string;
  description_short?: string;
  developer?: string;
  publisher?: string;
  genres?: unknown;
  tags?: unknown;
}

export interface UploadFileOpts {
  os?: string;
  fileType?: string;
  language?: string | null;
  version?: string | null;
  /** Called with (percent 0-100, rawProgressEvent) during the upload. */
  onProgress?: (percent: number, ev: unknown) => void;
}

export interface UploadFromUrlOpts {
  url: string;
  os?: string;
  fileType?: string;
  language?: string | null;
  version?: string | null;
}

export interface AddTorrentOpts {
  /** Magnet/.torrent URL string, or a File when `isFile` is true. */
  source: string | File;
  title: string;
  os?: string;
  /** Target library slug; "games"/empty/null => built-in Games library. */
  library?: string | null;
  /** true => `source` is an uploaded .torrent File, false => URL/magnet. */
  isFile?: boolean;
}

export interface AddByUploadOpts {
  title: string;
  file: File;
  library?: string | null;
  os?: string;
  fileType?: string;
  language?: string | null;
  version?: string | null;
  onProgress?: (percent: number, ev: unknown) => void;
}

/** The game already on this shelf with exactly this title, or null.
 *
 *  Reported by the owner: he uploaded Ion Fury, then uploaded its DLC under the
 *  same title with the type set to DLC, and got a SECOND library entry -
 *  `ion-fury` and `ion-fury-1`. The file itself went to the right place, under
 *  one `Ion Fury/` folder with the DLC in `dlc/`; what went wrong was the row.
 *
 *  `POST /library/games` always creates, appending `-1`, `-2` to a slug that is
 *  taken, and every upload dialog began by calling it. So the same title always
 *  made a second entry, and nothing in the interface added a file to a game
 *  that was already there.
 *
 *  This lives here rather than in each dialog because FOUR of them ask the
 *  question - the two core layouts and both themes - and the themes are
 *  published separately, so a copy inside one of them could not be corrected
 *  along with the core.
 */
export async function findGameByTitle(
  title: string,
  library?: string | null,
): Promise<any | null> {
  const wanted = (title || "").trim().toLowerCase();
  if (!wanted) return null;
  const { data } = await client.get("/library/games", {
    // Narrowed to the shelf being uploaded to: the same title on a different
    // library is a different game, and treating it as a collision would refuse
    // a perfectly ordinary upload.
    params: { search: title.trim(), library: _target(library) ?? "", limit: 25 },
  });
  const rows = (data?.games ?? data?.items ?? data) as any[];
  if (!Array.isArray(rows)) return null;
  // The search is a search: it answers with anything similar. Only an exact
  // title is a collision - "Ion Fury" must not match "Ion Fury: Aftershock".
  return rows.find(g => String(g?.title ?? "").trim().toLowerCase() === wanted) ?? null;
}

/** The game an upload goes into: the one already on the shelf, a new one, or
 *  null when the person cancels.
 *
 *  THE OWNER DECIDED, 2026-09-17: when the title is already on the shelf,
 *  ALWAYS ask - "uploader doda gre a admin moze dodac dlc na przyklad" - and
 *  anybody who may upload may add to a game somebody else added. So the
 *  question has three answers:
 *
 *    Add to the existing game   the file joins it (a DLC, an extra, a build);
 *    Separate entry             a different game that shares the title - Doom
 *                               1993 and Doom 2016 - made here, in its own
 *                               folder on the server;
 *    Cancel                     null: nothing is made and nothing is sent.
 *
 *  Before this, "no" gave up, and the only way to upload a second game with
 *  that title was to type a different one (1.0.34 audit, #13).
 *
 *  One place asks it, for all four upload dialogs: Modern, Classic, and the two
 *  themes through `__GD__.library`, which ship separately and could not be
 *  corrected with a copy of their own. */
export async function chooseUploadTarget(opts: CreateGameOpts): Promise<any | null> {
  const title = (opts.title || "").trim();
  const existing = await findGameByTitle(title, opts.library);
  if (!existing) return createGame(opts);

  const answer = await useDialog().gdChoose(
    t("upload.game_exists_choice", { title: existing.title }),
    {
      title:       t("upload.same_title"),
      confirmText: t("upload.add_to_existing"),
      altText:     t("upload.separate_entry"),
    },
  );
  if (answer === "confirm") return existing;
  if (answer !== "alt") return null;
  return createGame(opts);
}

/** Create a LibraryGame. When `library` names a folder-backed custom library
 * the server adds membership and keeps the game out of the default Games
 * library. Returns the created game (has `.id`). Always creates: a dialog
 * uploading under a title asks `chooseUploadTarget` instead. */
export async function createGame(opts: CreateGameOpts): Promise<any> {
  const { library, title, ...rest } = opts;
  const { data } = await client.post("/library/games", {
    title: (title || "").trim(),
    ...rest,
    library: _target(library),
  });
  return data;
}

/** Upload a single file to an existing game. Destination folder follows the
 * game's library automatically (server-side `_resolve_storage_folder`). */
export async function uploadFile(
  gameId: number | string,
  file: File,
  opts: UploadFileOpts = {},
): Promise<any> {
  const { os = "windows", fileType = "game", language, version, onProgress } = opts;
  const fd = new FormData();
  fd.append("os", os);
  fd.append("file_type", fileType);
  if (language) fd.append("language", language);
  if (version) fd.append("version", version);
  fd.append("file", file);
  const { data } = await client.post(`/library/games/${gameId}/upload`, fd, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: onProgress
      ? (ev: any) => { if (ev.total) onProgress(Math.round((ev.loaded / ev.total) * 100), ev); }
      : undefined,
  });
  return data;
}

/** Ask the server to download a file from a direct http(s) URL into an existing
 * game (runs in the background). Returns `{ id, filename }`; follow progress via
 * the `upload:url_progress|complete|error` socket events keyed on that id. */
export async function uploadFromUrl(
  gameId: number | string,
  opts: UploadFromUrlOpts,
): Promise<any> {
  const { url, os = "windows", fileType = "game", language, version } = opts;
  const { data } = await client.post(`/library/games/${gameId}/upload-url`, {
    url: (url || "").trim(),
    os,
    file_type: fileType,
    language: language ?? undefined,
    version: version ?? undefined,
  });
  return data;
}

/** Add a torrent (magnet/URL or uploaded .torrent) to the server. When the
 * download finishes it is auto-registered into `library` (folder + membership)
 * or the built-in Games library. Returns the download record (has `.id`,
 * `.percent`); follow progress via `torrent:download_*` socket events. */
export async function addTorrent(opts: AddTorrentOpts): Promise<any> {
  const { source, title, os = "windows", library, isFile = false } = opts;
  const lib = _target(library);
  if (isFile) {
    const fd = new FormData();
    fd.append("title", (title || "").trim());
    fd.append("target_os", os);
    if (lib) fd.append("library", lib);
    fd.append("file", source as File);
    const { data } = await client.post("/torrents/download/file", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  }
  const { data } = await client.post("/torrents/download/url", {
    url: (source as string || "").trim(),
    title: (title || "").trim(),
    os,
    library: lib,
  });
  return data;
}

/** Scan library folders and create/update games. With a slug, scans only that
 * library's folder; without one, scans the built-in Games folder plus every
 * folder-backed custom library. Returns `{ created, updated, errors, libraries }`. */
export async function scan(librarySlug?: string | null): Promise<any> {
  const lib = _target(librarySlug);
  const { data } = await client.post("/library/scan", null, {
    params: lib ? { library: lib } : {},
    // No timeout. The server walks the whole games folder before it answers,
    // and the client's default thirty seconds is nowhere near enough for a
    // real library: the scan carried on and finished perfectly well while the
    // browser reported it as failed, skipped the refresh that would have shown
    // the new games, and invited the operator to press Scan again on top of a
    // walk that was still running.
    timeout: 0,
  });
  return data;
}

/** Convenience for the common "Add game + upload one file" flow (used by themes
 * whose upload dialog only supports a local file). Finds or creates the game in
 * `library` the way every upload dialog does - asking when the title is already
 * there, see `chooseUploadTarget` - then uploads the file to it. Returns the
 * game, or null when the person cancelled and nothing was sent. */
export async function addByUpload(opts: AddByUploadOpts): Promise<any | null> {
  const { library, title, file, os = "windows", fileType = "game", language, version, onProgress } = opts;
  const game = await chooseUploadTarget({ title, library });
  if (!game) return null;
  await uploadFile(game.id, file, { os, fileType, language, version, onProgress });
  return game;
}

/** Bundle a game's loose per-platform files into one archive per platform
 * (GOG, custom, or an admin custom-library game). Runs server-side in the
 * background; follow progress via the `download:packaging` socket event (its
 * `id` is `pkg-g{gameId}-{platform}`). Returns `{ started, platforms }` -
 * `started` is false when there was nothing to bundle. Admin only. */
export interface PackageOpts {
  /** Subset of group labels to bundle (from packable()); omit for every group. */
  groups?: string[];
  /** Delete the loose originals after bundling (overrides the global setting). */
  deleteOriginals?: boolean;
  /** Bundle every file into one combined archive instead of one per group. */
  singleArchive?: boolean;
}
export async function packageGame(gameId: number | string, opts: PackageOpts = {}): Promise<any> {
  const { data } = await client.post(`/library/games/${gameId}/package`, {
    groups: opts.groups,
    delete_originals: opts.deleteOriginals,
    single_archive: opts.singleArchive,
  });
  return data;
}

/** Which of a game's platforms currently have loose files worth bundling (so a
 * theme can show or hide a "Package" button). Returns e.g. ["windows","linux"]. */
export async function packablePlatforms(gameId: number | string): Promise<string[]> {
  const { data } = await client.get(`/library/games/${gameId}/packable`);
  return Array.isArray(data?.platforms) ? data.platforms : [];
}

// ── GOG library ─────────────────────────────────────────────────────────────
// GOG is not folder-scanned like custom libraries; it syncs from the connected
// account and adopts already-downloaded games. Exposed here so every theme
// (built-in and plugin) drives the GOG library toolbar through one API instead
// of hand-rolling the /gog/library/* endpoints.

export interface GogSyncOpts {
  /** Also scrape metadata for newly synced games (default true). */
  autoScrape?: boolean;
  /** Re-scrape metadata even for games that already have it (default false). */
  forceRescrape?: boolean;
}

export interface GogSyncStatus {
  running: boolean;
  /** "adopt" (adding downloaded games) | "scrape" (fetching metadata) | undefined. */
  phase?: string;
  synced: number;
  adopted: number;
  error?: string | null;
}

/** Start a GOG library sync: pull the connected account's library, adopt any
 * already-downloaded games, and (unless disabled) scrape metadata. Runs
 * server-side; poll gogSyncStatus() for progress. Admin only. */
export async function gogSync(opts: GogSyncOpts = {}): Promise<void> {
  const params = new URLSearchParams();
  if (opts.autoScrape === false) params.set("auto_scrape", "false");
  if (opts.forceRescrape) params.set("force_rescrape", "true");
  const qs = params.toString();
  await client.post(`/gog/library/sync${qs ? "?" + qs : ""}`);
}

/** Current state of a running (or the last) GOG sync. Poll while `running`. */
export async function gogSyncStatus(): Promise<GogSyncStatus> {
  const { data } = await client.get("/gog/library/sync/status");
  return data as GogSyncStatus;
}

/** Clear all scraped metadata from the GOG library (keeps the games). Admin only. */
export async function gogClearMetadata(): Promise<void> {
  await client.delete("/gog/library/metadata");
}

// ── Per-game metadata ─────────────────────────────────────────────────────────

/** Which library a game lives in, for the endpoints that differ by source. */
export type GameKind = "games" | "gog" | "rom";

/** Remove all scraped metadata for ONE game (title, source and files are kept),
 * so it can be re-scraped from scratch. The endpoint differs per source, so
 * themes call this instead of hard-coding three routes. Admin only. */
export async function clearGameMetadata(kind: GameKind, id: number | string): Promise<void> {
  if (kind === "gog") {
    await client.delete(`/gog/library/games/${id}/metadata`);
  } else if (kind === "rom") {
    await client.post(`/roms/${id}/clear-metadata`);
  } else {
    await client.post(`/library/games/${id}/clear-metadata`);
  }
}

// >>> EVERY FUNCTION A THEME MAY CALL HAS TO BE LISTED HERE, BY HAND.
// The core screens import this module as a namespace (`import * as libActions`)
// and see every export; a theme only ever sees THIS object, through
// `__GD__.library`. Adding an export and forgetting this list therefore works
// perfectly in Modern and Classic and throws `undefined is not a function` in
// Vapor and NEON HORIZON - which is exactly what happened to `findGameByTitle`
// on 2026-09-10: the owner's upload died in the browser before a single request
// went out, and the tray said only "Upload failed".
const libraryActions = {
  findGameByTitle,
  chooseUploadTarget,
  createGame,
  uploadFile,
  uploadFromUrl,
  addTorrent,
  scan,
  addByUpload,
  package: packageGame,
  packable: packablePlatforms,
  gogSync,
  gogSyncStatus,
  gogClearMetadata,
  clearGameMetadata,
};

export default libraryActions;
