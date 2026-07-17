<!--
  DashDownloadQueue - live view of the server's in-flight transfers, admin only.
  Self-contained: polls window.__GD__.dashboard.queue() (fast while active, slow
  when idle) and renders up to three sections:
    * Downloads (server pulling in): GOG jobs + torrents, with progress + ETA.
    * Uploads (server -> user): files being sent to users who are downloading,
      attributed by username - "who is downloading right now".
    * Seeding (server -> peers): library files seeded over torrent, upload rate.
  Renders nothing when everything is idle, so it stays out of the way.
-->
<template>
  <div v-if="hasAny" class="ddq glass">
    <!-- Downloads (incoming) -->
    <template v-if="downloads.length">
      <div class="ddq-h"><i class="mdi mdi-progress-download ddq-h-ico"></i>{{ t("dashboard.download_queue", "Downloads in progress") }}<span class="ddq-badge">{{ downloads.length }}</span></div>
      <div v-for="(d, i) in downloads" :key="'d' + i" class="ddq-row">
        <i :class="['mdi', d.kind === 'torrent' ? 'mdi-magnet' : 'mdi-cloud-download-outline', 'ddq-kind', d.kind]"></i>
        <div class="ddq-info">
          <div class="ddq-title">{{ d.title }}<span v-if="d.file" class="dash-mut"> · {{ d.file }}</span></div>
          <div class="ddq-track"><span class="ddq-fill" :class="{ paused: d.status === 'paused' }" :style="{ width: Math.min(100, d.progress) + '%' }"></span></div>
          <div class="ddq-meta">
            <b>{{ d.progress }}%</b>
            <span v-if="d.total" class="dash-mut">{{ fmtBytes(d.downloaded) }} / {{ fmtBytes(d.total) }}</span>
            <span v-if="d.speed_bps" class="dash-mut">↓ {{ fmtBytes(d.speed_bps) }}/s</span>
            <span v-if="d.eta" class="dash-mut">ETA {{ fmtEta(d.eta) }}</span>
            <span v-if="d.status === 'paused'" class="ddq-tag">{{ t("dashboard.paused", "paused") }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Uploads (server -> user) -->
    <template v-if="uploads.length">
      <div class="ddq-h ddq-h--up"><i class="mdi mdi-account-arrow-up ddq-h-ico up"></i>{{ t("dashboard.uploads", "Uploads") }}<span class="ddq-badge up">{{ uploads.length }}</span></div>
      <div v-for="(u, i) in uploads" :key="'u' + i" class="ddq-row">
        <i class="mdi mdi-account-arrow-up ddq-kind up"></i>
        <div class="ddq-info">
          <div class="ddq-title"><b class="ddq-user">{{ u.username }}</b><span class="dash-mut"> · {{ u.filename }}</span></div>
          <div class="ddq-track"><span class="ddq-fill up" :style="{ width: Math.min(100, u.progress) + '%' }"></span></div>
          <div class="ddq-meta">
            <b>{{ u.progress }}%</b>
            <span v-if="u.total" class="dash-mut">{{ fmtBytes(u.sent) }} / {{ fmtBytes(u.total) }}</span>
            <span v-if="u.speed_bps" class="dash-mut">↑ {{ fmtBytes(u.speed_bps) }}/s</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Seeding (server -> peers) -->
    <template v-if="seeding.length">
      <div class="ddq-h ddq-h--up"><i class="mdi mdi-seed-outline ddq-h-ico seed"></i>{{ t("dashboard.seeding", "Seeding") }}<span class="ddq-badge seed">{{ seeding.length }}</span></div>
      <div v-for="(s, i) in seeding" :key="'s' + i" class="ddq-row">
        <i class="mdi mdi-magnet-on ddq-kind seed"></i>
        <div class="ddq-info">
          <div class="ddq-title">{{ s.filename }}</div>
          <div class="ddq-meta">
            <span class="dash-mut">↑ {{ fmtBytes(s.upload_bps) }}/s</span>
            <span class="dash-mut">{{ s.peers }} {{ t("dashboard.peers", "peers") }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useI18n } from "@/i18n";
import { useSocketStore } from "@/stores/socket";
import dashboardActions, { type DownloadQueueItem, type UploadItem, type SeedItem } from "@/lib/dashboardActions";

const { t } = useI18n();
const socketStore = useSocketStore();
const downloads = ref<DownloadQueueItem[]>([]);
const uploads = ref<UploadItem[]>([]);
const seeding = ref<SeedItem[]>([]);
const hasAny = computed(() => downloads.value.length || uploads.value.length || seeding.value.length);
let timer: ReturnType<typeof setTimeout> | undefined;
let stopped = false;
let offQueue: (() => void) | undefined;   // Socket.IO live-feed unsubscribe

function apply(q: { downloads?: DownloadQueueItem[]; uploads?: UploadItem[]; seeding?: SeedItem[] }): void {
  downloads.value = q.downloads || [];
  uploads.value = q.uploads || [];
  seeding.value = q.seeding || [];
}

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + u[i];
}
function fmtEta(sec: number): string {
  if (!sec || sec < 0) return "-";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

// Live feed = Socket.IO push (see dashboardActions.onQueue): a connected socket
// gets a fresh snapshot on subscribe and a push on every change, and NOTHING at
// rest. So the timer below HTTP-polls only while the socket is actually down;
// once it is connected we trust the push and generate no idle traffic.
async function tick(): Promise<void> {
  if (!socketStore.socket?.connected) {
    try {
      const q = await dashboardActions.queue();
      if (!stopped) apply(q);   // ignore a poll that resolved after teardown
    } catch { /* keep last */ }
  }
  if (stopped) return;
  timer = setTimeout(tick, hasAny.value ? 3000 : 6000);
}

onMounted(() => {
  offQueue = dashboardActions.onQueue(apply); // real-time push while connected
  tick();                                     // fallback poll only while the socket is down
});
onUnmounted(() => { stopped = true; if (timer) clearTimeout(timer); offQueue?.(); });
</script>

<style scoped>
.ddq { border-radius: 12px; padding: 14px 16px; margin-top: 14px; }
.ddq-h { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; margin-bottom: 10px; }
.ddq-h--up { margin-top: 14px; }
.ddq-h-ico { font-size: 26px; opacity: 0.9; color: var(--accent, #38d3db); }
.ddq-h-ico.up { color: #4ade80; }
.ddq-h-ico.seed { color: #a78bfa; }
.ddq-badge { margin-left: 4px; font-size: 10.5px; padding: 1px 8px; border-radius: 20px; background: color-mix(in srgb, var(--accent, #38d3db) 20%, transparent); color: var(--accent, #38d3db); font-weight: 700; }
.ddq-badge.up { background: color-mix(in srgb, #4ade80 20%, transparent); color: #4ade80; }
.ddq-badge.seed { background: color-mix(in srgb, #a78bfa 22%, transparent); color: #a78bfa; }
.ddq-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
.ddq-row:last-child { border-bottom: 0; }
.ddq-kind { font-size: 20px; flex: 0 0 auto; margin-top: 2px; opacity: 0.85; }
.ddq-kind.torrent { color: #a78bfa; }
.ddq-kind.gog { color: var(--accent, #38d3db); }
.ddq-kind.up { color: #4ade80; }
.ddq-kind.seed { color: #a78bfa; }
.ddq-info { flex: 1; min-width: 0; }
.ddq-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 5px; }
.ddq-user { color: #4ade80; }
.ddq-track { height: 7px; border-radius: 6px; background: rgba(255,255,255,0.08); overflow: hidden; }
.ddq-fill { display: block; height: 100%; border-radius: 6px; background: var(--accent, #38d3db); transition: width 0.6s ease; }
.ddq-fill.up { background: #4ade80; }
.ddq-fill.paused { background: #fbbf24; }
.ddq-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11.5px; margin-top: 5px; font-variant-numeric: tabular-nums; }
.ddq-tag { font-size: 10px; padding: 1px 7px; border-radius: 20px; background: color-mix(in srgb, #fbbf24 22%, transparent); color: #fbbf24; font-weight: 600; }
.dash-mut { opacity: 0.55; }
</style>
