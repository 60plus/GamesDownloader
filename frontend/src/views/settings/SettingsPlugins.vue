<template>
  <div class="sp-root">

    <!-- Installed Plugins -->
    <section class="sp-section">
      <div class="sp-section-head">
        <h2 class="sp-section-title">{{ t('plugins.installed') }}</h2>
        <p class="sp-section-sub">{{ t('plugins.installed_desc') }}</p>
      </div>

      <div v-if="loading" class="sp-loading">{{ t('plugins.loading') }}</div>

      <!-- Empty state -->
      <div v-else-if="!plugins.length" class="sp-empty">
        <svg class="sp-empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
        <span class="sp-empty-title">{{ t('plugins.empty_title', 'No plugins installed') }}</span>
        <span class="sp-empty-sub">{{ t('plugins.empty_subtitle', 'Upload a .zip plugin file to get started') }}</span>
      </div>

      <!-- Plugin grid -->
      <div v-else class="sp-plugin-grid">
        <div v-for="p in plugins" :key="p.plugin_id" class="sp-plugin">

          <!-- Header row: logo + info + actions -->
          <div class="sp-plugin-header">
            <img
              v-if="p.has_logo"
              :src="pluginLogoUrl(p.plugin_id)"
              :alt="p.name"
              class="sp-plugin-logo"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
            <div v-else class="sp-plugin-logo-fallback">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>

            <div class="sp-plugin-info">
              <div class="sp-plugin-name-row">
                <span class="sp-plugin-name">{{ p.name }}</span>
                <span class="sp-badge sp-badge--version">v{{ p.version }}</span>
                <span class="sp-badge" :class="typeBadgeClass(p.plugin_type)">{{ p.plugin_type }}</span>
              </div>
              <span class="sp-plugin-author">by {{ p.author }}</span>
            </div>

            <div class="sp-plugin-actions">
              <!-- Config gear -->
              <button
                v-if="p.config_schema && Object.keys(p.config_schema).length"
                class="sp-icon-btn"
                title="Configure"
                @click="toggleConfig(p.plugin_id)"
                @mouseenter="setHint(t('plugins.phint_settings_title'), t('plugins.phint_settings_body'))"
                @mouseleave="clearHint"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
              </button>

              <!-- Toggle -->
              <button
                class="sp-toggle"
                :class="{ 'sp-toggle--on': p.enabled }"
                :disabled="toggling[p.plugin_id]"
                @click="toggleEnabled(p)"
                @mouseenter="setHint(p.enabled ? t('plugins.phint_disable_title') : t('plugins.phint_enable_title'), p.enabled ? t('plugins.phint_disable_body') : t('plugins.phint_enable_body'))"
                @mouseleave="clearHint"
              >
                <span class="sp-toggle-thumb" />
              </button>

              <!-- Delete -->
              <button
                v-if="confirmDeleteId !== p.plugin_id"
                class="sp-icon-btn sp-icon-btn--danger"
                title="Delete plugin"
                @click="confirmDeleteId = p.plugin_id"
                @mouseenter="setHint(t('plugins.phint_delete_title'), t('plugins.phint_delete_body'))"
                @mouseleave="clearHint"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
              <div v-else class="sp-confirm-delete">
                <span class="sp-confirm-label">Delete?</span>
                <button class="sp-btn sp-btn--danger-sm" :disabled="deleting[p.plugin_id]" @click="deletePlugin(p.plugin_id)">
                  {{ deleting[p.plugin_id] ? 'Deleting...' : 'Yes' }}
                </button>
                <button class="sp-btn sp-btn--ghost-sm" @click="confirmDeleteId = null">No</button>
              </div>
            </div>
          </div>

          <!-- Description -->
          <p v-if="p.description" class="sp-plugin-desc">{{ p.description }}</p>

          <!-- Config panel (expandable) -->
          <div v-if="openConfigId === p.plugin_id && p.config_schema" class="sp-config-panel">
            <div class="sp-config-divider" />
            <div class="sp-config-body">
              <div
                v-for="(schema, key) in p.config_schema"
                :key="String(key)"
                class="sp-config-row"
              >
                <label class="sp-config-label">{{ schema.label || key }}</label>

                <!-- Boolean -->
                <button
                  v-if="schema.type === 'boolean'"
                  class="sp-toggle"
                  :class="{ 'sp-toggle--on': configDraft[p.plugin_id]?.[key as string] }"
                  @click="setConfigValue(p.plugin_id, String(key), !configDraft[p.plugin_id]?.[key as string])"
                >
                  <span class="sp-toggle-thumb" />
                </button>

                <!-- Select -->
                <select
                  v-else-if="schema.type === 'select'"
                  class="sp-config-select"
                  :value="configDraft[p.plugin_id]?.[key as string] ?? ''"
                  @change="setConfigValue(p.plugin_id, String(key), ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="opt in (schema.options || [])" :key="opt" :value="opt">{{ opt }}</option>
                </select>

                <!-- Number -->
                <input
                  v-else-if="schema.type === 'number'"
                  type="number"
                  class="sp-config-input"
                  :value="configDraft[p.plugin_id]?.[key as string] ?? ''"
                  @input="setConfigValue(p.plugin_id, String(key), Number(($event.target as HTMLInputElement).value))"
                />

                <!-- String (default) -->
                <input
                  v-else
                  type="text"
                  class="sp-config-input"
                  :value="configDraft[p.plugin_id]?.[key as string] ?? ''"
                  @input="setConfigValue(p.plugin_id, String(key), ($event.target as HTMLInputElement).value)"
                />
              </div>

              <div class="sp-config-actions">
                <button class="sp-btn sp-btn--primary" :disabled="savingConfig[p.plugin_id]" @click="saveConfig(p.plugin_id)">
                  {{ savingConfig[p.plugin_id] ? t('plugins.saving', 'Saving...') : t('plugins.save_config', 'Save Config') }}
                </button>
                <span v-if="configMsg[p.plugin_id]" class="sp-config-msg" :class="{ 'sp-config-msg--ok': configOk[p.plugin_id] }">
                  {{ configMsg[p.plugin_id] }}
                </span>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- Inline message -->
      <span v-if="listMsg" class="sp-inline-msg" :class="{ 'sp-inline-msg--err': !listOk }">{{ listMsg }}</span>
    </section>

    <!-- Install Plugin -->
    <section class="sp-section">
      <div class="sp-section-head">
        <h2 class="sp-section-title">{{ t('plugins.install') }}</h2>
        <p class="sp-section-sub">{{ t('plugins.install_desc') }}</p>
      </div>

      <div
        class="sp-dropzone"
        :class="{ 'sp-dropzone--over': dragOver, 'sp-dropzone--uploading': uploading }"
        @dragenter.prevent="dragOver = true"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="onDrop"
        @click="fileInputEl?.click()"
      >
        <input
          ref="fileInputEl"
          type="file"
          accept=".zip"
          class="sp-file-input"
          @change="onFileSelect"
        />

        <div v-if="uploading" class="sp-upload-progress">
          <span class="sp-spinner" />
          <span>{{ t('plugins.installing') }}</span>
        </div>
        <div v-else class="sp-dropzone-content">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <span class="sp-dropzone-label">{{ t('plugins.dropzone') }}</span>
        </div>
      </div>

      <span v-if="uploadMsg" class="sp-inline-msg" :class="{ 'sp-inline-msg--err': !uploadOk, 'sp-inline-msg--ok': uploadOk }">
        {{ uploadMsg }}
      </span>
    </section>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import client from '@/services/api/client'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const { setHint, clearHint } = useSettingsHint()

