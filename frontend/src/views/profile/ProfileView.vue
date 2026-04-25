<template>
  <div class="pv-root">

    <!-- ── Header ──────────────────────────────────────────────────────────── -->
    <div class="pv-header">
      <button class="pv-back-btn" @click="router.back()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        {{ t('common.back') }}
      </button>
      <h1 class="pv-title">{{ t('profile.title') }}</h1>
    </div>

    <!-- ── Tabs ────────────────────────────────────────────────────────────── -->
    <div class="pv-tabs">
      <button class="pv-tab" :class="{ active: tab === 'account' }" @click="tab = 'account'">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
        {{ t('profile.account') }}
      </button>
      <button class="pv-tab" :class="{ active: tab === 'security' }" @click="tab = 'security'">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
        {{ t('profile.security') }}
      </button>
      <button class="pv-tab" :class="{ active: tab === 'saves' }" @click="tab = 'saves'; loadSavesIfNeeded()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
          <polyline points="17 21 17 13 7 13 7 21"/>
          <polyline points="7 3 7 8 15 8"/>
        </svg>
        {{ t('profile.game_saves', 'Game Saves') }}
      </button>
    </div>

    <div class="pv-body">
      <div class="pv-content">

      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <!-- ACCOUNT TAB                                                           -->
      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <template v-if="tab === 'account'">

        <!-- Language -->
        <div class="pv-section">
          <div class="pv-section-title">{{ t('profile.language') }}</div>
          <div class="pv-lang-row">
            <select class="pv-lang-select" :value="locale" @change="setLocale(($event.target as HTMLSelectElement).value)">
              <option v-for="lang in SUPPORTED" :key="lang.code" :value="lang.code">{{ lang.flag }} {{ lang.name }}</option>
            </select>
          </div>
        </div>

        <!-- Avatar -->
        <div class="pv-section">
          <div class="pv-section-title">{{ t('profile.avatar') }}</div>
          <div class="pv-avatar-row">
            <div class="pv-avatar-wrap" @click="triggerAvatarUpload" :title="t('profile.click_change_avatar')">
              <img v-if="avatarUrl" :src="avatarUrl" class="pv-avatar" alt="Avatar" @error="avatarUrl = ''" />
              <div v-else class="pv-avatar-placeholder">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.4">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </div>
              <div class="pv-avatar-overlay">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                <span>Change</span>
              </div>
              <div v-if="avatarUploading" class="pv-avatar-uploading">
                <span class="spinner" />
              </div>
            </div>
            <input
              ref="fileInput"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              style="display:none"
              @change="uploadAvatar"
            />
            <div class="pv-avatar-info">
              <div class="pv-avatar-name">{{ user?.username || '-' }}</div>
              <div class="pv-avatar-sub">{{ user?.email || 'No email set' }}</div>
              <div class="pv-avatar-hint">PNG, JPG, GIF, WEBP · max 5 MB</div>
            </div>
          </div>
          <div v-if="avatarMsg" class="pv-msg" :class="avatarOk ? 'pv-msg--ok' : 'pv-msg--err'">{{ avatarMsg }}</div>
        </div>

        <!-- User details -->
        <div class="pv-section">
          <div class="pv-section-title">{{ t('profile.account_details') }}</div>
          <div class="pv-details-table">
            <div class="pv-detail-row">
              <span class="pv-detail-label">{{ t('profile.username') }}</span>
              <span class="pv-detail-value">{{ user?.username || '-' }}</span>
            </div>
            <div class="pv-detail-row">
              <span class="pv-detail-label">{{ t('profile.email') }}</span>
              <span class="pv-detail-value">{{ user?.email || '-' }}</span>
            </div>
            <div class="pv-detail-row">
              <span class="pv-detail-label">{{ t('profile.role') }}</span>
              <span class="pv-detail-value">
                <span class="pv-role-badge" :class="`pv-role--${(user?.role || 'viewer').toLowerCase()}`">
                  {{ user?.role || 'Viewer' }}
                </span>
              </span>
            </div>
            <div class="pv-detail-row">
              <span class="pv-detail-label">{{ t('profile.member_since') }}</span>
              <span class="pv-detail-value">{{ formatDate(user?.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- Library Stats -->
        <div class="pv-section" v-if="libraryCount > 0">
          <div class="pv-section-title">{{ t('profile.library_stats') }}</div>
          <div class="pv-stats-grid">
            <div class="pv-stat-card">
              <div class="pv-stat-val">{{ libraryCount }}</div>
              <div class="pv-stat-lbl">{{ t('profile.games_in_library') }}</div>
            </div>
            <div class="pv-stat-card">
              <div class="pv-stat-val">{{ downloadedCount }}</div>
              <div class="pv-stat-lbl">{{ t('profile.downloaded') }}</div>
            </div>
            <div v-if="favoriteGenre" class="pv-stat-card">
              <div class="pv-stat-val pv-stat-val--genre">{{ favoriteGenre }}</div>
              <div class="pv-stat-lbl">{{ t('profile.favorite_genre') }}</div>
            </div>
          </div>
        </div>

        <!-- GOG Account (hidden for admin - admin uses Settings > GOG) -->
        <div v-if="!isAdmin" class="pv-section">
          <div class="pv-section-title">{{ t('profile.gog_account') }}</div>

          <div v-if="gogLoading" class="pv-gog-loading">
            <span class="spinner" />
          </div>

          <!-- Connected state -->
          <div v-else-if="gogStatus?.authenticated" class="pv-gog-connected">

            <!-- Profile card -->
            <div class="sg-profile-card">
              <div class="sg-avatar-wrap">
                <img
                  v-if="gogStatus.avatar_url"
                  :src="gogStatus.avatar_url"
                  class="sg-avatar"
                  alt="GOG avatar"
                  @error="gogStatus!.avatar_url = ''"
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
                <div class="sg-username">{{ gogStatus.username }}</div>
                <div class="sg-sub">Connected GOG account</div>
              </div>
              <button class="sg-disconnect-btn" @click="disconnectGog">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/>
                </svg>
                Disconnect
              </button>
            </div>

            <!-- Details table -->
            <div class="sg-details">
              <div v-if="gogStatus.email" class="sg-detail-row">
                <span class="sg-detail-label">Email</span>
                <span class="sg-detail-value">{{ gogStatus.email }}</span>
              </div>
              <div class="sg-detail-row">
                <span class="sg-detail-label">GOG User ID</span>
                <span class="sg-detail-value sg-mono">{{ gogStatus.user_id || '-' }}</span>
              </div>
              <div v-if="gogStatus.country" class="sg-detail-row">
                <span class="sg-detail-label">Country</span>
                <span class="sg-detail-value">{{ gogStatus.country }}</span>
              </div>
              <div v-if="gogStatus.created_date" class="sg-detail-row">
                <span class="sg-detail-label">GOG member since</span>
                <span class="sg-detail-value">{{ formatDate(gogStatus.created_date) }}</span>
              </div>
              <div v-if="gogStatus.games_count !== undefined && gogStatus.games_count !== null" class="sg-detail-row">
                <span class="sg-detail-label">GOG games owned</span>
                <span class="sg-detail-value"><span class="sg-count">{{ gogStatus.games_count }}</span></span>
              </div>
              <div v-if="gogStatus.movies_count !== undefined && gogStatus.movies_count !== null && gogStatus.movies_count > 0" class="sg-detail-row">
                <span class="sg-detail-label">GOG movies owned</span>
                <span class="sg-detail-value"><span class="sg-count">{{ gogStatus.movies_count }}</span></span>
              </div>
              <div class="sg-detail-row">
                <span class="sg-detail-label">Games in library</span>
                <span class="sg-detail-value">
                  <span v-if="gogStatus.game_count !== undefined" class="sg-count">{{ gogStatus.game_count }}</span>
                  <span v-else>-</span>
                </span>
              </div>
              <div class="sg-detail-row">
                <span class="sg-detail-label">Token expires</span>
                <span class="sg-detail-value">{{ formatExpiry(gogStatus.expires_at) }}</span>
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
                  <div class="sg-section-title">Library sync</div>
                  <div class="sg-section-sub">Refresh your GOG game library from the server.</div>
                </div>
                <button class="sg-sync-btn" :class="{ 'sg-sync-btn--running': gogSyncing }" :disabled="gogSyncing" @click="syncGog">
                  <span v-if="gogSyncing" class="spinner spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                  </svg>
                  {{ gogSyncing ? 'Syncing...' : 'Sync Now' }}
                </button>
              </div>
              <div v-if="gogSyncMsg" class="sg-sync-msg" :class="gogSyncOk ? 'sg-sync-msg--ok' : 'sg-sync-msg--err'">
                {{ gogSyncMsg }}
              </div>
            </div>

          </div>

          <!-- Not connected -->
          <div v-else class="pv-gog-connect-wrap">
            <div class="pv-gog-connect-info">
              <img src="/icons/gog.ico" width="20" height="20" alt="GOG" style="image-rendering:pixelated;opacity:.7" />
              <div>
                <div class="pv-gog-connect-title">Connect your GOG account</div>
                <div class="pv-gog-connect-desc">Link your GOG.com account to import your game library.</div>
              </div>
            </div>

            <!-- Step-by-step instructions -->
            <div class="pv-gog-steps">
              <div class="pv-gog-steps-title">How to connect</div>
              <ol class="pv-gog-steps-list">
                <li>Click "Connect GOG Account" below</li>
                <li>A new tab will open with the GOG.com login page</li>
                <li>Log in with your GOG credentials</li>
                <li>After login, you will be redirected to a URL like:<br/>
                  <code class="pv-gog-url-example">https://embed.gog.com/on_login_success?code=XXXXX</code>
                </li>
                <li>Copy the entire URL from the address bar</li>
                <li>Paste it in the field below and click "Connect"</li>
              </ol>
              <div class="pv-gog-steps-title" style="margin-top:12px">After connecting</div>
              <ul class="pv-gog-after-list">
                <li>Click "Sync Library" to import your games</li>
                <li>Your games will appear in Game Requests under My GOG tab</li>
                <li>You can request games for the admin to download</li>
                <li>If you disconnect, non-downloaded games will be removed</li>
              </ul>
            </div>

            <button v-if="!gogCodeMode" class="pv-gog-action-btn pv-gog-action-btn--primary" @click="openGogAuth">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
              Connect GOG Account
            </button>
            <div v-if="gogCodeMode" class="pv-gog-code-wrap">
              <div class="pv-gog-code-hint">Log in to GOG.com in the new tab, then paste the redirect URL here:</div>
              <div class="pv-gog-code-row">
                <input v-model="gogCode" class="pv-input" :placeholder="t('profile.paste_gog_code')" />
                <button class="pv-gog-action-btn pv-gog-action-btn--primary" @click="submitGogCode" :disabled="gogLinking || !gogCode.trim()">
                  {{ gogLinking ? 'Connecting...' : 'Connect' }}
                </button>
              </div>
              <div v-if="gogError" class="pv-msg pv-msg--err" style="margin-top:8px">{{ gogError }}</div>
            </div>
          </div>
        </div>

      </template>

      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <!-- SECURITY TAB                                                          -->
      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <template v-else-if="tab === 'security'">

        <div class="pv-section">
          <div class="pv-section-title">{{ t('profile.change_password') }}</div>
          <div class="pv-section-sub">{{ t('profile.change_password_desc') }}</div>

          <form class="pv-form" @submit.prevent="changePassword">
            <div class="pv-field">
              <label class="pv-label">{{ t('profile.current_password') }}</label>
              <div class="pv-input-wrap">
                <input
                  v-model="pwForm.current"
                  :type="showCurrent ? 'text' : 'password'"
                  class="pv-input"
                  :placeholder="t('profile.enter_current_pw')"
                  autocomplete="current-password"
                />
                <button type="button" class="pv-eye" @click="showCurrent = !showCurrent" tabindex="-1">
                  <svg v-if="!showCurrent" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="pv-field">
              <label class="pv-label">{{ t('profile.new_password') }}</label>
              <div class="pv-input-wrap">
                <input
                  v-model="pwForm.newPw"
                  :type="showNew ? 'text' : 'password'"
                  class="pv-input"
                  :class="{ 'pv-input--error': pwError }"
                  :placeholder="t('profile.min_8_chars')"
                  autocomplete="new-password"
                />
                <button type="button" class="pv-eye" @click="showNew = !showNew" tabindex="-1">
                  <svg v-if="!showNew" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="pv-field">
              <label class="pv-label">{{ t('profile.confirm_password') }}</label>
              <input
                v-model="pwForm.confirm"
                type="password"
                class="pv-input pv-input--no-icon"
                :class="{ 'pv-input--error': pwError }"
                :placeholder="t('profile.repeat_password')"
                autocomplete="new-password"
              />
              <span v-if="pwError" class="pv-field-error">{{ pwError }}</span>
            </div>

            <div v-if="pwMsg" class="pv-msg" :class="pwOk ? 'pv-msg--ok' : 'pv-msg--err'">{{ pwMsg }}</div>

            <div class="pv-form-actions">
              <button
                type="submit"
                class="pv-save-btn"
                :disabled="!pwForm.current || !pwForm.newPw || !pwForm.confirm || pwSaving"
              >
                <span v-if="pwSaving" class="spinner spinner--sm" />
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ pwSaving ? 'Saving…' : 'Update Password' }}
              </button>
            </div>
          </form>
        </div>

      </template>

      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <!-- GAME SAVES TAB                                                        -->
      <!-- ══════════════════════════════════════════════════════════════════════ -->
      <template v-else-if="tab === 'saves'">

        <!-- Loading -->
        <div v-if="savesLoading" class="pv-saves-loading">
          <span class="spinner" />
        </div>

        <template v-else-if="savesData">

          <!-- Quota -->
          <div class="pv-section">
            <div class="pv-section-title">{{ t('profile.storage_quota') }}</div>
            <div class="pv-quota-wrap">
              <div class="pv-quota-bar">
                <div class="pv-quota-fill" :style="{ width: Math.min(quotaPercent, 100) + '%' }" :class="quotaPercent >= 90 ? 'pv-quota-fill--warn' : ''" />
              </div>
              <div class="pv-quota-text">
                <span>{{ formatBytes(savesData.used_bytes) }} {{ t('profile.used_of') }} {{ formatBytes(savesData.limit_bytes) }}</span>
              </div>
            </div>
          </div>

          <!-- Savestates -->
          <div class="pv-section">
            <div class="pv-section-title">
              {{ t('profile.save_states') }}
              <span class="pv-saves-count">{{ savesData.states.length }}</span>
            </div>
            <div v-if="savesData.states.length === 0" class="pv-saves-empty">
              {{ t('profile.no_save_states', 'No save states yet. Save states are created while playing in the browser emulator.') }}
            </div>
            <div v-else class="pv-saves-list">
              <div v-for="s in savesData.states" :key="s.id" class="pv-save-row">
                <div class="pv-save-thumb-wrap">
                  <img v-if="s.screenshot_url" :src="s.screenshot_url" class="pv-save-thumb" :alt="s.file_name" />
                  <div v-else class="pv-save-thumb-ph">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.3">
                      <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>
                      <polyline points="21 15 16 10 5 21"/>
                    </svg>
                  </div>
                </div>
                <div class="pv-save-info">
                  <div class="pv-save-name">{{ stripExt(s.file_name) }}</div>
                  <div class="pv-save-meta">
                    <span>{{ formatDate(s.created_at ?? undefined) }}</span>
                    <span class="pv-save-sep">·</span>
                    <span>{{ formatBytes(s.file_size_bytes) }}</span>
                    <span v-if="s.emulator_core" class="pv-save-sep">·</span>
                    <span v-if="s.emulator_core" class="pv-save-core">{{ s.emulator_core }}</span>
                  </div>
                </div>
                <button
                  class="pv-save-del"
                  :disabled="deletingStateId === s.id"
                  @click="deleteState(s.id)"
                  :title="t('profile.delete_save')"
                >
                  <span v-if="deletingStateId === s.id" class="spinner spinner--sm" />
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>
                    <path d="M9 6V4h6v2"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- Battery Saves -->
          <div class="pv-section">
            <div class="pv-section-title">
              {{ t('profile.battery_saves') }}
              <span class="pv-saves-count">{{ savesData.saves.length }}</span>
            </div>
            <div v-if="savesData.saves.length === 0" class="pv-saves-empty">
              {{ t('profile.no_saves') }}
            </div>
            <div v-else class="pv-saves-list">
              <div v-for="s in savesData.saves" :key="s.id" class="pv-save-row">
                <div class="pv-save-thumb-wrap">
                  <div class="pv-save-thumb-ph pv-save-thumb-ph--srm">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.5">
                      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                      <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
                    </svg>
                  </div>
                </div>
                <div class="pv-save-info">
                  <div class="pv-save-name">{{ stripExt(s.file_name) }}</div>
                  <div class="pv-save-meta">
                    <span>{{ formatDate(s.created_at ?? undefined) }}</span>
                    <span class="pv-save-sep">·</span>
                    <span>{{ formatBytes(s.file_size_bytes) }}</span>
                    <span v-if="s.emulator_core" class="pv-save-sep">·</span>
                    <span v-if="s.emulator_core" class="pv-save-core">{{ s.emulator_core }}</span>
                  </div>
                </div>
                <button
                  class="pv-save-del"
                  :disabled="deletingSaveId === s.id"
                  @click="deleteSave(s.id)"
                  :title="t('profile.delete_battery')"
                >
                  <span v-if="deletingSaveId === s.id" class="spinner spinner--sm" />
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>
                    <path d="M9 6V4h6v2"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>

        </template>
      </template>

      </div><!-- /pv-content -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t, locale, setLocale, SUPPORTED } = useI18n()

