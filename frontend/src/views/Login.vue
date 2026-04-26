<template>
  <div class="login-shell">
    <AmbientBackground />

    <div class="login-card">
      <!-- Brand -->
      <div class="login-brand">
        <div class="logo-glow-wrap">
          <img src="/GDLOGO.png" class="brand-logo" alt="GamesDownloader" />
        </div>
        <div class="brand-name">GamesDownloader</div>
      </div>

      <!-- SSO error from callback -->
      <Transition name="err">
        <div v-if="ssoError" class="login-error" style="margin-bottom:12px;">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ ssoError }}
        </div>
      </Transition>

      <!-- TOTP challenge: shown after password OK when 2FA is enabled -->
      <form v-if="totpChallenge" class="login-form" @submit.prevent="doLoginTotp">
        <div class="field">
          <label class="field-label">{{ t('auth.totp_label') }}</label>
          <input
            v-model="totpCode"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            class="field-input"
            :placeholder="t('auth.totp_placeholder')"
            maxlength="11"
            ref="totpCodeRef"
          />
          <div class="totp-hint">{{ t('auth.totp_hint') }}</div>
        </div>

        <Transition name="err">
          <div v-if="error" class="login-error">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ error }}
          </div>
        </Transition>

        <button type="submit" class="btn-login" :disabled="loading">
          <span v-if="loading" class="btn-spinner" />
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M9 12l2 2 4-4"/><path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9 9 4.03 9 9z"/>
          </svg>
          {{ loading ? t('auth.signing_in') : t('auth.totp_verify') }}
        </button>

        <div class="forgot-link-row">
          <button type="button" class="forgot-link" @click="cancelTotp">
            {{ t('common.cancel') }}
          </button>
        </div>
      </form>

      <!-- Local login form - hidden when mode is "replace" or TOTP step is active -->
      <form v-if="showLocalForm && !totpChallenge" class="login-form" @submit.prevent="doLogin">
        <div class="field">
          <label class="field-label">{{ t('auth.username') }}</label>
          <input
            v-model="username"
            type="text"
            class="field-input"
            placeholder="admin"
            autocomplete="username"
            ref="usernameRef"
          />
        </div>

        <div class="field">
          <label class="field-label">{{ t('auth.password') }}</label>
          <div class="field-password">
            <input
              v-model="password"
              :type="showPwd ? 'text' : 'password'"
              class="field-input"
              placeholder="••••••••"
              autocomplete="current-password"
            />
            <button type="button" class="pwd-toggle" @click="showPwd = !showPwd" tabindex="-1">
              <svg v-if="showPwd" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
              <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>

        <Transition name="err">
          <div v-if="error" class="login-error">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ error }}
          </div>
        </Transition>

        <button type="submit" class="btn-login" :disabled="loading">
          <span v-if="loading" class="btn-spinner" />
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
            <polyline points="10 17 15 12 10 7"/>
            <line x1="15" y1="12" x2="3" y2="12"/>
          </svg>
          {{ loading ? t('auth.signing_in') : t('auth.signin') }}
        </button>

        <div class="forgot-link-row">
          <button type="button" class="forgot-link" @click="showForgot = true" v-if="!showForgot">
            {{ t('login.forgot_password') }}
          </button>
        </div>
      </form>

      <!-- Forgot password inline form -->
      <Transition name="err">
        <div v-if="showForgot && showLocalForm" class="forgot-form">
          <div class="forgot-divider"><span>{{ t('login.reset_password') }}</span></div>

          <form @submit.prevent="doForgot" class="login-form">
            <div class="field">
              <label class="field-label">{{ t('login.email_address') }}</label>
              <input
                v-model="forgotEmail"
                type="email"
                class="field-input"
                placeholder="you@example.com"
                autocomplete="email"
                ref="forgotEmailRef"
              />
            </div>

            <Transition name="err">
              <div v-if="forgotError" class="login-error">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                {{ forgotError }}
              </div>
            </Transition>

            <Transition name="err">
              <div v-if="forgotSuccess" class="forgot-success">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                {{ t('login.reset_link_sent') }}
              </div>
            </Transition>

            <button type="submit" class="btn-login btn-forgot" :disabled="forgotLoading" v-if="!forgotSuccess">
              <span v-if="forgotLoading" class="btn-spinner" />
              <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                <polyline points="22,6 12,13 2,6"/>
              </svg>
              {{ forgotLoading ? t('login.sending') : t('login.send_reset_link') }}
            </button>
          </form>

          <button type="button" class="forgot-link forgot-back" @click="showForgot = false; forgotSuccess = false; forgotError = ''">
            {{ t('login.back_to_login') }}
          </button>
        </div>
      </Transition>

      <!-- SSO providers -->
      <template v-if="providers.length > 0">
        <div v-if="showLocalForm" class="sso-divider">
          <span>{{ t('login.or_continue_with') }}</span>
        </div>

        <div class="sso-buttons">
          <a
            v-for="p in providers"
            :key="p.id"
            :href="`/api/auth/sso/${p.id}`"
            class="btn-sso"
          >
            <!-- Google -->
            <svg v-if="p.icon === 'google'" width="17" height="17" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <!-- GitHub -->
            <svg v-else-if="p.icon === 'github'" width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            <!-- Microsoft -->
            <svg v-else-if="p.icon === 'microsoft'" width="17" height="17" viewBox="0 0 23 23">
              <rect x="1"  y="1"  width="10" height="10" fill="#f25022"/>
              <rect x="12" y="1"  width="10" height="10" fill="#7fba00"/>
              <rect x="1"  y="12" width="10" height="10" fill="#00a4ef"/>
              <rect x="12" y="12" width="10" height="10" fill="#ffb900"/>
            </svg>
            <!-- Generic OIDC -->
            <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 8v4l3 3"/>
            </svg>
            {{ p.name }}
          </a>
        </div>

        <!-- Emergency local login link when in "replace" mode -->
        <div v-if="!showLocalForm" class="sso-local-link">
          <button class="sso-local-btn" @click="showLocalForm = true">{{ t('login.use_local_login') }}</button>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AmbientBackground from '@/components/common/AmbientBackground.vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface Provider { id: string; name: string; icon: string }

