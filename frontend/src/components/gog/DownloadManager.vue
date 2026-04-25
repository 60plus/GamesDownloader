<template>
  <!-- Fixed bottom-right download tray - works in both Modern and Classic themes -->
  <div class="dm-tray" :class="{ 'dm-tray--open': expanded, 'dm-tray--has-active': hasActive, 'dm-tray--inline': inline }">

    <!-- ── Header bar (always visible when there are jobs) ───────────────── -->
    <div v-if="jobs.length > 0" class="dm-header" @click="expanded = !expanded">
      <div class="dm-header-left">
        <!-- Animated icon when downloading -->
        <div class="dm-status-dot" :class="dotClass" />
        <span class="dm-header-title">Downloads</span>
        <span class="dm-badge">{{ jobs.length }}</span>
      </div>

      <!-- Active download quick-info (collapsed view) -->
      <div v-if="!expanded && activeJob" class="dm-header-quick">
        <span class="dm-quick-name">{{ activeJob.file_name }}</span>
        <span class="dm-quick-pct">{{ activeJob.progress_pct.toFixed(0) }}%</span>
      </div>

      <button class="dm-toggle" :title="expanded ? 'Collapse' : 'Expand'">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline :points="expanded ? '18 15 12 9 6 15' : '6 9 12 15 18 9'" />
        </svg>
      </button>
    </div>

    <!-- ── Expanded job list ───────────────────────────────────────────────── -->
    <Transition name="dm-slide">
      <div v-if="expanded && jobs.length > 0" class="dm-body">

        <div v-for="job in jobs" :key="job.id" class="dm-job" :class="`dm-job--${job.status}`">

          <!-- Job header row -->
          <div class="dm-job-head">
            <div class="dm-job-info">
              <span class="dm-job-title">{{ job.game_title }}</span>
              <span class="dm-job-sep">·</span>
              <span class="dm-job-file">{{ job.file_name }}</span>
            </div>
            <div class="dm-job-actions">
              <!-- Pause button (only when downloading) -->
              <button
                v-if="job.status === 'downloading'"
                class="dm-action-btn"
                title="Pause"
                @click.stop="pauseJob(job.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
                </svg>
              </button>
              <!-- Resume button (only when paused) -->
              <button
                v-else-if="job.status === 'paused'"
                class="dm-action-btn dm-action-btn--resume"
                title="Resume"
                @click.stop="resumeJob(job.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5,3 19,12 5,21"/>
                </svg>
              </button>
              <!-- Cancel button (active/queued/paused) -->
              <button
                v-if="['downloading', 'queued', 'paused'].includes(job.status)"
                class="dm-action-btn dm-action-btn--cancel"
                title="Cancel"
                @click.stop="cancelJob(job.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
              <!-- Delete button (finished jobs) -->
              <button
                v-if="['completed', 'failed', 'cancelled'].includes(job.status)"
                class="dm-action-btn dm-action-btn--cancel"
                title="Remove"
                @click.stop="deleteJob(job.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- Progress bar -->
          <div class="dm-progress-track">
            <div
              class="dm-progress-fill"
              :class="`dm-progress-fill--${job.status}`"
              :style="{ width: progressWidth(job) }"
            />
          </div>

          <!-- Stats row -->
          <div class="dm-job-stats">
            <span class="dm-stat dm-stat--status" :class="`dm-status--${job.status}`">
              {{ statusLabel(job.status) }}
            </span>
            <template v-if="['downloading', 'paused'].includes(job.status)">
              <span class="dm-stat">
                {{ formatBytes(job.downloaded_size) }}
                <template v-if="job.total_size"> / {{ formatBytes(job.total_size) }}</template>
              </span>
              <template v-if="job.status === 'downloading' && job.speed_bps > 0">
                <span class="dm-stat dm-stat--speed">{{ formatSpeed(job.speed_bps) }}</span>
                <span v-if="job.total_size && job.downloaded_size" class="dm-stat dm-stat--eta">
                  {{ formatEta(job) }}
                </span>
              </template>
            </template>
            <span v-if="job.status === 'completed'" class="dm-stat">
              {{ formatBytes(job.downloaded_size) }}
            </span>
            <!-- Checksum status (only for completed jobs with verify enabled) -->
            <span
              v-if="job.status === 'completed' && job.verify_checksum"
              class="dm-stat dm-stat--checksum"
              :class="checksumClass(job.checksum_status)"
              :title="checksumTitle(job.checksum_status)"
            >{{ checksumLabel(job.checksum_status) }}</span>
            <span v-if="job.status === 'failed'" class="dm-stat dm-stat--error" :title="job.error_msg ?? undefined">
              {{ truncate(job.error_msg, 40) }}
            </span>
            <span class="dm-stat dm-stat--pct">{{ job.progress_pct.toFixed(0) }}%</span>
          </div>

        </div>

        <!-- Clear finished button -->
        <div v-if="hasFinished" class="dm-footer">
          <button class="dm-clear-btn" @click="clearFinished">Clear finished</button>
        </div>

      </div>
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import client from '@/services/api/client'
import { useSocketStore } from '@/stores/socket'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// ── Props ───────────────────────────────────────────────────────────────────