interface UserInfo {
  id: number
  username: string
  email?: string
  role: string
  avatar_path?: string
  created_at?: string
}

const router    = useRouter()
const authStore = useAuthStore()
const isAdmin   = computed(() => authStore.user?.role === 'admin')

interface GogStatus {
  authenticated: boolean
  username?: string
  avatar_url?: string
  user_id?: string
  email?: string
  expires_at?: string
  games_count?: number | null
  game_count?: number | null
  movies_count?: number | null
  country?: string
  created_date?: string
}

const tab        = ref<'account' | 'security' | 'saves'>('account')
const user       = ref<UserInfo | null>(null)
const avatarUrl  = ref('')
const fileInput  = ref<HTMLInputElement | null>(null)
const gogStatus  = ref<GogStatus | null>(null)
const gogLoading = ref(true)
const gogSyncing  = ref(false)
const gogSyncMsg  = ref('')
const gogSyncOk   = ref(true)
const gogCodeMode = ref(false)
const gogCode     = ref('')
const gogLinking  = ref(false)
const gogError    = ref('')
const libraryGames = ref<any[]>([])

const avatarUploading = ref(false)
const avatarMsg       = ref('')
const avatarOk        = ref(true)

const showCurrent = ref(false)
const showNew     = ref(false)
const pwSaving    = ref(false)
const pwMsg       = ref('')
const pwOk        = ref(true)
const pwError     = ref('')
const pwForm      = ref({ current: '', newPw: '', confirm: '' })

