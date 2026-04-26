<template>
  <div class="emu-home">

    <!-- Title bar -->
    <div class="emu-title-bar">
      <div class="emu-title-left">
        <button class="lib-back-btn" @click="router.push('/')" :title="t('library.back_to_libraries')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('library.libraries') }}
        </button>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" class="emu-title-ico">
          <rect x="2" y="6" width="20" height="14" rx="3"/>
          <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
          <path d="M6 10h4M8 8v4M14 11h4"/><path d="M8 6V4M16 6V4" stroke-width="1.5"/>
        </svg>
        <div>
          <h1 class="title-text">{{ t('nav.emulation') }}</h1>
          <p class="title-sub">{{ sortedPlatforms.length }} {{ t('emulation.platforms') }}</p>
        </div>
      </div>
      <div class="emu-title-right">
        <!-- Add ROMs (admin only) -->
        <button v-if="isAdmin" class="emu-add-btn" @click="openAddModal">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          {{ t('library.add_roms') }}
        </button>

        <!-- Scan (admin only) -->
        <button v-if="isAdmin" class="emu-scan-btn" :class="{ 'emu-scan-btn--running': scanning }" @click="triggerScan" :disabled="scanning">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ 'spin': scanning }">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          {{ scanning ? t('library.scanning') : t('library.scan_roms') }}
        </button>

        <!-- Sort -->
        <select v-model="sortBy" class="sort-select">
          <option value="name_asc">{{ t('library.a_to_z') }}</option>
          <option value="name_desc">{{ t('library.z_to_a') }}</option>
          <option value="roms_desc">{{ t('library.most_roms') }}</option>
          <option value="roms_asc">{{ t('library.fewest_roms') }}</option>
        </select>

        <!-- Card size -->
        <div class="size-group" title="Card size">
          <button v-for="sz in cardSizes" :key="sz.id" class="size-btn" :class="{ active: cardSize === sz.id }" @click="cardSize = sz.id">{{ sz.label }}</button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="emu-loading">
      <span class="spinner" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!platforms.length" class="emu-empty">
      <div class="emu-empty-icon">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <rect x="2" y="6" width="20" height="14" rx="2"/>
          <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
          <path d="M6 10h4M8 8v4M14 11h4"/>
        </svg>
      </div>
      <p class="emu-empty-title">{{ t('library.no_platforms') }}</p>
      <p class="emu-empty-sub">
        {{ t('library.add_roms_hint') }}
      </p>
      <button v-if="isAdmin" class="emu-scan-btn emu-scan-btn--primary" @click="triggerScan" :disabled="scanning">
        {{ scanning ? t('library.scanning') : t('library.scan_now') }}
      </button>
    </div>

    <!-- Platform grid -->
    <div v-if="sortedPlatforms.length" class="emu-platform-grid" :style="{
      '--card-min':    cardSizeMap[cardSize].min    + 'px',
      '--card-height': cardSizeMap[cardSize].height + 'px',
      '--card-icon':   cardSizeMap[cardSize].icon   + 'px',
      '--card-logo':   cardSizeMap[cardSize].logo   + 'px',
    }">
      <div
        v-for="(p, idx) in sortedPlatforms"
        :key="p.slug"
        class="emu-platform-card"
        :style="platformCardStyle(p.fs_slug)"
        @click="router.push({ name: 'emulation-library', params: { platform: p.slug } })"
      >
        <!-- Hero background (blurred, Ken Burns) - cover_path or POMOC fan art fallback -->
        <div class="emu-platform-hero">
          <img
            :src="p.cover_path || `/platforms/fanart/${p.fs_slug}.webp`"
            :class="['emu-platform-hero-bg', heroAnimClass]"
            :style="{ animationDelay: `-${idx * 7}s` }"
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
          <div class="emu-platform-hero-overlay" />
        </div>

        <!-- Controller icon (centered) -->
        <div class="emu-platform-icon-wrap">
          <img
            :src="`/platforms/icons/${p.fs_slug}.png`"
            :alt="p.name"
            class="emu-platform-icon"
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
        </div>

        <!-- Name logo + count (bottom) -->
        <div class="emu-platform-footer">
          <img
            :src="`/platforms/names/${p.fs_slug}.svg`"
            :alt="p.name"
            class="emu-platform-name-logo"
            @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLImageElement).nextElementSibling?.removeAttribute('style')"
          />
          <span class="emu-platform-name-text" style="display:none">{{ p.name }}</span>
          <span class="emu-platform-count">{{ p.rom_count }} {{ t('emulation.roms_count') }}</span>
        </div>
      </div>
    </div>

    <div v-if="scanMsg" class="emu-scan-msg">{{ scanMsg }}</div>

    <!-- ══ ADD ROMs MODAL ══════════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div v-if="addModal.open" class="gd-modal-backdrop" @click.self="closeAddModal">
        <div class="gd-modal emu-add-modal">

          <!-- Step 1: platform picker -->
          <template v-if="addModal.step === 1">
            <div class="gd-modal-header">
              <h2 class="gd-modal-title">{{ t('library.select_platform') }}</h2>
              <button class="gd-modal-close" @click="closeAddModal">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <p class="gd-modal-sub">{{ t('library.select_platform_desc') }}</p>

            <!-- Search -->
            <div class="emu-modal-search-wrap">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="emu-modal-search-ico"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input v-model="addModal.platformSearch" class="emu-modal-search" :placeholder="t('library.search_platforms')" autofocus />
            </div>

            <div class="emu-platform-picker">
              <button
                v-for="p in filteredAllPlatforms"
                :key="p.fs_slug"
                class="emu-picker-row"
                @click="selectUploadPlatform(p)"
              >
                <img
                  :src="`/platforms/icons/${p.fs_slug}.png`"
                  :alt="p.name"
                  class="emu-picker-icon"
                  @error="($event.target as HTMLImageElement).style.display='none'"
                />
                <span class="emu-picker-name">{{ p.name }}</span>
                <span v-if="p.inDb" class="emu-picker-count">{{ p.rom_count }} {{ t('emulation.roms_count') }}</span>
                <span v-else class="emu-picker-new">{{ t('library.new_platform') }}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="emu-picker-arrow"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
              <p v-if="!filteredAllPlatforms.length" class="emu-picker-empty">{{ t('library.no_platforms') }}</p>
            </div>
          </template>

          <!-- Step 2: file upload -->
          <template v-else-if="addModal.step === 2">
            <div class="gd-modal-header">
              <button class="gd-modal-back" @click="addModal.step = 1; addModal.files = []">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
                {{ t('common.back') }}
              </button>
              <h2 class="gd-modal-title">{{ t('library.upload_roms_title', { name: addModal.selectedPlatform?.name || '' }) }}</h2>
              <button class="gd-modal-close" @click="closeAddModal">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <p class="gd-modal-sub">{{ t('library.files_placed_in', { slug: addModal.selectedPlatform?.fs_slug || '' }) }}</p>

            <!-- Drop zone -->
            <div
              class="emu-drop-zone"
              :class="{ 'emu-drop-zone--over': addModal.dragOver }"
              @dragover.prevent="addModal.dragOver = true"
              @dragleave="addModal.dragOver = false"
              @drop.prevent="onDrop"
              @click="triggerFilePicker"
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.4">
                <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
              </svg>
              <p class="emu-drop-label">{{ t('library.drop_roms') }}</p>
              <p class="emu-drop-sub">{{ t('library.rom_formats') }}</p>
              <input ref="fileInputRef" type="file" multiple style="display:none" @change="onFileInputChange" />
            </div>

            <!-- Selected files list -->
            <div v-if="addModal.files.length" class="emu-file-list">
              <div v-for="(f, i) in addModal.files" :key="i" class="emu-file-row">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.5;flex-shrink:0"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                <span class="emu-file-name">{{ f.name }}</span>
                <span class="emu-file-size">{{ formatSize(f.size) }}</span>
                <!-- progress bar (shown during upload) -->
                <div v-if="addModal.uploading" class="emu-file-progress-wrap">
                  <div class="emu-file-progress-bar" :style="{ width: (addModal.progress[i] ?? 0) + '%' }" />
                </div>
                <button v-else class="emu-file-remove" @click.stop="removeFile(i)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>

            <!-- Actions -->
            <div class="gd-modal-footer">
              <span class="emu-upload-status" v-if="addModal.uploadError" style="color:var(--error)">{{ addModal.uploadError }}</span>
              <span class="emu-upload-status" v-else-if="addModal.uploadDone" style="color:#22c55e">
                {{ t('library.uploaded_ok', { count: addModal.savedCount }) }}
              </span>
              <div style="display:flex;gap: var(--space-2, 8px);margin-left:auto">
                <button class="gd-btn gd-btn--ghost" @click="closeAddModal" :disabled="addModal.uploading">{{ t('common.cancel') }}</button>
                <button
                  class="gd-btn gd-btn--primary"
                  :disabled="!addModal.files.length || addModal.uploading"
                  @click="uploadFiles"
                >
                  <span v-if="addModal.uploading" class="spinner" style="width:12px;height:12px;border-width:2px" />
                  {{ addModal.uploading ? t('library.uploading') : t('library.upload_files', { count: addModal.files.length }) }}
                </button>
              </div>
            </div>
          </template>

        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { usePlatformMetaStore } from '@/stores/platformMeta'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const router    = useRouter()
