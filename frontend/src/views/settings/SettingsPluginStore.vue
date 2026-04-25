<template>
  <div class="ps-root">

    <!-- Store Sources -->
    <section class="ps-section">
      <div class="ps-section-head">
        <h2 class="ps-section-title">{{ t('pstore.sources') }}</h2>
        <p class="ps-section-sub">{{ t('pstore.sources_desc') }}</p>
      </div>

      <div class="ps-sources">
        <div v-for="src in sources" :key="src.id" class="ps-source">
          <div class="ps-source-info">
            <span class="ps-source-name">{{ src.name }}</span>
            <span class="ps-source-url">{{ src.url }}</span>
          </div>
          <button class="ps-source-del" @click="removeSource(src.id)" title="Remove source">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="ps-source-add">
          <input v-model="newSourceUrl" class="ps-input" placeholder="https://gitea.example.com/.../store.json" @keydown.enter="addSource" />
          <button class="ps-btn ps-btn--primary" :disabled="!newSourceUrl.trim() || addingSource" @click="addSource">
            <span v-if="addingSource" class="ps-spinner" />
            {{ t('pstore.add_source', 'Add Source') }}
          </button>
        </div>
        <div v-if="sourceError" class="ps-error">{{ sourceError }}</div>
      </div>
    </section>

    <!-- Update check settings -->
    <div class="ps-check-interval">
      <span class="ps-check-label">{{ t('pstore.check_interval') }}</span>
      <select v-model="checkInterval" class="ps-input ps-check-select" @change="saveCheckInterval">
        <option value="off">{{ t('pstore.check_off') }}</option>
        <option value="1h">{{ t('pstore.check_1h') }}</option>
        <option value="6h">{{ t('pstore.check_6h') }}</option>
        <option value="24h">{{ t('pstore.check_24h') }}</option>
      </select>
      <button class="ps-btn ps-btn--primary" :disabled="checking" @click="checkNow">
        <span v-if="checking" class="ps-spinner" />
        {{ t('pstore.check_now') }}
      </button>
    </div>

    <!-- Available Plugins -->
    <section class="ps-section">
      <div class="ps-section-head">
        <h2 class="ps-section-title">{{ t('pstore.available') }}</h2>
        <p class="ps-section-sub">{{ t('pstore.available_desc') }}</p>
      </div>

      <!-- Filters -->
      <div class="ps-filters">
        <input v-model="search" class="ps-input ps-search" :placeholder="t('pstore.search')" />
        <div class="ps-filter-tags">
          <button v-for="t in types" :key="t" class="ps-filter-tag" :class="{ active: filterType === t }" @click="filterType = filterType === t ? '' : t">{{ t }}</button>
        </div>
        <button class="ps-btn ps-btn--primary" @click="fetchPlugins" :disabled="browsing">
          <span v-if="browsing" class="ps-spinner" />
          {{ t('pstore.refresh', 'Refresh') }}
        </button>
      </div>

      <!-- Loading -->
      <div v-if="browsing && !plugins.length" class="ps-loading">{{ t('pstore.fetching') }}</div>

      <!-- Empty -->
      <div v-else-if="!filteredPlugins.length && !browsing" class="ps-empty">
        <span v-if="!sources.length">{{ t('pstore.add_source_empty') }}</span>
        <span v-else-if="search || filterType">{{ t('pstore.no_match') }}</span>
        <span v-else>{{ t('pstore.no_plugins') }}</span>
      </div>

      <!-- Plugin grid -->
      <div v-else class="ps-grid">
        <div v-for="p in filteredPlugins" :key="p.id" class="ps-card" @click="openDetail(p)">
          <div class="ps-card-header">
            <img v-if="p.icon" :src="iconUrl(p.icon)" class="ps-card-icon" @error="($event.target as HTMLImageElement).style.display='none'" />
            <div v-else class="ps-card-icon-fallback">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
            </div>
            <div class="ps-card-info">
              <div class="ps-card-name">{{ p.name }}</div>
              <div class="ps-card-author">by {{ p.author }}</div>
            </div>
          </div>
          <div class="ps-card-badges">
            <span class="sp-badge sp-badge--version">v{{ p.version }}</span>
            <span class="sp-badge" :class="typeBadgeClass(p.type)">{{ p.type }}</span>
            <span v-if="p.category && p.category !== p.type" class="sp-badge sp-badge--default">{{ p.category }}</span>
          </div>
          <p class="ps-card-desc">{{ p.description }}</p>
          <div class="ps-card-footer">
            <span v-if="p.updated" class="ps-card-date">{{ p.updated }}</span>
            <span v-if="p._source" class="ps-card-source">{{ p._source }}</span>
          </div>
          <div class="ps-card-action" @click.stop>
            <template v-if="p.installed && p.updateAvailable">
              <button class="ps-btn ps-btn--update" :disabled="installing === p.id" @click="showUpdateConfirm(p)">
                <span v-if="installing === p.id" class="ps-spinner" />
                {{ t('pstore.update') }}
              </button>
            </template>
            <template v-else-if="p.installed">
              <span class="ps-installed-badge">{{ t('pstore.installed') }}</span>
            </template>
            <template v-else>
              <button class="ps-btn ps-btn--primary" :disabled="installing === p.id" @click="installPlugin(p)">
                <span v-if="installing === p.id" class="ps-spinner" />
                {{ t('pstore.install') }}
              </button>
            </template>
          </div>
        </div>
      </div>

      <!-- Fetch errors -->
      <div v-if="fetchErrors.length" class="ps-errors">
        <div v-for="(e, i) in fetchErrors" :key="i" class="ps-error">{{ e.source }}: {{ e.error }}</div>
      </div>
    </section>

    <!-- Detail modal -->
    <teleport to="body">
      <transition name="ps-modal">
        <div v-if="detailPlugin" class="ps-modal-overlay" @click.self="detailPlugin = null">
          <div class="ps-modal">
            <button class="ps-modal-close" @click="detailPlugin = null">&times;</button>
            <div class="ps-modal-header">
              <img v-if="detailPlugin.icon" :src="iconUrl(detailPlugin.icon)" class="ps-modal-icon" />
              <div>
                <h3 class="ps-modal-name">{{ detailPlugin.name }}</h3>
                <div class="ps-modal-meta">
                  <span class="sp-badge sp-badge--version">v{{ detailPlugin.version }}</span>
                  <span class="sp-badge" :class="typeBadgeClass(detailPlugin.type)">{{ detailPlugin.type }}</span>
                  <span class="ps-modal-author">by {{ detailPlugin.author }}</span>
                </div>
              </div>
            </div>
            <p class="ps-modal-desc">{{ detailPlugin.description }}</p>
            <div v-if="detailPlugin.screenshots?.length" class="ps-modal-screenshots">
              <img v-for="(s, i) in detailPlugin.screenshots" :key="i" :src="s" class="ps-modal-screenshot" @click="lightboxScreenshots = detailPlugin.screenshots; lightboxIdx = i" />
            </div>
            <div class="ps-modal-details">
              <div v-if="detailPlugin.gdVersionMin"><strong>Min GD Version:</strong> {{ detailPlugin.gdVersionMin }}</div>
              <div v-if="detailPlugin.repository"><strong>Repository:</strong> <a :href="detailPlugin.repository" target="_blank">{{ detailPlugin.repository }}</a></div>
              <div v-if="detailPlugin.updated"><strong>Updated:</strong> {{ detailPlugin.updated }}</div>
              <div v-if="detailPlugin.downloadSize"><strong>Size:</strong> {{ formatSize(detailPlugin.downloadSize) }}</div>
            </div>
            <div v-if="detailPlugin.changelog" class="ps-modal-changelog">
              <strong>{{ t('pstore.changelog') }}:</strong>
              <pre class="ps-changelog-text">{{ detailPlugin.changelog }}</pre>
            </div>
            <div class="ps-modal-actions">
              <template v-if="detailPlugin.installed && !detailPlugin.updateAvailable">
                <span class="ps-installed-badge">{{ t('pstore.installed') }} (v{{ detailPlugin.installedVersion }})</span>
              </template>
              <template v-else-if="detailPlugin.installed && detailPlugin.updateAvailable">
                <span class="ps-version-transition">v{{ detailPlugin.installedVersion }} → v{{ detailPlugin.version }}</span>
                <button class="ps-btn ps-btn--update ps-btn--lg" :disabled="installing === detailPlugin.id" @click="installPlugin(detailPlugin)">
                  <span v-if="installing === detailPlugin.id" class="ps-spinner" />
                  {{ t('pstore.update') }}
                </button>
              </template>
              <template v-else>
                <button class="ps-btn ps-btn--primary ps-btn--lg" :disabled="installing === detailPlugin.id" @click="installPlugin(detailPlugin)">
                  <span v-if="installing === detailPlugin.id" class="ps-spinner" />
                  {{ t('pstore.install') }}
                </button>
              </template>
            </div>
          </div>
        </div>
      </transition>
    </teleport>

    <!-- Restart banner -->
    <div v-if="needsRestart" class="ps-restart-banner">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
      <span>{{ t('pstore.restart_needed') }}</span>
      <button class="ps-btn ps-btn--primary" :disabled="restarting" @click="restartContainer">
        <span v-if="restarting" class="ps-spinner" />
        {{ t('pstore.restart_now') }}
      </button>
    </div>

    <!-- Status message -->
    <div v-if="statusMsg" class="ps-status" :class="statusOk ? 'ps-status--ok' : 'ps-status--err'">{{ statusMsg }}</div>

    <!-- Screenshot lightbox -->
    <teleport to="body">
      <transition name="ps-modal">
        <div v-if="lightboxImg" class="ps-lightbox" @click="lightboxIdx = -1">
          <button v-if="lightboxIdx > 0" class="ps-lightbox-nav ps-lightbox-prev" @click.stop="lightboxIdx--">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <img :src="lightboxImg" class="ps-lightbox-img" @click.stop />
          <button v-if="lightboxIdx < lightboxScreenshots.length - 1" class="ps-lightbox-nav ps-lightbox-next" @click.stop="lightboxIdx++">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <div class="ps-lightbox-counter">{{ lightboxIdx + 1 }} / {{ lightboxScreenshots.length }}</div>
          <button class="ps-lightbox-close" @click="lightboxIdx = -1">&times;</button>
        </div>
      </transition>
    </teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()