// ── Game Saves tab ─────────────────────────────────────────────────────────
interface SaveState {
  id: number
  rom_id: number
  file_name: string
  file_size_bytes: number
  emulator_core: string | null
  screenshot_url: string | null
  created_at: string | null
  download_url: string
}
interface BatterySave {
  id: number
  rom_id: number
  file_name: string
  file_size_bytes: number
  emulator_core: string | null
  slot: string | null
  created_at: string | null
  download_url: string
}
interface SavesData {
  states: SaveState[]
  saves: BatterySave[]
  used_bytes: number
  limit_bytes: number
}

const savesData       = ref<SavesData | null>(null)
const savesLoading    = ref(false)
const savesLoaded     = ref(false)
const deletingStateId = ref<number | null>(null)
const deletingSaveId  = ref<number | null>(null)

const quotaPercent = computed(() => {
  if (!savesData.value || savesData.value.limit_bytes === 0) return 0
  return (savesData.value.used_bytes / savesData.value.limit_bytes) * 100
})

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function stripExt(filename: string): string {
  return filename.replace(/\.(state|srm)$/, '')
}

async function loadSavesIfNeeded() {
  if (savesLoaded.value || savesLoading.value) return
  savesLoading.value = true
  try {
    const { data } = await client.get('/savestates/my')
    savesData.value  = data
    savesLoaded.value = true
  } catch { /* silent */ } finally {
    savesLoading.value = false
  }
}

