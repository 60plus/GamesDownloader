<template>
  <Teleport to="body">
    <Transition name="cdl-fade">
      <div v-if="modelValue" class="cdl-backdrop" @click.self="close">
        <div class="cdl-dialog" role="dialog" aria-modal="true">

          <!-- ── Header ──────────────────────────────────────────────────────── -->
          <div class="cdl-header">
            <div class="cdl-header-left">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" class="cdl-header-ico">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span class="cdl-title">{{ t('detail.download') }}</span>
            </div>
            <div class="cdl-game-name">{{ title }}</div>
            <button class="cdl-close" @click="close" :title="t('common.cancel')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- ── Nothing on offer ────────────────────────────────────────────── -->
          <div v-if="!assets.length" class="cdl-error">
            {{ t('detail.no_files') }}
          </div>

          <template v-else>
            <div class="cdl-body">

              <!-- ── Platform ────────────────────────────────────────────────── -->
              <!-- Only when there is a choice to make. A catalogue entry that
                   ships one build would get a single chip that decides nothing,
                   which is the kind of control that makes a dialog look busier
                   than it is. -->
              <div v-if="osGroups.length > 1" class="cdl-section">
                <div class="cdl-section-head">
                  <span class="cdl-section-label">{{ t('detail.platform') }}</span>
                  <span class="cdl-section-hint">{{ t('detail.dl_platform_hint') }}</span>
                </div>
                <div class="cdl-os-chips">
                  <button
                    v-for="os in osGroups"
                    :key="os"
                    class="cdl-os-chip"
                    :class="{ active: selectedOS === os }"
                    @click="selectOS(os)"
                  >
                    <svg v-if="os === 'windows'" width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                    </svg>
                    <svg v-else-if="os === 'mac'" width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M18.71,19.5C17.88,20.74 17,21.95 15.66,21.97C14.32,22 13.89,21.18 12.37,21.18C10.84,21.18 10.37,21.95 9.1,22C7.78,22.05 6.8,20.68 5.96,19.47C4.25,17 2.94,12.45 4.7,9.39C5.57,7.87 7.13,6.91 8.82,6.88C10.1,6.86 11.32,7.75 12.11,7.75C12.89,7.75 14.37,6.68 15.92,6.84C16.57,6.87 18.39,7.1 19.56,8.82C19.47,8.88 17.39,10.1 17.41,12.63C17.44,15.65 20.06,16.66 20.09,16.67C20.06,16.74 19.67,18.11 18.71,19.5M13,3.5C13.73,2.67 14.94,2.04 15.94,2C16.07,3.17 15.6,4.35 14.9,5.19C14.21,6.04 13.07,6.7 11.95,6.61C11.8,5.46 12.36,4.26 13,3.5Z"/>
                    </svg>
                    <img v-else-if="os === 'linux'" src="/icons/os-linux.svg" width="15" height="15" alt="Linux" />
                    <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                    </svg>
                    {{ osLabel(os) }}
                  </button>
                </div>
              </div>

              <!-- ── Builds ──────────────────────────────────────────────────── -->
              <div v-if="visibleAssets.length" class="cdl-section">
                <div class="cdl-section-head">
                  <span class="cdl-section-label">{{ t('detail.builds') }}</span>
                  <span class="cdl-section-hint">{{ t('detail.dl_builds_hint') }}</span>
                </div>
                <div class="cdl-file-list">
                  <label
                    v-for="a in visibleAssets"
                    :key="a.name"
                    class="cdl-file-row"
                    :class="{ checked: sel[a.name] }"
                  >
                    <input type="checkbox" class="cdl-check" v-model="sel[a.name]" />
                    <div class="cdl-file-info">
                      <span class="cdl-file-name">{{ a.name }}</span>
                      <!-- A build marked for every platform sits in every list,
                           so it says so rather than looking like a stray. -->
                      <span v-if="osKey(a.os) === 'all'" class="cdl-file-tag">{{ t('detail.dl_any_os') }}</span>
                      <span v-if="a.arch" class="cdl-file-tag">{{ a.arch }}</span>
                    </div>
                    <span class="cdl-file-size">{{ fmtSize(a.size) }}</span>
                  </label>
                </div>
              </div>

              <!-- ── Save location ───────────────────────────────────────────── -->
              <!-- The server decides this, so it is shown, not chosen. -->
              <div v-if="savePaths.length" class="cdl-section cdl-section--path">
                <div class="cdl-section-head">
                  <span class="cdl-section-label">{{ t('detail.dl_save_location') }}</span>
                  <span class="cdl-section-hint">{{ t('detail.dl_save_hint') }}</span>
                </div>
                <div v-for="p in savePaths" :key="p" class="cdl-path-row">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.5;flex-shrink:0">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="cdl-path-text">{{ p }}</span>
                </div>
              </div>

              <!-- ── Summary ─────────────────────────────────────────────────── -->
              <div v-if="selectedCount > 0" class="cdl-summary">
                {{ t('detail.dl_summary', { count: selectedCount, size: fmtSize(selectedSize) }) }}
              </div>

            </div><!-- /cdl-body -->

            <!-- ── Error banner ──────────────────────────────────────────────── -->
            <div v-if="errMsg" class="cdl-queue-error">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <div class="cdl-queue-error-text">{{ errMsg }}</div>
              <button class="cdl-queue-error-close" @click="errMsg = ''">&times;</button>
            </div>

            <!-- ── Footer ────────────────────────────────────────────────────── -->
            <div class="cdl-footer">
              <button class="cdl-btn-cancel" @click="close">{{ t('common.cancel') }}</button>
              <button class="cdl-btn-start" :disabled="selectedCount === 0 || starting" @click="start">
                <span v-if="starting" class="cdl-spinner" />
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {{ starting ? t('common.loading') : t('detail.download') }}
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
import { useI18n } from '@/i18n'
import client from '@/services/api/client'

