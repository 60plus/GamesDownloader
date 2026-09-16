<!--
  Paths a scan is told never to look at.

  The case it exists for: a modding folder kept beside the Amiga ROMs was picked
  up and reported as a game every single scan, forever. Deleting the entry did
  nothing, because the next scan found the file again and put it straight back.

  Two rules shape this screen, and both come from the owner:

  1. SAVING A PATTERN CHANGES NOTHING THAT IS ALREADY HERE. It only stops a
     future scan adding something, and deleting the line undoes it. Removing
     what has already slipped in is a separate act, with the list shown first.

  2. THE LIST SHOWN IS THE LIST REMOVED. The server works out what the SAVED
     patterns cover, so the check and the removal are offered only while the box
     matches what is saved - otherwise somebody confirms one list and loses
     another.

  One component for both sides: a ROM platform and a games library are the same
  thing from a scanner's point of view, a folder that gets walked.
-->
<template>
  <div class="xc">
    <div v-if="!items.length" class="xc-note">{{ emptyText }}</div>

    <div v-for="e in entries" :key="e.slug" class="xc-card">
      <button class="xc-head" @click="e.card.open = !e.card.open">
        <div class="xc-head-text">
          <span class="xc-title">{{ e.name }}</span>
          <span class="xc-sub">{{ e.sub }}</span>
        </div>
        <span v-if="e.card.saved.length" class="xc-chip xc-chip--set">
          {{ t('xc.n_patterns', { n: e.card.saved.length }) }}
        </span>
        <svg class="xc-chevron" :class="{ 'xc-chevron--open': e.card.open }"
             width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      <div v-if="e.card.open" class="xc-body">
        <!-- A card that could not be read shows that, and offers to try again.
             It must NOT fall through to an empty box: saving one would write
             nothing over the patterns that really are stored. -->
        <div v-if="e.card.failed" class="xc-foot" style="margin-top:0">
          <button class="xc-btn" :disabled="e.card.busy" @click="load(e.slug)">
            {{ t('xc.retry', 'Try again') }}
          </button>
          <span class="xc-msg xc-msg--bad">{{ t('xc.load_failed', 'Could not read what is saved here.') }}</span>
        </div>

        <div v-else-if="!e.card.loaded" class="xc-note">{{ t('xc.loading', 'Loading…') }}</div>

        <template v-else>
          <textarea
            v-model="e.card.draft"
            class="xc-area"
            rows="4"
            spellcheck="false"
            :disabled="e.card.busy"
            :placeholder="placeholder"
          />
          <p class="xc-help">{{ help }}</p>

          <div class="xc-foot">
            <!-- btn-save-action is the house rule, not decoration: it swaps the
                 accent to amber so every Save in the app is the same colour.
                 Without it this card had a purple Save sitting on a screen whose
                 other Save is amber. -->
            <button class="xc-btn xc-btn--primary btn-save-action"
                    :disabled="!dirty(e.card) || e.card.busy"
                    @click="save(e.slug)">
              {{ e.card.busy ? t('xc.working', 'Working…') : t('common.save', 'Save') }}
            </button>
            <span v-if="e.card.msg" class="xc-msg" :class="{ 'xc-msg--bad': !e.card.ok }">
              {{ e.card.msg }}
            </span>
          </div>

          <!-- Told which lines were dropped and why, rather than silently
               saving less than was typed. -->
          <div v-if="e.card.ignored.length" class="xc-warn">
            {{ t('xc.ignored', { lines: e.card.ignored.join(', ') }) }}
          </div>

          <div class="xc-sep" />

          <div class="xc-foot">
            <button class="xc-btn"
                    :disabled="dirty(e.card) || !e.card.saved.length || e.card.busy"
                    @click="check(e.slug)">
              {{ t('xc.check', 'Show what these cover') }}
            </button>
            <span v-if="dirty(e.card)" class="xc-hint">
              {{ t('xc.save_first', 'Save first: this reads what is saved, not what is typed.') }}
            </span>
            <span v-else-if="!e.card.saved.length" class="xc-hint">
              {{ t('xc.nothing_saved', 'Nothing is saved here yet.') }}
            </span>
          </div>

          <div v-if="e.card.checked">
            <div v-if="!e.card.found.length" class="xc-note">
              {{ t('xc.covers_nothing', 'Nothing already in the library matches.') }}
            </div>
            <template v-else>
              <div class="xc-found-head">
                {{ t('xc.covers_n', { n: e.card.found.length }) }}
              </div>
              <div v-for="row in e.card.found" :key="row.key" class="xc-row">
                <div class="xc-row-text">
                  <span class="xc-row-title">{{ row.title }}</span>
                  <span class="xc-row-path">{{ row.path }}</span>
                </div>
                <span class="xc-row-meta">{{ row.meta }}</span>
              </div>
              <div class="xc-warn xc-warn--danger">
                {{ t('xc.apply_warn', 'Removes the entries, not the files.') }}
              </div>
              <div class="xc-foot">
                <button class="xc-btn xc-btn--danger" :disabled="e.card.busy"
                        @click="apply(e.slug)">
                  {{ t('xc.apply', { n: e.card.found.length }) }}
                </button>
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, watch } from 'vue'
import client from '@/services/api/client'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const { gdConfirm } = useDialog()