// ── Types ────────────────────────────────────────────────────────────────────

interface PluginInfo {
  plugin_id: string
  name: string
  version: string
  author: string
  description: string | null
  plugin_type: string
  enabled: boolean
  has_logo: boolean
  installed_at: string | null
  config: Record<string, any> | null
  config_schema: Record<string, any> | null
}

// ── State ────────────────────────────────────────────────────────────────────

const plugins = ref<PluginInfo[]>([])
const loading = ref(true)
const listMsg = ref('')
const listOk  = ref(true)

const toggling = reactive<Record<string, boolean>>({})
const deleting = reactive<Record<string, boolean>>({})
const confirmDeleteId = ref<string | null>(null)

// Config panel
const openConfigId = ref<string | null>(null)
const configDraft  = reactive<Record<string, Record<string, any>>>({})
const savingConfig = reactive<Record<string, boolean>>({})
const configMsg    = reactive<Record<string, string>>({})
const configOk     = reactive<Record<string, boolean>>({})

// Upload
const fileInputEl = ref<HTMLInputElement | null>(null)
const dragOver    = ref(false)
const uploading   = ref(false)
const uploadMsg   = ref('')
const uploadOk    = ref(true)

// ── Helpers ──────────────────────────────────────────────────────────────────

function pluginLogoUrl(id: string): string {
  return `/api/plugins/${id}/logo`
}

