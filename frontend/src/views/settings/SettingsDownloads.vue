<template>
  <div class="sd-root">

    <!-- ── Header ────────────────────────────────────────────────────────────── -->
    <div class="sd-header">
      <div class="sd-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </div>
      <div>
        <div class="sd-title">{{ t('downloads.title') }}</div>
        <div class="sd-subtitle">{{ t('downloads.subtitle') }}</div>
      </div>
    </div>

    <!-- ── Section: Download Tokens ─────────────────────────────────────────── -->
    <div class="sd-section">
      <div class="sd-section-title sd-section-title--collapsible" @click="toggleSection('tokens')">
        <span>{{ t('downloads.tokens') }}</span>
        <svg class="sd-chevron" :class="{ 'sd-chevron--open': !collapsed.tokens }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.tokens">
      <div class="sd-section-actions-row">
        <button class="action-btn action-btn--ghost action-btn--sm" @click="loadTokens" :disabled="loading">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          {{ t('downloads.refresh') }}
        </button>
        <button class="action-btn action-btn--primary action-btn--sm" @click="showCreate = !showCreate">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          {{ t('downloads.new_token') }}
        </button>
      </div>

      <!-- ── Create form ──────────────────────────────────────────────────────── -->
      <div v-if="showCreate" class="sd-create-panel">
        <div class="sd-create-title">{{ t('downloads.create_title') }}</div>

        <div class="fields-grid">

          <!-- File selector -->
          <div class="field-group field-group--wide"
            @mouseenter="setHint(t('dhint.file_title'), t('dhint.file_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('downloads.file') }}</label>
            <div class="field-hint">{{ t('downloads.file_hint') }}</div>
            <div v-if="filesLoading" class="sd-files-loading">
              <span class="spinner" /> {{ t('downloads.loading_files') }}
            </div>
            <select v-else v-model.number="form.file_id" class="field-input">
              <option :value="null" disabled>{{ t('downloads.select_file') }}</option>
              <optgroup v-for="(files, title) in filesByGame" :key="title" :label="title">
                <option v-for="f in files" :key="f.file_id" :value="f.file_id">
                  {{ f.filename }}
                  <template v-if="f.os !== 'all'"> [{{ f.os }}]</template>
                  <template v-if="f.size_bytes"> · {{ fmtSize(f.size_bytes) }}</template>
                </option>
              </optgroup>
            </select>
          </div>

          <!-- Expiry -->
          <div class="field-group"
            @mouseenter="setHint(t('dhint.expires_title'), t('dhint.expires_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('downloads.expires_in') }}</label>
            <div class="field-hint">{{ t('downloads.expires_hint') }}</div>
            <input v-model.number="form.expires_in_hours" type="number" min="1" class="field-input" placeholder="e.g. 24" />
          </div>

          <!-- Max downloads -->
          <div class="field-group"
            @mouseenter="setHint(t('dhint.max_title'), t('dhint.max_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('downloads.max_downloads') }}</label>
            <div class="field-hint">{{ t('downloads.max_hint') }}</div>
            <input v-model.number="form.max_downloads" type="number" min="1" class="field-input" placeholder="e.g. 1" />
          </div>

          <!-- Password -->
          <div class="field-group"
            @mouseenter="setHint(t('dhint.password_title'), t('dhint.password_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('downloads.password') }}</label>
            <div class="field-hint">{{ t('downloads.password_hint') }}</div>
            <input v-model="form.password" type="password" class="field-input" autocomplete="new-password" placeholder="••••••••" />
          </div>

          <!-- Note -->
          <div class="field-group"
            @mouseenter="setHint(t('dhint.note_title'), t('dhint.note_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('downloads.note') }}</label>
            <div class="field-hint">{{ t('downloads.note_hint') }}</div>
            <input v-model="form.note" type="text" class="field-input" placeholder="e.g. for John" maxlength="256" />
          </div>

        </div>

        <div v-if="createError" class="field-server-error">{{ createError }}</div>

        <div class="sd-create-actions">
          <button class="action-btn action-btn--ghost" @click="cancelCreate">{{ t('common.cancel') }}</button>
          <button class="action-btn action-btn--primary" :disabled="creating || !form.file_id" @click="createToken">
            <span v-if="creating" class="spinner" />
            {{ t('downloads.create_token') }}
          </button>
        </div>
      </div>

      <!-- ── Created link popup ───────────────────────────────────────────────── -->
      <div v-if="newTokenUrl" class="sd-token-created">
        <div class="sd-token-created-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {{ t('downloads.token_created') }}
        </div>
        <div class="sd-token-url-row">
          <code class="sd-token-url">{{ newTokenUrl }}</code>
          <button class="action-btn action-btn--ghost action-btn--sm" @click="copyNewUrl">
            {{ newUrlCopied ? t('downloads.copied') : t('downloads.copy') }}
          </button>
        </div>
        <button class="action-btn action-btn--ghost action-btn--sm sd-token-dismiss" @click="newTokenUrl = ''">
          {{ t('downloads.dismiss') }}
        </button>
      </div>

      <!-- ── Table ────────────────────────────────────────────────────────────── -->
      <div v-if="loading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>

      <template v-else>
        <div v-if="tokens.length === 0" class="sd-empty">{{ t('downloads.no_tokens') }}</div>

        <div v-else class="sd-table-wrap">
        <table class="sd-table">
          <thead>
            <tr>
              <th>{{ t('downloads.col_file') }}</th>
              <th>{{ t('downloads.col_status') }}</th>
              <th>{{ t('downloads.col_uses') }}</th>
              <th>{{ t('downloads.col_expires') }}</th>
              <th>{{ t('downloads.col_created') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tk in tokens" :key="tk.id" :class="['sd-row', `sd-row--${tk.status}`]">
              <td class="sd-cell-file">
                <div class="sd-file-name">{{ tk.file_name }}</div>
                <div class="sd-file-meta">
                  <span v-if="tk.game_title">{{ tk.game_title }}</span>
                  <span v-if="tk.has_password" class="sd-pw-icon" :title="t('downloads.password_protected')">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--pl-light)" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                  </span>
                  <span v-if="tk.note" class="sd-note-tag">{{ tk.note }}</span>
                </div>
              </td>
              <td>
                <span :class="['sd-badge', `sd-badge--${tk.status}`]">{{ tk.status }}</span>
              </td>
              <td class="sd-cell-mono">
                {{ tk.download_count }}<span v-if="tk.max_downloads !== null">/{{ tk.max_downloads }}</span><span v-else>/∞</span>
              </td>
              <td class="sd-cell-mono">
                <span v-if="tk.expires_at">{{ fmtDateTime(tk.expires_at) }}</span>
                <span v-else class="sd-muted">{{ t('downloads.never') }}</span>
              </td>
              <td class="sd-cell-mono">{{ fmtDate(tk.created_at) }}</td>
              <td class="sd-cell-actions">
                <button class="action-btn action-btn--ghost action-btn--sm" @click="copyTokenUrl(tk.token)">
                  {{ copied === tk.token ? t('downloads.copied') : t('downloads.copy_link') }}
                </button>
                <button class="action-btn action-btn--danger action-btn--sm" @click="deleteToken(tk.id)">
                  {{ t('common.delete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        </div><!-- /sd-table-wrap -->
      </template>
      </div><!-- /v-show tokens -->
    </div>

    <!-- ── Section: Speed Limits ─────────────────────────────────────────────── -->
    <div class="sd-section">
      <div class="sd-section-title sd-section-title--collapsible" @click="toggleSection('speed')">
        <span>{{ t('downloads.speed_limits') }}</span>
        <svg class="sd-chevron" :class="{ 'sd-chevron--open': !collapsed.speed }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.speed">
      <div v-if="speedLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>

        <!-- Global limit -->
        <div class="field-group sd-speed-global"
          @mouseenter="setHint(t('dhint.global_speed_title'), t('dhint.global_speed_body'))"
          @mouseleave="clearHint()">
          <label class="field-label">{{ t('downloads.global_limit') }}</label>
          <div class="field-hint">{{ t('downloads.global_limit_hint') }}</div>
          <div class="sd-speed-input-row">
            <input v-model.number="speedDisplay.global_mbps" type="number" min="0" step="0.5" class="field-input sd-speed-input" placeholder="0" />
            <span class="sd-speed-equiv sd-speed-unlimited" v-if="!speedDisplay.global_mbps">{{ t('downloads.unlimited') }}</span>
          </div>
        </div>

        <!-- Per-user overrides -->
        <div class="sd-speed-users-label"
          @mouseenter="setHint(t('dhint.per_user_title'), t('dhint.per_user_body'))"
          @mouseleave="clearHint()">
          {{ t('downloads.per_user') }}
        </div>

        <div v-if="users.length === 0" class="sd-empty">{{ t('downloads.no_users') }}</div>
        <div v-else class="sd-speed-user-list">
          <div v-for="u in users" :key="u.username" class="sd-speed-user-row">
            <span class="sd-speed-username">{{ u.username }}</span>
            <span class="sd-speed-role">{{ u.role }}</span>
            <div class="sd-speed-input-row">
              <input
                type="number" min="0" step="0.5"
                class="field-input sd-speed-input"
                :placeholder="t('downloads.zero_global')"
                :value="speedDisplay.user_mbps[u.username] ?? 0"
                @input="setUserSpeed(u.username, ($event.target as HTMLInputElement).valueAsNumber)"
              />
              <span class="sd-speed-equiv sd-speed-global-label" v-if="!(speedDisplay.user_mbps[u.username] ?? 0)">{{ t('downloads.global_label') }}</span>
            </div>
          </div>
        </div>

        <div v-if="speedError" class="field-server-error">{{ speedError }}</div>
        <div v-if="speedSaved" class="field-ok">{{ t('downloads.speed_saved') }}</div>
        <div class="sd-actions">
          <button class="action-btn action-btn--primary" :disabled="speedSaving" @click="saveSpeed">
            <span v-if="speedSaving" class="spinner" />
            {{ t('common.save') }}
          </button>
        </div>

      </template>
      </div><!-- /v-show speed -->
    </div>

    <!-- ── Section: Transmission ─────────────────────────────────────────────── -->
    <div class="sd-section">
      <div class="sd-section-title sd-section-title--collapsible" @click="toggleSection('transmission')">
        <div class="sd-tr-title-row">
          <span>{{ t('transmission.title') }}</span>
          <span v-if="tr.enabled" :class="['sd-badge', trOnline ? 'sd-badge--active' : 'sd-badge--expired']" style="margin-left:10px; text-transform:lowercase;">
            {{ trOnline ? t('transmission.online') : t('transmission.offline') }}
          </span>
        </div>
        <svg class="sd-chevron" :class="{ 'sd-chevron--open': !collapsed.transmission }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.transmission">
        <div v-if="trLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
        <template v-else>

          <!-- Enable -->
          <div class="sd-tr-row"
            @mouseenter="setHint(t('thint.tr_enable_title'), t('thint.tr_enable_body'))"
            @mouseleave="clearHint()">
            <div>
              <div class="field-label">{{ t('transmission.enable') }}</div>
              <div class="field-hint">{{ t('transmission.enable_hint') }}</div>
            </div>
            <label class="sd-toggle">
              <input type="checkbox" v-model="tr.enabled" />
              <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
            </label>
          </div>

          <template v-if="tr.enabled">
            <!-- Peer port -->
            <div class="sd-tr-group-label">{{ t('transmission.networking') }}</div>
            <div class="sd-tr-fields">

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_port_title'), t('thint.tr_port_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.peer_port') }}</label>
                <div class="field-hint">{{ t('transmission.peer_port_hint') }}</div>
                <input v-model.number="tr.peer_port" type="number" min="1024" max="65535" class="field-input" />
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_random_title'), t('thint.tr_random_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.random_port') }}</label>
                <div class="field-hint">{{ t('transmission.random_port_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.peer_port_random" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_upnp_title'), t('thint.tr_upnp_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.upnp') }}</label>
                <div class="field-hint">{{ t('transmission.upnp_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.port_forwarding_enabled" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_hostname_title'), t('thint.tr_hostname_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.hostname') }}</label>
                <div class="field-hint">{{ t('transmission.hostname_hint') }}</div>
                <input v-model="tr.announce_ip" class="field-input" placeholder="e.g. 192.168.1.100 or my.domain.com" maxlength="255" />
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_dht_title'), t('thint.tr_dht_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.dht') }}</label>
                <div class="field-hint">{{ t('transmission.dht_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.dht_enabled" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_utp_title'), t('thint.tr_utp_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.utp') }}</label>
                <div class="field-hint">{{ t('transmission.utp_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.utp_enabled" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_lpd_title'), t('thint.tr_lpd_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.lpd') }}</label>
                <div class="field-hint">{{ t('transmission.lpd_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.lpd_enabled" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

            </div><!-- /sd-tr-fields -->

            <!-- Speed limits -->
            <div class="sd-tr-group-label">{{ t('transmission.speed_limits') }}</div>
            <div class="sd-tr-fields">

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_dl_speed_title'), t('thint.tr_dl_speed_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.limit_download') }}</label>
                <div class="field-hint">{{ t('transmission.limit_download_hint') }}</div>
                <div class="sd-speed-input-row">
                  <label class="sd-toggle sd-toggle--inline">
                    <input type="checkbox" v-model="tr.speed_limit_down_enabled" />
                    <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                  </label>
                  <input v-model.number="tr.speed_limit_down" type="number" min="0"
                    class="field-input sd-speed-input" :disabled="!tr.speed_limit_down_enabled" placeholder="KB/s" />
                </div>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_ul_speed_title'), t('thint.tr_ul_speed_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.limit_upload') }}</label>
                <div class="field-hint">{{ t('transmission.limit_upload_hint') }}</div>
                <div class="sd-speed-input-row">
                  <label class="sd-toggle sd-toggle--inline">
                    <input type="checkbox" v-model="tr.speed_limit_up_enabled" />
                    <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                  </label>
                  <input v-model.number="tr.speed_limit_up" type="number" min="0"
                    class="field-input sd-speed-input" :disabled="!tr.speed_limit_up_enabled" placeholder="KB/s" />
                </div>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_ratio_title'), t('thint.tr_ratio_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.ratio_limit') }}</label>
                <div class="field-hint">{{ t('transmission.ratio_hint') }}</div>
                <div class="sd-speed-input-row">
                  <label class="sd-toggle sd-toggle--inline">
                    <input type="checkbox" v-model="tr.ratio_limit_enabled" />
                    <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                  </label>
                  <input v-model.number="tr.ratio_limit" type="number" min="0" step="0.1"
                    class="field-input sd-speed-input" :disabled="!tr.ratio_limit_enabled" placeholder="e.g. 2.0" />
                </div>
              </div>

            </div><!-- /sd-tr-fields -->

            <!-- Advanced -->
            <div class="sd-tr-group-label">{{ t('transmission.advanced') }}</div>
            <div class="sd-tr-fields">

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_trash_title'), t('thint.tr_trash_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.trash_torrent') }}</label>
                <div class="field-hint">{{ t('transmission.trash_hint') }}</div>
                <label class="sd-toggle sd-toggle--inline">
                  <input type="checkbox" v-model="tr.trash_original" />
                  <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
                </label>
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_log_title'), t('thint.tr_log_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.log_verbosity') }}</label>
                <div class="field-hint">{{ t('transmission.log_hint') }}</div>
                <select v-model.number="tr.message_level" class="field-input">
                  <option :value="0">{{ t('transmission.log_silent') }}</option>
                  <option :value="1">{{ t('transmission.log_errors') }}</option>
                  <option :value="2">{{ t('transmission.log_info') }}</option>
                  <option :value="3">{{ t('transmission.log_debug') }}</option>
                </select>
              </div>

            </div><!-- /sd-tr-fields -->
          </template><!-- /v-if tr.enabled -->

          <div v-if="trError" class="field-server-error">{{ trError }}</div>
          <div v-if="trSaved" class="field-ok">{{ t('transmission.saved') }}</div>
          <div class="sd-actions">
            <button class="action-btn action-btn--primary" :disabled="trSaving" @click="saveTransmission">
              <span v-if="trSaving" class="spinner" />
              {{ t('common.save') }}
            </button>
          </div>

        </template>
      </div><!-- /v-show transmission -->
    </div>

    <!-- hint panel (rendered by parent SettingsIndex, hoisted via composable) -->
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const { setHint, clearHint } = useSettingsHint()
const { gdConfirm, gdAlert } = useDialog()

// ── State ─────────────────────────────────────────────────────────────────────

interface TokenEntry {
  id:             number
  token:          string
  file_id:        number
  file_name:      string
  game_title:     string | null
  created_by:     string
  created_at:     string
  expires_at:     string | null
  max_downloads:  number | null
  download_count: number
  has_password:   boolean
  note:           string | null
  is_active:      boolean
  status:         'active' | 'expired' | 'exhausted' | 'revoked'
}

interface FileEntry {
  file_id:    number
  filename:   string
  game_title: string
  os:         string
  file_type:  string
  size_bytes: number | null
}

const tokens      = ref<TokenEntry[]>([])
const loading     = ref(true)
const showCreate  = ref(false)
const creating    = ref(false)
const createError = ref('')
const newTokenUrl = ref('')
const newUrlCopied= ref(false)
const copied      = ref<string | null>(null)

const files       = ref<FileEntry[]>([])
const filesLoading= ref(false)

const form = reactive({
  file_id:          null as number | null,
  expires_in_hours: null as number | null,
  max_downloads:    null as number | null,
  password:         '',
  note:             '',
})

// ── Computed ──────────────────────────────────────────────────────────────────

const filesByGame = computed(() => {
  const map: Record<string, FileEntry[]> = {}
  for (const f of files.value) {
    const key = f.game_title || 'Unknown'
    if (!map[key]) map[key] = []
    map[key].push(f)
  }
  return map
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDateTime(iso: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function fmtDate(iso: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'short' })
}

function fmtSize(bytes: number): string {
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB'
  if (bytes >= 1048576)    return (bytes / 1048576).toFixed(0) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

function tokenUrl(token: string): string {
  return `${window.location.origin}/dl/${token}`
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadTokens() {
  loading.value = true
  try {
    const r = await client.get('/settings/downloads/tokens')
    tokens.value = r.data
  } catch { /* ignore */ } finally {
    loading.value = false
  }
}

async function loadFiles() {
  filesLoading.value = true
  try {
    const r = await client.get('/settings/downloads/tokens/files')
    files.value = r.data
  } catch { /* ignore */ } finally {
    filesLoading.value = false
  }
}

// ── CRUD ──────────────────────────────────────────────────────────────────────

async function createToken() {
  if (!form.file_id) return
  creating.value  = true
  createError.value = ''
  try {
    const r = await client.post('/settings/downloads/tokens', {
      file_id:          form.file_id,
      expires_in_hours: form.expires_in_hours || null,
      max_downloads:    form.max_downloads    || null,
      password:         form.password         || null,
      note:             form.note             || null,
    })
    newTokenUrl.value = tokenUrl(r.data.token)
    newUrlCopied.value = false
    showCreate.value   = false
    resetForm()
    await loadTokens()
  } catch (e: any) {
    createError.value = e?.response?.data?.detail || t('downloads.create_failed')
  } finally {
    creating.value = false
  }
}

async function deleteToken(id: number) {
  const ok = await gdConfirm(t('downloads.delete_confirm'), { danger: true })
  if (!ok) return
  try {
    await client.delete(`/settings/downloads/tokens/${id}`)
    await loadTokens()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || t('downloads.delete_failed'), { danger: true })
  }
}

function cancelCreate() {
  showCreate.value  = false
  createError.value = ''
  resetForm()
}

function resetForm() {
  form.file_id          = null
  form.expires_in_hours = null
  form.max_downloads    = null
  form.password         = ''
  form.note             = ''
}

// ── Clipboard ─────────────────────────────────────────────────────────────────

function _copyToClipboard(text: string): boolean {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {})
    return true
  }
  // Legacy fallback
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    return true
  } catch {
    return false
  }
}

async function copyTokenUrl(token: string) {
  const url = tokenUrl(token)
  if (_copyToClipboard(url)) {
    copied.value = token
    setTimeout(() => { copied.value = null }, 2000)
  } else {
    await gdAlert(url, { title: 'Copy this link', confirmText: 'Close' })
  }
}

async function copyNewUrl() {
  if (_copyToClipboard(newTokenUrl.value)) {
    newUrlCopied.value = true
  } else {
    await gdAlert(newTokenUrl.value, { title: 'Copy this link', confirmText: 'Close' })
  }
}

// ── Speed limits ──────────────────────────────────────────────────────────────
// UI works in MB/s; backend stores KB/s. We convert on load and save.

interface UserEntry { username: string; role: string }

const speedDisplay = reactive<{ global_mbps: number; user_mbps: Record<string, number> }>({
  global_mbps: 0,
  user_mbps: {},
})
const users       = ref<UserEntry[]>([])
const speedLoading= ref(true)
const speedSaving = ref(false)
const speedSaved  = ref(false)
const speedError  = ref('')

function setUserSpeed(username: string, val: number) {
  speedDisplay.user_mbps[username] = isNaN(val) ? 0 : Math.max(0, val)
}

async function loadSpeed() {
  speedLoading.value = true
  try {
    const [sr, ur] = await Promise.all([
      client.get('/settings/downloads/speed'),
      client.get('/users'),
    ])
    const rawKbps: number = sr.data.global_kbps ?? 0
    speedDisplay.global_mbps = rawKbps > 0 ? Math.round(rawKbps / 1024 * 100) / 100 : 0
    const rawLimits: Record<string, number> = sr.data.user_limits ?? {}
    speedDisplay.user_mbps = Object.fromEntries(
      Object.entries(rawLimits).map(([k, v]) => [k, v > 0 ? Math.round(v / 1024 * 100) / 100 : 0])
    )
    users.value = (Array.isArray(ur.data) ? ur.data : []).map((u: any) => ({ username: u.username, role: u.role }))
  } catch { /* ignore */ } finally {
    speedLoading.value = false
  }
}

async function saveSpeed() {
  speedSaving.value = true
  speedSaved.value  = false
  speedError.value  = ''
  try {
    await client.post('/settings/downloads/speed', {
      global_kbps: Math.round(speedDisplay.global_mbps * 1024),
      user_limits:  Object.fromEntries(
        Object.entries(speedDisplay.user_mbps).map(([k, v]) => [k, Math.round(v * 1024)])
      ),
    })
    speedSaved.value = true
    setTimeout(() => { speedSaved.value = false }, 3000)
  } catch (e: any) {
    speedError.value = e?.response?.data?.detail || t('downloads.speed_save_failed')
  } finally {
    speedSaving.value = false
  }
}

// ── Transmission ──────────────────────────────────────────────────────────────

interface TransmissionConfig {
  enabled:                  boolean
  peer_port:                number
  peer_port_random:         boolean
  port_forwarding_enabled:  boolean
  announce_ip:              string
  dht_enabled:              boolean
  utp_enabled:              boolean
  lpd_enabled:              boolean
  blocklist_enabled:        boolean
  speed_limit_down_enabled: boolean
  speed_limit_down:         number
  speed_limit_up_enabled:   boolean
  speed_limit_up:           number
  ratio_limit_enabled:      boolean
  ratio_limit:              number
  trash_original:           boolean
  message_level:            number
}

const tr = reactive<TransmissionConfig>({
  enabled: false, peer_port: 51413, peer_port_random: false,
  port_forwarding_enabled: false, announce_ip: '',
  dht_enabled: true, utp_enabled: true,
  lpd_enabled: false, blocklist_enabled: false,
  speed_limit_down_enabled: false, speed_limit_down: 0,
  speed_limit_up_enabled: false, speed_limit_up: 0,
  ratio_limit_enabled: false, ratio_limit: 2.0,
  trash_original: false, message_level: 1,
})
const trLoading = ref(true)
const trSaving  = ref(false)
const trSaved   = ref(false)
const trError   = ref('')
const trOnline  = ref(false)

async function loadTransmission() {
  trLoading.value = true
  try {
    const [cfgR, statusR] = await Promise.all([
      client.get('/settings/downloads/transmission'),
      client.get('/torrents/status').catch(() => ({ data: { available: false } })),
    ])
    Object.assign(tr, cfgR.data)
    trOnline.value = statusR.data?.available ?? false
  } catch { /* ignore */ } finally {
    trLoading.value = false
  }
}

async function saveTransmission() {
  trSaving.value = true
  trSaved.value  = false
  trError.value  = ''
  try {
    await client.post('/settings/downloads/transmission', { ...tr })
    trSaved.value = true
    setTimeout(() => { trSaved.value = false }, 5000)
    // Refresh online status
    const r = await client.get('/torrents/status').catch(() => ({ data: { available: false } }))
    trOnline.value = r.data?.available ?? false
  } catch (e: any) {
    trError.value = e?.response?.data?.detail || t('transmission.save_failed')
  } finally {
    trSaving.value = false
  }
}

// ── Collapse state ────────────────────────────────────────────────────────────

function _loadCollapsed(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem('sd_collapsed') || '{}') } catch { return {} }
}
const collapsed = reactive<Record<string, boolean>>(_loadCollapsed())

function toggleSection(key: string) {
  collapsed[key] = !collapsed[key]
  try { localStorage.setItem('sd_collapsed', JSON.stringify({ ...collapsed })) } catch {}
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([loadTokens(), loadFiles(), loadSpeed(), loadTransmission()])
})
</script>

<style scoped>
/* ── Root ─────────────────────────────────────────────────────────────────── */
.sd-root {
  display: flex; flex-direction: column; gap: var(--space-5, 20px);
  padding: 24px 28px; max-width: 900px;
}

/* ── Header ──────────────────────────────────────────────────────────────── */
.sd-header {
  display: flex; align-items: center; gap: 14px; padding-bottom: 16px;
  border-bottom: 1px solid var(--glass-border);
}
.sd-icon {
  width: 36px; height: 36px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 30%, transparent);
  display: flex; align-items: center; justify-content: center; color: var(--pl-light); flex-shrink: 0;
}
.sd-title    { font-size: var(--fs-lg, 16px); font-weight: 600; color: var(--text-primary); }
.sd-subtitle { font-size: var(--fs-sm, 12px); color: var(--text-muted); margin-top: 2px; }

/* ── Section ─────────────────────────────────────────────────────────────── */
.sd-section {
  display: flex; flex-direction: column; gap: var(--space-3, 12px);
  border: 1px solid var(--glass-border); border-radius: var(--radius);
  padding: 14px 16px;
}
.sd-section-title {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .5px;
}
.sd-section-title--collapsible {
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none; padding-bottom: 2px;
}
.sd-section-title--collapsible:hover { color: var(--text-primary); }
.sd-chevron { color: var(--text-muted); transition: transform .2s; }
.sd-chevron--open { transform: rotate(180deg); }
.sd-section-actions-row { display: flex; gap: var(--space-2, 8px); justify-content: flex-end; }
.sd-actions { display: flex; justify-content: flex-end; margin-top: 4px; }

/* ── Speed limits ────────────────────────────────────────────────────────── */
.sd-speed-global { max-width: 340px; margin-top: 4px; }
.sd-speed-input-row { display: flex; align-items: center; gap: 10px; }
.sd-speed-input { width: 120px !important; }
.sd-speed-equiv { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.sd-speed-unlimited { color: #4ade80; }
.sd-speed-global-label { color: var(--text-muted); }
.sd-speed-users-label {
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: .5px; margin-top: 10px; margin-bottom: 4px;
}
.sd-speed-user-list { display: flex; flex-direction: column; gap: 6px; }
.sd-speed-user-row {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 6px 10px; background: rgba(255,255,255,.02);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
}
.sd-speed-username { font-size: 13px; color: var(--text-primary); min-width: 100px; }
.sd-speed-role { font-size: 11px; color: var(--text-muted); min-width: 60px; }

.field-ok { color: #4ade80; font-size: var(--fs-sm, 12px); }

/* ── Create panel ────────────────────────────────────────────────────────── */
.sd-create-panel {
  padding: 16px 18px; border: 1px solid var(--glass-border);
  border-radius: var(--radius); background: rgba(255,255,255,.02);
  display: flex; flex-direction: column; gap: 14px;
}
.sd-create-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.sd-create-actions { display: flex; justify-content: flex-end; gap: var(--space-2, 8px); }
.sd-files-loading { display: flex; align-items: center; gap: var(--space-2, 8px); color: var(--text-muted); font-size: var(--fs-sm, 12px); padding: 8px 0; }

/* ── Created token URL ───────────────────────────────────────────────────── */
.sd-token-created {
  padding: 14px 16px; border: 1px solid rgba(74,222,128,.25);
  border-radius: var(--radius); background: rgba(74,222,128,.06);
  display: flex; flex-direction: column; gap: var(--space-2, 8px);
}
.sd-token-created-label { display: flex; align-items: center; gap: 7px; font-size: var(--fs-sm, 12px); color: #86efac; }
.sd-token-url-row { display: flex; align-items: center; gap: 10px; gap: var(--space-2, 8px); }
.sd-token-url {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 11px; font-family: monospace; color: var(--pl-light);
  background: rgba(0,0,0,.2); padding: 5px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); user-select: all;
}
.sd-token-dismiss { align-self: flex-end; }

/* ── Table ───────────────────────────────────────────────────────────────── */
.sd-table-wrap { overflow-x: auto; }
.sd-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm, 12px); min-width: 560px; }
.sd-table th {
  text-align: left; padding: 7px 10px; font-size: var(--fs-xs, 10px); font-weight: 700;
  color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px;
  border-bottom: 1px solid var(--glass-border); white-space: nowrap;
}
.sd-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.04); vertical-align: middle; }
.sd-row--expired   td, .sd-row--exhausted td, .sd-row--revoked td { opacity: .55; }
.sd-cell-file { max-width: 220px; }
.sd-file-name { color: var(--text-primary); font-size: var(--fs-sm, 12px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 210px; }
.sd-file-meta { display: flex; align-items: center; gap: 6px; margin-top: 2px; flex-wrap: wrap; }
.sd-file-meta > span:first-child { color: var(--text-muted); font-size: 11px; }
.sd-pw-icon { display: inline-flex; align-items: center; }
.sd-note-tag {
  font-size: var(--fs-xs, 10px); color: var(--pl-light);
  background: color-mix(in srgb, var(--pl) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 20%, transparent);
  padding: 1px 6px; border-radius: var(--radius-xs, 4px);
}
.sd-cell-mono { font-family: monospace; font-size: 11px; color: var(--text-secondary); white-space: nowrap; }
.sd-cell-actions { display: flex; gap: 6px; align-items: center; white-space: nowrap; }
.sd-muted { color: var(--text-muted); }

/* ── Status badges ───────────────────────────────────────────────────────── */
.sd-badge {
  display: inline-block; padding: 2px 7px; border-radius: 99px;
  font-size: var(--fs-xs, 10px); font-weight: 600; text-transform: uppercase; letter-spacing: .4px;
}
.sd-badge--active   { background: rgba(74,222,128,.15);  color: #4ade80; border: 1px solid rgba(74,222,128,.3); }
.sd-badge--expired  { background: rgba(107,114,128,.15); color: #9ca3af; border: 1px solid rgba(107,114,128,.3); }
.sd-badge--exhausted{ background: rgba(251,191,36,.15);  color: #fbbf24; border: 1px solid rgba(251,191,36,.3); }
.sd-badge--revoked  { background: rgba(239,68,68,.15);   color: #ef4444; border: 1px solid rgba(239,68,68,.3); }

/* ── Transmission ────────────────────────────────────────────────────────── */
.sd-tr-title-row { display: flex; align-items: center; }
.sd-tr-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--glass-border); margin-bottom: 10px;
}
.sd-tr-group-label {
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: .5px;
  margin-top: 14px; margin-bottom: 6px;
}
.sd-tr-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px; margin-bottom: 4px;
}

/* Toggle switch */
.sd-toggle { position: relative; display: inline-flex; cursor: pointer; }
.sd-toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.sd-toggle-track {
  width: 36px; height: 20px; border-radius: 10px;
  background: rgba(255,255,255,.1); border: 1px solid var(--glass-border);
  transition: background .2s; flex-shrink: 0;
}
.sd-toggle input:checked ~ .sd-toggle-track { background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1)); border-color: color-mix(in srgb, var(--pl) 50%, transparent); }
.sd-toggle-thumb {
  position: absolute; top: 3px; left: 3px;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--text-muted); transition: transform .2s, background .2s;
}
.sd-toggle input:checked ~ .sd-toggle-track .sd-toggle-thumb {
  transform: translateX(16px); background: #fff;
}
.sd-toggle--inline { align-items: center; margin-top: 8px; }