interface Item { slug: string; name: string; sub?: string }
interface Row  { id: number; key: string; title: string; path: string; meta: string }

interface Card {
  open: boolean
  // Read from the server, not guessed. `loaded` is what separates "no patterns
  // here" from "not asked yet" - without it an empty box looks like the saved
  // state and Save would appear to have nothing to do.
  loaded: boolean
  // The read failed. Kept apart from `loaded` on purpose: a card that fell back
  // to "loaded and empty" would offer an empty box as the saved state, and the
  // next Save would write that over patterns that really are stored.
  failed: boolean
  saved: string[]
  draft: string
  // Whether the check has been run since the last save. The list it produced is
  // the list the removal acts on, so a save clears it.
  checked: boolean
  found: Row[]
  ignored: string[]
  msg: string
  ok: boolean
  // Per card, not per component. One shared flag meant a fast card finishing
  // re-enabled the buttons on a slow one that was still mid-request.
  busy: boolean
  // Bumped whenever this card starts something new. A reply that comes back
  // carrying a stale number is dropped, so a slow preview cannot land after a
  // save and revive a list describing patterns that are no longer saved.
  gen: number
}

const props = defineProps<{
  kind: 'platform' | 'library'
  items: Item[]
}>()

function blank(): Card {
  return { open: false, loaded: false, failed: false, saved: [], draft: '',
           checked: false, found: [], ignored: [], msg: '', ok: true,
           busy: false, gen: 0 }
}

const cards = reactive<Record<string, Card>>({})

// The list the template walks, each item paired with its own state. Pairing it
// here rather than looking one up per expression keeps the template out of
// possibly-missing territory, which is how the type checker reads it.
//
// An item with no state yet is left out rather than shown against a shared
// stand-in. Rendering must not create state - a render that adds a key triggers
// the next one - and one stand-in shared by every card would collect "open"
// from whichever card was clicked first and hand it to all of them. The state
// is made the moment the item list arrives, at the bottom of this block, so
// this drops nothing for longer than a frame.
const entries = computed(() => props.items.flatMap((it) => {
  const card = cards[it.slug]
  return card ? [{ slug: it.slug, name: it.name, sub: it.sub || it.slug, card }] : []
}))

const emptyText = computed(() => props.kind === 'platform'
  ? t('xc.no_platforms', 'No platforms yet. One appears here once it has ROMs.')
  : t('xc.no_libraries', 'No library here is walked by a folder scan.'))

// Said separately for each side, because the two sides genuinely differ and a
// shared sentence had to lie about one of them. The ROM scan reads the platform
// folder itself and does not descend, so a folder pattern there has nothing to
// act on; the games scan walks folders, so a folder pattern is the main thing
// somebody writes.
const help = computed(() => props.kind === 'platform'
  ? t('xc.help_platform', 'One per line: a file name or a mask.')
  : t('xc.help_library', 'One per line: a folder, a name or a mask.'))

const placeholder = computed(() => (props.kind === 'platform'
  ? ['mods.zip', '*.txt', 'Thumbs.db']
  : ['_originals/', 'mods/', 'Thumbs.db']).join('\n'))

function base(slug: string): string {
  return props.kind === 'platform'
    ? `/roms/platforms/${encodeURIComponent(slug)}/exclusions`
    : `/libraries/${encodeURIComponent(slug)}/exclusions`
}

/** The lines of the box that are patterns, as the server reads them.
 *
 *  Notes and blank lines are not patterns, so they must not make a card look
 *  edited. Comparing raw text did exactly that: the help text invites `#` notes,
 *  and every one of them left the card permanently unequal to what was saved,
 *  which kept the check and the removal disabled for good. */
function typedPatterns(draft: string): string[] {
  return draft.split('\n')
    .map(l => l.trim())
    .filter(l => l && !l.startsWith('#'))
}

function dirty(card: Card): boolean {
  const typed = typedPatterns(card.draft)
  return typed.length !== card.saved.length
    || typed.some((p, i) => p !== card.saved[i])
}

