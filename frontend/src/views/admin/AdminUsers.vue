<template>
  <div class="admin-users">

    <!-- ── Header ────────────────────────────────────────────────────────────── -->
    <div class="au-header">
      <div class="au-header-left">
        <h1 class="au-title">{{ t('users.title') }}</h1>
        <span class="au-count">{{ t('users.count', { count: users.length }) }}</span>
      </div>
      <button class="au-add-btn" @click="openCreate">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('users.new_user') }}
      </button>
    </div>

    <!-- ── Loading ───────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="au-loading">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-svg" style="opacity:.3">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </div>

    <!-- ── Table ─────────────────────────────────────────────────────────────── -->
    <div v-else class="au-table-wrap">
      <table class="au-table">
        <thead>
          <tr>
            <th>{{ t('users.col_user') }}</th>
            <th>{{ t('users.col_role') }}</th>
            <th>{{ t('users.col_status') }}</th>
            <th>{{ t('users.col_permissions') }}</th>
            <th>{{ t('users.col_joined') }}</th>
            <th>{{ t('users.col_actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="u in users"
            :key="u.id"
            class="au-row"
            :class="{ 'au-row--me': u.id === myId, 'au-row--disabled': !u.enabled }"
          >
            <!-- User info -->
            <td class="au-cell-user">
              <div class="au-avatar">
                <img v-if="u.avatar_path" :src="avatarUrl(u)" class="au-avatar-img" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span v-else class="au-avatar-initials">{{ initials(u.username) }}</span>
              </div>
              <div class="au-user-info">
                <span class="au-username">{{ u.username }} <span v-if="u.id === myId" class="me-badge">{{ t('users.you') }}</span></span>
                <span class="au-email">{{ u.email || '-' }}</span>
              </div>
            </td>

            <!-- Role -->
            <td>
              <select
                class="au-role-sel"
                :value="u.role"
                :disabled="u.id === myId"
                @change="changeRole(u, ($event.target as HTMLSelectElement).value)"
              >
                <option value="admin">{{ t('users.role_admin', 'Admin') }}</option>
                <option value="uploader">{{ t('users.role_uploader', 'Uploader') }}</option>
                <option value="editor">{{ t('users.role_editor', 'Editor') }}</option>
                <option value="user">{{ t('users.role_user', 'User') }}</option>
              </select>
            </td>

            <!-- Status -->
            <td>
              <button
                class="au-toggle-btn"
                :class="{ active: u.enabled }"
                :disabled="u.id === myId"
                @click="toggleEnabled(u)"
                :title="u.enabled ? t('users.disable_user') : t('users.enable_user')"
              >
                {{ u.enabled ? t('users.active') : t('users.disabled_status') }}
              </button>
            </td>

            <!-- Permissions overrides -->
            <td>
              <div class="au-perms">
                <button
                  class="perm-chip"
                  :class="permChipClass(u, 'access_gamesdownloader')"
                  @click="togglePerm(u, 'access_gamesdownloader')"
                  :title="t('users.toggle_games')"
                >
                  {{ t('users.games') }}
                </button>
                <button
                  class="perm-chip"
                  :class="permChipClass(u, 'edit_metadata')"
                  @click="togglePerm(u, 'edit_metadata')"
                  :disabled="!['uploader','editor'].includes(u.role)"
                  :title="t('users.toggle_meta')"
                >
                  {{ t('users.edit_meta') }}
                </button>
                <button
                  class="perm-chip"
                  :class="permChipClass(u, 'upload')"
                  @click="togglePerm(u, 'upload')"
                  :disabled="u.role !== 'uploader'"
                  :title="t('users.toggle_upload')"
                >
                  {{ t('users.upload') }}
                </button>
              </div>
            </td>

            <!-- Joined -->
            <td class="au-cell-date">{{ fmtDate(u.created_at) }}</td>

            <!-- Actions -->
            <td>
              <div class="au-row-actions">
                <button class="au-icon-btn" @click="openResetPwd(u)" :title="t('users.reset_password')">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </button>
                <button
                  class="au-icon-btn au-icon-btn--danger"
                  :disabled="u.id === myId"
                  @click="confirmDelete(u)"
                  :title="t('users.delete_user')"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ══ Create user dialog ══════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div v-if="showCreate" class="au-overlay" @click.self="showCreate = false">
        <div class="au-dialog glass">
          <div class="au-dlg-header">
            <span>{{ t('users.create_dialog') }}</span>
            <button class="dlg-close" @click="showCreate = false">×</button>
          </div>
          <div class="au-dlg-body">
            <label class="au-label">{{ t('users.username') }}</label>
            <input v-model="createForm.username" class="au-input" placeholder="username" autocomplete="off" />
            <label class="au-label">{{ t('users.email') }}</label>
            <input v-model="createForm.email" class="au-input" placeholder="user@example.com" type="email" required />
            <label class="au-label">{{ t('users.password') }}</label>
            <input v-model="createForm.password" class="au-input" placeholder="min. 8 characters" type="password" autocomplete="new-password" />
            <label class="au-label">{{ t('users.role') }}</label>
            <select v-model="createForm.role" class="au-input">
              <option value="user">User</option>
              <option value="editor">Editor</option>
              <option value="uploader">Uploader</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div v-if="createError" class="au-dlg-error">{{ createError }}</div>
          <div class="au-dlg-footer">
            <button class="au-ghost-btn" @click="showCreate = false">{{ t('common.cancel') }}</button>
            <button class="au-submit-btn" :disabled="creating" @click="doCreate">
              <div v-if="creating" class="btn-spinner" />
              <span v-else>{{ t('users.create') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Reset password dialog ══════════════════════════════════════════════ -->
    <Teleport to="body">
      <div v-if="showResetPwd" class="au-overlay" @click.self="showResetPwd = false">
        <div class="au-dialog glass">
          <div class="au-dlg-header">
            <span>{{ t('users.reset_pwd_title', { name: resetPwdUser?.username || '' }) }}</span>
            <button class="dlg-close" @click="showResetPwd = false">×</button>
          </div>
          <div class="au-dlg-body">
            <label class="au-label">{{ t('users.new_pwd_label') }}</label>
            <input v-model="newPassword" class="au-input" placeholder="••••••••" type="password" autocomplete="new-password" />
          </div>
          <div v-if="resetPwdError" class="au-dlg-error">{{ resetPwdError }}</div>
          <div class="au-dlg-footer">
            <button class="au-ghost-btn" @click="showResetPwd = false">{{ t('common.cancel') }}</button>
            <button class="au-submit-btn" :disabled="resetting" @click="doResetPwd">
              <div v-if="resetting" class="btn-spinner" />
              <span v-else>{{ t('users.set_password') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Delete confirm ══════════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="au-overlay" @click.self="showDeleteConfirm = false">
        <div class="au-dialog au-dialog--danger glass">
          <div class="au-dlg-header">
            <span>{{ t('users.delete_title') }}</span>
            <button class="dlg-close" @click="showDeleteConfirm = false">×</button>
          </div>
          <div class="au-dlg-body">
            <p style="font-size:13px;color:var(--muted)" v-html="t('users.delete_confirm', { name: '<strong style=\'color:var(--text)\'>' + (deleteTarget?.username || '') + '</strong>' })">
            </p>
          </div>
          <div class="au-dlg-footer">
            <button class="au-ghost-btn" @click="showDeleteConfirm = false">{{ t('common.cancel') }}</button>
            <button class="au-danger-btn" :disabled="deleting" @click="doDelete">
              <div v-if="deleting" class="btn-spinner" />
              <span v-else>{{ t('common.delete') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Invite Codes ────────────────────────────────────────────────────── -->
    <div class="au-section" style="margin-top:28px">
      <div class="au-section-title">
        {{ t('users.invite_codes') }}
        <span v-if="activeInviteCount > 0" class="au-badge">{{ t('users.invite_active', { count: activeInviteCount }) }}</span>
      </div>
      <div class="au-invite-create">
        <div class="au-invite-fields">
          <div class="au-field">
            <label class="au-field-label">{{ t('users.max_uses') }}</label>
            <input type="number" v-model.number="newInvite.max_uses" min="1" max="100" class="au-input" style="width:80px" />
          </div>
          <div class="au-field">
            <label class="au-field-label">{{ t('users.expires_in') }}</label>
            <input type="number" v-model.number="newInvite.expires_in_hours" min="1" class="au-input" style="width:100px" placeholder="never" />
          </div>
          <div class="au-field" style="flex:1">
            <label class="au-field-label">{{ t('users.note') }}</label>
            <input type="text" v-model="newInvite.note" class="au-input" placeholder="e.g. for John" maxlength="100" />
          </div>
        </div>
        <button class="au-add-btn" :disabled="inviteCreating" @click="createInvite" style="margin-top:8px">
          <span v-if="inviteCreating" class="au-spinner" />
          <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {{ t('users.generate_code') }}
        </button>
      </div>
      <div v-if="inviteLoading" class="au-loading" style="padding:16px"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-svg" style="opacity:.3"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg></div>
      <div v-else-if="invites.length === 0" class="au-empty" style="padding:12px 0;color:var(--muted);font-size:13px">{{ t('users.no_invites') }}</div>
      <table v-else class="au-table" style="margin-top:8px">
        <thead>
          <tr><th>{{ t('users.col_code') }}</th><th>{{ t('users.col_uses') }}</th><th>{{ t('users.col_expires') }}</th><th>{{ t('users.col_note') }}</th><th>{{ t('users.col_by') }}</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="inv in invites" :key="inv.id" :style="!inv.is_active ? 'opacity:.4' : ''">
            <td><code class="au-invite-code" @click="copyInviteCode(inv.code)" title="Click to copy" style="cursor:pointer;color:var(--pl)">{{ inv.code }}</code></td>
            <td style="font-family:monospace">{{ inv.use_count }} / {{ inv.max_uses }}</td>
            <td>{{ inv.expires_at ? new Date(inv.expires_at).toLocaleString() : '∞' }}</td>
            <td>{{ inv.note || '-' }}</td>
            <td style="font-family:monospace">{{ inv.created_by || '-' }}</td>
            <td><button class="au-icon-btn au-icon-btn--danger" @click="deleteInvite(inv.id)"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="inviteCopied" class="au-ok" style="margin-top:6px;color:#4ade80;font-size:12px">{{ t('users.code_copied') }}</div>
    </div>

    <!-- ── Active Sessions (paginated, 10 per page) ─────────────────────────── -->
    <div class="au-section" style="margin-top:28px">
      <div class="au-section-header">
        <h2 class="au-section-title">{{ t('users.active_sessions') }}</h2>
        <div class="au-section-actions">
          <button class="au-ghost-btn" @click="loadSessions" :disabled="sessLoading">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('users.refresh') }}
          </button>
          <button class="au-danger-btn" @click="revokeAllSessions" :disabled="sessRevoking">
            <span v-if="sessRevoking" class="btn-spinner" />
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            {{ t('users.logout_everywhere') }}
          </button>
        </div>
      </div>

      <div v-if="sessLoading" class="au-loading">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-svg" style="opacity:.3">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
      </div>
      <div v-else-if="sessions.length === 0" class="au-sess-empty">{{ t('users.no_sessions') }}</div>
      <template v-else>
        <div class="au-table-wrap">
          <table class="au-table">
            <thead>
              <tr>
                <th></th>
                <th>{{ t('users.col_user') }}</th>
                <th>{{ t('users.col_browser') }}</th>
                <th>{{ t('users.col_ip') }}</th>
                <th>{{ t('users.col_last_used') }}</th>
                <th>{{ t('users.col_created') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in pagedSessions" :key="s.id" :class="{ 'au-sess-row--current': s.is_current }">
                <td class="au-sess-dot-cell">
                  <span class="au-sess-dot" :class="s.is_current ? 'au-sess-dot--current' : ''" />
                </td>
                <td class="au-cell-mono">{{ s.username }}</td>
                <td>
                  <span class="au-sess-browser">{{ s.user_agent || '-' }}</span>
                  <span v-if="s.is_current" class="au-sess-badge">{{ t('users.this_session') }}</span>
                </td>
                <td class="au-cell-mono">{{ s.ip_address || '-' }}</td>
                <td class="au-cell-date">{{ s.last_used ? fmtDateTime(s.last_used) : '-' }}</td>
                <td class="au-cell-date">{{ s.created_at ? fmtDateTime(s.created_at) : '-' }}</td>
                <td>
                  <button
                    class="au-icon-btn au-icon-btn--danger"
                    :disabled="sessRevoking"
                    @click="revokeSession(s.id, s.is_current)"
                    :title="s.is_current ? t('users.logout_session') : t('users.revoke_session')"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Pagination -->
        <div v-if="sessTotalPages > 1" class="au-pagination">
          <button class="au-page-btn" :disabled="sessPage <= 1" @click="sessPage--">&laquo;</button>
          <span class="au-page-info">{{ sessPage }} / {{ sessTotalPages }}</span>
          <button class="au-page-btn" :disabled="sessPage >= sessTotalPages" @click="sessPage++">&raquo;</button>
        </div>
      </template>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import client from '@/services/api/client'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface UserRecord {
  id: number
  username: string
  email: string | null
  role: string
  enabled: boolean
  avatar_path: string | null
  permissions: Record<string, boolean> | null
  created_at: string
}

const auth = useAuthStore()
const myId = ref<number | null>(null)
const { gdConfirm, gdAlert } = useDialog()

const users   = ref<UserRecord[]>([])
const loading = ref(true)

// ── Helpers ───────────────────────────────────────────────────────────────────

function initials(name: string) { return name.slice(0, 2).toUpperCase() }

function avatarUrl(u: UserRecord): string {
  const p = u.avatar_path
  if (!p) return ''
  if (p.startsWith('http')) return p
  const filename = p.split(/[\\/]/).pop() || ''
  return filename ? `/resources/avatars/${filename}` : ''
}

function fmtDate(iso: string): string {
  const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
  return new Date(iso).toLocaleDateString(loc, { year: 'numeric', month: 'short', day: 'numeric' })
}

function fmtDateTime(iso: string): string {
  const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
  return new Date(iso).toLocaleString(loc)
}

// Permission chip: undefined = role default (neutral), false = denied, true = explicitly granted
function permChipClass(u: UserRecord, key: string): string {
  const v = u.permissions?.[key]
  if (v === false) return 'denied'
  if (v === true) return 'granted'
  return ''
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

async function fetchUsers() {
  loading.value = true
  try {
    const { data } = await client.get('/users')
    users.value = data
  } catch (e) {
    console.error('Failed to load users', e)
  } finally {
    loading.value = false
  }
}

// ── Invite Codes ───────────────────────────────────────────────────────────
interface Invite { id: number; code: string; max_uses: number; use_count: number; expires_at: string | null; note: string; created_by: string; is_active: boolean }
const invites = ref<Invite[]>([])
const activeInviteCount = computed(() => (invites.value || []).filter(i => i.is_active).length)

// Sessions pagination
const SESS_PER_PAGE = 10
const sessPage = ref(1)
const sessTotalPages = computed(() => Math.max(1, Math.ceil(sessions.value.length / SESS_PER_PAGE)))
const pagedSessions = computed(() => {
  const start = (sessPage.value - 1) * SESS_PER_PAGE
  return sessions.value.slice(start, start + SESS_PER_PAGE)
})
const inviteLoading = ref(false)
const inviteCreating = ref(false)
const inviteCopied = ref(false)
const newInvite = ref({ max_uses: 1, expires_in_hours: null as number | null, note: '' })

async function loadInvites() {
  inviteLoading.value = true
  try { const { data } = await client.get('/settings/security/invites'); invites.value = Array.isArray(data) ? data : [] } catch {}
  finally { inviteLoading.value = false }
}
async function createInvite() {
  inviteCreating.value = true
  try {
    await client.post('/settings/security/invites', newInvite.value)
    newInvite.value = { max_uses: 1, expires_in_hours: null, note: '' }
    await loadInvites()
  } catch {}
  finally { inviteCreating.value = false }
}
async function deleteInvite(id: number) {
  try { await client.delete(`/settings/security/invites/${id}`); await loadInvites() } catch {}
}
function copyInviteCode(code: string) {
  const url = `${window.location.origin}/register?code=${code}`
  navigator.clipboard.writeText(url).then(() => { inviteCopied.value = true; setTimeout(() => { inviteCopied.value = false }, 3000) })
}

onMounted(async () => {
  myId.value = (auth.user as any)?.id ?? null
  await Promise.all([fetchUsers(), loadSessions()])
  loadInvites().catch(() => {})
})

// ── Role ──────────────────────────────────────────────────────────────────────

async function changeRole(u: UserRecord, role: string) {
  try {
    await client.patch(`/users/${u.id}`, { role })
    u.role = role
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to change role')
  }
}

// ── Enable / Disable ──────────────────────────────────────────────────────────

async function toggleEnabled(u: UserRecord) {
  try {
    await client.patch(`/users/${u.id}`, { enabled: !u.enabled })
    u.enabled = !u.enabled
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to update user')
  }
}

// ── Permission toggles ────────────────────────────────────────────────────────
// Cycle: role-default (no key) → explicitly denied (false) → explicitly granted (true) → role-default

async function togglePerm(u: UserRecord, key: string) {
  const current = u.permissions?.[key]
  let next: boolean | null
  if (current === undefined)   next = false   // role-default → deny
  else if (current === false)  next = true    // deny → explicitly allow
  else                         next = null    // grant → back to role-default (remove key)

  const newPerms: Record<string, boolean | null> = { ...(u.permissions ?? {}) }
  if (next === null) delete newPerms[key]
  else newPerms[key] = next

  const payload = Object.keys(newPerms).length ? newPerms : null
  try {
    await client.patch(`/users/${u.id}`, { permissions: payload })
    u.permissions = payload as Record<string, boolean> | null
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to update permissions')
  }
}

// ── Create user ───────────────────────────────────────────────────────────────

const showCreate  = ref(false)
const creating    = ref(false)
const createError = ref('')
const createForm  = ref({ username: '', email: '', password: '', role: 'user' })

function openCreate() {
  createForm.value = { username: '', email: '', password: '', role: 'user' }
  createError.value = ''
  showCreate.value = true
}

async function doCreate() {
  if (!createForm.value.username || !createForm.value.password || !createForm.value.email) {
    createError.value = 'Username, email and password are required'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const payload: Record<string, string> = {
      username: createForm.value.username,
      email:    createForm.value.email,
      password: createForm.value.password,
      role:     createForm.value.role,
    }
    await client.post('/users', payload)
    showCreate.value = false
    await fetchUsers()
  } catch (e: any) {
    createError.value = e?.response?.data?.detail || 'Failed to create user'
  } finally {
    creating.value = false
  }
}

// ── Reset password ────────────────────────────────────────────────────────────

const showResetPwd  = ref(false)
const resetting     = ref(false)
const resetPwdError = ref('')
const resetPwdUser  = ref<UserRecord | null>(null)
const newPassword   = ref('')

function openResetPwd(u: UserRecord) {
  resetPwdUser.value = u
  newPassword.value  = ''
  resetPwdError.value = ''
  showResetPwd.value = true
}

async function doResetPwd() {
  if (newPassword.value.length < 8) {
    resetPwdError.value = 'Password must be at least 8 characters'
    return
  }
  resetting.value = true
  resetPwdError.value = ''
  try {
    await client.post(`/users/${resetPwdUser.value!.id}/reset-password`, {
      new_password: newPassword.value,
    })
    showResetPwd.value = false
  } catch (e: any) {
    resetPwdError.value = e?.response?.data?.detail || 'Failed to reset password'
  } finally {
    resetting.value = false
  }
}

// ── Active Sessions ───────────────────────────────────────────────────────────

interface SessionEntry {
  id:         number
  username:   string
  ip_address: string | null
  user_agent: string | null
  last_used:  string | null
  created_at: string | null
  is_current: boolean
}

const sessions     = ref<SessionEntry[]>([])
const sessLoading  = ref(false)
const sessRevoking = ref(false)

async function loadSessions() {
  sessLoading.value = true
  try {
    sessions.value = await client.get('/settings/security/sessions').then(r => r.data)
  } catch { /* ignore */ } finally {
    sessLoading.value = false
  }
}

async function revokeSession(id: number, isCurrent: boolean) {
  const msg = isCurrent
    ? 'Log out of this session? You will need to log in again.'
    : 'Revoke this session? The device will be logged out immediately.'
  if (!await gdConfirm(msg, { title: isCurrent ? 'Logout' : 'Revoke Session', danger: true, confirmText: isCurrent ? 'Logout' : 'Revoke' })) return
  sessRevoking.value = true
  try {
    await client.delete(`/settings/security/sessions/${id}`)
    if (isCurrent) {
      auth.logout()
      window.location.href = '/login'
      return
    }
    await loadSessions()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to revoke session.', { title: 'Error', danger: true })
  } finally {
    sessRevoking.value = false
  }
}

async function revokeAllSessions() {
  if (!await gdConfirm('Revoke ALL your sessions? You will be logged out everywhere immediately.', {
    title: 'Logout Everywhere',
    danger: true,
    confirmText: 'Logout Everywhere',
  })) return
  sessRevoking.value = true
  try {
    await client.delete('/settings/security/sessions')
    auth.logout()
    window.location.href = '/login'
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed.', { title: 'Error', danger: true })
    sessRevoking.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

const showDeleteConfirm = ref(false)
const deleteTarget      = ref<UserRecord | null>(null)
const deleting          = ref(false)

function confirmDelete(u: UserRecord) {
  deleteTarget.value = u
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await client.delete(`/users/${deleteTarget.value.id}`)
    showDeleteConfirm.value = false
    await fetchUsers()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to delete user')
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.admin-users {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: var(--space-5, 20px);
  min-height: 100%;
  max-width: 1100px;
}

/* ── Header ─────────────────────────────────────────────────────────────────── */
.au-header { display: flex; align-items: center; justify-content: space-between; }
.au-header-left { display: flex; align-items: baseline; gap: 10px; }
.au-title { font-size: var(--fs-2xl, 22px); font-weight: 800; color: var(--text); margin: 0; }
.au-count { font-size: var(--fs-sm, 12px); color: var(--muted); }
.au-add-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm, 6px); font-size: 13px;
  font-weight: 600; cursor: pointer; transition: all var(--transition);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light);
}
.au-add-btn:hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }

/* ── Loading ────────────────────────────────────────────────────────────────── */
.au-loading { display: flex; justify-content: center; padding: var(--space-12, 48px); }
.spin-svg { animation: spin 1.2s linear infinite; }

/* ── Table ──────────────────────────────────────────────────────────────────── */
.au-table-wrap { overflow-x: auto; }
.au-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px; color: var(--text);
}
.au-table th {
  text-align: left; font-size: var(--fs-xs, 10px); font-weight: 700;
  text-transform: uppercase; letter-spacing: .7px; color: var(--muted);
  padding: 8px 14px; border-bottom: 1px solid var(--glass-border);
  white-space: nowrap;
}
.au-row { transition: background var(--transition); }
.au-row:hover { background: rgba(255,255,255,.03); }
.au-row--disabled { opacity: .5; }
.au-row--me td:first-child { border-left: 2px solid var(--pl, #7c3aed); }
.au-row td { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,.04); vertical-align: middle; }

/* User cell */
.au-cell-user { display: flex; align-items: center; gap: 10px; }
.au-avatar {
  width: 34px; height: 34px; border-radius: 50%; overflow: hidden;
  flex-shrink: 0; background: rgba(var(--pl-rgb, 124,58,237), .2);
  display: flex; align-items: center; justify-content: center;
}
.au-avatar-img { width: 100%; height: 100%; object-fit: cover; }
.au-avatar-initials { font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--pl, #a78bfa); }
.au-user-info { display: flex; flex-direction: column; gap: 1px; }
.au-username { font-size: 13px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 6px; }
.au-email { font-size: 11px; color: var(--muted); }
.me-badge {
  font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: var(--radius-sm, 8px);
  background: rgba(var(--pl-rgb, 124,58,237), .2); color: var(--pl, #a78bfa);
}

/* Role selector */
.au-role-sel {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--text); border-radius: 6px; padding: 4px 8px;
  font-size: var(--fs-sm, 12px); cursor: pointer;
}
.au-role-sel:disabled { opacity: .4; cursor: not-allowed; }

/* Toggle button */
.au-toggle-btn {
  font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 10px;
  cursor: pointer; border: 1px solid; transition: all var(--transition);
  color: var(--muted); background: rgba(255,255,255,.04); border-color: rgba(255,255,255,.1);
}
.au-toggle-btn.active { color: #4ade80; background: rgba(74,222,128,.1); border-color: rgba(74,222,128,.3); }
.au-toggle-btn:disabled { opacity: .3; cursor: not-allowed; }

/* Permission chips */
.au-perms { display: flex; gap: var(--space-1, 4px); flex-wrap: wrap; }
.perm-chip {
  font-size: var(--fs-xs, 10px); font-weight: 600; padding: 3px 9px; border-radius: 10px;
  cursor: pointer; border: 1px solid; transition: all var(--transition);
  color: rgba(255,255,255,.55); background: rgba(255,255,255,.05); border-color: rgba(255,255,255,.1);
}
.perm-chip.denied  { color: #f87171; background: rgba(239,68,68,.1); border-color: rgba(239,68,68,.3); text-decoration: line-through; }
.perm-chip.granted { color: #4ade80; background: rgba(74,222,128,.1); border-color: rgba(74,222,128,.3); }
.perm-chip:disabled { opacity: .3; cursor: not-allowed; }

/* Date */
.au-cell-date { font-size: 11px; color: var(--muted); white-space: nowrap; }

/* Row actions */
.au-row-actions { display: flex; gap: var(--space-1, 4px); }
.au-icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08);
  color: var(--muted); cursor: pointer; transition: all var(--transition);
}
.au-icon-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.au-icon-btn--danger:hover { background: rgba(239,68,68,.15); color: #f87171; border-color: rgba(239,68,68,.3); }
.au-icon-btn:disabled { opacity: .3; cursor: not-allowed; }

/* ── Dialogs ─────────────────────────────────────────────────────────────────── */
.au-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  backdrop-filter: blur(6px); display: flex; align-items: center;
  justify-content: center; z-index: 9000;
}
.au-dialog {
  width: 420px; max-width: 95vw; border-radius: 14px; overflow: hidden;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
.au-dialog--danger { border-color: rgba(239,68,68,.3); }
.au-dlg-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--glass-border);
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.dlg-close { background: none; border: none; color: var(--muted); font-size: 20px; cursor: pointer; padding: 0 4px; }
.au-dlg-body { padding: var(--space-5, 20px); display: flex; flex-direction: column; gap: 10px; }
.au-label { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: -4px; }
.au-input {
  background: color-mix(in srgb, var(--pl) 8%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--text); border-radius: var(--radius-sm, 6px); padding: 8px 12px;
  font-size: 13px; width: 100%; box-sizing: border-box;
}
.au-input:focus { outline: none; border-color: color-mix(in srgb, var(--pl) 50%, transparent); }
.au-dlg-error { padding: 0 20px 8px; font-size: var(--fs-sm, 12px); color: #f87171; }
.au-dlg-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: var(--space-2, 8px);
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
}
.au-ghost-btn {
  background: none; border: 1px solid var(--glass-border); color: var(--muted);
  padding: 8px 16px; border-radius: var(--radius-sm, 6px); font-size: 13px; cursor: pointer;
  transition: all var(--transition);
}
.au-ghost-btn:hover { background: rgba(255,255,255,.06); color: var(--text); }
.au-submit-btn {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  padding: 8px 16px; border-radius: var(--radius-sm, 6px);
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: var(--space-2, 8px);
  transition: all var(--transition);
}
.au-submit-btn:disabled { opacity: .5; cursor: not-allowed; }
.au-danger-btn {
  background: rgba(239,68,68,.15); color: #f87171;
  border: 1px solid rgba(239,68,68,.3);
  padding: 8px 16px; border-radius: var(--radius-sm, 6px);
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: var(--space-2, 8px);
  transition: all var(--transition);
}
.au-danger-btn:hover { background: rgba(239,68,68,.25); border-color: rgba(239,68,68,.5); }
.au-danger-btn:disabled { opacity: .5; }

/* ── Active Sessions section ─────────────────────────────────────────────────── */
.au-section {
  display: flex; flex-direction: column; gap: 14px;
  border: 1px solid var(--glass-border); border-radius: var(--radius);
  padding: 14px 16px;
}
.au-section-header {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-2, 8px);
}
.au-section-title {
  font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); margin: 0;
}
.au-section-actions { display: flex; align-items: center; gap: var(--space-2, 8px); }
.au-sess-empty {
  font-size: 13px; color: var(--muted); padding: 12px 0;
}
.au-pagination { display: flex; align-items: center; justify-content: center; gap: var(--space-3, 12px); margin-top: 10px; }
.au-page-btn { padding: 4px 12px; border-radius: var(--radius-xs, 4px); border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent); background: color-mix(in srgb, var(--pl) 12%, transparent); color: var(--text); font-size: 13px; cursor: pointer; }
.au-page-btn:disabled { opacity: .3; cursor: not-allowed; }
.au-page-btn:hover:not(:disabled) { background: rgba(255,255,255,.08); }
.au-page-info { font-size: var(--fs-sm, 12px); color: var(--muted); }
.au-sess-dot-cell { width: 24px; text-align: center; }
.au-sess-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: rgba(255,255,255,.2);
}
.au-sess-dot--current { background: #4ade80; box-shadow: 0 0 6px rgba(74,222,128,.6); }
.au-sess-row--current { background: rgba(74,222,128,.04); }
.au-sess-browser { font-size: 13px; color: var(--text); }
.au-sess-badge {
  display: inline-block; margin-left: 8px;
  font-size: var(--fs-xs, 10px); font-weight: 700; padding: 2px 7px; border-radius: var(--radius-sm, 8px);
  background: rgba(var(--pl-rgb, 124,58,237), .2); color: var(--pl-light, #a78bfa);
}
.au-cell-mono { font-size: var(--fs-sm, 12px); color: var(--muted); font-family: monospace; white-space: nowrap; }

/* ── Spinner ─────────────────────────────────────────────────────────────────── */
.btn-spinner {
  width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
