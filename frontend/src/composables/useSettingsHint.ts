import { ref } from 'vue'

// Module-level state - shared across all component instances
const hintTitle = ref('')
const hintBody  = ref('')

export function useSettingsHint() {
  function setHint(title: string, body: string) {
    hintTitle.value = title
    hintBody.value  = body
  }

  function clearHint() {
    hintTitle.value = ''
    hintBody.value  = ''
  }

  return { hintTitle, hintBody, setHint, clearHint }
}