function typeBadgeClass(type: string): string {
  const map: Record<string, string> = {
    metadata:  'sp-badge--metadata',
    download:  'sp-badge--download',
    library:   'sp-badge--library',
    theme:     'sp-badge--theme',
    widget:    'sp-badge--widget',
    lifecycle: 'sp-badge--lifecycle',
  }
  return map[type] || 'sp-badge--default'
}

// ── Load plugins ─────────────────────────────────────────────────────────────

async function loadPlugins() {
  loading.value = true
  listMsg.value = ''
  try {
    const { data } = await client.get('/plugins')
    plugins.value = data
  } catch (e: any) {
    listMsg.value = e?.response?.data?.detail || 'Failed to load plugins.'
    listOk.value = false
  } finally {
    loading.value = false
  }
}

// ── Toggle enable/disable ────────────────────────────────────────────────────

async function toggleEnabled(p: PluginInfo) {
  toggling[p.plugin_id] = true
  try {
    const action = p.enabled ? 'disable' : 'enable'
    await client.post(`/plugins/${p.plugin_id}/${action}`)
    p.enabled = !p.enabled
  } catch (e: any) {
    listMsg.value = e?.response?.data?.detail || `Failed to ${p.enabled ? 'disable' : 'enable'} plugin.`
    listOk.value = false
    setTimeout(() => { listMsg.value = '' }, 4000)
  } finally {
    toggling[p.plugin_id] = false
  }
}

// ── Delete plugin ────────────────────────────────────────────────────────────

async function deletePlugin(id: string) {
  deleting[id] = true
  try {
    await client.delete(`/plugins/${id}`)
    plugins.value = plugins.value.filter(p => p.plugin_id !== id)
    confirmDeleteId.value = null
  } catch (e: any) {
    listMsg.value = e?.response?.data?.detail || 'Failed to delete plugin.'
    listOk.value = false
    setTimeout(() => { listMsg.value = '' }, 4000)
  } finally {
    deleting[id] = false
  }
}

// ── Config panel ─────────────────────────────────────────────────────────────

async function toggleConfig(pluginId: string) {
  if (openConfigId.value === pluginId) {
    openConfigId.value = null
    return
  }
  openConfigId.value = pluginId
  try {
    const { data } = await client.get(`/plugins/${pluginId}/config`)
    configDraft[pluginId] = { ...(data.config || {}) }
  } catch {
    configDraft[pluginId] = {}
  }
}

function setConfigValue(pluginId: string, key: string, value: any) {
  if (!configDraft[pluginId]) configDraft[pluginId] = {}
  configDraft[pluginId][key] = value
}

async function saveConfig(pluginId: string) {
  savingConfig[pluginId] = true
  configMsg[pluginId] = ''
  try {
    await client.put(`/plugins/${pluginId}/config`, configDraft[pluginId])
    configMsg[pluginId] = t('plugins.saved', 'Saved')
    configOk[pluginId] = true
    const p = plugins.value.find(pl => pl.plugin_id === pluginId)
    if (p) p.config = { ...configDraft[pluginId] }
    setTimeout(() => { configMsg[pluginId] = '' }, 3000)
  } catch (e: any) {
    configMsg[pluginId] = e?.response?.data?.detail || t('plugins.save_failed', 'Save failed')
    configOk[pluginId] = false
    setTimeout(() => { configMsg[pluginId] = '' }, 4000)
  } finally {
    savingConfig[pluginId] = false
  }
}

// ── File upload ──────────────────────────────────────────────────────────────

function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) uploadFile(file)
  input.value = ''
}

