<!--
  CollectionEditPanel - admin editor for a collection's metadata.

  Mirrors the game metadata editor (LibraryMetadataPanel) chrome: a centred
  glass overlay with a cover preview on the left and the editable fields on the
  right. Name / description / year range / rating, plus a custom cover upload
  (with a "revert to the auto fan" action) and a confirmed delete. The cover is
  persisted immediately (its own endpoint); the text fields are saved together
  via PATCH. Scraper-assisted metadata search is deferred to a later phase.
-->
<template>
  <div class="cep-overlay" @click.self="$emit('close')">
    <div class="cep-panel" @click.stop>

      <!-- ── Header ──────────────────────────────────────────────────────────── -->
      <div class="cep-header">
        <div class="cep-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <span>{{ t('collections.edit') }}</span>
          <span class="cep-name">- {{ collection.name }}</span>
        </div>
        <button class="cep-close" @click="$emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- ── Body ────────────────────────────────────────────────────────────── -->
      <div class="cep-body">

        <!-- Left: cover preview + actions -->
        <div class="cep-left">
          <div class="cep-label">{{ t('meta.tab_cover') }}</div>
          <div class="cep-cover-box">
            <CollectionCover :cover="coverPath" :covers="collection.member_covers" :name="name" color="var(--pl)" />
          </div>
          <label class="cep-upload-btn">
            <input type="file" accept="image/png,image/jpeg,image/webp" class="cep-file" @change="onCoverFile" />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            {{ t('collections.cover_upload') }}
          </label>
          <button v-if="coverPath" class="cep-ghost-btn" :disabled="coverBusy" @click="revertCover">{{ t('collections.cover_revert') }}</button>
          <p class="cep-hint">{{ t('collections.cover_hint') }}</p>
          <div v-if="coverMsg" class="cep-cover-msg">{{ coverMsg }}</div>
        </div>

        <!-- Right: form -->
        <div class="cep-form">
          <div class="cep-section">{{ t('collections.basics') }}</div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('collections.field_name') }}</label>
            <input v-model="name" class="cep-input" maxlength="200" />
          </div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('collections.field_description') }} <span class="cep-hint">({{ t('collections.desc_long_hint') }})</span></label>
            <textarea v-model="description" rows="6" class="cep-textarea"></textarea>
          </div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('collections.field_description_short') }} <span class="cep-hint">({{ t('collections.desc_short_hint') }})</span></label>
            <textarea v-model="descriptionShort" rows="3" class="cep-textarea" maxlength="500"></textarea>
          </div>

          <div class="cep-section" style="margin-top:6px">{{ t('collections.details') }}</div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('collections.year_range') }}</label>
            <label class="cep-check"><input type="checkbox" v-model="yearsAuto" /><span>{{ t('collections.auto_from_games') }}</span></label>
            <div v-if="!yearsAuto" class="cep-field-row">
              <input v-model.number="yearFrom" type="number" class="cep-input" :placeholder="t('collections.year_from')" />
              <input v-model.number="yearTo" type="number" class="cep-input" :placeholder="t('collections.year_to')" />
            </div>
          </div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('collections.field_rating') }}</label>
            <label class="cep-check"><input type="checkbox" v-model="ratingAuto" /><span>{{ t('collections.rating_auto') }}</span></label>
            <input v-if="!ratingAuto" v-model.number="ratingManual" type="number" min="0" max="5" step="0.1" class="cep-input" />
            <span v-else class="cep-hint">{{ avgHint }}</span>
          </div>
          <div class="cep-field">
            <label class="cep-field-label">{{ t('detail.time_to_beat') }}</label>
            <label class="cep-check"><input type="checkbox" v-model="hltbAuto" /><span>{{ t('collections.auto_from_games') }}</span></label>
            <div v-if="!hltbAuto" class="cep-field-row">
              <input v-model.number="hltbMainH" type="number" min="0" step="0.5" class="cep-input" :placeholder="t('collections.hltb_main_h')" />
              <input v-model.number="hltbCompleteH" type="number" min="0" step="0.5" class="cep-input" :placeholder="t('collections.hltb_complete_h')" />
            </div>
            <span v-else class="cep-hint">{{ hltbHint }}</span>
          </div>
        </div>
      </div>

      <!-- ── Footer ──────────────────────────────────────────────────────────── -->
      <div class="cep-footer">
        <button class="cep-btn-delete" :disabled="busy" @click="onDelete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          {{ t('collections.delete') }}
        </button>
        <div class="cep-footer-right">
          <span v-if="saveError" class="cep-err">{{ saveError }}</span>
          <span v-else-if="saveOk" class="cep-ok">✓ {{ t('meta.saved') }}</span>
          <button class="cep-btn-cancel" @click="$emit('close')">{{ t('common.cancel') }}</button>
          <button class="cep-btn-save" :disabled="busy || !canSave" @click="save">
            <div v-if="busy" class="cep-spinner"></div>
            <span v-else>{{ t('common.save') }}</span>
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import client from '@/services/api/client'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const props = defineProps<{ collection: any }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
  (e: 'deleted', slug: string): void
}>()

