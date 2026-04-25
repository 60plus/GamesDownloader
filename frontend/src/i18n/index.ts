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
import pl from './pl.json'
import de from './de.json'
import fr from './fr.json'
import es from './es.json'
import pt from './pt.json'
import ru from './ru.json'
import it from './it.json'

// All translations loaded statically (dynamic import breaks MIME type in production)
const bundled: Record<string, Record<string, string>> = { en, pl, de, fr, es, pt, ru, it }

const SUPPORTED = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'pl', name: 'Polski', flag: '🇵🇱' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'pt', name: 'Português', flag: '🇧🇷' },
  { code: 'ru', name: 'Русский', flag: '🇷🇺' },
  { code: 'it', name: 'Italiano', flag: '🇮🇹' },
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
 */
function setLocale(code: string) {
  locale.value = code
  localStorage.setItem('gd3_locale', code)
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

// Default export for window.__GD__ exposure
export default { t, locale, setLocale, merge, SUPPORTED }
