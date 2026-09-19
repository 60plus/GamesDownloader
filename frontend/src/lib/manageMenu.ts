/**
 * The one "Manage" menu on a game's page and a ROM's page (Modern, and Neon
 * Horizon through it). The owner, 2026-09-18: the row keeps what every account
 * sees - Download, Torrent, Play, Manual - and what only an administrator, an
 * uploader or an editor may do goes under one button, in groups, with Delete on
 * its own at the foot.
 *
 * A page describes its items; ManageMenu.vue draws them.
 */

export type ManageGroup = 'metadata' | 'files' | 'publishing' | 'danger'

/** The order the groups are drawn in. `danger` has no heading, only a line. */
export const MANAGE_GROUPS: readonly ManageGroup[] = ['metadata', 'files', 'publishing', 'danger']

export interface ManageItem {
  key: string
  group: ManageGroup
  /** Whether this account is offered the item at all. The same check the
   *  button it replaced had: the menu hands nobody anything new. */
  show: boolean
  label: string
  /** A Material Design Icons class, e.g. `mdi-pencil-outline`. */
  icon: string
  run: () => unknown
  disabled?: boolean
  /** Running now: the item waits, and the Manage button shows a spinner. */
  busy?: boolean
  title?: string
  /** Drawn in red: it takes something away. */
  danger?: boolean
}
