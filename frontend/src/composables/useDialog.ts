/**
 * Global dialog composable - replaces native alert() / confirm() / prompt()
 * with theme-aware UI dialogs.
 *
 * Usage:
 *   const { gdConfirm, gdAlert } = useDialog()
 *   if (!await gdConfirm('Delete this?', { title: 'Confirm delete', danger: true })) return
 *   await gdAlert('File restored successfully.')
 */

import { reactive } from 'vue'

import { useI18n } from '@/i18n'

const { t } = useI18n()

export interface DialogOptions {
  title?:       string
  danger?:      boolean   // red confirm button
  confirmText?: string
  cancelText?:  string
  /** Picture to show instead of the round icon - the cartridge a save belongs
   *  to, say. Falls back to the icon when empty or when the image fails.
   *  Nullable because art off the API is `string | null`, and making every
   *  caller launder that into undefined would be noise. */
  image?:       string | null
  /** Make the confirm button wait for a deliberate tick.
   *
   *  For the handful of actions that take files off the disk or wipe the
   *  scraped work of a whole platform: the button stays disabled, and Enter
   *  does nothing, until the box is ticked. One extra click, on the sentence
   *  that says what goes.
   *
   *  A tick rather than typing a word on purpose. Typing means the word is
   *  either English for everybody or translated per language and then compared
   *  against the translation, and the themes carry eight languages. A tick
   *  needs one label, and it is the core dialog that renders it, so a theme
   *  asking through `__GD__.ui.confirm` gets this for nothing. */
  requireTick?: boolean
  /** A third answer between Cancel and the confirm button. Use `gdChoose`,
   *  which reads it back; on its own a confirm only knows yes and no. The third
   *  button is never guarded by the tick - it is not the destructive answer. */
  altText?:     string
  /** Called when the third button is pressed, before the dialog answers no.
   *  Set by `gdChoose` and not meant to be passed by hand. */
  onAlt?:       (() => void) | null
}

interface DialogState {
  visible:     boolean
  type:        'confirm' | 'alert'
  title:       string
  message:     string
  danger:      boolean
  confirmText: string
  cancelText:  string
  image:       string
  requireTick: boolean
  altText:     string
  onAlt:       (() => void) | null
  resolve:     ((value: boolean) => void) | null
  // Bumped every time a dialog is opened, so the component can tell "the same
  // question is still up" from "a different one took its place". `visible` says
  // neither: it is already true when a second question arrives, so the watcher
  // hanging off it never fires and a tick meant for the first arms the second.
  seq:         number
}

// Singleton - shared across the whole app
export const dialogState = reactive<DialogState>({
  visible:     false,
  type:        'confirm',
  title:       '',
  message:     '',
  danger:      false,
  confirmText: 'OK',
  cancelText:  'Cancel',
  image:       '',
  requireTick: false,
  altText:     '',
  onAlt:       null,
  resolve:     null,
  seq:         0,
})

export function useDialog() {
  /** Settle whatever question is still on screen before a new one replaces it.
   *
   *  The state is a singleton, so opening a second dialog overwrites the first
   *  and its `resolve` with it - the caller waiting on that promise waits for
   *  ever, and its "did they agree" branch simply never runs. Answered `false`,
   *  which is what actually happened: nobody confirmed it. */
  function _displace() {
    const pending = dialogState.resolve
    dialogState.resolve = null
    pending?.(false)
  }

  function gdConfirm(message: string, opts: DialogOptions = {}): Promise<boolean> {
    _displace()
    return new Promise(resolve => {
      dialogState.seq        += 1
      dialogState.visible     = true
      dialogState.type        = 'confirm'
      dialogState.title       = opts.title       ?? t('common.confirm')
      dialogState.message     = message
      dialogState.danger      = opts.danger      ?? false
      dialogState.confirmText = opts.confirmText ?? t('common.confirm')
      dialogState.cancelText  = opts.cancelText  ?? t('common.cancel')
      // Always assigned, never left as it was: the state is a singleton, so a
      // picture from an earlier dialog would otherwise sit above an unrelated
      // question.
      dialogState.image       = opts.image       ?? ''
      // Assigned every time for the same reason as the picture above: left as
      // it was, one guarded question would arm the next, unrelated one.
      dialogState.requireTick = opts.requireTick ?? false
      // And the third button, for the same reason again.
      dialogState.altText     = opts.altText     ?? ''
      dialogState.onAlt       = opts.onAlt       ?? null
      dialogState.resolve     = resolve
    })
  }

  function gdAlert(message: string, opts: DialogOptions = {}): Promise<void> {
    _displace()
    return new Promise(resolve => {
      dialogState.seq        += 1
      dialogState.visible     = true
      dialogState.type        = 'alert'
      dialogState.title       = opts.title       ?? t('common.notice')
      dialogState.message     = message
      dialogState.danger      = opts.danger      ?? false
      dialogState.confirmText = opts.confirmText ?? t('common.ok')
      dialogState.cancelText  = ''
      dialogState.image       = opts.image       ?? ''
      dialogState.requireTick = false   // nothing to guard: an alert only says OK
      dialogState.altText     = ''
      dialogState.onAlt       = null
      dialogState.resolve     = (v) => resolve()
    })
  }

  /** A question with three answers: the confirm button, a second choice, or
   *  Cancel. Built on `gdConfirm` rather than opened on its own, so there stays
   *  exactly one way a question replaces another. The answer is kept per call,
   *  not on the shared state, which the next question would overwrite.
   *
   *    const answer = await gdChoose('...', { confirmText: 'Add', altText: 'New' })
   *    // 'confirm' | 'alt' | 'cancel'
   */
  async function gdChoose(
    message: string, opts: DialogOptions & { altText: string },
  ): Promise<'confirm' | 'alt' | 'cancel'> {
    let alt = false
    const ok = await gdConfirm(message, { ...opts, onAlt: () => { alt = true } })
    if (ok) return 'confirm'
    return alt ? 'alt' : 'cancel'
  }

  return { gdConfirm, gdAlert, gdChoose }
}