async function uploadFile(file: File) {
  if (!file.name.endsWith('.zip')) {
    uploadMsg.value = t('plugins.zip_only', 'Only .zip files are accepted.')
    uploadOk.value = false
    setTimeout(() => { uploadMsg.value = '' }, 4000)
    return
  }

  uploading.value = true
  uploadMsg.value = ''

  const fd = new FormData()
  fd.append('file', file)

  try {
    await client.post('/plugins/install', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    uploadMsg.value = t('plugins.install_success', 'Plugin installed successfully.')
    uploadOk.value = true
    await loadPlugins()
    setTimeout(() => { uploadMsg.value = '' }, 5000)
  } catch (e: any) {
    uploadMsg.value = e?.response?.data?.detail || t('plugins.install_failed', 'Installation failed.')
    uploadOk.value = false
    setTimeout(() => { uploadMsg.value = '' }, 6000)
  } finally {
    uploading.value = false
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

onMounted(() => { loadPlugins() })
</script>

<style scoped>
.sp-root { display: flex; flex-direction: column; gap: 28px; padding: 4px 0; }

/* ── Section ──────────────────────────────────────────────────────────────── */
.sp-section { display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.sp-section-head { padding: 0 2px; }
.sp-section-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); margin: 0 0 2px; }
.sp-section-sub   { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }

/* ── Loading ──────────────────────────────────────────────────────────────── */
.sp-loading { font-size: var(--fs-sm, 12px); color: var(--muted); padding: 16px 0; }

/* ── Empty state ──────────────────────────────────────────────────────────── */
.sp-empty {
  display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px);
  padding: 48px 24px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); text-align: center;
}
.sp-empty-icon { color: var(--muted); opacity: .25; }
.sp-empty-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.sp-empty-sub   { font-size: var(--fs-sm, 12px); color: var(--muted); }

/* ── Plugin grid ──────────────────────────────────────────────────────────── */
.sp-plugin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}

/* ── Plugin card ──────────────────────────────────────────────────────────── */
.sp-plugin {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); overflow: hidden;
  display: flex; flex-direction: column;
  transition: border-color var(--transition);
}
.sp-plugin:hover { border-color: rgba(255,255,255,.12); }

.sp-plugin-header {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 14px 16px;
}

.sp-plugin-logo {
  width: 40px; height: 40px; object-fit: contain;
  border-radius: var(--radius-sm, 8px); flex-shrink: 0;
  background: rgba(255,255,255,.04);
}

.sp-plugin-logo-fallback {
  width: 40px; height: 40px; border-radius: var(--radius-sm, 8px);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  background: rgba(124,58,237,.12); color: var(--pl-light);
  border: 1px solid rgba(124,58,237,.25);
}

.sp-plugin-info { flex: 1; min-width: 0; }

.sp-plugin-name-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}

