<template>
  <Teleport to="body">
    <Transition name="dl-fade">
      <div v-if="modelValue" class="dl-backdrop" @click.self="$emit('update:modelValue', false)">
        <div class="dl-dialog" role="dialog" aria-modal="true">

          <!-- ── Header ──────────────────────────────────────────────────────── -->
          <div class="dl-header">
            <div class="dl-header-left">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" class="dl-header-ico">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span class="dl-title">Download</span>
            </div>
            <div class="dl-game-name">{{ gameTitle }}</div>
            <button class="dl-close" @click="$emit('update:modelValue', false)" title="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- ── Loading state ───────────────────────────────────────────────── -->
          <div v-if="loading" class="dl-loading">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="dl-spin">
              <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
            </svg>
            <span>Loading download options…</span>
          </div>

          <!-- ── Load error state ────────────────────────────────────────────── -->
          <div v-else-if="loadError" class="dl-error">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ loadError }}
            <button class="dl-retry" @click="fetchOptions">Retry</button>
          </div>

          <!-- ── No options ──────────────────────────────────────────────────── -->
          <div v-else-if="!options || (!options.installers.length && !options.bonus_content.length)" class="dl-error">
            No download options found for this game. Make sure your GOG account is connected.
          </div>

          <!-- ── Options ────────────────────────────────────────────────────── -->
          <template v-else>
            <div class="dl-body">

              <!-- ── OS selector ─────────────────────────────────────────────── -->
              <div class="dl-section">
                <div class="dl-section-head">
                  <span class="dl-section-label">Platform</span>
                  <span class="dl-section-hint">Choose which operating system to download for</span>
                </div>
                <div class="dl-os-chips">
                  <button
                    v-for="os in availableOS"
                    :key="os"
                    class="dl-os-chip"
                    :class="{ active: selectedOS === os }"
                    @click="selectOS(os)"
                  >
                    <!-- Windows -->
                    <svg v-if="os === 'windows'" width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                    </svg>
                    <!-- macOS -->
                    <svg v-else-if="os === 'mac'" width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M18.71,19.5C17.88,20.74 17,21.95 15.66,21.97C14.32,22 13.89,21.18 12.37,21.18C10.84,21.18 10.37,21.95 9.1,22C7.78,22.05 6.8,20.68 5.96,19.47C4.25,17 2.94,12.45 4.7,9.39C5.57,7.87 7.13,6.91 8.82,6.88C10.1,6.86 11.32,7.75 12.11,7.75C12.89,7.75 14.37,6.68 15.92,6.84C16.57,6.87 18.39,7.1 19.56,8.82C19.47,8.88 17.39,10.1 17.41,12.63C17.44,15.65 20.06,16.66 20.09,16.67C20.06,16.74 19.67,18.11 18.71,19.5M13,3.5C13.73,2.67 14.94,2.04 15.94,2C16.07,3.17 15.6,4.35 14.9,5.19C14.21,6.04 13.07,6.7 11.95,6.61C11.8,5.46 12.36,4.26 13,3.5Z"/>
                    </svg>
                    <!-- Linux -->
                    <img v-else-if="os === 'linux'" src="/icons/os-linux.svg" width="15" height="15" alt="Linux" />
                    {{ osDisplayName(os) }}
                  </button>
                </div>
              </div>

              <!-- ── Language selector ───────────────────────────────────────── -->
              <div v-if="availableLanguages.length > 1" class="dl-section">
                <div class="dl-section-head">
                  <span class="dl-section-label">Language</span>
                  <span class="dl-section-hint">Select the installer language (affects in-game text and voice)</span>
                </div>
                <div class="dl-lang-chips">
                  <button
                    v-for="lang in availableLanguages"
                    :key="lang.code"
                    class="dl-lang-chip"
                    :class="{ active: selectedLang === lang.code }"
                    @click="selectedLang = lang.code"
                  >
                    {{ lang.name }}
                  </button>
                </div>
              </div>

              <!-- ── Installer files ─────────────────────────────────────────── -->
              <div v-if="filteredInstallers.length" class="dl-section">
                <div class="dl-section-head">
                  <span class="dl-section-label">Installer Files</span>
                  <span class="dl-section-hint">Select which installer parts to download (multi-part games may have more than one)</span>
                </div>
                <div class="dl-file-list">
                  <label
                    v-for="inst in filteredInstallers"
                    :key="inst.id"
                    class="dl-file-row"
                    :class="{ checked: selectedInstallerIds.has(inst.id) }"
                  >
                    <input
                      type="checkbox"
                      class="dl-check"
                      :checked="selectedInstallerIds.has(inst.id)"
                      @change="toggleInstaller(inst.id)"
                    />
                    <div class="dl-file-info">
                      <span class="dl-file-name">{{ inst.name || inst.id }}</span>
                      <span v-if="inst.version" class="dl-file-ver">v{{ inst.version }}</span>
                    </div>
                    <span class="dl-file-size">{{ formatBytes(inst.total_size) }}</span>
                  </label>
                </div>
              </div>

              <!-- ── Bonus/Extras ─────────────────────────────────────────────── -->
              <div v-if="options.bonus_content.length" class="dl-section">
                <div class="dl-section-head">
                  <span class="dl-section-label">Bonus Content</span>
                  <span class="dl-section-hint">Extras included with the game - soundtracks, artbooks, wallpapers, etc.</span>
                </div>
                <div class="dl-file-list">
                  <label
                    v-for="bonus in options.bonus_content"
                    :key="bonus.id"
                    class="dl-file-row"
                    :class="{ checked: selectedBonusIds.has(bonus.id) }"
                  >
                    <input
                      type="checkbox"
                      class="dl-check"
                      :checked="selectedBonusIds.has(bonus.id)"
                      @change="toggleBonus(bonus.id)"
                    />
                    <div class="dl-file-info">
                      <span class="dl-bonus-type" :class="`dl-bonus-type--${bonus.type}`">
                        {{ bonusTypeLabel(bonus.type) }}
                      </span>
                      <span class="dl-file-name">{{ bonus.name }}</span>
                    </div>
                    <span class="dl-file-size">{{ formatBytes(bonus.total_size) }}</span>
                  </label>
                </div>
              </div>

              <!-- ── Parallel downloads ──────────────────────────────────────── -->
              <div class="dl-section">
                <div class="dl-section-head">
                  <span class="dl-section-label">Simultaneous Downloads</span>
                  <span class="dl-section-hint">How many files to download at once</span>
                </div>
                <div class="dl-parallel-row">
                  <button
                    v-for="n in [1, 2, 3, 4, 5]"
                    :key="n"
                    class="dl-parallel-chip"
                    :class="{ active: parallelCount === n }"
                    @click="parallelCount = n"
                  >{{ n }}</button>
                  <span class="dl-parallel-hint">
                    {{ parallelHint }}
                  </span>
                </div>
              </div>

              <!-- ── Verify checksum ─────────────────────────────────────────── -->
              <div class="dl-section dl-section--verify">
                <label class="dl-verify-row">
                  <div class="dl-verify-toggle" :class="{ active: verifyChecksum }" @click="verifyChecksum = !verifyChecksum">
                    <div class="dl-verify-knob" />
                  </div>
                  <div class="dl-verify-text">
                    <span class="dl-verify-label">Verify after download</span>
                    <span class="dl-verify-hint">Compare MD5 checksum with GOG data - detects corrupted files</span>
                  </div>
                </label>
              </div>

              <!-- ── Add to Games Library ────────────────────────────────────── -->
              <div class="dl-section dl-section--verify">
                <label class="dl-verify-row">
                  <div class="dl-verify-toggle" :class="{ active: addToLibrary }" @click="addToLibrary = !addToLibrary">
                    <div class="dl-verify-knob" />
                  </div>
                  <div class="dl-verify-text">
                    <span class="dl-verify-label">Add to Games Library</span>
                    <span class="dl-verify-hint">Publish this game to the Games Library so other users can download it</span>
                  </div>
                </label>
              </div>

              <!-- ── Download path ────────────────────────────────────────────── -->
              <div class="dl-section dl-section--path">
                <div class="dl-section-head">
                  <span class="dl-section-label">Save Location</span>
                  <span class="dl-section-hint">Files will be saved to these directories on the server</span>
                </div>
                <div v-for="p in pathPreviews" :key="p" class="dl-path-row">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.5;flex-shrink:0">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="dl-path-text">{{ p }}</span>
                </div>
              </div>

              <!-- ── Summary row ──────────────────────────────────────────────── -->
              <div v-if="selectedCount > 0" class="dl-summary">
                <span>{{ selectedCount }} file{{ selectedCount !== 1 ? 's' : '' }} selected</span>
                <span class="dl-summary-dot">·</span>
                <span>{{ formatBytes(selectedTotalSize) }} total</span>
              </div>

            </div><!-- /dl-body -->

            <!-- ── Queue error banner ─────────────────────────────────────────── -->
            <div v-if="queueError" class="dl-queue-error">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <div class="dl-queue-error-text">{{ queueError }}</div>
              <button class="dl-queue-error-close" @click="queueError = ''" title="Dismiss">×</button>
            </div>

            <!-- ── Footer ─────────────────────────────────────────────────────── -->
            <div class="dl-footer">
              <button class="dl-btn-cancel" @click="$emit('update:modelValue', false)">Cancel</button>
              <button
                class="dl-btn-start"
                :disabled="selectedCount === 0 || starting"
                @click="startDownloads"
              >
                <svg v-if="!starting" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="dl-spin">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                {{ starting ? 'Starting…' : `Download${selectedCount > 1 ? ` (${selectedCount})` : ''}` }}
              </button>
            </div>

          </template>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import client from '@/services/api/client'

