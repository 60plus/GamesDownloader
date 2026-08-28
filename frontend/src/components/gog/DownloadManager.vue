<template>
  <!-- Fixed bottom-right download tray - works in both Modern and Classic themes -->
  <div class="dm-tray" :class="{ 'dm-tray--open': expanded, 'dm-tray--has-active': hasActive, 'dm-tray--inline': inline }">

    <!-- ── Header bar (always visible when there are jobs) ───────────────── -->
    <div v-if="jobs.length > 0 || packagingList.length > 0 || urlList.length > 0 || romList.length > 0 || chdList.length > 0" class="dm-header" @click="expanded = !expanded">
      <div class="dm-header-left">
        <!-- Animated icon when downloading -->
        <div class="dm-status-dot" :class="dotClass" />
        <span class="dm-header-title">{{ t('download.downloads') }}</span>
        <span class="dm-badge">{{ jobs.length + packagingList.length + urlList.length + romList.length + chdList.length }}</span>
      </div>

      <!-- Active download quick-info (collapsed view) -->
      <div v-if="!expanded && activeJob" class="dm-header-quick">
        <span class="dm-quick-name">{{ activeJob.file_name }}</span>
        <span class="dm-quick-pct">{{ activeJob.progress_pct.toFixed(0) }}%</span>
      </div>

      <button class="dm-toggle" :title="expanded ? t('common.collapse') : t('common.expand')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline :points="expanded ? '18 15 12 9 6 15' : '6 9 12 15 18 9'" />
        </svg>
      </button>
    </div>

    <!-- ── Expanded job list ───────────────────────────────────────────────── -->
    <Transition name="dm-slide">
      <div v-if="expanded && (jobs.length > 0 || packagingList.length > 0 || urlList.length > 0 || romList.length > 0 || chdList.length > 0)" class="dm-body">

        <!-- Disc conversion to CHD. Local work like packaging, but it can be
             stopped: a four disc set is several minutes and somebody may want
             the machine back. -->
        <div v-for="cv in chdList" :key="cv.id" class="dm-job" :class="`dm-job--${pkClass(cv.status)}`">
          <div class="dm-job-head">
            <div class="dm-job-info">
              <span class="dm-job-title">{{ cv.title }}</span>
              <span class="dm-job-sep">·</span>
              <span class="dm-job-file">{{ t('chd.title') }}</span>
            </div>
            <div class="dm-job-actions">
              <button
                v-if="cv.status === 'converting' || cv.status === 'queued'"
                class="dm-act"
                :title="t('chd.cancel')"
                @click="cancelChd(cv)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
                  <line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="dm-progress-track">
            <div
              class="dm-progress-fill"
              :class="`dm-progress-fill--${pkClass(cv.status)}`"
              :style="{ width: cv.status === 'completed' ? '100%' : `${Math.max(2, cv.percent)}%` }"
            />
          </div>
          <div class="dm-job-stats">
            <span class="dm-stat dm-stat--status" :class="`dm-status--${pkClass(cv.status)}`">
              {{ chdStatusText(cv) }}
            </span>
            <span v-if="cv.total_discs > 1" class="dm-stat">
              {{ t('chd.disc_n_of', { n: Math.min(cv.done_discs + 1, cv.total_discs), total: cv.total_discs }) }}
            </span>
            <span v-if="cv.status === 'completed' && cv.saved_bytes > 0" class="dm-stat">
              {{ t('chd.saved', { size: formatBytes(cv.saved_bytes, '-') }) }}
            </span>
            <span v-if="cv.error" class="dm-stat dm-stat--error">{{ cv.error }}</span>
            <span class="dm-stat dm-stat--pct">{{ Math.round(cv.percent) }}%</span>
          </div>
        </div>

        <!-- Packaging items (GOG per-platform zip) -->
        <div v-for="pk in packagingList" :key="pk.id" class="dm-job" :class="`dm-job--${pkClass(pk.status)}`">
          <div class="dm-job-head">
            <div class="dm-job-info">
              <span class="dm-job-title">{{ pk.game_title }}</span>
              <span class="dm-job-sep">·</span>
              <span class="dm-job-file">{{ t('packaging.title') }} · {{ pk.platform }}</span>
            </div>
          </div>
          <div class="dm-progress-track">
            <div
              class="dm-progress-fill"
              :class="`dm-progress-fill--${pkClass(pk.status)}`"
              :style="{ width: pk.status === 'completed' ? '100%' : (pk.total ? `${pk.progress_pct}%` : '8%') }"
            />
          </div>
          <div class="dm-job-stats">
            <span class="dm-stat dm-stat--status" :class="`dm-status--${pkClass(pk.status)}`">
              {{ pk.status === 'completed' ? t('packaging.done') : pk.status === 'failed' ? t('packaging.failed') : t('packaging.packaging') }}
            </span>
            <span v-if="pk.status === 'packaging' && pk.total" class="dm-stat">{{ pk.done }} / {{ pk.total }}</span>
            <span class="dm-stat dm-stat--pct">{{ Math.round(pk.progress_pct) }}%</span>
          </div>
        </div>

        <!-- URL / catalogue downloads (storefront pulls). Socket-fed and short-
             lived like packaging, not part of the GOG job database: they report
             over upload:url_progress|complete|error and clear themselves once
             finished. A GOG download reaches the tray through `jobs`; this is the
             same visibility for a catalogue build (PC Ports and the like). -->
        <div v-for="u in urlList" :key="u.id" class="dm-job" :class="`dm-job--${pkClass(u.status)}`">
          <div class="dm-job-head">
            <div class="dm-job-info">
              <span class="dm-job-title">{{ u.game_title || u.file_name }}</span>
              <template v-if="u.game_title && u.file_name">
                <span class="dm-job-sep">·</span>
                <span class="dm-job-file">{{ u.file_name }}</span>
              </template>
            </div>
          </div>
          <div class="dm-progress-track">
            <div
              class="dm-progress-fill"
              :class="`dm-progress-fill--${pkClass(u.status)}`"
              :style="{ width: u.status === 'completed' ? '100%' : (u.total ? `${Math.min(u.progress_pct, 100)}%` : '8%') }"
            />
          </div>
          <div class="dm-job-stats">
            <span class="dm-stat dm-stat--status" :class="`dm-status--${pkClass(u.status)}`">{{ statusLabel(u.status) }}</span>
            <template v-if="u.status === 'downloading'">
              <span v-if="u.total" class="dm-stat">{{ formatBytes(u.received) }} / {{ formatBytes(u.total) }}</span>
              <span v-if="u.speed > 0" class="dm-stat dm-stat--speed">{{ formatSpeed(u.speed) }}</span>
            </template>
            <span v-if="u.status === 'failed'" class="dm-stat dm-stat--error" :title="u.error || undefined">{{ truncate(u.error, 40) }}</span>
            <span class="dm-stat dm-stat--pct">{{ Math.round(u.progress_pct) }}%</span>
          </div>
        </div>

        <!-- ROM-source downloads (RomDownloader). Socket-fed and self-clearing
             like the URL section, but keyed on the romsource job id (namespaced
             "rom:" so it never collides with a GOG job id). Title is the ROM
             file; the platform slug rides as the sub-label. -->
        <div v-for="r in romList" :key="r.id" class="dm-job" :class="`dm-job--${pkClass(r.status)}`">
          <div class="dm-job-head">
            <div class="dm-job-info">
              <span class="dm-job-title">{{ r.file_name }}</span>
              <template v-if="r.platform">
                <span class="dm-job-sep">·</span>
                <span class="dm-job-file">{{ r.platform }}</span>
              </template>
            </div>
            <!-- The same controls the GOG jobs below have had all along. A ROM
                 can be several gigabytes, so being unable to stop one, or having
                 to fetch it from the start after a dropped connection, was the
                 difference between a download manager and a progress bar. -->
            <div class="dm-job-actions">
              <button
                v-if="r.status === 'downloading'"
                class="dm-action-btn"
                :title="t('download.pause')"
                @click.stop="romPause(r.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
                </svg>
              </button>
              <button
                v-else-if="r.status === 'paused'"
                class="dm-action-btn dm-action-btn--resume"
                :title="t('download.resume')"
                @click.stop="romResume(r.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5,3 19,12 5,21"/>
                </svg>
              </button>
              <button
                v-if="['failed', 'cancelled'].includes(r.status)"
                class="dm-action-btn dm-action-btn--resume"
                :title="t('download.retry')"
                @click.stop="romRetry(r.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="23 4 23 10 17 10"/>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
              </button>
              <button
                class="dm-action-btn dm-action-btn--cancel"
                :title="['downloading', 'queued', 'paused'].includes(r.status)
                  ? t('download.cancel') : t('download.remove')"
                @click.stop="romCancel(r.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="dm-progress-track">
            <div
              class="dm-progress-fill"
              :class="`dm-progress-fill--${pkClass(r.status)}`"
              :style="{ width: r.status === 'completed' ? '100%' : (r.total ? `${Math.min(r.progress_pct, 100)}%` : '8%') }"
            />
          </div>
          <div class="dm-job-stats">
            <span class="dm-stat dm-stat--status" :class="`dm-status--${pkClass(r.status)}`">{{ statusLabel(r.status) }}</span>
            <template v-if="r.status === 'downloading'">
              <span v-if="r.total" class="dm-stat">{{ formatBytes(r.received) }} / {{ formatBytes(r.total) }}</span>
              <span v-if="r.speed > 0" class="dm-stat dm-stat--speed">{{ formatSpeed(r.speed) }}</span>
            </template>
            <span v-if="r.status === 'failed'" class="dm-stat dm-stat--error" :title="r.error || undefined">{{ truncate(r.error, 40) }}</span>
            <span class="dm-stat dm-stat--pct">{{ Math.round(r.progress_pct) }}%</span>
          </div>
        </div>

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
                :title="t('download.pause')"
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
                :title="t('download.resume')"
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
                :title="t('download.cancel')"
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
                :title="t('download.remove')"
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
          <button class="dm-clear-btn" @click="clearFinished">{{ t('download.clear_finished') }}</button>
        </div>

      </div>
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import client from '@/services/api/client'
import { useSocketStore } from '@/stores/socket'
import { useI18n } from '@/i18n'
import { formatBytes } from '@/utils/format'
import romSources from '@/lib/romSourceActions'

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

