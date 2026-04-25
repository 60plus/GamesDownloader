<template>
  <Transition name="cmenu-fade">
    <div v-if="visible" class="cmenu-backdrop" @click.self="$emit('close')">
      <div class="cmenu-panel" :class="`cmenu-theme--${theme}`">

        <!-- Header -->
        <div class="cmenu-header">
          <div class="cmenu-header-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="6" width="20" height="14" rx="3"/>
              <circle cx="8" cy="13" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="16" cy="13" r="1.5" fill="currentColor" stroke="none"/>
              <path d="M6 10h4M8 8v4M14 11h4" stroke-width="2"/>
            </svg>
          </div>
          <span class="cmenu-title">{{ t('couch.menu_title') }}</span>
          <button class="cmenu-close-btn" @click="$emit('close')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="cmenu-body">

          <!-- ── Appearance ── -->
          <div class="cmenu-section">
            <div class="cmenu-section-label">{{ t('couch.appearance') }}</div>

            <!-- Row 0: Theme -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 0 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                {{ t('couch.theme') }}
              </span>
              <div class="cmenu-theme-pills">
                <button
                  v-for="t in themes"
                  :key="t.value"
                  class="cmenu-pill"
                  :class="{ active: theme === t.value, [`cmenu-pill--${t.value}`]: true }"
                  @click="pickTheme(t.value)"
                >{{ t.label }}</button>
              </div>
            </div>

            <!-- Row 1: View mode -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 1 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                {{ t('couch.game_view') }}
              </span>
              <div class="cmenu-toggle">
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: view === 'list' }"
                  @click="pickView('list')"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                  {{ t('couch.list') }}
                </button>
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: view === 'grid' }"
                  @click="pickView('grid')"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                  {{ t('couch.grid') }}
                </button>
              </div>
            </div>
          </div>

          <!-- ── Emulator Options ── -->
          <div class="cmenu-section">
            <div class="cmenu-section-label">{{ t('couch.emulator') }}</div>

            <div class="cmenu-row cmenu-row--info">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              <span>{{ t('couch.emulator_info') }}</span>
            </div>

            <!-- Row 2: Launch mode -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 2 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                {{ t('couch.launch_in') }}
              </span>
              <div class="cmenu-toggle">
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: launchMode === 'tab' }"
                  @click="launchMode = 'tab'; saveLaunchMode()"
                >{{ t('couch.new_tab') }}</button>
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: launchMode === 'window' }"
                  @click="launchMode = 'window'; saveLaunchMode()"
                >{{ t('couch.window') }}</button>
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: launchMode === 'fullscreen' }"
                  @click="launchMode = 'fullscreen'; saveLaunchMode()"
                >{{ t('couch.fullscreen') }}</button>
              </div>
            </div>

            <!-- Row 3: Bezel -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 3 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="18" rx="2"/><rect x="6" y="7" width="12" height="10" rx="1"/></svg>
                {{ t('couch.bezel') }}
              </span>
              <div class="cmenu-toggle">
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: bezelMode === 'off' }"
                  @click="bezelMode = 'off'; saveBezelMode()"
                >{{ t('couch.off') }}</button>
                <button
                  class="cmenu-toggle-btn"
                  :class="{ active: bezelMode === 'on' }"
                  @click="bezelMode = 'on'; saveBezelMode()"
                >{{ t('couch.on') }}</button>
              </div>
            </div>

            <!-- Row 4: Cover Size -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 4 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2"/><path d="M9 2v20M2 9h20"/></svg>
                {{ t('couch.cover_size') }}
              </span>
              <div class="cmenu-theme-pills">
                <button v-for="s in SIZES" :key="s" class="cmenu-pill" :class="{ active: coverSize === s }" @click="coverSize = s; saveCoverSize()">{{ s.toUpperCase() }}</button>
              </div>
            </div>

            <!-- Row 5: Video Volume -->
            <div class="cmenu-row" :class="{ 'cmenu-row--focused': focusRow === 5 }">
              <span class="cmenu-row-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                {{ t('couch.video_volume') }}
              </span>
              <div class="cmenu-toggle">
                <button class="cmenu-toggle-btn" :class="{ active: videoMuted }" @click="videoMuted = true; saveVideoVol()">{{ t('couch.mute') }}</button>
                <button v-for="v in [25, 50, 75, 100]" :key="v" class="cmenu-toggle-btn" :class="{ active: !videoMuted && videoVol === v }" @click="videoMuted = false; videoVol = v; saveVideoVol()">{{ v }}%</button>
              </div>
            </div>
          </div>

          <!-- ── Navigation ── -->
          <div class="cmenu-section">
            <div class="cmenu-section-label">{{ t('couch.navigation') }}</div>

            <div class="cmenu-shortcut-grid">
              <div class="cmenu-shortcut"><kbd>← →</kbd><span>{{ t('couch.navigate') }}</span></div>
              <div class="cmenu-shortcut"><kbd>↑ ↓</kbd><span>{{ t('couch.browse_games') }}</span></div>
              <div class="cmenu-shortcut"><kbd>Enter</kbd><span>{{ t('couch.select_launch') }}</span></div>
              <div class="cmenu-shortcut"><kbd>Esc</kbd><span>{{ t('couch.back') }}</span></div>
              <div class="cmenu-shortcut"><kbd>M</kbd><span>{{ t('couch.this_menu') }}</span></div>
              <div class="cmenu-shortcut"><kbd>X</kbd><span>{{ t('couch.screenshots') }}</span></div>
              <div class="cmenu-shortcut"><kbd>Esc ×3</kbd><span>{{ t('couch.exit_couch') }}</span></div>
            </div>
          </div>

          <!-- ── Gamepad ── -->
          <div class="cmenu-section">
            <div class="cmenu-section-label">{{ t('couch.gamepad') }}</div>
            <div class="cmenu-shortcut-grid">
              <div class="cmenu-shortcut"><kbd>D-Pad</kbd><span>{{ t('couch.navigate_menu') }}</span></div>
              <div class="cmenu-shortcut"><kbd>A</kbd><span>{{ t('couch.confirm') }}</span></div>
              <div class="cmenu-shortcut"><kbd>B</kbd><span>{{ t('couch.back_close') }}</span></div>
              <div class="cmenu-shortcut"><kbd>Start</kbd><span>{{ t('couch.menu') }}</span></div>
              <div class="cmenu-shortcut"><kbd>X</kbd><span>{{ t('couch.screenshots') }}</span></div>
              <div class="cmenu-shortcut"><kbd>Start+Select</kbd><span>{{ t('couch.emulator_menu') }}</span></div>
            </div>
          </div>

        </div>

        <!-- Footer actions -->
        <div class="cmenu-footer">
          <!-- Row 4: Resume -->
          <button
            class="cmenu-btn cmenu-btn--ghost"
            :class="{ 'cmenu-btn--focused': focusRow === 6 }"
            @click="$emit('close')"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            {{ t('couch.resume') }}
          </button>
          <!-- Row 7: Exit -->
          <button
            class="cmenu-btn cmenu-btn--danger"
            :class="{ 'cmenu-btn--focused': focusRow === 7 }"
            @click="$emit('exit')"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            {{ t('couch.exit_couch') }}
          </button>
        </div>

        <!-- Gamepad focus hint -->
        <div class="cmenu-gp-hint">
          <kbd>↑↓</kbd> {{ t('couch.gp_navigate') }} &nbsp;·&nbsp; <kbd>◀▶</kbd> {{ t('couch.gp_change') }} &nbsp;·&nbsp; <kbd>A</kbd> {{ t('couch.gp_confirm') }} &nbsp;·&nbsp; <kbd>B</kbd> / <kbd>Start</kbd> {{ t('couch.gp_close') }}
        </div>

      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '@/i18n'