// ── Props / emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  modelValue: boolean
  gogId: number
  gameTitle: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'started', jobs: any[]): void
  (e: 'publish-library', payload: { gogId: number; jobIds: number[] }): void
}>()

// ── State ──────────────────────────────────────────────────────────────────

interface InstallerFile { id: string; size: number; downlink: string; md5?: string }
interface Installer {
  id: string; name: string; os: string; language: string;
  language_full: string; version: string; total_size: number;
  files: InstallerFile[]
}
interface BonusContent {
  id: string; name: string; type: string; total_size: number;
  files: InstallerFile[]
}
interface DownloadOptions {
  installers: Installer[]
  bonus_content: BonusContent[]
}

const options    = ref<DownloadOptions | null>(null)
const loading    = ref(false)
const loadError  = ref('')    // error while fetching options (replaces dialog content)
const queueError = ref('')    // error while queuing files (shown as banner, options stay visible)
const starting   = ref(false)

const selectedOS   = ref('windows')
const selectedLang = ref('en')
const selectedInstallerIds = ref(new Set<string>())
const selectedBonusIds     = ref(new Set<string>())
const parallelCount        = ref(1)
const verifyChecksum       = ref(true)
const addToLibrary         = ref(true)   // ON by default

// ── Computed ───────────────────────────────────────────────────────────────

