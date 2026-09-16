/**
 * Watching a ROM scan, and asking it to stop.
 *
 * Three views show the same scan - the Retro home, a platform's library, and
 * the Classic layout's sidebar - and each of them used to poll a boolean every
 * two seconds. That gave a progress bar that says "yes" for as long as the scan
 * runs, three times over, with no way to change your mind.
 *
 * One place instead. It subscribes to the socket, and it ALSO asks the server
 * once on mount: a view opened halfway through a scan has missed every event so
 * far, and that one call is how it catches up. Both carry the same shape, so
 * there is no second code path for the late arrival.
 */
import { ref, computed, onMounted, onUnmounted, watch } from "vue";

import client from "@/services/api/client";
import { useAuthStore } from "@/stores/auth";
import { useSocketStore } from "@/stores/socket";

export interface ScanState {
  running: boolean;
  cancelling: boolean;
  platform: string | null;
  platform_index: number;
  platform_total: number;
  files_done: number;
  files_total: number;
  current: string | null;
}

const IDLE: ScanState = {
  running: false, cancelling: false, platform: null,
  platform_index: 0, platform_total: 0,
  files_done: 0, files_total: 0, current: null,
};

/** What the indicator is saying, as a sequence rather than an on/off.
 *
 *  A scan of a small library used to make the whole indicator flash and vanish,
 *  and the reason was not that the scan is fast: the indicator only appeared
 *  when the FIRST progress event arrived from the server. "starting" shows the
 *  moment the button is pressed, so there is no gap to flash through, and it
 *  costs the scan nothing.
 *
 *  "done" is the other half. Holding a full progress bar for a second would be
 *  pretending something is still happening; saying how many ROMs were found is
 *  information, and the completion event already carries the numbers. */
export type ScanPhase = "idle" | "starting" | "scanning" | "done";

export interface ScanSummary {
  cancelled: boolean;
  roms_found: number;
  roms_new: number;
  roms_updated: number;
  /** Why it ended without walking anything. Today: "path_missing", an
   *  unmounted drive or a typo in Settings > ROMs. A scan that stops for a
   *  reason has to say the reason; this one used to say nothing at all and
   *  leave the bar up for the life of the page. */
  error?: string;
  /** Set when the watchdog ended this rather than the completion event. The
   *  status call carries a position, not a result - no counts, and no way to
   *  tell a scan that finished from one somebody stopped - so the numbers below
   *  are not known. They used to be filled in with zeros and rendered as
   *  "Scan finished. ROMs found: 0" after a scan that added hundreds. */
  unknown?: boolean;
}

/** How long the result stays up before the indicator lets go. Long enough to
 *  read a short sentence, short enough not to sit there while somebody works. */
const RESULT_LINGER_MS = 5000;

/** A scan that ends while the socket is down would otherwise never end here.
 *
 *  The completion event is the only thing that leaves the running phases, and
 *  it is genuinely droppable: any 401 makes the client rebuild the socket from
 *  scratch, and anything emitted during that gap is gone. The result was a
 *  progress line frozen on one platform for the rest of the session, a sync
 *  spinner that never stopped, and no way to start another scan without
 *  reloading the page.
 *
 *  So the status call is not only for catching up on mount any more: while
 *  something is on screen, it is asked again on this interval. It is one small
 *  request, only while a scan is showing, and only for the accounts that get
 *  the events in the first place. The code this replaced polled every two
 *  seconds unconditionally. */
const WATCHDOG_MS = 10000;