interface PackagingItem {
  id: string
  game_title: string
  platform: string
  status: string            // packaging | completed | failed
  done: number
  total: number
  progress_pct: number
}
interface ChdItem {
  id: string
  job_id: number
  rom_id: number
  title: string
  status: string            // queued | converting | completed | failed | cancelled
  percent: number
  done_discs: number
  total_discs: number
  saved_bytes: number
  error: string
}
const chdItems = reactive<Record<string, ChdItem>>({})
const chdList = computed(() => Object.values(chdItems))
const chdTimers = new Map<string, ReturnType<typeof setTimeout>>()

const packagingItems = reactive<Record<string, PackagingItem>>({})
const packagingList = computed(() => Object.values(packagingItems))
const pkTimers = new Map<string, ReturnType<typeof setTimeout>>()

function pkClass(status: string): string {
  // Paused and cancelled arrived with the ROM download controls; packaging and
  // URL rows never reach either, so they are unaffected.
  if (status === 'failed' || status === 'cancelled') return 'failed'
  if (status === 'completed') return 'completed'
  if (status === 'paused') return 'paused'
  return 'downloading'
}

// URL / catalogue downloads: a socket-fed, self-clearing section separate from
// the GOG job list (which is DB-backed and refetched on any unknown id). Keyed
// by the url job id, which is namespaced away from GOG ids so the two lists
// never collide.
interface UrlDl {
  id: string
  game_title: string
  file_name: string
  status: string            // downloading | completed | failed
  received: number
  total: number
  speed: number
  progress_pct: number
  error: string
}
const urlItems = reactive<Record<string, UrlDl>>({})
const urlList = computed(() => Object.values(urlItems))
const urlTimers = new Map<string, ReturnType<typeof setTimeout>>()