const availableOS = computed<string[]>(() => {
  if (!options.value) return []
  const osSet = new Set<string>()
  for (const inst of options.value.installers) {
    if (inst.os) osSet.add(inst.os)
  }
  return Array.from(osSet).sort()
})

const availableLanguages = computed<{ code: string; name: string }[]>(() => {
  if (!options.value) return []
  const map = new Map<string, string>()
  for (const inst of options.value.installers) {
    if (inst.os !== selectedOS.value) continue
    if (!map.has(inst.language)) map.set(inst.language, inst.language_full || inst.language)
  }
  return Array.from(map.entries()).map(([code, name]) => ({ code, name }))
})

const filteredInstallers = computed<Installer[]>(() => {
  if (!options.value) return []
  return options.value.installers.filter(
    i => i.os === selectedOS.value && i.language === selectedLang.value
  )
})

const selectedCount = computed(() =>
  selectedInstallerIds.value.size + selectedBonusIds.value.size
)

const selectedTotalSize = computed(() => {
  if (!options.value) return 0
  let total = 0
  for (const inst of options.value.installers) {
    if (selectedInstallerIds.value.has(inst.id)) total += inst.total_size
  }
  for (const b of options.value.bonus_content) {
    if (selectedBonusIds.value.has(b.id)) total += b.total_size
  }
  return total
})

const sanitizedTitle = computed(() =>
  props.gameTitle
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
    .replace(/[_\s]+/g, ' ')
    .trim()
    .replace(/[. ]+$/, '')
)

const parallelHint = computed(() => {
  const hints: Record<number, string> = {
    1: 'One file at a time - safest, lowest bandwidth impact',
    2: 'Two files in parallel - good balance for most connections',
    3: 'Three files in parallel - faster on high-speed connections',
    4: 'Four simultaneous downloads',
    5: 'Five simultaneous downloads - maximum speed',
  }
  return hints[parallelCount.value] ?? ''
})

