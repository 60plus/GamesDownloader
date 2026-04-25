<template>
  <div class="sg-root">

    <!-- ── Loading ─────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="sg-loading">
      <span class="spinner" /> {{ t('common.loading') }}
    </div>

    <!-- ── Connected ───────────────────────────────────────────────────────── -->
    <template v-else-if="status.authenticated">

      <!-- Profile card -->
      <div class="sg-profile-card">
        <div class="sg-avatar-wrap">
          <img
            v-if="status.avatar_url"
            :src="status.avatar_url"
            class="sg-avatar"
            alt="GOG avatar"
            @error="status.avatar_url = ''"
          />
          <div v-else class="sg-avatar-placeholder">
            <img src="/icons/gog.ico" width="32" height="32" alt="" />
          </div>
          <div class="sg-badge">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
        </div>
        <div class="sg-profile-info">
          <div class="sg-username">{{ status.username }}</div>
          <div class="sg-sub">{{ t('gog.connected_account') }}</div>
        </div>
        <button class="sg-disconnect-btn" :disabled="disconnecting" @click="disconnect">
          <span v-if="disconnecting" class="spinner spinner--sm" />
          <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/>
          </svg>
          {{ disconnecting ? t('gog.disconnecting') : t('gog.disconnect') }}
        </button>
      </div>

      <!-- Details table -->
      <div class="sg-details">
        <div v-if="status.email" class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.email') }}</span>
          <span class="sg-detail-value">{{ status.email }}</span>
        </div>
        <div class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.user_id') }}</span>
          <span class="sg-detail-value sg-mono">{{ status.user_id || '-' }}</span>
        </div>
        <div v-if="status.country" class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.country') }}</span>
          <span class="sg-detail-value">{{ status.country }}</span>
        </div>
        <div v-if="status.created_date" class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.member_since') }}</span>
          <span class="sg-detail-value">{{ formatDate(status.created_date) }}</span>
        </div>
        <div v-if="status.games_count !== undefined && status.games_count !== null" class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.games_owned') }}</span>
          <span class="sg-detail-value"><span class="sg-count">{{ status.games_count }}</span></span>
        </div>
        <div v-if="status.movies_count !== undefined && status.movies_count !== null && status.movies_count > 0" class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.movies_owned') }}</span>
          <span class="sg-detail-value"><span class="sg-count">{{ status.movies_count }}</span></span>
        </div>
        <div class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.games_in_library') }}</span>
          <span class="sg-detail-value">
            <span v-if="status.game_count !== undefined" class="sg-count">{{ status.game_count }}</span>
            <span v-else>-</span>
          </span>
        </div>
        <div class="sg-detail-row">
          <span class="sg-detail-label">{{ t('gog.token_expires') }}</span>
          <span class="sg-detail-value">{{ formatExpiry(status.expires_at) }}</span>
        </div>
      </div>

      <!-- Library sync -->
      <div class="sg-section">
        <div class="sg-section-head">
          <div class="sg-section-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </div>
          <div>
            <div class="sg-section-title">{{ t('gog.library_sync') }}</div>
            <div class="sg-section-sub">{{ t('gog.library_sync_desc') }}</div>
          </div>
          <button class="sg-sync-btn" :class="{ 'sg-sync-btn--running': syncing }" :disabled="syncing" @click="triggerSync">
            <span v-if="syncing" class="spinner spinner--sm" />
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ syncing ? t('gog.syncing') : t('gog.sync_now') }}
          </button>
        </div>
        <div v-if="syncMsg" class="sg-sync-msg" :class="syncOk ? 'sg-sync-msg--ok' : 'sg-sync-msg--err'">
          {{ syncMsg }}
        </div>
      </div>

      <div v-if="errorMsg" class="sg-error">{{ errorMsg }}</div>
    </template>

    <!-- ── Not connected ────────────────────────────────────────────────────── -->
    <template v-else>
      <div class="sg-disconnected">
        <div class="sg-dc-icon">
          <img src="/icons/gog.ico" alt="GOG" width="28" height="28" />
        </div>
        <div class="sg-dc-title">{{ t('gog.not_connected') }}</div>
        <div class="sg-dc-sub">{{ t('gog.not_connected_desc') }}</div>
      </div>

      <!-- Connect flow -->
      <div class="sg-connect-card">
        <div class="sg-step-list">
          <div class="sg-step"><span class="sg-step-num">1</span> {{ t('gog.step1') }}</div>
          <div class="sg-step"><span class="sg-step-num">2</span> {{ t('gog.step2') }}</div>
          <div class="sg-step"><span class="sg-step-num">3</span> {{ t('gog.step3') }}</div>
        </div>

        <div class="sg-connect-actions">
          <a v-if="authUrl" :href="authUrl" target="_blank" rel="noopener" class="sg-gog-btn">
            <img src="/icons/gog.ico" alt="" width="14" height="14" />
            {{ t('gog.open_auth') }}
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
          <div v-else class="sg-loading-url"><span class="spinner spinner--sm" /> {{ t('gog.loading_url') }}</div>
        </div>

        <div class="sg-field-group">
          <label class="sg-field-label">{{ t('gog.paste_redirect') }}</label>
          <textarea
            v-model="codeInput"
            class="sg-textarea"
            placeholder="https://embed.gog.com/on_login_success?origin=client&code=…"
            rows="2"
            @paste="onPaste"
          />
        </div>

        <div v-if="connectError" class="sg-error">{{ connectError }}</div>

        <div class="sg-connect-footer">
          <button
            class="sg-primary-btn"
            :disabled="!codeInput.trim() || connecting"
            @click="linkAccount"
          >
            <span v-if="connecting" class="spinner" />
            <span v-else>{{ t('gog.connect_account') }}</span>
          </button>
        </div>
      </div>
    </template>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()
