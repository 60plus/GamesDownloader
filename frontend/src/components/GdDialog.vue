<template>
  <Teleport to="body">
    <Transition name="gd-dlg">
      <div v-if="dialogState.visible" class="gd-dlg-backdrop" @mousedown.self="onBackdrop">
        <div class="gd-dlg-box" role="dialog" :aria-modal="true" :aria-labelledby="'gd-dlg-title'">

          <!-- Icon -->
          <div class="gd-dlg-icon" :class="dialogState.danger ? 'gd-dlg-icon--danger' : 'gd-dlg-icon--info'">
            <svg v-if="dialogState.danger" width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2.2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2.2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>

          <!-- Content -->
          <div class="gd-dlg-content">
            <div id="gd-dlg-title" class="gd-dlg-title">{{ dialogState.title }}</div>
            <div class="gd-dlg-message">{{ dialogState.message }}</div>
          </div>

          <!-- Buttons -->
          <div class="gd-dlg-actions">
            <button
              v-if="dialogState.type === 'confirm'"
              class="gd-dlg-btn gd-dlg-btn--ghost"
              @click="cancel"
            >{{ dialogState.cancelText }}</button>
            <button
              class="gd-dlg-btn"
              :class="dialogState.danger ? 'gd-dlg-btn--danger' : 'gd-dlg-btn--primary'"
              @click="confirm"
              ref="confirmBtnRef"
            >{{ dialogState.confirmText }}</button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { dialogState } from '@/composables/useDialog'

const confirmBtnRef = ref<HTMLButtonElement | null>(null)

// Auto-focus confirm button when dialog opens
watch(() => dialogState.visible, async (v) => {
  if (v) {
    await nextTick()
    confirmBtnRef.value?.focus()
  }
})

function confirm() {
  dialogState.visible = false
  dialogState.resolve?.(true)
  dialogState.resolve = null
}

function cancel() {
  dialogState.visible = false
  dialogState.resolve?.(false)
  dialogState.resolve = null
}

function onBackdrop() {
  // Clicking backdrop acts like Cancel
  cancel()
}

// Keyboard: Enter = confirm, Escape = cancel
function onKeydown(e: KeyboardEvent) {
  if (!dialogState.visible) return
  if (e.key === 'Escape') { e.preventDefault(); cancel() }
  if (e.key === 'Enter')  { e.preventDefault(); confirm() }
}

import { onMounted, onUnmounted } from 'vue'
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
/* Backdrop */
.gd-dlg-backdrop {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-5, 20px);
}

/* Box */
.gd-dlg-box {
  width: 100%; max-width: 420px;
  background: var(--glass-bg, #1a1a2e);
  border: 1px solid var(--glass-border, rgba(255,255,255,0.12));
  border-radius: var(--radius, 12px);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255,255,255,0.04);
  overflow: hidden;
  display: flex; flex-direction: column; gap: 0;
}

/* Icon bar */
.gd-dlg-icon {
  display: flex; align-items: center; justify-content: center;
  padding: 22px 24px 0;
}
.gd-dlg-icon > svg {
  width: 40px; height: 40px; padding: 10px;
  border-radius: 50%;
}
.gd-dlg-icon--danger > svg {
  background: rgba(248, 113, 113, 0.12);
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.25);
}
.gd-dlg-icon--info > svg {
  background: rgba(139, 92, 246, 0.12);
  color: var(--pl-light, #a78bfa);
  border: 1px solid rgba(139, 92, 246, 0.25);
}

/* Content */
.gd-dlg-content {
  padding: 16px 24px 20px;
  display: flex; flex-direction: column; gap: var(--space-2, 8px); text-align: center;
}
.gd-dlg-title {
  font-size: 15px; font-weight: 700;
  color: var(--text, #e2e8f0);
}
.gd-dlg-message {
  font-size: 13px; line-height: 1.6;
  color: var(--muted, rgba(255,255,255,0.55));
  white-space: pre-wrap;
}

/* Actions */
.gd-dlg-actions {
  display: flex; gap: var(--space-2, 8px); padding: 0 24px 20px;
  justify-content: flex-end;
}

.gd-dlg-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 20px; border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--glass-border, rgba(255,255,255,0.12));
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all 0.18s ease;
  min-width: 80px; justify-content: center;
}

.gd-dlg-btn--ghost {
  background: rgba(255,255,255,.05);
  color: var(--muted, rgba(255,255,255,0.55));
}
.gd-dlg-btn--ghost:hover {
  background: rgba(255,255,255,.1);
  color: var(--text, #e2e8f0);
}

.gd-dlg-btn--primary {
  background: var(--pl, #7c3aed);
  border-color: var(--pl, #7c3aed);
  color: #fff;
  box-shadow: 0 2px 12px var(--pglow2, rgba(124,58,237,0.35));
}
.gd-dlg-btn--primary:hover {
  background: var(--pl-light, #a78bfa);
  border-color: var(--pl-light, #a78bfa);
}

.gd-dlg-btn--danger {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.4);
  color: #f87171;
}
.gd-dlg-btn--danger:hover {
  background: rgba(248, 113, 113, 0.28);
  border-color: #f87171;
  color: #fff;
}

.gd-dlg-btn:focus-visible {
  outline: 2px solid var(--pl, #7c3aed);
  outline-offset: 2px;
}

/* Transition */
.gd-dlg-enter-active,
.gd-dlg-leave-active {
  transition: opacity 0.18s ease;
}
.gd-dlg-enter-active .gd-dlg-box,
.gd-dlg-leave-active .gd-dlg-box {
  transition: transform 0.18s ease, opacity 0.18s ease;
}
.gd-dlg-enter-from,
.gd-dlg-leave-to {
  opacity: 0;
}
.gd-dlg-enter-from .gd-dlg-box {
  transform: scale(0.93) translateY(-8px);
  opacity: 0;
}
.gd-dlg-leave-to .gd-dlg-box {
  transform: scale(0.96) translateY(4px);
  opacity: 0;
}
</style>
