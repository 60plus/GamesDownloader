<!--
  RomAddFileForm - add one file to a ROM game from its page (1.0.36).

  The ROM side of AddFileForm. An extra, a mod or the manual goes into the
  game's own folder; a further disc or file of the game goes in beside it and
  is scanned into the library. Administrators and uploaders alike, the bytes
  counting against the account that sends them. Every skin opens it the same
  way, through `__GD__.ui.openRomAddFileDialog`, so every skin sends the same
  request and shows the same refusal.
-->
<template>
  <div class="raf">
    <input
      ref="input"
      type="file"
      class="raf-input"
      :accept="kind === 'manual' ? 'application/pdf,.pdf' : undefined"
      :disabled="busy"
      @change="onPicked"
    />
    <select v-model="kind" class="raf-select" :disabled="busy">
      <option value="extra">{{ t('upload.type_extra') }}</option>
      <option value="mod">{{ t('upload.type_mod') }}</option>
      <option value="manual">{{ t('upload.type_manual') }}</option>
      <option v-if="platformFsSlug" value="game">{{ t('upload.type_disc') }}</option>
    </select>
    <button class="raf-btn" :disabled="busy || !file" @click="submit(false)">
      {{ busy ? `${progress}%` : t('detail.add_file') }}
    </button>
    <span v-if="hint" class="raf-hint">{{ hint }}</span>
    <span v-if="message" class="raf-msg" :class="{ 'raf-msg--bad': refused }">{{ message }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'
import { addRomFile, type RomFileKind } from '@/lib/romSourceActions'
import { describeUpload, uploadHadRefusals } from '@/lib/uploadResult'

const props = defineProps<{ romId: number; platformFsSlug?: string | null }>()
const emit = defineEmits<{ (e: 'added', scanning: boolean): void }>()

const { t } = useI18n()
const { gdConfirm } = useDialog()

const input = ref<HTMLInputElement>()
const file = ref<File | null>(null)
const kind = ref<RomFileKind>('extra')
const busy = ref(false)
const progress = ref(0)
const message = ref('')
const refused = ref(false)

const hint = computed(() =>
  kind.value === 'manual' ? t('upload.hint_manual')
    : kind.value === 'game' ? t('upload.hint_disc') : '')

// What each refusal of POST /roms/{id}/files is called (X-GD-Reason) and the
// words for it. The server names, the screen says (lib/uploadResult.ts); a name
// not listed here shows the server's own sentence rather than nothing.
const REASONS: Record<string, string> = {
  not_yours: 'library.reject_already_here',
  no_folder: 'library.reject_no_folder',
  threat: 'library.reject_threat',
  not_pdf: 'upload.reject_not_pdf',
  no_room: 'upload.reject_no_room',
  bad_name: 'upload.reject_bad_name',
  busy: 'upload.reject_busy',
  not_a_file: 'upload.reject_not_a_file',
}

function onPicked(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null
  message.value = ''
  refused.value = false
}

async function submit(overwrite: boolean) {
  if (!props.romId || !file.value || busy.value) return
  busy.value = true
  progress.value = 0
  message.value = ''
  refused.value = false
  let askToReplace = false
  const sent = kind.value
  try {
    const data = await addRomFile(props.romId, file.value, {
      kind: sent,
      platformFsSlug: props.platformFsSlug,
      overwrite,
      onProgress: (percent) => { progress.value = percent },
    })
    if (sent === 'game') {
      // The platform upload's own answer: what landed, and why anything did not.
      message.value = describeUpload(data, t)
      refused.value = uploadHadRefusals(data)
      if (refused.value) return
    }
    file.value = null
    // The picker keeps the old name otherwise, so a second add looks like it
    // is about to send the file that already went.
    if (input.value) input.value.value = ''
    // A further disc is registered by a scan after the upload answers, so the
    // host asks the page again while that runs (PluginUiHost.onRomFileAdded).
    emit('added', sent === 'game')
  } catch (e: any) {
    const reason = e?.response?.headers?.['x-gd-reason'] as string | undefined
    const detail = e?.response?.data?.detail
    // A name already there is replaced only when asked. Asked here, once, and
    // sent again with overwrite; the server still decides who may.
    if (reason === 'already_here' && !overwrite) {
      askToReplace = true
    } else {
      const key = reason ? REASONS[reason] : undefined
      message.value = key && file.value
        ? `${file.value.name} - ${t(key)}`
        : (typeof detail === 'string' && detail) || t('upload.failed')
      refused.value = true
    }
  } finally {
    busy.value = false
  }
  if (askToReplace && file.value
      && await gdConfirm(t('upload.replace_confirm', { name: file.value.name }),
                         { confirmText: t('common.replace') })) {
    await submit(true)
  }
}
</script>

<style scoped>
.raf {
  display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--glass-bg); border: 1px dashed var(--glass-border); border-radius: 6px;
}
.raf-input { font-size: var(--fs-xs, 10px); color: var(--muted); max-width: 100%; }
.raf-select {
  padding: 4px 8px; font-size: var(--fs-xs, 10px); font-family: inherit;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 4px); color: var(--text); outline: none;
}
.raf-btn {
  padding: 6px 14px; border-radius: var(--radius-sm, 4px); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; color: var(--text);
  background: color-mix(in srgb, var(--pl, #7c3aed) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl, #7c3aed) 40%, transparent);
}
.raf-btn:disabled { opacity: .45; cursor: default; }
.raf-hint { flex-basis: 100%; font-size: 11px; color: var(--muted); }
.raf-msg { flex-basis: 100%; font-size: 12px; color: #4ade80; }
.raf-msg--bad { color: #f87171; }
</style>
