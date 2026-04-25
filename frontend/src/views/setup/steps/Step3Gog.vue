<template>
  <div class="step-content">
    <div class="step-header">
      <div class="step-icon gog-icon">
        <img src="/icons/gog.ico" alt="GOG" width="22" height="22" />
      </div>
      <div>
        <h2 class="step-title">{{ t('setup.gog.title') }}</h2>
        <p class="step-subtitle">{{ t('setup.gog.subtitle') }}</p>
      </div>
    </div>

    <!-- ── Not connected ───────────────────────────────────────────────── -->
    <template v-if="!connected">
      <!-- Instructions -->
      <div class="gog-info">
        <div class="info-row">
          <span class="info-num">1</span>
          <span v-html="t('setup.gog.instruction.1')" />
        </div>
        <div class="info-row">
          <span class="info-num">2</span>
          <span v-html="t('setup.gog.instruction.2')" />
        </div>
        <div class="info-row">
          <span class="info-num">3</span>
          <span v-html="t('setup.gog.instruction.3')" />
        </div>
      </div>

      <!-- Auth URL buttons -->
      <div class="gog-actions">
        <template v-if="authUrl">
          <a :href="authUrl" target="_blank" rel="noopener" class="wizard-btn wizard-btn--gog">
            <img src="/icons/gog.ico" alt="" width="16" height="16" />
            {{ t('setup.gog.button.open_auth') }}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
          <button class="wizard-btn wizard-btn--secondary" @click="copyUrl">
            <svg v-if="!copied" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ copied ? t('setup.gog.button.copied') : t('setup.gog.button.copy_link') }}
          </button>
        </template>
        <div v-else class="gog-loading"><span class="spinner" /> {{ t('setup.gog.loading') }}</div>
      </div>

      <!-- Code / URL input -->
      <div class="field-group">
        <label class="field-label">{{ t('setup.gog.label.code') }}</label>
        <textarea
          v-model="codeInput"
          class="field-input field-textarea"
          :placeholder="t('setup.gog.placeholder.code')"
          rows="2"
          :class="{ 'field-input--error': codeError }"
          @paste="onPaste"
        />
        <span v-if="codeError" class="field-error">{{ codeError }}</span>
      </div>

      <div v-if="serverError" class="field-server-error">{{ serverError }}</div>

      <div class="step-actions">
        <button class="wizard-btn wizard-btn--ghost" @click="emit('skip')">
          {{ t('setup.gog.button.skip') }}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <button
          class="wizard-btn wizard-btn--primary"
          :disabled="!codeInput.trim() || linking"
          @click="linkAccount"
        >
          <span v-if="linking" class="spinner" />
          <span v-else>{{ t('setup.gog.button.link') }}</span>
        </button>
      </div>
    </template>

    <!-- ── Connected - show profile ────────────────────────────────────── -->
    <template v-else>
      <div class="gog-profile">
        <div class="profile-avatar-wrap">
          <img v-if="gogAvatar" :src="gogAvatar" class="profile-avatar" alt="GOG avatar" @error="gogAvatar = ''" />
          <div v-else class="profile-avatar-placeholder">
            <img src="/icons/gog.ico" width="32" height="32" alt="" />
          </div>
          <div class="profile-connected-badge">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
        </div>
        <div class="profile-info">
          <div class="profile-name">{{ gogUsername }}</div>
          <div class="profile-sub">{{ t('setup.gog.profile.connected') }}</div>
        </div>
      </div>

      <!-- Ask about profile picture -->
      <div v-if="gogAvatar" class="avatar-question">
        <div class="avatar-q-text">{{ t('setup.gog.avatar.question') }}</div>
        <div class="avatar-q-actions">
          <button
            class="wizard-btn wizard-btn--secondary"
            :class="{ 'wizard-btn--selected': useAsAvatar === true }"
            @click="useAsAvatar = true"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ t('setup.gog.avatar.yes') }}
          </button>
          <button
            class="wizard-btn wizard-btn--ghost"
            :class="{ 'wizard-btn--selected': useAsAvatar === false }"
            @click="useAsAvatar = false"
          >{{ t('setup.gog.avatar.no') }}</button>
        </div>
        <p v-if="useAsAvatar === true" class="avatar-note">{{ t('setup.gog.avatar.note') }}</p>
      </div>

      <div class="step-actions">
        <button class="wizard-btn wizard-btn--primary" :disabled="continuing" @click="handleContinue">
          <span v-if="continuing" class="spinner" />
          <template v-else>
            {{ t('setup.gog.button.continue') }}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </template>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const emit = defineEmits<{ next: []; skip: []; gogConnected: [boolean] }>()

const authUrl     = ref('')
const codeInput   = ref('')
const codeError   = ref('')
const serverError = ref('')
const linking     = ref(false)
const continuing  = ref(false)
const copied      = ref(false)
const connected   = ref(false)
const gogUsername  = ref('')
const gogAvatar    = ref('')
const useAsAvatar  = ref<boolean | null>(null)

