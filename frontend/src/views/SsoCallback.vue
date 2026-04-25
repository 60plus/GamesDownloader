<template>
  <div class="sso-shell">
    <div class="sso-card">
      <div v-if="state === 'loading'" class="sso-state">
        <div class="sso-spinner" />
        <div class="sso-msg">Signing you in…</div>
      </div>

      <div v-else-if="state === 'ok'" class="sso-state">
        <div class="sso-icon sso-icon--ok">✓</div>
        <div class="sso-msg">Signed in - redirecting…</div>
      </div>

      <div v-else class="sso-state">
        <div class="sso-icon sso-icon--err">✕</div>
        <div class="sso-msg">{{ errorMessage }}</div>
        <a href="/login" class="sso-back">Back to login</a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/services/api/client'

const router = useRouter()
const auth   = useAuthStore()

const state        = ref<'loading' | 'ok' | 'error'>('loading')
const errorMessage = ref('')

const ERROR_MESSAGES: Record<string, string> = {
  user_not_found:   'No account found matching your SSO identity. Contact an administrator to have your account created.',
  account_disabled: 'Your account has been disabled. Contact an administrator.',
  provider_denied:  'Access was denied by the identity provider.',
  state_invalid:    'Authentication session expired or invalid. Please try again.',
  token_error:      'Failed to obtain tokens from the identity provider.',
  provider_error:   'Identity provider returned an error. Try again later.',
  not_configured:   'This SSO provider is not configured.',
  missing_params:   'Invalid callback - required parameters are missing.',
  default:          'Sign-in failed. Please try again.',
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  const ssoError = params.get('sso_error')
  const sid      = params.get('sid')

  if (ssoError) {
    state.value        = 'error'
    errorMessage.value = ERROR_MESSAGES[ssoError] || ERROR_MESSAGES.default
    return
  }

  if (!sid) {
    state.value        = 'error'
    errorMessage.value = ERROR_MESSAGES.missing_params
    return
  }

  try {
    const { data } = await client.get(`/auth/sso/session/${sid}`)
    await auth.loginWithTokens(data.access_token, data.refresh_token)
    state.value = 'ok'
    setTimeout(() => router.replace('/'), 600)
  } catch {
    state.value        = 'error'
    errorMessage.value = ERROR_MESSAGES.default
  }
})
</script>

<style scoped>
.sso-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f0f13;
}
.sso-card {
  background: #1a1a24;
  border: 1px solid #2a2a3a;
  border-radius: 16px;
  padding: 48px 56px;
  text-align: center;
  min-width: 320px;
}
.sso-state { display: flex; flex-direction: column; align-items: center; gap: var(--space-4, 16px); }
.sso-spinner {
  width: 40px; height: 40px;
  border: 3px solid #2a2a3a;
  border-top-color: #a78bfa;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.sso-icon {
  width: 48px; height: 48px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: var(--fs-2xl, 22px); font-weight: 700;
}
.sso-icon--ok  { background: rgba(34,197,94,.15); color: #4ade80; }
.sso-icon--err { background: rgba(239,68,68,.15);  color: #f87171; }
.sso-msg  { font-size: var(--fs-md, 14px); color: #c0c0d0; max-width: 300px; line-height: 1.5; }
.sso-back {
  font-size: 13px; color: #a78bfa;
  text-decoration: none; margin-top: 4px;
}
.sso-back:hover { text-decoration: underline; }
</style>
