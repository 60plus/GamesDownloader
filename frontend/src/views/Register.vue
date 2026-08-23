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

      <!-- Sits above everything else because someone arriving from an invite
           link has never been here: no profile, no stored preference, and quite
           possibly no way to read the language this page opened in. Outside the
           state block on purpose, so it is there whether the page offers a form
           or explains why it cannot. -->
      <div class="reg-lang">
        <LanguagePicker />
      </div>

      <!-- Nothing is shown until the mode is known and, where it matters, the
           code has been checked. Rendering earlier would flash a form at
           someone who is about to be turned away. -->
      <div v-if="!ready" class="reg-wait"><span class="reg-spin" /></div>

      <!-- No form where an account cannot be created: closed outright, or open
           only to someone holding a working invite link. Nothing is offered
           that the server would refuse anyway. -->
      <div v-else-if="blocked" class="reg-gate">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
        <div class="reg-gate-title">{{ gateTitle }}</div>
        <div class="reg-gate-body">{{ gateBody }}</div>
        <button type="button" class="forgot-link" @click="router.push('/login')">
          {{ t('register.have_account') }}
        </button>
      </div>

      <!-- Done: the account exists and the session is live, so this is only a
           beat before the redirect rather than a step the user has to finish. -->
      <div v-else-if="done" class="reg-done">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 12l2 2 4-4"/><path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9 9 4.03 9 9z"/>
        </svg>
        <div class="reg-done-title">{{ t('register.welcome', { name: username.trim() }) }}</div>
      </div>

      <form v-else class="login-form" @submit.prevent="doRegister">
        <div class="reg-title">{{ t('register.title') }}</div>

        <div class="field">
          <label class="field-label">{{ t('auth.username') }}</label>
          <input
            v-model="username"
            type="text"
            class="field-input"
            autocomplete="username"
            maxlength="64"
            ref="usernameRef"
          />
        </div>

        <div class="field">
          <label class="field-label">{{ t('register.email') }}</label>
          <input
            v-model="email"
            type="email"
            class="field-input"
            placeholder="you@example.com"
            autocomplete="email"
            maxlength="255"
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
              autocomplete="new-password"
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
          <div class="totp-hint">{{ t('auth.password_hint') }}</div>
        </div>

        <!-- Not an input at all. The form is reachable in this mode only by
             opening a link whose code has already been checked, so there is
             nothing here to fill in or correct: showing a text box invites an
             edit that could only break a code that was known to be good. -->
        <div v-if="mode === 'invite_only'" class="field">
          <label class="field-label">{{ t('register.invite_code') }}</label>
          <div class="field-static">{{ inviteCode }}</div>
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
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>
          </svg>
          {{ loading ? t('register.creating') : t('register.submit') }}
        </button>

        <div class="forgot-link-row">
          <button type="button" class="forgot-link" @click="router.push('/login')">
            {{ t('register.have_account') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AmbientBackground from '@/components/common/AmbientBackground.vue'
import LanguagePicker from '@/components/common/LanguagePicker.vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { isPasswordOk } from '@/utils/password'

const { t } = useI18n()

const auth   = useAuthStore()
const router = useRouter()

const username   = ref('')
const email      = ref('')
const password   = ref('')
const inviteCode = ref('')
const error      = ref('')
const loading    = ref(false)
const showPwd    = ref(false)
const done       = ref(false)
const usernameRef = ref<HTMLInputElement>()

// '' until the server has told us; the form waits rather than guessing.
const mode = ref('')
// Whether a code arrived in the URL. Kept apart from the field so clearing the
// field cannot talk the page into showing a form it should not.
const arrivedWithCode = ref(false)

// The server confirmed the code is still good. A made-up or spent code has to
// meet the same closed door as no code at all, otherwise typing ?code=anything
// is enough to open the form.
const codeValid = ref(false)
// Every question the page had to ask has been answered.
const ready = ref(false)

// Nothing to fill in: registration is closed, or it is open only to someone
// holding a working invite link and this visitor does not have one.
const blocked = computed(() =>
  mode.value === 'disabled' ||
  (mode.value === 'invite_only' && !(arrivedWithCode.value && codeValid.value)))

// A code was presented and rejected, which is a different thing to explain than
// arriving with no code at all.
const badCode = computed(() =>
  mode.value === 'invite_only' && arrivedWithCode.value && !codeValid.value)

const gateTitle = computed(() =>
  mode.value === 'disabled' ? t('register.closed_title')
    : badCode.value ? t('register.invite_bad_title')
      : t('register.invite_only_title'))

const gateBody = computed(() =>
  mode.value === 'disabled' ? t('register.closed_body')
    : badCode.value ? t('register.invite_bad_body')
      : t('register.invite_only_body'))

// Mirrors UserCreate on the server (username 3-64). Checking here only saves a
// round trip; the server stays the authority. The password rule lives in
// utils/password so all six screens that ask for one cannot disagree.
const MIN_USERNAME = 3

onMounted(async () => {
  // An invite link carries the code, e.g. /register?code=abc123
  const code = new URLSearchParams(window.location.search).get('code')
  if (code) {
    inviteCode.value = code
    arrivedWithCode.value = true
  }
  try {
    const { data } = await client.get('/auth/registration-mode')
    mode.value = String(data?.mode || 'disabled')
  } catch (e) {
    // Cannot tell, so assume closed. Offering a form the server would refuse is
    // the worse of the two guesses.
    mode.value = 'disabled'
    console.error('Failed to read the registration mode', e)
  }

  // Ask whether the code is real before offering a form it could never finish.
  // The check does not spend a use, so opening the link twice costs nothing.
  if (mode.value === 'invite_only' && arrivedWithCode.value) {
    try {
      const { data } = await client.post('/auth/invite/check', { code: inviteCode.value })
      codeValid.value = data?.valid === true
    } catch (e) {
      codeValid.value = false
      console.error('Failed to check the invite code', e)
    }
  }

  ready.value = true
  if (!blocked.value) setTimeout(() => usernameRef.value?.focus(), 120)
})

async function doRegister() {
  error.value = ''
  const name = username.value.trim()
  const mail = email.value.trim()

  if (!name)                     { error.value = t('auth.username_required');    return }
  if (name.length < MIN_USERNAME) { error.value = t('register.username_short');  return }
  if (!mail)                     { error.value = t('register.email_required');   return }
  if (!password.value)           { error.value = t('auth.password_required');    return }
  if (!isPasswordOk(password.value))        { error.value = t('auth.password_rule');     return }

  loading.value = true
  try {
    const body: Record<string, string> = { username: name, email: mail, password: password.value }
    const code = inviteCode.value.trim()
    if (code) body.invite_code = code
    await client.post('/auth/register', body)

    // Registering does not sign anyone in, so do it here rather than sending a
    // brand new account back to the login screen to type the same thing again.
    done.value = true
    try {
      await auth.login(name, password.value)
      setTimeout(() => router.push('/'), 900)
    } catch {
      setTimeout(() => router.push('/login'), 900)
    }
  } catch (e: any) {
    // The server explains the refusal precisely: registrations closed, code
    // required, code spent, name taken. Show that rather than a generic line.
    error.value = e?.response?.data?.detail || t('register.failed')
  } finally {
    loading.value = false
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

.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.reg-lang { display: flex; justify-content: center; margin-bottom: 22px; }

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

.brand-name {
  font-size: var(--fs-lg, 16px);
  font-weight: 700;
  color: var(--pl-light, #c4b5fd);
  letter-spacing: .5px;
}

.reg-title {
  text-align: center;
  font-size: var(--fs-md, 14px);
  font-weight: 700;
  color: var(--text, #f1f1f1);
  margin-bottom: 2px;
}

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

/* Reads as a filled-in field rather than one waiting for input: dimmer, no
   focus ring, no caret. Still selectable, so the code can be copied. */
.field-static {
  width: 100%;
  padding: 12px 15px;
  background: rgba(255,255,255,.02);
  border: 1px dashed var(--glass-border, rgba(255,255,255,.1));
  border-radius: var(--radius-sm, 10px);
  color: var(--muted, rgba(255,255,255,.55));
  font-family: monospace;
  font-size: var(--fs-md, 14px);
  box-sizing: border-box;
  overflow-wrap: anywhere;
  cursor: default;
}

.totp-hint {
  font-size: 11px; color: var(--muted, rgba(255,255,255,.55));
  margin-top: 2px; line-height: 1.5;
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

.login-error {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; color: #f87171;
  padding: 9px 12px; border-radius: var(--radius-sm, 10px);
  background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.25);
}
.err-enter-active, .err-leave-active { transition: all .18s; }
.err-enter-from, .err-leave-to { opacity: 0; transform: translateY(-4px); }

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

.forgot-link-row { text-align: center; margin-top: 8px; }

.forgot-link {
  background: none; border: none; cursor: pointer;
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.35);
  font-family: inherit;
  transition: color .15s;
}
.forgot-link:hover { color: var(--pl-light, #a78bfa); }

.reg-done {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  padding: 8px 0 4px; color: #4ade80; text-align: center;
}
.reg-done-title {
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text, #f1f1f1);
}

.reg-wait { display: flex; justify-content: center; padding: 26px 0; }
.reg-spin {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid var(--glass-border, rgba(255,255,255,.12));
  border-top-color: var(--pl, #7c3aed);
  animation: spin .7s linear infinite; display: inline-block;
}

.reg-gate {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 4px 0; text-align: center; color: var(--muted, rgba(255,255,255,.45));
}
.reg-gate-title {
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text, #f1f1f1);
}
.reg-gate-body {
  font-size: var(--fs-sm, 12px); line-height: 1.6;
  color: var(--muted, rgba(255,255,255,.55));
}
</style>
