/**
 * Coerce a rating into a finite number before any .toFixed()/Math.round().
 *
 * Ratings can reach the UI as numeric strings (DB JSON columns, plugin
 * metadata payloads). Calling "8.5".toFixed(1) throws "is not a function"
 * and, inside a Vue render, takes down the whole component subtree. Run every
 * rating value through this first.
 */
export function ratingVal(v: unknown): number {
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return Number.isFinite(n) ? n : 0
}
