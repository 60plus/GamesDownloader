// Role-aware Dashboard data + actions, exposed to the built-in themes AND
// plugin themes as window.__GD__.dashboard (see main.ts). A theme renders its
// own dashboard by calling these instead of hitting the endpoints directly, the
// same way it uses window.__GD__.library. Payload shapes are intentionally loose
// so new sections can be added server-side without a breaking change here.
//
// Time-scoped reads take an optional window: { days } (1 = 24h, 7, 30) or a
// custom { start, end } (YYYY-MM-DD, end inclusive) which overrides days.

import client from "../services/api/client";
import { useSocketStore } from "../stores/socket";

/** One bucket in an activity series ({date,count}); downloads also carry bytes. */
export interface DaySample { date: string; count: number; bytes?: number }

/** Window selector passed to me()/admin(). */
/** `sections` narrows me() to what you will actually draw - a home rendering the
 * two play strips should pass ["continue_playing","recently_played"] rather than
 * make the server compute the download series and request list for nothing. */
export interface DashboardParams { days?: number; start?: string; end?: string; sections?: string[] }

/** One savestate a ROM holds. `save` is the value the player wants on the URL:
 * /emulation/<slug>/<id>?resume=1&save=<save>.
 *
 * Savestates only. A battery save is never listed here: it restores the memory
 * inside the cartridge rather than the running machine, so it cannot be resumed
 * from, and it is loaded on every launch regardless. `kind` is therefore always
 * "state" - the field stays so a theme written against an earlier GD keeps
 * working. */
export interface RomSaveRef {
  save: string; kind: "state"; slot: number | null;
  screenshot: string | null; updated_at: string | null;
}
// `rating` is the blended 0-5 score (every source the ROM carries), NOT the raw
// roms.rating column - that one is the ScreenScraper note over 20, a 0-1
// fraction that rendered as a bogus "0.8".
// `platform_slug` is routable (/emulation/<slug>/<id>); `platform_fs_slug` is the
// asset key (/platforms/names/<fs_slug>.svg). They differ - snes vs super-nintendo.
// `saves` is only populated on continue_playing, which is the strip that offers them.
// wheel/background/release_year/genres/player_count are here so a theme can draw
// its full ROM tile from this alone, rather than a bare cover beside a rich one.
export interface RecentRom {
  rom_id: number; name: string; cover: string | null; platform: string;
  platform_slug: string; platform_fs_slug?: string; last_played: string | null;
  aspect?: string; rating?: number | null; saves?: RomSaveRef[];
  wheel?: string | null; background?: string | null;
  release_year?: number | null; genres?: string[]; player_count?: string | null;
}

/** Live server vitals (from /proc). Pushed over Socket.IO via onHealth(). */
export interface ServerHealth { cpu_percent: number | null; load1: number | null; mem_used: number; mem_total: number; uptime_seconds: number; cores: number }

export interface UserDashboard {
  downloads: { count: number; games: number; bytes: number; avg_speed_bps: number; series: DaySample[] };
  continue_playing: RecentRom[];
  recently_played: RecentRom[];
  requests: { items: Array<{ title: string; status: string; platform: string; created_at: string | null }>; counts: Record<string, number> };
}

export interface AdminDashboard {
  library: { gog: number; custom: number; rom: number; total: number; size_bytes: number };
  downloads: { count: number; games: number; bytes: number; avg_speed_bps: number; series: DaySample[] };
  users: { total: number; admins: number };
  top_user: { username: string; avatar_path: string | null; downloads: number; bytes: number } | null;
  top_platforms: Array<{ name: string; slug: string; logo: string | null; count: number; bytes: number }>;
  recently_added: Array<{ kind: string; id: number; title: string; cover: string | null; platform_slug: string | null; created_at: string | null }>;
  top_downloaded: Array<{ id: number; title: string; cover: string | null; source: string; downloads: number; bytes: number }>;
  server_health: ServerHealth;
  requests: { counts: Record<string, number>; pending: number };
  security: { banned: Array<{ ip: string; remaining_seconds: number }>; failures: { ips: number; attempts: number } };
  antivirus: {
    enabled: boolean; upload_scan: boolean; download_scan: boolean; running: boolean;
    db_version: string | null; db_date: string | null; quarantined: number;
    recent: Array<{ filename: string; threat: string; file_size: number | null; triggered_by: string | null; created_at: string | null }>;
  };
  email: { total: number; in_range: number; series: DaySample[] };
  disk: Array<{ label: string; path: string; total_bytes: number; free_bytes: number; used_bytes: number }>;
}