export function useRomScan(onFinished?: () => void) {
  const sockets = useSocketStore();
  const auth = useAuthStore();
  const state = ref<ScanState>({ ...IDLE });
  const stopping = ref(false);
  const phase = ref<ScanPhase>("idle");
  const summary = ref<ScanSummary | null>(null);
  let lingerTimer: ReturnType<typeof setTimeout> | null = null;
  let watchdog: ReturnType<typeof setInterval> | null = null;
  let stopWatching: (() => void) | null = null;

  // Two different questions, and they have different answers.
  //
  // WATCHING is for the accounts that put things in the library. An uploader
  // cannot start a scan, but an upload starts one by itself, and watching it is
  // the only way to know when the file they just added has appeared. The
  // progress events are sent to exactly these two rooms (_SCAN_WATCHERS in the
  // scanner) and the status call admits exactly these two, so all three agree:
  // anybody else drew a bar from the status call and then froze on whatever
  // platform it first saw, because no event would ever reach them.
  //
  // STOPPING is an administrator's - PLATFORMS_WRITE, like starting one. So an
  // uploader watches without a button, rather than with one that answers
  // "Missing scopes" for the rest of the session.
  //
  // Asked once, here, rather than in each of the three views that draw this.
  const canWatchScan = computed(() => {
    const u = auth.user as { role?: string } | null;
    return auth.isAdmin || u?.role === "uploader";
  });
  const canStopScan = computed(() => auth.isAdmin);
  const allowed = canWatchScan;

  function clearLinger() {
    if (lingerTimer) clearTimeout(lingerTimer);
    lingerTimer = null;
  }

  function stopWatchdog() {
    if (watchdog) clearInterval(watchdog);
    watchdog = null;
  }

  /** True while there is anything to show, which outlasts the scan itself. */
  const visible = computed(() => phase.value !== "idle");

  const running = computed(() => state.value.running);

  /** 0-100 across the whole library, or null when there is nothing to divide.
   *
   *  Platforms carry the coarse position and files the fine one, because the
   *  total number of files is not known until each directory is listed - a
   *  count that needed the whole tree walked first would mean waiting for the
   *  scan to finish before the bar could start. */
  const percent = computed(() => {
    const s = state.value;
    if (!s.running || !s.platform_total) return null;
    const within = s.files_total ? s.files_done / s.files_total : 0;
    return Math.min(100, Math.round(
      ((s.platform_index - 1 + within) / s.platform_total) * 100));
  });

  async function refresh() {
    if (!allowed.value) return;
    try {
      const { data } = await client.get("/roms/scan/status");
      state.value = { ...IDLE, ...(data || {}) };
      // Arriving mid-scan starts at "scanning" rather than at "starting":
      // nobody here pressed anything, the scan is already under way.
      // From "starting" as well as from "idle". The card that pressed Scan is
      // already on "starting", so where the socket never delivers - the Classic
      // layout, a connection being rebuilt - it stayed there for the whole run:
      // the watchdog kept fetching the platform and the counters every ten
      // seconds and the template never drew them, because the "starting" branch
      // has no room for them and the Stop button lives in the scanning one.
      if (state.value.running
          && (phase.value === "idle" || phase.value === "starting")) {
        phase.value = state.value.platform ? "scanning" : "starting";
      }
      // The server says no scan is running while this still thinks one is: the
      // completion event was emitted into a gap, most likely while the socket
      // was being rebuilt after a token refresh. Finish the way the event
      // would have, so the line clears, the caller's reload runs and the sync
      // spinner it owns is released.
      if (!state.value.running && (phase.value === "scanning" || phase.value === "starting")) {
        // Marked unknown, not filled with zeros. /roms/scan/status answers
        // where a scan IS, not what it did: no counts, and no way to tell one
        // that finished from one somebody stopped. Reporting zeros here told
        // people "ROMs found: 0" after a scan that had added hundreds.
        finish({ cancelled: false, roms_found: 0, roms_new: 0, roms_updated: 0,
                 unknown: true });
      }
      // Something is running and this view has only just caught up with it, so
      // arm the watchdog here too. It used to be armed by `start()` and by the
      // first progress event only - and a page opened mid-scan whose socket is
      // being rebuilt gets neither, which is exactly the case the watchdog was
      // written for.
      if (state.value.running) startWatchdog();
    } catch (e: unknown) {
      // A refusal is not a dropped connection. Losing the network must leave
      // the bar alone - a failed catch-up must not report an idle scanner while
      // one is running - but a 403 says this account may not follow the scan at
      // all, and swallowing it drew a bar that could never be filled and hid
      // the reason. It happens: the role puts an account in the progress room
      // while a revoked upload permission closes the status call.
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        // The bar goes, and the subscription stays.
        //
        // Dropping it as well made one refusal permanent: nothing subscribes
        // again for the life of the component, and in the Classic layout that
        // component is mounted for the whole session. An account whose upload
        // permission was taken away in the middle of a scan - or one that fell
        // off an address allow-list - had no scan indicator afterwards, not
        // even once the permission came back.
        //
        // Keeping it costs nothing. Who receives these events is decided by the
        // server, from the room the socket is in, and the socket is rebuilt on
        // any change to what this account may do.
        stopWatchdog();
        clearLinger();
        phase.value = "idle";
        summary.value = null;
        state.value = { ...IDLE };
      }
    }
  }

  /** The one way out of the running phases, used by the event and the watchdog. */
  function finish(result: ScanSummary) {
    state.value = { ...IDLE };
    summary.value = result;
    phase.value = "done";
    stopWatchdog();
    clearLinger();
    lingerTimer = setTimeout(() => {
      // Only the result this timer was armed for. Starting another scan inside
      // the five seconds used to leave the old timer running, and it cleared a
      // bar belonging to a scan that was under way.
      if (phase.value !== "done") { lingerTimer = null; return; }
      phase.value = "idle";
      summary.value = null;
      lingerTimer = null;
    }, RESULT_LINGER_MS);
    onFinished?.();
  }

  function startWatchdog() {
    stopWatchdog();
    if (!allowed.value) return;
    watchdog = setInterval(() => {
      if (phase.value === "scanning" || phase.value === "starting") refresh();
      else stopWatchdog();
    }, WATCHDOG_MS);
  }

  async function start() {
    // Before the request, not after it. This is the gap the old indicator
    // flashed through.
    clearLinger();
    summary.value = null;
    phase.value = "starting";
    try {
      await client.post("/roms/scan");
      startWatchdog();
      await refresh();
    } catch (e) {
      phase.value = "idle";
      stopWatchdog();
      throw e;
    }
  }

  async function stop() {
    stopping.value = true;
    try {
      await client.post("/roms/scan/stop");
      state.value = { ...state.value, cancelling: true };
    } finally {
      stopping.value = false;
    }
  }

  let off: (() => void) | null = null;

  function listen() {
    if (off || !allowed.value) return;
    off = sockets.onRomScan((kind, data) => {
      if (kind === "complete") {
        const s = data as Record<string, unknown>;
        finish({
          cancelled: Boolean(s.cancelled),
          roms_found: Number(s.roms_found ?? 0),
          roms_new: Number(s.roms_new ?? 0),
          roms_updated: Number(s.roms_updated ?? 0),
          error: typeof s.error === "string" ? s.error : undefined,
        });
        return;
      }
      state.value = { ...IDLE, ...(data as unknown as ScanState) };
      if (state.value.running) startWatchdog();
      // "scanning" once there is a platform to name, not merely once the first
      // event lands. The first event carries no platform and no totals, so
      // switching on it made "starting" last a few milliseconds and the
      // sequence read as two steps. Measured: the walk spends that time
      // listing the folders that hold nothing, which is exactly what starting
      // up is.
      if (state.value.running && state.value.platform) phase.value = "scanning";
    });
    refresh();
  }

  onMounted(() => {
    // `allowed` reads the account, and the account arrives from GET /users/me a
    // round trip after mount - the layout mounts from cache and usually wins
    // that race. Subscribing once at mount therefore did nothing at all after a
    // page refresh: no progress events, so the bar sat on "Starting the scan"
    // for the whole run and the Stop button, which lives in the scanning
    // branch, never appeared. Watched instead, so it attaches the moment the
    // account is known, and once only.
    listen();
    stopWatching = watch(allowed, (may) => { if (may) listen(); });
  });

  onUnmounted(() => {
    clearLinger(); stopWatchdog(); stopWatching?.(); off?.(); off = null;
  });

  return { state, running, percent, stopping, phase, summary, visible,
           canWatch: canWatchScan, canStop: canStopScan,
           start, stop, refresh };
}
