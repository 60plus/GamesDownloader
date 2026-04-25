<template>
  <div class="step-content">
    <div class="step-header">
      <div class="step-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07M8.46 8.46a5 5 0 0 0 0 7.07"/>
        </svg>
      </div>
      <div>
        <h2 class="step-title">{{ t('setup.app.title') }}</h2>
        <p class="step-subtitle">{{ t('setup.app.subtitle') }}</p>
      </div>
    </div>

    <form class="wizard-form" @submit.prevent>
      <div class="field-group">
        <label class="field-label">{{ t('setup.app.label.registration') }}</label>
        <div class="toggle-card">
          <div class="toggle-info">
            <span class="toggle-name">{{ t('setup.app.toggle.name') }}</span>
            <span class="toggle-desc">{{ t('setup.app.toggle.desc') }}</span>
          </div>
          <div class="toggle-wrap" @click="form.enable_registrations = !form.enable_registrations">
            <div class="toggle-track" :class="{ 'toggle-track--on': form.enable_registrations }">
              <div class="toggle-thumb" />
            </div>
          </div>
        </div>
      </div>

      <div v-if="serverError" class="field-server-error">{{ serverError }}</div>
    </form>

    <div class="step-actions">
      <button
        class="wizard-btn wizard-btn--primary"
        :disabled="saving"
        @click="save"
      >
        <span v-if="saving" class="spinner" />
        <span v-else>{{ t('setup.app.button.save') }}</span>
        <svg v-if="!saving" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const emit = defineEmits<{ next: [] }>()

const saving = ref(false)
const serverError = ref('')

const form = reactive({
  enable_registrations: false,
})

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    await client.post('/setup/app-settings', form)
    emit('next')
  } catch (e: any) {
    serverError.value = e?.response?.data?.detail || t('setup.app.error.save_failed')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.step-content { display: flex; flex-direction: column; gap: var(--space-6, 24px); }

.step-header { display: flex; align-items: flex-start; gap: var(--space-4, 16px); }

.step-icon {
  width: 42px; height: 42px; border-radius: 10px;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light); flex-shrink: 0;
}

.step-title { font-size: 20px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.step-subtitle { font-size: 13px; color: var(--muted); margin: 0; line-height: 1.6; }

.wizard-form { display: flex; flex-direction: column; gap: 18px; }

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }

.field-input {
  width: 100%; padding: 10px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: var(--fs-md, 14px); font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input::placeholder { color: rgba(255,255,255,.25); }

.field-hint { font-size: var(--fs-sm, 12px); color: var(--muted); }

.toggle-card {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 14px 16px; gap: var(--space-4, 16px);
}

.toggle-info { display: flex; flex-direction: column; gap: 3px; }
.toggle-name { font-size: 13px; font-weight: 600; color: var(--text); }
.toggle-desc { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }

.toggle-wrap { cursor: pointer; flex-shrink: 0; }
.toggle-track {
  width: 36px; height: 20px; border-radius: 10px;
  background: rgba(255,255,255,.12); border: 1px solid var(--glass-border);
  transition: background var(--transition); position: relative;
}
.toggle-track--on { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); }
.toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px; border-radius: 50%; background: #fff;
  transition: transform var(--transition);
}
.toggle-track--on .toggle-thumb { transform: translateX(16px); }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

.step-actions { padding-top: 4px; }

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