.sp-plugin-name {
  font-size: 13px; font-weight: 700; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.sp-plugin-author {
  display: block; font-size: 11px; color: var(--muted); margin-top: 2px;
}

.sp-plugin-desc {
  font-size: 11px; color: var(--muted); line-height: 1.5;
  padding: 0 16px 12px;
  margin: 0;
}

.sp-plugin-actions {
  display: flex; align-items: center; gap: var(--space-2, 8px); flex-shrink: 0;
}

/* ── Badges ───────────────────────────────────────────────────────────────── */
.sp-badge {
  padding: 2px 7px; border-radius: 20px;
  font-size: var(--fs-xs, 10px); font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
  white-space: nowrap; flex-shrink: 0;
  border: 1px solid transparent;
}
.sp-badge--version  { background: rgba(255,255,255,.06); color: var(--muted); border-color: var(--glass-border); }
.sp-badge--metadata { background: rgba(59,130,246,.15); color: #60a5fa; border-color: rgba(59,130,246,.3); }
.sp-badge--download { background: rgba(251,146,60,.15); color: #fb923c; border-color: rgba(251,146,60,.3); }
.sp-badge--library  { background: rgba(74,222,128,.15); color: #4ade80; border-color: rgba(74,222,128,.3); }
.sp-badge--theme    { background: rgba(168,85,247,.15); color: #c084fc; border-color: rgba(168,85,247,.3); }
.sp-badge--widget   { background: rgba(34,211,238,.15); color: #22d3ee; border-color: rgba(34,211,238,.3); }
.sp-badge--lifecycle { background: rgba(244,114,182,.15); color: #f472b6; border-color: rgba(244,114,182,.3); }
.sp-badge--default  { background: rgba(255,255,255,.06); color: var(--muted); border-color: var(--glass-border); }

/* ── Toggle ───────────────────────────────────────────────────────────────── */
.sp-toggle {
  position: relative; width: 40px; height: 22px; border-radius: 11px;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.1);
  cursor: pointer; transition: background .2s; flex-shrink: 0; padding: 0;
}
.sp-toggle--on { background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1)); border-color: color-mix(in srgb, var(--pl) 50%, transparent); box-shadow: 0 0 10px var(--pglow2); }
.sp-toggle:disabled { opacity: .5; cursor: not-allowed; }
.sp-toggle-thumb {
  position: absolute; top: 3px; left: 3px;
  width: 14px; height: 14px; border-radius: 50%;
  background: rgba(255,255,255,.4); transition: all .2s; display: block;
}
.sp-toggle--on .sp-toggle-thumb { transform: translateX(18px); background: #fff; }

/* ── Icon button ──────────────────────────────────────────────────────────── */
.sp-icon-btn {
  width: 30px; height: 30px; border-radius: 6px;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--transition); flex-shrink: 0; padding: 0;
}
.sp-icon-btn:hover { background: rgba(255,255,255,.08); color: var(--text); border-color: var(--pl); }
.sp-icon-btn--danger:hover { border-color: #f87171; color: #f87171; background: rgba(248,113,113,.1); }

/* ── Confirm delete ───────────────────────────────────────────────────────── */
.sp-confirm-delete {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.sp-confirm-label { font-size: 11px; font-weight: 600; color: #f87171; }

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.sp-btn {
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.sp-btn:disabled { opacity: .5; cursor: not-allowed; }
.sp-btn--primary { background: color-mix(in srgb, var(--pl) 20%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light); opacity: .6; }
.sp-btn--primary:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); }
.sp-btn--danger-sm { padding: 4px 10px; font-size: 11px; background: rgba(248,113,113,.15); border-color: rgba(248,113,113,.4); color: #f87171; }
.sp-btn--danger-sm:hover:not(:disabled) { background: rgba(248,113,113,.3); }
.sp-btn--ghost-sm { padding: 4px 10px; font-size: 11px; background: transparent; border-color: var(--glass-border); color: var(--muted); }
.sp-btn--ghost-sm:hover { background: rgba(255,255,255,.06); color: var(--text); }

/* ── Config panel ─────────────────────────────────────────────────────────── */
.sp-config-panel { display: flex; flex-direction: column; }
.sp-config-divider { height: 1px; background: var(--glass-border); }
.sp-config-body { padding: 14px 16px; display: flex; flex-direction: column; gap: var(--space-3, 12px); }

.sp-config-row {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3, 12px);
}

.sp-config-label {
  font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--text);
  white-space: nowrap; flex-shrink: 0;
}

.sp-config-input {
  flex: 1; max-width: 220px; padding: 6px 10px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: var(--fs-sm, 12px);
  font-family: inherit; outline: none;
  transition: border-color var(--transition);
}
.sp-config-input:focus { border-color: var(--pl); }

.sp-config-select {
  flex: 1; max-width: 220px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: var(--fs-sm, 12px);
  padding: 6px 8px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.sp-config-select:hover,
.sp-config-select:focus { border-color: var(--pl); }
.sp-config-select option { background: var(--bg2); }

.sp-config-actions { display: flex; align-items: center; gap: 10px; padding-top: 4px; }

.sp-config-msg { font-size: 11px; color: #f87171; }
.sp-config-msg--ok { color: #4ade80; }

/* ── Dropzone ─────────────────────────────────────────────────────────────── */
.sp-dropzone {
  display: flex; align-items: center; justify-content: center;
  min-height: 120px; padding: var(--space-6, 24px);
  background: var(--glass-bg); border: 2px dashed var(--glass-border);
  border-radius: var(--radius); cursor: pointer;
  transition: all var(--transition);
}
.sp-dropzone:hover { border-color: var(--pl); background: rgba(124,58,237,.04); }
.sp-dropzone--over { border-color: var(--pl); background: rgba(124,58,237,.08); }
.sp-dropzone--uploading { cursor: default; pointer-events: none; }

.sp-dropzone-content {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  color: var(--muted);
}
.sp-dropzone-label { font-size: var(--fs-sm, 12px); }

.sp-file-input { display: none; }

.sp-upload-progress {
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; color: var(--pl-light);
}

/* ── Spinner ──────────────────────────────────────────────────────────────── */
.sp-spinner {
  display: inline-block; width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.2); border-top-color: var(--pl-light);
  animation: sp-spin .7s linear infinite;
}
@keyframes sp-spin { to { transform: rotate(360deg); } }

/* ── Inline messages ──────────────────────────────────────────────────────── */
.sp-inline-msg { font-size: var(--fs-sm, 12px); color: #4ade80; }
.sp-inline-msg--err { color: #f87171; }
.sp-inline-msg--ok { color: #4ade80; }
</style>
