<!--
  Emulator firmware.

  Grouped by emulator core rather than by console, because several consoles
  share one: supplying the Mega CD BIOS once covers Mega Drive, Mega CD and
  Game Gear, and listing them apart would ask for the same file four times.
  Each row therefore names the consoles it covers.

  Only cores behind platforms actually in the library are shown by default. The
  full list is 27 cores and most of them are irrelevant to any one person.

  Nothing here depends on a plugin: firmware is supplied from disk, the same way
  a ROM can be copied in by hand. A plugin may later offer to fetch a missing
  file, which is an addition to this screen rather than a precondition for it.
-->
<template>
  <div class="fw">
    <div v-if="loading" class="fw-loading">{{ t('fw.loading', 'Reading the firmware store…') }}</div>

    <template v-else>
      <div v-if="!visibleRows.length" class="fw-note">
        {{ showAll
          ? t('fw.none_at_all', 'No bundled core asks for firmware.')
          : t('fw.none_for_library', 'Nothing in your library needs firmware. Consoles that do will appear here once you add one.') }}
      </div>

      <div v-for="row in visibleRows" :key="row.core" class="fw-card">
        <button class="fw-head" @click="toggle(row.core)">
          <div class="fw-head-text">
            <span class="fw-title">{{ row.consoles || row.core }}</span>
            <span class="fw-sub">{{ row.libretro_core }}</span>
          </div>
          <span class="fw-chip" :class="chipClass(row)">{{ chipText(row) }}</span>
          <svg class="fw-chevron" :class="{ 'fw-chevron--open': open[row.core] }"
               width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <div v-if="open[row.core]" class="fw-body">
          <div v-if="!files[row.core]" class="fw-loading">{{ t('fw.loading_files', 'Loading…') }}</div>
          <div v-else>
            <div v-for="f in files[row.core]" :key="f.path" class="fw-file">
              <span class="fw-dot" :class="f.present ? 'fw-dot--on' : (f.optional ? 'fw-dot--opt' : 'fw-dot--miss')" />
              <div class="fw-file-text">
                <span class="fw-path">
                  {{ f.path }}
                  <span v-if="!f.optional" class="fw-req">{{ t('fw.required', 'required') }}</span>
                </span>
                <span class="fw-desc">{{ f.desc }}</span>
                <span v-if="f.present" class="fw-meta">MD5 {{ f.md5 }} · {{ prettySize(f.size) }}</span>
              </div>
              <div class="fw-actions">
                <button
                  v-if="!f.present && offers[row.core]?.[f.path]"
                  class="fw-btn fw-btn--primary"
                  :disabled="fetching === f.path"
                  @click="fetchFile(row.core, f.path)"
                >
                  {{ fetching === f.path
                    ? t('fw.fetching', 'Fetching…')
                    : t('fw.fetch_from', 'Fetch from {source}').replace('{source}', offers[row.core][f.path].source || '?') }}
                </button>
                <label class="fw-btn" :class="{ 'fw-btn--primary': !offers[row.core]?.[f.path] }">
                  {{ f.present ? t('fw.replace', 'Replace') : t('fw.upload', 'Upload') }}
                  <input type="file" hidden @change="onPick(row.core, f.path, $event)" />
                </label>
                <button v-if="f.present" class="fw-btn" @click="remove(row.core, f.path)">
                  {{ t('fw.remove', 'Remove') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- WHDLoad. Its own card because these are not firmware for a core:
           they are the two free pieces the Amiga hard-drive installs need
           beside a Kickstart, and the Kickstarts themselves stay in the amiga
           row above rather than being asked for twice. -->
      <div v-if="whd" class="fw-card">
        <button class="fw-head" @click="whdOpen = !whdOpen">
          <div class="fw-head-text">
            <span class="fw-title">{{ t('whd.title', 'WHDLoad (Amiga hard-drive installs)') }}</span>
            <span class="fw-sub">whdload.de · aminet.net</span>
          </div>
          <span class="fw-chip" :class="whdChipClass">{{ whdChipText }}</span>
          <svg class="fw-chevron" :class="{ 'fw-chevron--open': whdOpen }"
               width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <div v-if="whdOpen" class="fw-body">
          <div v-for="f in whdFiles" :key="f.name" class="fw-file">
            <span class="fw-dot" :class="f.present ? 'fw-dot--on' : (f.optional ? 'fw-dot--opt' : 'fw-dot--miss')" />
            <div class="fw-file-text">
              <span class="fw-path">
                {{ f.name }}
                <span v-if="!f.optional" class="fw-req">{{ t('fw.required', 'required') }}</span>
              </span>
              <span class="fw-desc">{{ f.desc }}</span>
              <span v-if="f.present && f.size" class="fw-meta">{{ prettySize(f.size) }}</span>
            </div>
            <div class="fw-actions">
              <button v-if="!f.present" class="fw-btn fw-btn--primary"
                      :disabled="fetching === f.name" @click="whdFetch(f.name)">
                {{ fetching === f.name
                  ? t('fw.fetching', 'Fetching…')
                  : t('fw.fetch_from', 'Fetch from {source}').replace('{source}', f.source) }}
              </button>
              <label class="fw-btn" :class="{ 'fw-btn--primary': f.present }">
                {{ f.present ? t('fw.replace', 'Replace') : t('fw.upload', 'Upload') }}
                <input type="file" hidden @change="whdPick(f.name, $event)" />
              </label>
              <button v-if="f.present" class="fw-btn" @click="whdRemove(f.name)">
                {{ t('fw.remove', 'Remove') }}
              </button>
            </div>
          </div>

          <!-- Not an item to supply: it is here so a missing Kickstart explains
               itself where the consequence shows, instead of leaving somebody
               wondering why the tables list is empty. -->
          <div class="fw-file">
            <span class="fw-dot" :class="whd.kickstart.present ? 'fw-dot--on' : 'fw-dot--miss'" />
            <div class="fw-file-text">
              <span class="fw-path">{{ t('whd.kickstart', 'Kickstart ROM') }}</span>
              <span class="fw-desc">
                {{ whd.kickstart.present
                  ? t('whd.kickstart_have', 'Using {name}. Supplied in the Amiga row above.').replace('{name}', whd.kickstart.name || '')
                  : t('whd.kickstart_none', 'None supplied. Add one in the Amiga row above - a hard-drive install cannot boot without it, and GD will not fetch one for you.') }}
              </span>
            </div>
          </div>

          <div class="fw-foot">
            <button class="fw-btn fw-btn--primary" :disabled="fetching === '*'" @click="whdFetch()">
              {{ fetching === '*'
                ? t('fw.fetching', 'Fetching…')
                : t('whd.fetch_all', 'Fetch everything that can be fetched') }}
            </button>
            <span class="fw-desc">{{ t('whd.fetch_note', 'Kickstarts are never fetched: they are somebody\'s property and stay yours to supply.') }}</span>
          </div>
        </div>
      </div>

      <div class="fw-foot">
        <button class="fw-btn" @click="showAll = !showAll">
          {{ showAll ? t('fw.only_mine', 'Only consoles I have') : t('fw.show_all', 'Show every core') }}
        </button>
        <span v-if="msg" class="fw-msg" :class="{ 'fw-msg--bad': msgBad }">{{ msg }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { getEjsCore } from '@/utils/ejsCores'

const { t } = useI18n()

interface Platform { fs_slug: string; name: string; rom_count: number }
interface CoreRow {
  core: string; libretro_core: string | null
  total: number; present: number; required: number; missing_required: number
  consoles?: string
}
interface FwFile {
  path: string; desc: string; optional: boolean
  present: boolean; size: number | null; md5: string | null
}

const props = defineProps<{ platforms: Platform[] }>()

const rows    = ref<CoreRow[]>([])
const files   = reactive<Record<string, FwFile[]>>({})
// What an installed plugin says it could fetch. Stays empty when none is
// installed, and the screen is expected to work exactly the same then.
const offers  = reactive<Record<string, Record<string, { source: string }>>>({})
const fetching = ref('')
const open    = reactive<Record<string, boolean>>({})
const loading = ref(true)
const showAll = ref(false)
const msg     = ref('')
const msgBad  = ref(false)

// Cores behind the platforms that actually hold ROMs, with the console names
// they answer for. A core with no platform here is still real, just not this
// person's concern until they add one.
const mine = computed(() => {
  const names: Record<string, string[]> = {}
  for (const p of props.platforms) {
    const core = getEjsCore(p.fs_slug)
    if (!core) continue
    ;(names[core] ||= []).push(p.name)
  }
  return names
})

const visibleRows = computed(() => {
  const owned = mine.value
  return rows.value
    .filter(r => showAll.value || owned[r.core])
    .map(r => ({ ...r, consoles: (owned[r.core] || []).join(', ') }))
})

function chipText(r: CoreRow) {
  if (r.missing_required) return t('fw.missing_required', '{n} required missing').replace('{n}', String(r.missing_required))
  if (r.present === r.total) return t('fw.complete', 'complete')
  if (r.present) return `${r.present}/${r.total}`
  return t('fw.empty', 'nothing supplied')
}
function chipClass(r: CoreRow) {
  if (r.missing_required) return 'fw-chip--bad'
  if (r.present) return 'fw-chip--ok'
  return ''
}

function prettySize(n: number | null) {
  if (!n) return ''
  return n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`
}

function say(text: string, bad = false) {
  msg.value = text; msgBad.value = bad
  setTimeout(() => { if (msg.value === text) msg.value = '' }, 6000)
}

async function loadRows() {
  loading.value = true
  try { rows.value = (await client.get('/firmware')).data }
  catch { say(t('fw.load_failed', 'Could not read the firmware store.'), true) }
  finally { loading.value = false }
}

async function loadFiles(core: string) {
  try { files[core] = (await client.get(`/firmware/${core}`)).data.files }
  catch { say(t('fw.load_failed', 'Could not read the firmware store.'), true) }
  // Offers are a bonus, not part of the screen working: a plugin that is slow,
  // broken or absent must not stop the file list from being usable.
  try { offers[core] = (await client.get(`/firmware/${core}/offers`)).data.offers || {} }
  catch { offers[core] = {} }
}

async function fetchFile(core: string, path: string) {
  fetching.value = path
  try {
    await client.post(`/firmware/${core}/fetch`, new URLSearchParams({ path }))
    say(t('fw.stored', 'Stored {name}').replace('{name}', path))
    await Promise.all([loadFiles(core), loadRows()])
  } catch (e: any) {
    say(e?.response?.data?.detail || t('fw.fetch_failed', 'Could not fetch that file.'), true)
  } finally {
    fetching.value = ''
  }
}

function toggle(core: string) {
  open[core] = !open[core]
  if (open[core] && !files[core]) loadFiles(core)
}

async function onPick(core: string, path: string, ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''            // so picking the same file again still fires
  if (!file) return
  const fd = new FormData()
  fd.append('path', path)
  fd.append('file', file)
  try {
    await client.post(`/firmware/${core}`, fd)
    say(t('fw.stored', 'Stored {name}').replace('{name}', path))
    await Promise.all([loadFiles(core), loadRows()])
  } catch (e: any) {
    say(e?.response?.data?.detail || t('fw.store_failed', 'Could not store that file.'), true)
  }
}

// ── WHDLoad ──────────────────────────────────────────────────────────────────
// Read from its own endpoint rather than folded into the core list, because it
// is not a core: the tables are per Kickstart on hand, so the rows only exist
// once somebody has supplied one.

interface WhdStatus {
  whdload: { present: boolean; size: number }
  kickstart: { present: boolean; name: string | null; aga_only: boolean; accepted: string[] }
  relocation_tables: { kickstart: string; name: string; present: boolean }[]
}

const whd = ref<WhdStatus | null>(null)
const whdOpen = ref(false)

const whdFiles = computed(() => {
  const s = whd.value
  if (!s) return []
  return [
    {
      name: 'WHDLoad', present: s.whdload.present, size: s.whdload.size, optional: false,
      source: 'whdload.de',
      desc: t('whd.whdload_desc', 'The loader itself. Every hard-drive install runs through it.'),
    },
    ...s.relocation_tables.map(r => ({
      name: r.name, present: r.present, size: 0, optional: true,
      source: 'Aminet',
      desc: t('whd.rtb_desc', 'Relocation table for {ks}. Without it some titles run, others stop at a black screen.')
        .replace('{ks}', r.kickstart),
    })),
  ]
})

const whdChipText = computed(() => {
  const files = whdFiles.value
  if (!whd.value?.whdload.present) return t('whd.no_loader', 'WHDLoad missing')
  const missing = files.filter(f => !f.present).length
  return missing
    ? t('whd.tables_missing', '{n} tables missing').replace('{n}', String(missing))
    : t('fw.complete', 'complete')
})
const whdChipClass = computed(() => {
  if (!whd.value?.whdload.present) return 'fw-chip--bad'
  return whdFiles.value.every(f => f.present) ? 'fw-chip--ok' : ''
})

async function loadWhd() {
  // A card that fails to load is left out entirely rather than shown broken:
  // it is one platform's concern and must not spoil the firmware screen.
  try { whd.value = (await client.get('/whdload/support')).data }
  catch { whd.value = null }
}

async function whdFetch(name?: string) {
  fetching.value = name || '*'
  try {
    const { data } = await client.post('/whdload/support/fetch', null,
      name ? { params: { name } } : undefined)
    const failed = Object.entries(data.failed || {})
    if (data.fetched?.length) say(t('fw.stored', 'Stored {name}').replace('{name}', data.fetched.join(', ')))
    // "not published" is the honest answer for a beta ROM nobody wrote a table
    // for, so it reads as a fact rather than as something to retry.
    if (failed.length) {
      say(failed.map(([f, why]) => `${f}: ${why}`).join(' · '), true)
    } else if (!data.fetched?.length) {
      say(t('whd.nothing_to_fetch', 'Nothing to fetch - everything is already here.'))
    }
    await loadWhd()
  } catch (e: any) {
    say(e?.response?.data?.detail || t('fw.fetch_failed', 'Could not fetch that file.'), true)
  } finally {
    fetching.value = ''
  }
}

async function whdPick(name: string, ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const fd = new FormData()
  fd.append('name', name)
  fd.append('file', file)
  try {
    await client.post('/whdload/support', fd)
    say(t('fw.stored', 'Stored {name}').replace('{name}', name))
    await loadWhd()
  } catch (e: any) {
    say(e?.response?.data?.detail || t('fw.store_failed', 'Could not store that file.'), true)
  }
}

async function whdRemove(name: string) {
  try {
    await client.delete('/whdload/support', { params: { name } })
    say(t('fw.removed', 'Removed {name}').replace('{name}', name))
    await loadWhd()
  } catch {
    say(t('fw.remove_failed', 'Could not remove that file.'), true)
  }
}

async function remove(core: string, path: string) {
  try {
    await client.delete(`/firmware/${core}`, { params: { path } })
    say(t('fw.removed', 'Removed {name}').replace('{name}', path))
    await Promise.all([loadFiles(core), loadRows()])
  } catch {
    say(t('fw.remove_failed', 'Could not remove that file.'), true)
  }
}

onMounted(() => { loadRows(); loadWhd() })
</script>

<style scoped>
.fw { display: flex; flex-direction: column; gap: 8px; }
.fw-loading, .fw-note { font-size: var(--fs-sm, 12px); color: var(--muted); padding: 6px 2px; }

.fw-card {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  background: var(--glass-bg); overflow: hidden;
}
.fw-head {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: none; border: 0; cursor: pointer;
  font-family: inherit; text-align: left; color: var(--text);
}
.fw-head-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.fw-title { font-size: 13px; font-weight: 600; color: var(--text); }
.fw-sub   { font-size: 11px; color: var(--muted); font-family: var(--font-mono, monospace); }

.fw-chip {
  flex-shrink: 0; font-size: 11px; font-weight: 600; padding: 3px 9px;
  border-radius: 999px; color: var(--muted);
  background: rgba(255,255,255,.05); border: 1px solid var(--glass-border);
}
.fw-chip--ok {
  background: color-mix(in srgb, var(--success, #4ade80) 18%, transparent);
  border-color: color-mix(in srgb, var(--success, #4ade80) 40%, transparent);
  color: var(--success, #4ade80);
}
.fw-chip--bad {
  background: color-mix(in srgb, #fbbf24 18%, transparent);
  border-color: color-mix(in srgb, #fbbf24 40%, transparent);
  color: #fbbf24;
}
.fw-chevron { flex-shrink: 0; color: var(--muted); transition: transform var(--transition); }
.fw-chevron--open { transform: rotate(180deg); }

.fw-body { border-top: 1px solid var(--glass-border); padding: 4px 12px 10px; }
.fw-file { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,.04); }
.fw-file:last-child { border-bottom: 0; }
.fw-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--muted); opacity: .35; }
.fw-dot--on   { background: var(--success, #4ade80); opacity: 1; }
.fw-dot--miss { background: #fbbf24; opacity: 1; }
.fw-dot--opt  { opacity: .3; }
.fw-file-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.fw-path { font-size: 12px; font-weight: 600; color: var(--text); font-family: var(--font-mono, monospace); }
.fw-req {
  margin-left: 6px; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 999px;
  font-family: inherit; color: #fbbf24;
  background: color-mix(in srgb, #fbbf24 15%, transparent);
  border: 1px solid color-mix(in srgb, #fbbf24 30%, transparent);
}
.fw-desc { font-size: 11px; color: var(--muted); }
.fw-meta { font-size: 10px; color: var(--muted); opacity: .75; font-family: var(--font-mono, monospace); }
.fw-actions { display: flex; gap: 6px; flex-shrink: 0; }

.fw-btn {
  padding: 5px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.fw-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.fw-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
}
.fw-btn--primary:hover {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}

.fw-foot { display: flex; align-items: center; gap: 10px; padding-top: 2px; }
/* The same row inside a card needs to read as a footer rather than as one more
   file, so it gets the rule the file rows drop on their last one. */
.fw-body .fw-foot {
  flex-wrap: wrap; margin-top: 6px; padding-top: 10px;
  border-top: 1px solid rgba(255,255,255,.04);
}
.fw-msg { font-size: var(--fs-sm, 12px); color: var(--success, #4ade80); }
.fw-msg--bad { color: #fbbf24; }
</style>