async function deleteState(id: number) {
  if (deletingStateId.value !== null) return
  deletingStateId.value = id
  try {
    await client.delete(`/savestates/states/${id}`)
    if (savesData.value) {
      savesData.value.states = savesData.value.states.filter(s => s.id !== id)
      // recalculate used_bytes from remaining items
      const used = savesData.value.states.reduce((a, s) => a + s.file_size_bytes, 0)
               + savesData.value.saves.reduce((a, s) => a + s.file_size_bytes, 0)
      savesData.value.used_bytes = used
    }
  } catch { /* silent */ } finally {
    deletingStateId.value = null
  }
}

async function deleteSave(id: number) {
  if (deletingSaveId.value !== null) return
  deletingSaveId.value = id
  try {
    await client.delete(`/savestates/saves/${id}`)
    if (savesData.value) {
      savesData.value.saves = savesData.value.saves.filter(s => s.id !== id)
      const used = savesData.value.states.reduce((a, s) => a + s.file_size_bytes, 0)
               + savesData.value.saves.reduce((a, s) => a + s.file_size_bytes, 0)
      savesData.value.used_bytes = used
    }
  } catch { /* silent */ } finally {
    deletingSaveId.value = null
  }
}

onMounted(async () => {
  try {
    const { data } = await client.get('/users/me')
    user.value = data
    if (data.avatar_path) {
      if (data.avatar_path.startsWith('http')) {
        avatarUrl.value = data.avatar_path
      } else {
        // avatar_path is a filesystem path like /data/resources/avatars/1.jpg
        // Static files are served at /resources/... without auth
        const filename = data.avatar_path.split(/[\\/]/).pop() || ''
        avatarUrl.value = filename ? `/resources/avatars/${filename}?t=${Date.now()}` : ''
      }
    }
  } catch { /* ignore */ }
  // User's own GOG account status
  gogLoading.value = true
  try {
    const { data } = await client.get('/gog/user/auth/status')
    gogStatus.value = data
  } catch { gogStatus.value = { authenticated: false } }
  gogLoading.value = false
  // Library stats (admin endpoint, best-effort)
  try {
    const { data } = await client.get('/gog/library/games')
    libraryGames.value = data
  } catch { /* library stats are best-effort */ }
})