const pathPreviews = computed<string[]>(() => {
  const base = `/data/games/GOG/${sanitizedTitle.value}`
  const paths = new Set<string>()
  if (selectedInstallerIds.value.size > 0) {
    paths.add(`${base}/${selectedOS.value}/`)
  }
  if (selectedBonusIds.value.size > 0) {
    paths.add(`${base}/extras/`)
  }
  if (paths.size === 0) {
    // Show default paths as preview when nothing is selected yet
    if (options.value?.installers.length) {
      paths.add(`${base}/${selectedOS.value}/`)
    }
    if (options.value?.bonus_content.length) {
      paths.add(`${base}/extras/`)
    }
    if (paths.size === 0) {
      paths.add(`${base}/`)
    }
  }
  return Array.from(paths)
})

// ── Watch dialog open ──────────────────────────────────────────────────────

watch(() => props.modelValue, (open) => {
  if (open) fetchOptions()
})

// ── Methods ────────────────────────────────────────────────────────────────

async function fetchOptions() {
  loading.value  = true
  loadError.value  = ''
  queueError.value = ''
  options.value  = null
  selectedInstallerIds.value = new Set()
  selectedBonusIds.value = new Set()
  addToLibrary.value = true   // reset to default ON each time dialog opens

  try {
    const { data } = await client.get<DownloadOptions>(
      `/gog/games/${props.gogId}/download-options`
    )
    options.value = data

    if (availableOS.value.length) {
      selectedOS.value = availableOS.value.includes('windows')
        ? 'windows'
        : availableOS.value[0]
    }
    autoSelectLanguage()
    autoSelectInstallers()
  } catch (e: any) {
    loadError.value = errMsg(e) || 'Failed to load download options'
  } finally {
    loading.value = false
  }
}

function selectOS(os: string) {
  selectedOS.value = os
  autoSelectLanguage()
  autoSelectInstallers()
}

function autoSelectLanguage() {
  const langs = availableLanguages.value
  if (!langs.length) return
  const en = langs.find(l => l.code === 'en')
  selectedLang.value = en ? 'en' : langs[0].code
}

function autoSelectInstallers() {
  // Check all installer files for current OS + lang
  const ids = new Set<string>()
  for (const inst of filteredInstallers.value) {
    ids.add(inst.id)
  }
  selectedInstallerIds.value = ids
}

// Watch filtered installers change → re-auto-select
watch(filteredInstallers, () => {
  autoSelectInstallers()
})

