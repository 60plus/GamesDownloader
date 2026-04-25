<template>
  <div class="sn-root">

    <!-- ── SMTP ──────────────────────────────────────────────────────────────── -->
    <section class="sn-section">
      <div class="sn-section-head">
        <div class="sn-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
            <polyline points="22,6 12,13 2,6"/>
          </svg>
        </div>
        <div>
          <div class="sn-section-title">{{ t('notif.smtp_title') }}</div>
          <div class="sn-section-sub">{{ t('notif.smtp_desc') }}</div>
        </div>
        <label class="toggle-pill" :title="t('notif.enable_smtp')">
          <input type="checkbox" v-model="smtp.enabled" class="toggle-input" />
          <span class="toggle-track" :class="{ 'toggle-track--on': smtp.enabled }">
            <span class="toggle-thumb" />
          </span>
        </label>
      </div>

      <div v-if="smtpLoading" class="sn-loading"><span class="spinner" /> {{ t('common.loading') }}</div>

      <template v-else>
        <div class="sn-form">
          <div class="field-row">
            <div class="field-group field-group--grow">
              <label class="field-label">{{ t('notif.smtp_host') }}</label>
              <input v-model="smtp.host" class="field-input" placeholder="smtp.example.com" />
            </div>
            <div class="field-group field-group--port">
              <label class="field-label">{{ t('notif.port') }}</label>
              <input v-model.number="smtp.port" class="field-input" type="number" placeholder="587" />
            </div>
          </div>

          <div class="field-row">
            <div class="field-group field-group--grow">
              <label class="field-label">{{ t('notif.username') }}</label>
              <input v-model="smtp.username" class="field-input" placeholder="user@example.com" autocomplete="off" />
            </div>
            <div class="field-group field-group--grow">
              <label class="field-label">{{ t('notif.password') }}</label>
              <input v-model="smtp.password" class="field-input" type="password" placeholder="SMTP password" autocomplete="new-password" />
            </div>
          </div>

          <div class="field-row">
            <div class="field-group field-group--grow">
              <label class="field-label">{{ t('notif.from_address') }}</label>
              <input v-model="smtp.from_address" class="field-input" placeholder="noreply@example.com" />
            </div>
            <div class="field-group field-group--grow">
              <label class="field-label">{{ t('notif.test_recipient') }}</label>
              <input v-model="smtp.test_to" class="field-input" placeholder="your@email.com" />
            </div>
          </div>

          <div class="toggle-row-inline">
            <span class="toggle-name">{{ t('notif.use_tls') }}</span>
            <label class="toggle-pill">
              <input type="checkbox" v-model="smtp.use_tls" class="toggle-input" />
              <span class="toggle-track" :class="{ 'toggle-track--on': smtp.use_tls }">
                <span class="toggle-thumb" />
              </span>
            </label>
          </div>

          <!-- Trigger toggles -->
          <div class="field-label">{{ t('notif.trigger_on') }}</div>
          <div class="toggle-group">
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.download_complete') }}</div>
                <div class="toggle-desc">{{ t('notif.download_complete_desc') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="smtp.email_notify_download" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': smtp.email_notify_download }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.library_sync') }}</div>
                <div class="toggle-desc">{{ t('notif.library_sync_desc') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="smtp.email_notify_sync" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': smtp.email_notify_sync }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.game_requests') }}</div>
                <div class="toggle-desc">{{ t('notif.game_requests_desc') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="smtp.email_notify_request" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': smtp.email_notify_request }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
          </div>

          <!-- Advanced: email templates -->
          <div class="toggle-group" style="margin-top:4px">
            <button type="button" class="sn-advanced-toggle" @click="emailAdvOpen = !emailAdvOpen">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"
                :style="{ transform: emailAdvOpen ? 'rotate(90deg)' : '', transition: 'transform .15s' }">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
              {{ t('notif.advanced_email_templates') }}
            </button>
            <div v-if="emailAdvOpen" class="sn-templates">
              <div class="sn-tpl-hint">
                {{ t('notif.placeholders_hint') }}<br>
                {{ t('notif.html_hint') }}
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.download_complete') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.subject') }}</div>
                  <input v-model="smtp.email_tpl_download_subject" class="field-input field-input--sm" placeholder="Download Complete: {title}" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <textarea v-model="smtp.email_tpl_download_body" class="sn-tpl-textarea" placeholder="<p><strong>{title}</strong> has finished downloading and is ready to play.</p>"></textarea>
                </div>
                <div class="sn-tpl-preview" style="background:#1a1a2e">
                  <div class="sn-tpl-preview-bar" style="background:#7C3AED;width:3px" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">Subject: {{ tplPreview(smtp.email_tpl_download_subject, 'Download Complete: {title}', sampleDl) }}</div>
                    <div class="sn-tpl-preview-text" v-html="tplPreview(smtp.email_tpl_download_body, '&lt;p&gt;&lt;strong&gt;{title}&lt;/strong&gt; has finished downloading and is ready to play.&lt;/p&gt;', sampleDl)"></div>
                  </div>
                </div>
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.library_sync') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.subject') }}</div>
                  <input v-model="smtp.email_tpl_sync_subject" class="field-input field-input--sm" placeholder="GOG Library Synced" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <textarea v-model="smtp.email_tpl_sync_body" class="sn-tpl-textarea" placeholder="<p>Your GOG library has been synchronized successfully.</p>"></textarea>
                </div>
                <div class="sn-tpl-preview" style="background:#1a1a2e">
                  <div class="sn-tpl-preview-bar" style="background:#7C3AED;width:3px" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">Subject: {{ tplPreview(smtp.email_tpl_sync_subject, 'GOG Library Synced', sampleSync) }}</div>
                    <div class="sn-tpl-preview-text" v-html="tplPreview(smtp.email_tpl_sync_body, '&lt;p&gt;Your GOG library has been synchronized successfully.&lt;/p&gt;', sampleSync)"></div>
                  </div>
                </div>
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.new_game_request') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.subject') }}</div>
                  <input v-model="smtp.email_tpl_request_new_subject" class="field-input field-input--sm" placeholder="New Game Request: {title}" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <textarea v-model="smtp.email_tpl_request_new_body" class="sn-tpl-textarea" placeholder="<p><strong>{username}</strong> requested <strong>{title}</strong>.</p><p>{description}</p>"></textarea>
                </div>
                <div class="sn-tpl-preview" style="background:#1a1a2e">
                  <div class="sn-tpl-preview-bar" style="background:#3B82F6;width:3px" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">Subject: {{ tplPreview(smtp.email_tpl_request_new_subject, 'New Game Request: {title}', sampleReqNew) }}</div>
                    <div class="sn-tpl-preview-text" v-html="tplPreview(smtp.email_tpl_request_new_body, '&lt;p&gt;&lt;strong&gt;{username}&lt;/strong&gt; requested &lt;strong&gt;{title}&lt;/strong&gt;.&lt;/p&gt;&lt;p&gt;{description}&lt;/p&gt;', sampleReqNew)"></div>
                  </div>
                </div>
              </div>

              <div v-for="st in emailStatusTypes" :key="st.key" class="sn-tpl-section">
                <div class="sn-tpl-section-hdr" :style="{ color: st.color }">{{ st.label }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.subject') }}</div>
                  <input v-model="(smtp as any)['email_tpl_request_' + st.key + '_subject']" class="field-input field-input--sm" :placeholder="st.defaultSubject" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <textarea v-model="(smtp as any)['email_tpl_request_' + st.key + '_body']" class="sn-tpl-textarea" :placeholder="st.defaultBody"></textarea>
                </div>
                <div class="sn-tpl-preview" style="background:#1a1a2e">
                  <div class="sn-tpl-preview-bar" :style="{ background: st.color, width: '3px' }" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">Subject: {{ tplPreview((smtp as any)['email_tpl_request_' + st.key + '_subject'] || '', st.defaultSubject, st.sample) }}</div>
                    <div class="sn-tpl-preview-text" v-html="tplPreview((smtp as any)['email_tpl_request_' + st.key + '_body'] || '', st.defaultBody, st.sample)"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="smtpTestResult" class="test-result" :class="smtpTestResult.ok ? 'test-result--ok' : 'test-result--err'">
            <svg v-if="smtpTestResult.ok" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            {{ smtpTestResult.message }}
          </div>
          <div v-if="smtpError" class="field-server-error">{{ smtpError }}</div>
          <div v-if="smtpSaved" class="field-ok">{{ t('notif.smtp_saved') }}</div>

          <div class="sn-actions">
            <button v-if="smtp.host" class="action-btn action-btn--secondary" :disabled="smtpTesting" @click="testSmtp">
              <span v-if="smtpTesting" class="spinner" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              {{ smtpTesting ? t('notif.sending') : t('notif.send_test_email') }}
            </button>
            <button class="action-btn action-btn--primary" :disabled="smtpSaving" @click="saveSmtp">
              <span v-if="smtpSaving" class="spinner" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              {{ t('notif.save_smtp') }}
            </button>
          </div>
        </div>
      </template>
    </section>

    <!-- ── Webhooks ───────────────────────────────────────────────────────────── -->
    <section class="sn-section">
      <div class="sn-section-head">
        <div class="sn-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </div>
        <div>
          <div class="sn-section-title">{{ t('notif.webhooks') }}</div>
          <div class="sn-section-sub">{{ t('notif.webhooks_desc') }}</div>
        </div>
        <label class="toggle-pill" :title="t('notif.enable_webhooks')">
          <input type="checkbox" v-model="wh.enabled" class="toggle-input" />
          <span class="toggle-track" :class="{ 'toggle-track--on': wh.enabled }">
            <span class="toggle-thumb" />
          </span>
        </label>
      </div>

      <div v-if="whLoading" class="sn-loading"><span class="spinner" /> {{ t('common.loading') }}</div>

      <template v-else>
        <div class="sn-form">
          <!-- Type selector -->
          <div class="field-group">
            <label class="field-label">{{ t('notif.webhook_type') }}</label>
            <div class="chip-row">
              <button
                v-for="opt in whTypeOptions"
                :key="opt.value"
                class="chip"
                :class="{ 'chip--active': wh.type === opt.value }"
                type="button"
                @click="wh.type = opt.value"
              >{{ opt.label }}</button>
            </div>
            <div v-if="wh.type === 'discord'" class="field-hint">
              {{ t('notif.discord_desc') }}
            </div>
            <div v-else class="field-hint">
              {{ t('notif.generic_desc') }}
            </div>
          </div>

          <!-- Webhook URL -->
          <div class="field-group">
            <label class="field-label">{{ t('notif.webhook_url') }}</label>
            <input
              v-model="wh.url"
              class="field-input"
              :placeholder="wh.type === 'discord' ? 'https://discord.com/api/webhooks/…' : 'https://your-server.com/hook'"
            />
          </div>

          <!-- Trigger toggles -->
          <div class="field-label">{{ t('notif.trigger_on') }}</div>
          <div class="toggle-group">
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.download_complete') }}</div>
                <div class="toggle-desc">{{ t('notif.fire_download') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="wh.notify_download" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': wh.notify_download }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.library_sync') }}</div>
                <div class="toggle-desc">{{ t('notif.fire_sync') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="wh.notify_sync" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': wh.notify_sync }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.game_requests') }}</div>
                <div class="toggle-desc">{{ t('notif.fire_request') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="wh.notify_request" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': wh.notify_request }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
          </div>

          <!-- Discord-only options -->
          <div v-if="wh.type === 'discord'" class="toggle-group">
            <div class="toggle-row" style="flex-direction:column;align-items:stretch;gap:6px">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.avatar_url') }}</div>
                <div class="toggle-desc">{{ t('notif.avatar_desc') }}</div>
              </div>
              <input v-model="wh.avatar_url" type="url" class="field-input" placeholder="https://your-server.com/GDLOGO.png" style="font-size:12px" />
            </div>
            <div class="toggle-row">
              <div class="toggle-info">
                <div class="toggle-name">{{ t('notif.include_cover') }}</div>
                <div class="toggle-desc">{{ t('notif.include_cover_desc') }}</div>
              </div>
              <label class="toggle-pill">
                <input type="checkbox" v-model="wh.include_cover" class="toggle-input" />
                <span class="toggle-track" :class="{ 'toggle-track--on': wh.include_cover }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
          </div>

          <!-- Advanced: message templates -->
          <div v-if="wh.type === 'discord'" class="toggle-group" style="margin-top:4px">
            <button type="button" class="sn-advanced-toggle" @click="advOpen = !advOpen">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"
                :style="{ transform: advOpen ? 'rotate(90deg)' : '', transition: 'transform .15s' }">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
              {{ t('notif.advanced_msg_templates') }}
            </button>
            <div v-if="advOpen" class="sn-templates">
              <div class="sn-tpl-hint">
                {{ t('notif.placeholders_hint') }}
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.download_complete') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.title_field') }}</div>
                  <input v-model="wh.tpl_download_title" class="field-input field-input--sm" placeholder="Download Complete: {title}" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <input v-model="wh.tpl_download_body" class="field-input field-input--sm" placeholder="{title} has finished downloading." />
                </div>
                <div class="sn-tpl-preview">
                  <div class="sn-tpl-preview-bar" style="background:#7C3AED" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">{{ tplPreview(wh.tpl_download_title, 'Download Complete: {title}', sampleDl) }}</div>
                    <div class="sn-tpl-preview-text">{{ tplPreview(wh.tpl_download_body, '{title} has finished downloading.', sampleDl) }}</div>
                  </div>
                </div>
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.library_sync') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.title_field') }}</div>
                  <input v-model="wh.tpl_sync_title" class="field-input field-input--sm" placeholder="GOG Library Synced" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <input v-model="wh.tpl_sync_body" class="field-input field-input--sm" placeholder="Library sync completed successfully." />
                </div>
                <div class="sn-tpl-preview">
                  <div class="sn-tpl-preview-bar" style="background:#7C3AED" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">{{ tplPreview(wh.tpl_sync_title, 'GOG Library Synced', sampleSync) }}</div>
                    <div class="sn-tpl-preview-text">{{ tplPreview(wh.tpl_sync_body, 'Library sync completed successfully.', sampleSync) }}</div>
                  </div>
                </div>
              </div>

              <div class="sn-tpl-section">
                <div class="sn-tpl-section-hdr">{{ t('notif.new_game_request') }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.title_field') }}</div>
                  <input v-model="wh.tpl_request_new_title" class="field-input field-input--sm" placeholder="New Game Request: {title}" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <input v-model="wh.tpl_request_new_body" class="field-input field-input--sm" placeholder="{description}" />
                </div>
                <div class="sn-tpl-preview">
                  <div class="sn-tpl-preview-bar" style="background:#3B82F6" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">{{ tplPreview(wh.tpl_request_new_title, 'New Game Request: {title}', sampleReqNew) }}</div>
                    <div class="sn-tpl-preview-text">{{ tplPreview(wh.tpl_request_new_body, '{description}', sampleReqNew) }}</div>
                  </div>
                </div>
              </div>

              <div v-for="st in statusTypes" :key="st.key" class="sn-tpl-section">
                <div class="sn-tpl-section-hdr" :style="{ color: st.color }">{{ st.label }}</div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.title_field') }}</div>
                  <input v-model="(wh as any)['tpl_request_' + st.key + '_title']" class="field-input field-input--sm" :placeholder="st.defaultTitle" />
                </div>
                <div class="sn-tpl-group">
                  <div class="sn-tpl-label">{{ t('notif.body') }}</div>
                  <input v-model="(wh as any)['tpl_request_' + st.key + '_body']" class="field-input field-input--sm" :placeholder="st.defaultBody" />
                </div>
                <div class="sn-tpl-preview">
                  <div class="sn-tpl-preview-bar" :style="{ background: st.color }" />
                  <div class="sn-tpl-preview-body">
                    <div class="sn-tpl-preview-title">{{ tplPreview((wh as any)['tpl_request_' + st.key + '_title'] || '', st.defaultTitle, st.sample) }}</div>
                    <div class="sn-tpl-preview-text">{{ tplPreview((wh as any)['tpl_request_' + st.key + '_body'] || '', st.defaultBody, st.sample) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="whTestResult" class="test-result" :class="whTestResult.ok ? 'test-result--ok' : 'test-result--err'">
            <svg v-if="whTestResult.ok" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            {{ whTestResult.message }}
          </div>
          <div v-if="whError" class="field-server-error">{{ whError }}</div>
          <div v-if="whSaved" class="field-ok">{{ t('notif.webhook_saved') }}</div>

          <div class="sn-actions">
            <button v-if="wh.url" class="action-btn action-btn--secondary" :disabled="whTesting" @click="testWebhook" type="button">
              <span v-if="whTesting" class="spinner" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              {{ whTesting ? t('notif.sending') : t('notif.send_test') }}
            </button>
            <button class="action-btn action-btn--primary" :disabled="whSaving" @click="saveWebhook" type="button">
              <span v-if="whSaving" class="spinner" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              {{ t('notif.save_webhook') }}
            </button>
          </div>
        </div>
      </template>
    </section>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// ── SMTP state ────────────────────────────────────────────────────────────────
const smtpLoading = ref(true)
const smtpSaving  = ref(false)
const smtpTesting = ref(false)
const smtpSaved   = ref(false)
const smtpError   = ref('')
const smtpTestResult = ref<{ ok: boolean; message: string } | null>(null)

const smtp = reactive({
  enabled: false,
  host: '', port: 587, username: '', password: '', from_address: '', use_tls: true, test_to: '',
  email_notify_download: true,
  email_notify_sync: true,
  email_notify_request: true,
  email_tpl_download_subject: '',
  email_tpl_download_body: '',
  email_tpl_sync_subject: '',
  email_tpl_sync_body: '',
  email_tpl_request_new_subject: '',
  email_tpl_request_new_body: '',
  email_tpl_request_pending_subject: '',
  email_tpl_request_pending_body: '',
  email_tpl_request_approved_subject: '',
  email_tpl_request_approved_body: '',
  email_tpl_request_rejected_subject: '',
  email_tpl_request_rejected_body: '',
  email_tpl_request_done_subject: '',
  email_tpl_request_done_body: '',
})

// ── Webhook state ─────────────────────────────────────────────────────────────
const whLoading = ref(true)
const whSaving  = ref(false)
const whTesting = ref(false)
const whSaved   = ref(false)
const whError   = ref('')
const whTestResult = ref<{ ok: boolean; message: string } | null>(null)

const advOpen = ref(false)
const emailAdvOpen = ref(false)

// Email template status types
const emailStatusTypes = [
  { key: 'pending',  label: 'Pending',  color: '#3B82F6', defaultSubject: 'Game Request Pending: {title}',  defaultBody: '<p>Request for <strong>{title}</strong> by {username} has been <strong>Pending</strong>.</p><p>{note}</p>', sample: { title: 'Half-Life 3', username: 'admin', status: 'Pending', platform: 'Games', note: '', description: '' } },
  { key: 'approved', label: 'Approved', color: '#22C55E', defaultSubject: 'Game Request Approved: {title}', defaultBody: '<p>Request for <strong>{title}</strong> by {username} has been <strong>Approved</strong>.</p><p>{note}</p>', sample: { title: 'Half-Life 3', username: 'admin', status: 'Approved', platform: 'Games', note: 'Added to the library!', description: '' } },
  { key: 'rejected', label: 'Rejected', color: '#EF4444', defaultSubject: 'Game Request Rejected: {title}', defaultBody: '<p>Request for <strong>{title}</strong> by {username} has been <strong>Rejected</strong>.</p><p>{note}</p>', sample: { title: 'Half-Life 3', username: 'admin', status: 'Rejected', platform: 'Games', note: 'Not available anywhere.', description: '' } },
  { key: 'done',     label: 'Done',     color: '#7C3AED', defaultSubject: 'Game Request Done: {title}',     defaultBody: '<p>Request for <strong>{title}</strong> by {username} has been <strong>Done</strong>.</p><p>{note}</p>', sample: { title: 'Half-Life 3', username: 'admin', status: 'Done', platform: 'Games', note: 'Ready to download!', description: '' } },
]

// Sample data for live preview
const sampleDl = { title: 'Cyberpunk 2077', username: 'admin', status: '', platform: 'PC', note: '', description: '' }
const sampleSync = { title: '', username: '', status: '', platform: '', note: '', description: '' }
const sampleReqNew = { title: 'Half-Life 3', username: 'admin', status: 'Pending', platform: 'Games', note: '', description: 'Valve please release this game already.' }
const statusTypes = [
  { key: 'pending',  label: 'Pending',  color: '#3B82F6', defaultTitle: 'Game Request Pending: {title}',  defaultBody: 'Requested by {username}.', sample: { title: 'Half-Life 3', username: 'admin', status: 'Pending', platform: 'Games', note: '', description: '' } },
  { key: 'approved', label: 'Approved', color: '#22C55E', defaultTitle: 'Game Request Approved: {title}', defaultBody: 'Requested by {username}. {note}', sample: { title: 'Half-Life 3', username: 'admin', status: 'Approved', platform: 'Games', note: 'Added to the library!', description: '' } },
  { key: 'rejected', label: 'Rejected', color: '#EF4444', defaultTitle: 'Game Request Rejected: {title}', defaultBody: 'Requested by {username}. {note}', sample: { title: 'Half-Life 3', username: 'admin', status: 'Rejected', platform: 'Games', note: 'Not available anywhere.', description: '' } },
  { key: 'done',     label: 'Done',     color: '#7C3AED', defaultTitle: 'Game Request Done: {title}',     defaultBody: 'Requested by {username}. {note}', sample: { title: 'Half-Life 3', username: 'admin', status: 'Done', platform: 'Games', note: 'Ready to download!', description: '' } },
]

function tplPreview(custom: string, fallback: string, data: Record<string, string>): string {
  let text = custom.trim() || fallback
  for (const [k, v] of Object.entries(data)) {
    text = text.replaceAll(`{${k}}`, v)
  }
  return text
}
const wh = reactive({
  enabled: false,
  url: '',
  type: 'generic',
  notify_download: true,
  notify_sync: true,
  notify_request: true,
  include_cover: true,
  avatar_url: '',
  tpl_download_title: '',
  tpl_download_body: '',
  tpl_sync_title: '',
  tpl_sync_body: '',
  tpl_request_new_title: '',
  tpl_request_new_body: '',
  tpl_request_pending_title: '',
  tpl_request_pending_body: '',
  tpl_request_approved_title: '',
  tpl_request_approved_body: '',
  tpl_request_rejected_title: '',
  tpl_request_rejected_body: '',
  tpl_request_done_title: '',
  tpl_request_done_body: '',
})

const whTypeOptions = [
  { value: 'generic', label: 'Generic JSON' },
  { value: 'discord', label: 'Discord Rich Embed' },
]

// ── Load on mount ─────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const data = await client.get('/settings/smtp').then(r => r.data)
    Object.assign(smtp, data)
    if (!smtp.test_to) smtp.test_to = ''
  } catch { /* ignore */ } finally { smtpLoading.value = false }

  try {
    const data = await client.get('/settings/webhooks').then(r => r.data)
    Object.assign(wh, data)
  } catch { /* ignore */ } finally { whLoading.value = false }
})

