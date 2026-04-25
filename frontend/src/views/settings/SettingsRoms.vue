<template>
  <div class="sr-root">

    <!-- ── ROM Library ──────────────────────────────────────────────────────── -->
    <section class="sr-section">
      <div class="sr-section-head">
        <h2 class="sr-section-title">{{ t('roms.library_title') }}</h2>
        <p class="sr-section-sub">{{ t('roms.library_desc') }}</p>
      </div>

      <div class="sr-card">
        <div class="sr-row"
          @mouseenter="setHint(t('rhint.library_path_title'), t('rhint.library_path_body'))"
          @mouseleave="clearHint"
        >
          <div class="sr-row-label">
            <span class="sr-label">{{ t('roms.library_path') }}</span>
            <span class="sr-sub">{{ t('roms.library_path_hint') }}</span>
          </div>
          <div class="sr-row-control sr-row-control--wide">
            <input v-model="form.library_path" type="text" class="sr-input" placeholder="/data/games/roms" />
          </div>
        </div>

        <div class="sr-divider" />

        <div class="sr-row"
          @mouseenter="setHint(t('rhint.auto_scan_title'), t('rhint.auto_scan_body'))"
          @mouseleave="clearHint"
        >
          <div class="sr-row-label">
            <span class="sr-label">{{ t('roms.auto_scan') }}</span>
            <span class="sr-sub">{{ t('roms.auto_scan_hint') }}</span>
          </div>
          <div class="sr-row-control">
            <button class="sr-toggle" :class="{ 'sr-toggle--on': form.auto_scan_on_start }" @click="form.auto_scan_on_start = !form.auto_scan_on_start">
              <span class="sr-toggle-thumb" />
            </button>
          </div>
        </div>
      </div>

      <div class="sr-actions">
        <button class="sr-btn sr-btn--primary" @click="save" :disabled="saving">{{ saving ? t('roms.saving') : t('common.save') }}</button>
        <span v-if="savedMsg" class="sr-saved-msg">{{ savedMsg }}</span>
      </div>
    </section>

    <!-- ── Scrapers ─────────────────────────────────────────────────────────── -->
    <section class="sr-section">
      <div class="sr-section-head">
        <h2 class="sr-section-title">{{ t('roms.scrapers') }}</h2>
        <p class="sr-section-sub">{{ t('roms.scrapers_desc') }}</p>
      </div>

      <div class="sr-card">
        <div class="sr-scraper-row">
          <div class="sr-scraper-icon sr-scraper-icon--ss">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/>
            </svg>
          </div>
          <div class="sr-scraper-info">
            <span class="sr-scraper-name">ScreenScraper</span>
            <span class="sr-scraper-sub">{{ t('roms.ss_desc') }}</span>
          </div>
          <div class="sr-scraper-badge sr-scraper-badge--active">{{ t('roms.active') }}</div>
        </div>

        <div class="sr-divider" />

        <div class="sr-scraper-row">
          <div class="sr-scraper-icon sr-scraper-icon--igdb">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10A15.3 15.3 0 0 1 8 12a15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </div>
          <div class="sr-scraper-info">
            <span class="sr-scraper-name">IGDB</span>
            <span class="sr-scraper-sub">{{ t('roms.igdb_desc') }}</span>
          </div>
          <div class="sr-scraper-badge sr-scraper-badge--active">{{ t('roms.active') }}</div>
        </div>

        <div class="sr-divider" />

        <div class="sr-scraper-row"
          @mouseenter="setHint(t('rhint.lb_title'), t('rhint.lb_body'))"
          @mouseleave="clearHint"
        >
          <div class="sr-scraper-icon sr-scraper-icon--lb">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 4h16v16H4z"/><path d="M9 9h6v6H9z"/>
            </svg>
          </div>
          <div class="sr-scraper-info">
            <span class="sr-scraper-name">{{ t('roms.lb_name') }}</span>
            <span class="sr-scraper-sub">{{ t('roms.lb_desc') }}</span>
          </div>
          <button class="sr-toggle" :class="{ 'sr-toggle--on': form.launchbox_enabled }"
            @click="form.launchbox_enabled = !form.launchbox_enabled">
            <span class="sr-toggle-thumb" />
          </button>
        </div>
      </div>
    </section>

    <!-- ── Scrape Presets (dropdown) ──────────────────────────────────────── -->
    <section class="sr-section">
      <div class="sr-section-head-row">
        <div>
          <h2 class="sr-section-title">{{ t('roms.presets') }}</h2>
          <p class="sr-section-sub">{{ t('roms.presets_desc') }}</p>
        </div>
        <button class="sr-btn sr-btn--primary" @click="savePresets" :disabled="savingPresets" style="flex-shrink:0">
          {{ savingPresets ? t('roms.saving') : t('roms.save_presets') }}
        </button>
      </div>
      <span v-if="savedPresetsMsg" class="sr-saved-msg" style="margin-top:-8px">{{ savedPresetsMsg }}</span>

      <div v-if="loadingPresets" class="sr-loading">{{ t('roms.loading_platforms') }}</div>

      <div v-else-if="!platforms.length" class="sr-note">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
        {{ t('roms.no_platforms') }}
      </div>

      <template v-else>
        <div class="sr-preset-list">
          <div v-for="p in platforms" :key="p.fs_slug" class="sr-preset-card">

            <!-- Accordion header (clickable) -->
            <div class="sr-preset-header" @click="togglePresetOpen(p.fs_slug)">
              <img
                :src="`/platforms/icons/${p.fs_slug}.png`"
                :alt="p.name"
                class="sr-preset-icon"
                @error="($event.target as HTMLImageElement).style.display='none'"
              />
              <div class="sr-preset-name-block">
                <span class="sr-preset-name">{{ p.name }}</span>
                <span class="sr-preset-fs">{{ p.fs_slug }}</span>
              </div>
              <span class="sr-preset-count">{{ p.rom_count }} ROMs</span>
              <svg class="sr-preset-chevron" :class="{ 'sr-preset-chevron--open': presetOpen[p.fs_slug] }"
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>

            <!-- Accordion body -->
            <template v-if="presetOpen[p.fs_slug]">
              <div class="sr-preset-divider" />

              <!-- Primary Cover -->
              <div class="sr-preset-row">
                <span class="sr-preset-row-label">{{ t('roms.primary_cover') }}</span>
                <select v-model="presets[p.fs_slug].cover_type" class="sr-preset-select">
                  <option v-for="ct in COVER_TYPES" :key="ct.value" :value="ct.value">{{ ct.label }}</option>
                </select>
              </div>

              <!-- Region -->
              <div class="sr-preset-row">
                <span class="sr-preset-row-label">{{ t('roms.region') }}</span>
                <select v-model="presets[p.fs_slug].region" class="sr-preset-select">
                  <option v-for="r in REGIONS" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
              </div>

              <div class="sr-preset-divider" />

              <!-- Additional Media -->
              <div class="sr-preset-extras">
                <span class="sr-preset-row-label" style="margin-bottom:8px;display:block">{{ t('roms.additional_media') }}</span>
                <div v-for="group in EXTRAS_GROUPS" :key="group.label" class="sr-extras-group">
                  <span class="sr-extras-group-label">{{ group.label }}</span>
                  <div class="sr-extras-items">
                    <label
                      v-for="item in group.items"
                      :key="item.value"
                      class="sr-extras-check"
                      :class="{ checked: presets[p.fs_slug].extras.includes(item.value) }"
                    >
                      <input
                        type="checkbox"
                        :checked="presets[p.fs_slug].extras.includes(item.value)"
                        @change="toggleExtra(p.fs_slug, item.value)"
                        class="sr-check-input"
                      />
                      {{ item.label }}
                    </label>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </template>
    </section>

    <!-- ── HLTB Bulk Rescrape ───────────────────────────────────────────────── -->
    <section class="sr-section">
      <div class="sr-section-head">
        <h2 class="sr-section-title">{{ t('roms.hltb_title') }}</h2>
        <p class="sr-section-sub">{{ t('roms.hltb_desc') }}</p>
      </div>

      <div class="sr-card">
        <div class="sr-hltb-grid">
          <div v-for="lib in hltbLibs" :key="lib.key" class="sr-hltb-row">
            <div class="sr-hltb-info">
              <span class="sr-label">{{ lib.label }}</span>
              <span class="sr-sub">{{ lib.sub }}</span>
            </div>
            <label class="sr-hltb-force">
              <input type="checkbox" v-model="hltbForce[lib.key]" />
              <span>{{ t('roms.hltb_force') }}</span>
            </label>
            <button
              class="sr-btn sr-btn--ghost"
              :disabled="hltbRunning[lib.key]"
              @click="runHltb(lib)"
            >
              <span v-if="hltbRunning[lib.key]" class="sr-spinner" />
              {{ hltbRunning[lib.key] ? t('roms.saving') : t('roms.rescrape') }}
            </button>
            <span v-if="hltbMsg[lib.key]" class="sr-hltb-msg" :class="{ 'sr-hltb-msg--ok': hltbOk[lib.key], 'sr-hltb-msg--err': !hltbOk[lib.key] }">
              {{ hltbMsg[lib.key] }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Emulation ─────────────────────────────────────────────────────── -->
    <section class="sr-section">
      <div class="sr-section-head">
        <h2 class="sr-section-title">{{ t('roms.emulation_title', 'Emulation') }}</h2>
        <p class="sr-section-sub">{{ t('roms.emulation_desc', 'In-browser emulator settings') }}</p>
      </div>

      <div class="sr-card">
        <div class="sr-row"
          @mouseenter="setHint(t('roms.ejs_threads', 'Emulator Threads'), t('rhint.ejs_threads', 'Use multi-threaded WASM cores for better emulation performance. Requires the emulator page to be reloaded after changing.'))"
          @mouseleave="clearHint"
        >
          <div class="sr-row-label">
            <span class="sr-label">{{ t('roms.ejs_threads', 'Emulator Threads') }}</span>
            <span class="sr-sub">{{ t('roms.ejs_threads_hint', 'Multi-threaded cores for better performance') }}</span>
          </div>
          <div class="sr-row-control">
            <button class="sr-toggle" :class="{ 'sr-toggle--on': ejsThreads }" @click="toggleEjsThreads">
              <span class="sr-toggle-thumb" />
            </button>
          </div>
        </div>
        <div v-if="ejsThreadsChanged" class="sr-note" style="margin-top:8px;border-color:rgba(251,191,36,.25);background:rgba(251,191,36,.06)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01" stroke-linecap="round"/>
          </svg>
          {{ t('roms.ejs_threads_restart', 'Reload the emulator page for this change to take effect.') }}
        </div>
      </div>
    </section>

    <!-- ── Priority note ──────────────────────────────────────────────────────── -->
    <div class="sr-note">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01" stroke-linecap="round"/>
      </svg>
      {{ t('roms.priority_note') }}
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import client from '@/services/api/client'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const { setHint, clearHint } = useSettingsHint()

// ── EJS Threads (localStorage) ───────────────────────────────────────────────
const _ejsInitial = localStorage.getItem('gd_ejs_threads') === '1'
const ejsThreads = ref(_ejsInitial)
const ejsThreadsChanged = ref(false)
function toggleEjsThreads() {
  ejsThreads.value = !ejsThreads.value
  localStorage.setItem('gd_ejs_threads', ejsThreads.value ? '1' : '0')
  ejsThreadsChanged.value = ejsThreads.value !== _ejsInitial
}

// ── Constants ─────────────────────────────────────────────────────────────────

const COVER_TYPES = [
  { value: 'box-2D',           label: t('roms.cover_box2d') },
  { value: 'box-3D',           label: t('roms.cover_box3d') },
  { value: 'box-2D-side',      label: t('roms.cover_box2d_side') },
  { value: 'box-texture',      label: t('roms.cover_box_texture') },
  { value: 'support-2D',       label: t('roms.cover_support2d') },
  { value: 'support-texture',  label: t('roms.cover_support_texture') },
  { value: 'ss',               label: t('roms.cover_ss') },
  { value: 'ss-titre',         label: t('roms.cover_ss_title') },
  { value: 'marquee',          label: t('roms.cover_marquee') },
  { value: 'fanart',           label: t('roms.cover_fanart') },
  { value: 'background',       label: t('roms.cover_background') },
]

const REGIONS = [
  { value: 'wor', label: t('roms.region_wor') },
  { value: 'eu',  label: t('roms.region_eu') },
  { value: 'us',  label: t('roms.region_us') },
  { value: 'jp',  label: t('roms.region_jp') },
  { value: 'ss',  label: t('roms.region_ss') },
]

const EXTRAS_GROUPS = [
  { label: t('roms.extras_box'),         items: [{ value: 'box-texture',  label: 'Texture' }] },
  { label: t('roms.extras_manual'),      items: [{ value: 'manuel', label: 'Manual (PDF)' }, { value: 'maps', label: 'Maps' }] },
  { label: t('roms.extras_screenshots'), items: [{ value: 'ss', label: 'Gameplay' }, { value: 'ss-titre', label: 'Title Screen' }] },
  { label: t('roms.extras_video'),       items: [{ value: 'video', label: 'Video' }, { value: 'video-normalized', label: 'Normalized' }] },
  { label: t('roms.extras_support'),     items: [{ value: 'support-2D', label: 'Support 2D' }, { value: 'support-texture', label: 'Texture' }] },
  { label: t('roms.extras_bezel'),       items: [{ value: 'bezel-16-9', label: 'Bezel 16:9' }, { value: 'bezel-4-3', label: 'Bezel 4:3' }] },
  { label: t('roms.extras_art'),         items: [{ value: 'marquee', label: 'Marquee' }, { value: 'fanart', label: 'Fan Art' }, { value: 'background', label: 'Background' }] },
]

// ── General settings ──────────────────────────────────────────────────────────

const form = ref({
  library_path:       '/data/games/roms',
  auto_scan_on_start: false,
  launchbox_enabled:  true,
})
const saving   = ref(false)
const savedMsg = ref('')

async function load() {
  try {
    const { data } = await client.get('/settings/roms')
    form.value.library_path       = data.library_path       ?? '/data/games/roms'
    form.value.auto_scan_on_start = data.auto_scan_on_start ?? false
    form.value.launchbox_enabled  = data.launchbox_enabled  ?? true
  } catch { /* ignore */ }
}

async function save() {
  saving.value = true; savedMsg.value = ''
  try {
    await client.post('/settings/roms', form.value)
    savedMsg.value = t('roms.saved')
    setTimeout(() => { savedMsg.value = '' }, 2500)
  } catch { savedMsg.value = t('roms.save_failed') }
  finally { saving.value = false }
}

// ── Scrape presets ────────────────────────────────────────────────────────────

interface Platform { id: number; slug: string; fs_slug: string; name: string; rom_count: number }
interface ScrapePreset { cover_type: string; region: string; extras: string[] }

const platforms        = ref<Platform[]>([])
const presets          = ref<Record<string, ScrapePreset>>({})
const loadingPresets   = ref(true)
const savingPresets    = ref(false)
const savedPresetsMsg  = ref('')
const presetOpen       = reactive<Record<string, boolean>>({})

const DEFAULT_PRESET: ScrapePreset = { cover_type: 'box-2D', region: 'wor', extras: [] }

function togglePresetOpen(fsSlug: string) {
  presetOpen[fsSlug] = !presetOpen[fsSlug]
}

function ensurePreset(fsSlug: string) {
  if (!presets.value[fsSlug]) {
    presets.value[fsSlug] = { ...DEFAULT_PRESET, extras: [] }
  }
}

function toggleExtra(fsSlug: string, value: string) {
  ensurePreset(fsSlug)
  const list = presets.value[fsSlug].extras
  const idx = list.indexOf(value)
  if (idx === -1) list.push(value)
  else list.splice(idx, 1)
}

async function loadPresets() {
  loadingPresets.value = true
  try {
    const [pRes, prRes] = await Promise.all([
      client.get('/roms/platforms'),
      client.get('/settings/roms/scrape-presets'),
    ])
    platforms.value = pRes.data
    const saved: Record<string, ScrapePreset> = prRes.data || {}
    const merged: Record<string, ScrapePreset> = {}
    for (const p of pRes.data) {
      merged[p.fs_slug] = saved[p.fs_slug]
        ? { ...DEFAULT_PRESET, ...saved[p.fs_slug], extras: saved[p.fs_slug].extras ?? [] }
        : { ...DEFAULT_PRESET, extras: [] }
    }
    presets.value = merged
  } catch { /* ignore */ }
  finally { loadingPresets.value = false }
}

async function savePresets() {
  savingPresets.value = true; savedPresetsMsg.value = ''
  try {
    await client.post('/settings/roms/scrape-presets', { presets: presets.value })
    savedPresetsMsg.value = t('roms.presets_saved')
    setTimeout(() => { savedPresetsMsg.value = '' }, 2500)
  } catch { savedPresetsMsg.value = t('roms.save_failed') }
  finally { savingPresets.value = false }
}

// ── HLTB bulk rescrape ────────────────────────────────────────────────────────

const hltbLibs = [
  { key: 'roms',    label: t('roms.hltb_rom'),    sub: t('roms.hltb_rom_sub'),    endpoint: '/roms/hltb-rescrape' },
  { key: 'gog',     label: t('roms.hltb_gog'),    sub: t('roms.hltb_gog_sub'),    endpoint: '/gog/library/hltb-rescrape' },
  { key: 'library', label: t('roms.hltb_custom'),  sub: t('roms.hltb_custom_sub'), endpoint: '/library/hltb-rescrape' },
]
const hltbForce   = ref<Record<string, boolean>>({ roms: false, gog: false, library: false })
const hltbRunning = ref<Record<string, boolean>>({ roms: false, gog: false, library: false })
const hltbMsg     = ref<Record<string, string>>({})
const hltbOk      = ref<Record<string, boolean>>({})

async function runHltb(lib: typeof hltbLibs[number]) {
  hltbRunning.value[lib.key] = true
  hltbMsg.value[lib.key] = ''
  try {
    await client.post(lib.endpoint, null, { params: { force: hltbForce.value[lib.key] } })
    hltbMsg.value[lib.key] = t('roms.hltb_started')
    hltbOk.value[lib.key] = true
  } catch (e: any) {
    hltbMsg.value[lib.key] = e?.response?.data?.detail || t('roms.hltb_failed')
    hltbOk.value[lib.key] = false
  } finally {
    hltbRunning.value[lib.key] = false
    setTimeout(() => { hltbMsg.value[lib.key] = '' }, 6000)
  }
}

onMounted(() => { load(); loadPresets() })
</script>

<style scoped>
.sr-root { display: flex; flex-direction: column; gap: 28px; padding: 4px 0; }

/* ── Section ──────────────────────────────────────────────────────────────── */
.sr-section { display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.sr-section-head { padding: 0 2px; }
.sr-section-head-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: var(--space-4, 16px); padding: 0 2px; flex-wrap: wrap;
}
.sr-section-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); margin: 0 0 2px; }
.sr-section-sub   { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }

/* ── Card ─────────────────────────────────────────────────────────────────── */
.sr-card {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); overflow: hidden;
}
.sr-divider { height: 1px; background: var(--glass-border); }

/* ── Row ──────────────────────────────────────────────────────────────────── */
.sr-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-4, 16px); padding: 14px 18px; transition: background var(--transition);
}
.sr-row:hover { background: rgba(255,255,255,.03); }
.sr-row-label { flex: 1; min-width: 0; }
.sr-label { display: block; font-size: 13px; font-weight: 600; color: var(--text); }
.sr-sub   { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
.sr-row-control { display: flex; align-items: center; }
.sr-row-control--wide { flex: 0 0 280px; }

/* ── Input ────────────────────────────────────────────────────────────────── */
.sr-input {
  width: 100%; padding: 7px 10px;
  background: var(--input-bg, rgba(255,255,255,.06));
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  color: var(--text); font-size: var(--fs-sm, 12px); font-family: monospace;
  transition: border-color var(--transition); outline: none;
}
.sr-input:focus { border-color: var(--pl); }
.sr-input::placeholder { color: var(--muted); }

/* ── Toggle (glass style) ────────────────────────────────────────────────── */
.sr-toggle {
  position: relative; width: 40px; height: 22px; border-radius: 11px;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.1);
  cursor: pointer; transition: all .2s; flex-shrink: 0; padding: 0;
}
.sr-toggle--on {
  background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1));
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  box-shadow: 0 0 10px var(--pglow2);
}
.sr-toggle-thumb {
  position: absolute; top: 3px; left: 3px;
  width: 14px; height: 14px; border-radius: 50%;
  background: rgba(255,255,255,.4); transition: all .2s; display: block;
}
.sr-toggle--on .sr-toggle-thumb { transform: translateX(18px); background: #fff; }

/* ── Actions ──────────────────────────────────────────────────────────────── */
.sr-actions { display: flex; align-items: center; gap: var(--space-3, 12px); }
.sr-btn {
  padding: 8px 18px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: 13px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.sr-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
}
.sr-btn--primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}
.sr-btn--ghost { background: rgba(255,255,255,.05); }
.sr-btn--ghost:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.sr-btn:disabled { opacity: .5; cursor: not-allowed; }
.sr-saved-msg { font-size: var(--fs-sm, 12px); color: var(--success, #4ade80); }

/* ── Scraper rows ─────────────────────────────────────────────────────────── */
.sr-scraper-row {
  display: flex; align-items: center; gap: var(--space-3, 12px); padding: 14px 18px;
  transition: background var(--transition);
}
.sr-scraper-row:hover { background: rgba(255,255,255,.03); }
.sr-scraper-icon {
  width: 36px; height: 36px; border-radius: var(--radius-sm, 8px);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; border: 1px solid var(--glass-border);
}
.sr-scraper-icon--ss   { background: rgba(59,130,246,.15); color: #60a5fa; border-color: rgba(59,130,246,.3); }
.sr-scraper-icon--igdb { background: color-mix(in srgb, var(--pl) 15%, transparent); color: var(--pl-light); border-color: color-mix(in srgb, var(--pl) 30%, transparent); }
.sr-scraper-icon--lb   { background: rgba(251,146,60,.15); color: #fb923c; border-color: rgba(251,146,60,.3); }
.sr-scraper-info { flex: 1; min-width: 0; }
.sr-scraper-name { display: block; font-size: 13px; font-weight: 600; color: var(--text); }
.sr-scraper-sub  { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
.sr-scraper-badge { padding: 3px 8px; border-radius: 20px; font-size: var(--fs-xs, 10px); font-weight: 700; text-transform: uppercase; letter-spacing: .5px; flex-shrink: 0; }
.sr-scraper-badge--active { background: rgba(74,222,128,.15); color: #4ade80; border: 1px solid rgba(74,222,128,.3); }

/* ── Loading ──────────────────────────────────────────────────────────────── */
.sr-loading { font-size: var(--fs-sm, 12px); color: var(--muted); padding: 16px 0; }

/* ── Preset list (accordion) ──────────────────────────────────────────── */
.sr-preset-list { display: flex; flex-direction: column; gap: 6px; }

.sr-preset-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex; flex-direction: column;
}

/* Card header (clickable) */
.sr-preset-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px;
  background: rgba(255,255,255,.03);
  cursor: pointer; transition: background var(--transition);
  user-select: none;
}
.sr-preset-header:hover { background: rgba(255,255,255,.06); }

.sr-preset-chevron {
  flex-shrink: 0; color: var(--muted);
  transition: transform .2s;
}
.sr-preset-chevron--open { transform: rotate(180deg); }
.sr-preset-icon {
  width: 36px; height: 36px; object-fit: contain;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,.4));
}
.sr-preset-name-block { flex: 1; min-width: 0; }
.sr-preset-name { display: block; font-size: 13px; font-weight: 700; color: var(--text); }
.sr-preset-fs   { display: block; font-size: var(--fs-xs, 10px); color: var(--muted); font-family: monospace; margin-top: 1px; }
.sr-preset-count { font-size: 11px; color: var(--muted); flex-shrink: 0; }

.sr-preset-divider { height: 1px; background: var(--glass-border); }

/* Cover + region rows */
.sr-preset-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3, 12px); padding: 10px 16px;
}
.sr-preset-row-label { font-size: 11px; font-weight: 600; color: var(--muted); white-space: nowrap; }

