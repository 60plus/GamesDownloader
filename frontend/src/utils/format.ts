/**
 * Shared size and date formatting.
 *
 * Both jobs had grown a copy per view: nineteen byte formatters and fifteen
 * date ones. They had drifted in every direction a small function can. Sizes
 * disagreed on where to stop (GB, TB or PB), on how many decimals to show, and
 * on what a missing value looks like. Dates disagreed on the locale: two of
 * them read a localStorage key nothing has ever written, so those two views
 * printed US dates no matter which language was picked.
 *
 * The empty case stays a decision the caller makes, because it genuinely
 * differs: a total wants "0 B", a table cell wants a dash, a badge wants
 * nothing at all. Everything else is settled here.
 */

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

/** The locale the language picker writes, falling back to the browser's own. */
export function uiLocale(): string {
  return localStorage.getItem('gd3_locale') || navigator.language || 'en'
}

/**
 * Human size. Whole bytes, one decimal for KB and MB, two from GB up, where
 * the difference between 1.2 and 1.25 is a good half gigabyte.
 */
export function formatBytes(bytes: number | null | undefined, empty = '0 B'): string {
  if (!bytes || bytes < 0 || !isFinite(bytes)) return empty
  const i = Math.min(UNITS.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / Math.pow(1024, i)
  const decimals = i === 0 ? 0 : i >= 3 ? 2 : 1
  return `${value.toFixed(decimals)} ${UNITS[i]}`
}

/**
 * Long date, as in 3 March 2024.
 *
 * Release dates arrive from the scrapers in whatever shape the source had, so
 * anything that will not parse is handed back as it came rather than shown as
 * "Invalid Date" - trimmed to the leading date part when it is longer.
 */
export function formatDate(raw: string | null | undefined, empty = ''): string {
  if (!raw) return empty
  const d = new Date(raw)
  if (isNaN(d.getTime())) return raw.length <= 10 ? raw : raw.slice(0, 10)
  return d.toLocaleDateString(uiLocale(), { year: 'numeric', month: 'long', day: 'numeric' })
}

/** Short date, as in 3 Mar 2024. For tables and lists, where space is tight. */
export function formatDateShort(raw: string | null | undefined, empty = ''): string {
  if (!raw) return empty
  const d = new Date(raw)
  if (isNaN(d.getTime())) return empty
  return d.toLocaleDateString(uiLocale(), { year: 'numeric', month: 'short', day: 'numeric' })
}

/** Date and time, in whatever order and separator the locale prefers. */
export function formatDateTime(raw: string | null | undefined, empty = ''): string {
  if (!raw) return empty
  const d = new Date(raw)
  if (isNaN(d.getTime())) return empty
  return d.toLocaleString(uiLocale(), { dateStyle: 'short', timeStyle: 'short' })
}