import { useCouchTheme, type CouchTheme, type CouchView } from '@/composables/useCouchTheme'

const { t } = useI18n()

const props = defineProps<{ visible: boolean }>()
const emit  = defineEmits<{ close: []; exit: [] }>()

const { theme, view, setTheme, setView } = useCouchTheme()

const themes = [
  { value: 'noir'  as CouchTheme, label: 'Noir'  },
  { value: 'aura'  as CouchTheme, label: 'Aura'  },
  { value: 'slick' as CouchTheme, label: 'Slick' },
]

const launchMode = ref<'tab' | 'window' | 'fullscreen'>(
  (localStorage.getItem('gd3_couch_launch') as 'tab' | 'window' | 'fullscreen') || 'tab'
)
const bezelMode = ref<'on' | 'off'>(
  (localStorage.getItem('gd3_couch_bezel') as 'on' | 'off') || 'off'
)

const SIZES = ['xs', 's', 'm', 'l'] as const
const coverSize = ref<string>(localStorage.getItem('gd3_couch_cover_size') || 'm')
const videoMuted = ref(localStorage.getItem('gd3_couch_video_muted') !== '0')
const videoVol = ref(parseInt(localStorage.getItem('gd3_couch_video_vol') || '50', 10))

function pickTheme(t: CouchTheme) { setTheme(t) }
function pickView(v: CouchView)   { setView(v) }
function saveLaunchMode()         { localStorage.setItem('gd3_couch_launch', launchMode.value) }
function saveBezelMode()          { localStorage.setItem('gd3_couch_bezel', bezelMode.value) }
function saveCoverSize() {
  localStorage.setItem('gd3_couch_cover_size', coverSize.value)
  window.dispatchEvent(new CustomEvent('gd-cover-size-change', { detail: coverSize.value }))
}
function saveVideoVol() {
  localStorage.setItem('gd3_couch_video_muted', videoMuted.value ? '1' : '0')
  localStorage.setItem('gd3_couch_video_vol', String(videoVol.value))
  // Notify CouchGamelist to apply volume (same-page custom event)
  window.dispatchEvent(new Event('gd-video-vol-change'))
}