const downloadedCount = computed(() =>
  libraryGames.value.filter(g => g.is_downloaded || g.download_status === 'completed').length
)
const libraryCount = computed(() => libraryGames.value.length)
const favoriteGenre = computed<string | null>(() => {
  const dl = libraryGames.value.filter(g => g.is_downloaded || g.download_status === 'completed')
  if (!dl.length) return null
  const counts: Record<string, number> = {}
  for (const g of dl) {
    for (const genre of (g.genres || [])) {
      counts[genre] = (counts[genre] || 0) + 1
    }
  }
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]
  return top ? top[0] : null
})

function formatDate(iso?: string): string {
  if (!iso) return '-'
  try {
    const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
    return new Date(iso).toLocaleDateString(loc, { dateStyle: 'long' })
  } catch { return iso }
}

function formatExpiry(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  } catch { return iso }
}

function triggerAvatarUpload() {
  fileInput.value?.click()
}

async function uploadAvatar(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const maxSize = 5 * 1024 * 1024
  if (file.size > maxSize) {
    avatarOk.value = false
    avatarMsg.value = t('profile.avatar_too_large', 'File is too large. Maximum size is 5 MB.')
    setTimeout(() => { avatarMsg.value = '' }, 4000)
    return
  }
  const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!allowedTypes.includes(file.type)) {
    avatarOk.value = false
    avatarMsg.value = t('profile.avatar_invalid_type', 'Only JPEG, PNG, GIF, and WebP images are accepted.')
    setTimeout(() => { avatarMsg.value = '' }, 4000)
    return
  }
  avatarUploading.value = true
  avatarMsg.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    // Use native fetch - Axios may corrupt multipart/form-data boundary
    // when a default Content-Type: application/json is set on the instance.
    const token = localStorage.getItem('gd3_token') || ''
    const resp = await fetch('/api/users/me/avatar', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err?.detail || `HTTP ${resp.status}`)
    }
    const respData = await resp.json()
    // Use static path from response (no auth required for /resources/...)
    avatarUrl.value = (respData.avatar_url || '') + `?t=${Date.now()}`
    avatarOk.value  = true
    avatarMsg.value = 'Profile picture updated.'
    await authStore.fetchUser()
    setTimeout(() => { avatarMsg.value = '' }, 3000)
  } catch (e: any) {
    avatarOk.value  = false
    avatarMsg.value = e?.message || 'Failed to upload avatar.'
  } finally {
    avatarUploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

// ── GOG Account ───────────────────────────────────────────────────────────
async function openGogAuth() {
  gogError.value = ''
  try {
    const { data } = await client.get('/gog/user/auth/url')
    if (data.url) window.open(data.url, '_blank')
    gogCodeMode.value = true
  } catch { /* ignore */ }
}

async function submitGogCode() {
  if (!gogCode.value.trim()) return
  gogLinking.value = true
  gogError.value = ''
  try {
    const { data } = await client.post('/gog/user/auth/callback', { code: gogCode.value.trim() })
    gogStatus.value = { authenticated: true, ...data }
    gogCodeMode.value = false
    gogCode.value = ''
    // Refresh status to get full info
    const { data: st } = await client.get('/gog/user/auth/status')
    gogStatus.value = st
  } catch (e: any) {
    gogError.value = e?.response?.data?.detail || 'Failed to connect GOG account.'
  } finally {
    gogLinking.value = false
  }
}

async function syncGog() {
  gogSyncing.value = true
  gogSyncMsg.value = ''
  gogSyncOk.value  = true
  try {
    const result = await client.post('/gog/user/library/sync')
    // Refresh status to update game count
    const { data } = await client.get('/gog/user/auth/status')
    gogStatus.value = data
    gogSyncOk.value  = true
    gogSyncMsg.value = `Sync complete - ${data.game_count ?? 0} games`
  } catch (e: any) {
    gogSyncOk.value  = false
    gogSyncMsg.value = e?.response?.data?.detail || 'Sync failed.'
  } finally {
    gogSyncing.value = false
  }
}

async function disconnectGog() {
  if (!confirm('Disconnect your GOG account? Non-downloaded games will be removed.')) return
  try {
    await client.delete('/gog/user/auth')
    gogStatus.value = { authenticated: false }
    gogCodeMode.value = false
    gogCode.value = ''
  } catch { /* ignore */ }
}

async function changePassword() {
  pwError.value = ''
  pwMsg.value   = ''
  if (pwForm.value.newPw.length < 8) {
    pwError.value = 'New password must be at least 8 characters.'
    return
  }
  if (pwForm.value.newPw !== pwForm.value.confirm) {
    pwError.value = 'Passwords do not match.'
    return
  }
  pwSaving.value = true
  try {
    await client.post('/users/me/password', {
      current_password: pwForm.value.current,
      new_password:     pwForm.value.newPw,
    })
    pwOk.value  = true
    pwMsg.value = 'Password updated successfully.'
    pwForm.value = { current: '', newPw: '', confirm: '' }
    setTimeout(() => { pwMsg.value = '' }, 3000)
  } catch (e: any) {
    pwOk.value  = false
    pwMsg.value = e?.response?.data?.detail || 'Failed to update password.'
  } finally {
    pwSaving.value = false
  }
}
</script>

<style scoped>
.pv-root {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
.pv-header {
  display: flex; align-items: center; gap: var(--space-4, 16px);
  padding: 20px 28px 16px; flex-shrink: 0;
}
.pv-back-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 12px 6px 8px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition); flex-shrink: 0;
}
.pv-back-btn:hover { background: var(--glass-highlight); border-color: var(--pl); color: var(--text); }
.pv-title { font-size: var(--fs-2xl, 22px); font-weight: 700; color: var(--text); margin: 0; }

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.pv-tabs {
  display: flex; gap: 2px;
  padding: 0 28px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.pv-tab {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 16px;
  border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--muted);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; white-space: nowrap;
  transition: all var(--transition); margin-bottom: -1px;
}
.pv-tab:hover { color: var(--text); }
.pv-tab.active { color: var(--pl-light); border-bottom-color: var(--pl); }

