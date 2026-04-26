<template>
  <!--
    Custom language dropdown. We render our own button + popover instead
    of a native <select> because <option> cannot embed HTML and the
    flag-icons sprite is what gives every OS a consistent flag glyph.
    See utils/langMap.ts for the country-code mapping.
  -->
  <div ref="rootEl" class="lp-wrap">
    <button
      type="button"
      class="lp-trigger"
      :class="{ 'lp-trigger--open': open }"
      :aria-expanded="open"
      :aria-haspopup="true"
      @click.stop="open = !open"
    >
      <span v-if="active" class="fi" :class="`fi-${active.flag}`"></span>
      <span class="lp-trigger-name">{{ active?.name ?? locale }}</span>
      <svg
        class="lp-trigger-chev"
        width="12" height="12" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2.5"
      >
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>

    <!--
      Teleport the popover to <body> so an `overflow: hidden` ancestor
      (e.g. .pv-section's clipping for rounded corners) cannot truncate
      it. The position is computed from the trigger's bounding rect at
      open time and updated on resize / scroll.
    -->
    <Teleport to="body">
      <transition name="lp-pop">
        <ul
          v-if="open"
          ref="popEl"
          class="lp-pop"
          role="listbox"
          :style="popStyle"
        >
          <li
            v-for="lang in SUPPORTED"
            :key="lang.code"
            class="lp-item"
            :class="{ 'lp-item--active': lang.code === locale }"
            role="option"
            :aria-selected="lang.code === locale"
            @click="select(lang.code)"
          >
            <span class="fi" :class="`fi-${lang.flag}`"></span>
            <span class="lp-item-name">{{ lang.name }}</span>
            <svg
              v-if="lang.code === locale"
              class="lp-item-check"
              width="14" height="14" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2.5"
            >
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </li>
        </ul>
      </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import { useI18n } from '@/i18n'

const { locale, setLocale, SUPPORTED } = useI18n()
const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const popEl  = ref<HTMLElement | null>(null)
const popStyle = ref<CSSProperties>({})

const active = computed(() => SUPPORTED.find(l => l.code === locale.value))

function select(code: string) {
  setLocale(code)
  open.value = false
}

// Compute the teleported popover's viewport position from the trigger's
// bounding rect. Called on open and on resize / scroll so the popover
// follows the trigger if the layout shifts while it is open.
function reposition() {
  if (!rootEl.value) return
  const r = rootEl.value.getBoundingClientRect()
  popStyle.value = {
    position: 'fixed',
    top:   `${r.bottom + 6}px`,
    left:  `${r.left}px`,
    minWidth: `${r.width}px`,
  }
}

// Close when the user clicks anywhere outside the picker. The popover is
// teleported to <body> so it is NOT a descendant of rootEl - we have to
// check it separately, otherwise the capture-phase listener fires before
// the item's @click handler and removes the listbox before the click lands.
function onDocMouseDown(e: MouseEvent) {
  const target = e.target as Node
  const insideRoot = rootEl.value?.contains(target)
  const insidePop  = popEl.value?.contains(target)
  if (!insideRoot && !insidePop) open.value = false
}
watch(open, (isOpen) => {
  if (isOpen) {
    reposition()
    document.addEventListener('mousedown', onDocMouseDown, true)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
  } else {
    document.removeEventListener('mousedown', onDocMouseDown, true)
    window.removeEventListener('resize', reposition)
    window.removeEventListener('scroll', reposition, true)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMouseDown, true)
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
})
</script>

<style scoped>
.lp-wrap {
  position: relative;
  display: inline-block;
}

/* ── Trigger button ──────────────────────────────────────────────────────── */
.lp-trigger {
  display: inline-flex; align-items: center; gap: 10px;
  min-width: 180px;
  padding: 8px 12px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px);
  color: var(--text);
  font-family: inherit;
  font-size: var(--fs-md, 14px);
  cursor: pointer;
  transition: all var(--transition);
}
.lp-trigger:hover,
.lp-trigger--open {
  border-color: color-mix(in srgb, var(--pl) 50%, var(--glass-border));
}
.lp-trigger .fi {
  width: 1.4em; height: 1em;
  border-radius: 2px;
  flex-shrink: 0;
}
.lp-trigger-name {
  flex: 1;
  text-align: left;
}
.lp-trigger-chev {
  opacity: .65;
  transition: transform var(--transition);
}
.lp-trigger--open .lp-trigger-chev { transform: rotate(180deg); }

/* ── Popover ─────────────────────────────────────────────────────────────── */
/* Position is set inline via :style so the popover can teleport into <body>
   and still align with the trigger's viewport rect (escapes overflow:hidden
   ancestors like .pv-section's rounded-corner clip). */
.lp-pop {
  margin: 0; padding: 4px;
  list-style: none;
  background: var(--glass-bg, rgba(20, 18, 35, .92));
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border, rgba(255, 255, 255, .08));
  border-radius: var(--radius-sm, 8px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .35);
  z-index: 9000;
}
.lp-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-xs, 5px);
  color: var(--text);
  font-size: var(--fs-md, 14px);
  cursor: pointer;
  transition: background var(--transition);
}
.lp-item .fi {
  width: 1.4em; height: 1em;
  border-radius: 2px;
  flex-shrink: 0;
}
.lp-item:hover {
  background: color-mix(in srgb, var(--pl) 14%, transparent);
}
.lp-item--active {
  color: var(--pl);
}
.lp-item-name { flex: 1; }
.lp-item-check { color: var(--pl); flex-shrink: 0; }

.lp-pop-enter-active,
.lp-pop-leave-active { transition: opacity .12s, transform .12s; }
.lp-pop-enter-from,
.lp-pop-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