// ── SMTP actions ──────────────────────────────────────────────────────────────
async function testSmtp() {
  smtpTesting.value = true
  smtpTestResult.value = null
  try {
    await client.post('/settings/smtp/test', smtp)
    smtpTestResult.value = { ok: true, message: t('notif.email_sent_ok') }
  } catch (e: any) {
    smtpTestResult.value = { ok: false, message: e?.response?.data?.detail || t('notif.email_sent_fail') }
  } finally { smtpTesting.value = false }
}

async function saveSmtp() {
  smtpSaving.value = true
  smtpError.value = ''
  smtpSaved.value = false
  try {
    await client.post('/settings/smtp', smtp)
    smtpSaved.value = true
    setTimeout(() => { smtpSaved.value = false }, 3000)
  } catch (e: any) {
    smtpError.value = e?.response?.data?.detail || t('notif.smtp_save_failed')
  } finally { smtpSaving.value = false }
}

// ── Webhook actions ───────────────────────────────────────────────────────────
async function testWebhook() {
  whTesting.value = true
  whTestResult.value = null
  try {
    await client.post('/settings/webhooks/test', wh)
    whTestResult.value = { ok: true, message: t('notif.webhook_sent_ok') }
  } catch (e: any) {
    whTestResult.value = { ok: false, message: e?.response?.data?.detail || t('notif.webhook_sent_fail') }
  } finally { whTesting.value = false }
}