/* ── Body ─────────────────────────────────────────────────────────────────── */
.pv-body {
  flex: 1; overflow-y: auto;
  display: flex; justify-content: center;
  padding: 0;
}
.pv-content {
  width: 660px; max-width: 100%;
  padding: 28px;
  display: flex; flex-direction: column; gap: var(--space-4, 16px);
}

/* ── Section ──────────────────────────────────────────────────────────────── */
.pv-section {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  overflow: hidden;
}
.pv-section-title {
  padding: 14px 20px 0;
  font-size: 13px; font-weight: 700; color: var(--text);
}
.pv-section-sub {
  padding: 4px 20px 0;
  font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.55;
}
.pv-lang-row { padding: 4px 20px; }
.pv-lang-select {
  padding: 8px 14px; border-radius: 6px;
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: rgba(255,255,255,.04); color: var(--text, #fff);
  font-size: var(--fs-md, 14px); cursor: pointer; outline: none;
  min-width: 200px;
}
.pv-lang-select:focus { border-color: var(--pl, #00d4ff); }
.pv-lang-select option { background: var(--bg2, #0a0a1a); color: var(--text, #fff); }

/* ── Avatar ───────────────────────────────────────────────────────────────── */
.pv-avatar-row {
  display: flex; align-items: center; gap: 18px;
  padding: 16px 20px;
}
.pv-avatar-wrap {
  position: relative; width: 76px; height: 76px;
  border-radius: 50%; cursor: pointer; flex-shrink: 0;
}
.pv-avatar {
  width: 100%; height: 100%; border-radius: 50%;
  object-fit: cover; border: 2px solid var(--pl); display: block;
}
.pv-avatar-placeholder {
  width: 100%; height: 100%; border-radius: 50%;
  background: var(--pl-dim); border: 2px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
}
.pv-avatar-overlay {
  position: absolute; inset: 0; border-radius: 50%;
  background: rgba(0,0,0,.6);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 3px;
  opacity: 0; transition: opacity .18s; color: #fff;
  font-size: var(--fs-xs, 10px); font-weight: 600;
}
.pv-avatar-wrap:hover .pv-avatar-overlay { opacity: 1; }
.pv-avatar-uploading {
  position: absolute; inset: 0; border-radius: 50%;
  background: rgba(0,0,0,.7);
  display: flex; align-items: center; justify-content: center;
}
.pv-avatar-info { display: flex; flex-direction: column; gap: 3px; }
.pv-avatar-name { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); }
.pv-avatar-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); }
.pv-avatar-hint { font-size: 11px; color: var(--muted); opacity: .7; margin-top: 4px; }

/* ── Details table ────────────────────────────────────────────────────────── */
.pv-details-table { display: flex; flex-direction: column; }
.pv-detail-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 20px; gap: var(--space-4, 16px);
}
.pv-detail-row + .pv-detail-row { border-top: 1px solid var(--glass-border); }
.pv-detail-label { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted); flex-shrink: 0; }
.pv-detail-value { font-size: 13px; color: var(--text); }