.sr-preset-select {
  flex: 1; max-width: 260px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: var(--fs-sm, 12px);
  padding: 5px 8px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.sr-preset-select:hover,
.sr-preset-select:focus { border-color: var(--pl); }
.sr-preset-select option { background: var(--bg2, #1a1a2e); }

/* Extras */
.sr-preset-extras { padding: 10px 16px 14px; display: flex; flex-direction: column; gap: var(--space-2, 8px); }

.sr-extras-group { display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.sr-extras-group-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .5px;
  color: var(--muted); text-transform: uppercase;
}
.sr-extras-items { display: flex; flex-wrap: wrap; gap: 5px; }

.sr-extras-check {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 9px; border-radius: 20px;
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.04);
  font-size: 11px; font-weight: 500; color: var(--muted);
  cursor: pointer; transition: all var(--transition);
  user-select: none;
}
.sr-extras-check:hover { border-color: var(--pl); color: var(--text); }
.sr-extras-check.checked {
  border-color: var(--pl);
  background: color-mix(in srgb, var(--pl) 15%, transparent);
  color: var(--pl-light);
}
.sr-check-input { display: none; }

/* ── HLTB ─────────────────────────────────────────────────────────────────── */
.sr-hltb-grid { display: flex; flex-direction: column; }
.sr-hltb-row {
  display: flex; align-items: center; gap: 14px; padding: 12px 18px;
  flex-wrap: wrap;
}
.sr-hltb-row + .sr-hltb-row { border-top: 1px solid var(--glass-border); }
.sr-hltb-info { flex: 1; min-width: 140px; }
.sr-hltb-force {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--muted); cursor: pointer; white-space: nowrap;
}
.sr-hltb-force input { accent-color: var(--pl); }
.sr-hltb-msg { font-size: 11px; }
.sr-hltb-msg--ok  { color: #22c55e; }
.sr-hltb-msg--err { color: #f87171; }
.sr-spinner {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: sr-spin .7s linear infinite;
}
@keyframes sr-spin { to { transform: rotate(360deg); } }

/* ── Note ─────────────────────────────────────────────────────────────────── */
.sr-note {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 20%, transparent);
  font-size: var(--fs-sm, 12px); color: var(--muted);
}
.sr-note strong { color: var(--text); }
</style>