onMounted(async () => {
  try {
    const { data } = await client.get('/setup/gog/url')
    authUrl.value = data.url
  } catch { /* ignore */ }
})

function copyUrl() {
  navigator.clipboard.writeText(authUrl.value).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}

function onPaste() {
  // Auto-submit if pasted text contains code=
  setTimeout(() => {
    const v = codeInput.value.trim()
    if (v.includes('code=') && v.length > 20) {
      linkAccount()
    }
  }, 60)
}

async function handleContinue() {
  if (useAsAvatar.value === true && gogAvatar.value) {
    continuing.value = true
    try {
      await client.post('/setup/gog/avatar', { avatar_url: gogAvatar.value })
    } catch { /* non-fatal - avatar can be set later in Settings */ }
    continuing.value = false
  }
  emit('next')
}

async function linkAccount() {
  if (!codeInput.value.trim()) return
  linking.value = true
  codeError.value = ''
  serverError.value = ''
  try {
    const { data } = await client.post('/setup/gog', { code: codeInput.value.trim() })
    gogUsername.value = data.username || 'GOG User'
    gogAvatar.value   = data.avatar_url || ''
    connected.value   = true
    emit('gogConnected', true)
  } catch (e: any) {
    const msg = e?.response?.data?.detail || ''
    if (msg.toLowerCase().includes('code')) {
      codeError.value = t('setup.gog.error.invalid_code')
    } else {
      serverError.value = msg || t('setup.gog.error.auth_failed')
    }
    emit('gogConnected', false)
  } finally {
    linking.value = false
  }
}
</script>

<style scoped>
.step-content { display: flex; flex-direction: column; gap: var(--space-5, 20px); }

.step-header { display: flex; align-items: flex-start; gap: var(--space-4, 16px); }
.step-icon {
  width: 42px; height: 42px; border-radius: 10px;
  background: rgba(131,99,183,.15); border: 1px solid rgba(131,99,183,.4);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.step-title { font-size: 20px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.step-subtitle { font-size: 13px; color: var(--muted); margin: 0; line-height: 1.6; }

.gog-info {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.info-row { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; color: var(--muted); line-height: 1.5; }
.info-row strong { color: var(--text); }
.info-row em { color: var(--pl-light); font-style: normal; }
.info-num {
  width: 20px; height: 20px; border-radius: 50%; background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700;
  color: var(--pl-light); flex-shrink: 0; margin-top: 1px;
}

.gog-actions { display: flex; flex-wrap: wrap; gap: var(--space-2, 8px); align-items: center; }

.wizard-btn--gog {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px); padding: 10px 18px;
  border-radius: var(--radius-sm); background: rgba(131,99,183,.2);
  border: 1.5px solid rgba(131,99,183,.5); color: var(--text);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; text-decoration: none; transition: all var(--transition);
}
.wizard-btn--gog:hover { background: rgba(131,99,183,.35); border-color: rgba(131,99,183,.8); }

.gog-loading { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: 13px; color: var(--muted); }

.field-group { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.field-input {
  width: 100%; padding: 10px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.field-textarea { resize: none; line-height: 1.5; }
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input--error { border-color: #f87171 !important; }
.field-input::placeholder { color: rgba(255,255,255,.2); font-size: var(--fs-sm, 12px); }
.field-error { font-size: var(--fs-sm, 12px); color: #f87171; }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

/* Profile display */
.gog-profile {
  display: flex; align-items: center; gap: var(--space-4, 16px);
  background: var(--glass-bg); border: 1px solid var(--pl);
  border-radius: var(--radius-sm); padding: 16px 18px;
}
.profile-avatar-wrap { position: relative; flex-shrink: 0; }
.profile-avatar {
  width: 56px; height: 56px; border-radius: 50%;
  border: 2px solid var(--pl); object-fit: cover;
}
.profile-avatar-placeholder {
  width: 56px; height: 56px; border-radius: 50%; border: 2px solid var(--pl);
  background: var(--pl-dim); display: flex; align-items: center; justify-content: center;
}
.profile-connected-badge {
  position: absolute; bottom: -2px; right: -2px;
  width: 18px; height: 18px; border-radius: 50%;
  background: #22c55e; border: 2px solid var(--glass-bg);
  display: flex; align-items: center; justify-content: center; color: #fff;
}
.profile-name { font-size: 15px; font-weight: 700; color: var(--text); }
.profile-sub { font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 2px; }

/* Avatar question */
.avatar-question {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.avatar-q-text { font-size: 13px; font-weight: 600; color: var(--text); }
.avatar-q-actions { display: flex; gap: var(--space-2, 8px); }
.wizard-btn--selected {
  border-color: var(--pl) !important;
  background: var(--pl-dim) !important;
  color: var(--pl-light) !important;
}
.avatar-note { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }

.step-actions { display: flex; gap: 10px; padding-top: 4px; }

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