const { t } = useI18n()

export interface CatalogAsset {
  name: string
  os?: string | null
  size?: number | null
  arch?: string | null
}

const props = defineProps<{
  modelValue: boolean
  entryId: number
  title: string
  assets: CatalogAsset[]
  /** Where the server will put the files. Shown, never edited. */
  saveRoot?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'started', result: any): void
}>()

const sel      = ref<Record<string, boolean>>({})
const selectedOS = ref('')
const starting = ref(false)
const errMsg   = ref('')

/** The four folders the server accepts; anything else is refused downstream. */
function osKey(os?: string | null): string {
  const v = String(os || 'all').toLowerCase()
  if (v.startsWith('win')) return 'windows'
  if (v.startsWith('mac') || v === 'osx' || v === 'darwin') return 'mac'
  if (v.startsWith('lin')) return 'linux'
  return 'all'
}

function osLabel(os: string): string {
  return { windows: 'Windows', mac: 'macOS', linux: 'Linux', all: t('detail.dl_any_os') }[os] ?? os
}

/** Platforms with a build of their own. A build marked "all" belongs to every
 *  platform rather than to one of its own, so it never opens a group - an entry
 *  offering only such builds gets a single "any platform" group instead. */
const osGroups = computed<string[]>(() => {
  const named = new Set<string>()
  let anyOnly = false
  for (const a of props.assets) {
    const k = osKey(a.os)
    if (k === 'all') anyOnly = true
    else named.add(k)
  }
  const order = ['windows', 'linux', 'mac']
  const list = order.filter(o => named.has(o))
  if (!list.length && anyOnly) return ['all']
  return list
})

const visibleAssets = computed<CatalogAsset[]>(() => {
  if (!selectedOS.value || selectedOS.value === 'all') return props.assets
  return props.assets.filter(a => {
    const k = osKey(a.os)
    return k === selectedOS.value || k === 'all'
  })
})