// ROM-source downloads (RomDownloader): socket-fed, self-clearing, keyed by the
// romsource job id (prefixed so it can never clash with a GOG job or url id).
interface RomDl {
  id: string
  file_name: string        // the ROM filename
  platform: string         // fs_slug
  status: string           // downloading | completed | failed
  received: number
  total: number
  speed: number
  progress_pct: number
  error: string
}
const romItems = reactive<Record<string, RomDl>>({})
const romList = computed(() => Object.values(romItems))
const romTimers = new Map<string, ReturnType<typeof setTimeout>>()

let pollTimer: ReturnType<typeof setInterval> | null = null
let unsubSocket: (() => void) | null = null
let unsubPackaging: (() => void) | null = null
let unsubUrl: (() => void) | null = null
let unsubRom: (() => void) | null = null
let unsubChd: (() => void) | null = null

const POLL_INTERVAL = 30000  // ms - fallback only, WebSocket is primary

// ── Computed ───────────────────────────────────────────────────────────────

const activeJob = computed(() =>
  jobs.value.find(j => j.status === 'downloading')
)

const hasActivePackaging = computed(() =>
  packagingList.value.some(p => p.status === 'packaging')
)

const hasActive = computed(() =>
  jobs.value.some(j => ['downloading', 'queued', 'paused'].includes(j.status)) ||
  hasActivePackaging.value ||
  urlList.value.some(u => u.status === 'downloading') ||
  romList.value.some(r => r.status === 'downloading')
)