/** A ROM savestate or battery save (from /savestates/my). */
export interface GameSaveItem {
  id: number; rom_id: number; file_name: string; file_size_bytes: number;
  emulator_core: string | null; created_at: string | null; download_url: string;
  screenshot_url?: string | null;
  // Savestates sit in slot 1-9 and are replaced in place; null only on legacy
  // rows saved before slots existed. updated_at is when the slot was last
  // written - created_at stays at its first use.
  slot?: number | null; updated_at?: string | null;
  // The save's ROM, so the UI can group by game without a call per row.
  // rom_cover_aspect is the cover's real ratio (SNES boxes are 4/3) - render the
  // frame from it or the art gets cropped. rom_support is the cartridge/disc art
  // (scraped, so often absent); a battery save is that cartridge's SRAM.
  rom_name?: string | null; rom_cover?: string | null; rom_cover_aspect?: string | null;
  rom_support?: string | null;
  platform_name?: string | null; platform_slug?: string | null;
  // The routable slug and the artwork key are different strings for all but
  // twenty of the platforms ("super-nintendo" against "snes"), so a tile that
  // wants console art needs this one.
  platform_fs_slug?: string | null;
}
export interface SavesData {
  states: GameSaveItem[]; saves: GameSaveItem[];
  max_slot?: number; used_bytes: number; limit_bytes: number;
}

/** A game request row (from /requests). */
export interface GameRequestItem {
  id: number; title: string; description: string | null; link: string | null;
  platform: string; platform_slug: string | null; cover_url: string | null;
  status: string; admin_note: string | null; user_id: number; username: string | null;
  vote_count: number; user_voted: boolean; created_at: string | null;
}

/** One active server-side download (GOG job or torrent). */
export interface DownloadQueueItem {
  kind: string; title: string; file: string | null; status: string;
  progress: number; speed_bps: number; downloaded: number; total: number; eta: number | null;
}
/** A file the server is uploading to a user (that user's in-flight download). */
export interface UploadItem { username: string; filename: string; sent: number; total: number; speed_bps: number; progress: number }
/** A library file being seeded to torrent peers. */
export interface SeedItem { filename: string; upload_bps: number; peers: number }
export interface QueueData { downloads: DownloadQueueItem[]; uploads: UploadItem[]; seeding: SeedItem[]; active: number }

function qs(p?: DashboardParams): string {
  if (!p) return "";
  const s = new URLSearchParams();
  if (p.start && p.end) { s.set("start", p.start); s.set("end", p.end); }
  else if (p.days) s.set("days", String(p.days));
  if (p.sections?.length) s.set("sections", p.sections.join(","));
  const str = s.toString();
  return str ? `?${str}` : "";
}

/** The signed-in user's own stats (downloads + requests). Any user may call it. */
export async function me(params?: DashboardParams): Promise<UserDashboard> {
  const { data } = await client.get(`/dashboard/me${qs(params)}`);
  return data as UserDashboard;
}

/** Server-wide operational overview. Admin only (403 otherwise); a theme should
 * only call this when the current user's role is "admin". */
export async function admin(params?: DashboardParams): Promise<AdminDashboard> {
  const { data } = await client.get(`/dashboard/admin${qs(params)}`);
  return data as AdminDashboard;
}

/** Live server-side transfer queue (admin only): incoming downloads (GOG jobs +
 * torrents), outgoing uploads (files being sent to downloading users) and seeds.
 * One-shot HTTP read; for a live feed prefer onQueue() (Socket.IO push). */
export async function queue(): Promise<QueueData> {
  const { data } = await client.get("/dashboard/queue");
  return data as QueueData;
}

/** Live transfer-queue feed over Socket.IO (admin only). The server pushes a
 * fresh QueueData whenever transfers change and stays silent while idle, so this
 * is cheaper than polling and updates in real time. Returns an unsubscribe fn;
 * call it on teardown. A theme should still keep queue() as a fallback for when
 * the socket is unavailable. */
export function onQueue(cb: (q: QueueData) => void): () => void {
  const s = useSocketStore();
  s.connect(); // idempotent - ensures the socket is up
  return s.onDashboardQueue((data) => cb(data as unknown as QueueData));
}