const { inline = false } = defineProps<{ inline?: boolean }>()

// ── Types ──────────────────────────────────────────────────────────────────

interface DownloadJob {
  id: number
  gog_id: number
  game_title: string
  file_name: string
  file_type: string
  os_platform: string | null
  language: string | null
  status: string
  total_size: number | null
  downloaded_size: number
  speed_bps: number
  progress_pct: number
  error_msg: string | null
  verify_checksum: boolean
  checksum_status: string | null   // null | "pending" | "ok" | "failed" | "skipped"
  started_at: string | null
  finished_at: string | null
}

// ── State ──────────────────────────────────────────────────────────────────

const jobs     = ref<DownloadJob[]>([])
const expanded = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
let unsubSocket: (() => void) | null = null

const POLL_INTERVAL = 30000  // ms - fallback only, WebSocket is primary

// ── Computed ───────────────────────────────────────────────────────────────

const activeJob = computed(() =>
  jobs.value.find(j => j.status === 'downloading')
)

const hasActive = computed(() =>
  jobs.value.some(j => ['downloading', 'queued', 'paused'].includes(j.status))
)

const hasFinished = computed(() =>
  jobs.value.some(j => ['completed', 'failed', 'cancelled'].includes(j.status))
)

const dotClass = computed(() => {
  if (jobs.value.some(j => j.status === 'downloading')) return 'dm-status-dot--active'
  if (jobs.value.some(j => j.status === 'paused'))      return 'dm-status-dot--paused'
  if (jobs.value.some(j => j.status === 'failed'))      return 'dm-status-dot--error'
  return 'dm-status-dot--idle'
})

// ── WebSocket + fallback polling ───────────────────────────────────────────

async function fetchJobs() {
  try {
    const { data } = await client.get<DownloadJob[]>('/gog/downloads')
    jobs.value = data
  } catch {
    // silent
  }
}