const auth      = useAuthStore()
const themeStore = useThemeStore()
const platformMeta = usePlatformMetaStore()

const isAdmin = computed(() => auth.user?.role === 'admin')

const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `home-lib-hero-bg--${themeStore.heroAnimStyle}`
})

interface Platform {
  id:         number
  slug:       string
  fs_slug:    string
  name:       string
  rom_count:  number
  cover_path: string | null
}

const platforms = ref<Platform[]>([])
const loading   = ref(true)
const scanning  = ref(false)
const scanMsg   = ref('')

// ── Sort ─────────────────────────────────────────────────────────────────────
const sortBy = ref<'name_asc' | 'name_desc' | 'roms_desc' | 'roms_asc'>((localStorage.getItem('emu_home_sort') as any) || 'name_asc')
watch(sortBy, v => localStorage.setItem('emu_home_sort', v))

const sortedPlatforms = computed(() => {
  const list = [...platforms.value]
  switch (sortBy.value) {
    case 'name_desc': return list.sort((a, b) => b.name.localeCompare(a.name))
    case 'roms_desc': return list.sort((a, b) => b.rom_count - a.rom_count)
    case 'roms_asc':  return list.sort((a, b) => a.rom_count - b.rom_count)
    default:          return list.sort((a, b) => a.name.localeCompare(b.name))
  }
})