function toggleInstaller(id: string) {
  const s = new Set(selectedInstallerIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedInstallerIds.value = s
}

function toggleBonus(id: string) {
  const s = new Set(selectedBonusIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedBonusIds.value = s
}

/** Convert any axios/fetch error to a human-readable string. */
function errMsg(e: any): string {
  const detail = e?.response?.data?.detail
  if (!detail) return e?.message || 'Unknown error'
  // FastAPI 422 returns detail as array of {loc, msg, type} objects
  if (Array.isArray(detail)) {
    return detail.map((d: any) => {
      const loc = Array.isArray(d?.loc) ? d.loc.join('.') : ''
      return loc ? `${loc}: ${d?.msg}` : (d?.msg ?? JSON.stringify(d))
    }).join('; ')
  }
  return String(detail)
}

async function queueFile(payload: Record<string, unknown>): Promise<{ ok: boolean; data?: any; err?: string }> {
  // Validate downlink before sending - a null/empty downlink means GOG
  // doesn't provide a direct download link for this file.
  if (!payload.downlink_url) {
    return { ok: false, err: 'No download link available for this file (GOG API returned empty downlink)' }
  }
  try {
    const { data } = await client.post('/gog/downloads', payload)
    return { ok: true, data }
  } catch (e: any) {
    return { ok: false, err: errMsg(e) }
  }
}

async function startDownloads() {
  if (!options.value || selectedCount.value === 0) return
  starting.value   = true
  queueError.value = ''

  // Apply concurrency setting before queuing jobs
  try {
    await client.post('/gog/downloads/config', { max_parallel: parallelCount.value })
  } catch { /* non-fatal - proceed anyway */ }

  const started: any[] = []
  const errors: string[] = []

  // ── Queue selected installers ───────────────────────────────────────────
  for (const inst of filteredInstallers.value) {
    if (!selectedInstallerIds.value.has(inst.id)) continue
    for (const f of (inst.files ?? [])) {
      const res = await queueFile({
        gog_id:           props.gogId,
        game_title:       props.gameTitle,
        file_name:        fileNameFromDownlink(f.downlink, f.id),
        file_type:        'installer',
        os_platform:      inst.os,
        language:         inst.language,
        version:          inst.version || null,
        installer_id:     inst.id,
        file_id:          f.id,
        downlink_url:     f.downlink || null,
        total_size:       f.size || null,
        verify_checksum:  verifyChecksum.value,
        checksum:         f.md5 || null,
      })
      res.ok ? started.push(res.data) : errors.push(res.err!)
    }
  }

  // ── Queue selected bonus content ────────────────────────────────────────
  for (const bonus of options.value.bonus_content) {
    if (!selectedBonusIds.value.has(bonus.id)) continue
    const files = bonus.files ?? []
    if (!files.length) {
      errors.push(`"${bonus.name}": no downloadable files found (GOG API returned empty file list)`)
      continue
    }
    for (const f of files) {
      const res = await queueFile({
        gog_id:           props.gogId,
        game_title:       props.gameTitle,
        file_name:        fileNameFromDownlink(f.downlink, f.id || bonus.id),
        file_type:        'bonus',
        os_platform:      null,
        language:         null,
        version:          null,
        installer_id:     bonus.id,
        file_id:          f.id || bonus.id,
        downlink_url:     f.downlink || null,
        total_size:       f.size || bonus.total_size || null,
        verify_checksum:  verifyChecksum.value,
        checksum:         f.md5 || null,
      })
      res.ok ? started.push(res.data) : errors.push(`"${bonus.name}": ${res.err}`)
    }
  }

  starting.value = false

  if (started.length > 0) {
    emit('started', started)
    if (addToLibrary.value) {
      emit('publish-library', { gogId: props.gogId, jobIds: started.map((j: any) => j.id) })
    }
    emit('update:modelValue', false)
  }

  if (errors.length) {
    queueError.value = errors.join('\n')
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fileNameFromDownlink(downlink: string, fallbackId: string): string {
  // The real filename (e.g. setup_game_1.0.exe) is only known AFTER the backend
  // resolves the GOG downlink to an actual CDN URL. We pass the internal GOG file ID
  // (e.g. "en1installer") as a placeholder - the backend overwrites it during execute_job.
  // We still try to extract something meaningful from the downlink path if possible.
  try {
    const path = downlink.split('?')[0]
    const parts = path.split('/')
    const last = parts[parts.length - 1]
    if (last && last.includes('.')) return last   // already has extension → real name
  } catch { /* ignore */ }
  return fallbackId   // GOG internal ID - will be replaced by backend after CDN resolve
}

function formatBytes(bytes: number): string {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes
  let u = 0
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++ }
  return `${v.toFixed(u > 0 ? 1 : 0)} ${units[u]}`
}

function osDisplayName(os: string): string {
  return { windows: 'Windows', mac: 'macOS', linux: 'Linux' }[os] ?? os
}

function bonusTypeLabel(type: string): string {
  return {
    soundtrack: '🎵 Soundtrack',
    artbook: '🎨 Artbook',
    wallpaper: '🖼 Wallpaper',
    avatar: '👤 Avatar',
    ebook: '📖 eBook',
    skin: '🎨 Skin',
    patch: '🔧 Patch',
    game: '🎮 Game',
    video: '🎬 Video',
  }[type] ?? type.charAt(0).toUpperCase() + type.slice(1)
}
</script>

<style scoped>
/* ── Transitions ──────────────────────────────────────────────────────────── */
.dl-fade-enter-active,
.dl-fade-leave-active { transition: opacity .18s ease; }
.dl-fade-enter-active .dl-dialog { transition: transform .2s cubic-bezier(.22,1,.36,1), opacity .18s; }
.dl-fade-leave-active .dl-dialog { transition: transform .15s ease-in, opacity .15s; }
.dl-fade-enter-from .dl-dialog,
.dl-fade-leave-to   .dl-dialog  { transform: scale(.95) translateY(8px); opacity: 0; }
.dl-fade-enter-from,
.dl-fade-leave-to               { opacity: 0; }

/* ── Backdrop ─────────────────────────────────────────────────────────────── */
.dl-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0,0,0,.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4, 16px);
}

/* ── Dialog ───────────────────────────────────────────────────────────────── */
.dl-dialog {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
    0 24px 60px rgba(0,0,0,.6),
    0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  overflow: hidden;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
.dl-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,.07));
  flex-shrink: 0;
}

