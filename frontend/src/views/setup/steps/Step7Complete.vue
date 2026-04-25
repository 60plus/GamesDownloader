<template>
  <div class="step-content">
    <div class="complete-icon">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>

    <h2 class="step-title">{{ t('setup.complete.title') }}</h2>
    <p class="step-desc">{{ t('setup.complete.description') }}</p>

    <div class="summary-grid">
      <div
        v-for="item in summary"
        :key="item.key"
        class="summary-item"
        :class="item.done ? 'summary-item--done' : 'summary-item--skip'"
      >
        <svg v-if="item.done" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>{{ t(item.key) }}</span>
        <span v-if="!item.done" class="skip-hint">{{ t('setup.complete.skip_hint') }}</span>
      </div>
    </div>

    <div v-if="error" class="field-server-error">{{ error }}</div>

    <button class="wizard-btn wizard-btn--primary wizard-btn--wide" :disabled="loading" @click="finish">
      <span v-if="loading" class="spinner" />
      <span v-else>{{ t('setup.complete.button') }}</span>
      <svg v-if="!loading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useSetupStore } from '@/stores/setup'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const router     = useRouter()
const setupStore = useSetupStore()
const loading    = ref(false)
const error      = ref('')

const summary = computed(() => [
  { key: 'setup.complete.summary.admin',    done: setupStore.isDone(2) || setupStore.hasAdmin },
  { key: 'setup.complete.summary.gog',      done: setupStore.isDone(3) },
  { key: 'setup.complete.summary.scrapers', done: setupStore.isDone(4) },
  { key: 'setup.complete.summary.smtp',     done: setupStore.isDone(5) },
  { key: 'setup.complete.summary.settings', done: setupStore.isDone(6) },
])

async function finish() {
  loading.value = true
  error.value = ''
  try {
    await client.post('/setup/complete')
    setupStore.isComplete = true
    localStorage.setItem('gd3_setup_complete', '1')
    router.push({ name: 'login' })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('setup.complete.error')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.step-content {
  display: flex; flex-direction: column; align-items: center;
  text-align: center; gap: var(--space-5, 20px); padding: 8px 0;
}

.complete-icon {
  width: 72px; height: 72px; border-radius: 50%;
  background: var(--pl-dim); border: 2px solid var(--pl);
  display: flex; align-items: center; justify-content: center; color: var(--pl-light);
  box-shadow: 0 0 32px var(--pglow), 0 0 8px var(--pglow2);
}

.step-title { font-size: 26px; font-weight: 700; color: var(--text); margin: 0; }
.step-desc { font-size: 13px; color: var(--muted); line-height: 1.7; max-width: 380px; margin: 0; }

.summary-grid {
  display: flex; flex-direction: column; gap: 6px; width: 100%; max-width: 360px;
}

.summary-item {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: 13px; padding: 9px 14px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); text-align: left;
}
.summary-item--done { color: var(--text); border-color: color-mix(in srgb, var(--pl) 40%, transparent); }
.summary-item--done svg { color: #22c55e; flex-shrink: 0; }
.summary-item--skip { color: var(--muted); }
.summary-item--skip svg { color: rgba(255,255,255,.2); flex-shrink: 0; }
.skip-hint { font-size: 11px; color: rgba(255,255,255,.2); margin-left: auto; white-space: nowrap; }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px; width: 100%; max-width: 360px; text-align: left;
}

.wizard-btn--wide { width: 100%; max-width: 360px; justify-content: center; }

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