const { gdConfirm } = useDialog()

interface StoreSource { id: number; name: string; url: string; enabled: boolean }
interface StorePlugin {
  id: string; name: string; description: string; version: string; author: string
  type: string; category?: string; icon?: string; screenshots?: string[]
  downloadUrl: string; downloadSize?: number; gdVersionMin?: string
  repository?: string; updated?: string; changelog?: string
  installed: boolean; installedVersion: string | null; updateAvailable: boolean
  _source?: string; _sourceUrl?: string
}

const sources = ref<StoreSource[]>([])
const newSourceUrl = ref('')
const addingSource = ref(false)
const sourceError = ref('')

const plugins = ref<StorePlugin[]>([])
const browsing = ref(false)
const fetchErrors = ref<{ source: string; error: string }[]>([])
const search = ref('')
const filterType = ref('')
const installing = ref<string | null>(null)
const detailPlugin = ref<StorePlugin | null>(null)
const statusMsg = ref('')
const statusOk = ref(true)
const checkInterval = ref(localStorage.getItem('gd3_plugin_check_interval') || '6h')
const checking = ref(false)
function saveCheckInterval() { localStorage.setItem('gd3_plugin_check_interval', checkInterval.value) }
async function checkNow() {
  checking.value = true
  try {
    const { data } = await client.get('/plugins/store/updates')
    localStorage.setItem('gd3_plugin_check_last', String(Date.now()))
    if (data.count > 0) {
      const { useNotificationStore } = await import('@/stores/notifications')
      const details = data.updates.map((u: any) => `${u.name}: ${u.installed} -> ${u.available}`)
      useNotificationStore().add({ id: 'plugin-updates', count: data.count, label: t('pstore.updates_badge'), details, action: '/settings?tab=pluginstore', actionLabel: t('pstore.go_to_store') })
      statusMsg.value = `${data.count} ${t('pstore.updates_badge')}`; statusOk.value = true
    } else {
      statusMsg.value = t('pstore.no_updates'); statusOk.value = true
    }
    await fetchPlugins()
    setTimeout(() => { statusMsg.value = '' }, 4000)
  } catch { statusMsg.value = 'Check failed'; statusOk.value = false }
  finally { checking.value = false }
}
const lightboxIdx = ref(-1)
const lightboxScreenshots = ref<string[]>([])
const lightboxImg = computed(() => lightboxIdx.value >= 0 ? lightboxScreenshots.value[lightboxIdx.value] || '' : '')
const needsRestart = ref(false)
const restarting = ref(false)