// ── Card size ─────────────────────────────────────────────────────────────────
const cardSizes = [
  { id: 'xs',  label: 'XS' },
  { id: 's',   label: 'S'  },
  { id: 'm',   label: 'M'  },
  { id: 'l',   label: 'L'  },
  { id: 'xl',  label: 'XL' },
  { id: 'xxl', label: 'XXL'},
] as const
type CardSizeId = typeof cardSizes[number]['id']
const cardSizeMap: Record<CardSizeId, { min: number; height: number; icon: number; logo: number }> = {
  xs:  { min: 140, height: 120, icon: 44,  logo: 80  },
  s:   { min: 180, height: 155, icon: 58,  logo: 100 },
  m:   { min: 220, height: 195, icon: 76,  logo: 130 },
  l:   { min: 260, height: 230, icon: 92,  logo: 155 },
  xl:  { min: 300, height: 268, icon: 108, logo: 180 },
  xxl: { min: 360, height: 320, icon: 130, logo: 210 },
}
const cardSize = ref<CardSizeId>((localStorage.getItem('emu-home-card-size') as CardSizeId) || 'm')
watch(cardSize, v => localStorage.setItem('emu-home-card-size', v))

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchPlatforms() {
  loading.value = true
  try {
    const { data } = await client.get('/roms/platforms')
    platforms.value = data
  } catch {
    platforms.value = []
  } finally {
    loading.value = false
  }
}

