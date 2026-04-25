<template>
  <div class="ss-root">

    <!-- ── Header ──────────────────────────────────────────────────────────── -->
    <div class="ss-header">
      <div class="ss-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>
      <div>
        <div class="ss-title">{{ t('security.title') }}</div>
        <div class="ss-subtitle">{{ t('security.subtitle') }}</div>
      </div>
    </div>

    <!-- ── Section A: Brute-force Protection ───────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('bruteforce')">
        <span>{{ t('security.bruteforce') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.bruteforce }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.bruteforce">
      <div v-if="bfLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>

      <template v-else>
        <div class="field-row field-row--toggle"
          @mouseenter="setHint(t('shint.bf_title'), t('shint.bf_body'))"
          @mouseleave="clearHint()">
          <label class="toggle-label">
            <input type="checkbox" v-model="bf.enabled" class="toggle-input" />
            <span class="toggle-track"><span class="toggle-thumb" /></span>
            <span class="toggle-text">{{ t('security.bruteforce_enable') }}</span>
          </label>
        </div>

        <div class="fields-grid">
          <div class="field-group"
            @mouseenter="setHint(t('shint.bf_max_title'), t('shint.bf_max_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.max_attempts') }}</label>
            <div class="field-hint">{{ t('security.max_attempts_hint') }}</div>
            <input v-model.number="bf.max_attempts" type="number" min="1" max="100" class="field-input" :disabled="!bf.enabled" />
          </div>
          <div class="field-group"
            @mouseenter="setHint(t('shint.bf_window_title'), t('shint.bf_window_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.time_window') }}</label>
            <div class="field-hint">{{ t('security.time_window_hint') }}</div>
            <div class="field-input-wrap"><input v-model.number="bf.window_seconds" type="number" min="30" class="field-input" :disabled="!bf.enabled" /><span class="field-unit">{{ t('security.seconds', 'seconds') }}</span></div>
          </div>
          <div class="field-group"
            @mouseenter="setHint(t('shint.bf_ban_title'), t('shint.bf_ban_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.ban_duration') }}</label>
            <div class="field-hint">{{ t('security.ban_duration_hint') }}</div>
            <div class="field-input-wrap"><input v-model.number="bf.ban_seconds" type="number" min="60" class="field-input" :disabled="!bf.enabled" /><span class="field-unit">{{ t('security.seconds', 'seconds') }}</span></div>
          </div>
          <div class="field-group field-group--wide"
            @mouseenter="setHint(t('shint.bf_whitelist_title'), t('shint.bf_whitelist_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.whitelist') }}</label>
            <div class="field-hint">{{ t('security.whitelist_hint') }}</div>
            <textarea
              v-model="bf.whitelist"
              class="field-textarea"
              rows="2"
              placeholder="192.168.1.1, 10.0.0.1"
              :disabled="!bf.enabled"
            />
          </div>
        </div>

        <div v-if="bfError" class="field-server-error">{{ bfError }}</div>
        <div v-if="bfSaved" class="field-ok">{{ t('security.bruteforce_saved') }}</div>

        <div class="ss-actions">
          <button class="action-btn action-btn--primary" :disabled="bfSaving" @click="saveBf">
            <span v-if="bfSaving" class="spinner" />
            <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              <polyline points="17 21 17 13 7 13 7 21"/>
              <polyline points="7 3 7 8 15 8"/>
            </svg>
            {{ t('common.save') }}
          </button>
        </div>

        <!-- Banned IPs table -->
        <div class="ss-subsection-title">{{ t('security.banned_ips') }}</div>
        <div v-if="bannedLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
        <div v-else-if="bannedIps.length === 0" class="ss-empty">{{ t('security.no_banned') }}</div>
        <table v-else class="ss-table">
          <thead>
            <tr>
              <th>IP Address</th>
              <th>Remaining (s)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in bannedIps" :key="entry.ip">
              <td class="td-mono">{{ entry.ip }}</td>
              <td>{{ entry.remaining_seconds }}</td>
              <td>
                <button class="action-btn action-btn--danger action-btn--sm" @click="unban(entry.ip)">{{ t('security.unban') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
      </div><!-- /v-show bruteforce -->
    </div>

    <!-- ── Section C: ClamAV Antivirus ─────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('clamav')">
        <span>{{ t('security.clamav') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.clamav }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.clamav">
      <div v-if="cvLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>

      <template v-else>
        <!-- Status card -->
        <div class="cv-status-card"
          @mouseenter="setHint(t('shint.cv_status_title'), t('shint.cv_status_body'))"
          @mouseleave="clearHint()">
          <div class="cv-status-dot" :class="cvStatus.running ? 'cv-status-dot--ok' : 'cv-status-dot--err'" />
          <div class="cv-status-info">
            <div class="cv-status-label">
              <strong>{{ cvStatus.running ? t('security.daemon_running') : t('security.daemon_not_running') }}</strong>
              <span v-if="cvStatus.version" class="cv-status-ver">{{ cvStatus.version }}</span>
            </div>
            <div class="cv-status-sub">
              <template v-if="cvStatus.db_date">
                {{ t('security.virus_db') }}: <strong>{{ cvStatus.db_version }}</strong> - {{ t('security.updated') }} {{ formatTime(cvStatus.db_date) }}
              </template>
              <template v-else-if="!cvStatus.running">
                {{ t('security.no_definitions') }}
              </template>
            </div>
          </div>
          <button class="action-btn action-btn--ghost action-btn--sm" @click="loadCvStatus">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('security.refresh') }}
          </button>
        </div>

        <!-- Action on infected file -->
        <div class="ss-subsection-title">{{ t('security.action_on_infected') }}</div>
        <div class="cv-action-picker">
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': cv.action === 'none' }"
            @mouseenter="setHint(t('shint.cv_report_title'), t('shint.cv_report_body'))"
            @mouseleave="clearHint()">
            <input type="radio" v-model="cv.action" value="none" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--none">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.report_only') }}</div>
              <div class="cv-action-hint">{{ t('security.report_only_hint') }}</div>
            </div>
          </label>
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': cv.action === 'quarantine' }"
            @mouseenter="setHint(t('shint.cv_quarantine_title'), t('shint.cv_quarantine_body'))"
            @mouseleave="clearHint()">
            <input type="radio" v-model="cv.action" value="quarantine" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--quarantine">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.quarantine') }} <span class="cv-action-badge">{{ t('security.recommended') }}</span></div>
              <div class="cv-action-hint">{{ t('security.quarantine_hint') }}</div>
            </div>
          </label>
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': cv.action === 'delete' }"
            @mouseenter="setHint(t('shint.cv_delete_title'), t('shint.cv_delete_body'))"
            @mouseleave="clearHint()">
            <input type="radio" v-model="cv.action" value="delete" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--delete">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.delete_permanently') }}</div>
              <div class="cv-action-hint">⚠ {{ t('security.delete_perm_hint') }}</div>
            </div>
          </label>
        </div>

        <!-- Config toggles -->
        <div class="cv-toggle-group">
          <div class="cv-trow"
            @mouseenter="setHint(t('shint.cv_enable_title'), t('shint.cv_enable_body'))"
            @mouseleave="clearHint()">
            <div class="cv-tinfo">
              <div class="cv-tname">{{ t('security.enable_clamav') }}</div>
              <div class="cv-tdesc">{{ t('security.enable_clamav_hint') }}</div>
            </div>
            <label class="cv-tpill">
              <input type="checkbox" v-model="cv.enabled" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
            </label>
          </div>
          <div class="cv-trow" :class="{ 'cv-trow--dim': !cv.enabled }"
            @mouseenter="setHint(t('shint.cv_auto_upload_title'), t('shint.cv_auto_upload_body'))"
            @mouseleave="clearHint()">
            <div class="cv-tinfo">
              <div class="cv-tname">{{ t('security.auto_scan_upload') }}</div>
              <div class="cv-tdesc">{{ t('security.auto_scan_upload_hint') }}</div>
            </div>
            <label class="cv-tpill">
              <input type="checkbox" v-model="cv.auto_scan_upload" class="toggle-input" :disabled="!cv.enabled" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
            </label>
          </div>
          <div class="cv-trow" :class="{ 'cv-trow--dim': !cv.enabled }"
            @mouseenter="setHint(t('shint.cv_auto_download_title'), t('shint.cv_auto_download_body'))"
            @mouseleave="clearHint()">
            <div class="cv-tinfo">
              <div class="cv-tname">{{ t('security.auto_scan_download') }}</div>
              <div class="cv-tdesc">{{ t('security.auto_scan_download_hint') }}</div>
            </div>
            <label class="cv-tpill">
              <input type="checkbox" v-model="cv.auto_scan_download" class="toggle-input" :disabled="!cv.enabled" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
            </label>
          </div>
          <div class="cv-trow" :class="{ 'cv-trow--dim': !cv.enabled }"
            @mouseenter="setHint(t('shint.cv_auto_update_title'), t('shint.cv_auto_update_body'))"
            @mouseleave="clearHint()">
            <div class="cv-tinfo">
              <div class="cv-tname">{{ t('security.auto_update_defs') }}</div>
              <div class="cv-tdesc">{{ t('security.auto_update_defs_hint') }}</div>
            </div>
            <label class="cv-tpill">
              <input type="checkbox" v-model="cv.auto_update" class="toggle-input" :disabled="!cv.enabled" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
            </label>
          </div>
        </div>

        <!-- Auto-update interval (shown when auto-update is on) -->
        <div v-if="cv.auto_update && cv.enabled" class="cv-interval-row"
          @mouseenter="setHint(t('shint.cv_interval_title'), t('shint.cv_interval_body'))"
          @mouseleave="clearHint()">
          <label class="field-label">{{ t('security.update_interval') }}</label>
          <div class="cv-interval-input-wrap">
            <input type="number" v-model.number="cv.update_interval_hours" min="1" max="168" class="field-input cv-interval-input" :disabled="!cv.enabled" />
            <span class="cv-interval-unit">{{ t('security.hours') }}</span>
          </div>
          <div v-if="cvLastAutoUpdate" class="cv-last-update">
            {{ t('security.last_auto_update') }}: <strong>{{ formatTime(cvLastAutoUpdate) }}</strong>
          </div>
        </div>

        <div v-if="cvSaved" class="field-ok">{{ t('security.clamav_saved') }}</div>
        <div class="ss-actions">
          <button class="action-btn action-btn--primary" :disabled="cvConfigSaving" @click="saveCvConfig">
            <span v-if="cvConfigSaving" class="spinner" />
            <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
            </svg>
            {{ t('common.save') }}
          </button>
        </div>

        <!-- Update definitions -->
        <div class="ss-subsection-title">{{ t('security.virus_definitions') }}</div>
        <div class="field-hint cv-section-hint">
          {{ t('security.update_defs_desc') }}
        </div>
        <div class="ss-actions"
          @mouseenter="setHint(t('shint.cv_update_title'), t('shint.cv_update_body'))"
          @mouseleave="clearHint()">
          <button class="action-btn action-btn--ghost" :disabled="cvUpdating" @click="updateDefinitions">
            <span v-if="cvUpdating" class="spinner" />
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('security.update_definitions') }}
          </button>
        </div>
        <!-- Update log -->
        <div v-if="cvUpdateLog.length > 0" class="cv-log" ref="cvLogEl">
          <div v-for="(line, i) in cvUpdateLog" :key="i" class="cv-log-line" :class="line.status === 'error' ? 'cv-log-line--err' : line.status === 'complete' ? 'cv-log-line--ok' : ''">{{ line.msg }}</div>
        </div>

        <!-- Scan -->
        <div class="ss-subsection-title">{{ t('security.manual_scan') }}</div>
        <div class="field-hint cv-section-hint">
          {{ t('security.manual_scan_desc') }}
          {{ t('security.progress_hint') }}
        </div>
        <div class="cv-scan-paths">
          <label v-for="key in cvAvailablePaths" :key="key" class="cv-path-check"
            @mouseenter="setHint(cvPathMeta[key]?.label ?? key, (cvPathMeta[key]?.desc ?? key) + '. ' + t('shint.cv_path_scan_suffix'))"
            @mouseleave="clearHint()">
            <input type="checkbox" :value="key" v-model="cvSelectedPaths" />
            <div class="cv-path-info">
              <span class="cv-path-name">{{ cvPathMeta[key]?.label ?? key }}</span>
              <span class="cv-path-desc">{{ cvPathMeta[key]?.desc ?? '' }}</span>
            </div>
          </label>
        </div>
        <div v-if="!cvStatus.running" class="field-hint cv-hint-warn">
          ⚠ {{ t('security.daemon_not_running_warn') }}
        </div>
        <div class="ss-actions"
          @mouseenter="setHint(t('shint.cv_scan_title'), t('shint.cv_scan_body'))"
          @mouseleave="clearHint()">
          <button
            class="action-btn action-btn--ghost"
            :disabled="cvScanning || !cvStatus.running || cvSelectedPaths.length === 0"
            @click="startScan"
            :title="!cvStatus.running ? 'ClamAV daemon not running' : cvSelectedPaths.length === 0 ? 'Select at least one folder' : 'Start scanning selected folders'"
          >
            <span v-if="cvScanning" class="spinner" />
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              <polyline points="9 12 11 14 15 10"/>
            </svg>
            {{ t('security.scan_now') }}
          </button>
        </div>

        <!-- Scan progress -->
        <div v-if="cvScanProgress" class="cv-scan-progress">
          <div class="cv-scan-prog-bar">
            <div class="cv-scan-prog-fill" :style="{ width: cvScanPct + '%' }" />
          </div>
          <div class="cv-scan-prog-info">
            {{ cvScanProgress.current }} / {{ cvScanProgress.total }} - <span class="td-mono">{{ cvScanProgress.path }}</span>
          </div>
        </div>
        <div v-if="cvLastResult" class="cv-result" :class="cvLastResult.infected > 0 ? 'cv-result--infected' : 'cv-result--clean'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline v-if="cvLastResult.infected === 0" points="20 6 9 17 4 12"/>
            <template v-else><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></template>
          </svg>
          <span v-if="cvLastResult.infected === 0">{{ t('security.scan_complete') }} - {{ cvLastResult.clean }} {{ t('security.files_clean') }}</span>
          <span v-else>⚠ {{ cvLastResult.infected }} {{ t('security.infected_found') }}</span>
        </div>

        <!-- Scan history -->
        <div class="ss-subsection-title">{{ t('security.scan_history') }}</div>
        <div v-if="cvScansLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
        <div v-else-if="cvScans.length === 0" class="ss-empty">No scans yet.</div>
        <table v-else class="ss-table">
          <thead>
            <tr>
              <th>{{ t('security.col_time') }}</th>
              <th>{{ t('security.col_paths') }}</th>
              <th>{{ t('security.col_status') }}</th>
              <th>{{ t('security.col_files') }}</th>
              <th>{{ t('security.col_infected') }}</th>
              <th>{{ t('security.col_by') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in cvScans" :key="s.id">
              <td class="td-time">{{ formatTime(s.created_at) }}</td>
              <td class="td-mono">{{ s.paths || '-' }}</td>
              <td>
                <span class="status-badge" :class="cvScanStatusClass(s.status)">{{ s.status }}</span>
              </td>
              <td>{{ s.total_files }}</td>
              <td>
                <span v-if="s.infected_count > 0" class="cv-infected-count">{{ s.infected_count }}</span>
                <span v-else class="cv-clean-count">0</span>
              </td>
              <td class="td-mono">{{ s.triggered_by || '-' }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Quarantine -->
        <div class="ss-subsection-title">
          {{ t('security.quarantine_title') }}
          <span v-if="cvQuarantine.length > 0" class="cv-q-count">{{ cvQuarantine.length }}</span>
        </div>
        <div class="field-hint cv-section-hint">
          {{ t('security.quarantine_desc') }}
        </div>
        <div v-if="cvQLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
        <div v-else-if="cvQuarantine.length === 0" class="ss-empty">{{ t('security.quarantine_empty') }}</div>
        <table v-else class="ss-table cv-q-table">
          <thead>
            <tr>
              <th>{{ t('security.col_file') }}</th>
              <th>{{ t('security.col_threat') }}</th>
              <th>{{ t('security.col_size') }}</th>
              <th>{{ t('security.quarantined') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in cvQuarantine" :key="q.id" :class="{ 'cv-q-row--missing': !q.file_exists }">
              <td>
                <div class="cv-q-filename">{{ q.filename }}</div>
                <div class="cv-q-origpath">{{ q.original_path }}</div>
              </td>
              <td class="cv-q-threat">{{ q.threat }}</td>
              <td class="td-mono">{{ q.file_size ? formatSize(q.file_size) : '-' }}</td>
              <td class="td-time">{{ formatTime(q.created_at) }}</td>
              <td class="cv-q-actions">
                <button
                  class="action-btn action-btn--ghost action-btn--sm"
                  :disabled="!q.file_exists"
                  :title="q.file_exists ? 'Restore to original location' : 'File missing from quarantine storage'"
                  @click="restoreQuarantine(q.id)"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4"/>
                  </svg>
                  {{ t('security.restore') }}
                </button>
                <button
                  class="action-btn action-btn--danger action-btn--sm"
                  :title="t('common.delete') + ' ' + q.filename"
                  @click="deleteQuarantine(q.id, q.filename)"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                  </svg>
                  {{ t('common.delete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
      </div><!-- /v-show clamav -->
    </div>

    <!-- ── Section D: Network & Access ────────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('network')">
        <span>{{ t('security.network') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.network }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.network">
      <div v-if="netLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>

        <!-- Trusted Proxies -->
        <div class="ss-subsection-title">{{ t('security.trusted_proxies') }}</div>
        <div class="field-hint cv-section-hint">
          {{ t('security.trusted_proxies_desc') }}
        </div>
        <div class="field-group field-group--wide"
          @mouseenter="setHint(t('shint.net_proxies_title'), t('shint.net_proxies_body'))"
          @mouseleave="clearHint()">
          <textarea v-model="net.trusted_proxies" class="field-textarea" rows="2"
            placeholder="192.168.1.10, 10.0.0.0/8" />
        </div>

        <!-- IP Allowlist -->
        <div class="ss-subsection-title">{{ t('security.ip_allowlist') }}</div>
        <div class="cv-toggle-group" style="margin-bottom:8px">
          <div class="cv-trow"
            @mouseenter="setHint(t('shint.net_allowlist_title'), t('shint.net_allowlist_body'))"
            @mouseleave="clearHint()">
            <div class="cv-tinfo">
              <div class="cv-tname">{{ t('security.ip_allowlist_enable') }}</div>
              <div class="cv-tdesc">{{ t('security.ip_allowlist_hint') }}</div>
            </div>
            <label class="cv-tpill">
              <input type="checkbox" v-model="net.ip_allowlist_enabled" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
            </label>
          </div>
        </div>
        <div class="field-group field-group--wide"
          @mouseenter="setHint(t('shint.net_allowed_ips_title'), t('shint.net_allowed_ips_body'))"
          @mouseleave="clearHint()">
          <textarea v-model="net.ip_allowlist" class="field-textarea" rows="3"
            placeholder="192.168.0.0/24, 10.0.0.5" :disabled="!net.ip_allowlist_enabled" />
        </div>

        <!-- CORS -->
        <div class="ss-subsection-title">{{ t('security.cors') }}</div>
        <div class="field-group field-group--wide"
          @mouseenter="setHint(t('shint.net_cors_title'), t('shint.net_cors_body'))"
          @mouseleave="clearHint()">
          <label class="field-label">{{ t('security.cors_label') }}</label>
          <div class="field-hint">{{ t('security.cors_hint') }}</div>
          <textarea v-model="net.cors_origins" class="field-textarea" rows="2"
            placeholder="* or https://app.example.com, https://mobile.example.com" />
        </div>

        <div v-if="netSaved" class="field-ok">{{ t('security.network_saved') }}</div>
        <div class="ss-actions">
          <button class="action-btn action-btn--primary" :disabled="netSaving" @click="saveNet">
            <span v-if="netSaving" class="spinner" />
            <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
            </svg>
            {{ t('common.save') }}
          </button>
        </div>

        <!-- Registration -->
        <div class="ss-subsection-title">{{ t('security.registration') }}</div>
        <div class="cv-action-picker"
          @mouseenter="setHint(t('shint.net_reg_title'), t('shint.net_reg_body'))"
          @mouseleave="clearHint()">
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': net.registration_mode === 'open' }">
            <input type="radio" v-model="net.registration_mode" value="open" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--none">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.reg_open') }}</div>
              <div class="cv-action-hint">{{ t('security.reg_open_hint') }}</div>
            </div>
          </label>
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': net.registration_mode === 'disabled' }">
            <input type="radio" v-model="net.registration_mode" value="disabled" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--delete">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.reg_disabled') }}</div>
              <div class="cv-action-hint">{{ t('security.reg_disabled_hint') }}</div>
            </div>
          </label>
          <label class="cv-action-opt" :class="{ 'cv-action-opt--active': net.registration_mode === 'invite_only' }">
            <input type="radio" v-model="net.registration_mode" value="invite_only" class="cv-action-radio" />
            <div class="cv-action-icon cv-action-icon--quarantine">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </div>
            <div>
              <div class="cv-action-label">{{ t('security.reg_invite') }}</div>
              <div class="cv-action-hint">{{ t('security.reg_invite_hint') }}</div>
            </div>
          </label>
        </div>
        <div class="ss-actions">
          <button class="action-btn action-btn--primary" :disabled="netRegSaving" @click="saveRegistration">
            <span v-if="netRegSaving" class="spinner" />
            <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
            </svg>
            {{ t('common.save') }}
          </button>
          <span v-if="netRegSaved" class="field-ok" style="align-self:center">{{ t('security.saved') }}</span>
        </div>

        <!-- Invite Codes moved to Settings → Users -->

      </template>
      </div><!-- /v-show network -->
    </div>

    <!-- ── Section E: Session Lifetime ─────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('session')">
        <span>{{ t('security.session') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.session }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.session">
        <div class="ss-row"
          @mouseenter="setHint(t('shint.net_session_title'), t('shint.net_session_body'))"
          @mouseleave="clearHint()">
          <div class="ss-row-label">
            <div class="ss-row-title">{{ t('security.stay_logged_in') }}</div>
            <div class="ss-row-desc">{{ t('security.stay_logged_desc') }}</div>
          </div>
          <div class="ss-row-control">
            <div class="session-lifetime-chips">
              <button
                v-for="opt in sessionLifetimeOptions"
                :key="opt.value"
                class="lifetime-chip"
                :class="{ active: sessionLifetimeDays === opt.value }"
                @click="setSessionLifetime(opt.value)"
                :disabled="sessionLifetimeSaving"
              >{{ opt.label }}</button>
            </div>
            <span v-if="sessionLifetimeSaved" class="field-ok" style="margin-left:10px;">Saved</span>
          </div>
        </div>
        <div class="ss-hint-note">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ t('security.currently_set_to') }} <strong>{{ currentLifetimeLabel }}</strong>. {{ t('security.session_note') }}
        </div>
      </div>
    </div>

    <!-- ── Section F: Email Alerts ──────────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('email')">
        <span>{{ t('security.email_alerts') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.email }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.email">
      <div v-if="emailLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>

        <!-- Info note -->
        <div class="email-smtp-note"
          @mouseenter="setHint(t('shint.email_smtp_title'), t('shint.email_smtp_body'))"
          @mouseleave="clearHint()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ t('security.smtp_shared') }}
        </div>

        <!-- Recipient -->
        <div class="fields-grid">
          <div class="field-group"
            @mouseenter="setHint(t('shint.email_recipient_title'), t('shint.email_recipient_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.alert_recipient') }}</label>
            <div class="field-hint">{{ t('security.alert_recipient_hint') }}</div>
            <input v-model="emailCfg.smtp_to" type="email" class="field-input" placeholder="admin@yourdomain.com" />
          </div>
        </div>

        <!-- Alert toggles -->
        <div class="email-alert-toggles">
          <div class="field-row field-row--toggle"
            @mouseenter="setHint(t('shint.email_failed_title'), t('shint.email_failed_body'))"
            @mouseleave="clearHint()">
            <label class="toggle-label">
              <input type="checkbox" v-model="emailCfg.alert_on_failed_login" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              <span class="toggle-text">{{ t('security.alert_failed_login') }}</span>
            </label>
          </div>
          <div class="field-row field-row--toggle"
            @mouseenter="setHint(t('shint.email_newip_title'), t('shint.email_newip_body'))"
            @mouseleave="clearHint()">
            <label class="toggle-label">
              <input type="checkbox" v-model="emailCfg.alert_on_new_ip" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              <span class="toggle-text">{{ t('security.alert_new_ip') }}</span>
            </label>
          </div>
          <div class="field-row field-row--toggle"
            @mouseenter="setHint(t('shint.email_newuser_title'), t('shint.email_newuser_body'))"
            @mouseleave="clearHint()">
            <label class="toggle-label">
              <input type="checkbox" v-model="emailCfg.alert_on_new_user" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              <span class="toggle-text">{{ t('security.alert_new_user') }}</span>
            </label>
          </div>
          <div class="field-row field-row--toggle"
            @mouseenter="setHint(t('shint.email_admin_title'), t('shint.email_admin_body'))"
            @mouseleave="clearHint()">
            <label class="toggle-label">
              <input type="checkbox" v-model="emailCfg.alert_on_new_admin" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              <span class="toggle-text">{{ t('security.alert_admin_promoted') }}</span>
            </label>
          </div>
          <div class="field-row field-row--toggle"
            @mouseenter="setHint(t('shint.email_ban_title'), t('shint.email_ban_body'))"
            @mouseleave="clearHint()">
            <label class="toggle-label">
              <input type="checkbox" v-model="emailCfg.alert_on_brute_force" class="toggle-input" />
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              <span class="toggle-text">{{ t('security.alert_ip_ban') }}</span>
            </label>
          </div>
        </div>

        <div v-if="emailError" class="field-server-error">{{ emailError }}</div>
        <div v-if="emailSaved" class="field-ok">Alert settings saved.</div>
        <div v-if="emailTestOk" class="field-ok">{{ t('security.test_email_ok') }}</div>
        <div v-if="emailTestErr" class="field-server-error">{{ emailTestErr }}</div>

        <div class="ss-actions">
          <button class="action-btn action-btn--ghost" :disabled="emailTesting" @click="testEmail">
            <span v-if="emailTesting" class="spinner" />
            {{ t('security.send_test_email') }}
          </button>
          <button class="action-btn action-btn--primary" :disabled="emailSaving" @click="saveEmail">
            <span v-if="emailSaving" class="spinner" />
            {{ t('common.save') }}
          </button>
        </div>

      </template>
      </div><!-- /v-show email -->
    </div>

    <!-- ── Section G: Security Report ──────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('report')">
        <span>{{ t('security.security_report') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.report }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.report">
      <div v-if="reportLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>

        <!-- Info -->
        <div class="email-smtp-note"
          @mouseenter="setHint(t('shint.report_title'), t('shint.report_body'))"
          @mouseleave="clearHint()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ t('security.report_recipient_info') }}
        </div>

        <!-- Config -->
        <div class="fields-grid">
          <div class="field-group"
            @mouseenter="setHint(t('shint.report_enable_title'), t('shint.report_enable_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.scheduled_report') }}</label>
            <div class="field-hint">{{ t('security.auto_send_summary') }}</div>
            <div class="field-row field-row--toggle" style="margin-top:6px;">
              <label class="toggle-label">
                <input type="checkbox" v-model="reportCfg.enabled" class="toggle-input" />
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                <span class="toggle-text">{{ reportCfg.enabled ? t('security.enabled') : t('security.disabled') }}</span>
              </label>
            </div>
          </div>

          <div class="field-group"
            @mouseenter="setHint(t('shint.report_freq_title'), t('shint.report_freq_body'))"
            @mouseleave="clearHint()">
            <label class="field-label">{{ t('security.report_frequency') }}</label>
            <div class="field-hint">{{ t('security.report_frequency_hint') }}</div>
            <select v-model="reportCfg.frequency" class="field-input" style="margin-top:6px;">
              <option value="weekly">{{ t('security.weekly') }}</option>
              <option value="monthly">{{ t('security.monthly') }}</option>
            </select>
          </div>
        </div>

        <div v-if="reportLastSent" class="sr-last-sent">
          {{ t('security.last_sent', { date: reportLastSent }) }}
        </div>

        <div v-if="reportError" class="field-server-error">{{ reportError }}</div>
        <div v-if="reportSaved" class="field-ok">{{ t('security.report_saved') }}</div>
        <div v-if="reportSentOk" class="field-ok">{{ t('security.report_sent_ok') }}</div>
        <div v-if="reportSentErr" class="field-server-error">{{ reportSentErr }}</div>

        <div class="ss-actions">
          <button class="action-btn action-btn--ghost" :disabled="reportSending" @click="sendReportNow">
            <span v-if="reportSending" class="spinner" />
            {{ t('security.send_now') }}
          </button>
          <button class="action-btn action-btn--primary" :disabled="reportSaving" @click="saveReport">
            <span v-if="reportSaving" class="spinner" />
            {{ t('common.save') }}
          </button>
        </div>

        <!-- Period preview -->
        <div class="sr-preview-title">
          {{ reportCfg.frequency === 'weekly' ? t('security.current_7day_summary') : t('security.current_30day_summary') }}
          <button class="action-btn action-btn--ghost action-btn--sm sr-refresh-btn" @click="loadReportPreview" :disabled="previewLoading">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('security.refresh') }}
          </button>
        </div>

        <div v-if="previewLoading" class="ss-loading"><span class="spinner" /> {{ t('security.loading_preview') }}</div>
        <div v-else-if="previewData" class="sr-preview-grid">
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.successful_logins') }}</div>
            <div class="sr-stat-value sr-stat--green">{{ previewData.logins_ok }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.failed_logins') }}</div>
            <div class="sr-stat-value" :class="previewData.logins_failed > 0 ? 'sr-stat--amber' : ''">{{ previewData.logins_failed }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.blocked_attempts') }}</div>
            <div class="sr-stat-value" :class="previewData.logins_blocked > 0 ? 'sr-stat--red' : ''">{{ previewData.logins_blocked }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.active_users') }}</div>
            <div class="sr-stat-value">{{ previewData.unique_users }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.new_registrations') }}</div>
            <div class="sr-stat-value" :class="previewData.new_users > 0 ? 'sr-stat--green' : ''">{{ previewData.new_users }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.downloads') }}</div>
            <div class="sr-stat-value">{{ previewData.downloads_count }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.data_transferred') }}</div>
            <div class="sr-stat-value">{{ fmtBytes(previewData.downloads_bytes) }}</div>
          </div>
          <div class="sr-stat-card">
            <div class="sr-stat-label">{{ t('security.threats_detected') }}</div>
            <div class="sr-stat-value" :class="previewData.threats_found > 0 ? 'sr-stat--red' : 'sr-stat--green'">
              {{ previewData.threats_found > 0 ? previewData.threats_found : t('security.none_clear') + ' ✓' }}
            </div>
          </div>
        </div>

      </template>
      </div><!-- /v-show report -->
    </div>

    <!-- ── Section H: Single Sign-On ────────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('sso')">
        <span>{{ t('security.sso') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.sso }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.sso">
      <div v-if="ssoLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>

        <!-- Login mode -->
        <div class="field-group"
          @mouseenter="setHint(t('shint.sso_mode_title'), t('shint.sso_mode_body'))"
          @mouseleave="clearHint()">
          <label class="field-label">{{ t('security.login_mode') }}</label>
          <div class="sso-mode-cards">
            <label class="sso-mode-card" :class="{ 'sso-mode-card--active': ssoCfg.login_mode === 'alongside' }">
              <input type="radio" v-model="ssoCfg.login_mode" value="alongside" class="sr-only" />
              <div class="sso-mode-title">{{ t('security.sso_alongside') }}</div>
              <div class="sso-mode-desc">{{ t('security.sso_alongside_desc') }}</div>
            </label>
            <label class="sso-mode-card" :class="{ 'sso-mode-card--active': ssoCfg.login_mode === 'replace' }">
              <input type="radio" v-model="ssoCfg.login_mode" value="replace" class="sr-only" />
              <div class="sso-mode-title">{{ t('security.sso_replace') }}</div>
              <div class="sso-mode-desc">{{ t('security.sso_replace_desc') }}</div>
            </label>
          </div>
        </div>

        <!-- ── OIDC ──────────────────────────────────────────────────── -->
        <div class="sso-provider-card">
          <div class="sso-provider-header" @click="toggleSection('sso_oidc')">
            <div class="sso-provider-name">
              <div class="sso-provider-dot" :class="ssoCfg.oidc_enabled ? 'sso-dot--on' : 'sso-dot--off'" />
              {{ t('security.sso_oidc') }}
              <span class="sso-provider-hint">{{ t('security.sso_oidc_hint') }}</span>
            </div>
            <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.sso_oidc }"
              width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>
          <div v-show="!collapsed.sso_oidc" class="sso-provider-fields">
            <div class="field-row field-row--toggle"
              @mouseenter="setHint(t('shint.sso_oidc_enable_title'), t('shint.sso_oidc_enable_body'))"
              @mouseleave="clearHint()">
              <label class="toggle-label">
                <input type="checkbox" v-model="ssoCfg.oidc_enabled" class="toggle-input" />
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                <span class="toggle-text">{{ t('common.enable') }}</span>
              </label>
            </div>
            <div class="fields-grid">
              <div class="field-group field-group--wide"
                @mouseenter="setHint(t('shint.sso_discovery_title'), t('shint.sso_discovery_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('security.discovery_url') }}</label>
                <input v-model="ssoCfg.oidc_discovery_url" type="url" class="field-input" placeholder="https://keycloak.example.com/realms/myrealm/.well-known/openid-configuration" />
              </div>
              <div class="field-group"
                @mouseenter="setHint(t('shint.sso_provider_name_title'), t('shint.sso_provider_name_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('security.button_label') }}</label>
                <input v-model="ssoCfg.oidc_provider_name" type="text" class="field-input" placeholder="Keycloak" />
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('security.client_id') }}</label>
                <input v-model="ssoCfg.oidc_client_id" type="text" class="field-input" placeholder="gamesdownloader" />
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('security.client_secret') }}</label>
                <input v-model="ssoCfg.oidc_client_secret" type="password" class="field-input" autocomplete="off" placeholder="••••••••" />
              </div>
              <div class="field-group field-group--wide"
                @mouseenter="setHint(t('shint.sso_scopes_title'), t('shint.sso_scopes_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('security.scopes') }}</label>
                <input v-model="ssoCfg.oidc_scopes" type="text" class="field-input" placeholder="openid email profile" />
              </div>
            </div>
            <div class="sso-callback-info"
              @mouseenter="setHint(t('shint.sso_redirect_title'), t('shint.sso_redirect_body'))"
              @mouseleave="clearHint()">
              {{ t('security.redirect_uri') }} <code>{{ origin }}/api/auth/sso/oidc/callback</code>
            </div>
          </div>
        </div>

        <!-- ── Google ─────────────────────────────────────────────────── -->
        <div class="sso-provider-card">
          <div class="sso-provider-header" @click="toggleSection('sso_google')">
            <div class="sso-provider-name">
              <div class="sso-provider-dot" :class="ssoCfg.oauth_google_enabled ? 'sso-dot--on' : 'sso-dot--off'" />
              Google
            </div>
            <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.sso_google }"
              width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>
          <div v-show="!collapsed.sso_google" class="sso-provider-fields">
            <div class="field-row field-row--toggle">
              <label class="toggle-label">
                <input type="checkbox" v-model="ssoCfg.oauth_google_enabled" class="toggle-input" />
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                <span class="toggle-text">{{ t('common.enable') }}</span>
              </label>
            </div>
            <div class="fields-grid">
              <div class="field-group">
                <label class="field-label">{{ t('security.client_id') }}</label>
                <input v-model="ssoCfg.oauth_google_client_id" type="text" class="field-input" placeholder="123456789.apps.googleusercontent.com" />
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('security.client_secret') }}</label>
                <input v-model="ssoCfg.oauth_google_client_secret" type="password" class="field-input" autocomplete="off" placeholder="••••••••" />
              </div>
            </div>
            <div class="sso-callback-info">
              {{ t('security.redirect_uri') }} <code>{{ origin }}/api/auth/sso/google/callback</code>
            </div>
          </div>
        </div>

        <!-- ── GitHub ─────────────────────────────────────────────────── -->
        <div class="sso-provider-card">
          <div class="sso-provider-header" @click="toggleSection('sso_github')">
            <div class="sso-provider-name">
              <div class="sso-provider-dot" :class="ssoCfg.oauth_github_enabled ? 'sso-dot--on' : 'sso-dot--off'" />
              GitHub
            </div>
            <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.sso_github }"
              width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>
          <div v-show="!collapsed.sso_github" class="sso-provider-fields">
            <div class="field-row field-row--toggle">
              <label class="toggle-label">
                <input type="checkbox" v-model="ssoCfg.oauth_github_enabled" class="toggle-input" />
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                <span class="toggle-text">{{ t('common.enable') }}</span>
              </label>
            </div>
            <div class="fields-grid">
              <div class="field-group">
                <label class="field-label">{{ t('security.client_id') }}</label>
                <input v-model="ssoCfg.oauth_github_client_id" type="text" class="field-input" placeholder="Ov23li…" />
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('security.client_secret') }}</label>
                <input v-model="ssoCfg.oauth_github_client_secret" type="password" class="field-input" autocomplete="off" placeholder="••••••••" />
              </div>
            </div>
            <div class="sso-callback-info">
              {{ t('security.redirect_uri') }} <code>{{ origin }}/api/auth/sso/github/callback</code>
            </div>
          </div>
        </div>

        <!-- ── Microsoft ──────────────────────────────────────────────── -->
        <div class="sso-provider-card">
          <div class="sso-provider-header" @click="toggleSection('sso_microsoft')">
            <div class="sso-provider-name">
              <div class="sso-provider-dot" :class="ssoCfg.oauth_microsoft_enabled ? 'sso-dot--on' : 'sso-dot--off'" />
              Microsoft / Azure AD
            </div>
            <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.sso_microsoft }"
              width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>
          <div v-show="!collapsed.sso_microsoft" class="sso-provider-fields">
            <div class="field-row field-row--toggle">
              <label class="toggle-label">
                <input type="checkbox" v-model="ssoCfg.oauth_microsoft_enabled" class="toggle-input" />
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                <span class="toggle-text">{{ t('common.enable') }}</span>
              </label>
            </div>
            <div class="fields-grid">
              <div class="field-group">
                <label class="field-label">{{ t('security.client_id') }}</label>
                <input v-model="ssoCfg.oauth_microsoft_client_id" type="text" class="field-input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('security.client_secret') }}</label>
                <input v-model="ssoCfg.oauth_microsoft_client_secret" type="password" class="field-input" autocomplete="off" placeholder="••••••••" />
              </div>
              <div class="field-group"
                @mouseenter="setHint(t('shint.sso_tenant_title'), t('shint.sso_tenant_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('security.tenant') }}</label>
                <input v-model="ssoCfg.oauth_microsoft_tenant" type="text" class="field-input" placeholder="common" />
              </div>
            </div>
            <div class="sso-callback-info">
              {{ t('security.redirect_uri') }} <code>{{ origin }}/api/auth/sso/microsoft/callback</code>
            </div>
          </div>
        </div>

        <div v-if="ssoError" class="field-server-error">{{ ssoError }}</div>
        <div v-if="ssoSaved" class="field-ok">{{ t('security.sso_saved') }}</div>
        <div class="ss-actions" style="margin-top:12px;">
          <button class="action-btn action-btn--primary" :disabled="ssoSaving" @click="saveSso">
            <span v-if="ssoSaving" class="spinner" />
            {{ t('common.save') }}
          </button>
        </div>

        <div class="sso-note">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ t('security.sso_note') }}
        </div>

      </template>
      </div><!-- /v-show sso -->
    </div>

    <!-- ── Section B: Audit Log ─────────────────────────────────────────────── -->
    <div class="ss-section">
      <div class="ss-section-title ss-section-title--collapsible" @click="toggleSection('audit')">
        <span>{{ t('security.audit') }}</span>
        <svg class="ss-chevron" :class="{ 'ss-chevron--open': !collapsed.audit }"
          width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-show="!collapsed.audit">
      <div class="audit-toolbar">
        <input
          v-model="auditFilter"
          class="field-input audit-filter"
          :placeholder="t('security.filter_by_action')"
          @keydown.enter="loadAudit(0)"
          @mouseenter="setHint(t('shint.audit_filter_title'), t('shint.audit_filter_body'))"
          @mouseleave="clearHint()"
        />
        <button class="action-btn action-btn--ghost" @click="loadAudit(0)"
          @mouseenter="setHint(t('shint.audit_search_title'), t('shint.audit_search_body'))"
          @mouseleave="clearHint()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          {{ t('common.search') }}
        </button>
        <button class="action-btn action-btn--danger" @click="confirmClearAudit"
          @mouseenter="setHint(t('shint.audit_clear_title'), t('shint.audit_clear_body'))"
          @mouseleave="clearHint()">{{ t('security.clear_all') }}</button>
      </div>

      <div v-if="auditLoading" class="ss-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <div v-else-if="auditItems.length === 0" class="ss-empty">{{ t('security.no_audit_entries') }}</div>
      <template v-else>
        <table class="ss-table ss-table--audit">
          <thead>
            <tr>
              <th>{{ t('security.col_time') }}</th>
              <th>{{ t('security.col_action') }}</th>
              <th>{{ t('security.col_user') }}</th>
              <th>{{ t('security.col_ip') }}</th>
              <th>{{ t('security.col_status') }}</th>
              <th>{{ t('security.col_details') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in auditItems" :key="item.id">
              <td class="td-time">{{ formatTime(item.created_at) }}</td>
              <td>
                <span class="action-badge" :class="`action-badge--${item.action}`">
                  <component :is="actionIcon(item.action)" class="badge-icon" />
                  {{ item.action }}
                </span>
              </td>
              <td class="td-mono">{{ item.username || '-' }}</td>
              <td class="td-mono">{{ item.ip_address || '-' }}</td>
              <td>
                <span class="status-badge" :class="`status-badge--${item.status}`">{{ item.status }}</span>
              </td>
              <td class="td-details">{{ item.details || '' }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div class="pagination">
          <button class="action-btn action-btn--ghost action-btn--sm" :disabled="auditOffset === 0" @click="loadAudit(auditOffset - auditLimit)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            {{ t('security.prev') }}
          </button>
          <span class="pagination-info">{{ auditOffset + 1 }}–{{ Math.min(auditOffset + auditLimit, auditTotal) }} of {{ auditTotal }}</span>
          <button class="action-btn action-btn--ghost action-btn--sm" :disabled="auditOffset + auditLimit >= auditTotal" @click="loadAudit(auditOffset + auditLimit)">
            {{ t('security.next') }}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        </div>
      </template>
      </div><!-- /v-show audit -->
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick, h, computed } from 'vue'
import client from '@/services/api/client'
import { useSocketStore } from '@/stores/socket'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

const { t } = useI18n()
import { useDialog } from '@/composables/useDialog'

const { gdConfirm, gdAlert } = useDialog()

// ── Collapsible sections ───────────────────────────────────────────────────────

function _loadCollapsed(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem('ss_collapsed') || '{}') } catch { return {} }
}
const collapsed = reactive<Record<string, boolean>>(_loadCollapsed())

function toggleSection(key: string) {
  collapsed[key] = !collapsed[key]
  try { localStorage.setItem('ss_collapsed', JSON.stringify({ ...collapsed })) } catch {}
}

// ── Brute-force ───────────────────────────────────────────────────────────────

interface BfConfig {
  enabled: boolean
  max_attempts: number
  window_seconds: number
  ban_seconds: number
  whitelist: string
}

const bf = reactive<BfConfig>({
  enabled: true,
  max_attempts: 5,
  window_seconds: 300,
  ban_seconds: 900,
  whitelist: '',
})

const bfLoading = ref(true)
const bfSaving  = ref(false)
const bfSaved   = ref(false)
const bfError   = ref('')

interface BannedEntry { ip: string; remaining_seconds: number }
const bannedIps     = ref<BannedEntry[]>([])
const bannedLoading = ref(false)

async function loadBf() {
  bfLoading.value = true
  try {
    const data = await client.get('/settings/security/brute-force').then(r => r.data)
    Object.assign(bf, data)
  } catch { /* ignore */ } finally {
    bfLoading.value = false
  }
}

async function loadBanned() {
  bannedLoading.value = true
  try {
    bannedIps.value = await client.get('/settings/security/banned-ips').then(r => r.data)
  } catch { /* ignore */ } finally {
    bannedLoading.value = false
  }
}

async function saveBf() {
  bfSaving.value = true
  bfError.value  = ''
  bfSaved.value  = false
  try {
    await client.post('/settings/security/brute-force', { ...bf })
    bfSaved.value = true
    setTimeout(() => { bfSaved.value = false }, 3000)
  } catch (e: any) {
    bfError.value = e?.response?.data?.detail || 'Failed to save.'
  } finally {
    bfSaving.value = false
  }
}

async function unban(ip: string) {
  const ok = await gdConfirm(t('security.unban_confirm', `Unban IP address ${ip}?`), { title: t('security.unban', 'Unban'), confirmText: t('security.unban', 'Unban') })
  if (!ok) return
  try {
    await client.delete(`/settings/security/banned-ips/${encodeURIComponent(ip)}`)
    await loadBanned()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to unban.', { title: 'Error', danger: true })
  }
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

interface AuditItem {
  id: number
  action: string
  username: string | null
  ip_address: string | null
  details: string | null
  status: string
  created_at: string | null
}

const auditItems   = ref<AuditItem[]>([])
const auditTotal   = ref(0)
const auditOffset  = ref(0)
const auditLimit   = 50
const auditFilter  = ref('')
const auditLoading = ref(false)

async function loadAudit(offset = 0) {
  auditLoading.value = true
  auditOffset.value  = Math.max(0, offset)
  try {
    const data = await client.get('/settings/security/audit-log', {
      params: { limit: auditLimit, offset: auditOffset.value, filter: auditFilter.value },
    }).then(r => r.data)
    auditItems.value = data.items
    auditTotal.value = data.total
  } catch { /* ignore */ } finally {
    auditLoading.value = false
  }
}

async function confirmClearAudit() {
  if (!await gdConfirm('Delete all audit log entries? This cannot be undone.', { title: 'Clear Audit Log', danger: true, confirmText: 'Delete All' })) return
  try {
    await client.delete('/settings/security/audit-log')
    await loadAudit(0)
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to clear.', { title: 'Error', danger: true })
  }
}

function getLocale(): string {
  return localStorage.getItem('gd3_locale') || navigator.language || 'en'
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString(getLocale())
  } catch {
    return iso
  }
}

// Action badge icons
function actionIcon(action: string) {
  const props = { width: 11, height: 11, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }
  if (action === 'login_ok') {
    return () => h('svg', props, [h('polyline', { points: '20 6 9 17 4 12' })])
  }
  if (action === 'login_fail') {
    return () => h('svg', props, [
      h('circle', { cx: 12, cy: 12, r: 10 }),
      h('line', { x1: 15, y1: 9, x2: 9, y2: 15 }),
      h('line', { x1: 9, y1: 9, x2: 15, y2: 15 }),
    ])
  }
  if (action === 'login_blocked') {
    return () => h('svg', props, [
      h('circle', { cx: 12, cy: 12, r: 10 }),
      h('line', { x1: 4.93, y1: 4.93, x2: 19.07, y2: 19.07 }),
    ])
  }
  if (action === 'unban_ip') {
    return () => h('svg', props, [h('path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' })])
  }
  if (action === 'audit_log_cleared') {
    return () => h('svg', props, [
      h('polyline', { points: '3 6 5 6 21 6' }),
      h('path', { d: 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2' }),
    ])
  }
  // Default icon
  return () => h('svg', props, [h('circle', { cx: 12, cy: 12, r: 5 })])
}

// ── ClamAV ────────────────────────────────────────────────────────────────────

interface CvStatus {
  running: boolean
  version: string | null
  db_version: string | null
  db_date: string | null
  error: string | null
}
interface CvConfig {
  enabled: boolean
  auto_scan_upload: boolean
  auto_scan_download: boolean
  action: 'none' | 'quarantine' | 'delete'
  auto_update: boolean
  update_interval_hours: number
}
interface QuarantineEntry {
  id: number
  filename: string
  original_path: string
  quarantine_path: string
  threat: string
  file_size: number | null
  scan_id: number | null
  triggered_by: string | null
  created_at: string | null
  file_exists: boolean
}
interface CvUpdateLine { msg: string; status: string }
interface CvScan {
  id: number; scan_type: string; paths: string | null; status: string
  total_files: number; infected_count: number; clean_count: number; error_count: number
  infected_files: any[]; triggered_by: string | null; created_at: string | null
}

const socketStore = useSocketStore()
const { setHint, clearHint } = useSettingsHint()
const cvLoading      = ref(true)
const cvStatus       = ref<CvStatus>({ running: false, version: null, db_version: null, db_date: null, error: null })
const cv             = reactive<CvConfig>({ enabled: true, auto_scan_upload: false, auto_scan_download: false, action: 'quarantine', auto_update: false, update_interval_hours: 24 })
const cvLastAutoUpdate = ref<string | null>(null)
const cvConfigSaving = ref(false)
const cvSaved        = ref(false)
const cvAvailablePaths = ref<string[]>(['gog', 'custom', 'downloads'])

// Human-readable labels and descriptions for each scannable path key
const cvPathMeta: Record<string, { label: string; desc: string }> = {
  gog:       { label: t('shint.cv_path_gog'),       desc: t('shint.cv_path_gog_desc') },
  custom:    { label: t('shint.cv_path_custom'),     desc: t('shint.cv_path_custom_desc') },
  downloads: { label: t('shint.cv_path_downloads'),  desc: t('shint.cv_path_downloads_desc') },
}
const cvSelectedPaths  = ref<string[]>(['gog', 'custom', 'downloads'])

const cvUpdating   = ref(false)
const cvUpdateLog  = ref<CvUpdateLine[]>([])
const cvLogEl      = ref<HTMLElement | null>(null)

const cvScanning      = ref(false)
const cvActiveScanId  = ref<number | null>(null)
const cvScanProgress  = ref<{ current: number; total: number; path: string } | null>(null)
const cvLastResult    = ref<{ infected: number; clean: number } | null>(null)
const cvScanPct       = computed(() => {
  if (!cvScanProgress.value || !cvScanProgress.value.total) return 0
  return Math.round((cvScanProgress.value.current / cvScanProgress.value.total) * 100)
})

const cvScans        = ref<CvScan[]>([])
const cvScansLoading = ref(false)

async function loadCvStatus() {
  cvLoading.value = true
  try {
    const data = await client.get('/settings/security/clamav/status').then(r => r.data)
    cvStatus.value = {
      running:    data.running,
      version:    data.version,
      db_version: data.db_version,
      db_date:    data.db_date,
      error:      data.error,
    }
    if (data.config) {
      Object.assign(cv, data.config)
      cvLastAutoUpdate.value = data.config.last_auto_update || null
    }
    if (data.scannable_paths) cvAvailablePaths.value = data.scannable_paths
  } catch { /* ignore */ } finally {
    cvLoading.value = false
  }
}

async function saveCvConfig() {
  cvConfigSaving.value = true
  cvSaved.value = false
  try {
    await client.post('/settings/security/clamav/config', { ...cv })
    cvSaved.value = true
    setTimeout(() => { cvSaved.value = false }, 3000)
  } catch { /* ignore */ } finally {
    cvConfigSaving.value = false
  }
}

async function updateDefinitions() {
  cvUpdating.value = true
  cvUpdateLog.value = []
  try {
    await client.post('/settings/security/clamav/update-definitions')
  } catch (e: any) {
    cvUpdateLog.value.push({ msg: e?.response?.data?.detail || 'Request failed', status: 'error' })
    cvUpdating.value = false
  }
  // Progress comes via Socket.IO: clamav:update_progress
}

async function startScan() {
  if (cvSelectedPaths.value.length === 0) return
  if (cv.action === 'delete') {
    const ok = await gdConfirm(t('security.scan_delete_warn', 'ClamAV is set to DELETE infected files permanently. Proceed with scan?'), { title: t('security.manual_scan', 'Manual Scan'), danger: true, confirmText: t('security.scan_now', 'Scan Now') })
    if (!ok) return
  }
  cvScanning.value = true
  cvScanProgress.value = null
  cvLastResult.value = null
  try {
    const data = await client.post('/settings/security/clamav/scan', {
      paths: cvSelectedPaths.value,
    }).then(r => r.data)
    cvActiveScanId.value = data.scan_id
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to start scan.', { title: 'Scan Error', danger: true })
    cvScanning.value = false
  }
}

async function loadCvScans() {
  cvScansLoading.value = true
  try {
    cvScans.value = await client.get('/settings/security/clamav/scans', { params: { limit: 20 } }).then(r => r.data)
  } catch { /* ignore */ } finally {
    cvScansLoading.value = false
  }
}

// ── Quarantine ────────────────────────────────────────────────────────────────

const cvQuarantine = ref<QuarantineEntry[]>([])
const cvQLoading   = ref(false)

async function loadQuarantine() {
  cvQLoading.value = true
  try {
    cvQuarantine.value = await client.get('/settings/security/clamav/quarantine').then(r => r.data)
  } catch { /* ignore */ } finally {
    cvQLoading.value = false
  }
}

async function restoreQuarantine(id: number) {
  try {
    const data = await client.post(`/settings/security/clamav/quarantine/${id}/restore`).then(r => r.data)
    await loadQuarantine()
    await gdAlert(`File restored to:\n${data.restored_to}`, { title: 'Restored', confirmText: 'OK' })
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Restore failed.', { title: 'Error', danger: true })
  }
}

async function deleteQuarantine(id: number, filename: string) {
  if (!await gdConfirm(`Permanently delete "${filename}"?\n\nThis cannot be undone.`, { title: 'Delete File', danger: true, confirmText: 'Delete' })) return
  try {
    await client.delete(`/settings/security/clamav/quarantine/${id}`)
    await loadQuarantine()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Delete failed.', { title: 'Error', danger: true })
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function cvScanStatusClass(status: string) {
  if (status === 'complete') return 'status-badge--ok'
  if (status === 'error')    return 'status-badge--fail'
  if (status === 'running')  return 'status-badge--warn'
  return ''
}

// Socket.IO event handlers
function onCvUpdateProgress(data: { status: string; message: string }) {
  cvUpdateLog.value.push({ msg: data.message, status: data.status })
  if (data.status === 'complete' || data.status === 'error') {
    cvUpdating.value = false
    if (data.status === 'complete') loadCvStatus()
  }
  // Auto-scroll log
  nextTick(() => {
    if (cvLogEl.value) cvLogEl.value.scrollTop = cvLogEl.value.scrollHeight
  })
}

function onCvScanProgress(data: { scan_id: number; current: number; total: number; path: string }) {
  if (cvActiveScanId.value !== data.scan_id) return
  cvScanProgress.value = { current: data.current, total: data.total, path: data.path }
}

function onCvScanComplete(data: { scan_id: number; total: number; infected: number; clean: number; errors: number }) {
  if (cvActiveScanId.value !== data.scan_id && data.scan_id !== undefined) return
  cvScanning.value = false
  cvScanProgress.value = null
  cvLastResult.value = { infected: data.infected ?? 0, clean: data.clean ?? 0 }
  loadCvScans()
  loadQuarantine()
}

// ── Network & Access ──────────────────────────────────────────────────────────

interface NetConfig {
  trusted_proxies:      string
  ip_allowlist_enabled: boolean
  ip_allowlist:         string
  cors_origins:         string
}

interface InviteCode {
  id:         number
  code:       string
  created_by: string | null
  note:       string | null
  max_uses:   number
  use_count:  number
  expires_at: string | null
  is_active:  boolean
}

const net = reactive<NetConfig & { registration_mode: string }>({
  trusted_proxies:      '',
  ip_allowlist_enabled: false,
  ip_allowlist:         '',
  cors_origins:         '',
  registration_mode:    'open',
})

const netLoading    = ref(true)
const netSaving     = ref(false)
const netSaved      = ref(false)
const netRegSaving  = ref(false)
const netRegSaved   = ref(false)

const invites        = ref<InviteCode[]>([])
const inviteLoading  = ref(false)
const inviteCreating = ref(false)
const inviteCopied   = ref(false)

const newInvite = reactive({ max_uses: 1, expires_in_hours: null as number | null, note: '' })

async function loadNet() {
  netLoading.value = true
  try {
    const [cfg, reg] = await Promise.all([
      client.get('/settings/security/network/config').then(r => r.data),
      client.get('/settings/security/network/registration').then(r => r.data),
    ])
    net.trusted_proxies      = cfg.trusted_proxies      ?? ''
    net.ip_allowlist_enabled = cfg.ip_allowlist_enabled ?? false
    net.ip_allowlist         = cfg.ip_allowlist         ?? ''
    net.cors_origins         = cfg.cors_origins         ?? ''
    net.registration_mode    = reg.mode                  ?? 'open'
  } catch { /* ignore */ } finally {
    netLoading.value = false
  }
}

async function saveNet() {
  netSaving.value = true
  netSaved.value  = false
  try {
    await client.post('/settings/security/network/config', {
      trusted_proxies:      net.trusted_proxies,
      ip_allowlist_enabled: net.ip_allowlist_enabled,
      ip_allowlist:         net.ip_allowlist,
      cors_origins:         net.cors_origins,
    })
    netSaved.value = true
    setTimeout(() => { netSaved.value = false }, 3000)
  } catch { /* ignore */ } finally {
    netSaving.value = false
  }
}

async function saveRegistration() {
  netRegSaving.value = true
  netRegSaved.value  = false
  try {
    await client.post('/settings/security/network/registration', {
      mode: net.registration_mode,
    })
    netRegSaved.value = true
    setTimeout(() => { netRegSaved.value = false }, 3000)
  } catch { /* ignore */ } finally {
    netRegSaving.value = false
  }
}

async function loadInvites() {
  inviteLoading.value = true
  try {
    invites.value = await client.get('/settings/security/network/invites').then(r => r.data)
  } catch { /* ignore */ } finally {
    inviteLoading.value = false
  }
}

async function createInvite() {
  inviteCreating.value = true
  try {
    await client.post('/settings/security/network/invites', {
      max_uses:        newInvite.max_uses,
      expires_in_hours: newInvite.expires_in_hours || null,
      note:            newInvite.note || null,
    })
    newInvite.max_uses = 1
    newInvite.expires_in_hours = null
    newInvite.note = ''
    await loadInvites()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to create invite code.', { title: 'Error', danger: true })
  } finally {
    inviteCreating.value = false
  }
}

async function deleteInvite(id: number) {
  if (!await gdConfirm('Delete this invite code?', { title: 'Delete Invite', danger: true, confirmText: 'Delete' })) return
  try {
    await client.delete(`/settings/security/network/invites/${id}`)
    await loadInvites()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Failed to delete.', { title: 'Error', danger: true })
  }
}

async function copyInviteCode(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    inviteCopied.value = true
    setTimeout(() => { inviteCopied.value = false }, 2500)
  } catch {
    await gdAlert(`Could not access clipboard.\n\nYour invite code:\n${code}`, { title: 'Copy Code', confirmText: 'Close' })
  }
}

// ── Email alerts ──────────────────────────────────────────────────────────────

interface EmailConfig {
  smtp_to:               string
  alert_on_failed_login: boolean
  alert_on_new_ip:       boolean
  alert_on_new_user:     boolean
  alert_on_new_admin:    boolean
  alert_on_brute_force:  boolean
}

const emailCfg = reactive<EmailConfig>({
  smtp_to:               '',
  alert_on_failed_login: true,
  alert_on_new_ip:       true,
  alert_on_new_user:     true,
  alert_on_new_admin:    true,
  alert_on_brute_force:  true,
})

const emailLoading  = ref(true)
const emailSaving   = ref(false)
const emailSaved    = ref(false)
const emailError    = ref('')
const emailTesting  = ref(false)
const emailTestOk   = ref(false)
const emailTestErr  = ref('')

async function loadEmail() {
  emailLoading.value = true
  try {
    const r = await client.get('/settings/security/email')
    Object.assign(emailCfg, r.data)
  } catch { /* ignore */ } finally {
    emailLoading.value = false
  }
}

async function saveEmail() {
  emailSaving.value = true
  emailSaved.value  = false
  emailError.value  = ''
  try {
    await client.post('/settings/security/email', {
      smtp_to:               emailCfg.smtp_to,
      alert_on_failed_login: emailCfg.alert_on_failed_login,
      alert_on_new_ip:       emailCfg.alert_on_new_ip,
      alert_on_new_user:     emailCfg.alert_on_new_user,
      alert_on_new_admin:    emailCfg.alert_on_new_admin,
      alert_on_brute_force:  emailCfg.alert_on_brute_force,
    })
    emailSaved.value = true
    setTimeout(() => { emailSaved.value = false }, 3000)
  } catch (e: any) {
    emailError.value = e?.response?.data?.detail || 'Failed to save alert settings.'
  } finally {
    emailSaving.value = false
  }
}

async function testEmail() {
  emailTesting.value = true
  emailTestOk.value  = false
  emailTestErr.value = ''
  try {
    await client.post('/settings/security/email/test')
    emailTestOk.value = true
    setTimeout(() => { emailTestOk.value = false }, 5000)
  } catch (e: any) {
    emailTestErr.value = e?.response?.data?.detail || t('security.test_email_fail')
    setTimeout(() => { emailTestErr.value = '' }, 8000)
  } finally {
    emailTesting.value = false
  }
}

// ── Sessions ──────────────────────────────────────────────────────────────────

const sessionLifetimeOptions = computed(() => [
  { value: 1,   label: t('security.1_day') },
  { value: 7,   label: t('security.7_days') },
  { value: 14,  label: t('security.14_days') },
  { value: 30,  label: t('security.30_days') },
  { value: 90,  label: t('security.3_months') },
  { value: 365, label: t('security.1_year') },
])

const sessionLifetimeDays   = ref(7)
const sessionLifetimeSaving = ref(false)
const sessionLifetimeSaved  = ref(false)

const currentLifetimeLabel = computed(() => {
  const opt = sessionLifetimeOptions.value.find(o => o.value === sessionLifetimeDays.value)
  return opt ? opt.label : `${sessionLifetimeDays.value}`
})

async function loadSessionLifetime() {
  try {
    const r = await client.get('/settings/security/sessions/config')
    sessionLifetimeDays.value = r.data.session_lifetime_days
  } catch { /* ignore */ }
}

async function setSessionLifetime(days: number) {
  sessionLifetimeDays.value = days
  sessionLifetimeSaving.value = true
  sessionLifetimeSaved.value  = false
  try {
    await client.post('/settings/security/sessions/config', { session_lifetime_days: days })
    sessionLifetimeSaved.value = true
    setTimeout(() => { sessionLifetimeSaved.value = false }, 2500)
  } catch { /* ignore */ } finally {
    sessionLifetimeSaving.value = false
  }
}

// ── SSO ───────────────────────────────────────────────────────────────────────

const origin = window.location.origin

interface SsoCfg {
  login_mode: string
  oidc_enabled: boolean; oidc_provider_name: string; oidc_discovery_url: string
  oidc_client_id: string; oidc_client_secret: string; oidc_scopes: string
  oauth_google_enabled: boolean; oauth_google_client_id: string; oauth_google_client_secret: string
  oauth_github_enabled: boolean; oauth_github_client_id: string; oauth_github_client_secret: string
  oauth_microsoft_enabled: boolean; oauth_microsoft_client_id: string
  oauth_microsoft_client_secret: string; oauth_microsoft_tenant: string
}

const ssoCfg = reactive<SsoCfg>({
  login_mode: 'alongside',
  oidc_enabled: false, oidc_provider_name: '', oidc_discovery_url: '',
  oidc_client_id: '', oidc_client_secret: '', oidc_scopes: 'openid email profile',
  oauth_google_enabled: false, oauth_google_client_id: '', oauth_google_client_secret: '',
  oauth_github_enabled: false, oauth_github_client_id: '', oauth_github_client_secret: '',
  oauth_microsoft_enabled: false, oauth_microsoft_client_id: '',
  oauth_microsoft_client_secret: '', oauth_microsoft_tenant: 'common',
})
const ssoLoading = ref(true)
const ssoSaving  = ref(false)
const ssoSaved   = ref(false)
const ssoError   = ref('')

async function loadSso() {
  ssoLoading.value = true
  try {
    const r = await client.get('/settings/security/sso')
    Object.assign(ssoCfg, r.data)
  } catch { /* ignore */ } finally {
    ssoLoading.value = false
  }
}

async function saveSso() {
  ssoSaving.value = true
  ssoSaved.value  = false
  ssoError.value  = ''
  try {
    await client.post('/settings/security/sso', { ...ssoCfg })
    ssoSaved.value = true
    setTimeout(() => { ssoSaved.value = false }, 3000)
  } catch (e: any) {
    ssoError.value = e?.response?.data?.detail || 'Failed to save SSO settings.'
  } finally {
    ssoSaving.value = false
  }
}

// ── Security report ───────────────────────────────────────────────────────────

interface ReportCfg { enabled: boolean; frequency: string }
interface PreviewData {
  logins_ok: number; logins_failed: number; logins_blocked: number
  unique_users: number; new_users: number
  downloads_count: number; downloads_bytes: number
  scans_total: number; threats_found: number
  top_users: { username: string; count: number }[]
}

const reportCfg    = reactive<ReportCfg>({ enabled: false, frequency: 'weekly' })
const reportLastSent = ref('')
const reportLoading  = ref(true)
const reportSaving   = ref(false)
const reportSaved    = ref(false)
const reportError    = ref('')
const reportSending  = ref(false)
const reportSentOk   = ref(false)
const reportSentErr  = ref('')
const previewLoading = ref(false)
const previewData    = ref<PreviewData | null>(null)

function fmtBytes(n: number): string {
  const units = ['B','KB','MB','GB','TB']
  let v = n
  for (const u of units) {
    if (v < 1024) return `${v.toFixed(1)} ${u}`
    v /= 1024
  }
  return `${v.toFixed(1)} PB`
}

async function loadReport() {
  reportLoading.value = true
  try {
    const r = await client.get('/settings/security/report/config')
    reportCfg.enabled   = r.data.enabled
    reportCfg.frequency = r.data.frequency
    if (r.data.last_sent) {
      reportLastSent.value = new Date(r.data.last_sent).toLocaleString(getLocale())
    }
  } catch { /* ignore */ } finally {
    reportLoading.value = false
  }
  loadReportPreview()
}

async function loadReportPreview() {
  previewLoading.value = true
  try {
    const r = await client.get('/settings/security/report/preview')
    previewData.value = r.data
  } catch { /* ignore */ } finally {
    previewLoading.value = false
  }
}

async function saveReport() {
  reportSaving.value = true
  reportSaved.value  = false
  reportError.value  = ''
  try {
    await client.post('/settings/security/report/config', {
      enabled:   reportCfg.enabled,
      frequency: reportCfg.frequency,
    })
    reportSaved.value = true
    setTimeout(() => { reportSaved.value = false }, 3000)
  } catch (e: any) {
    reportError.value = e?.response?.data?.detail || 'Failed to save report settings.'
  } finally {
    reportSaving.value = false
  }
}

async function sendReportNow() {
  reportSending.value = true
  reportSentOk.value  = false
  reportSentErr.value = ''
  try {
    await client.post('/settings/security/report/send-now')
    reportSentOk.value = true
    reportLastSent.value = new Date().toLocaleString(getLocale())
    setTimeout(() => { reportSentOk.value = false }, 5000)
  } catch (e: any) {
    reportSentErr.value = e?.response?.data?.detail || 'Failed to send report.'
    setTimeout(() => { reportSentErr.value = '' }, 8000)
  } finally {
    reportSending.value = false
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([loadBf(), loadBanned(), loadAudit(0), loadCvStatus(), loadCvScans(), loadQuarantine(), loadNet(), loadInvites(), loadEmail(), loadSso(), loadReport(), loadSessionLifetime()])

  // Register Socket.IO listeners
  socketStore.connect()
  socketStore.socket?.on('clamav:update_progress', onCvUpdateProgress)
  socketStore.socket?.on('clamav:scan_progress',   onCvScanProgress)
  socketStore.socket?.on('clamav:scan_complete',   onCvScanComplete)
})

onUnmounted(() => {
  socketStore.socket?.off('clamav:update_progress', onCvUpdateProgress)
  socketStore.socket?.off('clamav:scan_progress',   onCvScanProgress)
  socketStore.socket?.off('clamav:scan_complete',   onCvScanComplete)
})
</script>

<style scoped>
.ss-root { display: flex; flex-direction: column; gap: var(--space-6, 24px); }

/* Header */
.ss-header { display: flex; align-items: flex-start; gap: 14px; }
.ss-icon {
  width: 38px; height: 38px; border-radius: 9px; flex-shrink: 0;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light);
}
.ss-title    { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 2px; }
.ss-subtitle { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }

/* Sections */
.ss-section {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); padding: 18px 20px;
  display: flex; flex-direction: column; gap: 14px;
}
.ss-section-title    { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.ss-section-title--collapsible {
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none; border-radius: var(--radius-sm);
  padding: 2px 0;
  transition: color var(--transition);
}
.ss-section-title--collapsible:hover { color: var(--pl-light); }
.ss-chevron {
  flex-shrink: 0; color: var(--muted); transition: transform 0.22s ease;
  transform: rotate(0deg);
}
.ss-chevron--open { transform: rotate(-180deg); }
.ss-subsection-title { font-size: 13px; font-weight: 600; color: var(--muted); margin-top: 4px; }

/* Loading / empty */
.ss-loading { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: 13px; color: var(--muted); }
.ss-empty   { font-size: 13px; color: var(--muted); padding: 8px 0; }

/* Toggle */
.field-row--toggle { display: flex; align-items: center; }
.toggle-label { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.toggle-input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle-track {
  display: block; width: 36px; height: 20px; border-radius: 10px;
  background: rgba(255,255,255,.12); border: 1px solid var(--glass-border);
  position: relative; transition: background var(--transition), border-color var(--transition);
  flex-shrink: 0; cursor: pointer;
}
.toggle-input:checked + .toggle-track { background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1)); border-color: color-mix(in srgb, var(--pl) 50%, transparent); }
.toggle-thumb {
  display: block; position: absolute; top: 3px; left: 3px;
  width: 12px; height: 12px; border-radius: 50%;
  background: #fff; transition: transform var(--transition);
}
.toggle-input:checked + .toggle-track .toggle-thumb { transform: translateX(16px); }
.toggle-text { font-size: 13px; color: var(--text); font-weight: 500; }

/* Fields grid */
.fields-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3, 12px);
}
.field-group { display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.field-group--wide { grid-column: 1 / -1; }
.field-label { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted); }
.field-hint  { font-size: 11px; color: rgba(255,255,255,.3); margin-top: -2px; }

