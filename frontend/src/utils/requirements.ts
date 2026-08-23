/**
 * Shared reader for "minimum system requirements".
 *
 * This lived as four near-copies (Games detail and Catalog detail, each in the
 * Modern and the Classic skin) and the copies had drifted apart, so one game
 * described itself differently depending on which skin was on:
 *
 *   - Modern listed OS, Storage and DirectX; Classic stopped at the GPU.
 *   - Only Classic understood requirements delivered as one plain string,
 *     which is exactly the shape RAWG returns for catalog entries.
 *   - Every copy looked for the Windows block under `os`, but the scrapers
 *     write it under `type`, so a per-OS payload produced an empty card.
 *
 * The GOG detail view keeps its own reader on purpose: it draws one card per
 * operating system, so an "OS" row there would only repeat the card heading.
 */

/** Keys worth showing, plus the aliases the scrapers actually emit. */
const REQ_SHOW = new Set([
  'os', 'system',
  'processor', 'cpu',
  'memory', 'ram',
  'graphics', 'gpu', 'video', 'video card',
  'storage', 'disk_space', 'hard drive', 'hard disk',
  'directx',
])

/** Human label for a requirement key. Unknown keys are returned untouched. */
export function formatReqKey(k: string): string {
  const key = (k || '').toLowerCase().trim()
  if (['os', 'system'].includes(key))                                     return 'OS'
  if (['processor', 'cpu'].includes(key))                                 return 'CPU'
  if (['memory', 'ram'].includes(key))                                    return 'RAM'
  if (['graphics', 'gpu', 'video', 'video card'].includes(key))           return 'GPU'
  if (['storage', 'disk_space', 'hard drive', 'hard disk'].includes(key)) return 'Storage'
  if (key === 'directx')                                                  return 'DirectX'
  return k
}

/**
 * Pick the minimum block, preferring Windows. Per-OS payloads come in two
 * shapes: an entry carrying `minimum` directly, or one carrying
 * `requirement_groups` where the wanted group is the one not named
 * "recommended".
 */
function pickMinimum(reqs: any): any {
  const direct =
    reqs.minimum ??
    reqs.Windows?.minimum ??
    reqs.windows?.minimum ?? null
  if (direct) return direct

  const perOs = reqs.per_os as any[] | undefined
  if (Array.isArray(perOs) && perOs.length) {
    const isWin = (o: any) => String(o?.os || o?.type || '').toLowerCase().includes('win')
    const entry = perOs.find(isWin) ?? perOs[0]
    if (entry?.minimum) return entry.minimum
    const group = (entry?.requirement_groups as any[] | undefined)
      ?.find((g: any) => !String(g?.type || '').toLowerCase().includes('rec'))
    if (group?.requirements) return group.requirements
  }

  return (Object.values(reqs)[0] as any)?.minimum ?? null
}

/** Which operating system a name belongs to. Windows when nothing says otherwise. */
export function osTypeOf(name: string | null | undefined): 'win' | 'mac' | 'linux' {
  const n = String(name || '').toLowerCase()
  if (n.includes('mac') || n.includes('osx') || n.includes('os x') || n.includes('apple')) return 'mac'
  if (n.includes('linux') || n.includes('ubuntu') || n.includes('steamos')) return 'linux'
  return 'win'
}

/**
 * The operating system the rows describe, or null when nothing says.
 *
 * Read from the block the rows came out of when it is named, and otherwise
 * from the OS row itself, which is where a flat payload keeps it.
 */
export function reqOs(reqs: any): 'win' | 'mac' | 'linux' | null {
  if (!reqs || typeof reqs !== 'object') return null

  if (!reqs.minimum) {
    if (reqs.Windows?.minimum || reqs.windows?.minimum) return 'win'
    const perOs = reqs.per_os as any[] | undefined
    if (Array.isArray(perOs) && perOs.length) {
      const isWin = (o: any) => String(o?.os || o?.type || '').toLowerCase().includes('win')
      const entry = perOs.find(isWin) ?? perOs[0]
      const named = entry?.os || entry?.type
      if (named) return osTypeOf(named)
    }
  }

  // Flat payload: the OS is one of the rows.
  for (const [k, v] of reqRows(reqs)) {
    if (['os', 'system'].includes(k.toLowerCase())) return osTypeOf(String(v))
  }
  return null
}

/** Rows to render, as [key, value] pairs in the order the source listed them. */
export function reqRows(reqs: any): [string, string][] {
  if (!reqs || typeof reqs !== 'object') return []
  const minimum = pickMinimum(reqs)
  if (!minimum) return []

  if (Array.isArray(minimum)) {
    return minimum
      .filter((r: any) => REQ_SHOW.has(String(r?.name || r?.id || '').toLowerCase()) && (r?.description || r?.value))
      .map((r: any) => [r.name || r.id, r.description || r.value] as [string, string])
  }

  if (typeof minimum === 'string') {
    // One "Key: value" per line. Some sources separate with <br> and wrap the
    // key in markup, so tags are flattened away before the line is read.
    const rows: [string, string][] = []
    for (const line of minimum.replace(/<br\s*\/?>/gi, '\n').split(/\r?\n/)) {
      const plain = line.replace(/<[^>]+>/g, ' ').trim()
      const m = plain.match(/^([^:]+):\s*(.+)/)
      if (m && REQ_SHOW.has(m[1].trim().toLowerCase())) rows.push([m[1].trim(), m[2].trim()])
    }
    return rows
  }

  if (typeof minimum === 'object') {
    return Object.entries(minimum)
      .filter(([k, v]) => REQ_SHOW.has(k.toLowerCase()) && v)
      .map(([k, v]) => [k, String(v)] as [string, string])
  }

  return []
}
