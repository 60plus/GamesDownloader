<template>
  <!-- Nothing at all for an account offered none of it: a plain user's row
       stays exactly what it was. -->
  <div v-if="visible.length" ref="rootEl" class="mm-wrap">
    <button
      ref="triggerEl"
      type="button"
      class="gd-btn-ghost mm-trigger"
      :class="{ 'mm-trigger--open': open }"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle"
      @keydown="onTriggerKey"
    >
      <!-- A scrape or a conversion goes on after the menu is closed, and the
           spinner that used to turn on its own button has to show somewhere. -->
      <span v-if="anyBusy" class="mm-spinner" aria-hidden="true" />
      <i v-else class="mdi mdi-cog-outline mm-icon" aria-hidden="true" />
      {{ t('manage.button') }}
      <svg class="mm-chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>

    <!-- In <body>, so that no clipped ancestor can cut the list short; its
         place is worked out from the button's (the same as LanguagePicker). -->
    <Teleport to="body">
      <transition name="mm-pop">
        <div
          v-if="open"
          ref="popEl"
          class="mm-pop"
          role="menu"
          :aria-label="t('manage.button')"
          :style="popStyle"
          @keydown="onMenuKey"
        >
          <template v-for="g in groups" :key="g.name">
            <div v-if="g.name === 'danger'" class="mm-sep" role="separator" />
            <div role="group" class="mm-group" :aria-label="groupLabel(g.name)">
              <div v-if="g.name !== 'danger'" class="mm-head" aria-hidden="true">{{ groupLabel(g.name) }}</div>
              <button
                v-for="item in g.items"
                :key="item.key"
                type="button"
                role="menuitem"
                class="mm-item"
                :class="{ 'mm-item--danger': item.danger }"
                :disabled="item.disabled || item.busy"
                :title="item.title"
                @click="choose(item)"
              >
                <span v-if="item.busy" class="mm-spinner" aria-hidden="true" />
                <i v-else class="mdi mm-icon" :class="item.icon" aria-hidden="true" />
                <span class="mm-label">{{ item.label }}</span>
              </button>
            </div>
          </template>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import { useI18n } from '@/i18n'
import { MANAGE_GROUPS, type ManageGroup, type ManageItem } from '@/lib/manageMenu'

const props = defineProps<{ items: ManageItem[] }>()
const { t } = useI18n()

const GROUP_LABEL: Record<Exclude<ManageGroup, 'danger'>, string> = {
  metadata: 'manage.group_metadata',
  files: 'manage.group_files',
  publishing: 'manage.group_publishing',
}

function groupLabel(name: ManageGroup): string | undefined {
  return name === 'danger' ? undefined : t(GROUP_LABEL[name])
}

const visible = computed(() => props.items.filter(i => i.show))
const anyBusy = computed(() => visible.value.some(i => i.busy))
const groups = computed(() => MANAGE_GROUPS
  .map(name => ({ name, items: visible.value.filter(i => i.group === name) }))
  .filter(g => g.items.length))

const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLButtonElement | null>(null)
const popEl = ref<HTMLElement | null>(null)
const popStyle = ref<CSSProperties>({})

async function openMenu(focusAt: number) {
  // Drawn out of sight first: where it goes depends on its own height.
  popStyle.value = { position: 'fixed', top: '0px', left: '0px', visibility: 'hidden' }
  open.value = true
  await nextTick()
  reposition()
  // Out of sight it cannot take focus: wait until it is drawn in its place.
  await nextTick()
  focusItem(focusAt)
}

function close(returnFocus = false) {
  open.value = false
  if (returnFocus) triggerEl.value?.focus()
}

function toggle() {
  if (open.value) close()
  else openMenu(0)
}

function choose(item: ManageItem) {
  // Most items ask a question or open a panel of their own, and the menu must
  // not sit on top of it. The keyboard goes back to the button first: the list
  // lives at the end of the page, and a focus left there is lost.
  open.value = false
  triggerEl.value?.focus()
  item.run()
}

// ── Keyboard ─────────────────────────────────────────────────────────────────

function menuItems(): HTMLButtonElement[] {
  return Array.from(popEl.value?.querySelectorAll<HTMLButtonElement>('.mm-item:not(:disabled)') ?? [])
}

function focusItem(index: number) {
  const list = menuItems()
  if (!list.length) return
  list[((index % list.length) + list.length) % list.length].focus()
}

function onTriggerKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  openMenu(e.key === 'ArrowDown' ? 0 : -1)
}

function onMenuKey(e: KeyboardEvent) {
  const at = menuItems().indexOf(document.activeElement as HTMLButtonElement)
  switch (e.key) {
    case 'ArrowDown': e.preventDefault(); focusItem(at + 1); break
    case 'ArrowUp':   e.preventDefault(); focusItem(at < 0 ? -1 : at - 1); break
    case 'Home':      e.preventDefault(); focusItem(0); break
    case 'End':       e.preventDefault(); focusItem(-1); break
    // Back to the button, whose place in the page is where Tab goes on from.
    case 'Tab':       e.preventDefault(); close(true); break
  }
}

function onDocKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') close(true)
}

// ── Place and closing from outside ───────────────────────────────────────────

// Under the button, or above it when there is more room there; never past the
// edge of the window, and scrolling inside itself when neither side is enough.
function reposition() {
  const trigger = triggerEl.value
  const pop = popEl.value
  if (!trigger || !pop) return
  const r = trigger.getBoundingClientRect()
  const gap = 6
  const edge = 8
  const below = window.innerHeight - r.bottom - gap - edge
  const above = r.top - gap - edge
  const up = pop.scrollHeight > below && above > below
  const left = Math.max(edge, Math.min(r.left, window.innerWidth - pop.offsetWidth - edge))
  popStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    ...(up ? { bottom: `${window.innerHeight - r.top + gap}px` } : { top: `${r.bottom + gap}px` }),
    maxHeight: `${Math.max(160, up ? above : below)}px`,
  }
}

// The list is not inside rootEl (it lives in <body>), so it is checked on its
// own; otherwise a press on an item would close the menu before the click.
function onDocMouseDown(e: MouseEvent) {
  const target = e.target as Node
  if (rootEl.value?.contains(target) || popEl.value?.contains(target)) return
  close()
}

function unlisten() {
  document.removeEventListener('mousedown', onDocMouseDown, true)
  document.removeEventListener('keydown', onDocKeyDown)
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
}

watch(open, (isOpen) => {
  if (!isOpen) { unlisten(); return }
  document.addEventListener('mousedown', onDocMouseDown, true)
  document.addEventListener('keydown', onDocKeyDown)
  window.addEventListener('resize', reposition)
  window.addEventListener('scroll', reposition, true)
})

// The last item going away (the page reloaded under a different role) takes
// the button with it, and an open list must not be left behind in <body>.
watch(() => visible.value.length, (n) => { if (!n) open.value = false })

onBeforeUnmount(unlisten)
</script>

<style scoped>
.mm-wrap { position: relative; display: inline-flex; }

/* The page's secondary buttons, which Neon Horizon restyles through
   .gd-btn-ghost - the trigger carries that class for it. */
.mm-trigger {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.16);
  color: rgba(255,255,255,.68); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.mm-trigger:hover,
.mm-trigger--open { background: rgba(255,255,255,.13); color: #fff; border-color: rgba(255,255,255,.3); }
.mm-trigger:focus-visible { outline: 2px solid var(--pl); outline-offset: 2px; }
.mm-chev { opacity: .65; transition: transform var(--transition, .16s ease); }
.mm-trigger--open .mm-chev { transform: rotate(180deg); }

.mm-icon { font-size: 15px; line-height: 1; width: 16px; text-align: center; flex-shrink: 0; }

/* Nearly opaque: the list opens over artwork and text, and a theme's glass
   (Neon Horizon's is a third opaque) would let both show through the words. */
.mm-pop {
  display: flex; flex-direction: column;
  min-width: 220px; max-width: calc(100vw - 16px);
  padding: 6px;
  overflow-y: auto;
  background: color-mix(in srgb, var(--bg, #0d0b1a) 92%, transparent);
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid color-mix(in srgb, var(--pl) 28%, rgba(255,255,255,.08));
  border-radius: var(--radius-sm, 8px);
  box-shadow: 0 14px 36px rgba(0,0,0,.5);
  z-index: 9000;
}

.mm-group { display: flex; flex-direction: column; }
.mm-head {
  padding: 8px 10px 4px;
  font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted, rgba(255,255,255,.5));
}
.mm-sep { height: 1px; margin: 6px 4px; background: rgba(255,255,255,.1); }

.mm-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 8px 10px;
  border: 0; border-radius: var(--radius-xs, 5px);
  background: transparent;
  color: var(--text, #e8e8f0);
  font-size: 13px; font-weight: 500; font-family: inherit; text-align: left;
  cursor: pointer; transition: background .12s, color .12s;
}
.mm-item:not(:disabled):hover,
.mm-item:focus-visible {
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  color: #fff;
  outline: none;
}
.mm-item:disabled { opacity: .45; cursor: not-allowed; }
.mm-item .mm-icon { opacity: .8; }
.mm-label { flex: 1; white-space: nowrap; }

.mm-item--danger { color: #f87171; }
.mm-item--danger:not(:disabled):hover,
.mm-item--danger:focus-visible { background: rgba(239,68,68,.16); color: #fecaca; }

.mm-spinner {
  width: 14px; height: 14px; flex-shrink: 0;
  border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%;
  animation: mm-spin .8s linear infinite;
}
@keyframes mm-spin { to { transform: rotate(360deg); } }

.mm-pop-enter-active,
.mm-pop-leave-active { transition: opacity .12s, transform .12s; }
.mm-pop-enter-from,
.mm-pop-leave-to { opacity: 0; transform: translateY(-4px); }

@media (prefers-reduced-motion: reduce) {
  .mm-spinner { animation-duration: 2.4s; }
  .mm-pop-enter-active,
  .mm-pop-leave-active { transition: none; }
}
</style>