const { gdConfirm } = useDialog()

interface GogStatus {
  authenticated: boolean
  username?: string
  avatar_url?: string
  user_id?: string
  expires_at?: string
  game_count?: number
  email?: string
  country?: string
  created_date?: string
  games_count?: number
  movies_count?: number
}

const loading      = ref(true)
const disconnecting = ref(false)
const connecting   = ref(false)
const syncing      = ref(false)
const syncMsg      = ref('')
const syncOk       = ref(true)
const errorMsg     = ref('')
const connectError = ref('')
const codeInput    = ref('')
const authUrl      = ref('')

const status = reactive<GogStatus>({ authenticated: false })

onMounted(async () => {
  await loadStatus()
  loading.value = false
  if (!status.authenticated) {
    try {
      const { data } = await client.get('/gog/auth/url')
      authUrl.value = data.url || ''
    } catch { /* ignore */ }
  }
})

async function loadStatus() {
  try {
    const { data } = await client.get('/gog/auth/status')
    Object.assign(status, data)
  } catch {
    status.authenticated = false
  }
}

function getLocale(): string {
  return localStorage.getItem('gd3_locale') || navigator.language || 'en'
}

function formatExpiry(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString(getLocale(), { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

function formatDate(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(getLocale(), { year: 'numeric', month: 'long', day: 'numeric' })
  } catch {
    return iso
  }
}

async function disconnect() {
  const ok = await gdConfirm(t('gog.disconnect_confirm', 'Disconnect your GOG account? You will need to reconnect to access your GOG library.'), { title: t('gog.disconnect', 'Disconnect'), danger: true, confirmText: t('gog.disconnect', 'Disconnect') })
  if (!ok) return
  disconnecting.value = true
  errorMsg.value = ''
  try {
    await client.delete('/gog/auth')
    status.authenticated = false
    status.username = undefined
    status.avatar_url = undefined
    status.user_id = undefined
    status.expires_at = undefined
    status.game_count = undefined
    // Load GOG auth URL for re-connect
    try {
      const { data } = await client.get('/gog/auth/url')
      authUrl.value = data.url || ''
    } catch { /* ignore */ }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t('gog.disconnect_failed')
  } finally {
    disconnecting.value = false
  }
}

function onPaste() {
  setTimeout(() => {
    const v = codeInput.value.trim()
    if (/^https:\/\/embed\.gog\.com\/on_login_success\?.*code=/.test(v)) linkAccount()
  }, 60)
}

async function linkAccount() {
  if (!codeInput.value.trim()) return
  connecting.value = true
  connectError.value = ''
  try {
    const { data } = await client.post('/gog/auth/callback', { code: codeInput.value.trim() })
    Object.assign(status, {
      authenticated: true,
      username:  data.username || 'GOG User',  // fallback display name
      avatar_url: data.avatar_url || '',
    })
    codeInput.value = ''
    await loadStatus()  // reload to get user_id, expires_at, game_count
  } catch (e: any) {
    connectError.value = e?.response?.data?.detail || t('gog.auth_failed')
  } finally {
    connecting.value = false
  }
}

let _syncPoll: ReturnType<typeof setInterval> | null = null

onUnmounted(() => {
  if (_syncPoll !== null) {
    clearInterval(_syncPoll)
    _syncPoll = null
  }
})

async function triggerSync() {
  syncing.value = true
  syncMsg.value = ''
  syncOk.value  = true
  try {
    await client.post('/gog/library/sync')
    _syncPoll = setInterval(async () => {
      try {
        const { data } = await client.get('/gog/library/sync/status')
        if (!data.running) {
          clearInterval(_syncPoll!)
          syncing.value = false
          if (data.error) {
            syncOk.value  = false
            syncMsg.value = t('gog.sync_failed', { error: data.error })
          } else {
            syncOk.value  = true
            syncMsg.value = t('gog.sync_complete', { count: data.synced })
            status.game_count = data.synced
          }
        }
      } catch {
        clearInterval(_syncPoll!)
        syncing.value = false
      }
    }, 1500)
  } catch (e: any) {
    syncing.value = false
    syncOk.value  = false
    syncMsg.value = e?.response?.data?.detail || t('gog.start_sync_failed')
  }
}
</script>

<style scoped>
.sg-root { display: flex; flex-direction: column; gap: var(--space-4, 16px); }

/* ── Loading ──────────────────────────────────────────────────────────────── */
.sg-loading {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: 13px; color: var(--muted); padding: 8px 0;
}

/* ── Profile card ─────────────────────────────────────────────────────────── */
.sg-profile-card {
  display: flex; align-items: center; gap: var(--space-4, 16px);
  padding: 16px 18px;
  background: var(--glass-bg); border: 1px solid var(--pl);
  border-radius: var(--radius-sm);
}

.sg-avatar-wrap { position: relative; flex-shrink: 0; }
.sg-avatar {
  width: 60px; height: 60px; border-radius: 50%;
  border: 2px solid var(--pl); object-fit: cover;
}
.sg-avatar-placeholder {
  width: 60px; height: 60px; border-radius: 50%;
  border: 2px solid var(--pl); background: var(--pl-dim);
  display: flex; align-items: center; justify-content: center;
}
.sg-badge {
  position: absolute; bottom: -2px; right: -2px;
  width: 18px; height: 18px; border-radius: 50%;
  background: #22c55e; border: 2px solid var(--glass-bg);
  display: flex; align-items: center; justify-content: center; color: #fff;
}

.sg-profile-info { flex: 1; min-width: 0; }
.sg-username { font-size: 17px; font-weight: 700; color: var(--text); }
.sg-sub { font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 2px; }

.sg-disconnect-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: var(--radius-sm);
  border: 1px solid rgba(248,113,113,.4); background: rgba(248,113,113,.08);
  color: #f87171; font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition); flex-shrink: 0;
  white-space: nowrap;
}
.sg-disconnect-btn:not(:disabled):hover { background: rgba(248,113,113,.16); border-color: #f87171; }
.sg-disconnect-btn:disabled { opacity: .55; cursor: not-allowed; }

/* ── Details ──────────────────────────────────────────────────────────────── */
.sg-details {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); overflow: hidden;
}
.sg-detail-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 16px; gap: var(--space-4, 16px);
}
.sg-detail-row + .sg-detail-row { border-top: 1px solid var(--glass-border); }
.sg-detail-label { font-size: var(--fs-sm, 12px); color: var(--muted); font-weight: 600; flex-shrink: 0; }
.sg-detail-value { font-size: 13px; color: var(--text); text-align: right; }
.sg-mono { font-family: monospace; font-size: var(--fs-sm, 12px); }
.sg-count {
  display: inline-block; background: var(--pl-dim); border: 1px solid var(--pl);
  color: var(--pl-light); border-radius: var(--radius, 12px); padding: 1px 10px;
  font-size: var(--fs-sm, 12px); font-weight: 700;
}