const types = ['theme', 'metadata', 'lifecycle', 'widget', 'download', 'library']

const filteredPlugins = computed(() => {
  let list = plugins.value
  if (filterType.value) list = list.filter(p => p.type === filterType.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || p.author.toLowerCase().includes(q))
  }
  return list
})

function typeBadgeClass(type: string): string {
  const map: Record<string, string> = { metadata: 'sp-badge--metadata', download: 'sp-badge--download', library: 'sp-badge--library', theme: 'sp-badge--theme', widget: 'sp-badge--widget', lifecycle: 'sp-badge--lifecycle' }
  return map[type] || 'sp-badge--default'
}

function iconUrl(url: string | undefined): string {
  if (!url) return ''
  return `/api/plugins/store/icon?url=${encodeURIComponent(url)}`
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

async function fetchSources() {
  try {
    const { data } = await client.get('/plugins/store/sources')
    sources.value = data
  } catch { /* ignore */ }
}

async function addSource() {
  const url = newSourceUrl.value.trim()
  if (!url) return
  addingSource.value = true; sourceError.value = ''
  try {
    await client.post('/plugins/store/sources', { url, name: '' })
    newSourceUrl.value = ''
    await fetchSources()
    await fetchPlugins()
  } catch (err: any) {
    sourceError.value = err?.response?.data?.detail || 'Failed to add source'
  } finally { addingSource.value = false }
}

async function removeSource(id: number) {
  try {
    await client.delete(`/plugins/store/sources/${id}`)
    await fetchSources()
    plugins.value = plugins.value.filter(p => {
      const src = sources.value.find(s => s.url === p._sourceUrl)
      return src !== undefined
    })
  } catch { /* ignore */ }
}

async function fetchPlugins() {
  browsing.value = true; fetchErrors.value = []
  try {
    const { data } = await client.get('/plugins/store/browse')
    plugins.value = data.plugins || []
    fetchErrors.value = data.errors || []
  } catch { /* ignore */ }
  finally { browsing.value = false }
}

async function installPlugin(p: StorePlugin) {
  const ok = await gdConfirm(t('pstore.install_confirm', `Install plugin "${p.name}" v${p.version}?`), { title: t('pstore.install', 'Install Plugin'), confirmText: t('pstore.install', 'Install') })
  if (!ok) return
  installing.value = p.id; statusMsg.value = ''
  try {
    await client.post('/plugins/store/install', { downloadUrl: p.downloadUrl })
    statusMsg.value = `${p.name} installed successfully!`; statusOk.value = true
    p.installed = true; p.installedVersion = p.version; p.updateAvailable = false
    if (p.type === 'theme') needsRestart.value = true
    setTimeout(() => { statusMsg.value = '' }, 6000)
  } catch (err: any) {
    statusMsg.value = err?.response?.data?.detail || 'Install failed'; statusOk.value = false
    setTimeout(() => { statusMsg.value = '' }, 6000)
  } finally { installing.value = null }
}

function openDetail(p: StorePlugin) { detailPlugin.value = p }

function showUpdateConfirm(p: StorePlugin) {
  detailPlugin.value = p
}

async function restartContainer() {
  restarting.value = true
  try {
    await client.post('/plugins/restart')
    statusMsg.value = t('pstore.restarting'); statusOk.value = true
    // Wait for container to come back
    setTimeout(() => { window.location.reload() }, 8000)
  } catch {
    statusMsg.value = 'Restart failed'; statusOk.value = false
    restarting.value = false
  }
}

onMounted(async () => {
  await fetchSources()
  if (sources.value.length) await fetchPlugins()
})
</script>

<style scoped>
.ps-root { display: flex; flex-direction: column; gap: 28px; }

/* Sections */
.ps-section { display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.ps-section-head { padding: 0 2px; }
.ps-section-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); margin: 0 0 2px; }
.ps-section-sub { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }

/* Sources */
.ps-sources { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.ps-source { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: var(--radius-sm, 8px); background: var(--glass-bg); border: 1px solid var(--glass-border); }
.ps-source-info { flex: 1; min-width: 0; }
.ps-source-name { font-weight: 600; font-size: 13px; display: block; }
.ps-source-url { font-size: 11px; color: var(--muted); word-break: break-all; }
.ps-source-del { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); color: rgba(255,255,255,.5); cursor: pointer; padding: 6px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.ps-source-del:hover { color: #f87171; background: rgba(248,113,113,.12); border-color: rgba(248,113,113,.3); }
.ps-source-add { display: flex; gap: var(--space-2, 8px); }
.ps-check-interval { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 10px 14px; border-radius: var(--radius-sm, 8px); background: var(--glass-bg, rgba(255,255,255,.03)); border: 1px solid var(--glass-border, rgba(255,255,255,.08)); }
.ps-check-label { font-size: var(--fs-sm, 12px); color: var(--muted); font-weight: 600; }
.ps-check-select { width: auto; min-width: 120px; }

/* Inputs & Buttons */
.ps-input { flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid color-mix(in srgb, var(--pl) 20%, transparent); background: color-mix(in srgb, var(--pl) 8%, transparent); color: var(--text); font-size: 13px; outline: none; }
.ps-input:focus { border-color: var(--pl); }
.ps-search { max-width: 280px; }
.ps-btn { padding: 8px 16px; opacity: .6; border-radius: 6px; border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); background: color-mix(in srgb, var(--pl) 20%, transparent); color: var(--pl-light); font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: all .15s; }
.ps-btn:hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }
.ps-btn:disabled { opacity: .5; cursor: not-allowed; }
.ps-btn--primary { /* same as base - kept for semantic clarity */ }
.ps-btn--update { background: rgba(251,146,60,.2); border-color: rgba(251,146,60,.4); color: #fb923c; }
.ps-btn--lg { padding: 10px 24px; font-size: var(--fs-md, 14px); }

/* Filters */
.ps-filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ps-filter-tags { display: flex; gap: var(--space-1, 4px); }
.ps-filter-tag { padding: 4px 10px; border-radius: 99px; border: 1px solid var(--glass-border); background: rgba(255,255,255,.04); color: var(--muted); font-size: 11px; font-weight: 600; cursor: pointer; text-transform: capitalize; transition: all .15s; }
.ps-filter-tag.active { background: color-mix(in srgb, var(--pl) 20%, transparent); border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: var(--pl-light, #fff); }
.ps-filter-tag:hover:not(.active) { background: rgba(255,255,255,.08); }

/* Grid */
.ps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.ps-card { padding: var(--space-4, 16px); border-radius: 10px; border: 1px solid var(--glass-border); background: var(--glass-bg); cursor: pointer; transition: all .2s; display: flex; flex-direction: column; gap: var(--space-2, 8px); position: relative; }
.ps-card:hover { border-color: var(--pl); box-shadow: 0 4px 20px rgba(0,0,0,.2); transform: translateY(-2px); }
.ps-card-header { display: flex; align-items: center; gap: 10px; }
.ps-card-icon { width: 36px; height: 36px; border-radius: var(--radius-sm, 8px); object-fit: contain; }
.ps-card-icon-fallback { width: 36px; height: 36px; border-radius: var(--radius-sm, 8px); background: rgba(255,255,255,.06); display: flex; align-items: center; justify-content: center; color: var(--muted); }
.ps-card-info { flex: 1; min-width: 0; }
.ps-card-name { font-weight: 700; font-size: var(--fs-md, 14px); }
.ps-card-author { font-size: 11px; color: var(--muted); }
.ps-card-badges { display: flex; gap: 5px; flex-wrap: wrap; }
.ps-card-desc { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin: 0; }
.ps-card-footer { display: flex; gap: var(--space-3, 12px); font-size: 11px; color: var(--muted); margin-top: auto; }
.ps-card-action { position: absolute; top: 14px; right: 14px; }
.ps-installed-badge { padding: 4px 10px; border-radius: 99px; background: rgba(74,222,128,.12); color: #4ade80; font-size: 11px; font-weight: 600; border: 1px solid rgba(74,222,128,.3); }

/* Loading & Empty */
.ps-loading { padding: var(--space-8, 32px); text-align: center; color: var(--muted); font-size: 13px; }
.ps-empty { padding: var(--space-8, 32px); text-align: center; color: var(--muted); font-size: 13px; }
.ps-error { padding: 6px 10px; border-radius: 6px; background: rgba(248,113,113,.1); color: #f87171; font-size: var(--fs-sm, 12px); }
.ps-errors { display: flex; flex-direction: column; gap: var(--space-1, 4px); }

/* Restart banner */
.ps-restart-banner {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: var(--radius-sm, 8px);
  background: color-mix(in srgb, var(--pl) 12%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light); font-size: 13px; font-weight: 600;
}
.ps-restart-banner svg { flex-shrink: 0; color: var(--pl); }
.ps-restart-banner span { flex: 1; }

/* Status toast */
.ps-status { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); padding: 10px 24px; border-radius: var(--radius-sm, 8px); font-size: 13px; font-weight: 600; z-index: 1000; box-shadow: 0 4px 20px rgba(0,0,0,.3); }
.ps-status--ok { background: rgba(74,222,128,.15); color: #4ade80; border: 1px solid rgba(74,222,128,.3); }
.ps-status--err { background: rgba(248,113,113,.15); color: #f87171; border: 1px solid rgba(248,113,113,.3); }

/* Spinner */
.ps-spinner { width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.2); border-top-color: currentColor; border-radius: 50%; animation: ps-spin .6s linear infinite; display: inline-block; }
@keyframes ps-spin { to { transform: rotate(360deg); } }

/* Modal */
.ps-modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 900; backdrop-filter: blur(4px); }
.ps-modal { background: var(--bg2, #0f0f1a); border: 1px solid var(--glass-border); border-radius: var(--radius, 12px); padding: 28px; max-width: 560px; width: 90%; max-height: 80vh; overflow-y: auto; position: relative; }
.ps-modal-close { position: absolute; top: 12px; right: 14px; background: none; border: none; color: var(--muted); font-size: 24px; cursor: pointer; }
.ps-modal-header { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
.ps-modal-icon { width: 48px; height: 48px; border-radius: 10px; object-fit: contain; }
.ps-modal-name { font-size: var(--fs-xl, 18px); font-weight: 700; margin: 0; }
.ps-modal-meta { display: flex; gap: 6px; align-items: center; margin-top: 4px; }
.ps-modal-author { font-size: var(--fs-sm, 12px); color: var(--muted); }
.ps-modal-desc { font-size: 13px; color: var(--muted); line-height: 1.6; }
.ps-modal-screenshots { display: flex; gap: var(--space-2, 8px); overflow-x: auto; padding: 8px 0; }
.ps-modal-screenshot { height: 160px; border-radius: var(--radius-sm, 8px); border: 1px solid var(--glass-border); cursor: pointer; transition: all .2s; }
.ps-modal-screenshot:hover { border-color: var(--pl); transform: scale(1.03); }

/* Screenshot lightbox */
.ps-lightbox { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,.9); display: flex; align-items: center; justify-content: center; cursor: pointer; }
.ps-lightbox-img { max-width: 92vw; max-height: 90vh; object-fit: contain; border-radius: var(--radius-sm, 8px); cursor: default; box-shadow: 0 0 60px rgba(0,0,0,.8); }
.ps-lightbox-close { position: absolute; top: 16px; right: 20px; background: none; border: none; color: rgba(255,255,255,.6); font-size: 32px; cursor: pointer; }
.ps-lightbox-close:hover { color: #fff; }
.ps-lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.2); border-radius: 50%; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.7); cursor: pointer; transition: all .15s; }
.ps-lightbox-nav:hover { background: rgba(255,255,255,.2); color: #fff; }
.ps-lightbox-prev { left: 20px; }
.ps-lightbox-next { right: 20px; }
.ps-lightbox-counter { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); color: rgba(255,255,255,.5); font-size: 13px; }
.ps-modal-details { font-size: var(--fs-sm, 12px); color: var(--muted); display: flex; flex-direction: column; gap: var(--space-1, 4px); margin: 12px 0; }
.ps-modal-details a { color: var(--pl); }
.ps-modal-changelog { margin: 12px 0; padding: 10px 14px; border-radius: var(--radius-sm, 8px); background: rgba(255,255,255,.03); border: 1px solid var(--glass-border); }
.ps-modal-changelog strong { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--pl); }
.ps-changelog-text { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.6; margin: 6px 0 0; white-space: pre-wrap; font-family: inherit; }
.ps-version-transition { font-size: 13px; font-weight: 700; color: #fb923c; display: flex; align-items: center; gap: 6px; }
.ps-modal-actions { display: flex; gap: var(--space-2, 8px); justify-content: flex-end; align-items: center; margin-top: 16px; }

/* Modal transition */
.ps-modal-enter-active { transition: all .25s ease; }
.ps-modal-leave-active { transition: all .2s ease; }
.ps-modal-enter-from, .ps-modal-leave-to { opacity: 0; }
.ps-modal-enter-from .ps-modal, .ps-modal-leave-to .ps-modal { transform: scale(.95); }
</style>