async function saveWebhook() {
  whSaving.value = true
  whError.value = ''
  whSaved.value = false
  try {
    await client.post('/settings/webhooks', wh)
    whSaved.value = true
    setTimeout(() => { whSaved.value = false }, 3000)
  } catch (e: any) {
    whError.value = e?.response?.data?.detail || t('notif.webhook_save_failed')
  } finally { whSaving.value = false }
}
</script>

<style scoped>
.sn-root { display: flex; flex-direction: column; gap: var(--space-6, 24px); }

/* ── Section ─────────────────────────────────────────────────────────────── */
.sn-section {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  background: var(--glass-bg);
  overflow: hidden;
}

.sn-section-head {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--glass-border);
}

.sn-icon {
  width: 34px; height: 34px; border-radius: var(--radius-sm, 8px); flex-shrink: 0;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light);
}

.sn-section-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.sn-section-sub { font-size: 11px; color: var(--muted); margin-top: 2px; line-height: 1.4; }

/* ── Toggle pill ─────────────────────────────────────────────────────────── */
.toggle-pill { margin-left: auto; cursor: pointer; flex-shrink: 0; }
.toggle-input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle-track {
  display: block; width: 38px; height: 22px; border-radius: 11px;
  background: rgba(255,255,255,.12); border: 1px solid var(--glass-border);
  position: relative; transition: background var(--transition), border-color var(--transition);
}
.toggle-track--on { background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1)); border-color: color-mix(in srgb, var(--pl) 50%, transparent); box-shadow: 0 0 10px var(--pglow2); }
.toggle-thumb {
  display: block; position: absolute; top: 3px; left: 3px;
  width: 14px; height: 14px; border-radius: 50%; background: rgba(255,255,255,.4);
  transition: transform var(--transition);
}
.toggle-track--on .toggle-thumb { transform: translateX(16px); background: #fff; }

/* ── Form ────────────────────────────────────────────────────────────────── */
.sn-form { padding: 16px 18px; display: flex; flex-direction: column; gap: var(--space-3, 12px); }

.sn-loading {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 16px 18px; font-size: 13px; color: var(--muted);
}

.field-row { display: flex; gap: 10px; }
.field-group { display: flex; flex-direction: column; gap: 5px; }
.field-group--grow { flex: 1; }
.field-group--port { width: 86px; }

.field-label {
  font-size: 11px; font-weight: 700; letter-spacing: 1px;
  color: var(--muted); text-transform: uppercase;
}

.field-hint { font-size: 11px; color: var(--muted); margin-top: 4px; }
.field-hint code {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs, 4px); padding: 1px 5px; font-size: var(--fs-xs, 10px); font-family: monospace;
  color: var(--pl-light);
}

