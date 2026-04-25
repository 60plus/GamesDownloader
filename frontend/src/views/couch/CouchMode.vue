<template>
  <div class="cmode-root">

    <!-- ══ FIRST-LAUNCH THEME PICKER ══ -->
    <Transition name="cmode-slide">
      <CouchWelcome
        v-if="!welcomed"
        @done="onWelcomeDone"
      />
    </Transition>

    <!-- ══ MAIN COUCH UI (systems → games) ══ -->
    <template v-if="welcomed">

      <!-- System carousel -->
      <Transition name="cmode-slide">
        <CouchSystemView
          v-if="couchState === 'systems'"
          :platforms="platforms"
          v-model="systemIndex"
          @select="onSystemSelect"
          @menu="openMenu"
        />
      </Transition>

      <!-- Game browser -->
      <Transition name="cmode-slide">
        <CouchGamelist
          v-if="couchState === 'games' && currentPlatform"
          :platform="currentPlatform"
          :view="view"
          @back="onGamelistBack"
          @menu="openMenu"
          @launch="onLaunch"
          @set-view="onSetView"
        />
      </Transition>

    </template>

    <!-- ══ MENU OVERLAY ══ -->
    <CouchMenu
      :visible="menuOpen"
      @close="menuOpen = false"
      @exit="confirmExit"
    />

    <!-- ══ EXIT CONFIRM DIALOG - styled like in-game pause menu ══ -->
    <Transition name="cmode-fade">
      <div v-if="exitDialog" class="cmode-exit-backdrop" @click.self="cancelExit">
        <div class="cmode-exit-panel">
          <div class="cmode-exit-hdr">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            {{ t('couch.exit_title') }}
          </div>
          <div class="cmode-exit-row" :class="{ 'cmode-exit-row--focus': exitFocus === 0 }" @click="cancelExit" @mouseenter="exitFocus = 0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            {{ t('couch.stay') }}
          </div>
          <div class="cmode-exit-row cmode-exit-row--danger" :class="{ 'cmode-exit-row--focus': exitFocus === 1 }" @click="doExit" @mouseenter="exitFocus = 1">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            {{ t('couch.exit') }}
          </div>
          <div class="cmode-exit-hint">
            <kbd>↑↓</kbd> {{ t('couch.exit_hint') }} &nbsp;·&nbsp; <kbd>A</kbd> {{ t('couch.exit_confirm') }} &nbsp;·&nbsp; <kbd>B</kbd> {{ t('couch.exit_cancel') }}
          </div>
        </div>
      </div>
    </Transition>

    <!-- ══ LOADING STATE ══ -->
    <Transition name="cmode-fade">
      <div v-if="loading && welcomed" class="cmode-loading">
        <div class="cmode-loading-spinner" />
        <span>{{ t('couch.loading_platforms') }}</span>
      </div>
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import { useThemeStore } from '@/stores/theme'
import { useCouchTheme, type CouchTheme, type CouchView } from '@/composables/useCouchTheme'
import { useCouchNav, navPaused } from '@/composables/useCouchNav'
import { getEjsCore } from '@/utils/ejsCores'
import client from '@/services/api/client'

import CouchWelcome    from './CouchWelcome.vue'
import CouchSystemView from './CouchSystemView.vue'
import type { CouchPlatform } from './CouchSystemView.vue'
import CouchGamelist   from './CouchGamelist.vue'
import type { CouchRom } from './CouchGamelist.vue'
import CouchMenu       from './CouchMenu.vue'

const router = useRouter()
const { t } = useI18n()
const themeStore = useThemeStore()
const { welcomed, view, setTheme, setView, markWelcomed } = useCouchTheme()

// ── State machine ────────────────────────────────────────────────────────────
type CouchState = 'systems' | 'games'
const couchState  = ref<CouchState>('systems')
const systemIndex = ref(0)
const platforms   = ref<CouchPlatform[]>([])
const loading     = ref(false)
const menuOpen    = ref(false)
const exitDialog  = ref(false)

const currentPlatform = computed(() => platforms.value[systemIndex.value] ?? null)

// ── Welcome ─────────────────────────────────────────────────────────────────
function onWelcomeDone(t: CouchTheme) {
  setTheme(t)
  markWelcomed()
  fetchPlatforms()
}