const selectedAssets = computed(() => props.assets.filter(a => sel.value[a.name]))
const selectedCount  = computed(() => selectedAssets.value.length)
const selectedSize   = computed(() => selectedAssets.value.reduce((n, a) => n + (a.size ?? 0), 0))

/** One line per folder the selection will land in, matching the server's
 *  <store>/<title>/<os>/ layout - a build for every platform lands in the
 *  title folder itself, which is why "all" contributes no subfolder. */
const savePaths = computed<string[]>(() => {
  const root = (props.saveRoot || '').replace(/\/+$/, '')
  if (!root) return []
  const picked = selectedAssets.value.length ? selectedAssets.value : visibleAssets.value
  const dirs = new Set<string>()
  for (const a of picked) {
    const k = osKey(a.os)
    dirs.add(k === 'all' ? `${root}/` : `${root}/${k}/`)
  }
  return dirs.size ? Array.from(dirs).sort() : [`${root}/`]
})

/** Opening the dialog is what resets it: a cancelled pick must not survive
 *  into the next open, and the entry can change under a route move. */
watch(() => props.modelValue, (open) => {
  if (!open) return
  errMsg.value = ''
  selectedOS.value = osGroups.value[0] || 'all'
  autoSelect()
})

/** Switching platform re-picks that platform's builds, the way the GOG dialog
 *  re-checks its installers - the previous platform's ticks are not a choice
 *  the reader made about this one. */
function selectOS(os: string) {
  selectedOS.value = os
  autoSelect()
}

function autoSelect() {
  const s: Record<string, boolean> = {}
  for (const a of visibleAssets.value) s[a.name] = true
  sel.value = s
}

function close() {
  emit('update:modelValue', false)
}

async function start() {
  if (starting.value || !selectedCount.value) return
  starting.value = true
  errMsg.value = ''
  try {
    const names = selectedAssets.value.map(a => a.name)
    const { data } = await client.post(
      `/plugins/library/catalog-entries/${props.entryId}/download`,
      { assets: names },
    )
    // A per-build refusal (too large, no URL) comes back in `failed` with the
    // rest queued. Reporting only the total would call a half-done download
    // finished, so the dialog stays open and names what did not start.
    const failed: any[] = Array.isArray(data?.failed) ? data.failed : []
    const started: any[] = Array.isArray(data?.started) ? data.started : []
    if (started.length) emit('started', data)
    if (failed.length) {
      errMsg.value = failed.map(f => `${f.name}: ${f.error}`).join('\n')
      if (!started.length) return
    }
    close()
  } catch (e: any) {
    const d = e?.response?.data?.detail
    errMsg.value = typeof d === 'string' ? d : (e?.message || t('detail.download_failed'))
  } finally {
    starting.value = false
  }
}

function fmtSize(bytes?: number | null): string {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes, u = 0
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++ }
  return `${v.toFixed(u > 0 ? 1 : 0)} ${units[u]}`
}
</script>

<style scoped>
/* Shaped after the GOG download dialog so a store download and a library
   download read as the same act - see components/gog/DownloadDialog.vue. */

.cdl-fade-enter-active,
.cdl-fade-leave-active { transition: opacity .18s ease; }
.cdl-fade-enter-active .cdl-dialog { transition: transform .2s cubic-bezier(.22,1,.36,1), opacity .18s; }
.cdl-fade-leave-active .cdl-dialog { transition: transform .15s ease-in, opacity .15s; }
.cdl-fade-enter-from .cdl-dialog,
.cdl-fade-leave-to   .cdl-dialog  { transform: scale(.95) translateY(8px); opacity: 0; }
.cdl-fade-enter-from,
.cdl-fade-leave-to                { opacity: 0; }

.cdl-backdrop {
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

.cdl-dialog {
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

.cdl-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,.07));
  flex-shrink: 0;
}
.cdl-header-left { display: flex; align-items: center; gap: var(--space-2, 8px); }
.cdl-header-ico  { color: var(--pl-light, var(--pl)); flex-shrink: 0; }