const hasFinished = computed(() =>
  jobs.value.some(j => ['completed', 'failed', 'cancelled'].includes(j.status))
)

const dotClass = computed(() => {
  if (jobs.value.some(j => j.status === 'downloading') || hasActivePackaging.value || urlList.value.some(u => u.status === 'downloading') || romList.value.some(r => r.status === 'downloading')) return 'dm-status-dot--active'
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

// Rehydrate in-progress packaging after a page refresh: the WebSocket progress
// events are lost on reload, so pull the current snapshot from the server.
async function fetchActivePackaging() {
  try {
    const { data } = await client.get<Record<string, unknown>[]>('/gog/packaging/active')
    data.forEach(handlePackaging)
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

function chdStatusText(cv: ChdItem): string {
  if (cv.status === 'completed') return t('chd.done')
  if (cv.status === 'failed') return t('chd.failed')
  if (cv.status === 'cancelled') return t('chd.cancelled')
  if (cv.status === 'queued') return t('chd.queued')
  return t('chd.converting')
}

async function cancelChd(cv: ChdItem) {
  try { await romSources.cancelChdJob(cv.job_id) } catch { /* already gone */ }
}

function handleChd(data: Record<string, unknown>) {
  const id = String(data.id ?? '')
  if (!id) return
  chdItems[id] = {
    id,
    job_id:      Number(data.job_id ?? 0),
    rom_id:      Number(data.rom_id ?? 0),
    title:       String(data.title ?? ''),
    status:      String(data.status ?? 'queued'),
    percent:     Number(data.percent ?? 0),
    done_discs:  Number(data.done_discs ?? 0),
    total_discs: Number(data.total_discs ?? 1),
    saved_bytes: Number(data.saved_bytes ?? 0),
    error:       String(data.error ?? ''),
  }
  // Open the tray so a conversion that takes minutes is not invisible.
  if (['queued', 'converting'].includes(chdItems[id].status)) expanded.value = true
  const existing = chdTimers.get(id)
  if (existing) { clearTimeout(existing); chdTimers.delete(id) }
  if (['completed', 'failed', 'cancelled'].includes(chdItems[id].status)) {
    const ms = chdItems[id].status === 'failed' ? 12000 : 6000
    const timer = setTimeout(() => { delete chdItems[id]; chdTimers.delete(id) }, ms)
    chdTimers.set(id, timer)
  }
}

async function fetchChdJobs() {
  try {
    for (const row of await romSources.listChdJobs()) handleChd(row)
  } catch { /* not an admin, or the server is not up yet */ }
}

function handlePackaging(data: Record<string, unknown>) {
  const id = String(data.id ?? '')
  if (!id) return
  packagingItems[id] = {
    id,
    game_title:   String(data.game_title ?? ''),
    platform:     String(data.platform ?? ''),
    status:       String(data.status ?? 'packaging'),
    done:         Number(data.done ?? 0),
    total:        Number(data.total ?? 0),
    progress_pct: Number(data.progress_pct ?? 0),
  }
  // Open the tray so the user sees packaging start.
  if (packagingItems[id].status === 'packaging') expanded.value = true
  // Auto-clear finished items after a short delay.
  const existing = pkTimers.get(id)
  if (existing) { clearTimeout(existing); pkTimers.delete(id) }
  if (['completed', 'failed'].includes(packagingItems[id].status)) {
    const t = setTimeout(() => { delete packagingItems[id]; pkTimers.delete(id) },
      packagingItems[id].status === 'failed' ? 8000 : 5000)
    pkTimers.set(id, t)
  }
}

function handleUrlUpload(kind: string, data: Record<string, unknown>) {
  // Only downloads that asked to be surfaced (catalogue pulls). A plain admin
  // URL upload keeps its own inline progress bar and stays out of the tray.
  if (!data || !data.tray) return
  const id = String(data.id ?? '')
  if (!id) return
  const cur = urlItems[id]
  if (kind === 'complete') {
    urlItems[id] = {
      id,
      game_title: String(data.game_title ?? cur?.game_title ?? ''),
      file_name: cur?.file_name ?? '',
      status: 'completed',
      received: cur?.total || cur?.received || 0,
      total: cur?.total ?? 0,
      speed: 0,
      progress_pct: 100,
      error: '',
    }
    scheduleUrlClear(id, 5000)
  } else if (kind === 'error') {
    urlItems[id] = {
      id,
      game_title: String(data.game_title ?? cur?.game_title ?? ''),
      file_name: cur?.file_name ?? '',
      status: 'failed',
      received: cur?.received ?? 0,
      total: cur?.total ?? 0,
      speed: 0,
      progress_pct: cur?.progress_pct ?? 0,
      error: String(data.error ?? ''),
    }
    scheduleUrlClear(id, 8000)
  } else {
    const pct = Number(data.percent)
    urlItems[id] = {
      id,
      game_title: String(data.game_title ?? cur?.game_title ?? ''),
      file_name: String(data.filename ?? cur?.file_name ?? ''),
      status: 'downloading',
      received: Number(data.received ?? 0),
      total: Number(data.total ?? 0),
      speed: Number(data.speed ?? 0),
      progress_pct: pct >= 0 ? pct : 0,
      error: '',
    }
    expanded.value = true
    // Watchdog: rearmed on every progress tick. A live download emits ~1/s, so
    // 90s of silence means the backend task is gone (e.g. the container was
    // restarted mid-download) and no terminal event is coming - drop the row so
    // it does not sit "Downloading..." forever. A later complete/error resets it.
    scheduleUrlClear(id, 90000)
  }
}

function scheduleUrlClear(id: string, ms: number) {
  const ex = urlTimers.get(id); if (ex) clearTimeout(ex)
  const t = setTimeout(() => { delete urlItems[id]; urlTimers.delete(id) }, ms)
  urlTimers.set(id, t)
}

function handleRomSource(kind: string, data: Record<string, unknown>) {
  const id = 'rom:' + String(data.id ?? '')
  if (id === 'rom:') return
  const cur = romItems[id]
  const fileName = String(data.filename ?? cur?.file_name ?? '')
  const platform = String(data.fs_slug ?? cur?.platform ?? '')
  if (kind === 'complete') {
    romItems[id] = {
      id, file_name: fileName, platform, status: 'completed',
      received: cur?.total || cur?.received || 0, total: cur?.total ?? 0,
      speed: 0, progress_pct: 100, error: '',
    }
    scheduleRomClear(id, 5000)
  } else if (kind === 'error') {
    romItems[id] = {
      id, file_name: fileName, platform, status: 'failed',
      received: cur?.received ?? 0, total: cur?.total ?? 0,
      speed: 0, progress_pct: cur?.progress_pct ?? 0, error: String(data.error ?? ''),
    }
    // A failed row used to vanish after eight seconds. Now that it can be
    // retried it stays until someone decides, one way or the other.
    cancelRomClear(id)
  } else if (kind === 'state') {
    // Paused, resumed or cancelled: a state change, no bytes attached. The
    // watchdog has to go with it - a paused download is silent on purpose.
    const status = String(data.status ?? '')
    const pct = Number(data.percent)
    romItems[id] = {
      id, file_name: fileName, platform, status,
      received: Number(data.received ?? cur?.received ?? 0),
      total: Number(data.total ?? cur?.total ?? 0),
      speed: 0, progress_pct: pct >= 0 ? pct : (cur?.progress_pct ?? 0),
      error: String(data.error ?? ''),
    }
    cancelRomClear(id)
    if (status === 'completed') scheduleRomClear(id, 5000)
  } else {
    const pct = Number(data.percent)
    romItems[id] = {
      id, file_name: fileName, platform, status: 'downloading',
      received: Number(data.received ?? 0), total: Number(data.total ?? 0),
      speed: Number(data.speed ?? 0), progress_pct: pct >= 0 ? pct : 0, error: '',
    }
    expanded.value = true
    // Watchdog like the URL section: a live download emits ~1/s, so 90s of
    // silence means the backend task is gone (container restart mid-download) and
    // no terminal event is coming - drop the row so it does not hang "downloading".
    scheduleRomClear(id, 90000)
  }
}

function cancelRomClear(id: string) {
  const ex = romTimers.get(id)
  if (ex) { clearTimeout(ex); romTimers.delete(id) }
}

// The id the panel keys on is prefixed so it cannot collide with a GOG job;
// the server only knows the number.
function romJobId(id: string): number { return Number(id.replace(/^rom:/, '')) }

async function romPause(id: string) {
  try { await romSources.pauseJob(romJobId(id)) } catch { /* the row keeps its state */ }
}
async function romResume(id: string) {
  const cur = romItems[id]
  if (cur) romItems[id] = { ...cur, status: 'downloading' }
  try { await romSources.resumeJob(romJobId(id)) } catch { /* progress will correct it */ }
}
async function romRetry(id: string) {
  const cur = romItems[id]
  if (cur) romItems[id] = { ...cur, status: 'queued', error: '' }
  try { await romSources.retryJob(romJobId(id)) } catch { /* progress will correct it */ }
}
async function romCancel(id: string) {
  const cur = romItems[id]
  const live = cur && ['downloading', 'queued', 'paused'].includes(cur.status)
  try { await romSources.cancelJob(romJobId(id)) } catch { /* fall through */ }
  // Stopping leaves the row so it can be retried; a second press clears it.
  if (!live) { cancelRomClear(id); delete romItems[id] }
}

function scheduleRomClear(id: string, ms: number) {
  const ex = romTimers.get(id); if (ex) clearTimeout(ex)
  const t = setTimeout(() => { delete romItems[id]; romTimers.delete(id) }, ms)
  romTimers.set(id, t)
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => { fetchJobs(); fetchActivePackaging() }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function fetchRomJobs() {
  // A paused ROM download makes no noise, so without this a refreshed page
  // would show nothing and the file would look abandoned.
  try {
    for (const j of await romSources.listJobs()) {
      const id = 'rom:' + String(j.id ?? '')
      const total = Number(j.total ?? 0)
      const received = Number(j.received ?? 0)
      const pct = Number(j.percent)
      romItems[id] = {
        id,
        file_name: String(j.filename ?? ''),
        platform: String(j.fs_slug ?? ''),
        status: String(j.status ?? ''),
        received, total, speed: 0,
        progress_pct: pct >= 0 ? pct : 0,
        error: String(j.error ?? ''),
      }
    }
  } catch { /* not an admin, or the endpoint is not there yet */ }
}

onMounted(() => {
  fetchJobs()
  fetchActivePackaging()   // restore packaging progress after a refresh
  fetchRomJobs()           // and the ROM downloads, paused ones included
  fetchChdJobs()           // and any disc conversion still running
  // WebSocket: real-time updates per job
  try {
    const socketStore = useSocketStore()
    unsubSocket = socketStore.onDownloadJob(handleJobUpdate)
    unsubPackaging = socketStore.onPackaging(handlePackaging)
    unsubUrl = socketStore.onUrlUpload(handleUrlUpload)
    unsubRom = socketStore.onRomSource(handleRomSource)
    unsubChd = socketStore.onChdConvert(handleChd)
  } catch { /* socket not available */ }
  // Fallback: slow poll every 30s for full sync
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  if (unsubSocket) { unsubSocket(); unsubSocket = null }
  if (unsubPackaging) { unsubPackaging(); unsubPackaging = null }
  if (unsubUrl) { unsubUrl(); unsubUrl = null }
  if (unsubRom) { unsubRom(); unsubRom = null }
  if (unsubChd) { unsubChd(); unsubChd = null }
  chdTimers.forEach(timer => clearTimeout(timer)); chdTimers.clear()
  pkTimers.forEach(t => clearTimeout(t)); pkTimers.clear()
  urlTimers.forEach(t => clearTimeout(t)); urlTimers.clear()
  romTimers.forEach(t => clearTimeout(t)); romTimers.clear()
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