/* ── Section (sync) ───────────────────────────────────────────────────────── */
.sg-section {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.sg-section-head {
  display: flex; align-items: center; gap: var(--space-3, 12px); padding: 14px 16px;
}
.sg-section-icon {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px); flex-shrink: 0;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center; color: var(--pl-light);
}
.sg-section-title { font-size: 13px; font-weight: 700; color: var(--text); }
.sg-section-sub { font-size: 11px; color: var(--muted); margin-top: 1px; }

.sg-sync-btn {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: var(--radius-sm); flex-shrink: 0;
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.sg-sync-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.sg-sync-btn:disabled { opacity: .6; cursor: not-allowed; }
.sg-sync-btn--running { border-color: var(--pl); color: var(--pl-light); }

.sg-sync-msg {
  padding: 9px 16px; font-size: var(--fs-sm, 12px);
  border-top: 1px solid var(--glass-border);
}
.sg-sync-msg--ok { color: #86efac; background: rgba(34,197,94,.06); }
.sg-sync-msg--err { color: #f87171; background: rgba(248,113,113,.06); }

/* ── Error ────────────────────────────────────────────────────────────────── */
.sg-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

/* ── Disconnected state ───────────────────────────────────────────────────── */
.sg-disconnected {
  display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px);
  padding: 24px 0 8px; text-align: center;
}
.sg-dc-icon {
  width: 56px; height: 56px; border-radius: 50%;
  background: rgba(131,99,183,.12); border: 2px solid rgba(131,99,183,.35);
  display: flex; align-items: center; justify-content: center;
}
.sg-dc-title { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); }
.sg-dc-sub { font-size: 13px; color: var(--muted); max-width: 380px; line-height: 1.5; }

/* ── Connect card ─────────────────────────────────────────────────────────── */
.sg-connect-card {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 16px 18px;
  display: flex; flex-direction: column; gap: 14px;
}
.sg-step-list { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.sg-step {
  display: flex; align-items: flex-start; gap: 10px;
  font-size: 13px; color: var(--muted); line-height: 1.5;
}
.sg-step em { color: var(--pl-light); font-style: normal; }
.sg-step-num {
  width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: var(--pl-light);
}

.sg-connect-actions { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }

.sg-gog-btn {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--text); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; text-decoration: none; transition: all var(--transition);
}
.sg-gog-btn:hover { background: rgba(131,99,183,.28); border-color: rgba(131,99,183,.7); }

.sg-loading-url {
  display: flex; align-items: center; gap: 6px;
  font-size: var(--fs-sm, 12px); color: var(--muted);
}

.sg-field-group { display: flex; flex-direction: column; gap: 5px; }
.sg-field-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1px;
}
.sg-textarea {
  width: 100%; padding: 9px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  resize: none; line-height: 1.5;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.sg-textarea:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.sg-textarea::placeholder { color: rgba(255,255,255,.2); font-size: var(--fs-sm, 12px); }

.sg-connect-footer { display: flex; justify-content: flex-end; }

.sg-primary-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
  box-shadow: 0 2px 12px var(--pglow2);
}
.sg-primary-btn:not(:disabled):hover { background: var(--pl-light); }
.sg-primary-btn:disabled { opacity: .6; cursor: not-allowed; }

/* ── Spinner ──────────────────────────────────────────────────────────────── */
.spinner {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
.spinner--sm { width: 10px; height: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