function prettySize(bytes: number): string {
  if (!bytes) return ''
  const u = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${u[i]}`
}

function toRows(data: any): Row[] {
  if (props.kind === 'platform') {
    return ((data?.roms || []) as any[]).map(r => ({
      id:    Number(r.id),
      key:   `r${r.id}`,
      title: r.name || r.fs_name,
      path:  String(r.path || ''),
      meta:  prettySize(Number(r.size_bytes || 0)),
    }))
  }
  return ((data?.games || []) as any[]).map(g => ({
    id:    Number(g.id),
    key:   `g${g.id}`,
    title: g.title,
    path:  String(g.path || ''),
    meta:  t('xc.n_files', { n: Number(g.files ?? 0) }),
  }))
}

function samePatterns(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((p, i) => p === b[i])
}

function note(card: Card, text: string, good: boolean) {
  card.msg = text
  card.ok = good
}

async function load(slug: string) {
  const card = cards[slug]
  if (!card) return
  const gen = ++card.gen
  card.busy = true
  card.failed = false
  card.msg = ''
  try {
    const { data } = await client.get(base(slug))
    if (card.gen !== gen) return
    card.saved = (data?.patterns || []) as string[]
    card.draft = card.saved.join('\n')
    card.loaded = true
  } catch {
    if (card.gen !== gen) return
    // Deliberately NOT `loaded`. A card that claimed to be loaded and empty
    // would put an empty box in front of somebody whose patterns are fine, and
    // the next Save would write that emptiness over them.
    card.failed = true
  } finally {
    if (card.gen === gen) card.busy = false
  }
}

async function save(slug: string) {
  const card = cards[slug]
  if (!card) return
  const gen = ++card.gen
  card.busy = true
  card.msg = ''
  const sent = card.draft
  try {
    const { data } = await client.put(base(slug), { patterns: sent })
    if (card.gen !== gen) return
    card.saved = (data?.patterns || []) as string[]
    const ignored = (data?.ignored || []) as string[]
    card.ignored = ignored
    // The typed text back, minus only the lines the server refused. Rebuilding
    // it from the saved patterns instead threw away every `#` note in the box,
    // which the help text directly underneath invites people to write.
    card.draft = sent.split('\n')
      .filter(line => !ignored.includes(line.trim()))
      .join('\n')
    // Whatever was listed described the previous patterns.
    card.checked = false
    card.found = []
    note(card, t('xc.saved', 'Saved. Nothing already in the library changed.'), true)
  } catch (e: any) {
    if (card.gen !== gen) return
    note(card, e?.response?.data?.detail || t('xc.save_failed', 'Could not save.'), false)
  } finally {
    if (card.gen === gen) card.busy = false
  }
}

async function check(slug: string) {
  const card = cards[slug]
  if (!card) return
  const gen = ++card.gen
  card.busy = true
  card.msg = ''
  try {
    const { data } = await client.get(`${base(slug)}/preview`)
    if (card.gen !== gen) return
    // The preview reports the patterns it ran against. If they are not the ones
    // this screen thinks are saved, somebody else has been here since - another
    // tab, another administrator - and the list about to be drawn describes a
    // rule this person never agreed to. Take the new patterns and say so
    // instead of showing it.
    const server = (data?.patterns || []) as string[]
    if (!samePatterns(server, card.saved)) {
      card.saved = server
      card.draft = server.join('\n')
      card.checked = false
      card.found = []
      note(card, t('xc.changed_elsewhere',
        'Somebody changed these patterns while this page was open. Reloaded them, look again.'), false)
      return
    }
    card.found = toRows(data)
    card.checked = true
  } catch {
    if (card.gen === gen) {
      note(card, t('xc.check_failed', 'Could not work out what these cover.'), false)
    }
  } finally {
    if (card.gen === gen) card.busy = false
  }
}

async function apply(slug: string) {
  const card = cards[slug]
  if (!card) return
  // The list above is the confirmation the owner asked for; this is the tick
  // that the rest of the app puts in front of anything that takes entries and
  // their saves away. The same dialog guards deleting a library.
  const sure = await gdConfirm(
    t('xc.confirm', { n: card.found.length }),
    { title: t('xc.confirm_title', 'Remove these entries'), danger: true, requireTick: true },
  )
  if (!sure) return
  const gen = ++card.gen
  card.busy = true
  card.msg = ''
  // The ids that were on screen. The server removes only these, whatever the
  // patterns cover by the time it reads them, so nothing can go that this
  // person did not see and confirm.
  const ids = card.found.map(r => r.id)
  try {
    const { data } = await client.post(`${base(slug)}/apply`, { ids })
    if (card.gen !== gen) return
    const removed = Number(data?.removed ?? 0)
    const skipped = (data?.skipped || []) as number[]
    const failed = (data?.failed || []) as number[]
    // The ones that did not go stay on screen. Clearing the whole list put the
    // amber "could not remove 2" directly above the sentence "nothing already
    // in the library matches" - two statements contradicting each other, with
    // nothing left identifying the two entries that are still there and still
    // match. The only way back to them was to press the button again, which the
    // message gave no reason to do.
    card.found = failed.length
      ? card.found.filter(row => failed.includes(row.id))
      : []
    // A partial removal is the state somebody must not miss: some entries are
    // already gone, so pressing the button again is the wrong reflex.
    if (failed.length) {
      note(card, t('xc.removed_failed', { n: removed, failed: failed.length }), false)
    } else {
      note(card, skipped.length
        ? t('xc.removed_some', { n: removed, skipped: skipped.length })
        : t('xc.removed', { n: removed }), true)
    }
  } catch (e: any) {
    if (card.gen !== gen) return
    note(card, e?.response?.data?.detail || t('xc.apply_failed', 'Could not remove them.'), false)
  } finally {
    if (card.gen === gen) card.busy = false
  }
}

