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
  resolve:     ((value: boolean) => void) | null
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
  resolve:     null,
})

export function useDialog() {
  function gdConfirm(message: string, opts: DialogOptions = {}): Promise<boolean> {
    return new Promise(resolve => {
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
      dialogState.resolve     = resolve
    })
  }

  function gdAlert(message: string, opts: DialogOptions = {}): Promise<void> {
    return new Promise(resolve => {
      dialogState.visible     = true
      dialogState.type        = 'alert'
      dialogState.title       = opts.title       ?? t('common.notice')
      dialogState.message     = message
      dialogState.danger      = opts.danger      ?? false
      dialogState.confirmText = opts.confirmText ?? t('common.ok')
      dialogState.cancelText  = ''
      dialogState.image       = opts.image       ?? ''
      dialogState.resolve     = (v) => resolve()
    })
  }

  return { gdConfirm, gdAlert }
}