// ── Platform fetch ───────────────────────────────────────────────────────────
async function fetchPlatforms() {
  loading.value = true
  try {
    // Use the DB platforms endpoint (same as EmulationHome) - has rom_count, slug, cover_path
    const { data } = await client.get('/roms/platforms')
    platforms.value = (data as any[])
      .filter((p: any) => (p.rom_count ?? 0) > 0)
      .sort((a: any, b: any) => (a.name ?? '').localeCompare(b.name ?? ''))
      .map((p: any) => ({
        id:                    p.id,
        slug:                  p.slug,
        fs_slug:               p.fs_slug,
        name:                  p.custom_name || p.name,
        rom_count:             p.rom_count ?? 0,
        cover_path:            p.cover_path        ?? null,
        cover_aspect:          p.cover_aspect      ?? null,
        photo_path:            null,   // lazy-loaded via /roms/platforms/{slug}
        system_color:          null,   // lazy-loaded
        description:           null,
        manufacturer:          null,
        release_year_platform: null,
        generation:            null,
        wheel_path:            null,
      }))
  } catch (e) {
    console.error('[CouchMode] fetch platforms failed', e)
  } finally {
    loading.value = false
  }
}

// ── Navigation ───────────────────────────────────────────────────────────────
function onSystemSelect(_p: CouchPlatform) {
  couchState.value = 'games'
}

let _stateChangedAt = 0
function onGamelistBack() {
  couchState.value = 'systems'
  _stateChangedAt = Date.now()
}

function onSetView(v: CouchView) {
  setView(v)
}

function openMenu() {
  menuOpen.value = true
}

// ── Launch game ──────────────────────────────────────────────────────────────
function onLaunch(rom: CouchRom) {
  const platform = currentPlatform.value
  if (!platform) return
  const core = getEjsCore(platform.fs_slug)
  if (!core) {
    console.warn('[CouchMode] No EJS core for platform:', platform.fs_slug)
    return
  }
  const params: Record<string, string> = {
    rom_id:   String(rom.id),
    rom_name: rom.title || String(rom.id),
    ejs_core: core,
    platform: platform.fs_slug,
  }
  // Bezel: player.html fetches bezel_path from ROM API when bezel=1
  if (localStorage.getItem('gd3_couch_bezel') === 'on') {
    params.bezel = '1'
  }
  const launchMode = localStorage.getItem('gd3_couch_launch') || 'tab'
  const p = new URLSearchParams(params)
  const url = `/player.html?${p.toString()}`
  if (launchMode === 'fullscreen') {
    // Same-tab navigation - preserves browser fullscreen, no popup blocker issues.
    // Player returns to /couch on exit via returnTo param.
    window.location.href = `/player.html?${p.toString()}&returnTo=/couch`
    return  // no navPaused needed - we navigate away
  } else if (launchMode === 'window') {
    window.open(url, 'gd3-player', 'width=1280,height=720,menubar=no,toolbar=no')
  } else {
    window.open(url, '_blank')
  }

  // Pause gamepad/keyboard nav while game window is open.
  // Resume when this window regains focus (user returns from game tab/window).
  navPaused.value = true
  const onFocus = () => {
    if (!menuOpen.value && !exitDialog.value) navPaused.value = false
    window.removeEventListener('focus', onFocus)
  }
  window.addEventListener('focus', onFocus)
}

// ── Esc handling - only active at system level for triple-tap exit ───────────
// CouchGamelist handles its own Esc (back to systems), so CouchMode only
// needs to handle Esc when in 'systems' state (for the triple-tap exit sequence)
// and when overlays are open.
function handleEsc() {
  // Close overlays first
  if (menuOpen.value) {
    menuOpen.value = false
    return
  }
  if (exitDialog.value) {
    cancelExit()
    return
  }
  // In games view: CouchGamelist handles back internally via its own useCouchNav.
  if (couchState.value === 'games') return
  // Cooldown: if state JUST changed from games→systems (same frame), skip
  if (Date.now() - _stateChangedAt < 300) return

  // In systems view - B/Esc shows exit confirmation dialog
  confirmExit()
}

// ── Exit ─────────────────────────────────────────────────────────────────────
function confirmExit() {
  menuOpen.value = false
  exitDialog.value = true
  // Reset gamepad cooldowns so held A from CouchMenu doesn't bleed into exit dialog
  const now = Date.now()
  _exitGpCool['a'] = now
  _exitGpCool['b'] = now
  _exitGpCool['ud'] = now
  _exitGpCool['start'] = now
}
function cancelExit() {
  exitDialog.value = false
}
function doExit() {
  exitDialog.value = false
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
  // Classic layout has no Home page - go to default library instead
  const dest = themeStore.currentLayout === 'classic' ? '/library' : '/'
  window.location.href = dest
}

