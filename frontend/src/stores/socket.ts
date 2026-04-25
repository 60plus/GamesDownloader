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

  function onDownloadJob(cb: (data: Record<string, unknown>) => void) {
    downloadJobCallbacks.push(cb);
    return () => { const i = downloadJobCallbacks.indexOf(cb); if (i >= 0) downloadJobCallbacks.splice(i, 1) }
  }

  function connect() {
    if (socket.value?.connected) return;

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
  }

  return { socket, syncProgress, scrapeProgress, downloadProgress, downloadJobUpdate, onDownloadJob, connect, disconnect, reconnectWithFreshToken };
});