const SSO_ERROR_KEYS: Record<string, string> = {
  user_not_found:   'login.sso_user_not_found',
  account_disabled: 'login.sso_account_disabled',
  provider_denied:  'login.sso_provider_denied',
  state_invalid:    'login.sso_state_invalid',
  token_error:      'login.sso_token_error',
  provider_error:   'login.sso_provider_error',
  not_configured:   'login.sso_not_configured',
}

const auth         = useAuthStore()
const router       = useRouter()
const username     = ref('')
const password     = ref('')
const error        = ref('')
const ssoError     = ref('')
const loading      = ref(false)
const showPwd      = ref(false)
const usernameRef  = ref<HTMLInputElement>()
const providers    = ref<Provider[]>([])
const showLocalForm = ref(true)

// TOTP step (after a successful password when 2FA is enabled on the account)
const totpChallenge = ref<string | null>(null)
const totpCode      = ref('')
const totpCodeRef   = ref<HTMLInputElement>()

// Forgot password state
const showForgot      = ref(false)
const forgotEmail     = ref('')
const forgotError     = ref('')
const forgotSuccess   = ref(false)
const forgotLoading   = ref(false)
const forgotEmailRef  = ref<HTMLInputElement>()

onMounted(async () => {
  // Read SSO error from URL if redirected back from callback
  const params = new URLSearchParams(window.location.search)
  const errCode = params.get('sso_error')
  if (errCode) {
    ssoError.value = SSO_ERROR_KEYS[errCode] ? t(SSO_ERROR_KEYS[errCode]) : t('login.sso_generic_error')
    history.replaceState({}, '', '/login')
  }

  // Load enabled SSO providers
  try {
    const { data } = await client.get('/auth/sso/providers')
    providers.value = data.providers || []
    if (data.login_mode === 'replace' && providers.value.length > 0) {
      showLocalForm.value = false
    }
  } catch { /* SSO not available or not configured */ }

  if (showLocalForm.value) {
    setTimeout(() => usernameRef.value?.focus(), 120)
  }
})

