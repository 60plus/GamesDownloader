<template>
  <!-- A ROM's download picker, the way a GOG or custom game offers its files:
       the game ticked, its extras and mods beside it to add. The game is one
       entry however many discs it came on - they download as one archive, the
       way the Download button always gave them. Shared by every theme on the
       core ROM page; a theme plugin uses __GD__.roms.downloadFiles itself. -->
  <Teleport to="body">
    <div v-if="modelValue" class="dl-overlay" @click.self="close">
      <div class="dl-dialog glass" role="dialog" aria-modal="true">
        <div class="dl-header">
          <div class="dl-title">{{ t('detail.download_title', { title }) }}</div>
          <button class="dl-close" :title="t('common.close')" @click="close">×</button>
        </div>

        <div class="dl-files">
          <div class="dl-type-section">
            <div class="dl-type-head">{{ t('detail.type_game') }}</div>
            <div class="dl-file-row">
              <label class="dl-file-check">
                <input type="checkbox" :checked="selected.has(GAME)" @change="toggle(GAME)" />
                <span class="dl-file-name">{{ gameLabel }}</span>
              </label>
              <span class="dl-file-size">{{ formatBytes(gameSize) }}</span>
            </div>
          </div>

          <div v-for="group in groups" :key="group.kind" class="dl-type-section">
            <div class="dl-type-head">{{ group.label }}</div>
            <div v-for="f in group.files" :key="f.path" class="dl-file-row">
              <label class="dl-file-check">
                <input type="checkbox" :checked="selected.has(f.path)" @change="toggle(f.path)" />
                <span class="dl-file-name" :title="f.name">{{ f.name }}</span>
              </label>
              <span class="dl-file-size">{{ formatBytes(f.size) }}</span>
            </div>
          </div>
        </div>

        <div class="dl-footer">
          <span class="dl-selected-info">{{ t('detail.files_selected', { count: selected.size }) }}</span>
          <button class="dl-btn" :disabled="selected.size === 0 || downloading" @click="download">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {{ t('detail.download_selected') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'
import { romActions } from '@/lib/romSourceActions'
import { formatBytes as _formatBytes } from '@/utils/format'

export interface RomExtra {
  kind: 'extra' | 'mod'; path: string; name: string; size: number
  /** Whether this caller's bin would work on it (roms_router._mark_extras). */
  can_delete?: boolean
}

const props = defineProps<{
  modelValue: boolean
  romId: number
  title: string
  gameLabel: string
  gameSize: number
  wholeSet?: boolean
  extras: RomExtra[]
}>()
const emit = defineEmits<{ (e: 'update:modelValue', open: boolean): void }>()

const { t } = useI18n()
const { gdAlert } = useDialog()
const formatBytes = (b: number | null | undefined): string => _formatBytes(b, '-')

// The game's own key: no file path is empty, so it cannot collide with one.
const GAME = ''
const selected = ref(new Set<string>([GAME]))
const downloading = ref(false)

const groups = computed(() => [
  { kind: 'extra', label: t('detail.type_extras'), files: props.extras.filter(f => f.kind === 'extra') },
  { kind: 'mod', label: t('detail.type_mods'), files: props.extras.filter(f => f.kind === 'mod') },
].filter(g => g.files.length))

// Opened afresh each time: the game ticked, the rest left to choose.
watch(() => props.modelValue, (open) => { if (open) selected.value = new Set([GAME]) })

function toggle(key: string) {
  const next = new Set(selected.value)
  next.has(key) ? next.delete(key) : next.add(key)
  selected.value = next
}

function close() { emit('update:modelValue', false) }

async function download() {
  downloading.value = true
  try {
    await romActions.downloadFiles(props.romId, {
      game: selected.value.has(GAME),
      wholeSet: !!props.wholeSet,
      paths: [...selected.value].filter(k => k !== GAME),
    })
    close()
  } catch {
    gdAlert(t('detail.download_failed'))
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
/* The same dialog a GOG or custom game offers its files in (GamesGameDetail). */
.dl-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
}
.dl-dialog {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  width: 100%; max-width: 560px; max-height: 85vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
}
.dl-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 24px; border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.dl-title { font-size: 15px; font-weight: 700; color: var(--text); }
.dl-close {
  background: none; border: none; color: var(--muted); font-size: 20px;
  cursor: pointer; padding: 4px; border-radius: 6px; transition: all .15s;
}
.dl-close:hover { color: var(--text); background: rgba(255,255,255,.08); }
.dl-files {
  flex: 1; overflow-y: auto; padding: 16px 24px 20px;
  display: flex; flex-direction: column; gap: 18px;
}
.dl-type-section { display: flex; flex-direction: column; gap: 6px; }
.dl-type-head {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .8px; color: var(--pl-light); margin: 4px 0 6px;
}
.dl-file-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.07);
  transition: background .12s;
}
.dl-file-row:hover { background: rgba(255,255,255,.07); }
.dl-file-check { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; cursor: pointer; }
.dl-file-check input { width: 16px; height: 16px; cursor: pointer; accent-color: var(--pl); flex-shrink: 0; }
.dl-file-name { font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-file-size { font-size: 12px; color: var(--muted); font-weight: 500; white-space: nowrap; font-variant-numeric: tabular-nums; }
.dl-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.dl-selected-info { font-size: 12px; color: var(--muted); }
.dl-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 22px; border-radius: var(--radius-sm, 8px);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.dl-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}
.dl-btn:disabled { opacity: .4; cursor: not-allowed; }
.dl-btn:focus-visible, .dl-close:focus-visible { outline: 2px solid var(--pl-light, #fff); outline-offset: 2px; }
</style>
