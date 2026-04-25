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

export interface DialogOptions {
  title?:       string
  danger?:      boolean   // red confirm button
  confirmText?: string
  cancelText?:  string
}

interface DialogState {
  visible:     boolean
  type:        'confirm' | 'alert'
  title:       string
  message:     string
  danger:      boolean
  confirmText: string
  cancelText:  string
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
  resolve:     null,
})

export function useDialog() {
  function gdConfirm(message: string, opts: DialogOptions = {}): Promise<boolean> {
    return new Promise(resolve => {
      dialogState.visible     = true
      dialogState.type        = 'confirm'
      dialogState.title       = opts.title       ?? 'Confirm'
      dialogState.message     = message
      dialogState.danger      = opts.danger      ?? false
      dialogState.confirmText = opts.confirmText ?? 'Confirm'
      dialogState.cancelText  = opts.cancelText  ?? 'Cancel'
      dialogState.resolve     = resolve
    })
  }

  function gdAlert(message: string, opts: DialogOptions = {}): Promise<void> {
    return new Promise(resolve => {
      dialogState.visible     = true
      dialogState.type        = 'alert'
      dialogState.title       = opts.title       ?? 'Notice'
      dialogState.message     = message
      dialogState.danger      = opts.danger      ?? false
      dialogState.confirmText = opts.confirmText ?? 'OK'
      dialogState.cancelText  = ''
      dialogState.resolve     = (v) => resolve()
    })
  }

  return { gdConfirm, gdAlert }
}