.pv-role-badge {
  display: inline-block; padding: 2px 10px; border-radius: var(--radius, 12px);
  font-size: 11px; font-weight: 700; letter-spacing: .3px; text-transform: uppercase;
}
.pv-role--admin  { background: rgba(167,139,250,.15); border: 1px solid rgba(167,139,250,.4);  color: #c4b5fd; }
.pv-role--editor { background: rgba(251,191,36,.12);  border: 1px solid rgba(251,191,36,.35);  color: #fbbf24; }
.pv-role--viewer { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);   color: var(--muted); }

/* ── Form ─────────────────────────────────────────────────────────────────── */
.pv-form { padding: 16px 20px 20px; display: flex; flex-direction: column; gap: 14px; }
.pv-field { display: flex; flex-direction: column; gap: 5px; }
.pv-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .6px;
}
.pv-input-wrap { position: relative; }
.pv-input {
  width: 100%; padding: 9px 36px 9px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.pv-input.pv-input--no-icon { padding-right: 12px; }
.pv-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.pv-input--error { border-color: #f87171 !important; }
.pv-input::placeholder { color: rgba(255,255,255,.2); }
.pv-eye {
  position: absolute; right: 9px; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--muted);
  cursor: pointer; padding: 2px; display: flex; align-items: center;
}
.pv-eye:hover { color: var(--text); }
.pv-field-error { font-size: var(--fs-sm, 12px); color: #f87171; }

.pv-form-actions { display: flex; justify-content: flex-end; padding-top: 4px; }

.pv-save-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
  box-shadow: 0 2px 12px var(--pglow2);
}
.pv-save-btn:not(:disabled):hover { background: var(--pl-light); }
.pv-save-btn:disabled { opacity: .55; cursor: not-allowed; }

/* ── Messages ─────────────────────────────────────────────────────────────── */
.pv-msg {
  margin: 0 20px 16px; padding: 9px 12px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 600;
}
.pv-msg--ok  { background: rgba(34,197,94,.08);  border: 1px solid rgba(34,197,94,.25);  color: #86efac; }
.pv-msg--err { background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.3); color: #f87171; }

/* ── Library stats ────────────────────────────────────────────────────────── */
.pv-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-3, 12px);
  padding: 14px 20px 20px;
}
.pv-stat-card {
  padding: 18px 12px 14px;
  background: rgba(255,255,255,.04);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  text-align: center;
}
.pv-stat-val {
  font-size: 30px; font-weight: 800; color: var(--pl-light);
  line-height: 1; letter-spacing: -1px;
}
.pv-stat-val--genre {
  font-size: 15px; font-weight: 700; letter-spacing: 0;
  color: var(--pl-light);
}
.pv-stat-lbl {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px;
  margin-top: 8px;
}

.pv-eye-btn {
  flex-shrink: 0; background: none; border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 6px 8px; cursor: pointer;
  color: var(--muted); display: flex; align-items: center;
  transition: color var(--transition), border-color var(--transition);
}
.pv-eye-btn:hover { color: var(--text); border-color: var(--pl); }

/* ── GOG Account card ─────────────────────────────────────────────────────── */
.pv-gog-loading { padding: var(--space-5, 20px); display: flex; justify-content: center; }
.pv-gog-connected {
  display: flex; flex-direction: column; gap: var(--space-4, 16px); padding: 16px 20px;
}

