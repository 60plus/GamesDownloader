<template>
  <!-- A GOG or custom game's files behind "Show details" (the owner,
       2026-09-18), the way Vapor lists them and a ROM's page lists its own:
       each file with what it is, the system it is for and its size, and a bin
       where the server says pressing it will work (can_delete). -->
  <div v-if="listed.length" class="gfl">
    <button type="button" class="gfl-toggle" :aria-expanded="open" @click="open = !open">
      {{ open ? t('detail.hide_details') : t('detail.show_details') }}
    </button>
    <div v-if="open" class="gfl-list">
      <div v-for="f in listed" :key="f.id" class="gfl-row">
        <span class="gfl-name" :title="f.display_name || f.filename">{{ f.display_name || f.filename }}</span>
        <span class="gfl-type" :class="'gfl-type--' + kindOf(f)">{{ labelOf(f) }}</span>
        <span v-if="f.os && f.os !== 'all'" class="gfl-os">{{ osLabel(f.os) }}</span>
        <span class="gfl-size">{{ formatBytes(f.size_bytes) }}</span>
        <button v-if="f.can_delete" type="button" class="gfl-bin"
                :disabled="removing === f.id" :title="t('detail.remove_file')"
                :aria-label="t('detail.remove_file')" @click="remove(f)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'
import { removeFile } from '@/lib/libraryActions'
import { formatBytes as _formatBytes } from '@/utils/format'

export interface GameFile {
  id: number
  filename: string
  display_name?: string | null
  file_type: string
  os?: string | null
  size_bytes?: number | null
  is_available?: boolean
  /** Whether this caller's bin would work on it (library_router._mark_removable). */
  can_delete?: boolean
}

const props = defineProps<{ files: GameFile[] }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const { t } = useI18n()
const { gdConfirm, gdAlert } = useDialog()
const formatBytes = (b: number | null | undefined): string => _formatBytes(b, '-')
const open = ref(false)
const removing = ref<number | null>(null)

// The downloadable files, in the order the download picker groups them.
const ORDER = ['game', 'dlc', 'extra', 'mod']
const listed = computed(() =>
  (props.files || [])
    .filter(f => f.is_available !== false)
    .slice()
    .sort((a, b) => ORDER.indexOf(kindOf(a)) - ORDER.indexOf(kindOf(b))))

function kindOf(f: GameFile): string {
  return ORDER.includes(f.file_type) ? f.file_type : 'game'
}

function labelOf(f: GameFile): string {
  const kind = kindOf(f)
  if (kind === 'dlc') return t('detail.type_dlc')
  if (kind === 'extra') return t('detail.type_extras')
  if (kind === 'mod') return t('detail.type_mods')
  return t('detail.type_game')
}

const OS_NAMES: Record<string, string> = { windows: 'Windows', mac: 'macOS', linux: 'Linux' }
function osLabel(os: string): string {
  return OS_NAMES[os] || os
}

async function remove(f: GameFile) {
  if (removing.value) return
  const name = f.display_name || f.filename
  if (!await gdConfirm(t('detail.remove_file_body', { name }), {
    danger: true, title: t('detail.remove_file'), confirmText: t('common.remove'),
  })) return
  removing.value = f.id
  try {
    await removeFile(f.id)
    emit('changed')
  } catch {
    await gdAlert(t('detail.remove_file_failed'))
  } finally {
    removing.value = null
  }
}
</script>

<style scoped>
.gfl { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.gfl-toggle {
  align-self: flex-start;
  padding: 5px 12px; border-radius: 6px; cursor: pointer;
  font: inherit; font-size: 12px; font-weight: 600;
  color: var(--muted, rgba(255,255,255,.6));
  background: color-mix(in srgb, var(--pl) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent);
  transition: background .15s, color .15s, border-color .15s;
}
.gfl-toggle:hover { color: #fff; background: color-mix(in srgb, var(--pl) 20%, transparent); }
.gfl-toggle:focus-visible { outline: 2px solid var(--pl-light, #fff); outline-offset: 2px; }
.gfl-list { display: flex; flex-direction: column; }
.gfl-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; border-top: 1px solid rgba(255,255,255,.07);
  font-size: 12.5px;
}
.gfl-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text, #fff); }
.gfl-os { color: var(--muted, rgba(255,255,255,.55)); font-size: 11.5px; white-space: nowrap; }
.gfl-size { color: var(--muted, rgba(255,255,255,.55)); white-space: nowrap; font-variant-numeric: tabular-nums; }
/* Glass chips, one hue each, the same as a ROM's list (RomFilesList). */
.gfl-type {
  --chip: var(--pl);
  flex-shrink: 0;
  padding: 1px 7px; border-radius: 4px;
  font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: color-mix(in srgb, var(--chip) 75%, #fff);
  background: color-mix(in srgb, var(--chip) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--chip) 45%, transparent);
}
.gfl-type--game { --chip: #4aa3ff; }
.gfl-type--dlc { --chip: #c084fc; }
.gfl-type--extra { --chip: #3fbf6f; }
.gfl-type--mod { --chip: #e0a33a; }
.gfl-bin {
  flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; padding: 0; border-radius: 5px; cursor: pointer;
  color: #f87171; background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.25);
}
.gfl-bin:hover { background: rgba(239,68,68,.18); }
.gfl-bin:disabled { opacity: .45; cursor: default; }
.gfl-bin:focus-visible { outline: 2px solid #f87171; outline-offset: 1px; }
</style>
