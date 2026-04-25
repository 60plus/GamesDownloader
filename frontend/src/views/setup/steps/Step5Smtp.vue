<template>
  <div class="step-content">
    <div class="step-header">
      <div class="step-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
          <polyline points="22,6 12,13 2,6"/>
        </svg>
      </div>
      <div>
        <h2 class="step-title">{{ t('setup.smtp.title') }}</h2>
        <p class="step-subtitle">{{ t('setup.smtp.subtitle') }}</p>
      </div>
    </div>

    <form class="wizard-form" @submit.prevent>
      <div class="field-row">
        <div class="field-group field-group--grow">
          <label class="field-label">{{ t('setup.smtp.label.host') }}</label>
          <input v-model="form.host" class="field-input" :placeholder="t('setup.smtp.placeholder.host')" />
        </div>
        <div class="field-group field-group--port">
          <label class="field-label">{{ t('setup.smtp.label.port') }}</label>
          <input v-model="form.port" class="field-input" type="number" :placeholder="t('setup.smtp.placeholder.port')" />
        </div>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.smtp.label.username') }}</label>
        <input v-model="form.username" class="field-input" :placeholder="t('setup.smtp.placeholder.username')" autocomplete="email" />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.smtp.label.password') }}</label>
        <input v-model="form.password" class="field-input" type="password" :placeholder="t('setup.smtp.placeholder.password')" autocomplete="current-password" />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.smtp.label.from') }}</label>
        <input v-model="form.from_address" class="field-input" :placeholder="t('setup.smtp.placeholder.from')" />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.smtp.label.test_to') }}</label>
        <input v-model="form.test_to" class="field-input" :placeholder="t('setup.smtp.placeholder.test_to')" />
      </div>

      <div class="field-toggle-row">
        <label class="toggle-label">
          <span>{{ t('setup.smtp.label.use_tls') }}</span>
          <div class="toggle-wrap">
            <input type="checkbox" v-model="form.use_tls" class="toggle-input" />
            <div class="toggle-track" :class="{ 'toggle-track--on': form.use_tls }">
              <div class="toggle-thumb" />
            </div>
          </div>
        </label>
      </div>

      <!-- Test result -->
      <div v-if="testResult" class="test-result" :class="testResult.ok ? 'test-result--ok' : 'test-result--err'">
        <svg v-if="testResult.ok" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        {{ testResult.message }}
      </div>

      <div v-if="serverError" class="field-server-error">{{ serverError }}</div>
    </form>

    <div class="step-actions">
      <button class="wizard-btn wizard-btn--ghost" @click="emit('skip')">
        {{ t('setup.smtp.button.skip') }}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <button v-if="form.host" class="wizard-btn wizard-btn--secondary" :disabled="testing" @click="testSmtp">
        <span v-if="testing" class="spinner" />
        <span v-else>{{ t('setup.smtp.button.test') }}</span>
      </button>
      <button
        v-if="form.host"
        class="wizard-btn wizard-btn--primary"
        :disabled="saving"
        @click="save"
      >
        <span v-if="saving" class="spinner" />
        <span v-else>{{ t('setup.smtp.button.save') }}</span>
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
const emit = defineEmits<{ next: []; skip: [] }>()

const saving = ref(false)
const testing = ref(false)
const serverError = ref('')
const testResult = ref<{ ok: boolean; message: string } | null>(null)

const form = reactive({
  host: '', port: 587, username: '', password: '', from_address: '', use_tls: true, enabled: true, test_to: '',
})

async function testSmtp() {
  testing.value = true
  testResult.value = null
  try {
    await client.post('/setup/smtp/test', form)
    testResult.value = { ok: true, message: t('setup.smtp.result.success') }
  } catch (e: any) {
    testResult.value = { ok: false, message: e?.response?.data?.detail || t('setup.smtp.error.test_failed') }
  } finally {
    testing.value = false
  }
}

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    await client.post('/setup/smtp', form)
    emit('next')
  } catch (e: any) {
    serverError.value = e?.response?.data?.detail || t('setup.smtp.error.save_failed')
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

.wizard-form { display: flex; flex-direction: column; gap: 14px; }

.field-row { display: flex; gap: 10px; }
.field-group--grow { flex: 1; }
.field-group--port { width: 90px; }
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

.field-toggle-row { padding: 4px 0; }
.toggle-label {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; color: var(--text); cursor: pointer;
}
.toggle-wrap { position: relative; }
.toggle-input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle-track {
  width: 36px; height: 20px; border-radius: 10px;
  background: rgba(255,255,255,.12); border: 1px solid var(--glass-border);
  transition: background var(--transition); position: relative; cursor: pointer;
}
.toggle-track--on { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); }
.toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px; border-radius: 50%; background: #fff;
  transition: transform var(--transition);
}
.toggle-track--on .toggle-thumb { transform: translateX(16px); }

.test-result {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px;
}
.test-result--ok { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25); color: #86efac; }
.test-result--err { background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3); color: #f87171; }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

.step-actions { display: flex; gap: 10px; flex-wrap: wrap; padding-top: 4px; }

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
