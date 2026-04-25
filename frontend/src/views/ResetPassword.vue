<template>
  <div class="reset-shell">
    <AmbientBackground />

    <div class="reset-card">
      <!-- Brand -->
      <div class="reset-brand">
        <div class="logo-glow-wrap">
          <img src="/GDLOGO.png" class="brand-logo" alt="GamesDownloader" />
        </div>
        <div class="brand-name">GamesDownloader</div>
      </div>

      <!-- No token provided -->
      <div v-if="!token" class="reset-error-box">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>Invalid reset link. No token was provided.</span>
      </div>

      <!-- Success state -->
      <div v-else-if="success" class="reset-success-box">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <div>
          <div class="success-title">Password reset successfully!</div>
          <div class="success-sub">Redirecting to login...</div>
        </div>
      </div>

      <!-- Reset form -->
      <form v-else class="reset-form" @submit.prevent="doReset">
        <p class="reset-intro">Enter your new password below.</p>

        <div class="field">
          <label class="field-label">New Password</label>
          <div class="field-password">
            <input
              v-model="newPassword"
              :type="showPwd ? 'text' : 'password'"
              class="field-input"
              placeholder="New password"
              autocomplete="new-password"
              ref="passwordRef"
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

        <div class="field">
          <label class="field-label">Confirm Password</label>
          <div class="field-password">
            <input
              v-model="confirmPassword"
              :type="showPwd2 ? 'text' : 'password'"
              class="field-input"
              placeholder="Confirm password"
              autocomplete="new-password"
            />
            <button type="button" class="pwd-toggle" @click="showPwd2 = !showPwd2" tabindex="-1">
              <svg v-if="showPwd2" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          {{ loading ? 'Resetting...' : 'Reset Password' }}
        </button>
      </form>

      <div class="back-row">
        <router-link to="/login" class="back-link">Back to login</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AmbientBackground from '@/components/common/AmbientBackground.vue'
import client from '@/services/api/client'

const route  = useRoute()
const router = useRouter()

const token           = ref('')
const newPassword     = ref('')
const confirmPassword = ref('')
const error           = ref('')
const loading         = ref(false)
const success         = ref(false)
const showPwd         = ref(false)
const showPwd2        = ref(false)
const passwordRef     = ref<HTMLInputElement>()

onMounted(() => {
  token.value = (route.query.token as string) || ''
  if (token.value) {
    setTimeout(() => passwordRef.value?.focus(), 120)
  }
})

async function doReset() {
  error.value = ''

  if (!newPassword.value) {
    error.value = 'Password is required'
    return
  }
  if (newPassword.value.length < 4) {
    error.value = 'Password must be at least 4 characters'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }

  loading.value = true
  try {
    await client.post('/auth/reset-password', {
      token: token.value,
      password: newPassword.value,
    })
    success.value = true
    setTimeout(() => router.push('/login'), 2500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Invalid or expired reset link'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.reset-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5, 20px);
  background: var(--bg, #0d0d1a);
  position: relative;
  overflow: hidden;
}

.reset-card {
  position: relative;
  z-index: 1;
  width: 400px;
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
.reset-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
}

.logo-glow-wrap { position: relative; }

.brand-logo {
  height: 64px;
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
.reset-form { display: flex; flex-direction: column; gap: var(--space-4, 16px); }

.reset-intro {
  font-size: 13px;
  color: rgba(255,255,255,.45);
  margin: 0 0 4px;
  text-align: center;
}

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

/* Submit button */
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

/* Error / success boxes */
.reset-error-box {
  display: flex; align-items: center; gap: 10px;
  font-size: var(--fs-md, 14px); color: #f87171;
  padding: 14px 16px; border-radius: var(--radius-sm, 10px);
  background: rgba(248,113,113,.06); border: 1px solid rgba(248,113,113,.2);
}

.reset-success-box {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: var(--space-4, 16px);
  border-radius: var(--radius-sm, 10px);
  background: rgba(52,211,153,.06);
  border: 1px solid rgba(52,211,153,.2);
  color: #34d399;
}
.success-title { font-size: 15px; font-weight: 600; }
.success-sub { font-size: var(--fs-sm, 12px); color: rgba(52,211,153,.7); margin-top: 4px; }

/* Back link */
.back-row {
  text-align: center;
  margin-top: 20px;
}
.back-link {
  font-size: var(--fs-sm, 12px);
  color: rgba(255,255,255,.35);
  text-decoration: none;
  transition: color .15s;
}
.back-link:hover { color: var(--pl-light, #a78bfa); }
</style>