const { t } = useI18n()
const { gdConfirm } = useDialog()

const c = props.collection
const name        = ref<string>(c.name || '')
const description = ref<string>(c.description || '')
const descriptionShort = ref<string>(c.description_short || '')
// Year range: auto = derived from member release years (both stored as null).
const yearsAuto = ref<boolean>(!!c.start_year_auto && !!c.end_year_auto)
const yearFrom  = ref<number | null>(c.start_year ?? null)
const yearTo    = ref<number | null>(c.end_year ?? null)
// Rating: auto = average of member ratings (stored null); override = manual 0-5.
const ratingAuto   = ref<boolean>(c.rating_auto !== false)
const ratingManual = ref<number | null>(c.rating_auto ? null : (c.rating ?? null))
const coverPath = ref<string | null>(c.cover_path ?? null)
// Time to Beat: auto = average of member playtimes (stored null); override = manual hours.
const hltbAuto      = ref<boolean>(c.hltb_auto !== false)
const hltbMainH     = ref<number | null>(c.hltb_auto ? null : (c.hltb_main_s ? c.hltb_main_s / 3600 : null))
const hltbCompleteH = ref<number | null>(c.hltb_auto ? null : (c.hltb_complete_s ? c.hltb_complete_s / 3600 : null))

// The computed member-average rating, shown as a hint while in auto mode.
const avg = computed<number | null>(() => (c.rating != null ? Number(c.rating) : null))
const avgHint = computed(() =>
  t('collections.rating_avg', { value: avg.value != null ? avg.value.toFixed(1) : '-' }),
)
function _fmtH(s: number | null | undefined): string {
  if (!s) return '-'
  const h = Math.floor(s / 3600); const m = Math.round((s % 3600) / 60)
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`
}
const hltbHint = computed(() => t('collections.hltb_avg', { main: _fmtH(c.hltb_main_s), complete: _fmtH(c.hltb_complete_s) }))

const busy      = ref(false)
const coverBusy = ref(false)
const saveError = ref('')
const saveOk    = ref(false)
const coverMsg  = ref('')

const canSave = computed(() => name.value.trim().length > 0)

async function onCoverFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  coverBusy.value = true; coverMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await client.post(`/collections/${c.slug}/cover`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    coverPath.value = data.cover_path
    coverMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverMsg.value = err?.response?.data?.detail || 'Upload failed'
  } finally {
    coverBusy.value = false
    input.value = ''
  }
}

async function revertCover() {
  coverBusy.value = true; coverMsg.value = ''
  try {
    await client.patch(`/collections/${c.slug}`, { cover_path: null })
    coverPath.value = null
    coverMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverMsg.value = err?.response?.data?.detail || 'Failed'
  } finally {
    coverBusy.value = false
  }
}

async function save() {
  if (!canSave.value) return
  busy.value = true; saveError.value = ''; saveOk.value = false
  try {
    const payload: Record<string, unknown> = {
      name: name.value.trim(),
      description: description.value ? description.value : null,
      description_short: descriptionShort.value ? descriptionShort.value : null,
      start_year: yearsAuto.value ? null : (yearFrom.value != null ? Number(yearFrom.value) : null),
      end_year:   yearsAuto.value ? null : (yearTo.value != null ? Number(yearTo.value) : null),
      rating:     ratingAuto.value ? null : (ratingManual.value != null ? Number(ratingManual.value) : null),
      hltb_main_s:     hltbAuto.value ? null : (hltbMainH.value != null ? Math.round(Number(hltbMainH.value) * 3600) : null),
      hltb_complete_s: hltbAuto.value ? null : (hltbCompleteH.value != null ? Math.round(Number(hltbCompleteH.value) * 3600) : null),
    }
    await client.patch(`/collections/${c.slug}`, payload)
    saveOk.value = true
    emit('updated')
    setTimeout(() => emit('close'), 700)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Save failed'
  } finally {
    busy.value = false
  }
}

async function onDelete() {
  const ok = await gdConfirm(
    t('collections.delete_confirm', { name: c.name }),
    { title: t('collections.delete'), danger: true, confirmText: t('common.delete'), cancelText: t('common.cancel') },
  )
  if (!ok) return
  busy.value = true; saveError.value = ''
  try {
    await client.delete(`/collections/${c.slug}`)
    emit('deleted', c.slug)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Delete failed'
    busy.value = false
  }
}
</script>

<style scoped>
.cep-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  animation: cep-fade-in .18s ease;
}
@keyframes cep-fade-in { from { opacity: 0; } to { opacity: 1; } }

.cep-panel {
  width: 90vw; max-width: 760px; max-height: 90vh;
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  display: flex; flex-direction: column; overflow: hidden;
  animation: cep-slide-up .2s cubic-bezier(.23,1,.32,1);
}
@keyframes cep-slide-up { from { transform: translateY(24px); opacity: 0; } to { transform: none; opacity: 1; } }

.cep-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--glass-border); flex-shrink: 0;
}
.cep-header-left {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.cep-name { color: var(--muted); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 360px; }
.cep-close {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s; flex-shrink: 0;
}
.cep-close:hover { background: rgba(255,255,255,.12); color: var(--text); }

.cep-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }

/* Left - cover preview */
.cep-left {
  width: 210px; flex-shrink: 0; padding: 18px;
  border-right: 1px solid var(--glass-border);
  overflow-y: auto; background: rgba(255,255,255,.02);
  display: flex; flex-direction: column; gap: 10px;
}
.cep-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px;
}
.cep-cover-box {
  position: relative; width: 100%; aspect-ratio: 1 / 1;
  border-radius: var(--radius-sm, 8px); overflow: hidden;
  background: var(--bg2, rgba(0,0,0,.3)); border: 1px solid var(--glass-border);
}
.cep-upload-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--text); font-size: 12px; font-weight: 600; transition: all .15s;
}
.cep-upload-btn:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.25); }
.cep-file { display: none; }
.cep-ghost-btn {
  padding: 7px 12px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 12px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-ghost-btn:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.cep-ghost-btn:disabled { opacity: .5; cursor: not-allowed; }
.cep-hint { margin: 0; font-size: 11px; color: var(--muted); line-height: 1.5; }
.cep-cover-msg { font-size: 12px; color: #4ade80; }

/* Right - form */
.cep-form { flex: 1; padding: 18px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.cep-section {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px;
  padding-bottom: 4px; border-bottom: 1px solid var(--glass-border);
}
.cep-field { display: flex; flex-direction: column; gap: 6px; }
.cep-field-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; }
.cep-field-row { display: flex; gap: var(--space-2, 8px); }
.cep-input {
  flex: 1; background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; transition: border-color .15s; width: 100%;
}
.cep-input:focus { border-color: var(--pl); }
.cep-textarea {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; resize: vertical; transition: border-color .15s; line-height: 1.6;
}
.cep-textarea:focus { border-color: var(--pl); }
.cep-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
.cep-check input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; accent-color: var(--pl); }

/* Footer */
.cep-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
  flex-shrink: 0; background: rgba(255,255,255,.02);
}
.cep-footer-right { display: flex; align-items: center; gap: 10px; }
.cep-ok  { color: #4ade80; font-size: 13px; }
.cep-err { color: #f87171; font-size: 13px; }
.cep-btn-delete {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, #ef4444 16%, transparent); border: 1px solid color-mix(in srgb, #ef4444 40%, transparent);
  color: #fca5a5; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-btn-delete:hover:not(:disabled) { background: color-mix(in srgb, #ef4444 28%, transparent); border-color: #ef4444; color: #fff; }
.cep-btn-delete:disabled { opacity: .5; cursor: not-allowed; }
.cep-btn-cancel {
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-btn-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cep-btn-save {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 9px 22px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 12px var(--pglow2, transparent);
}
.cep-btn-save:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.cep-btn-save:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.cep-spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.25); border-top-color: var(--pl-light, #fff);
  animation: cep-spin .7s linear infinite;
}
@keyframes cep-spin { to { transform: rotate(360deg); } }

@media (max-width: 640px) {
  .cep-body { flex-direction: column; overflow-y: auto; }
  .cep-left { width: auto; border-right: none; border-bottom: 1px solid var(--glass-border); flex-direction: row; flex-wrap: wrap; align-items: center; }
  .cep-cover-box { width: 120px; }
}
</style>