/** Live server-health heartbeat over Socket.IO (admin only): the server pushes
 * ServerHealth (CPU/RAM/uptime/load) every couple of seconds while an admin is
 * watching, and nothing when nobody is. Returns an unsubscribe fn. Cheap - it is
 * just /proc reads, never the full admin payload. Shares one subscription with
 * onQueue(). */
export function onHealth(cb: (h: ServerHealth) => void): () => void {
  const s = useSocketStore();
  s.connect();
  return s.onDashboardHealth((data) => cb(data as unknown as ServerHealth));
}

/** One user's download tally for a game (from gameDownloaders). */
export interface Downloader { username: string; count: number; bytes: number; last: string | null }
/** Admin: which users downloaded a given library game (drill-down). */
export async function gameDownloaders(gameId: number): Promise<{ title: string | null; downloaders: Downloader[] }> {
  const { data } = await client.get(`/dashboard/game/${gameId}/downloaders`);
  return data as { title: string | null; downloaders: Downloader[] };
}

/** The signed-in user's ROM saves + savestates + quota (any user). */
export async function saves(): Promise<SavesData> {
  const { data } = await client.get("/savestates/my");
  return data as SavesData;
}
export async function deleteSaveState(id: number): Promise<void> { await client.delete(`/savestates/states/${id}`); }
export async function deleteBatterySave(id: number): Promise<void> { await client.delete(`/savestates/saves/${id}`); }

/** Fetch `url` through the API client and hand the bytes to the browser as a
 * download. A plain <a href> cannot be used: the API authenticates on the
 * Authorization header, which a link does not send, so it would 401. */
async function _download(url: string, fallbackName: string, params?: object): Promise<void> {
  const res = await client.get(url, { responseType: "blob", params, timeout: 0 });
  const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: "application/zip" });
  const cd = (res.headers as Record<string, string>)?.["content-disposition"] || "";
  const m = /filename="?([^"]+)"?/i.exec(cd);
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objUrl);
}

/** Download one savestate as an archive: the save, its screenshot and a manifest
 * saying which game and slot it belongs to, so an import can put it back. */
export async function exportSaveState(id: number): Promise<void> {
  await _download(`/savestates/states/${id}/export`, "save.zip");
}
/** Download one battery save as an archive (see exportSaveState). */
export async function exportBatterySave(id: number): Promise<void> {
  await _download(`/savestates/saves/${id}/export`, "battery.zip");
}
/** Download every save this user holds - or one game's, with `romId`. The backup
 * half of the reinstall round-trip. */
export async function exportSaves(romId?: number): Promise<void> {
  await _download("/savestates/export", "gd-saves.zip",
                  romId != null ? { rom_id: romId } : undefined);
}

/** What became of one entry in an import. `no_rom`: the archive names a game
 * this server does not have. `need_target`: a bare .state/.srm arrived without
 * being told which game it belongs to. */
export interface ImportResult {
  name: string; slot?: number | null; kind?: string;
  status: "imported" | "replaced" | "no_rom" | "need_target" | "error";
  detail?: string;
}
/** Restore saves. An archive routes itself from its manifest; a bare .state/.srm
 * needs `target` to say which ROM (and slot) it belongs to. */
export async function importSaves(
  files: File[], target?: { romId: number; slot?: number },
): Promise<{ results: ImportResult[]; imported: number }> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  if (target) {
    fd.append("rom_id", String(target.romId));
    if (target.slot != null) fd.append("slot", String(target.slot));
  }
  const { data } = await client.post("/savestates/import", fd, { timeout: 0 });
  return data as { results: ImportResult[]; imported: number };
}

/** All game requests (any user with request-read). */
export async function requests(): Promise<GameRequestItem[]> {
  const { data } = await client.get("/requests");
  return Array.isArray(data) ? data : [];
}
/** Admin: change a request's status and/or admin note. Notifies the requester. */
export async function setRequestStatus(id: number, body: { status?: string; admin_note?: string }): Promise<void> {
  await client.patch(`/requests/${id}`, body);
}
/** Admin: delete a request. */
export async function deleteRequest(id: number): Promise<void> { await client.delete(`/requests/${id}`); }

const dashboardActions = {
  me, admin, queue, onQueue, onHealth, gameDownloaders, saves, deleteSaveState, deleteBatterySave,
  exportSaveState, exportBatterySave, exportSaves, importSaves,
  requests, setRequestStatus, deleteRequest,
};

export default dashboardActions;