.field-input {
  width: 100%; padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input::placeholder { color: rgba(255,255,255,.25); }
.field-input:disabled { opacity: .5; cursor: not-allowed; }
.field-input-wrap { display: flex; align-items: center; gap: var(--space-2, 8px); }
.field-input-wrap .field-input { flex: 1; }
.field-unit { font-size: 13px; color: var(--muted); white-space: nowrap; }

.field-textarea {
  width: 100%; padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  resize: vertical; transition: border-color var(--transition);
}
.field-textarea:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-textarea::placeholder { color: rgba(255,255,255,.25); }
.field-textarea:disabled { opacity: .5; cursor: not-allowed; }

/* Messages */
.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}
.field-ok {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25);
  color: #86efac; font-size: 13px;
}

/* SSO */
.sso-mode-cards {
  display: flex; gap: 10px; margin-top: 6px;
}
.sso-mode-card {
  flex: 1; padding: 12px 14px; cursor: pointer;
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  background: rgba(255,255,255,.02); transition: border-color .15s, background .15s;
}
.sso-mode-card--active {
  border-color: #a78bfa; background: rgba(167,139,250,.08);
}
.sso-mode-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 3px; }
.sso-mode-desc  { font-size: 11px; color: var(--text-muted); }

.sso-provider-card {
  margin-top: 12px;
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.sso-provider-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; cursor: pointer;
  background: rgba(255,255,255,.02);
  user-select: none;
}
.sso-provider-header:hover { background: rgba(255,255,255,.04); }
.sso-provider-name {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.sso-provider-hint { font-size: 11px; font-weight: 400; color: var(--text-muted); }
.sso-provider-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.sso-dot--on  { background: #4ade80; box-shadow: 0 0 6px #4ade8088; }
.sso-dot--off { background: #444; }
.sso-provider-fields { padding: 14px; border-top: 1px solid var(--glass-border); }
.sso-callback-info {
  margin-top: 10px; font-size: 11px; color: var(--text-muted);
}
.sso-callback-info code {
  font-family: monospace; font-size: 11px;
  background: rgba(255,255,255,.05); padding: 2px 6px; border-radius: var(--radius-xs, 4px);
  color: #a78bfa; word-break: break-all;
}
.sso-note {
  margin-top: 14px; display: flex; align-items: flex-start; gap: var(--space-2, 8px);
  font-size: var(--fs-sm, 12px); color: var(--text-muted); line-height: 1.5;
  padding: 10px 12px;
  background: rgba(255,255,255,.02); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }

/* Security Report */
.sr-last-sent {
  font-size: var(--fs-sm, 12px); color: var(--text-muted); margin-bottom: 4px;
}
.sr-preview-title {
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: .5px;
  margin-top: 18px; margin-bottom: 10px;
  display: flex; align-items: center; gap: 10px;
}
.sr-refresh-btn { padding: 3px 8px !important; font-size: 11px !important; }
.sr-preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.sr-stat-card {
  padding: 14px 16px;
  background: rgba(255,255,255,.02);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}
.sr-stat-label { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.sr-stat-value { font-size: 20px; font-weight: 700; color: var(--text-primary); font-family: monospace; }
.sr-stat--green { color: #4ade80; }
.sr-stat--amber { color: #fbbf24; }
.sr-stat--red   { color: #f87171; }

/* Actions */
.ss-actions { display: flex; gap: 10px; }

.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); font-size: 13px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all var(--transition);
  background: rgba(255,255,255,.05); color: var(--muted);
}
.action-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.action-btn:disabled { opacity: .5; cursor: not-allowed; }

.action-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light);
}
.action-btn--primary:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }

.action-btn--ghost {
  background: transparent; color: var(--muted);
}
.action-btn--ghost:not(:disabled):hover { background: var(--glass-highlight); color: var(--text); }

.action-btn--danger {
  background: rgba(248,113,113,.1); border-color: rgba(248,113,113,.3); color: #f87171;
}
.action-btn--danger:not(:disabled):hover { background: rgba(248,113,113,.2); border-color: #f87171; }

.action-btn--sm { padding: 5px 10px; font-size: var(--fs-sm, 12px); }

/* Table */
.ss-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.ss-table th {
  text-align: left; font-size: 11px; font-weight: 600; color: var(--muted);
  padding: 6px 10px; border-bottom: 1px solid var(--glass-border);
}
.ss-table td {
  padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.04);
  color: var(--text); vertical-align: middle;
}
.ss-table--audit td { font-size: var(--fs-sm, 12px); }
.td-mono    { font-family: monospace; font-size: var(--fs-sm, 12px); color: var(--muted); }
.td-time    { font-size: 11px; color: var(--muted); white-space: nowrap; }
.td-details { color: var(--muted); font-size: 11px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Status badge */
.status-badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600;
}
.status-badge--ok   { background: rgba(34,197,94,.1);  color: #86efac; border: 1px solid rgba(34,197,94,.3); }
.status-badge--fail { background: rgba(248,113,113,.1); color: #fca5a5; border: 1px solid rgba(248,113,113,.3); }
.status-badge--warn { background: rgba(251,191,36,.1);  color: #fde68a; border: 1px solid rgba(251,191,36,.3); }

/* Action badge */
.action-badge {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted);
}
.action-badge--login_ok      { background: rgba(34,197,94,.08);  color: #86efac; border-color: rgba(34,197,94,.25); }
.action-badge--login_fail    { background: rgba(248,113,113,.08); color: #fca5a5; border-color: rgba(248,113,113,.25); }
.action-badge--login_blocked { background: rgba(251,191,36,.08);  color: #fde68a; border-color: rgba(251,191,36,.25); }
.action-badge--unban_ip      { background: rgba(139,92,246,.08);  color: #c4b5fd; border-color: rgba(139,92,246,.25); }
.badge-icon { flex-shrink: 0; }

/* Audit toolbar */
.audit-toolbar { display: flex; gap: var(--space-2, 8px); align-items: center; }
.audit-filter  { flex: 1; max-width: 260px; }

/* Pagination */
.pagination { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.pagination-info { font-size: var(--fs-sm, 12px); color: var(--muted); flex: 1; text-align: center; }

/* ClamAV */
/* ClamAV action picker */
.cv-action-picker { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.cv-action-opt {
  display: flex; align-items: flex-start; gap: var(--space-3, 12px);
  padding: 12px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.03);
  cursor: pointer; transition: border-color var(--transition), background var(--transition);
}
.cv-action-opt:hover { border-color: var(--pl); background: rgba(255,255,255,.05); }
.cv-action-opt--active { border-color: var(--pl); background: var(--pl-dim); }
.cv-action-radio { display: none; }
.cv-action-icon {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.cv-action-icon--none       { background: rgba(148,163,184,.12); color: var(--muted); }
.cv-action-icon--quarantine { background: rgba(139,92,246,.15);  color: #c4b5fd; }
.cv-action-icon--delete     { background: rgba(248,113,113,.12); color: #fca5a5; }
.cv-action-label {
  font-size: 13px; font-weight: 600; color: var(--text);
  display: flex; align-items: center; gap: var(--space-2, 8px); margin-bottom: 3px;
}
.cv-action-hint { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }
.cv-action-badge {
  font-size: var(--fs-xs, 10px); font-weight: 600; padding: 1px 6px; border-radius: 6px;
  background: rgba(139,92,246,.2); color: #c4b5fd; border: 1px solid rgba(139,92,246,.35);
}

/* Quarantine table */
.cv-q-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 9px; font-size: 11px; font-weight: 700;
  background: rgba(248,113,113,.2); color: #fca5a5;
  border: 1px solid rgba(248,113,113,.35); margin-left: 6px;
}
.cv-q-table .cv-q-filename { font-size: 13px; color: var(--text); font-weight: 500; }
.cv-q-table .cv-q-origpath {
  font-size: 11px; color: var(--muted); font-family: monospace;
  max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cv-q-threat { color: #fca5a5; font-size: var(--fs-sm, 12px); font-family: monospace; }
.cv-q-actions { display: flex; gap: 6px; white-space: nowrap; }
.cv-q-row--missing { opacity: .55; }
.cv-q-row--missing .cv-q-filename::after {
  content: ' (missing)'; font-size: 11px; color: #fca5a5; font-weight: 400;
}

/* ClamAV toggle group - matches SettingsNotifications pattern */
.cv-toggle-group {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.cv-trow {
  display: flex; align-items: center; gap: 14px; padding: 10px 14px;
  transition: opacity var(--transition);
}
.cv-trow + .cv-trow { border-top: 1px solid var(--glass-border); }
.cv-trow--dim { opacity: .45; pointer-events: none; }
.cv-tinfo { flex: 1; }
.cv-tname { font-size: 13px; font-weight: 600; color: var(--text); }
.cv-tdesc { font-size: 11px; color: var(--muted); margin-top: 2px; line-height: 1.4; }
.cv-tpill { display: flex; align-items: center; flex-shrink: 0; cursor: pointer; }
.cv-interval-row {
  display: flex; flex-direction: column; gap: 6px;
  padding: 10px 14px; background: rgba(255,255,255,.03);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
}
.cv-interval-input-wrap { display: flex; align-items: center; gap: 10px; }
.cv-interval-input { width: 100px; }
.cv-interval-unit { font-size: var(--fs-sm, 12px); color: var(--muted); }
.cv-last-update { font-size: 11px; color: var(--muted); }

/* Hint blocks below subsection titles */
.cv-section-hint {
  font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.6;
  padding: 8px 12px; background: rgba(255,255,255,.03);
  border-left: 2px solid var(--glass-border); border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.cv-hint-warn {
  font-size: var(--fs-sm, 12px); color: #fde68a; line-height: 1.5;
  padding: 6px 10px; background: rgba(251,191,36,.07);
  border: 1px solid rgba(251,191,36,.25); border-radius: var(--radius-sm);
}

.cv-status-card {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  padding: 12px 14px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
}
.cv-status-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.cv-status-dot--ok  { background: #4ade80; box-shadow: 0 0 6px #4ade8066; }
.cv-status-dot--err { background: #f87171; box-shadow: 0 0 6px #f8717166; }
.cv-status-info  { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.cv-status-label { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text); }
.cv-status-ver   { font-size: 11px; color: var(--muted); font-family: monospace; }
.cv-status-sub   { font-size: var(--fs-sm, 12px); color: var(--muted); }

.cv-log {
  background: rgba(0,0,0,.25); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 10px 12px;
  max-height: 180px; overflow-y: auto; font-family: monospace; font-size: 11px;
  display: flex; flex-direction: column; gap: 2px;
}
.cv-log-line     { color: var(--muted); line-height: 1.5; }
.cv-log-line--ok  { color: #86efac; }
.cv-log-line--err { color: #fca5a5; }

.cv-scan-paths { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.cv-path-check {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.03);
  cursor: pointer; transition: border-color var(--transition);
}
.cv-path-check:hover { border-color: var(--pl); }
.cv-path-check input { accent-color: var(--pl); cursor: pointer; flex-shrink: 0; }
.cv-path-info { display: flex; flex-direction: column; gap: 1px; }
.cv-path-name { font-size: 13px; color: var(--text); font-weight: 500; }
.cv-path-desc { font-size: 11px; color: var(--muted); font-family: monospace; }

.cv-scan-progress {
  display: flex; flex-direction: column; gap: 6px;
}
.cv-scan-prog-bar {
  height: 4px; border-radius: 2px;
  background: rgba(255,255,255,.1); overflow: hidden;
}
.cv-scan-prog-fill {
  height: 100%; background: color-mix(in srgb, var(--pl) 30%, transparent);
  border-radius: 2px; transition: width .3s;
}
.cv-scan-prog-info { font-size: var(--fs-sm, 12px); color: var(--muted); }

.cv-result {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 10px 14px; border-radius: var(--radius-sm);
  font-size: 13px;
}
.cv-result--clean    { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25); color: #86efac; }
.cv-result--infected { background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3); color: #fca5a5; }

.cv-infected-count { color: #fca5a5; font-weight: 700; }
.cv-clean-count    { color: var(--muted); }


/* Sessions / Session Lifetime */
.session-lifetime-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.lifetime-chip {
  padding: 5px 14px;
  border-radius: 7px;
  font-size: 12.5px;
  font-weight: 500;
  border: 1px solid var(--glass-border, rgba(255,255,255,0.1));
  background: rgba(255,255,255,0.04);
  color: var(--muted);
  cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.lifetime-chip:hover:not(:disabled) {
  background: rgba(255,255,255,0.08);
  color: var(--text);
}
.lifetime-chip.active {
  background: color-mix(in srgb, var(--pl) 20%, rgba(255,255,255,.06));
  color: var(--pl);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
}
.lifetime-chip:disabled { opacity: .5; cursor: not-allowed; }
.ss-hint-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 7px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--glass-border, rgba(255,255,255,0.07));
  font-size: var(--fs-sm, 12px);
  color: var(--muted);
}

.sess-row--current {
  background: rgba(139, 92, 246, 0.06);
}
.sess-status-cell { width: 18px; text-align: center; }
.sess-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: rgba(255,255,255,.2);
}
.sess-current-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: #4ade80;
  box-shadow: 0 0 6px #4ade8066;
}
.sess-browser { font-size: 13px; color: var(--text); }
.sess-current-badge {
  display: inline-block; margin-left: 8px;
  font-size: var(--fs-xs, 10px); font-weight: 600; padding: 1px 6px;
  border-radius: 6px; background: rgba(139,92,246,.2);
  color: #c4b5fd; border: 1px solid rgba(139,92,246,.35);
  vertical-align: middle;
}

/* Spinner */
.spinner {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block; flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Invite codes */
.cv-invite-create {
  display: flex; flex-direction: column; gap: 10px;
  padding: 12px 14px; border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); background: rgba(255,255,255,.03);
}
.cv-invite-fields {
  display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end;
}
.cv-invite-fields .field-group { min-width: 100px; }
.cv-invite-code {
  display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm);
  background: rgba(139,92,246,.15); border: 1px solid rgba(139,92,246,.3);
  color: #c4b5fd; font-size: var(--fs-sm, 12px); font-family: monospace;
  cursor: pointer; transition: background var(--transition), border-color var(--transition);
  user-select: all;
}
.cv-invite-code:hover {
  background: rgba(139,92,246,.28); border-color: rgba(139,92,246,.55);
}

/* Email alerts */
.fields-grid--disabled { opacity: .45; pointer-events: none; }
.email-alert-toggles { display: flex; flex-direction: column; gap: var(--space-1, 4px); margin-top: 4px; }
.email-smtp-note {
  display: flex; align-items: center; gap: 7px;
  padding: 9px 13px; margin-bottom: 12px;
  border-radius: var(--radius-sm); border: 1px solid rgba(139,92,246,.25);
  background: rgba(139,92,246,.08); color: #9d84e8; font-size: var(--fs-sm, 12px);
}
.email-smtp-note svg { flex-shrink: 0; color: #a78bfa; }
.email-smtp-note strong { color: #c4b5fd; }
</style>