// ── Scan ──────────────────────────────────────────────────────────────────────
async function triggerScan() {
  scanning.value = true
  scanMsg.value = ''
  try {
    await client.post('/roms/scan')
    scanMsg.value = 'Scanning ROMs…'
    const poll = setInterval(async () => {
      try {
        const { data } = await client.get('/roms/scan/status')
        if (!data.running) {
          clearInterval(poll)
          await fetchPlatforms()
          scanMsg.value = ''
          scanning.value = false
        }
      } catch { /* ignore */ }
    }, 2000)
  } catch (e: any) {
    scanMsg.value = e?.response?.data?.detail || 'Scan failed'
    scanning.value = false
  }
}

// ── Add ROMs modal ────────────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)

interface PickerPlatform {
  fs_slug:   string
  name:      string
  rom_count: number    // 0 for platforms not yet in DB
  inDb:      boolean
}

const knownPlatforms = ref<{ fs_slug: string; name: string }[]>([])

async function fetchKnownPlatforms() {
  try {
    const { data } = await client.get('/roms/platforms/known')
    knownPlatforms.value = data
  } catch {
    knownPlatforms.value = []
  }
}

// Merge PLATFORM_MAP entries with DB platforms (adds rom_count + inDb flag)
const allPickerPlatforms = computed<PickerPlatform[]>(() => {
  const dbMap = new Map(platforms.value.map(p => [p.fs_slug, p]))
  return knownPlatforms.value.map(kp => {
    const db = dbMap.get(kp.fs_slug)
    return {
      fs_slug:   kp.fs_slug,
      name:      kp.name,
      rom_count: db?.rom_count ?? 0,
      inDb:      !!db,
    }
  })
})

const addModal = reactive({
  open:             false,
  step:             1 as 1 | 2,
  platformSearch:   '',
  selectedPlatform: null as PickerPlatform | null,
  files:            [] as File[],
  dragOver:         false,
  uploading:        false,
  progress:         [] as number[],
  uploadError:      '',
  uploadDone:       false,
  savedCount:       0,
})

const filteredAllPlatforms = computed(() => {
  const q = addModal.platformSearch.trim().toLowerCase()
  if (!q) return allPickerPlatforms.value
  return allPickerPlatforms.value.filter(p =>
    p.name.toLowerCase().includes(q) || p.fs_slug.includes(q)
  )
})

function openAddModal() {
  addModal.open             = true
  addModal.step             = 1
  addModal.platformSearch   = ''
  addModal.selectedPlatform = null
  addModal.files            = []
  addModal.dragOver         = false
  addModal.uploading        = false
  addModal.progress         = []
  addModal.uploadError      = ''
  addModal.uploadDone       = false
  addModal.savedCount       = 0
}

function closeAddModal() {
  if (addModal.uploading) return
  addModal.open = false
}

function selectUploadPlatform(p: PickerPlatform) {
  addModal.selectedPlatform = p
  addModal.step             = 2
  addModal.files            = []
  addModal.uploadError      = ''
  addModal.uploadDone       = false
}

function addFiles(incoming: FileList | null) {
  if (!incoming) return
  for (const f of Array.from(incoming)) {
    if (!addModal.files.find(x => x.name === f.name && x.size === f.size)) {
      addModal.files.push(f)
    }
  }
}

function onDrop(e: DragEvent) {
  addModal.dragOver = false
  addFiles(e.dataTransfer?.files ?? null)
}

function onFileInputChange(e: Event) {
  addFiles((e.target as HTMLInputElement).files)
}

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function removeFile(index: number) {
  addModal.files.splice(index, 1)
}

function formatSize(bytes: number): string {
  if (bytes < 1024)        return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3)   return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