async function doLogin() {
  error.value = ''
  if (!username.value.trim()) { error.value = t('auth.username_required'); return }
  if (!password.value)        { error.value = t('auth.password_required'); return }
  loading.value = true
  try {
    const res = await auth.login(username.value.trim(), password.value)
    if (res.requires_totp && res.challenge_token) {
      totpChallenge.value = res.challenge_token
      totpCode.value = ''
      // Focus the code field once Vue has rendered it
      setTimeout(() => totpCodeRef.value?.focus(), 60)
      return
    }
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('login.invalid_credentials')
  } finally {
    loading.value = false
  }
}

async function doLoginTotp() {
  error.value = ''
  const code = totpCode.value.trim()
  if (!code) { error.value = t('auth.totp_required'); return }
  if (!totpChallenge.value) { error.value = t('auth.totp_expired'); return }
  loading.value = true
  try {
    await auth.loginTotp(totpChallenge.value, code)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('auth.totp_invalid')
    // 5-min challenge expired or already burned: drop back to password step
    if (e?.response?.status === 400) {
      totpChallenge.value = null
    }
  } finally {
    loading.value = false
  }
}

function cancelTotp() {
  totpChallenge.value = null
  totpCode.value = ''
  error.value = ''
  password.value = ''
  setTimeout(() => usernameRef.value?.focus(), 60)
}