// ── Exit dialog: gamepad + keyboard navigation ──────────────────────────────
const exitFocus = ref(0)  // 0 = Stay, 1 = Exit
let _exitGpFrame = 0
const _exitGpCool: Record<string, number> = {}

function _couchGpPoll() {
  _exitGpFrame = requestAnimationFrame(_couchGpPoll)
  if (!document.hasFocus()) return
  const gps = navigator.getGamepads?.() ?? []
  const now = Date.now()

  for (const gp of gps) {
    if (!gp) continue

    // Exit dialog navigation
    if (exitDialog.value) {
      const up   = gp.buttons[12]?.pressed || gp.axes[1] < -0.5
      const down = gp.buttons[13]?.pressed || gp.axes[1] >  0.5
      if (up   && (now - (_exitGpCool['ud'] ?? 0)) > 220) { _exitGpCool['ud'] = now; exitFocus.value = 0 }
      if (down && (now - (_exitGpCool['ud'] ?? 0)) > 220) { _exitGpCool['ud'] = now; exitFocus.value = 1 }
      if (gp.buttons[0]?.pressed && (now - (_exitGpCool['a'] ?? 0)) > 300) {
        _exitGpCool['a'] = now
        if (exitFocus.value === 0) cancelExit(); else doExit()
      }
      if (gp.buttons[1]?.pressed && (now - (_exitGpCool['b'] ?? 0)) > 300) {
        _exitGpCool['b'] = now; cancelExit()
      }
      continue
    }

    // Start button (9) = toggle CouchMenu (works even if useCouchNav doesn't reach it)
    if (gp.buttons[9]?.pressed && (now - (_exitGpCool['start'] ?? 0)) > 300) {
      _exitGpCool['start'] = now
      if (!menuOpen.value && !exitDialog.value) openMenu()
      else if (menuOpen.value) menuOpen.value = false
    }
  }
}

function _exitKeyHandler(e: KeyboardEvent) {
  if (!exitDialog.value) return
  if (e.key === 'ArrowUp')    { e.preventDefault(); e.stopImmediatePropagation(); exitFocus.value = 0 }
  if (e.key === 'ArrowDown')  { e.preventDefault(); e.stopImmediatePropagation(); exitFocus.value = 1 }
  if (e.key === 'Enter') {
    e.preventDefault(); e.stopImmediatePropagation()
    if (exitFocus.value === 0) cancelExit(); else doExit()
  }
  if (e.key === 'Escape' || e.key === 'Backspace') {
    e.preventDefault(); e.stopImmediatePropagation(); cancelExit()
  }
}

watch(exitDialog, (v) => { if (v) exitFocus.value = 0 })

// ── Global nav (Esc / Menu key) ──────────────────────────────────────────────
useCouchNav({
  back: handleEsc,
  menu: () => {
    if (!menuOpen.value && !exitDialog.value) openMenu()
    else if (menuOpen.value) menuOpen.value = false
  },
})

// ── Pause navigation when overlays are open ───────────────────────────────────
watch([menuOpen, exitDialog], ([m, e]) => { navPaused.value = m || e })

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  if (welcomed.value) fetchPlatforms()

  // Enter browser fullscreen - works on first entry (user navigated here) and
  // on return from a game (sessionStorage signal set by player.html exitPlayer).
  const resumeFs = sessionStorage.getItem('gd_resumeFs') === '1'
  sessionStorage.removeItem('gd_resumeFs')

  const tryFs = () => document.documentElement.requestFullscreen?.().catch(() => {})
  tryFs()

  // If requestFullscreen fails (gesture chain expired), retry on first user interaction
  if (resumeFs) {
    const onInteract = () => {
      tryFs()
      window.removeEventListener('keydown',   onInteract)
      window.removeEventListener('click',     onInteract)
      window.removeEventListener('gamepadconnected', onInteract)
    }
    // Gamepad button press via polling
    let _retryRaf = 0
    const _retryGp = () => {
      if (document.fullscreenElement) return  // already fullscreen
      const gps = navigator.getGamepads?.() ?? []
      if ([...gps].some(gp => gp && gp.buttons.some(b => b?.pressed))) {
        tryFs()
        return
      }
      _retryRaf = requestAnimationFrame(_retryGp)
    }
    _retryRaf = requestAnimationFrame(_retryGp)
    window.addEventListener('keydown', onInteract, { once: true })
    window.addEventListener('click',   onInteract, { once: true })
  }

  // Exit dialog handlers
  document.addEventListener('keydown', _exitKeyHandler, { capture: true })
  _exitGpFrame = requestAnimationFrame(_couchGpPoll)
})