.dl-header-left {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
}

.dl-header-ico {
  color: var(--pl-light, var(--pl));
  flex-shrink: 0;
}

.dl-title {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  letter-spacing: .02em;
  text-transform: uppercase;
}

.dl-game-name {
  font-size: 13px;
  color: rgba(255,255,255,.45);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dl-close {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(255,255,255,.4);
  padding: var(--space-1, 4px);
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: color .15s, background .15s;
  flex-shrink: 0;
}
.dl-close:hover { color: rgba(255,255,255,.9); background: rgba(255,255,255,.06); }

/* ── Loading / Error ──────────────────────────────────────────────────────── */
.dl-loading,
.dl-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3, 12px);
  padding: 48px 24px;
  color: rgba(255,255,255,.5);
  font-size: var(--fs-md, 14px);
  text-align: center;
}

.dl-spin {
  animation: dl-rotate 1s linear infinite;
  color: var(--pl);
}
@keyframes dl-rotate { to { transform: rotate(360deg); } }

.dl-retry {
  background: var(--glass-highlight, rgba(255,255,255,.06));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: var(--radius-sm, 8px);
  color: rgba(255,255,255,.7);
  cursor: pointer;
  padding: 6px 14px;
  font-size: var(--fs-sm, 12px);
  transition: background .15s;
}
.dl-retry:hover { background: rgba(255,255,255,.1); }

/* ── Queue error banner ───────────────────────────────────────────────────── */
.dl-queue-error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 8px);
  padding: 10px 14px;
  background: rgba(220, 38, 38, .15);
  border-top: 1px solid rgba(239, 68, 68, .3);
  color: #fca5a5;
  font-size: var(--fs-sm, 12px);
  line-height: 1.5;
  white-space: pre-line;   /* renders \n as line breaks */
}

.dl-queue-error-text { flex: 1; }

.dl-queue-error-close {
  background: none;
  border: none;
  color: #fca5a5;
  cursor: pointer;
  font-size: var(--fs-lg, 16px);
  line-height: 1;
  padding: 0 2px;
  opacity: .7;
  flex-shrink: 0;
}
.dl-queue-error-close:hover { opacity: 1; }

/* ── Body ─────────────────────────────────────────────────────────────────── */
.dl-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,.1) transparent;
}

/* ── Sections ─────────────────────────────────────────────────────────────── */
.dl-section {
  padding: 16px 0 4px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,.06));
}
.dl-section:last-child { border-bottom: none; }

.dl-section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.dl-section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--pl-light, var(--pl));
}

.dl-section-hint {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  flex: 1;
}

/* ── OS chips ─────────────────────────────────────────────────────────────── */
.dl-os-chips {
  display: flex;
  gap: var(--space-2, 8px);
  flex-wrap: wrap;
}

.dl-os-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: var(--glass-highlight, rgba(255,255,255,.04));
  color: rgba(255,255,255,.6);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.dl-os-chip:hover { border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }
.dl-os-chip.active {
  border-color: var(--pl);
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  color: #fff;
  box-shadow: 0 0 10px color-mix(in srgb, var(--pl) 25%, transparent);
}

/* ── Language chips ───────────────────────────────────────────────────────── */
.dl-lang-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.dl-lang-chip {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: transparent;
  color: rgba(255,255,255,.55);
  font-size: var(--fs-sm, 12px);
  cursor: pointer;
  transition: all .15s;
}
.dl-lang-chip:hover { color: #fff; border-color: rgba(255,255,255,.25); }
.dl-lang-chip.active {
  border-color: var(--pl-light, var(--pl));
  background: color-mix(in srgb, var(--pl-light, var(--pl)) 15%, transparent);
  color: #fff;
}

/* ── File list ────────────────────────────────────────────────────────────── */
.dl-file-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 4px);
  margin-bottom: 8px;
}