.field-input {
  width: 100%; padding: 9px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input::placeholder { color: rgba(255,255,255,.25); }

.toggle-row-inline {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 0;
}
.toggle-name { font-size: 13px; color: var(--text); }

/* ── Chip selector ───────────────────────────────────────────────────────── */
.chip-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 2px; }
.chip {
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.chip:hover { border-color: var(--pl); color: var(--text); }
.chip--active { border-color: var(--pl); background: var(--pl-dim); color: var(--pl-light); }

/* ── Toggle group ────────────────────────────────────────────────────────── */
.toggle-group {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.toggle-row {
  display: flex; align-items: center; gap: 14px; padding: 10px 14px;
}
.toggle-row + .toggle-row { border-top: 1px solid var(--glass-border); }
.toggle-info { flex: 1; }
.toggle-name { font-size: 13px; font-weight: 600; color: var(--text); }
.toggle-desc { font-size: 11px; color: var(--muted); margin-top: 1px; }

/* ── Status messages ─────────────────────────────────────────────────────── */
.test-result {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 9px 12px; border-radius: var(--radius-sm); font-size: var(--fs-sm, 12px);
}
.test-result--ok { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25); color: #86efac; }
.test-result--err { background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3); color: #f87171; }

.field-server-error {
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: var(--fs-sm, 12px);
}
.field-ok {
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25);
  color: #86efac; font-size: var(--fs-sm, 12px);
}

/* ── Actions ─────────────────────────────────────────────────────────────── */
.sn-actions { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }

.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 600; cursor: pointer; border: 1px solid var(--glass-border);
  font-family: inherit; transition: all var(--transition);
  background: rgba(255,255,255,.05); color: var(--muted);
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.action-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.action-btn--secondary { background: rgba(255,255,255,.05); color: var(--muted); }
.action-btn--secondary:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.action-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light);
}
.action-btn--primary:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }

.spinner {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Advanced templates */
.sn-advanced-toggle {
  background: none; border: none; color: var(--muted, rgba(255,255,255,.4));
  font-size: 11px; font-weight: 600; cursor: pointer; display: flex;
  align-items: center; gap: 6px; padding: 6px 0;
  letter-spacing: .03em; text-transform: uppercase;
}
.sn-advanced-toggle:hover { color: var(--text, #fff); }
.sn-templates { display: flex; flex-direction: column; gap: var(--space-2, 8px); padding: 8px 0; }
.sn-tpl-hint {
  font-size: 11px; color: var(--muted, rgba(255,255,255,.35));
  line-height: 1.5; padding: 6px 10px; border-radius: 6px;
  background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.06);
}
.sn-tpl-hint code {
  background: rgba(99,102,241,.15); color: rgba(99,102,241,.9);
  padding: 1px 4px; border-radius: 3px; font-size: var(--fs-xs, 10px);
}
.sn-tpl-group { display: flex; flex-direction: column; gap: 3px; }
.sn-tpl-label { font-size: 11px; font-weight: 600; color: var(--muted, rgba(255,255,255,.45)); }
.field-input--sm { font-size: 12px !important; padding: 6px 10px !important; }

/* Template sections + preview */
.sn-tpl-section {
  padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,.05);
}
.sn-tpl-section:last-child { border-bottom: none; }
.sn-tpl-section-hdr {
  font-size: 11px; font-weight: 700; color: var(--text, rgba(255,255,255,.7));
  margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em;
}
.sn-tpl-preview {
  display: flex; margin-top: 6px; border-radius: var(--radius-xs, 4px);
  background: #2f3136; overflow: hidden;
}
.sn-tpl-preview-bar { width: 4px; flex-shrink: 0; }
.sn-tpl-preview-body { padding: 8px 10px; flex: 1; min-width: 0; }
.sn-tpl-preview-title {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sn-tpl-preview-text {
  font-size: 11px; color: #dcddde; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sn-tpl-preview-badge {
  font-size: 9px; font-weight: 800; letter-spacing: .06em;
  text-transform: uppercase; margin-bottom: 2px;
}
.sn-tpl-previews { display: flex; flex-direction: column; gap: var(--space-1, 4px); margin-top: 6px; }

.sn-tpl-textarea {
  width: 100%; min-height: 60px; font-size: 11px; font-family: monospace;
  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08);
  border-radius: 6px; color: var(--text, #fff); padding: var(--space-2, 8px); resize: vertical;
  box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.sn-tpl-textarea:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.sn-tpl-textarea::placeholder { color: rgba(255,255,255,.25); }
</style>