// ── Gamepad row navigation ────────────────────────────────────────────────────
// 8 interactive "rows":  0=Theme  1=View  2=Launch  3=Bezel  4=Size  5=VideoVol  6=Resume  7=Exit
const ROWS  = ['theme', 'view', 'launch', 'bezel', 'size', 'videovol', 'resume', 'exit'] as const
const focusRow = ref(0)

// Reset focus when menu becomes visible
watch(() => props.visible, (v) => { if (v) focusRow.value = 0 })

function menuUp()   { if (focusRow.value > 0) focusRow.value-- }
function menuDown() { if (focusRow.value < ROWS.length - 1) focusRow.value++ }

const LAUNCH_MODES = ['tab', 'window', 'fullscreen'] as const

const VOL_STEPS = [0, 25, 50, 75, 100]

function menuLeft() {
  const row = ROWS[focusRow.value]
  if (row === 'theme') {
    const idx = themes.findIndex(t => t.value === theme.value)
    if (idx > 0) pickTheme(themes[idx - 1].value)
  } else if (row === 'view') {
    pickView('list')
  } else if (row === 'launch') {
    const idx = LAUNCH_MODES.indexOf(launchMode.value)
    if (idx > 0) { launchMode.value = LAUNCH_MODES[idx - 1]; saveLaunchMode() }
  } else if (row === 'bezel') {
    bezelMode.value = 'off'; saveBezelMode()
  } else if (row === 'size') {
    const idx = SIZES.indexOf(coverSize.value as any)
    if (idx > 0) { coverSize.value = SIZES[idx - 1]; saveCoverSize() }
  } else if (row === 'videovol') {
    if (videoMuted.value) { videoMuted.value = false; saveVideoVol() }
    else {
      const cur = VOL_STEPS.indexOf(videoVol.value)
      if (cur > 0) { videoVol.value = VOL_STEPS[cur - 1]; saveVideoVol() }
      else { videoMuted.value = true; saveVideoVol() }
    }
  }
}

function menuRight() {
  const row = ROWS[focusRow.value]
  if (row === 'theme') {
    const idx = themes.findIndex(t => t.value === theme.value)
    if (idx < themes.length - 1) pickTheme(themes[idx + 1].value)
  } else if (row === 'view') {
    pickView('grid')
  } else if (row === 'launch') {
    const idx = LAUNCH_MODES.indexOf(launchMode.value)
    if (idx < LAUNCH_MODES.length - 1) { launchMode.value = LAUNCH_MODES[idx + 1]; saveLaunchMode() }
  } else if (row === 'bezel') {
    bezelMode.value = 'on'; saveBezelMode()
  } else if (row === 'size') {
    const idx = SIZES.indexOf(coverSize.value as any)
    if (idx < SIZES.length - 1) { coverSize.value = SIZES[idx + 1]; saveCoverSize() }
  } else if (row === 'videovol') {
    if (videoMuted.value) { videoMuted.value = false; saveVideoVol() }
    else {
      const cur = VOL_STEPS.indexOf(videoVol.value)
      if (cur < VOL_STEPS.length - 1) { videoVol.value = VOL_STEPS[cur + 1]; saveVideoVol() }
    }
  }
}