async function doForgot() {
  forgotError.value = ''
  forgotSuccess.value = false
  const email = forgotEmail.value.trim()
  if (!email) { forgotError.value = t('login.email_required'); return }
  forgotLoading.value = true
  try {
    await client.post('/auth/forgot-password', { email })
    forgotSuccess.value = true
  } catch (e: any) {
    forgotError.value = e?.response?.data?.detail || t('login.generic_error')
  } finally {
    forgotLoading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5, 20px);
  background: var(--bg, #0d0d1a);
  position: relative;
  overflow: hidden;
}

/* Card */
.login-card {
  position: relative;
  z-index: 1;
  width: 360px;
  max-width: 100%;
  padding: 40px 36px 36px;
  border-radius: var(--radius, 16px);
  background: var(--glass-bg, rgba(255,255,255,.04));
  border: 1.5px solid var(--glass-border, rgba(255,255,255,.1));
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 32px 80px rgba(0,0,0,.5);
  animation: card-in .35s ease;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(18px) scale(.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* Brand */
.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-bottom: 32px;
}

.logo-glow-wrap { position: relative; }

.brand-logo {
  height: 72px;
  width: auto;
  object-fit: contain;
  display: block;
  filter:
    drop-shadow(0 0 12px var(--pglow, rgba(124,77,255,.7)))
    drop-shadow(0 0 28px var(--pglow2, rgba(91,33,182,.5)));
  animation: logo-pulse 3.5s ease-in-out infinite;
}
@keyframes logo-pulse {
  0%,100% { filter: drop-shadow(0 0 10px var(--pglow)) drop-shadow(0 0 22px var(--pglow2)); }
  50%     { filter: drop-shadow(0 0 20px var(--pglow)) drop-shadow(0 0 48px var(--pglow2)); }
}

.brand-name {
  font-size: var(--fs-lg, 16px);
  font-weight: 700;
  color: var(--pl-light, #c4b5fd);
  letter-spacing: .5px;
}

/* Form */
.login-form { display: flex; flex-direction: column; gap: var(--space-4, 16px); }

.field { display: flex; flex-direction: column; gap: 6px; }

.field-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--muted, rgba(255,255,255,.45));
  text-transform: uppercase;
}

.field-input {
  width: 100%;
  padding: 12px 15px;
  background: rgba(255,255,255,.05);
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: var(--radius-sm, 10px);
  color: var(--text, #f1f1f1);
  font-family: inherit;
  font-size: var(--fs-md, 14px);
  outline: none;
  transition: border-color .15s, box-shadow .15s;
  box-sizing: border-box;
}
.field-input:focus {
  border-color: var(--pl, #7c3aed);
  box-shadow: 0 0 0 3px var(--pl-dim, rgba(124,77,255,.15));
}
.field-input::placeholder { color: rgba(255,255,255,.25); }

.totp-hint {
  font-size: 11px; color: var(--muted, rgba(255,255,255,.55));
  margin-top: 6px; line-height: 1.5;
}

.field-password { position: relative; }
.field-password .field-input { padding-right: 44px; }

.pwd-toggle {
  position: absolute; right: 12px; top: 50%;
  transform: translateY(-50%);
  background: none; border: none; cursor: pointer;
  padding: var(--space-1, 4px); color: var(--muted);
  display: flex; align-items: center;
}
.pwd-toggle:hover { color: var(--text); }

/* Error */
.login-error {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; color: #f87171;
  padding: 9px 12px; border-radius: var(--radius-sm, 10px);
  background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.25);
}
.err-enter-active, .err-leave-active { transition: all .18s; }
.err-enter-from, .err-leave-to { opacity: 0; transform: translateY(-4px); }

/* Sign In button */
.btn-login {
  display: flex; align-items: center; justify-content: center; gap: var(--space-2, 8px);
  padding: 13px; margin-top: 4px;
  background: var(--pl, #7c3aed); color: #fff;
  border: none; border-radius: var(--radius-sm, 10px);
  cursor: pointer; font-family: inherit; font-weight: 700;
  font-size: var(--fs-md, 14px); letter-spacing: .5px;
  transition: background .15s, box-shadow .15s, transform .1s;
  box-shadow: 0 4px 20px var(--pglow2, rgba(91,33,182,.4));
}
.btn-login:not(:disabled):hover {
  background: var(--pl-light, #a78bfa);
  box-shadow: 0 6px 28px var(--pglow, rgba(124,77,255,.5));
  transform: translateY(-1px);
}
.btn-login:disabled { opacity: .6; cursor: not-allowed; transform: none; }

.btn-spinner {
  width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* SSO divider */
.sso-divider {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  margin: 20px 0 16px;
  font-size: 11px; color: rgba(255,255,255,.3); text-transform: uppercase; letter-spacing: .5px;
}
.sso-divider::before, .sso-divider::after {
  content: ''; flex: 1; height: 1px; background: rgba(255,255,255,.1);
}

/* SSO buttons */
.sso-buttons { display: flex; flex-direction: column; gap: 10px; }

.btn-sso {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 11px 16px;
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-sm, 10px);
  color: var(--text, #f1f1f1);
  font-family: inherit; font-size: var(--fs-md, 14px); font-weight: 500;
  text-decoration: none; cursor: pointer;
  transition: background .15s, border-color .15s, transform .1s;
}
.btn-sso:hover {
  background: rgba(255,255,255,.08);
  border-color: rgba(255,255,255,.22);
  transform: translateY(-1px);
}

/* Emergency local login link */
.sso-local-link { text-align: center; margin-top: 16px; }
.sso-local-btn {
  background: none; border: none; cursor: pointer;
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.3);
  font-family: inherit;
  transition: color .15s;
}
.sso-local-btn:hover { color: rgba(255,255,255,.6); }

/* Forgot password */
.forgot-link-row {
  text-align: center;
  margin-top: 8px;
}

.forgot-link {
  background: none; border: none; cursor: pointer;
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.35);
  font-family: inherit;
  transition: color .15s;
}
.forgot-link:hover { color: var(--pl-light, #a78bfa); }

.forgot-back {
  display: block;
  margin: 12px auto 0;
}

.forgot-form {
  margin-top: 4px;
}

.forgot-divider {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  margin: 12px 0 16px;
  font-size: 11px; color: rgba(255,255,255,.3); text-transform: uppercase; letter-spacing: .5px;
}
.forgot-divider::before, .forgot-divider::after {
  content: ''; flex: 1; height: 1px; background: rgba(255,255,255,.1);
}

.btn-forgot {
  background: var(--pl-dim2, #5b21b6);
  box-shadow: 0 4px 16px rgba(91,33,182,.3);
}
.btn-forgot:not(:disabled):hover {
  background: var(--pl, #7c3aed);
  box-shadow: 0 6px 24px var(--pglow, rgba(124,77,255,.4));
}

.forgot-success {
  display: flex; align-items: flex-start; gap: 7px;
  font-size: 13px; color: #34d399;
  padding: 10px 12px; border-radius: var(--radius-sm, 10px);
  background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.25);
  line-height: 1.4;
}
.forgot-success svg { flex-shrink: 0; margin-top: 2px; }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .login-card { padding: 28px 20px 24px; width: 100%; border-radius: 0; border-left: none; border-right: none; }
}
</style>