// Read every card up front so the headers can say which ones have something
// saved. It is one row each, and it is the question somebody opening this
// screen is asking: where did I already set this up. The parent fetches its
// list asynchronously, so this waits for the list rather than for mount.
watch(() => props.items, (list) => {
  for (const it of list) {
    if (cards[it.slug]) continue
    cards[it.slug] = blank()
    load(it.slug)
  }
}, { immediate: true, deep: false })
</script>

<style scoped>
.xc { display: flex; flex-direction: column; gap: 8px; }
.xc-note { font-size: var(--fs-sm, 12px); color: var(--muted); padding: 6px 2px; }

.xc-card {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  background: var(--glass-bg); overflow: hidden;
}
.xc-head {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: none; border: 0; cursor: pointer;
  font-family: inherit; text-align: left; color: var(--text);
}
.xc-head-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.xc-title { font-size: 13px; font-weight: 600; color: var(--text); }
.xc-sub   { font-size: 11px; color: var(--muted); font-family: var(--font-mono, monospace); }

.xc-chip {
  flex-shrink: 0; font-size: 11px; font-weight: 600; padding: 3px 9px;
  border-radius: 999px; color: var(--muted);
  background: rgba(255,255,255,.05); border: 1px solid var(--glass-border);
}
.xc-chip--set {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 45%, transparent);
  color: var(--pl-light);
}
.xc-chevron { flex-shrink: 0; color: var(--muted); transition: transform var(--transition); }
.xc-chevron--open { transform: rotate(180deg); }

.xc-body { border-top: 1px solid var(--glass-border); padding: 10px 12px 12px; }

.xc-area {
  width: 100%; box-sizing: border-box; resize: vertical;
  padding: 8px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(0,0,0,.18);
  color: var(--text); font-size: 12px; line-height: 1.6;
  font-family: var(--font-mono, monospace);
}
.xc-area:focus { outline: none; border-color: color-mix(in srgb, var(--pl) 55%, transparent); }
.xc-help { margin: 6px 0 0; font-size: 11px; color: var(--muted); line-height: 1.5; }

.xc-foot { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
.xc-msg  { font-size: var(--fs-sm, 12px); color: var(--success, #4ade80); }
.xc-msg--bad { color: #fbbf24; }
.xc-hint { font-size: 11px; color: var(--muted); }

.xc-warn {
  margin-top: 10px; padding: 8px 10px; border-radius: var(--radius-sm);
  font-size: 11px; line-height: 1.5; color: #fbbf24;
  background: color-mix(in srgb, #fbbf24 8%, transparent);
  border: 1px solid color-mix(in srgb, #fbbf24 28%, transparent);
}
.xc-warn--danger {
  color: #f87171;
  background: color-mix(in srgb, #f87171 8%, transparent);
  border-color: color-mix(in srgb, #f87171 28%, transparent);
}

.xc-sep { height: 1px; margin: 12px 0 0; background: var(--glass-border); }

.xc-found-head { margin-top: 10px; font-size: 12px; font-weight: 600; color: var(--text); }
.xc-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,.04);
}
.xc-row:last-of-type { border-bottom: 0; }
.xc-row-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.xc-row-title { font-size: 12px; font-weight: 600; color: var(--text); }
.xc-row-path {
  font-size: 11px; color: var(--muted); font-family: var(--font-mono, monospace);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.xc-row-meta {
  flex-shrink: 0; font-size: 10px; color: var(--muted); opacity: .75;
  font-family: var(--font-mono, monospace);
}

.xc-btn {
  padding: 5px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  color: var(--muted); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
}
.xc-btn:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.xc-btn:disabled { opacity: .45; cursor: default; }
.xc-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
}
.xc-btn--primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}
.xc-btn--danger {
  background: color-mix(in srgb, #f87171 18%, transparent);
  border-color: color-mix(in srgb, #f87171 45%, transparent);
  color: #f87171;
}
.xc-btn--danger:hover:not(:disabled) {
  background: color-mix(in srgb, #f87171 30%, transparent);
  border-color: #f87171; color: #fff;
}
</style>
