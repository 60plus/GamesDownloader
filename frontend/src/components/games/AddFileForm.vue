<!--
  AddFileForm - add one file to a game that is already on the shelf.

  The way round the upload dialog's "is this title already here" question: the
  game is the one on screen, so there is nothing to ask and nothing to create.
  It only ever uploads into the game it is given.

  One component for every skin (1.0.35). Modern shows it on the game page; Vapor
  and Classic draw their own game pages and open it as a dialog through
  `__GD__.ui.openAddFileDialog`, the same door the metadata editors use. The
  owner decided an uploader may add files to a game somebody else added, and
  the bytes count against the account that sends them, so an uploader gets this
  as well as an admin.
-->
<template>
  <div class="add-file">
    <input
      ref="input"
      type="file"
      class="add-file-input"
      :disabled="busy"
      @change="onPicked"
    />
    <select v-model="form.os" class="add-file-select" :disabled="busy">
      <option value="windows">Windows</option>
      <option value="mac">macOS</option>
      <option value="linux">Linux</option>
      <option value="all">All</option>
    </select>
    <select v-model="form.file_type" class="add-file-select" :disabled="busy">
      <option value="game">{{ t('upload.type_game') }}</option>
      <option value="dlc">DLC</option>
      <option value="extra">{{ t('upload.type_extra') }}</option>
    </select>
    <button class="add-file-btn" :disabled="busy || !file" @click="submit">
      {{ busy ? `${progress}%` : t('detail.add_file') }}
    </button>
    <span v-if="error" class="add-file-error">{{ error }}</span>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useI18n } from '@/i18n'
import * as libActions from '@/lib/libraryActions'

const props = defineProps<{ gameId: number | string }>()
const emit = defineEmits<{ (e: 'added'): void }>()

const { t } = useI18n()

const input = ref<HTMLInputElement>()
const file = ref<File | null>(null)
const form = reactive({ os: 'windows', file_type: 'game' })
const busy = ref(false)
const progress = ref(0)
const error = ref('')

function onPicked(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
}

async function submit() {
  if (!props.gameId || !file.value || busy.value) return
  busy.value = true
  progress.value = 0
  error.value = ''
  try {
    await libActions.uploadFile(props.gameId, file.value, {
      os: form.os,
      fileType: form.file_type,
      onProgress: (percent) => { progress.value = percent },
    })
    file.value = null
    // The picker keeps the old name otherwise, so a second add looks like it
    // is about to send the file that already went.
    if (input.value) input.value.value = ''
    emit('added')
  } catch (e: any) {
    // The server's own sentence: somebody else's file under this name, no room
    // left in the allowance, a game this account cannot see.
    error.value = e?.response?.data?.detail || t('upload.failed')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.add-file {
  display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--glass-bg); border: 1px dashed var(--glass-border); border-radius: 6px;
}
.add-file-input { font-size: var(--fs-xs, 10px); color: var(--muted); max-width: 100%; }
.add-file-select {
  padding: 4px 8px; font-size: var(--fs-xs, 10px); font-family: inherit;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 4px); color: var(--text); outline: none;
}
.add-file-btn {
  padding: 6px 14px; border-radius: var(--radius-sm, 4px); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; color: var(--text);
  background: color-mix(in srgb, var(--pl, #7c3aed) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl, #7c3aed) 40%, transparent);
}
.add-file-btn:disabled { opacity: .45; cursor: default; }
.add-file-error { font-size: 12px; color: #f87171; }
</style>
