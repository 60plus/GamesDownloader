<template>
  <div class="step-content">
    <div class="step-header">
      <div class="step-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
      <div>
        <h2 class="step-title">{{ t('setup.admin.title') }}</h2>
        <p class="step-subtitle">{{ t('setup.admin.subtitle') }}</p>
      </div>
    </div>

    <form class="wizard-form" @submit.prevent="submit">
      <div class="field-group">
        <label class="field-label">{{ t('setup.admin.label.username') }}</label>
        <input
          v-model="form.username"
          class="field-input"
          type="text"
          :placeholder="t('setup.admin.placeholder.username')"
          autocomplete="username"
          :class="{ 'field-input--error': errors.username }"
        />
        <span v-if="errors.username" class="field-error">{{ errors.username }}</span>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.admin.label.email') }}</label>
        <input
          v-model="form.email"
          class="field-input"
          type="email"
          :placeholder="t('setup.admin.placeholder.email')"
          autocomplete="email"
          required
          :class="{ 'field-input--error': errors.email }"
        />
        <span v-if="errors.email" class="field-error">{{ errors.email }}</span>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.admin.label.password') }}</label>
        <div class="field-input-wrap">
          <input
            v-model="form.password"
            class="field-input"
            :type="showPass ? 'text' : 'password'"
            :placeholder="t('setup.admin.placeholder.password')"
            autocomplete="new-password"
            :class="{ 'field-input--error': errors.password }"
          />
          <button type="button" class="field-eye" @click="showPass = !showPass" tabindex="-1">
            <svg v-if="!showPass" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
          </button>
        </div>
        <span v-if="errors.password" class="field-error">{{ errors.password }}</span>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('setup.admin.label.confirm') }}</label>
        <input
          v-model="form.confirm"
          class="field-input"
          :type="showPass ? 'text' : 'password'"
          :placeholder="t('setup.admin.placeholder.confirm')"
          autocomplete="new-password"
          :class="{ 'field-input--error': errors.confirm }"
        />
        <span v-if="errors.confirm" class="field-error">{{ errors.confirm }}</span>
      </div>

      <div v-if="serverError" class="field-server-error">{{ serverError }}</div>

      <div class="step-actions">
        <button type="submit" class="wizard-btn wizard-btn--primary" :disabled="loading">
          <span v-if="loading" class="spinner" />
          <span v-else>{{ t('setup.admin.button') }}</span>
          <svg v-if="!loading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const emit = defineEmits<{ next: [] }>()

const showPass   = ref(false)
const loading    = ref(false)
const serverError = ref('')

const form = reactive({ username: '', email: '', password: '', confirm: '' })
const errors = reactive({ username: '', email: '', password: '', confirm: '' })

function validate() {
  errors.username = ''
  errors.email    = ''
  errors.password = ''
  errors.confirm  = ''
  let ok = true
  if (!form.username.trim()) { errors.username = t('setup.admin.error.username_required'); ok = false }
  if (!form.email.trim()) { errors.email = t('setup.admin.error.email_required'); ok = false }
  if (form.password.length < 8) { errors.password = t('setup.admin.error.password_min'); ok = false }
  else if (!/[a-zA-Z]/.test(form.password) || !/[0-9]/.test(form.password)) {
    errors.password = t('setup.admin.error.password_strength'); ok = false
  }
  if (form.password !== form.confirm) { errors.confirm = t('setup.admin.error.password_mismatch'); ok = false }
  return ok
}

async function submit() {
  if (!validate()) return
  loading.value = true
  serverError.value = ''
  try {
    await client.post('/setup/admin', {
      username: form.username,
      password: form.password,
      email: form.email,
    })
    emit('next')
  } catch (e: any) {
    serverError.value = e?.response?.data?.detail || t('setup.admin.error.failed')
  } finally {
    loading.value = false
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
.step-subtitle { font-size: 13px; color: var(--muted); margin: 0; }

.wizard-form { display: flex; flex-direction: column; gap: var(--space-4, 16px); }

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }

.field-input-wrap { position: relative; }

.field-input {
  width: 100%; padding: 10px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: var(--fs-md, 14px); font-family: inherit;
  transition: border-color var(--transition), box-shadow var(--transition);
  box-sizing: border-box;
}
.field-input-wrap .field-input { padding-right: 44px; width: 100%; }
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input--error { border-color: #f87171 !important; }
.field-input::placeholder { color: rgba(255,255,255,.25); }

.field-optional {
  font-size: var(--fs-xs, 10px); font-weight: 500; color: rgba(255,255,255,.3);
  text-transform: none; letter-spacing: 0;
}

.field-eye {
  position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--muted); cursor: pointer;
  padding: 0; display: flex; align-items: center;
}
.field-eye:hover { color: var(--text); }

.field-error { font-size: var(--fs-sm, 12px); color: #f87171; }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

.step-actions { padding-top: 8px; }

.spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
