<template>
  <div class="dp-root">
    <div class="dp-card">

      <!-- Logo / branding -->
      <div class="dp-logo">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </div>

      <!-- Loading -->
      <div v-if="state === 'loading'" class="dp-loading">
        <span class="dp-spinner" />
        <span>Checking link…</span>
      </div>

      <!-- Not found / expired / exhausted -->
      <div v-else-if="state === 'invalid'" class="dp-error">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <div class="dp-error-title">Link unavailable</div>
        <div class="dp-error-msg">{{ errorMsg }}</div>
      </div>

      <!-- Password prompt -->
      <div v-else-if="state === 'password'" class="dp-pw-form">
        <div class="dp-file-info">
          <div class="dp-file-name">{{ info.file_name }}</div>
          <div v-if="info.game_title" class="dp-game-title">{{ info.game_title }}</div>
        </div>
        <div class="dp-pw-label">This download is password-protected.</div>
        <input
          v-model="password"
          type="password"
          class="dp-input"
          placeholder="Enter password…"
          @keydown.enter="startDownload"
          ref="pwInput"
          autocomplete="off"
        />
        <div v-if="pwError" class="dp-pw-error">{{ pwError }}</div>
        <button class="dp-btn" :disabled="downloading || !password" @click="startDownload">
          <span v-if="downloading" class="dp-spinner" />
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Download
        </button>
      </div>

      <!-- Ready (no password) -->
      <div v-else-if="state === 'ready'" class="dp-ready">
        <div class="dp-file-info">
          <div class="dp-file-name">{{ info.file_name }}</div>
          <div v-if="info.game_title" class="dp-game-title">{{ info.game_title }}</div>
        </div>
        <button class="dp-btn" :disabled="downloading" @click="startDownload">
          <span v-if="downloading" class="dp-spinner" />
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Download
        </button>
      </div>

      <!-- Downloading -->
      <div v-else-if="state === 'downloading'" class="dp-downloading">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="1.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <div class="dp-dl-title">Download started</div>
        <div class="dp-dl-msg">Your file is downloading. You can close this page.</div>
      </div>

      <div class="dp-footer">GamesDownloader</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route  = useRoute()
const token  = route.params.token as string

type State = 'loading' | 'ready' | 'password' | 'downloading' | 'invalid'
const state      = ref<State>('loading')
const info       = ref<{ file_name: string; game_title: string | null }>({ file_name: '', game_title: null })
const errorMsg   = ref('')
const password   = ref('')
const pwError    = ref('')
const downloading= ref(false)
const pwInput    = ref<HTMLInputElement | null>(null)

onMounted(async () => {
  try {
    const r = await axios.get(`/api/dl/${token}/info`)
    const d = r.data
    info.value = { file_name: d.file_name, game_title: d.game_title }
    if (!d.valid) {
      state.value = 'invalid'
      errorMsg.value = 'This download link has expired or has reached its download limit.'
      return
    }
    if (d.password_required) {
      state.value = 'password'
      await nextTick()
      pwInput.value?.focus()
    } else {
      state.value = 'ready'
    }
  } catch (e: any) {
    state.value = 'invalid'
    errorMsg.value = e?.response?.data?.detail || 'This download link was not found or is no longer valid.'
  }
})

async function startDownload() {
  pwError.value = ''
  downloading.value = true

  let downloadUrl = `/api/dl/${token}`

  if (password.value) {
    // POST password to get a short-lived bypass token - plain password never goes in the URL
    try {
      const { data } = await axios.post(`/api/dl/${token}/auth`, { password: password.value })
      downloadUrl = `/api/dl/${token}?bt=${encodeURIComponent(data.bypass_token)}`
    } catch (e: any) {
      const detail = (e?.response?.data?.detail || '').toLowerCase()
      pwError.value = detail.includes('incorrect') ? 'Incorrect password.' : 'Verification failed. Please try again.'
      downloading.value = false
      return
    }
  }

  // Trigger browser download via hidden anchor
  const a = document.createElement('a')
  a.href = downloadUrl
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)

  await new Promise(r => setTimeout(r, 800))
  state.value = 'downloading'
  downloading.value = false
}
</script>

<style scoped>
.dp-root {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #0f0f13; font-family: 'Segoe UI', Arial, sans-serif; padding: var(--space-4, 16px);
}
.dp-card {
  width: 100%; max-width: 420px;
  background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 16px;
  padding: 36px 32px; display: flex; flex-direction: column; align-items: center; gap: var(--space-6, 24px);
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
.dp-logo {
  width: 56px; height: 56px; border-radius: 14px;
  background: rgba(139,92,246,.15); border: 1px solid rgba(139,92,246,.3);
  display: flex; align-items: center; justify-content: center; color: #a78bfa;
}
.dp-file-info { text-align: center; display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.dp-file-name  { font-size: 15px; font-weight: 600; color: #e2e2f0; word-break: break-all; }
.dp-game-title { font-size: var(--fs-sm, 12px); color: #6b6b8a; }

/* Loading */
.dp-loading { display: flex; align-items: center; gap: 10px; color: #6b6b8a; font-size: var(--fs-md, 14px); }

/* Error */
.dp-error { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.dp-error-title { font-size: var(--fs-lg, 16px); font-weight: 600; color: #f87171; }
.dp-error-msg   { font-size: 13px; color: #6b6b8a; }

/* Password */
.dp-pw-form { width: 100%; display: flex; flex-direction: column; align-items: center; gap: var(--space-3, 12px); }
.dp-pw-label { font-size: 13px; color: #9d9db8; text-align: center; }
.dp-pw-error { font-size: var(--fs-sm, 12px); color: #f87171; }
.dp-input {
  width: 100%; box-sizing: border-box;
  background: #12121c; border: 1px solid #2a2a3a; border-radius: var(--radius-sm, 8px);
  padding: 10px 14px; color: #e2e2f0; font-size: var(--fs-md, 14px); outline: none;
  transition: border-color .15s;
}
.dp-input:focus { border-color: rgba(139,92,246,.6); }

/* Ready */
.dp-ready { display: flex; flex-direction: column; align-items: center; gap: var(--space-4, 16px); width: 100%; }

/* Button */
.dp-btn {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 28px; border-radius: var(--radius-sm, 8px); font-size: var(--fs-md, 14px); font-weight: 600;
  background: rgba(139,92,246,.25); color: #c4b5fd;
  border: 1px solid rgba(139,92,246,.4); cursor: pointer;
  transition: background .15s; min-width: 140px; justify-content: center;
}
.dp-btn:not(:disabled):hover { background: rgba(139,92,246,.4); }
.dp-btn:disabled { opacity: .5; cursor: not-allowed; }

/* Downloading */
.dp-downloading { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.dp-dl-title { font-size: var(--fs-lg, 16px); font-weight: 600; color: #c4b5fd; }
.dp-dl-msg   { font-size: 13px; color: #6b6b8a; }

/* Footer */
.dp-footer { font-size: 11px; color: #3a3a54; margin-top: 8px; }

/* Spinner */
.dp-spinner {
  width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor; border-radius: 50%;
  animation: spin .7s linear infinite; display: inline-block; flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
