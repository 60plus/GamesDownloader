/**
 * Lightweight i18n composable for GamesDownloader V3.
 *
 * - Auto-detects browser language on first load
 * - Falls back to English for missing keys
 * - Plugins can extend translations via window.__GD__.i18n.merge()
 * - Language choice saved in localStorage
 */

import { ref, readonly } from 'vue'

import en from './en.json'

// Stamped at build time so a new release cannot serve a cached old translation
// file, while an unchanged one stays cached hard between releases.
declare const __I18N_BUILD__: string

/**
 * English is bundled: `t()` falls back to it for any key the active language is
 * missing, so it has to be there before the first render, synchronously.
 *
 * The other seven are fetched. Together they are well over a megabyte of JSON
 * on disk, of which a reader uses one - and every byte of it was in the entry
 * graph, including on the login screen.
 *
 * Fetched, not `import()`ed. That was tried once and reverted: the browser
 * refuses a module import of a file served as application/json, which is
 * exactly how a static .json is served. `fetch` has no such rule.
 */
const bundled: Record<string, Record<string, string>> = { en }
const inFlight: Record<string, Promise<boolean>> = {}

async function ensureLocale(code: string): Promise<boolean> {
  if (bundled[code]) return true
  if (!SUPPORTED.some(s => s.code === code)) return false
  let pending = inFlight[code]
  if (!pending) {
    pending = inFlight[code] = (async () => {
      try {
        const r = await fetch(`/i18n/${code}.json?v=${__I18N_BUILD__}`)
        // The content-type check is not decoration. The backend answers any
        // unknown non-/api path with index.html and a 200, so a wrong filename
        // returns HTML that .json() would throw on - and a throw here would
        // block the mount rather than fall back to English.
        const type = r.headers.get('content-type') || ''
        if (!r.ok || !type.includes('json')) return false
        bundled[code] = await r.json()
        return true
      } catch {
        return false
      } finally {
        delete inFlight[code]
      }
    })()
  }
  return pending
}

// `flag` is an ISO 3166-1 alpha-2 country code (lowercase) used as the
// flag-icons CSS class suffix - templates render <span class="fi fi-XX">.
const SUPPORTED = [
  { code: 'en', name: 'English',  flag: 'gb' },
  { code: 'pl', name: 'Polski',   flag: 'pl' },
  { code: 'de', name: 'Deutsch',  flag: 'de' },
  { code: 'fr', name: 'Français', flag: 'fr' },
  { code: 'es', name: 'Español',  flag: 'es' },
  { code: 'pt', name: 'Português', flag: 'br' },
  { code: 'ru', name: 'Русский',  flag: 'ru' },
  { code: 'it', name: 'Italiano', flag: 'it' },
]

// Detect initial locale
function detectLocale(): string {
  const saved = localStorage.getItem('gd3_locale')
  if (saved && SUPPORTED.some(s => s.code === saved)) return saved
  const browser = (navigator.language || '').slice(0, 2).toLowerCase()
  if (SUPPORTED.some(s => s.code === browser)) return browser
  return 'en'
}

const locale = ref(detectLocale())

// Plugin translations (merged at runtime)
const pluginMessages: Record<string, Record<string, string>> = {}

// No async loading needed - all bundles imported statically above

/**
 * Translate a key. Checks: plugin msgs → locale bundle → English bundle → raw key.
 * Supports parameter interpolation: t('key', { count: 5 }) replaces {count} in the string.
 */
function t(key: string, paramsOrFallback?: Record<string, string | number> | string): string {
  const lang = locale.value
  let result = pluginMessages[lang]?.[key]
    || bundled[lang]?.[key]
    || pluginMessages['en']?.[key]
    || bundled['en']?.[key]

  if (!result) {
    if (typeof paramsOrFallback === 'string') return paramsOrFallback
    return key
  }

  if (paramsOrFallback && typeof paramsOrFallback === 'object') {
    for (const [k, v] of Object.entries(paramsOrFallback)) {
      result = result.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
    }
  }

  return result
}

/**
 * Change locale. Saves to localStorage.
 *
 * Asynchronous because the language may still have to be fetched, and the
 * order matters: the messages have to be in `bundled` before `locale.value`
 * changes, because that ref is what `t()` tracks and `bundled` is a plain
 * object. Assigning first would repaint the whole interface in English and
 * leave it there.
 *
 * A language that will not load is not selected at all - better than a picker
 * showing Italian over an English interface, with the choice remembered.
 */
async function setLocale(code: string): Promise<boolean> {
  if (!(await ensureLocale(code))) return false
  locale.value = code
  localStorage.setItem('gd3_locale', code)
  return true
}

/**
 * Merge plugin translations (called by frontend on plugin i18n load).
 * Format: { "pl": { "nh.favorites": "Ulubione" }, "en": { ... } }
 */
function merge(translations: Record<string, Record<string, string>>) {
  for (const [lang, msgs] of Object.entries(translations)) {
    if (!pluginMessages[lang]) pluginMessages[lang] = {}
    Object.assign(pluginMessages[lang], msgs)
  }
}

export function useI18n() {
  return {
    t,
    locale: readonly(locale),
    setLocale,
    merge,
    SUPPORTED,
  }
}

export { ensureLocale }

// Default export for window.__GD__ exposure
export default { t, locale, setLocale, ensureLocale, merge, SUPPORTED }