async function uploadFiles() {
  if (!addModal.selectedPlatform || !addModal.files.length) return
  addModal.uploading    = true
  addModal.uploadError  = ''
  addModal.uploadDone   = false
  addModal.savedCount   = 0
  addModal.progress     = addModal.files.map(() => 0)

  const slug     = addModal.selectedPlatform.fs_slug
  const formData = new FormData()
  addModal.files.forEach(f => formData.append('files', f))

  try {
    const { data } = await client.post(`/roms/platforms/${slug}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress(ev) {
        const pct = ev.total ? Math.round((ev.loaded / ev.total) * 100) : 0
        addModal.progress = addModal.files.map(() => pct)
      },
    })
    addModal.savedCount = data.saved?.length ?? addModal.files.length
    addModal.uploadDone = true
    addModal.uploading  = false
    // Refresh platform list so ROM count is updated after next scan
    await fetchPlatforms()
  } catch (e: any) {
    addModal.uploadError = e?.response?.data?.detail || 'Upload failed'
    addModal.uploading   = false
  }
}

function platformCardStyle(fsSlug: string): Record<string, string> {
  const color = platformMeta.getColor(fsSlug)
  return color ? { '--platform-color': `#${color}` } : {}
}

onMounted(() => {
  fetchPlatforms()
  fetchKnownPlatforms()
  platformMeta.fetchIfNeeded()
})
</script>

<style scoped>
.emu-home {
  display: flex;
  flex-direction: column;
  gap: var(--space-6, 24px);
  padding: 24px 32px;
  min-height: 100%;
}

/* ── Title bar ──────────────────────────────────────────────────────────── */
.emu-title-bar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-3, 12px); flex-shrink: 0;
  padding: 14px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
}
.emu-title-left  { display: flex; align-items: center; gap: var(--space-3, 12px); }
.emu-title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }

.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
  cursor: pointer; font-family: inherit; transition: all var(--transition);
  margin-right: 4px; flex-shrink: 0;
}
.lib-back-btn:hover { color: var(--text); background: rgba(255,255,255,.1); }

.emu-title-ico { color: #14b8a6; filter: drop-shadow(0 0 8px rgba(20,184,166,.5)); flex-shrink: 0; }
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }

/* Add ROMs button */
.emu-add-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 13px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.emu-add-btn:hover { border-color: var(--pl); color: var(--text); }

.emu-scan-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.emu-scan-btn:hover:not(:disabled) { border-color: var(--pl); color: var(--text); }
.emu-scan-btn:disabled             { opacity: .5; cursor: not-allowed; }
.emu-scan-btn--running             { color: var(--pl-light); border-color: var(--pl); }
.emu-scan-btn--primary {
  border-color: var(--pl); background: var(--pl-dim); color: var(--pl-light);
}

/* Sort */
.sort-select {
  height: 32px; padding: 0 28px 0 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-family: inherit;
  cursor: pointer; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
  transition: border-color var(--transition), color var(--transition);
}
.sort-select:hover { border-color: var(--pl); color: var(--text); }

/* Card size buttons */
.size-group { display: flex; align-items: center; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.size-btn {
  padding: 5px 8px; font-size: var(--fs-xs, 10px); font-weight: 600; font-family: inherit;
  background: transparent; border: none; color: var(--muted);
  cursor: pointer; transition: background var(--transition), color var(--transition);
  line-height: 1;
}
.size-btn + .size-btn { border-left: 1px solid var(--glass-border); }
.size-btn:hover  { background: rgba(255,255,255,.07); color: var(--text); }
.size-btn.active { background: var(--pl-dim); color: var(--pl-light); }

/* ── Loading ────────────────────────────────────────────────────────────── */
.emu-loading {
  display: flex; align-items: center; justify-content: center;
  padding: 80px; color: var(--muted);
}

/* ── Empty ──────────────────────────────────────────────────────────────── */
.emu-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-3, 12px); padding: 80px 24px; text-align: center;
}
.emu-empty-icon {
  width: 80px; height: 80px; border-radius: 20px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); margin-bottom: 8px;
}
.emu-empty-title { font-size: var(--fs-xl, 18px); font-weight: 700; color: var(--text); margin: 0; }
.emu-empty-sub   { font-size: 13px; color: var(--muted); max-width: 400px; }
.emu-empty-sub code {
  background: rgba(255,255,255,.07); padding: 2px 6px; border-radius: var(--radius-xs, 4px);
  font-size: 11px; font-family: monospace;
}

/* ── Platform grid ──────────────────────────────────────────────────────── */
.emu-platform-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min, 220px), 1fr));
  gap: var(--space-4, 16px);
}

