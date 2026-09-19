<template>
  <!-- What a ROM's download holds, behind "Show details", the way a GOG or
       custom game lists its files: the game, every disc of it on a line of its
       own, then its extras and mods, each with what it is and how big. A page
       that names the file elsewhere shows it only when there is something
       beside the game; one that does not passes `always`. -->
  <div v-if="always || extras.length" class="rfl">
    <button type="button" class="rfl-toggle" :aria-expanded="open" @click="open = !open">
      {{ open ? t('detail.hide_details') : t('detail.show_details') }}
    </button>
    <div v-if="open" class="rfl-list">
      <template v-if="discs && discs.length > 1">
        <div v-for="d in discs" :key="d.name" class="rfl-row">
          <span class="rfl-name" :title="d.name">{{ d.name }}</span>
          <span class="rfl-type rfl-type--game">{{ t('detail.type_game') }}</span>
          <span class="rfl-size">{{ formatBytes(d.size) }}</span>
        </div>
      </template>
      <div v-else class="rfl-row">
        <span class="rfl-name" :title="gameLabel">{{ gameLabel }}</span>
        <span class="rfl-type rfl-type--game">{{ t('detail.type_game') }}</span>
        <span class="rfl-size">{{ formatBytes(gameSize) }}</span>
      </div>
      <div v-for="f in extras" :key="f.path" class="rfl-row">
        <span class="rfl-name" :title="f.name">{{ f.name }}</span>
        <span class="rfl-type" :class="'rfl-type--' + f.kind">
          {{ f.kind === 'mod' ? t('detail.type_mods') : t('detail.type_extras') }}
        </span>
        <span class="rfl-size">{{ formatBytes(f.size) }}</span>
        <!-- Only where the server says pressing it will work (can_delete):
             an administrator, or the account that added the file. -->
        <button v-if="romId && f.can_delete" type="button" class="rfl-bin"
                :disabled="removing === f.path" :title="t('detail.remove_file')"
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
import { ref } from 'vue'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'
import { removeRomExtra } from '@/lib/romSourceActions'
import { formatBytes as _formatBytes } from '@/utils/format'
import type { RomExtra } from './RomDownloadDialog.vue'

const props = defineProps<{
  gameLabel: string
  gameSize: number
  extras: RomExtra[]
  /** The discs of a title on several, each listed on its own. */
  discs?: { name: string; size?: number | null }[]
  /** Shown even with nothing beside the game: the page names no file elsewhere. */
  always?: boolean
  /** The ROM the bins act on. Without it no bin is drawn. */
  romId?: number
}>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const { t } = useI18n()
const { gdConfirm, gdAlert } = useDialog()
const formatBytes = (b: number | null | undefined): string => _formatBytes(b, '-')
const open = ref(false)
const removing = ref<string | null>(null)

async function remove(f: RomExtra) {
  if (!props.romId || removing.value) return
  if (!await gdConfirm(t('detail.remove_file_body', { name: f.name }), {
    danger: true, title: t('detail.remove_file'), confirmText: t('common.remove'),
  })) return
  removing.value = f.path
  try {
    await removeRomExtra(props.romId, f.path)
    emit('changed')
  } catch {
    await gdAlert(t('detail.remove_file_failed'))
  } finally {
    removing.value = null
  }
}
</script>

<style scoped>
.rfl { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.rfl-toggle {
  align-self: flex-start;
  padding: 5px 12px; border-radius: 6px; cursor: pointer;
  font: inherit; font-size: 12px; font-weight: 600;
  color: var(--muted, rgba(255,255,255,.6));
  background: color-mix(in srgb, var(--pl) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent);
  transition: background .15s, color .15s, border-color .15s;
}
.rfl-toggle:hover { color: #fff; background: color-mix(in srgb, var(--pl) 20%, transparent); }
.rfl-toggle:focus-visible { outline: 2px solid var(--pl-light, #fff); outline-offset: 2px; }
.rfl-list { display: flex; flex-direction: column; }
.rfl-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; border-top: 1px solid rgba(255,255,255,.07);
  font-size: 12.5px;
}
.rfl-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text, #fff); }
.rfl-size { color: var(--muted, rgba(255,255,255,.55)); white-space: nowrap; font-variant-numeric: tabular-nums; }
/* Glass chips, one hue each: the game, what came with it, what was added. */
.rfl-type {
  --chip: var(--pl);
  flex-shrink: 0;
  padding: 1px 7px; border-radius: 4px;
  font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: color-mix(in srgb, var(--chip) 75%, #fff);
  background: color-mix(in srgb, var(--chip) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--chip) 45%, transparent);
}
.rfl-bin {
  flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; padding: 0; border-radius: 5px; cursor: pointer;
  color: #f87171; background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.25);
}
.rfl-bin:hover { background: rgba(239,68,68,.18); }
.rfl-bin:disabled { opacity: .45; cursor: default; }
.rfl-bin:focus-visible { outline: 2px solid #f87171; outline-offset: 1px; }
.rfl-type--game { --chip: #4aa3ff; }
.rfl-type--extra { --chip: #3fbf6f; }
.rfl-type--mod { --chip: #e0a33a; }
</style>