function handleJobUpdate(data: Record<string, unknown>) {
  const id = data.id as number
  const idx = jobs.value.findIndex(j => j.id === id)
  if (idx >= 0) {
    // Update existing job in-place
    Object.assign(jobs.value[idx], data)
  } else {
    // New job appeared - full refresh
    fetchJobs()
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(fetchJobs, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onMounted(() => {
  fetchJobs()
  // WebSocket: real-time updates per job
  try {
    const socketStore = useSocketStore()
    unsubSocket = socketStore.onDownloadJob(handleJobUpdate)
  } catch { /* socket not available */ }
  // Fallback: slow poll every 30s for full sync
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  if (unsubSocket) { unsubSocket(); unsubSocket = null }
})

// Auto-expand tray when a new download starts
watch(
  () => jobs.value.filter(j => j.status === 'downloading').length,
  (n, prev) => { if (n > 0 && prev === 0) expanded.value = true }
)

// ── Actions ────────────────────────────────────────────────────────────────

async function pauseJob(id: number) {
  try {
    await client.post(`/gog/downloads/${id}/pause`)
    await fetchJobs()
  } catch { /* ignore */ }
}

async function resumeJob(id: number) {
  try {
    await client.post(`/gog/downloads/${id}/resume`)
    await fetchJobs()
  } catch { /* ignore */ }
}

async function cancelJob(id: number) {
  try {
    await client.delete(`/gog/downloads/${id}?action=cancel`)
    await fetchJobs()
  } catch { /* ignore */ }
}

async function deleteJob(id: number) {
  try {
    await client.delete(`/gog/downloads/${id}?action=delete`)
    jobs.value = jobs.value.filter(j => j.id !== id)
  } catch { /* ignore */ }
}

async function clearFinished() {
  const finished = jobs.value.filter(j =>
    ['completed', 'failed', 'cancelled'].includes(j.status)
  )
  await Promise.all(finished.map(j => deleteJob(j.id)))
}

// ── Helpers ────────────────────────────────────────────────────────────────

function progressWidth(job: DownloadJob): string {
  if (job.status === 'completed') return '100%'
  if (!job.total_size) return '0%'
  return `${Math.min(job.progress_pct, 100)}%`
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes, u = 0
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++ }
  return `${v.toFixed(u > 0 ? 1 : 0)} ${units[u]}`
}

function formatSpeed(bps: number): string {
  return `${formatBytes(bps)}/s`
}

function formatEta(job: DownloadJob): string {
  if (!job.total_size || !job.speed_bps || job.speed_bps <= 0) return ''
  const remaining = job.total_size - job.downloaded_size
  const secs = Math.round(remaining / job.speed_bps)
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`
}

function statusLabel(status: string): string {
  return {
    queued:      t('download.queued'),
    downloading: t('download.downloading'),
    paused:      t('download.paused'),
    completed:   t('download.completed'),
    failed:      t('download.failed'),
    cancelled:   t('download.cancelled'),
  }[status] ?? status
}

function checksumLabel(status: string | null): string {
  return {
    ok:        '✓ MD5 OK',
    failed:    '✗ MD5 FAIL',
    size_ok:   '✓ Size OK',
    size_fail: '✗ Size FAIL',
    skipped:   '– No checksum',
    pending:   '⋯ Verifying',
  }[status ?? 'pending'] ?? '⋯ Verifying'
}

function checksumClass(status: string | null): string {
  return {
    ok:        'dm-checksum--ok',
    failed:    'dm-checksum--failed',
    size_ok:   'dm-checksum--size-ok',
    size_fail: 'dm-checksum--failed',
    skipped:   'dm-checksum--skipped',
    pending:   'dm-checksum--pending',
  }[status ?? 'pending'] ?? 'dm-checksum--pending'
}

function checksumTitle(status: string | null): string {
  return {
    ok:        'MD5 checksum verified - file is intact',
    failed:    'MD5 mismatch - file may be corrupted, try re-downloading',
    size_ok:   'No MD5 from GOG - file size matches manifest',
    size_fail: 'File size mismatch - download may be incomplete or corrupted',
    skipped:   'GOG did not provide MD5 or file size for this file',
    pending:   'Calculating…',
  }[status ?? 'pending'] ?? ''
}

function truncate(s: string | null, n: number): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

// Expose fetchJobs so parent can trigger a refresh after starting a download
defineExpose({ fetchJobs })
</script>

<style scoped>
/* ── Tray container ───────────────────────────────────────────────────────── */
.dm-tray {
  position: fixed;
  bottom: 18px;
  right: 20px;
  z-index: 8000;
  width: 360px;
  border-radius: var(--radius, 12px);
  overflow: hidden;
  background: var(--glass-bg, rgba(15, 10, 30, .92));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 160%));
  box-shadow:
    0 8px 32px rgba(0,0,0,.5),
    0 0 0 1px color-mix(in srgb, var(--pl) 12%, transparent);
  transition: box-shadow .25s;
}

.dm-tray--has-active {
  box-shadow:
    0 8px 32px rgba(0,0,0,.5),
    0 0 0 1px color-mix(in srgb, var(--pl) 30%, transparent),
    0 0 20px color-mix(in srgb, var(--pl) 12%, transparent);
}

/* ── Inline mode (Classic sidebar panel-bottom) ────────────────────────────── */
.dm-tray--inline {
  position: static;
  bottom: unset;
  right: unset;
  z-index: unset;
  width: 100%;
  border-radius: var(--radius-sm, 8px);
  box-shadow: none;
}
.dm-tray--inline.dm-tray--has-active {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 30%, transparent);
}

/* ── Header bar ───────────────────────────────────────────────────────────── */
.dm-header {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background .15s;
}
.dm-header:hover { background: rgba(255,255,255,.04); }

.dm-header-left {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}

.dm-header-title {
  font-size: var(--fs-sm, 12px);
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: rgba(255,255,255,.75);
}

.dm-badge {
  font-size: var(--fs-xs, 10px);
  font-weight: 700;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  color: var(--pl-light, var(--pl));
  border-radius: 10px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}

/* ── Status dot ───────────────────────────────────────────────────────────── */
.dm-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dm-status-dot--active {
  background: var(--pl-light, var(--pl));
  box-shadow: 0 0 6px var(--pl-light, var(--pl));
  animation: dm-pulse 1.4s ease-in-out infinite;
}
.dm-status-dot--paused { background: #f59e0b; }
.dm-status-dot--error  { background: #ef4444; }
.dm-status-dot--idle   { background: rgba(255,255,255,.25); }

@keyframes dm-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: .3; }
}

/* ── Quick info (collapsed) ───────────────────────────────────────────────── */
.dm-header-quick {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  overflow: hidden;
}

.dm-quick-name {
  font-size: 11px;
  color: rgba(255,255,255,.45);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.dm-quick-pct {
  font-size: 11px;
  font-weight: 600;
  color: var(--pl-light, var(--pl));
  white-space: nowrap;
  flex-shrink: 0;
}

.dm-toggle {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(255,255,255,.35);
  display: flex;
  align-items: center;
  padding: 2px;
  flex-shrink: 0;
  transition: color .15s;
}
.dm-toggle:hover { color: rgba(255,255,255,.7); }

/* ── Slide transition ─────────────────────────────────────────────────────── */
.dm-slide-enter-active,
.dm-slide-leave-active { transition: max-height .2s ease, opacity .15s; overflow: hidden; }
.dm-slide-enter-from,
.dm-slide-leave-to     { max-height: 0; opacity: 0; }
.dm-slide-enter-to,
.dm-slide-leave-from   { max-height: 500px; opacity: 1; }

/* ── Body ─────────────────────────────────────────────────────────────────── */
.dm-body {
  border-top: 1px solid var(--glass-border, rgba(255,255,255,.06));
  max-height: 420px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,.08) transparent;
}

/* ── Job card ─────────────────────────────────────────────────────────────── */
.dm-job {
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,.05));
}
.dm-job:last-child { border-bottom: none; }
.dm-job--completed { opacity: .65; }
.dm-job--cancelled { opacity: .45; }
.dm-job--failed    { opacity: .7; }

/* ── Job header row ───────────────────────────────────────────────────────── */
.dm-job-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2, 8px);
  margin-bottom: 6px;
}

.dm-job-info {
  display: flex;
  align-items: baseline;
  gap: 5px;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

.dm-job-title {
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  color: rgba(255,255,255,.85);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
  max-width: 130px;
}

.dm-job-sep { color: rgba(255,255,255,.2); font-size: 11px; flex-shrink: 0; }

.dm-job-file {
  font-size: 11px;
  color: rgba(255,255,255,.4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Action buttons ───────────────────────────────────────────────────────── */
.dm-job-actions {
  display: flex;
  gap: var(--space-1, 4px);
  flex-shrink: 0;
}

.dm-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.5);
  cursor: pointer;
  transition: all .15s;
}
.dm-action-btn:hover { background: rgba(255,255,255,.1); color: #fff; }

.dm-action-btn--resume { color: var(--pl-light, var(--pl)); border-color: color-mix(in srgb, var(--pl-light, var(--pl)) 40%, transparent); }
.dm-action-btn--resume:hover { background: color-mix(in srgb, var(--pl) 20%, transparent); }

.dm-action-btn--cancel:hover { background: rgba(239,68,68,.2); color: #fca5a5; border-color: rgba(239,68,68,.4); }

/* ── Progress bar ─────────────────────────────────────────────────────────── */
.dm-progress-track {
  height: 3px;
  background: rgba(255,255,255,.07);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 5px;
}

.dm-progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width .8s ease;
}
.dm-progress-fill--downloading {
  background: linear-gradient(90deg, var(--pl) 0%, var(--pl-light, var(--pl)) 100%);
  animation: dm-shimmer 1.5s ease-in-out infinite;
}
.dm-progress-fill--paused  { background: #f59e0b; }
.dm-progress-fill--completed { background: #22c55e; }
.dm-progress-fill--failed  { background: #ef4444; }
.dm-progress-fill--cancelled { background: rgba(255,255,255,.2); }
.dm-progress-fill--queued  { background: rgba(255,255,255,.15); width: 8% !important; animation: dm-queued-pulse 1s ease-in-out infinite; }

@keyframes dm-shimmer {
  0%, 100% { filter: brightness(1); }
  50%       { filter: brightness(1.3); }
}
@keyframes dm-queued-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: .3; }
}

/* ── Stats row ────────────────────────────────────────────────────────────── */
.dm-job-stats {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  flex-wrap: wrap;
}

.dm-stat {
  font-size: var(--fs-xs, 10px);
  color: rgba(255,255,255,.4);
  white-space: nowrap;
}

.dm-stat--status { font-weight: 600; }
.dm-status--downloading { color: var(--pl-light, var(--pl)); }
.dm-status--paused      { color: #f59e0b; }
.dm-status--completed   { color: #22c55e; }
.dm-status--failed      { color: #ef4444; }
.dm-status--cancelled   { color: rgba(255,255,255,.3); }
.dm-status--queued      { color: rgba(255,255,255,.4); }

.dm-stat--speed { color: rgba(255,255,255,.55); }
.dm-stat--eta   { color: rgba(255,255,255,.3); }

.dm-stat--pct {
  margin-left: auto;
  font-weight: 600;
  color: rgba(255,255,255,.5);
}

.dm-stat--error {
  color: #fca5a5;
  cursor: help;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dm-stat--checksum {
  font-weight: 600;
  cursor: help;
  white-space: nowrap;
}
.dm-checksum--ok      { color: #22c55e; }
.dm-checksum--failed  { color: #ef4444; }
.dm-checksum--size-ok { color: #a3e635; }   /* lime - weaker than full MD5 green */
.dm-checksum--skipped { color: rgba(255,255,255,.3); font-weight: 400; }
.dm-checksum--pending { color: rgba(255,255,255,.4); font-weight: 400; }

/* ── Footer ───────────────────────────────────────────────────────────────── */
.dm-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--glass-border, rgba(255,255,255,.06));
  display: flex;
  justify-content: flex-end;
}

.dm-clear-btn {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  background: none;
  border: none;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: var(--radius-xs, 4px);
  transition: color .15s, background .15s;
}
.dm-clear-btn:hover { color: rgba(255,255,255,.7); background: rgba(255,255,255,.06); }
</style>