/* GOG connected state (mirrors SettingsGog.vue sg-* classes) */
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
.sg-disconnect-btn:hover { background: rgba(248,113,113,.16); border-color: #f87171; }

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
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
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
.pv-gog-action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); cursor: pointer; transition: all .15s; white-space: nowrap;
}
.pv-gog-action-btn:hover { background: rgba(255,255,255,.12); color: var(--text); border-color: rgba(255,255,255,.2); }
.pv-gog-action-btn:disabled { opacity: .5; cursor: not-allowed; }
.pv-gog-action-btn--primary {
  background: color-mix(in srgb, var(--pl) 25%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  box-shadow: 0 2px 10px var(--pglow2);
}
.pv-gog-action-btn--primary:hover { background: var(--pl-light); }
.pv-gog-action-btn--danger:hover { background: rgba(239,68,68,.15); border-color: #f87171; color: #f87171; }
.pv-gog-connect-wrap { padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }
.pv-gog-connect-info { display: flex; align-items: flex-start; gap: var(--space-3, 12px); }
.pv-gog-connect-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); margin-bottom: 4px; }
.pv-gog-connect-desc { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.55; }
.pv-gog-code-wrap { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.pv-gog-code-hint { font-size: var(--fs-sm, 12px); color: var(--muted); }
.pv-gog-code-row { display: flex; gap: var(--space-2, 8px); }
.pv-gog-code-row .pv-input { flex: 1; }

/* ── GOG steps instructions ──────────────────────────────────────────────── */
.pv-gog-steps {
  background: rgba(255,255,255,.03); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 14px 18px;
}
.pv-gog-steps-title {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px; margin-bottom: 8px;
}
.pv-gog-steps-list {
  margin: 0; padding-left: 20px;
  display: flex; flex-direction: column; gap: 6px;
  font-size: 13px; color: var(--muted); line-height: 1.55;
}
.pv-gog-steps-list li::marker { color: var(--pl-light); font-weight: 700; }
.pv-gog-url-example {
  display: inline-block; margin-top: 4px;
  padding: 3px 8px; border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  font-family: monospace; font-size: 11px; color: var(--pl-light);
  word-break: break-all;
}
.pv-gog-after-list {
  margin: 0; padding-left: 20px;
  display: flex; flex-direction: column; gap: var(--space-1, 4px);
  font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5;
}
.pv-gog-after-list li::marker { color: rgba(255,255,255,.2); }

/* ── Spinner ──────────────────────────────────────────────────────────────── */
.spinner {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
.spinner--sm { width: 10px; height: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Game Saves tab ───────────────────────────────────────────────────────── */
.pv-saves-loading {
  display: flex; justify-content: center; padding: var(--space-12, 48px);
}
.pv-saves-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 18px; padding: 0 6px;
  background: rgba(255,255,255,.07); border: 1px solid var(--glass-border);
  border-radius: 9px; font-size: 11px; font-weight: 700; color: var(--muted);
  margin-left: 8px; vertical-align: middle;
}

/* Quota */
.pv-quota-wrap {
  padding: 14px 20px 18px; display: flex; flex-direction: column; gap: var(--space-2, 8px);
}
.pv-quota-bar {
  width: 100%; height: 7px; border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.07); overflow: hidden;
}
.pv-quota-fill {
  height: 100%; border-radius: var(--radius-xs, 4px);
  background: color-mix(in srgb, var(--pl) 30%, transparent); transition: width .4s ease;
}
.pv-quota-fill--warn { background: #f87171; }
.pv-quota-text {
  display: flex; justify-content: space-between; align-items: center;
  font-size: var(--fs-sm, 12px); color: var(--text);
}
.pv-quota-limit { color: var(--muted); }

/* Saves list */
.pv-saves-empty {
  padding: var(--space-5, 20px); font-size: 13px; color: var(--muted); line-height: 1.55;
}
.pv-saves-list { display: flex; flex-direction: column; }
.pv-save-row {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 10px 14px 10px 16px;
  transition: background var(--transition);
}
.pv-save-row + .pv-save-row { border-top: 1px solid var(--glass-border); }
.pv-save-row:hover { background: rgba(255,255,255,.02); }

/* Thumbnail */
.pv-save-thumb-wrap { flex-shrink: 0; }
.pv-save-thumb {
  width: 64px; height: 40px; border-radius: var(--radius-xs, 4px);
  object-fit: cover; display: block;
  border: 1px solid var(--glass-border);
}
.pv-save-thumb-ph {
  width: 64px; height: 40px; border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center;
}
.pv-save-thumb-ph--srm { background: rgba(var(--pl-rgb, 124,58,237),.06); }

/* Info */
.pv-save-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.pv-save-name {
  font-size: 13px; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pv-save-meta {
  display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-1, 4px);
  font-size: 11px; color: var(--muted);
}
.pv-save-sep { opacity: .4; }
.pv-save-core {
  padding: 1px 6px; border-radius: var(--radius-xs, 4px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  font-family: monospace;
}

/* Delete button */
.pv-save-del {
  flex-shrink: 0; width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid transparent; border-radius: var(--radius-sm);
  background: none; color: var(--muted);
  cursor: pointer; transition: all var(--transition);
}
.pv-save-del:not(:disabled):hover {
  color: #f87171; border-color: rgba(248,113,113,.3);
  background: rgba(248,113,113,.07);
}
.pv-save-del:disabled { opacity: .4; cursor: not-allowed; }
</style>
