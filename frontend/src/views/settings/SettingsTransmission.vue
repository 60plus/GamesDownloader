<template>
  <div class="sd-wrap">

    <!-- Five views rather than one very long page. The settings alone are four
         groups of fields, and the three lists answer different questions: what
         is arriving, what is going out, and what the daemon is holding that
         this application did not put there. -->
    <div class="sub-tabs">
      <button v-for="s in SUBS" :key="s" class="sub-tab" :class="{ active: sub === s }"
        @click="sub = s">{{ t('transmission.sub_' + s) }}</button>
    </div>

    <!-- ── Downloads in flight ──────────────────────────────────────────────
         Transmission has always been able to pause, resume and re-check a
         torrent - the client wrapper had the calls - but nothing exposed them,
         so the only way to do any of it was Transmission's own web interface,
         on a port that is now deliberately shut. -->
    <div v-show="sub === 'downloads'" class="sd-section">
      <div class="sd-section-title">
        <div class="sd-tr-title-row">
          <span>{{ t('transmission.active_title') }}</span>
          <span v-if="!trOnline" class="sd-badge sd-badge--expired">{{ t('transmission.offline') }}</span>
        </div>
      </div>

      <div v-if="dlLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <div v-else-if="!downloads.length" class="sd-empty">{{ t('transmission.no_active') }}</div>
      <div v-else class="sd-dl-list">
        <div v-for="d in downloads" :key="d.id" class="sd-dl">
          <div class="sd-dl-head">
            <div class="sd-dl-name" :title="d.title">{{ d.title }}</div>
            <span class="sd-badge" :class="dlBadge(d.status)">{{ dlStatusLabel(d.status) }}</span>
          </div>

          <div class="sd-dl-bar"><span :style="{ width: dlPercent(d) + '%' }" /></div>
          <div class="sd-dl-meta">
            <span>{{ dlPercent(d) }}%</span>
            <span v-if="d.total_size">{{ fmtSize(d.total_size) }}</span>
            <span v-if="d.rate_download">{{ fmtSize(d.rate_download) }}/s</span>
            <span v-if="d.eta > 0">{{ fmtEta(d.eta) }}</span>
          </div>

          <div class="sd-dl-actions">
            <button v-if="d.status === 'downloading'" class="action-btn action-btn--sm"
              :disabled="busy === d.id" @click="act(d, 'pause')">{{ t('transmission.pause') }}</button>
            <button v-if="d.status === 'paused'" class="action-btn action-btn--sm"
              :disabled="busy === d.id" @click="act(d, 'resume')">{{ t('transmission.resume') }}</button>
            <button v-if="d.status === 'downloading' || d.status === 'paused'"
              class="action-btn action-btn--sm" :disabled="busy === d.id"
              @click="act(d, 'verify')">{{ t('transmission.verify') }}</button>
            <button class="action-btn action-btn--sm" :disabled="busy === d.id"
              @click="openFiles(d)">{{ t('transmission.choose_files') }}</button>
            <button class="action-btn action-btn--sm action-btn--danger" :disabled="busy === d.id"
              @click="removeDownload(d)">{{ t('common.remove') }}</button>
          </div>

          <!-- File picker: a torrent is often a shelf rather than a game. -->
          <div v-if="filesFor === d.id" class="sd-files">
            <div v-if="filesLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
            <template v-else>
              <div v-if="!files.length" class="sd-empty">{{ t('transmission.files_unknown') }}</div>
              <template v-else>
                <label v-for="f in files" :key="f.index" class="sd-file">
                  <input type="checkbox" v-model="f.wanted" />
                  <span class="sd-file-name" :title="f.name">{{ f.name }}</span>
                  <span class="sd-file-size">{{ fmtSize(f.length) }}</span>
                  <span class="sd-file-pct">{{ f.percent }}%</span>
                </label>
                <div v-if="filesError" class="field-server-error">{{ filesError }}</div>
                <div class="sd-actions">
                  <button class="action-btn action-btn--sm" @click="filesFor = null">{{ t('common.cancel') }}</button>
                  <button class="action-btn action-btn--primary action-btn--sm btn-save-action"
                    :disabled="filesSaving" @click="saveFiles(d)">
                    <span v-if="filesSaving" class="spinner" />
                    {{ t('common.save') }}
                  </button>
                </div>
              </template>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ── What this server is sharing ─────────────────────────────────────── -->
    <div v-show="sub === 'seeds'" class="sd-section">
      <div class="sd-section-title"><div class="sd-tr-title-row">
        <span>{{ t('transmission.sub_seeds') }}</span>
      </div></div>
      <div v-if="seedsLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <div v-else-if="!seeds.length" class="sd-empty">{{ t('transmission.no_seeds') }}</div>
      <div v-else class="sd-table-wrap">
        <table class="sd-table">
          <thead><tr>
            <th>{{ t('transmission.col_file') }}</th>
            <th>{{ t('transmission.col_status') }}</th>
            <th>{{ t('transmission.col_size') }}</th>
            <th>{{ t('transmission.col_uploaded') }}</th>
            <th>{{ t('transmission.col_ratio') }}</th>
            <th>{{ t('transmission.col_peers') }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="s in seeds" :key="s.id">
              <td class="sd-cell-name" :title="s.filename">{{ s.filename }}</td>
              <td>
                <span class="sd-badge" :class="s.live ? 'sd-badge--active' : 'sd-badge--expired'">
                  {{ s.live ? t('transmission.seed_live') : t('transmission.seed_gone') }}
                </span>
              </td>
              <td>{{ fmtSize(s.file_size) }}</td>
              <td>{{ fmtSize(s.uploaded) }}</td>
              <td>{{ s.ratio }}</td>
              <td>{{ s.peers_to }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="field-hint" style="margin-top:10px">{{ t('transmission.seeds_hint') }}</div>
    </div>

    <!-- ── Everything the daemon holds ─────────────────────────────────────── -->
    <div v-show="sub === 'all'" class="sd-section">
      <div class="sd-section-title"><div class="sd-tr-title-row">
        <span>{{ t('transmission.sub_all') }}</span>
      </div></div>
      <div v-if="allLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <div v-else-if="!allTorrents.length" class="sd-empty">{{ t('transmission.no_torrents') }}</div>
      <div v-else class="sd-dl-list">
        <div v-for="a in allTorrents" :key="a.id" class="sd-dl">
          <div class="sd-dl-head">
            <div class="sd-dl-name" :title="a.name">{{ a.name }}</div>
            <span v-if="!a.ours" class="sd-badge sd-badge--expired">{{ t('transmission.not_ours') }}</span>
            <span class="sd-badge" :class="a.status === 'seeding' ? 'sd-badge--active' : 'sd-badge--exhausted'">
              {{ t('transmission.tstatus_' + a.status, a.status) }}
            </span>
          </div>
          <div class="sd-dl-bar"><span :style="{ width: a.percent + '%' }" /></div>
          <div class="sd-dl-meta">
            <span>{{ a.percent }}%</span>
            <span>{{ fmtSize(a.total_size) }}</span>
            <span v-if="a.rate_down">↓ {{ fmtSize(a.rate_down) }}/s</span>
            <span v-if="a.rate_up">↑ {{ fmtSize(a.rate_up) }}/s</span>
            <span>{{ t('transmission.col_ratio') }} {{ a.ratio }}</span>
            <span>{{ a.peers }} {{ t('transmission.col_peers') }}</span>
          </div>
          <div v-if="a.error" class="field-server-error">{{ a.error }}</div>
          <div class="sd-dl-actions">
            <button class="action-btn action-btn--sm" :disabled="busy === a.id"
              @click="actAll(a, a.status === 'stopped' ? 'resume' : 'pause')">
              {{ a.status === 'stopped' ? t('transmission.resume') : t('transmission.pause') }}
            </button>
            <button class="action-btn action-btn--sm" :disabled="busy === a.id" @click="actAll(a, 'verify')">{{ t('transmission.verify') }}</button>
            <button class="action-btn action-btn--sm" :disabled="busy === a.id" @click="actAll(a, 'top')">{{ t('transmission.queue_top') }}</button>
            <button class="action-btn action-btn--sm" :disabled="busy === a.id" @click="actAll(a, 'bottom')">{{ t('transmission.queue_bottom') }}</button>
            <button class="action-btn action-btn--sm action-btn--danger" :disabled="busy === a.id" @click="dropTorrent(a, false)">{{ t('common.remove') }}</button>
            <button class="action-btn action-btn--sm action-btn--danger" :disabled="busy === a.id" @click="dropTorrent(a, true)">{{ t('transmission.remove_with_data') }}</button>
          </div>
        </div>
      </div>
      <div v-if="allError" class="field-server-error">{{ allError }}</div>
    </div>

    <!-- ── Statistics ──────────────────────────────────────────────────────── -->
    <div v-show="sub === 'stats'" class="sd-section">
      <div class="sd-section-title"><div class="sd-tr-title-row">
        <span>{{ t('transmission.sub_stats') }}</span>
      </div></div>
      <div v-if="!stats" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>
        <div class="sd-stat-grid">
          <div class="sd-stat"><span class="sd-stat-n">{{ stats.torrents }}</span><span class="sd-stat-l">{{ t('transmission.stat_torrents') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ stats.active }}</span><span class="sd-stat-l">{{ t('transmission.stat_active') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ stats.paused }}</span><span class="sd-stat-l">{{ t('transmission.stat_paused') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.rate_down) }}/s</span><span class="sd-stat-l">{{ t('transmission.stat_down') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.rate_up) }}/s</span><span class="sd-stat-l">{{ t('transmission.stat_up') }}</span></div>
        </div>
        <div class="sd-tr-group-label">{{ t('transmission.stat_session') }}</div>
        <div class="sd-stat-grid">
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.current.downloaded) }}</span><span class="sd-stat-l">{{ t('transmission.stat_downloaded') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.current.uploaded) }}</span><span class="sd-stat-l">{{ t('transmission.stat_uploaded') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtDur(stats.current.seconds) }}</span><span class="sd-stat-l">{{ t('transmission.stat_running') }}</span></div>
        </div>
        <div class="sd-tr-group-label">{{ t('transmission.stat_lifetime') }}</div>
        <div class="sd-stat-grid">
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.cumulative.downloaded) }}</span><span class="sd-stat-l">{{ t('transmission.stat_downloaded') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtSize(stats.cumulative.uploaded) }}</span><span class="sd-stat-l">{{ t('transmission.stat_uploaded') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ fmtDur(stats.cumulative.seconds) }}</span><span class="sd-stat-l">{{ t('transmission.stat_running') }}</span></div>
          <div class="sd-stat"><span class="sd-stat-n">{{ stats.cumulative.sessions }}</span><span class="sd-stat-l">{{ t('transmission.stat_sessions') }}</span></div>
        </div>
      </template>
    </div>

    <!-- ── Settings ─────────────────────────────────────────────────────────
         Lifted wholesale out of Settings > Downloads, which now keeps only the
         on/off switch. Same fields, same endpoint, same keys. -->
    <div v-show="sub === 'settings'" class="sd-section">
      <div class="sd-section-title">
        <div class="sd-tr-title-row">
          <span>{{ t('transmission.settings_title') }}</span>
          <span v-if="tr.enabled" :class="['sd-badge', trOnline ? 'sd-badge--active' : 'sd-badge--expired']">
            {{ trOnline ? t('transmission.online') : t('transmission.offline') }}
          </span>
        </div>
      </div>

      <div v-if="trLoading" class="sd-loading"><span class="spinner" /> {{ t('common.loading') }}</div>
      <template v-else>
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

          <!-- RPC access. Transmission's own control interface listens on its
               own port, so nothing reaching it passes through this app's
               sign-in. Closed by default: this app talks to Transmission from
               inside the container and nothing outside needs the port. -->
          <div class="sd-tr-group-label">{{ t('transmission.rpc_access') }}</div>
          <div class="sd-tr-fields">

            <div class="field-group"
              @mouseenter="setHint(t('thint.tr_rpc_expose_title'), t('thint.tr_rpc_expose_body'))"
              @mouseleave="clearHint()">
              <label class="field-label">{{ t('transmission.rpc_expose') }}</label>
              <div class="field-hint">{{ t('transmission.rpc_expose_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.rpc_expose" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
              <!-- Turning this on without a password does nothing: the server
                   keeps the daemon on loopback rather than publish an
                   unauthenticated socket. Say so here instead of letting the
                   toggle look like it worked. -->
              <div v-if="tr.rpc_expose && !tr.rpc_auth_enabled" class="field-server-error">
                {{ t('transmission.rpc_expose_needs_auth') }}
              </div>
            </div>

            <div class="field-group"
              @mouseenter="setHint(t('thint.tr_rpc_auth_title'), t('thint.tr_rpc_auth_body'))"
              @mouseleave="clearHint()">
              <label class="field-label">{{ t('transmission.rpc_auth') }}</label>
              <div class="field-hint">{{ t('transmission.rpc_auth_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.rpc_auth_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
            </div>

            <template v-if="tr.rpc_auth_enabled">
              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_rpc_user_title'), t('thint.tr_rpc_user_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.rpc_username') }}</label>
                <input v-model="tr.rpc_username" class="field-input" autocomplete="off" maxlength="64" />
              </div>

              <div class="field-group"
                @mouseenter="setHint(t('thint.tr_rpc_pass_title'), t('thint.tr_rpc_pass_body'))"
                @mouseleave="clearHint()">
                <label class="field-label">{{ t('transmission.rpc_password') }}</label>
                <div class="field-hint">
                  {{ tr.rpc_password_set ? t('transmission.rpc_password_keep') : t('transmission.rpc_password_hint') }}
                </div>
                <input v-model="tr.rpc_password" type="password" class="field-input" autocomplete="new-password" maxlength="128" />
              </div>
            </template>

            <div class="field-group"
              @mouseenter="setHint(t('thint.tr_rpc_wl_title'), t('thint.tr_rpc_wl_body'))"
              @mouseleave="clearHint()">
              <label class="field-label">{{ t('transmission.rpc_whitelist_on') }}</label>
              <div class="field-hint">{{ t('transmission.rpc_whitelist_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.rpc_whitelist_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
            </div>

            <div v-if="tr.rpc_whitelist_enabled" class="field-group"
              @mouseenter="setHint(t('thint.tr_rpc_wl_list_title'), t('thint.tr_rpc_wl_list_body'))"
              @mouseleave="clearHint()">
              <label class="field-label">{{ t('transmission.rpc_whitelist') }}</label>
              <div class="field-hint">{{ t('transmission.rpc_whitelist_list_hint') }}</div>
              <input v-model="tr.rpc_whitelist" class="field-input" placeholder="127.0.0.1,::1,192.168.*.*" maxlength="255" />
            </div>

            <div class="field-group"
              @mouseenter="setHint(t('thint.tr_rpc_host_title'), t('thint.tr_rpc_host_body'))"
              @mouseleave="clearHint()">
              <label class="field-label">{{ t('transmission.rpc_host_whitelist') }}</label>
              <div class="field-hint">{{ t('transmission.rpc_host_whitelist_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.rpc_host_whitelist_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
            </div>

            <div class="field-group">
              <div class="field-hint">{{ t('transmission.rpc_restart_note') }}</div>
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

          <!-- Turtle mode: a second pair of caps, by hand or on a clock. -->
          <div class="sd-tr-group-label">{{ t('transmission.turtle') }}</div>
          <div class="sd-tr-fields">
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_on') }}</label>
              <div class="field-hint">{{ t('transmission.turtle_on_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.alt_speed_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_down') }}</label>
              <div class="field-hint">{{ t('transmission.kbs_hint') }}</div>
              <input v-model.number="tr.alt_speed_down" type="number" min="0" class="field-input" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_up') }}</label>
              <div class="field-hint">{{ t('transmission.kbs_hint') }}</div>
              <input v-model.number="tr.alt_speed_up" type="number" min="0" class="field-input" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_schedule') }}</label>
              <div class="field-hint">{{ t('transmission.turtle_schedule_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.alt_speed_time_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_from') }}</label>
              <input v-model="turtleFrom" type="time" class="field-input" :disabled="!tr.alt_speed_time_enabled" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.turtle_to') }}</label>
              <input v-model="turtleTo" type="time" class="field-input" :disabled="!tr.alt_speed_time_enabled" />
            </div>
          </div>

          <!-- Queues: without them a hundred added torrents all start at once
               and none of them finishes. -->
          <div class="sd-tr-group-label">{{ t('transmission.queues') }}</div>
          <div class="sd-tr-fields">
            <div class="field-group">
              <label class="field-label">{{ t('transmission.dl_queue') }}</label>
              <div class="field-hint">{{ t('transmission.dl_queue_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.download_queue_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
              <input v-model.number="tr.download_queue_size" type="number" min="1" max="99"
                class="field-input sd-speed-input" :disabled="!tr.download_queue_enabled" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.seed_queue') }}</label>
              <div class="field-hint">{{ t('transmission.seed_queue_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.seed_queue_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
              <input v-model.number="tr.seed_queue_size" type="number" min="1" max="99"
                class="field-input sd-speed-input" :disabled="!tr.seed_queue_enabled" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.stalled') }}</label>
              <div class="field-hint">{{ t('transmission.stalled_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.queue_stalled_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
              <input v-model.number="tr.queue_stalled_minutes" type="number" min="1" max="999"
                class="field-input sd-speed-input" :disabled="!tr.queue_stalled_enabled" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.idle_seed') }}</label>
              <div class="field-hint">{{ t('transmission.idle_seed_hint') }}</div>
              <label class="sd-toggle sd-toggle--inline">
                <input type="checkbox" v-model="tr.idle_seeding_limit_enabled" />
                <span class="sd-toggle-track"><span class="sd-toggle-thumb" /></span>
              </label>
              <input v-model.number="tr.idle_seeding_limit" type="number" min="1" max="9999"
                class="field-input sd-speed-input" :disabled="!tr.idle_seeding_limit_enabled" />
            </div>
          </div>

          <!-- Peers -->
          <div class="sd-tr-group-label">{{ t('transmission.peers') }}</div>
          <div class="sd-tr-fields">
            <div class="field-group">
              <label class="field-label">{{ t('transmission.encryption') }}</label>
              <div class="field-hint">{{ t('transmission.encryption_hint') }}</div>
              <select v-model="tr.encryption" class="field-input">
                <option value="tolerated">{{ t('transmission.enc_tolerated') }}</option>
                <option value="preferred">{{ t('transmission.enc_preferred') }}</option>
                <option value="required">{{ t('transmission.enc_required') }}</option>
              </select>
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.peer_global') }}</label>
              <div class="field-hint">{{ t('transmission.peer_global_hint') }}</div>
              <input v-model.number="tr.peer_limit_global" type="number" min="1" max="2000" class="field-input" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.peer_torrent') }}</label>
              <div class="field-hint">{{ t('transmission.peer_torrent_hint') }}</div>
              <input v-model.number="tr.peer_limit_per_torrent" type="number" min="1" max="500" class="field-input" />
            </div>
            <div class="field-group">
              <label class="field-label">{{ t('transmission.cache') }}</label>
              <div class="field-hint">{{ t('transmission.cache_hint') }}</div>
              <input v-model.number="tr.cache_size_mb" type="number" min="1" max="1024" class="field-input" />
            </div>
          </div>

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
        <div v-if="trError" class="field-server-error">{{ trError }}</div>
        <div v-if="trSaved" class="field-ok">{{ t('transmission.saved') }}</div>
        <div class="sd-actions">
          <button class="action-btn action-btn--primary btn-save-action" :disabled="trSaving" @click="saveTransmission">
            <span v-if="trSaving" class="spinner" />
            {{ t('common.save') }}
          </button>
        </div>
      </template>
    </div>

    <!-- hint panel (rendered by parent SettingsIndex, hoisted via composable) -->
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useDialog } from '@/composables/useDialog'
import { formatBytes as fmtSize } from '@/utils/format'

const { t } = useI18n()
const { setHint, clearHint } = useSettingsHint()
const { gdConfirm } = useDialog()

const SUBS = ['downloads', 'seeds', 'all', 'stats', 'settings'] as const
const sub = ref<typeof SUBS[number]>('downloads')

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
  rpc_auth_enabled:         boolean
  rpc_username:             string
  // Write-only: the server never sends it back, so an empty box means
  // "leave whatever is stored". rpc_password_set says whether there is one.
  rpc_password:             string
  rpc_password_set?:        boolean
  rpc_whitelist_enabled:    boolean
  rpc_whitelist:            string
  rpc_host_whitelist_enabled: boolean
  // Publish Transmission's control port outside the container. Refused by the
  // server unless rpc_auth_enabled is on as well.
  rpc_expose:               boolean
  alt_speed_enabled:          boolean
  alt_speed_down:             number
  alt_speed_up:               number
  alt_speed_time_enabled:     boolean
  alt_speed_time_begin:       number
  alt_speed_time_end:         number
  alt_speed_time_day:         number
  download_queue_enabled:     boolean
  download_queue_size:        number
  seed_queue_enabled:         boolean
  seed_queue_size:            number
  queue_stalled_enabled:      boolean
  queue_stalled_minutes:      number
  idle_seeding_limit_enabled: boolean
  idle_seeding_limit:         number
  encryption:                 string
  peer_limit_global:          number
  peer_limit_per_torrent:     number
  cache_size_mb:              number
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
  rpc_auth_enabled: false, rpc_username: '', rpc_password: '', rpc_password_set: false,
  rpc_expose: false,
  alt_speed_enabled: false, alt_speed_down: 500, alt_speed_up: 100,
  alt_speed_time_enabled: false, alt_speed_time_begin: 540, alt_speed_time_end: 1380,
  alt_speed_time_day: 127,
  download_queue_enabled: true, download_queue_size: 5,
  seed_queue_enabled: false, seed_queue_size: 10,
  queue_stalled_enabled: true, queue_stalled_minutes: 30,
  idle_seeding_limit_enabled: false, idle_seeding_limit: 30,
  encryption: 'preferred', peer_limit_global: 200, peer_limit_per_torrent: 50,
  cache_size_mb: 4,
  rpc_whitelist_enabled: false, rpc_whitelist: '127.0.0.1,::1,192.168.*.*',
  rpc_host_whitelist_enabled: false,
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
    // Drop the typed password and ask the server what it now holds. Keeping it
    // in the box would leave it in memory for the rest of the visit, and the
    // reply is the only thing that knows whether one is stored.
    tr.rpc_password = ''
    try {
      const { data } = await client.get('/settings/downloads/transmission')
      tr.rpc_password_set = data?.rpc_password_set === true
    } catch { /* the save itself succeeded; the indicator can wait */ }
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

// ── Downloads in flight ──────────────────────────────────────────────────────

interface TorrentDownloadRow {
  id:            number
  title:         string
  status:        string
  percent_done:  number
  total_size:    number
  rate_download: number
  eta:           number
}

const downloads  = ref<TorrentDownloadRow[]>([])
const dlLoading  = ref(true)
const busy       = ref<number | null>(null)

// Poll while this tab is open. Cleared on unmount: a poller left running after
// the component is gone calls into a destroyed instance, which is a mistake
// this codebase has made in four other places.
let poll: ReturnType<typeof setInterval> | null = null

function dlPercent(d: TorrentDownloadRow): number {
  return Math.round((d.percent_done || 0) * 1000) / 10
}

function dlStatusLabel(s: string): string {
  const known = ['downloading', 'paused', 'complete', 'error', 'removed']
  return known.includes(s) ? t('transmission.status_' + s) : s
}

function dlBadge(s: string): string {
  if (s === 'complete')    return 'sd-badge--active'
  if (s === 'error')       return 'sd-badge--revoked'
  if (s === 'paused')      return 'sd-badge--exhausted'
  if (s === 'downloading') return 'sd-badge--active'
  return 'sd-badge--expired'
}

function fmtEta(secs: number): string {
  if (!secs || secs < 0) return ''
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m`
}

async function loadDownloads(quiet = false) {
  if (!quiet) dlLoading.value = true
  try {
    const { data } = await client.get('/torrents/downloads')
    downloads.value = (data || []).filter((d: TorrentDownloadRow) => d.status !== 'removed')
  } catch {
    // A blip should not empty the list under somebody who is reading it.
  } finally {
    dlLoading.value = false
  }
}

async function act(d: TorrentDownloadRow, what: 'pause' | 'resume' | 'verify') {
  busy.value = d.id
  try {
    await client.post(`/torrents/downloads/${d.id}/${what}`)
    await loadDownloads(true)
  } catch (e: any) {
    filesError.value = e?.response?.data?.detail || t('transmission.action_failed')
  } finally {
    busy.value = null
  }
}

async function removeDownload(d: TorrentDownloadRow) {
  if (!await gdConfirm(t('transmission.remove_confirm', { name: d.title }),
                       { title: t('common.remove'), danger: true })) return
  busy.value = d.id
  try {
    await client.delete(`/torrents/downloads/${d.id}`)
    await loadDownloads(true)
  } catch (e: any) {
    filesError.value = e?.response?.data?.detail || t('transmission.action_failed')
  } finally {
    busy.value = null
  }
}

// ── Which files to fetch ─────────────────────────────────────────────────────

interface TorrentFile {
  index:  number
  name:   string
  length: number
  percent: number
  wanted: boolean
}

const filesFor     = ref<number | null>(null)
const files        = ref<TorrentFile[]>([])
const filesLoading = ref(false)
const filesSaving  = ref(false)
const filesError   = ref('')

async function openFiles(d: TorrentDownloadRow) {
  if (filesFor.value === d.id) { filesFor.value = null; return }
  filesFor.value = d.id
  filesError.value = ''
  filesLoading.value = true
  try {
    const { data } = await client.get(`/torrents/downloads/${d.id}/files`)
    files.value = data || []
  } catch (e: any) {
    files.value = []
    filesError.value = e?.response?.data?.detail || t('transmission.files_failed')
  } finally {
    filesLoading.value = false
  }
}

async function saveFiles(d: TorrentDownloadRow) {
  filesSaving.value = true
  filesError.value = ''
  try {
    const wanted   = files.value.filter(f => f.wanted).map(f => f.index)
    const unwanted = files.value.filter(f => !f.wanted).map(f => f.index)
    const { data } = await client.put(`/torrents/downloads/${d.id}/files`, { wanted, unwanted })
    files.value = data?.files || files.value
  } catch (e: any) {
    filesError.value = e?.response?.data?.detail || t('transmission.files_failed')
  } finally {
    filesSaving.value = false
  }
}

// ── Seeds, everything, statistics ────────────────────────────────────────────

interface SeedRow {
  id: number; filename: string; status: string; file_size: number
  uploaded: number; ratio: number; peers_to: number; live: boolean
}
interface AnyTorrent {
  id: number; name: string; status: string; percent: number; total_size: number
  ratio: number; rate_down: number; rate_up: number; peers: number
  error: string; ours: boolean
}
interface Stats {
  torrents: number; active: number; paused: number
  rate_down: number; rate_up: number
  current:    { downloaded: number; uploaded: number; seconds: number; sessions: number }
  cumulative: { downloaded: number; uploaded: number; seconds: number; sessions: number }
}

const seeds        = ref<SeedRow[]>([])
const seedsLoading = ref(true)
const allTorrents  = ref<AnyTorrent[]>([])
const allLoading   = ref(true)
const allError     = ref('')
const stats        = ref<Stats | null>(null)

// Turtle's schedule is stored as minutes past midnight, which is what
// Transmission wants; the field is a clock, which is what a person wants.
const turtleFrom = computed({
  get: () => minutesToClock(tr.alt_speed_time_begin),
  set: (v: string) => { tr.alt_speed_time_begin = clockToMinutes(v) },
})
const turtleTo = computed({
  get: () => minutesToClock(tr.alt_speed_time_end),
  set: (v: string) => { tr.alt_speed_time_end = clockToMinutes(v) },
})

function minutesToClock(m: number): string {
  const mm = Math.max(0, Math.min(1439, m || 0))
  return String(Math.floor(mm / 60)).padStart(2, '0') + ':' + String(mm % 60).padStart(2, '0')
}
function clockToMinutes(v: string): number {
  const [h, m] = (v || '00:00').split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

function fmtDur(secs: number): string {
  if (!secs) return '0'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${m}m`
  return `${m}m`
}

async function loadSeeds(quiet = false) {
  if (!quiet) seedsLoading.value = true
  try {
    const { data } = await client.get('/torrents/seeds')
    seeds.value = data || []
  } catch { /* keep what is on screen */ } finally { seedsLoading.value = false }
}

async function loadAll(quiet = false) {
  if (!quiet) allLoading.value = true
  try {
    const { data } = await client.get('/torrents/all')
    allTorrents.value = data || []
  } catch { /* keep what is on screen */ } finally { allLoading.value = false }
}

async function loadStats() {
  try {
    const { data } = await client.get('/torrents/stats')
    stats.value = data
  } catch { /* the panel keeps showing its spinner */ }
}

async function actAll(a: AnyTorrent, what: string) {
  busy.value = a.id
  allError.value = ''
  try {
    await client.post(`/torrents/all/${a.id}/${what}`)
    await loadAll(true)
  } catch (e: any) {
    allError.value = e?.response?.data?.detail || t('transmission.action_failed')
  } finally { busy.value = null }
}

async function dropTorrent(a: AnyTorrent, withData: boolean) {
  // Removing the data of a seed deletes the library file it was sharing, so
  // that branch says so plainly and wears the danger colour.
  const ok = await gdConfirm(
    withData ? t('transmission.remove_data_confirm', { name: a.name })
             : t('transmission.remove_confirm', { name: a.name }),
    // Ticked only on the branch that takes the file with it. Removing a torrent
    // and leaving its data is a stop-seeding button, and putting a tick in front
    // of the harmless one teaches people to tick without reading, which is
    // precisely what would then happen on the branch that does delete.
    { title: t('common.remove'), danger: true, requireTick: withData },
  )
  if (!ok) return
  busy.value = a.id
  try {
    await client.delete(`/torrents/all/${a.id}`, { params: { delete_data: withData } })
    await loadAll(true)
  } catch (e: any) {
    allError.value = e?.response?.data?.detail || t('transmission.action_failed')
  } finally { busy.value = null }
}

// One poller for the whole tab, refreshing whichever list is being looked at.
// Four other pollers in this codebase are never cleared; this one is.
//
// It also refuses to start a round while the previous one is still out. Three
// seconds is comfortable against a local daemon and not against a slow RPC or
// a few hundred torrents, and without this the requests would begin to overlap
// exactly when the daemon is already struggling.
let ticking = false

async function tick() {
  if (ticking) return
  ticking = true
  try {
    if (sub.value === 'downloads') await loadDownloads(true)
    else if (sub.value === 'seeds') await loadSeeds(true)
    else if (sub.value === 'all')   await loadAll(true)
    else if (sub.value === 'stats') await loadStats()
  } finally {
    ticking = false
  }
}

watch(sub, (v) => {
  if (v === 'seeds' && !seeds.value.length) loadSeeds()
  if (v === 'all'   && !allTorrents.value.length) loadAll()
  if (v === 'stats' && !stats.value) loadStats()
})

onMounted(async () => {
  await Promise.all([loadTransmission(), loadDownloads()])
  poll = setInterval(tick, 3000)
})

onUnmounted(() => {
  if (poll) clearInterval(poll)
  poll = null
})
</script>

<style scoped>
.sd-wrap { display: flex; flex-direction: column; gap: 18px; }
.sd-empty { color: var(--muted); font-size: 13px; padding: 10px 0; }

/* ── Sub-tabs ─────────────────────────────────────────────────────────────── */
.sub-tabs {
  display: flex; gap: 2px; flex-wrap: wrap;
  border-bottom: 1px solid var(--glass-border); padding-bottom: 0;
}
.sub-tab {
  background: none; border: none; cursor: pointer;
  color: var(--muted); font: inherit; font-size: 13px;
  padding: 8px 14px; border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
}
.sub-tab:hover { color: var(--text); }
.sub-tab.active { color: var(--pl-light, var(--pl)); border-bottom-color: var(--pl); }
.sub-tab:focus-visible { outline: 2px solid var(--pl); outline-offset: -2px; }

/* ── Statistics ───────────────────────────────────────────────────────────── */
.sd-stat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; margin-bottom: 6px;
}
.sd-stat {
  border: 1px solid var(--glass-border); border-radius: 8px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 4px;
}
.sd-stat-n { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
.sd-stat-l { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }

.sd-cell-name { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Table (same shape as the one on the Downloads page) ──────────────────── */
.sd-table-wrap { overflow-x: auto; }
.sd-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm, 12px); min-width: 560px; }
.sd-table th {
  text-align: left; padding: 7px 10px; font-size: var(--fs-xs, 10px); font-weight: 700;
  color: var(--muted); text-transform: uppercase; letter-spacing: .5px;
  border-bottom: 1px solid var(--glass-border); white-space: nowrap;
}
.sd-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.04); vertical-align: middle; }

/* ── A download in flight ─────────────────────────────────────────────────── */
.sd-dl-list { display: flex; flex-direction: column; gap: 12px; }
.sd-dl {
  border: 1px solid var(--glass-border); border-radius: 8px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.sd-dl-head { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
.sd-dl-name {
  font-size: 13.5px; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sd-dl-bar {
  height: 5px; border-radius: 3px; overflow: hidden;
  background: color-mix(in srgb, var(--pl) 14%, transparent);
}
.sd-dl-bar span { display: block; height: 100%; background: var(--pl); transition: width .4s ease; }
.sd-dl-meta {
  display: flex; gap: 14px; font-size: 11.5px; color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.sd-dl-actions { display: flex; gap: 6px; flex-wrap: wrap; }

/* ── File picker ──────────────────────────────────────────────────────────── */
.sd-files {
  border-top: 1px solid var(--glass-border); padding-top: 10px; margin-top: 2px;
  display: flex; flex-direction: column; gap: 4px;
  max-height: 320px; overflow-y: auto;
}
.sd-file {
  display: grid; grid-template-columns: auto 1fr auto auto; gap: 10px;
  align-items: center; font-size: 12.5px; padding: 3px 0; cursor: pointer;
}
.sd-file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sd-file-size,
.sd-file-pct { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 11.5px; }

/* ── Transmission ────────────────────────────────────────────────────────── */
.sd-tr-title-row { display: flex; align-items: center; gap: 10px; }
.sd-tr-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--glass-border); margin-bottom: 10px;
}
.sd-tr-group-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
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
  background: var(--muted); transition: transform .2s, background .2s;
}
.sd-toggle input:checked ~ .sd-toggle-track .sd-toggle-thumb {
  transform: translateX(16px); background: #fff;
}
.sd-toggle--inline { align-items: center; margin-top: 8px; }

/* ── Misc ────────────────────────────────────────────────────────────────── */
.sd-loading { display: flex; align-items: center; gap: var(--space-2, 8px); color: var(--muted); font-size: 13px; padding: 16px 0; }
.sd-empty   { color: var(--muted); font-size: 13px; padding: 16px 0; }

/* ── Shared form classes (mirror SettingsSecurity) ───────────────────────── */
.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}
.field-group        { display: flex; flex-direction: column; gap: 5px; }
.field-group--wide  { grid-column: 1 / -1; }
.field-label        { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .4px; }
.field-hint         { font-size: 11px; color: var(--muted); }
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
</style>