onUnmounted(() => {
  document.removeEventListener('keydown', _exitKeyHandler, { capture: true })
  cancelAnimationFrame(_exitGpFrame)
})
</script>

<style scoped>
.cmode-root {
  position: fixed; inset: 0; z-index: 90;
  background: #050508; overflow: hidden;
}

/* Slide transitions for view changes */
.cmode-slide-enter-active { transition: opacity .35s ease, transform .35s cubic-bezier(.25,.46,.45,.94); }
.cmode-slide-leave-active { transition: opacity .25s ease, transform .25s cubic-bezier(.25,.46,.45,.94); pointer-events: none; }
.cmode-slide-enter-from { opacity: 0; transform: translateX(40px); }
.cmode-slide-leave-to   { opacity: 0; transform: translateX(-40px); }

/* Fade for overlays */
.cmode-fade-enter-active, .cmode-fade-leave-active { transition: opacity .2s ease; }
.cmode-fade-enter-from, .cmode-fade-leave-to { opacity: 0; }

/* Exit dialog */
/* ── Exit dialog - same visual style as in-game pause menu ── */
.cmode-exit-backdrop {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.78); backdrop-filter: blur(12px) saturate(1.4);
  display: flex; align-items: center; justify-content: center;
}
.cmode-exit-panel {
  width: 380px; max-width: 88vw;
  background: rgba(10,6,24,.97);
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 20px; padding: 28px 24px 20px;
  display: flex; flex-direction: column; gap: var(--space-2, 8px);
  box-shadow: 0 32px 80px rgba(0,0,0,.9);
  animation: cmode-pop .2s cubic-bezier(.34,1.56,.64,1);
}
@keyframes cmode-pop {
  from { transform: scale(.88); opacity: 0; }
  to   { transform: scale(1);   opacity: 1; }
}
.cmode-exit-hdr {
  font-size: 11px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: #f87171; margin-bottom: 8px;
  display: flex; align-items: center; gap: var(--space-2, 8px);
}
.cmode-exit-row {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 13px 16px; border-radius: var(--radius, 12px);
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.07);
  cursor: pointer; transition: all .12s;
  font-size: var(--fs-md, 14px); font-weight: 600; color: rgba(255,255,255,.65);
  user-select: none;
}
.cmode-exit-row svg { flex-shrink: 0; opacity: .5; transition: opacity .12s; }
.cmode-exit-row--focus, .cmode-exit-row:hover {
  background: rgba(167,139,250,.12); border-color: rgba(167,139,250,.35); color: #fff;
}
.cmode-exit-row--focus svg, .cmode-exit-row:hover svg { opacity: 1; }
.cmode-exit-row--danger.cmode-exit-row--focus, .cmode-exit-row--danger:hover {
  background: rgba(220,38,38,.12); border-color: rgba(220,38,38,.35); color: #f87171;
}
.cmode-exit-hint {
  text-align: center; margin-top: 6px;
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.2); letter-spacing: .04em;
}
.cmode-exit-hint kbd {
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-xs, 4px); padding: 1px 5px; font-size: 9px;
  font-family: inherit; color: rgba(255,255,255,.35);
}

/* Loading */
.cmode-loading {
  position: fixed; inset: 0; z-index: 150;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-4, 16px); color: rgba(255,255,255,.4); font-size: 13px;
  background: #050508;
}
.cmode-loading-spinner {
  width: 40px; height: 40px; border-radius: 50%;
  border: 3px solid rgba(255,255,255,.1);
  border-top-color: #7c3aed;
  animation: cmode-spin .8s linear infinite;
}
@keyframes cmode-spin { to { transform: rotate(360deg); } }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .cmode-exit-panel { padding: 20px 16px 16px; border-radius: 14px; }
  .cmode-exit-row { padding: 10px 14px; font-size: 13px; }
}
</style>
