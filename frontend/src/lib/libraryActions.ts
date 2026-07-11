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

/** Create a LibraryGame. When `library` names a folder-backed custom library
 * the server adds membership and keeps the game out of the default Games
 * library. Returns the created game (has `.id`). */
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
  });
  return data;
}

/** Convenience for the common "Add game + upload one file" flow (used by themes
 * whose upload dialog only supports a local file). Creates the game in `library`
 * then uploads the file to it. Returns the created game. */
export async function addByUpload(opts: AddByUploadOpts): Promise<any> {
  const { library, title, file, os = "windows", fileType = "game", language, version, onProgress } = opts;
  const game = await createGame({ title, library });
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

const libraryActions = {
  createGame,
  uploadFile,
  uploadFromUrl,
  addTorrent,
  scan,
  addByUpload,
  package: packageGame,
  packable: packablePlatforms,
};

export default libraryActions;