function menuConfirm() {
  const row = ROWS[focusRow.value]
  if (row === 'theme') {
    const idx = themes.findIndex(t => t.value === theme.value)
    pickTheme(themes[(idx + 1) % themes.length].value)
  } else if (row === 'view') {
    pickView(view.value === 'list' ? 'grid' : 'list')
  } else if (row === 'launch') {
    const idx = LAUNCH_MODES.indexOf(launchMode.value)
    launchMode.value = LAUNCH_MODES[(idx + 1) % LAUNCH_MODES.length]; saveLaunchMode()
  } else if (row === 'bezel') {
    bezelMode.value = bezelMode.value === 'off' ? 'on' : 'off'; saveBezelMode()
  } else if (row === 'size') {
    const idx = SIZES.indexOf(coverSize.value as any)
    coverSize.value = SIZES[(idx + 1) % SIZES.length]; saveCoverSize()
  } else if (row === 'videovol') {
    videoMuted.value = !videoMuted.value; saveVideoVol()
  } else if (row === 'resume') {
    emit('close')
  } else if (row === 'exit') {
    emit('exit')
  }
}

// ── Own keyboard handler (capture phase so it runs first & can intercept) ────
function onMenuKey(e: KeyboardEvent) {
  if (!props.visible) return
  switch (e.key) {
    case 'ArrowUp':    e.preventDefault(); e.stopImmediatePropagation(); menuUp();      break
    case 'ArrowDown':  e.preventDefault(); e.stopImmediatePropagation(); menuDown();    break
    case 'ArrowLeft':  e.preventDefault(); e.stopImmediatePropagation(); menuLeft();    break
    case 'ArrowRight': e.preventDefault(); e.stopImmediatePropagation(); menuRight();   break
    case 'Enter':      e.stopImmediatePropagation(); menuConfirm();                      break
    case 'Escape':
    case 'Backspace':  e.stopImmediatePropagation(); emit('close');                      break
  }
}

// ── Own RAF gamepad poll (independent of navPaused) ──────────────────────────
let _gpFrame = 0
const _gpCool: Record<string, number> = {}
const GP_MS = 220

function _press(key: string, fn: () => void) {
  const now = Date.now()
  if ((now - (_gpCool[key] ?? 0)) < GP_MS) return
  _gpCool[key] = now
  fn()
}

function _gpPoll() {
  _gpFrame = requestAnimationFrame(_gpPoll)
  if (!document.hasFocus()) return  // don't fire when another window is active
  if (!props.visible) return
  const gps = navigator.getGamepads?.() ?? []
  for (const gp of gps) {
    if (!gp) continue
    const up    = gp.buttons[12]?.pressed || gp.axes[1] < -0.5
    const down  = gp.buttons[13]?.pressed || gp.axes[1] >  0.5
    const left  = gp.buttons[14]?.pressed || gp.axes[0] < -0.5
    const right = gp.buttons[15]?.pressed || gp.axes[0] >  0.5
    if (up)                        _press('up',      menuUp)
    if (down)                      _press('down',    menuDown)
    if (left)                      _press('left',    menuLeft)
    if (right)                     _press('right',   menuRight)
    if (gp.buttons[0]?.pressed)    _press('confirm', menuConfirm)
    if (gp.buttons[1]?.pressed)    _press('back',    () => emit('close'))
  }
}

onMounted(() => {
  document.addEventListener('keydown', onMenuKey, { capture: true })
  _gpFrame = requestAnimationFrame(_gpPoll)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onMenuKey, { capture: true })
  cancelAnimationFrame(_gpFrame)
})
</script>

<style scoped>
.cmenu-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0, 0, 0, .65);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.cmenu-fade-enter-active, .cmenu-fade-leave-active { transition: opacity .2s ease; }
.cmenu-fade-enter-from, .cmenu-fade-leave-to { opacity: 0; }
.cmenu-fade-enter-active .cmenu-panel,
.cmenu-fade-leave-active .cmenu-panel { transition: transform .2s ease; }
.cmenu-fade-enter-from .cmenu-panel { transform: scale(.94) translateY(12px); }
.cmenu-fade-leave-to   .cmenu-panel { transform: scale(.94) translateY(12px); }