.cdl-title {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  letter-spacing: .02em;
  text-transform: uppercase;
}

.cdl-game-name {
  font-size: 13px;
  color: rgba(255,255,255,.45);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cdl-close {
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
.cdl-close:hover { color: rgba(255,255,255,.9); background: rgba(255,255,255,.06); }

.cdl-error {
  padding: 48px 24px;
  text-align: center;
  color: rgba(255,255,255,.5);
  font-size: var(--fs-md, 14px);
}

.cdl-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,.1) transparent;
}

.cdl-section {
  padding: 16px 0 4px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,.06));
}
.cdl-section:last-child { border-bottom: none; }

.cdl-section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.cdl-section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--pl-light, var(--pl));
}

.cdl-section-hint {
  font-size: 11px;
  color: rgba(255,255,255,.35);
  flex: 1;
}

.cdl-os-chips { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }

.cdl-os-chip {
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
.cdl-os-chip:hover { border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }
.cdl-os-chip.active {
  border-color: var(--pl);
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  color: #fff;
  box-shadow: 0 0 10px color-mix(in srgb, var(--pl) 25%, transparent);
}

.cdl-file-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 4px);
  margin-bottom: 8px;
}

.cdl-file-row {
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
.cdl-file-row:hover {
  background: color-mix(in srgb, var(--pl) 10%, transparent);
  border-color: color-mix(in srgb, var(--pl) 30%, transparent);
}
.cdl-file-row.checked {
  background: color-mix(in srgb, var(--pl) 14%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
}

.cdl-check {
  width: 16px;
  height: 16px;
  accent-color: var(--pl);
  flex-shrink: 0;
  cursor: pointer;
}

.cdl-file-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  min-width: 0;
}

.cdl-file-name {
  font-size: 13px;
  color: rgba(255,255,255,.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cdl-file-tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.07);
  color: rgba(255,255,255,.5);
  white-space: nowrap;
  flex-shrink: 0;
}

.cdl-file-size {
  font-size: var(--fs-sm, 12px);
  color: rgba(255,255,255,.4);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.cdl-path-row {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 8px 12px;
  border-radius: 7px;
  background: rgba(0,0,0,.25);
  border: 1px solid rgba(255,255,255,.06);
  margin-bottom: 6px;
}
.cdl-path-row:last-child { margin-bottom: 0; }

.cdl-path-text {
  font-size: var(--fs-sm, 12px);
  font-family: 'Fira Code', 'Courier New', monospace;
  color: rgba(255,255,255,.55);
  word-break: break-all;
}

.cdl-summary {
  padding: 10px 0 14px;
  font-size: var(--fs-sm, 12px);
  color: rgba(255,255,255,.45);
}

.cdl-queue-error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 8px);
  padding: 10px 14px;
  background: rgba(220, 38, 38, .15);
  border-top: 1px solid rgba(239, 68, 68, .3);
  color: #fca5a5;
  font-size: var(--fs-sm, 12px);
  line-height: 1.5;
  white-space: pre-line;
}
.cdl-queue-error-text { flex: 1; }
.cdl-queue-error-close {
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
.cdl-queue-error-close:hover { opacity: 1; }

.cdl-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--glass-border, rgba(255,255,255,.07));
  flex-shrink: 0;
}

.cdl-btn-cancel {
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
.cdl-btn-cancel:hover { background: rgba(255,255,255,.06); color: rgba(255,255,255,.8); }

.cdl-btn-start {
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
.cdl-btn-start:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl);
  color: #fff;
}
.cdl-btn-start:disabled { opacity: .4; cursor: not-allowed; box-shadow: none; }

.cdl-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: cdl-spin .8s linear infinite;
  flex-shrink: 0;
}
@keyframes cdl-spin { to { transform: rotate(360deg); } }
</style>