.emu-platform-card {
  position: relative;
  height: var(--card-height, 195px);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  background: #0c0817;
  border: 1px solid var(--glass-border);
  transition: border-color var(--transition), transform 0.2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.emu-platform-card:hover {
  border-color: color-mix(in srgb, var(--platform-color, var(--pl)) 70%, transparent);
  box-shadow: 0 0 16px color-mix(in srgb, var(--platform-color, var(--pl)) 25%, transparent);
  transform: translateY(-2px);
}
/* Hero background */
.emu-platform-hero {
  position: absolute; inset: 0; z-index: 0;
}
.emu-platform-hero-bg {
  position: absolute; inset: -10px;
  width: calc(100% + 20px); height: calc(100% + 20px);
  object-fit: cover;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(110%) brightness(.35);
  transform-origin: center center;
}
/* Reuse home-lib Ken Burns animation classes */
.home-lib-hero-bg--kenburns {
  animation: emu-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.home-lib-hero-bg--drift {
  animation: emu-drift calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate;
}
.home-lib-hero-bg--pulse {
  animation: emu-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
@keyframes emu-kenburns {
  0%   { transform: scale(1.06) translateX(0%); }
  50%  { transform: scale(1.14) translateX(-4%); }
  100% { transform: scale(1.06) translateX(0%); }
}
@keyframes emu-drift {
  0%   { transform: scale(1.1) translateX(0%); }
  100% { transform: scale(1.1) translateX(-5%); }
}
@keyframes emu-pulse {
  0%, 100% { transform: scale(1.04); }
  50%       { transform: scale(1.12); }
}

.emu-platform-hero-overlay {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 50% 30%, color-mix(in srgb, var(--pl) 18%, transparent) 0%, transparent 70%),
              linear-gradient(to bottom, rgba(0,0,0,.1) 0%, rgba(0,0,0,.5) 100%);
}

/* Controller icon */
.emu-platform-icon-wrap {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: center;
  flex: 1;
}
.emu-platform-icon {
  width: var(--card-icon, 76px); height: var(--card-icon, 76px);
  object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.6));
  transition: width .2s, height .2s;
}

/* Footer: name logo + count */
.emu-platform-footer {
  position: relative; z-index: 1;
  width: 100%;
  padding: 8px 12px 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1, 4px);
  background: linear-gradient(to top, rgba(0,0,0,.7) 0%, transparent 100%);
}
.emu-platform-name-logo {
  max-width: var(--card-logo, 130px); max-height: 28px;
  object-fit: contain;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,.8)) brightness(1.1);
}
.emu-platform-name-text {
  font-size: 11px; font-weight: 700; color: rgba(255,255,255,.9);
  text-align: center; letter-spacing: .3px;
  text-shadow: 0 1px 4px rgba(0,0,0,.8);
}
.emu-platform-count {
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.5);
  font-weight: 500;
}

/* ── Misc ───────────────────────────────────────────────────────────────── */
.emu-scan-msg {
  font-size: var(--fs-sm, 12px); color: var(--muted);
  text-align: center; padding: var(--space-2, 8px);
}

.spinner {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.15); border-top-color: var(--pl-light);
  animation: spin .8s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

.spin { animation: spin .8s linear infinite; }

/* ── Add ROMs modal ──────────────────────────────────────────────────────── */
.gd-modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,.65);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-6, 24px);
}
.gd-modal {
  background: var(--bg-card, #12101a);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  box-shadow: 0 24px 64px rgba(0,0,0,.6);
  display: flex; flex-direction: column;
  max-height: 80vh; overflow: hidden;
}
.emu-add-modal { width: 520px; max-width: 100%; }

.gd-modal-header {
  display: flex; align-items: center; gap: 10px;
  padding: 18px 20px 0;
}
.gd-modal-title { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); margin: 0; flex: 1; }
.gd-modal-sub   { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 6px 20px 12px; }
.gd-modal-sub code {
  background: rgba(255,255,255,.07); padding: 1px 5px; border-radius: 3px;
  font-family: monospace; font-size: 11px;
}

