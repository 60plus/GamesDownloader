import { defineStore } from "pinia";
import { ref } from "vue";
import { io, type Socket } from "socket.io-client";

const TOKEN_KEY = "gd3_token";

export const useSocketStore = defineStore("socket", () => {
  const socket = ref<Socket | null>(null);
  const syncProgress = ref({ current: 0, total: 0, progress: 0, message: "" });
  const scrapeProgress = ref({ current: 0, total: 0, progress: 0, message: "" });
  const downloadProgress = ref({ current: 0, total: 0, progress: 0, message: "" });
  const downloadJobUpdate = ref<Record<string, unknown> | null>(null);
  const downloadJobCallbacks: Array<(data: Record<string, unknown>) => void> = [];
  const packagingCallbacks: Array<(data: Record<string, unknown>) => void> = [];
  const chdCallbacks: Array<(data: Record<string, unknown>) => void> = [];
  const urlUploadCallbacks: Array<(kind: string, data: Record<string, unknown>) => void> = [];
  const romSourceCallbacks: Array<(kind: string, data: Record<string, unknown>) => void> = [];
  const dashboardQueueCallbacks: Array<(data: Record<string, unknown>) => void> = [];
  const dashboardHealthCallbacks: Array<(data: Record<string, unknown>) => void> = [];
  let liveSubs = 0; // dashboard-live consumers sharing this per-tab socket

  function onDownloadJob(cb: (data: Record<string, unknown>) => void) {
    downloadJobCallbacks.push(cb);
    return () => { const i = downloadJobCallbacks.indexOf(cb); if (i >= 0) downloadJobCallbacks.splice(i, 1) }
  }

  // A CHD conversion reports over chd:convert, one payload carrying the whole
  // job: status, overall percent and how many discs of the set are done. Same
  // shape as onPackaging because it is the same kind of thing - long local
  // work with a progress bar, not a transfer.
  function onChdConvert(cb: (data: Record<string, unknown>) => void) {
    chdCallbacks.push(cb);
    return () => { const i = chdCallbacks.indexOf(cb); if (i >= 0) chdCallbacks.splice(i, 1) }
  }

  function onPackaging(cb: (data: Record<string, unknown>) => void) {
    packagingCallbacks.push(cb);
    return () => { const i = packagingCallbacks.indexOf(cb); if (i >= 0) packagingCallbacks.splice(i, 1) }
  }

  // A URL/catalogue download reports over upload:url_progress|complete|error.
  // The callback gets the kind ("progress"|"complete"|"error") plus the payload,
  // so one subscription follows a job from start to finish (used by the download
  // tray and the storefront detail page). Registered on the store so it survives
  // token-refresh reconnects, like onDownloadJob/onPackaging.
  function onUrlUpload(cb: (kind: string, data: Record<string, unknown>) => void) {
    urlUploadCallbacks.push(cb);
    return () => { const i = urlUploadCallbacks.indexOf(cb); if (i >= 0) urlUploadCallbacks.splice(i, 1) }
  }

  // A ROM-source download (RomDownloader) reports over
  // romsource:download_progress|complete|error. Same shape as onUrlUpload: the
  // callback gets the kind plus the payload (keyed on the job id, with entry_id
  // and fs_slug), so the ROM list follows a row and the download tray shows it.
  function onRomSource(cb: (kind: string, data: Record<string, unknown>) => void) {
    romSourceCallbacks.push(cb);
    return () => { const i = romSourceCallbacks.indexOf(cb); if (i >= 0) romSourceCallbacks.splice(i, 1) }
  }

  // One "dashboard live" subscription feeds both the transfer queue and the
  // server-health heartbeat. It is reference-counted across every onDashboard*
  // consumer (the store socket is a per-tab singleton), so the server joins the
  // room on the FIRST consumer and leaves on the LAST - and the broadcaster loop
  // stays completely idle while nobody is watching.
  function _subscribeLive() { if (liveSubs++ === 0) socket.value?.emit("dashboard:subscribe"); }
  function _unsubscribeLive() { if (liveSubs > 0 && --liveSubs === 0) socket.value?.emit("dashboard:unsubscribe"); }

  function onDashboardQueue(cb: (data: Record<string, unknown>) => void) {
    dashboardQueueCallbacks.push(cb);
    _subscribeLive();
    return () => { const i = dashboardQueueCallbacks.indexOf(cb); if (i >= 0) dashboardQueueCallbacks.splice(i, 1); _unsubscribeLive(); };
  }
  function onDashboardHealth(cb: (data: Record<string, unknown>) => void) {
    dashboardHealthCallbacks.push(cb);
    _subscribeLive();
    return () => { const i = dashboardHealthCallbacks.indexOf(cb); if (i >= 0) dashboardHealthCallbacks.splice(i, 1); _unsubscribeLive(); };
  }

  function connect() {
    // Guard on existence, not connected-state: socket.io-client auto-reconnects
    // the existing instance, so calling connect() again mid-handshake must NOT
    // spin up a second orphaned socket (with a duplicate listener set).
    if (socket.value) return;

    const token = localStorage.getItem(TOKEN_KEY) || "";
    if (!token) {
      // No token => server will refuse the handshake. Skip connecting.
      return;
    }

    socket.value = io({
      path: "/socket.io",
      transports: ["websocket"],
      auth: { token },
    });

    socket.value.on("connect_error", (err) => {
      // Common case: token expired. Surface to console; auth refresh will reconnect.
      // eslint-disable-next-line no-console
      console.warn("Socket.IO connect_error:", err?.message || err);
    });

    socket.value.on("connect", () => {
      // A (re)connect gets a fresh sid, so re-assert the dashboard-live
      // subscription if anyone is still watching (survives token-refresh reconnects).
      if (liveSubs > 0) socket.value?.emit("dashboard:subscribe");
    });

    socket.value.on("sync_progress", (data) => {
      syncProgress.value = data;
    });
    socket.value.on("scrape_progress", (data) => {
      scrapeProgress.value = data;
    });
    socket.value.on("download_progress", (data) => {
      downloadProgress.value = data;
    });
    socket.value.on("download:progress", (data) => {
      downloadJobUpdate.value = data;
      downloadJobCallbacks.forEach(cb => cb(data));
    });
    socket.value.on("download:packaging", (data) => {
      packagingCallbacks.forEach(cb => cb(data));
    });
    socket.value.on("chd:convert", (data) => {
      chdCallbacks.forEach(cb => cb(data));
    });
    socket.value.on("upload:url_progress", (data) => {
      urlUploadCallbacks.forEach(cb => cb("progress", data));
    });
    socket.value.on("upload:url_complete", (data) => {
      urlUploadCallbacks.forEach(cb => cb("complete", data));
    });
    socket.value.on("upload:url_error", (data) => {
      urlUploadCallbacks.forEach(cb => cb("error", data));
    });
    socket.value.on("romsource:download_progress", (data) => {
      romSourceCallbacks.forEach(cb => cb("progress", data));
    });
    socket.value.on("romsource:download_complete", (data) => {
      romSourceCallbacks.forEach(cb => cb("complete", data));
    });
    socket.value.on("romsource:download_error", (data) => {
      romSourceCallbacks.forEach(cb => cb("error", data));
    });
    // Paused, resumed, cancelled: a state change with no bytes attached.
    socket.value.on("romsource:download_state", (data) => {
      romSourceCallbacks.forEach(cb => cb("state", data));
    });
    socket.value.on("dashboard:queue", (data) => {
      dashboardQueueCallbacks.forEach(cb => cb(data));
    });
    socket.value.on("dashboard:health", (data) => {
      dashboardHealthCallbacks.forEach(cb => cb(data));
    });
  }

  function reconnectWithFreshToken() {
    if (socket.value) {
      socket.value.disconnect();
      socket.value = null;
    }
    connect();
  }

  function disconnect() {
    socket.value?.disconnect();
    socket.value = null;
    // The refcount has to go with the socket. A leftover count made the next
    // connect() re-assert dashboard:subscribe for consumers that no longer
    // exist - a phantom subscription surviving a logout.
    liveSubs = 0;
  }

  return { socket, syncProgress, scrapeProgress, downloadProgress, downloadJobUpdate, onDownloadJob, onPackaging, onChdConvert, onUrlUpload, onRomSource, onDashboardQueue, onDashboardHealth, connect, disconnect, reconnectWithFreshToken };
});