/* ── Misc ────────────────────────────────────────────────────────────────── */
.sd-loading { display: flex; align-items: center; gap: var(--space-2, 8px); color: var(--text-muted); font-size: 13px; padding: 16px 0; }
.sd-empty   { color: var(--text-muted); font-size: 13px; padding: 16px 0; }

/* ── Shared form classes (mirror SettingsSecurity) ───────────────────────── */
.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}
.field-group        { display: flex; flex-direction: column; gap: 5px; }
.field-group--wide  { grid-column: 1 / -1; }
.field-label        { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .4px; }
.field-hint         { font-size: 11px; color: var(--text-muted); }
.field-input {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 7px 10px;
  color: var(--text-primary); font-size: 13px; outline: none;
  transition: border-color var(--transition); width: 100%; box-sizing: border-box;
}
.field-input:focus  { border-color: var(--pl); }
.field-server-error { color: #f87171; font-size: var(--fs-sm, 12px); }

.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 600; cursor: pointer; border: 1px solid var(--glass-border);
  font-family: inherit; transition: all var(--transition);
  background: rgba(255,255,255,.05); color: var(--muted);
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.action-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.action-btn--primary { background: color-mix(in srgb, var(--pl) 20%, transparent); color: var(--pl-light); opacity: .6; border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); }
.action-btn--primary:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }
.action-btn--ghost   { background: rgba(255,255,255,.05); color: var(--text-secondary); border: 1px solid var(--glass-border); }
.action-btn--ghost:not(:disabled):hover   { background: rgba(255,255,255,.1); }
.action-btn--danger  { background: rgba(239,68,68,.15); color: #f87171; border: 1px solid rgba(239,68,68,.3); }
.action-btn--danger:not(:disabled):hover  { background: rgba(239,68,68,.28); }
.action-btn--sm { padding: 4px 10px; font-size: 11px; }

.spinner {
  width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor; border-radius: 50%;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