.dl-file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid transparent;
  background: var(--glass-highlight, rgba(255,255,255,.03));
  cursor: pointer;
  transition: all .15s;
}
.dl-file-row:hover {
  background: color-mix(in srgb, var(--pl) 10%, transparent);
  border-color: color-mix(in srgb, var(--pl) 30%, transparent);
}
.dl-file-row.checked {
  background: color-mix(in srgb, var(--pl) 14%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
}

.dl-check {
  width: 16px;
  height: 16px;
  accent-color: var(--pl);
  flex-shrink: 0;
  cursor: pointer;
}

.dl-file-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  min-width: 0;
}

.dl-file-name {
  font-size: 13px;
  color: rgba(255,255,255,.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dl-file-ver {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  white-space: nowrap;
  flex-shrink: 0;
}

.dl-file-size {
  font-size: var(--fs-sm, 12px);
  color: rgba(255,255,255,.4);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ── Bonus type badge ─────────────────────────────────────────────────────── */
.dl-bonus-type {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.07);
  color: rgba(255,255,255,.5);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── Verify toggle ────────────────────────────────────────────────────────── */
.dl-section--verify { padding-bottom: 4px; }

.dl-verify-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3, 12px);
  cursor: pointer;
  user-select: none;
}

.dl-verify-toggle {
  flex-shrink: 0;
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.1);
  position: relative;
  transition: background .2s, border-color .2s;
  margin-top: 2px;
  cursor: pointer;
}
.dl-verify-toggle.active {
  background: color-mix(in srgb, var(--pl) 70%, transparent);
  border-color: color-mix(in srgb, var(--pl) 80%, transparent);
}

.dl-verify-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255,255,255,.5);
  transition: transform .2s, background .2s;
}
.dl-verify-toggle.active .dl-verify-knob {
  transform: translateX(16px);
  background: #fff;
}

.dl-verify-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.dl-verify-label {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255,255,255,.8);
}

.dl-verify-hint {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  line-height: 1.4;
}

/* ── Parallel count selector ──────────────────────────────────────────────── */
.dl-parallel-row {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  flex-wrap: wrap;
}

.dl-parallel-chip {
  width: 36px;
  height: 34px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--glass-border, rgba(255,255,255,.12));
  background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.55);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
  flex-shrink: 0;
}
.dl-parallel-chip:hover { background: rgba(255,255,255,.1); color: rgba(255,255,255,.85); }
.dl-parallel-chip.active {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 60%, transparent);
  color: var(--pl-light, var(--pl));
  box-shadow: 0 0 8px color-mix(in srgb, var(--pl) 15%, transparent);
}

.dl-parallel-hint {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  flex: 1;
  min-width: 0;
}

/* ── Path row ─────────────────────────────────────────────────────────────── */
.dl-path-row {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 8px 12px;
  border-radius: 7px;
  background: rgba(0,0,0,.25);
  border: 1px solid rgba(255,255,255,.06);
  margin-bottom: 6px;
}
.dl-path-row:last-child { margin-bottom: 0; }

.dl-path-text {
  font-size: var(--fs-sm, 12px);
  font-family: 'Fira Code', 'Courier New', monospace;
  color: rgba(255,255,255,.55);
  word-break: break-all;
}

/* ── Summary ──────────────────────────────────────────────────────────────── */
.dl-summary {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 10px 0 14px;
  font-size: var(--fs-sm, 12px);
  color: rgba(255,255,255,.45);
}

.dl-summary-dot { color: rgba(255,255,255,.2); }

/* ── Footer ───────────────────────────────────────────────────────────────── */
.dl-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--glass-border, rgba(255,255,255,.07));
  flex-shrink: 0;
}

.dl-btn-cancel {
  padding: 9px 18px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: transparent;
  color: rgba(255,255,255,.55);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.dl-btn-cancel:hover { background: rgba(255,255,255,.06); color: rgba(255,255,255,.8); }

.dl-btn-start {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 22px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--pl-light);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .18s;
  letter-spacing: .02em;
  box-shadow: 0 2px 12px var(--pglow2);
}
.dl-btn-start:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}
.dl-btn-start:disabled {
  opacity: .4;
  cursor: not-allowed;
  box-shadow: none;
}
</style>
