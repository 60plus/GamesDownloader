/**
 * Couch Mode - keyboard + gamepad navigation composable.
 * Handles arrow keys, Enter, Escape, M (menu), plus standard gamepad buttons.
 *
 * navPaused: when true, movement + confirm are suppressed.
 * back/menu always fire so overlays can still be closed.
 */
import { ref, watch, onMounted, onUnmounted } from 'vue'

/** Set to true (e.g. when a menu/dialog overlay is open) to pause movement. */
export const navPaused = ref(false)

/** Cooldown timestamp - inputs ignored until Date.now() > this value.
 *  Set automatically when navPaused transitions from true → false so that
 *  a held button (e.g. A to confirm "Resume") doesn't bleed into the view underneath. */
let _unpausedAt = 0
const UNPAUSE_COOLDOWN = 300  // ms

export interface CouchNavHandlers {
  up?:      () => void
  down?:    () => void
  left?:    () => void
  right?:   () => void
  confirm?: () => void
  back?:    () => void
  menu?:    () => void
  x?:       () => void   // Gamepad X button (button 2) - secondary action
}

// When overlay closes (navPaused: true → false), set cooldown so held buttons don't bleed through
watch(navPaused, (now, prev) => {
  if (prev && !now) _unpausedAt = Date.now()
})

export function useCouchNav(handlers: CouchNavHandlers) {
  function onKeyDown(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    const blocked = navPaused.value || Date.now() < (_unpausedAt + UNPAUSE_COOLDOWN)
    switch (e.key) {
      case 'ArrowUp':    if (!blocked) { e.preventDefault(); handlers.up?.() }    break
      case 'ArrowDown':  if (!blocked) { e.preventDefault(); handlers.down?.() }  break
      case 'ArrowLeft':  if (!blocked) { e.preventDefault(); handlers.left?.() }  break
      case 'ArrowRight': if (!blocked) { e.preventDefault(); handlers.right?.() } break
      case 'Enter':      if (!blocked) handlers.confirm?.();                       break
      case 'Escape':
      case 'Backspace':                      handlers.back?.();                   break
      case 'm':
      case 'M':                              handlers.menu?.();                   break
      case 'x':
      case 'X':          if (!blocked) handlers.x?.();                            break
    }
  }

  // Gamepad polling with per-button cooldown to avoid repeated triggers
  let gpFrame = 0
  const gpCooldown: Record<string, number> = {}
  const GP_MS = 200  // ms between repeated presses while held

  function pressGp(key: string, fn: (() => void) | undefined) {
    if (!fn) return
    const now = Date.now()
    if ((now - (gpCooldown[key] ?? 0)) < GP_MS) return
    gpCooldown[key] = now
    fn()
  }

  function pollGamepad() {
    gpFrame = requestAnimationFrame(pollGamepad)   // always schedule next frame
    if (!document.hasFocus()) return               // don't fire when another window is active
    const gps = navigator.getGamepads?.() ?? []
    for (const gp of gps) {
      if (!gp) continue
      // Standard gamepad mapping
      // D-pad: 12=up 13=down 14=left 15=right
      // A=0  B=1  Start=9
      const paused = navPaused.value
      const coolingDown = Date.now() < (_unpausedAt + UNPAUSE_COOLDOWN)

      if (!paused && !coolingDown) {
        const up    = gp.buttons[12]?.pressed || gp.axes[1] < -0.5
        const down  = gp.buttons[13]?.pressed || gp.axes[1] >  0.5
        const left  = gp.buttons[14]?.pressed || gp.axes[0] < -0.5
        const right = gp.buttons[15]?.pressed || gp.axes[0] >  0.5
        if (up)                        pressGp('up',      handlers.up)
        if (down)                      pressGp('down',    handlers.down)
        if (left)                      pressGp('left',    handlers.left)
        if (right)                     pressGp('right',   handlers.right)
        if (gp.buttons[0]?.pressed)    pressGp('confirm', handlers.confirm)
        if (gp.buttons[2]?.pressed)    pressGp('x',       handlers.x)
      }
      // menu always fires (needed for overlay open/close from anywhere)
      // back respects both pause AND cooldown - overlays handle their own B directly
      if (!paused && !coolingDown && gp.buttons[1]?.pressed) pressGp('back', handlers.back)
      if (gp.buttons[9]?.pressed) pressGp('menu', handlers.menu)
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', onKeyDown)
    gpFrame = requestAnimationFrame(pollGamepad)
    // Wake up gamepad API
    window.dispatchEvent(new Event('gamepadconnected'))
  })
  onUnmounted(() => {
    document.removeEventListener('keydown', onKeyDown)
    cancelAnimationFrame(gpFrame)
  })
}
