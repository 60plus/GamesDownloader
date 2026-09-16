<!--
  Rows whose file is gone.

  Every listing, count and search in the application filters these out, so a row
  pointing into empty space is not merely unimportant, it is invisible. Nobody
  could learn that forty entries point at nothing, and the saves and play history
  hanging off them were equally out of sight.

  One button with a count, above the per-platform cards, rather than a control on
  each of them: the question somebody has is "what has gone missing", not "has
  anything gone missing on the Amiga". Disabled when the answer is none, which is
  itself the useful answer most of the time.

  Removing takes the ENTRY. There is no file to take - that is what made it
  missing - but the saves and the play history go with it, so it asks for a tick.
-->
<template>
  <div class="mr">
    <button class="mr-btn" :class="{ 'mr-btn--some': count > 0 }"
            :disabled="!count || busy" @click="open = true">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" /><path d="M12 8v5m0 3h.01" stroke-linecap="round" />
      </svg>
      {{ count ? t('mr.button', { n: count }) : t('mr.none', 'No missing files') }}
    </button>
    <span v-if="msg" class="mr-msg" :class="{ 'mr-msg--bad': !ok }">{{ msg }}</span>

    <teleport to="body">
      <transition name="mr-fade">
        <div v-if="open" class="mr-overlay" @click.self="open = false">
          <div class="mr-modal glass">
            <div class="mr-head">
              <div class="mr-title">{{ t('mr.title', 'Files that are gone') }}</div>
              <button class="mr-close" :aria-label="t('common.close', 'Close')"
                      @click="open = false">&times;</button>
            </div>

            <p class="mr-lede">{{ t('mr.lede', 'These entries point at files that are no longer on disk.') }}</p>

            <div class="mr-list">
              <div v-for="group in grouped" :key="group.slug" class="mr-group">
                <div class="mr-group-head">
                  {{ group.name }}
                  <span class="mr-group-n">{{ group.rows.length }}</span>
                </div>
                <div v-for="row in group.rows" :key="row.id" class="mr-row">
                  <div class="mr-row-text">
                    <span class="mr-row-title">{{ row.name }}</span>
                    <span class="mr-row-path">{{ row.path }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="mr-warn">{{ t('mr.warn', 'Removing takes the entries and everything hanging off them: saves, play history, collection membership. The files are already gone.') }}</div>

            <div class="mr-foot">
              <button class="mr-act" @click="open = false">{{ t('common.cancel', 'Cancel') }}</button>
              <button class="mr-act mr-act--danger" :disabled="busy" @click="remove">
                {{ t('mr.remove', { n: count }) }}
              </button>
            </div>
          </div>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const { gdConfirm } = useDialog()

interface Row {
  id: number
  name: string
  path: string
  platform_slug: string
  platform_name: string
}

const rows  = ref<Row[]>([])
const open  = ref(false)
const busy  = ref(false)
const msg   = ref('')
const ok    = ref(true)

const count = computed(() => rows.value.length)

/** By platform, in the order the server sent them, which is already sorted. */
const grouped = computed(() => {
  const out: { slug: string; name: string; rows: Row[] }[] = []
  for (const row of rows.value) {
    let group = out.find(g => g.slug === row.platform_slug)
    if (!group) {
      group = { slug: row.platform_slug, name: row.platform_name, rows: [] }
      out.push(group)
    }
    group.rows.push(row)
  }
  return out
})

async function load() {
  try {
    const { data } = await client.get('/roms/missing')
    rows.value = (data?.roms || []) as Row[]
  } catch {
    // A count nobody can read is better than a wrong one. The button stays
    // disabled and says there is nothing, which is what it says on a healthy
    // library too - so the failure is reported rather than dressed up.
    rows.value = []
    msg.value = t('mr.load_failed', 'Could not check for missing files.')
    ok.value = false
  }
}

async function remove() {
  const sure = await gdConfirm(
    t('mr.confirm', { n: count.value }),
    { title: t('mr.title', 'Files that are gone'), danger: true, requireTick: true },
  )
  if (!sure) return
  busy.value = true
  msg.value = ''
  // The ids that were on screen. A drive coming back between the list and the
  // click makes a row stop being missing, and the server leaves those alone.
  const ids = rows.value.map(r => r.id)
  try {
    const { data } = await client.post('/roms/missing/remove', { ids })
    const removed = Number(data?.removed ?? 0)
    const failed = (data?.failed || []) as number[]
    open.value = false
    msg.value = failed.length
      ? t('mr.removed_failed', { n: removed, failed: failed.length })
      : t('mr.removed', { n: removed })
    ok.value = !failed.length
    await load()
  } catch (e: any) {
    msg.value = e?.response?.data?.detail || t('mr.remove_failed', 'Could not remove them.')
    ok.value = false
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mr { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }

.mr-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.mr-btn:disabled { opacity: .5; cursor: default; }
/* Amber, not red: something to look at, not something going wrong. */
.mr-btn--some {
  background: color-mix(in srgb, #fbbf24 15%, transparent);
  border-color: color-mix(in srgb, #fbbf24 40%, transparent);
  color: #fbbf24;
}
.mr-btn--some:hover:not(:disabled) {
  background: color-mix(in srgb, #fbbf24 28%, transparent);
  border-color: #fbbf24;
}

.mr-msg { font-size: var(--fs-sm, 12px); color: var(--success, #4ade80); }
.mr-msg--bad { color: #fbbf24; }

.mr-overlay {
  position: fixed; inset: 0; z-index: 950;
  display: flex; align-items: center; justify-content: center;
  padding: 5vh 1rem; background: rgba(0,0,0,.55);
}
.mr-modal {
  width: min(680px, 100%); max-height: 90vh;
  display: flex; flex-direction: column; gap: 12px;
  padding: 18px 20px; border-radius: var(--radius);
  border: 1px solid var(--glass-border); background: var(--panel, var(--glass-bg));
  backdrop-filter: blur(18px);
}
.mr-head { display: flex; align-items: center; gap: 12px; }
.mr-title { flex: 1; font-size: 15px; font-weight: 600; color: var(--text); }
.mr-close {
  background: none; border: 0; color: var(--muted); cursor: pointer;
  font-size: 22px; line-height: 1; padding: 0 4px;
}
.mr-close:hover { color: var(--text); }
.mr-lede { margin: 0; font-size: 12px; color: var(--muted); }

.mr-list { overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.mr-group { display: flex; flex-direction: column; gap: 2px; }
.mr-group-head {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted);
  padding-bottom: 4px; border-bottom: 1px solid var(--glass-border);
}
.mr-group-n {
  font-family: var(--font-mono, monospace); font-weight: 500;
  font-variant-numeric: tabular-nums; opacity: .7;
}
.mr-row { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,.04); }
.mr-row:last-child { border-bottom: 0; }
.mr-row-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.mr-row-title { font-size: 12px; font-weight: 600; color: var(--text); }
.mr-row-path {
  font-size: 11px; color: var(--muted); font-family: var(--font-mono, monospace);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.mr-warn {
  padding: 8px 10px; border-radius: var(--radius-sm);
  font-size: 11px; line-height: 1.5; color: #f87171;
  background: color-mix(in srgb, #f87171 8%, transparent);
  border: 1px solid color-mix(in srgb, #f87171 28%, transparent);
}

.mr-foot { display: flex; justify-content: flex-end; gap: 8px; }
.mr-act {
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.mr-act:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.mr-act:disabled { opacity: .45; cursor: default; }
.mr-act--danger {
  background: color-mix(in srgb, #f87171 18%, transparent);
  border-color: color-mix(in srgb, #f87171 45%, transparent);
  color: #f87171;
}
.mr-act--danger:hover:not(:disabled) {
  background: color-mix(in srgb, #f87171 30%, transparent);
  border-color: #f87171; color: #fff;
}

.mr-fade-enter-active, .mr-fade-leave-active { transition: opacity .15s; }
.mr-fade-enter-from, .mr-fade-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .mr-fade-enter-active, .mr-fade-leave-active { transition: none; }
}
</style>
