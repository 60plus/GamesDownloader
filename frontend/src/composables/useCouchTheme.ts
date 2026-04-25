/**
 * Couch Mode - shared theme & view state (module-level reactive refs).
 */
import { ref } from 'vue'

export type CouchTheme = 'noir' | 'aura' | 'slick'
export type CouchView  = 'list' | 'grid'

// Module-level refs → shared across all component instances
const theme    = ref<CouchTheme>((localStorage.getItem('gd3_couch_theme') as CouchTheme) || 'noir')
const view     = ref<CouchView>((localStorage.getItem('gd3_couch_view')   as CouchView)  || 'list')
const welcomed = ref(localStorage.getItem('gd3_couch_welcomed') === '1')

export function useCouchTheme() {
  function setTheme(t: CouchTheme) {
    theme.value = t
    localStorage.setItem('gd3_couch_theme', t)
  }
  function setView(v: CouchView) {
    view.value = v
    localStorage.setItem('gd3_couch_view', v)
  }
  function markWelcomed() {
    welcomed.value = true
    localStorage.setItem('gd3_couch_welcomed', '1')
  }
  function resetWelcome() {
    welcomed.value = false
    localStorage.removeItem('gd3_couch_welcomed')
  }
  return { theme, view, welcomed, setTheme, setView, markWelcomed, resetWelcome }
}