/* Panel */
.cmenu-panel {
  width: 480px; max-height: 90vh;
  background: rgba(10, 8, 20, .96);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 20px;
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 32px 80px rgba(0,0,0,.8);
  --cmenu-accent: #7c3aed;
}
.cmenu-theme--noir  { --cmenu-accent: #c9a84c; }
.cmenu-theme--aura  { --cmenu-accent: #7c3aed; }
.cmenu-theme--slick { --cmenu-accent: #cc0000; }

/* Header */
.cmenu-header {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 18px 20px 16px;
  border-bottom: 1px solid rgba(255,255,255,.07);
  flex-shrink: 0;
}
.cmenu-header-icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  display: flex; align-items: center; justify-content: center;
  color: var(--cmenu-accent);
}
.cmenu-title {
  flex: 1; font-size: var(--fs-lg, 16px); font-weight: 700; color: #fff; letter-spacing: -.01em;
}
.cmenu-close-btn {
  width: 30px; height: 30px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.5); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.cmenu-close-btn:hover { background: rgba(255,255,255,.13); color: #fff; }

/* Body */
.cmenu-body {
  flex: 1; overflow-y: auto; padding: 16px 20px;
  display: flex; flex-direction: column; gap: var(--space-5, 20px);
  scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.1) transparent;
}

/* Sections */
.cmenu-section { display: flex; flex-direction: column; gap: 10px; }
.cmenu-section-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; text-transform: uppercase; letter-spacing: .1em;
  color: var(--cmenu-accent); margin-bottom: 2px;
}

/* Rows */
.cmenu-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3, 12px); min-height: 36px;
  border-radius: var(--radius-sm, 8px); padding: 4px 8px; margin: 0 -8px;
  transition: background .12s, outline .12s;
}
.cmenu-row--focused {
  background: rgba(255,255,255,.06);
  outline: 1px solid rgba(255,255,255,.18);
}
.cmenu-row--info {
  font-size: 11px; color: rgba(255,255,255,.4); line-height: 1.5;
  gap: var(--space-2, 8px); align-items: flex-start; justify-content: flex-start;
  background: none !important; outline: none !important;
}
.cmenu-row--info svg { flex-shrink: 0; margin-top: 1px; color: rgba(255,255,255,.3); }
.cmenu-row-label {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; color: rgba(255,255,255,.7); flex-shrink: 0;
}
.cmenu-row-label svg { color: rgba(255,255,255,.35); }

/* Theme pills */
.cmenu-theme-pills { display: flex; gap: 6px; }
.cmenu-pill {
  padding: 5px 14px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.5); cursor: pointer; transition: all .15s;
}
.cmenu-pill:hover { border-color: rgba(255,255,255,.25); color: rgba(255,255,255,.8); }
.cmenu-pill.active { background: rgba(124,58,237,.2); border-color: #7c3aed; color: #a78bfa; }
.cmenu-pill--noir.active  { background: rgba(201,168,76,.2); border-color: #c9a84c; color: #c9a84c; }
.cmenu-pill--aura.active  { background: rgba(124,58,237,.2); border-color: #7c3aed; color: #a78bfa; }
.cmenu-pill--slick.active { background: rgba(204,0,0,.2);    border-color: #cc0000; color: #ff4444; }

/* Toggle */
.cmenu-toggle {
  display: flex; border-radius: var(--radius-sm, 8px); overflow: hidden;
  border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.05);
}
.cmenu-toggle-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 14px; font-size: var(--fs-sm, 12px); font-weight: 600;
  color: rgba(255,255,255,.4); cursor: pointer; background: none; border: none;
  transition: all .15s;
}
.cmenu-toggle-btn:hover { color: rgba(255,255,255,.7); }
.cmenu-toggle-btn.active {
  background: var(--cmenu-accent); color: #fff;
}

/* Shortcuts */
.cmenu-shortcut-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px;
}
.cmenu-shortcut {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.45);
}
.cmenu-shortcut kbd {
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14);
  border-radius: 5px; padding: 2px 7px; font-size: var(--fs-xs, 10px); font-family: inherit;
  white-space: nowrap; color: rgba(255,255,255,.6); flex-shrink: 0;
}

/* Footer */
.cmenu-footer {
  display: flex; gap: 10px; padding: 14px 20px 10px;
  border-top: 1px solid rgba(255,255,255,.07);
  flex-shrink: 0;
}
.cmenu-btn {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 7px;
  padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all .15s; border: none;
}
.cmenu-btn--ghost {
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.6);
}
.cmenu-btn--ghost:hover { background: rgba(255,255,255,.13); color: #fff; }
.cmenu-btn--danger {
  background: rgba(220,38,38,.15); border: 1px solid rgba(220,38,38,.3);
  color: #f87171;
}
.cmenu-btn--danger:hover { background: rgba(220,38,38,.28); color: #fca5a5; }

/* Focused state for footer buttons */
.cmenu-btn--focused {
  outline: 2px solid var(--cmenu-accent);
  outline-offset: 2px;
}

/* Gamepad hint bar */
.cmenu-gp-hint {
  text-align: center; padding: 8px 20px 14px;
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.22); letter-spacing: .04em;
  flex-shrink: 0;
}
.cmenu-gp-hint kbd {
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-xs, 4px); padding: 1px 5px; font-size: 9px; font-family: inherit;
  color: rgba(255,255,255,.4);
}
</style>