.gd-modal-close, .gd-modal-back {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 8px; border-radius: var(--radius-sm);
  border: 1px solid transparent; background: transparent;
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 500; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.gd-modal-close:hover, .gd-modal-back:hover { background: rgba(255,255,255,.07); color: var(--text); }

.gd-modal-footer {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.emu-upload-status { font-size: var(--fs-sm, 12px); }

/* Platform search */
.emu-modal-search-wrap {
  position: relative; margin: 0 20px 10px;
}
.emu-modal-search-ico {
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  color: var(--muted); pointer-events: none;
}
.emu-modal-search {
  width: 100%; padding: 7px 10px 7px 32px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit;
  outline: none; transition: border-color var(--transition);
  box-sizing: border-box;
}
.emu-modal-search:focus { border-color: var(--pl); }

/* Platform picker list */
.emu-platform-picker {
  overflow-y: auto; flex: 1;
  scrollbar-gutter: stable;
  padding: 0 12px 12px;
  display: flex; flex-direction: column; gap: 2px;
}
.emu-picker-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 10px; border-radius: var(--radius-sm);
  border: none; background: transparent; width: 100%;
  cursor: pointer; text-align: left;
  transition: background var(--transition);
}
.emu-picker-row:hover { background: rgba(255,255,255,.06); }
.emu-picker-icon { width: 24px; height: 24px; object-fit: contain; flex-shrink: 0; }
.emu-picker-name { flex: 1; font-size: 13px; font-weight: 500; color: var(--text); }
.emu-picker-count { font-size: 11px; color: var(--muted); flex-shrink: 0; }
.emu-picker-new {
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .4px;
  color: #14b8a6; background: rgba(20,184,166,.12);
  padding: 2px 6px; border-radius: var(--radius-xs, 4px); flex-shrink: 0;
}
.emu-picker-arrow { color: var(--muted); flex-shrink: 0; }
.emu-picker-empty { font-size: 13px; color: var(--muted); text-align: center; padding: 24px 0; }

/* Drop zone */
.emu-drop-zone {
  margin: 0 20px 12px;
  border: 2px dashed var(--glass-border);
  border-radius: var(--radius);
  padding: 32px 20px;
  display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px);
  cursor: pointer; transition: border-color var(--transition), background var(--transition);
  color: var(--muted);
}
.emu-drop-zone:hover, .emu-drop-zone--over {
  border-color: var(--pl); background: var(--pl-dim, rgba(124,58,237,.06));
}
.emu-drop-label { font-size: 13px; color: var(--text); margin: 0; }
.emu-drop-link  { color: var(--pl-light); text-decoration: underline; cursor: pointer; }
.emu-drop-sub   { font-size: 11px; color: var(--muted); margin: 0; }

/* File list */
.emu-file-list {
  margin: 0 20px 4px;
  max-height: 180px; overflow-y: auto;
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
}
.emu-file-row {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 7px 10px;
  border-bottom: 1px solid var(--glass-border);
  position: relative;
}
.emu-file-row:last-child { border-bottom: none; }
.emu-file-name  { flex: 1; font-size: var(--fs-sm, 12px); color: var(--text); word-break: break-all; }
.emu-file-size  { font-size: 11px; color: var(--muted); flex-shrink: 0; }
.emu-file-remove {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: var(--radius-xs, 4px);
  border: none; background: transparent; color: var(--muted);
  cursor: pointer; transition: all var(--transition); flex-shrink: 0;
}
.emu-file-remove:hover { background: rgba(255,80,80,.15); color: #f87171; }
.emu-file-progress-wrap {
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: rgba(255,255,255,.08);
}
.emu-file-progress-bar {
  height: 100%; background: var(--pl-light); transition: width .2s;
}

/* Buttons */
.gd-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 16px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition); border: 1px solid transparent;
}
.gd-btn:disabled { opacity: .45; cursor: not-allowed; }
.gd-btn--ghost {
  border-color: var(--glass-border); background: transparent; color: var(--muted);
}
.gd-btn--ghost:hover:not(:disabled) { background: rgba(255,255,255,.06); color: var(--text); }
.gd-btn--primary {
  border-color: var(--pl); background: var(--pl-dim); color: var(--pl-light);
}
.gd-btn--primary:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); }
</style>
