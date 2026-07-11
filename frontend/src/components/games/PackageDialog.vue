<!-- Shared "Package" dialog for Games-library games (Modern + Classic). Lets an
     admin pick which groups to bundle (OS platforms + extras/dlc) and whether to
     delete the loose originals afterwards, then calls the packaging API. Progress
     shows in the download tray. -->
<template>
  <Teleport to="body">
    <div v-if="open" class="pkg-overlay" @click.self="close">
      <div class="pkg-card">
        <div class="pkg-title">{{ t('packaging.package_now') }}</div>
        <div class="pkg-hint">{{ t('packaging.package_now_hint') }}</div>

        <div v-if="loading" class="pkg-empty">…</div>
        <div v-else-if="!groups.length" class="pkg-empty">{{ t('packaging.nothing') }}</div>
        <div v-else class="pkg-groups">
          <label v-for="g in groups" :key="g" class="pkg-row" :class="{ 'pkg-row--dim': singleArchive }">
            <input type="checkbox" :value="g" v-model="selected" :disabled="singleArchive" />
            <span class="pkg-ico">
              <svg v-if="groupKind(g) === 'windows'" viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.4l7.2-1v7.1H3zM11.4 4.2L21 3v8.5h-9.6zM3 12.7h7.2v7.1l-7.2-1zM11.4 12.7H21V21l-9.6-1.3z"/></svg>
              <svg v-else-if="groupKind(g) === 'mac'" viewBox="0 0 24 24" fill="currentColor"><path d="M16.7 12.6c0-2 1.6-3 1.7-3-.9-1.4-2.4-1.6-2.9-1.6-1.2-.1-2.4.7-3 .7s-1.6-.7-2.6-.7c-1.3 0-2.6.8-3.3 2-1.4 2.5-.4 6.1 1 8.1.7 1 1.4 2.1 2.5 2.1 1 0 1.4-.7 2.6-.7s1.5.7 2.6.6c1.1 0 1.8-1 2.4-2 .8-1.1 1.1-2.2 1.1-2.3s-2.1-.8-2.1-3zM14.8 6.3c.5-.7.9-1.6.8-2.6-.8 0-1.8.6-2.4 1.3-.5.6-1 1.5-.8 2.5.9 0 1.8-.5 2.4-1.2z"/></svg>
              <svg v-else-if="groupKind(g) === 'linux'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 9l2.5 2.5L7 14"/><path d="M12 14h5"/><path d="M9 21h6"/></svg>
              <svg v-else-if="groupKind(g) === 'dlc'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M19.4 13a1.7 1.7 0 000-3l-1-.1a1.7 1.7 0 01-1.2-2.4l.4-.9a1.7 1.7 0 00-2.2-2.2l-.9.4A1.7 1.7 0 0112 3.6L11.9 3a1.7 1.7 0 00-3 0l-.1 1A1.7 1.7 0 016.4 5.2l-.9-.4a1.7 1.7 0 00-2.2 2.2l.4.9A1.7 1.7 0 013.6 12L3 12.1a1.7 1.7 0 000 3l1 .1a1.7 1.7 0 011.2 2.4l-.4.9a1.7 1.7 0 002.2 2.2l.9-.4a1.7 1.7 0 012.4 1.2l.1 1a1.7 1.7 0 003 0"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 8v13H4V8"/><rect x="2" y="3" width="20" height="5"/><path d="M10 12h4"/></svg>
            </span>
            <span>{{ groupLabel(g) }}</span>
          </label>
          <label class="pkg-row pkg-row--sep">
            <input type="checkbox" v-model="singleArchive" />
            <span>{{ t('packaging.single_archive') }}</span>
          </label>
          <label class="pkg-row">
            <input type="checkbox" v-model="deleteOriginals" />
            <span>{{ t('packaging.delete_originals') }}</span>
          </label>
        </div>

        <div class="pkg-actions">
          <button class="pkg-btn" @click="close">{{ t('common.cancel') }}</button>
          <button class="pkg-btn pkg-btn--primary" :disabled="busy || (!singleArchive && !selected.length)" @click="submit">
            {{ busy ? t('packaging.packaging') : t('packaging.package_now') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const props = defineProps<{ gameId: number | string; open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'done'): void }>()
const { t } = useI18n()

const groups         = ref<string[]>([])
const selected       = ref<string[]>([])
const deleteOriginals = ref(false)
const singleArchive  = ref(false)
const loading        = ref(false)
const busy           = ref(false)

watch(() => props.open, async (o) => {
  if (!o) return
  loading.value = true
  groups.value = []; selected.value = []; deleteOriginals.value = false; singleArchive.value = false
  try {
    const { data } = await client.get(`/library/games/${props.gameId}/packable`)
    groups.value = Array.isArray(data?.platforms) ? data.platforms : []
    selected.value = [...groups.value]
  } catch { groups.value = [] }
  finally { loading.value = false }
}, { immediate: true })

function close() { emit('update:open', false) }

const _OS: Record<string, string> = { windows: 'Windows', mac: 'macOS', linux: 'Linux' }
function groupKind(g: string): string {
  const k = (g || '').toLowerCase()
  if (k === 'windows' || k === 'mac' || k === 'linux') return k
  if (k === 'dlc') return 'dlc'
  return 'extra'
}
function groupLabel(g: string): string {
  const k = (g || '').toLowerCase()
  if (_OS[k]) return `${t('packaging.group_game')} - ${_OS[k]}`
  if (k === 'dlc') return 'DLC'
  return 'Extras'
}

async function submit() {
  if (busy.value) return
  if (!singleArchive.value && !selected.value.length) return
  busy.value = true
  try {
    await client.post(`/library/games/${props.gameId}/package`,
      singleArchive.value
        ? { single_archive: true, delete_originals: deleteOriginals.value }
        : { groups: selected.value, delete_originals: deleteOriginals.value })
    emit('done')
    close()
  } catch { /* errors + progress surface in the download tray */ }
  finally { busy.value = false }
}
</script>

<style scoped>
.pkg-overlay {
  position: fixed; inset: 0; z-index: 4000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(3px);
}
.pkg-card {
  width: min(420px, calc(100vw - 32px));
  background: var(--card-bg, #1a1a24);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.12));
  border-radius: 14px; padding: 20px 22px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); color: var(--text, #eee);
}
.pkg-title { font-size: 17px; font-weight: 700; margin-bottom: 4px; }
.pkg-hint { font-size: 12.5px; opacity: 0.7; margin-bottom: 14px; }
.pkg-empty { font-size: 13px; opacity: 0.7; padding: 12px 0; }
.pkg-groups { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
.pkg-row { display: flex; align-items: center; gap: 9px; cursor: pointer; font-size: 14px; }
.pkg-row input { width: 16px; height: 16px; accent-color: var(--pl, #7c3aed); cursor: pointer; }
.pkg-ico { display: inline-flex; width: 16px; height: 16px; opacity: 0.8; }
.pkg-ico svg { width: 16px; height: 16px; }
.pkg-row--sep { margin-top: 4px; padding-top: 12px; border-top: 1px solid var(--glass-border, rgba(255, 255, 255, 0.1)); opacity: 0.9; }
.pkg-row--dim { opacity: 0.4; }
.pkg-actions { display: flex; justify-content: flex-end; gap: 10px; }
.pkg-btn {
  padding: 8px 16px; border-radius: 9px; font-size: 13.5px; font-weight: 600; cursor: pointer;
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.15));
  background: color-mix(in srgb, var(--pl, #7c3aed) 10%, transparent); color: var(--text, #eee);
}
.pkg-btn--primary {
  background: color-mix(in srgb, var(--pl, #7c3aed) 30%, transparent);
  border-color: color-mix(in srgb, var(--pl, #7c3aed) 55%, transparent);
}
.pkg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
