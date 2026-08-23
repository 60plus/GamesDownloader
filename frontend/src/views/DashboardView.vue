<!--
  Dashboard - role-aware overview built into the core.

  * Every user sees "Your activity" (downloads + activity chart + game saves +
    their requests), from GET /api/dashboard/me.
  * Admins additionally see "Server overview" (library, users, downloads, emails,
    most active user, platforms, security, antivirus, disk) plus the full
    game-request review queue, from GET /api/dashboard/admin and /api/requests.
  * A window selector (24h / 7d / 30d / custom) re-scopes the time-based
    sections. Sections are collapsible; the state persists per browser.
  * Plugin widget cards (widget_get_cards) still render underneath.

  The same data + actions are exposed to plugin themes as window.__GD__.dashboard,
  so a custom theme can render its own dashboard from identical payloads.
-->
<template>
  <div class="dash" :class="{ 'is-refreshing': refreshing }">
    <div class="dash-head">
      <h1 class="dash-title"><i class="mdi mdi-view-dashboard-outline dash-title-ico"></i>{{ t("dashboard.title", "Dashboard") }}</h1>
      <div class="dash-actions">
        <div class="dash-period">
          <button v-for="p in periods" :key="p.key" class="dash-per" :class="{ active: period === p.key }" @click="setPeriod(p.key)">{{ p.label }}</button>
          <span v-if="refreshing" class="dash-refresh"></span>
        </div>
        <button type="button" class="dash-edit-btn" :class="{ active: editLayout }" @click="editLayout = !editLayout" :title="t('dashboard.customize', 'Customize layout')">
          <i :class="editLayout ? 'mdi mdi-check' : 'mdi mdi-view-dashboard-edit-outline'"></i>
          <span class="dash-edit-lbl">{{ editLayout ? t("dashboard.done", "Done") : t("dashboard.customize", "Customize") }}</span>
        </button>
        <button v-if="editLayout" type="button" class="dash-edit-btn dash-edit-btn--ghost" @click="resetLayout" :title="t('dashboard.reset_layout', 'Reset layout')"><i class="mdi mdi-restore"></i></button>
      </div>
    </div>
    <div v-if="period === 'custom'" class="dash-custom">
      <input type="date" v-model="customStart" class="dash-date" :max="customEnd || undefined" @change="onCustom" />
      <span class="dash-custom-sep">→</span>
      <input type="date" v-model="customEnd" class="dash-date" :min="customStart || undefined" @change="onCustom" />
    </div>

    <div v-if="loading" class="dash-empty"><span class="dash-spin"></span> {{ t("dashboard.loading", "Loading your dashboard…") }}</div>

    <template v-else>
      <!-- YOUR ACTIVITY (all users) -->
      <section v-if="me" class="dash-sect">
        <button class="dash-h2" @click="toggle('activity')">
          <i class="mdi mdi-chevron-down dash-chev" :class="{ collapsed: collapsed.activity }"></i>
          <i class="mdi mdi-account dash-h2-ico"></i>{{ t("dashboard.your_activity", "Your activity") }}
        </button>
        <div v-show="!collapsed.activity">
          <template v-for="id in layoutActivity" :key="id">
            <div v-if="editLayout || !isHidden(id)" class="dash-block" :class="{ 'is-edit': editLayout, 'is-hidden': isHidden(id) }" :draggable="editLayout" @dragstart="onDragStart('activity', id, $event)" @dragover.prevent @drop="onDrop('activity', id)">
              <div v-if="editLayout" class="dash-block-bar">
                <i class="mdi mdi-drag-horizontal-variant dash-block-grip"></i>
                <span class="dash-block-name">{{ blockLabel(id) }}</span>
                <button type="button" class="dash-block-eye" @click="toggleHide(id)"><i :class="isHidden(id) ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button>
              </div>
              <div class="dash-block-body">
                <div v-if="id === 'a_cards'" class="dash-grid">
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-download dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.games_downloaded", "Games downloaded") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="me.downloads.games" /></div>
                    <div class="dash-card-sub">{{ me.downloads.count }} {{ t("dashboard.file_downloads", "file downloads") }} · {{ periodLabel }}</div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-swap-vertical dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.transferred", "Transferred") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="me.downloads.bytes" :format="fmtBytes" /></div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-speedometer dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.avg_speed", "Avg download speed") }}</span></div>
                    <div class="dash-card-value"><DashStat v-if="me.downloads.avg_speed_bps" :value="me.downloads.avg_speed_bps" :format="fmtSpeed" /><span v-else>-</span></div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-playlist-check dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.your_requests", "Your requests") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="myReqTotal" /></div>
                    <div class="dash-card-sub">{{ me.requests.counts.pending || 0 }} {{ t("dashboard.pending", "pending") }}</div>
                  </div>
                </div>

                <div v-else-if="id === 'a_dl' && me.downloads.series && me.downloads.series.length" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-chart-timeline-variant dash-panel-ico"></i>{{ t("dashboard.download_activity", "Download activity") }} <span class="dash-mut">· {{ periodLabel }}</span></div>
                  <DashSparkline :series="me.downloads.series" :height="52" />
                  <div class="dash-spark-cap">{{ seriesTotal(me.downloads.series) }} {{ t("dashboard.downloads_in_period", "downloads in this period") }}</div>
                </div>

                <GameSavesPanel v-else-if="id === 'a_saves'" />

                <div v-else-if="id === 'a_reqs' && me.requests.items.length" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-playlist-star dash-panel-ico"></i>{{ t("dashboard.your_game_requests", "Your game requests") }}</div>
                  <div v-for="(r, i) in me.requests.items" :key="i" class="dash-req">
                    <span class="dash-req-title">{{ r.title }}</span>
                    <span class="dash-badge" :class="'st-' + r.status">{{ t("requests.status_" + r.status, r.status) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- SERVER OVERVIEW (admin) -->
      <section v-if="admin" class="dash-sect">
        <button class="dash-h2" @click="toggle('server')">
          <i class="mdi mdi-chevron-down dash-chev" :class="{ collapsed: collapsed.server }"></i>
          <i class="mdi mdi-server dash-h2-ico"></i>{{ t("dashboard.server_overview", "Server overview") }}
        </button>
        <div v-show="!collapsed.server" class="dash-srv">
          <template v-for="id in layoutServer" :key="id">
            <div v-if="editLayout || !isHidden(id)" class="dash-block" :class="{ 'is-edit': editLayout, 'is-hidden': isHidden(id), 'dash-block--wide': isWide(id) }" :draggable="editLayout" @dragstart="onDragStart('server', id, $event)" @dragover.prevent @drop="onDrop('server', id)">
              <div v-if="editLayout" class="dash-block-bar">
                <i class="mdi mdi-drag-horizontal-variant dash-block-grip"></i>
                <span class="dash-block-name">{{ blockLabel(id) }}</span>
                <button type="button" class="dash-block-eye" @click="toggleHide(id)"><i :class="isHidden(id) ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button>
              </div>
              <div class="dash-block-body">
                <div v-if="id === 's_stats'" class="dash-grid">
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-gamepad-variant dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.games_total", "Games total") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="admin.library.total" /></div>
                    <div class="dash-card-sub">GOG {{ admin.library.gog }} · Custom {{ admin.library.custom }} · ROM {{ admin.library.rom }}</div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-harddisk dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.library_size", "Library size") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="admin.library.size_bytes" :format="fmtBytes" /></div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-account-group dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.users", "Users") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="admin.users.total" /></div>
                    <div class="dash-card-sub">{{ admin.users.admins }} {{ t("dashboard.admins", "admins") }}</div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-download-network dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.downloads", "Downloads") }} <span class="dash-mut">{{ periodLabel }}</span></span></div>
                    <div class="dash-card-value"><DashStat :value="admin.downloads.count" /></div>
                    <div class="dash-card-sub">{{ fmtBytes(admin.downloads.bytes) }} · {{ t("dashboard.avg", "avg") }} {{ admin.downloads.avg_speed_bps ? fmtSpeed(admin.downloads.avg_speed_bps) : "-" }}</div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-email-fast-outline dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.emails_sent", "Emails sent") }}</span></div>
                    <div class="dash-card-value"><DashStat :value="admin.email.total" /></div>
                    <div class="dash-card-sub">{{ admin.email.in_range }} {{ t("dashboard.in_selected_range", "in selected range") }}</div>
                  </div>
                  <div class="dash-card glass">
                    <div class="dash-card-top"><i class="mdi mdi-account-star dash-card-ico"></i><span class="dash-card-title">{{ t("dashboard.most_active_user", "Most active user") }} <span class="dash-mut">{{ periodLabel }}</span></span></div>
                    <div class="dash-user">
                      <span class="dash-avatar">
                        <img v-if="topUserAvatar" :src="topUserAvatar" alt="" @error="(e) => ((e.target as HTMLImageElement).style.display = 'none')" />
                        <i v-else class="mdi mdi-account"></i>
                      </span>
                      <div class="dash-user-txt">
                        <div class="dash-card-value dash-card-value--sm">{{ admin.top_user ? admin.top_user.username : "-" }}</div>
                        <div v-if="admin.top_user" class="dash-card-sub">{{ admin.top_user.downloads }} {{ t("dashboard.downloads_word", "downloads") }} · {{ fmtBytes(admin.top_user.bytes) }}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <DashDownloadQueue v-else-if="id === 's_queue'" />

                <div v-else-if="id === 's_recent' && admin.recently_added.length" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-new-box dash-panel-ico"></i>{{ t("dashboard.recently_added", "Recently added") }}</div>
                  <DashCoverStrip :items="raItems" clickable hover="lift" @select="onRaSelect" />
                </div>

                <div v-else-if="id === 's_dl_chart'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-chart-bar dash-panel-ico"></i>{{ t("dashboard.downloads", "Downloads") }} <span class="dash-mut">· {{ periodLabel }}</span></div>
                  <DashSparkline :series="admin.downloads.series" :height="52" />
                  <div class="dash-spark-cap">{{ seriesTotal(admin.downloads.series) }} {{ t("dashboard.downloads_word", "downloads") }} · {{ fmtBytes(seriesBytes(admin.downloads.series)) }}</div>
                </div>

                <div v-else-if="id === 's_email_chart'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-email-fast dash-panel-ico"></i>{{ t("dashboard.email_activity", "Email activity") }} <span class="dash-mut">· {{ periodLabel }}</span></div>
                  <DashSparkline :series="admin.email.series" :height="52" />
                  <div class="dash-spark-cap">{{ seriesTotal(admin.email.series) }} {{ t("dashboard.sent_in_period", "sent in this period") }}</div>
                </div>

                <div v-else-if="id === 's_top_downloaded'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-fire dash-panel-ico"></i>{{ t("dashboard.top_downloaded", "Top downloaded") }} <span class="dash-mut">· {{ periodLabel }}</span></div>
                  <div v-if="!admin.top_downloaded.length" class="dash-av-empty">{{ t("dashboard.no_downloads_period", "No downloads in this period") }}</div>
                  <div v-else class="dash-td-list">
                    <div v-for="(g, i) in admin.top_downloaded" :key="g.id" class="dash-td-row dash-td-row--click" :title="t('dashboard.who_downloaded', 'Who downloaded this')" @click="openDownloaders(g.id, g.title)">
                      <span class="dash-td-rank">{{ i + 1 }}</span>
                      <span class="dash-td-cover"><i class="mdi mdi-gamepad-variant-outline"></i><img v-if="g.cover" :src="g.cover" alt="" @error="imgErr" /></span>
                      <span class="dash-td-title">{{ g.title }}</span>
                      <span class="dash-td-n">{{ g.downloads }}<i class="mdi mdi-download"></i></span>
                    </div>
                  </div>
                </div>

                <div v-else-if="id === 's_platforms' && admin.top_platforms.length" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-controller-classic dash-panel-ico"></i>{{ t("dashboard.top_platforms", "Top ROM platforms") }}</div>
                  <div v-for="p in admin.top_platforms" :key="p.name" class="dash-bar dash-bar--click" :title="p.name" @click="goPlatform(p.slug)">
                    <span class="dash-bar-nm">
                      <img v-if="p.logo && !logoFail.has(p.name)" :src="p.logo" :alt="p.name" class="dash-plat-logo" @error="logoFail.add(p.name)" />
                      <span v-else>{{ p.name }}</span>
                    </span>
                    <span class="dash-bar-track"><span class="dash-bar-fill" :style="{ width: pct(p.count, admin.top_platforms[0].count) }"></span></span>
                    <span class="dash-bar-n">{{ p.count }} · {{ fmtBytes(p.bytes) }}</span>
                  </div>
                </div>

                <div v-else-if="id === 's_health'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-heart-pulse dash-panel-ico"></i>{{ t("dashboard.server_health", "Server health") }}</div>
                  <div class="dash-kv"><span><i class="mdi mdi-cpu-64-bit dash-kv-ico"></i>CPU</span><b>{{ admin.server_health.cpu_percent != null ? admin.server_health.cpu_percent + "%" : "-" }}</b></div>
                  <span v-if="admin.server_health.cpu_percent != null" class="dash-bar-track"><span class="dash-bar-fill" :class="{ warn: admin.server_health.cpu_percent > 85 }" :style="{ width: admin.server_health.cpu_percent + '%' }"></span></span>
                  <div class="dash-kv"><span><i class="mdi mdi-memory dash-kv-ico"></i>RAM</span><b>{{ fmtBytes(admin.server_health.mem_used) }} / {{ fmtBytes(admin.server_health.mem_total) }}</b></div>
                  <span v-if="admin.server_health.mem_total" class="dash-bar-track"><span class="dash-bar-fill" :class="{ warn: memPct > 90 }" :style="{ width: memPct + '%' }"></span></span>
                  <div class="dash-kv"><span><i class="mdi mdi-clock-outline dash-kv-ico"></i>{{ t("dashboard.uptime", "Uptime") }}</span><span class="dash-mut">{{ fmtUptime(admin.server_health.uptime_seconds) }}</span></div>
                  <div class="dash-kv"><span><i class="mdi mdi-chip dash-kv-ico"></i>{{ t("dashboard.load", "Load") }} · {{ admin.server_health.cores }} {{ t("dashboard.cores", "cores") }}</span><span class="dash-mut">{{ admin.server_health.load1 != null ? admin.server_health.load1 : "-" }}</span></div>
                </div>

                <div v-else-if="id === 's_security'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-shield-lock dash-panel-ico"></i>{{ t("dashboard.security", "Security") }}</div>
                  <div class="dash-kv"><span><i class="mdi mdi-account-alert dash-kv-ico"></i>{{ t("dashboard.failed_logins", "Failed logins (window)") }}</span><b>{{ admin.security.failures.attempts }}</b></div>
                  <div class="dash-kv"><span><i class="mdi mdi-ip-network dash-kv-ico"></i>{{ t("dashboard.ips_failures", "IPs with failures") }}</span><b>{{ admin.security.failures.ips }}</b></div>
                  <div class="dash-kv"><span><i class="mdi mdi-cancel dash-kv-ico"></i>{{ t("dashboard.banned_ips", "Banned IPs") }}</span><b :class="{ warn: admin.security.banned.length }">{{ admin.security.banned.length }}</b></div>
                  <div v-for="b in admin.security.banned.slice(0, 4)" :key="b.ip" class="dash-kv dash-kv--sub"><span>{{ b.ip }}</span><span class="dash-mut">{{ Math.round(b.remaining_seconds / 60) }} {{ t("dashboard.min_left", "min left") }}</span></div>
                </div>

                <div v-else-if="id === 's_antivirus'" class="dash-panel glass">
                  <div class="dash-panel-h">
                    <i class="mdi mdi-shield-bug dash-panel-ico"></i>{{ t("dashboard.antivirus", "Antivirus") }}
                    <span class="dash-av-badge" :class="avClass">{{ avStatus }}</span>
                  </div>
                  <div class="dash-kv"><span><i class="mdi mdi-database-outline dash-kv-ico"></i>{{ t("dashboard.definitions", "Definitions") }}</span><span class="dash-mut">{{ admin.antivirus.db_version || "-" }}<template v-if="admin.antivirus.db_date"> · {{ fmtDate(admin.antivirus.db_date) }}</template></span></div>
                  <div class="dash-kv"><span><i class="mdi mdi-upload dash-kv-ico"></i>{{ t("dashboard.av_uploads", "Uploads") }}</span><b :class="admin.antivirus.upload_scan ? 'ok' : 'off'">{{ admin.antivirus.upload_scan ? "on" : "off" }}</b></div>
                  <div class="dash-kv"><span><i class="mdi mdi-download dash-kv-ico"></i>{{ t("dashboard.av_downloads", "Downloads") }}</span><b :class="admin.antivirus.download_scan ? 'ok' : 'off'">{{ admin.antivirus.download_scan ? "on" : "off" }}</b></div>
                  <div class="dash-kv"><span><i class="mdi mdi-biohazard dash-kv-ico"></i>{{ t("dashboard.quarantined", "Quarantined") }}</span><b :class="{ warn: admin.antivirus.quarantined }">{{ admin.antivirus.quarantined }}</b></div>
                  <div v-if="!admin.antivirus.recent.length" class="dash-av-empty"><i class="mdi mdi-shield-check"></i> {{ t("dashboard.no_threats", "No threats detected") }}</div>
                  <div v-else class="dash-av-list">
                    <div v-for="(q, i) in admin.antivirus.recent" :key="i" class="dash-av-row">
                      <i class="mdi mdi-bug dash-av-ico"></i>
                      <div class="dash-av-txt">
                        <div class="dash-av-name">{{ q.filename }}</div>
                        <div class="dash-av-meta">{{ q.threat }}<span class="dash-mut"> · {{ fmtDate(q.created_at) }}<template v-if="q.triggered_by"> · {{ t("dashboard.by", "by") }} {{ q.triggered_by }}</template></span></div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="id === 's_disk'" class="dash-panel glass">
                  <div class="dash-panel-h"><i class="mdi mdi-harddisk dash-panel-ico"></i>{{ t("dashboard.disk_space", "Disk space") }}</div>
                  <div v-for="d in admin.disk" :key="d.path" class="dash-disk">
                    <div class="dash-disk-top"><span>{{ d.label }} <span class="dash-mut">{{ d.path }}</span></span><span>{{ fmtBytes(d.free_bytes) }} {{ t("dashboard.free", "free") }} / {{ fmtBytes(d.total_bytes) }}</span></div>
                    <span class="dash-bar-track"><span class="dash-bar-fill" :class="{ warn: d.used_bytes / d.total_bytes > 0.9 }" :style="{ width: pct(d.used_bytes, d.total_bytes) }"></span></span>
                  </div>
                </div>

                <DashRequests v-else-if="id === 's_reqs'" />
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- PLUGIN CARDS -->
      <section v-if="cards.length" class="dash-sect">
        <button class="dash-h2" @click="toggle('plugins')">
          <i class="mdi mdi-chevron-down dash-chev" :class="{ collapsed: collapsed.plugins }"></i>
          <i class="mdi mdi-puzzle dash-h2-ico"></i>{{ t("dashboard.plugins", "Plugins") }}
        </button>
        <div v-show="!collapsed.plugins" class="dash-grid">
          <div v-for="c in cards" :key="c.id" class="dash-card glass" :class="{ 'dash-card--link': isInternal(c.link) }" @click="go(c.link)">
            <div class="dash-card-top">
              <i v-if="isMdi(c.icon)" :class="['mdi', c.icon, 'dash-card-ico']"></i>
              <img v-else-if="c.icon" :src="c.icon" class="dash-card-ico-img" alt="" />
              <span class="dash-card-title">{{ c.title }}</span>
            </div>
            <div v-if="c.value !== null && c.value !== undefined" class="dash-card-value">{{ c.value }}</div>
            <div v-if="c.subtitle" class="dash-card-sub">{{ c.subtitle }}</div>
          </div>
        </div>
      </section>
    </template>

    <div v-if="dl" class="dash-modal" @click.self="dl = null">
      <div class="dash-modal-box glass">
        <div class="dash-modal-h">
          <i class="mdi mdi-account-multiple dash-modal-ico"></i>
          <span class="dash-modal-title">{{ t("dashboard.who_downloaded", "Who downloaded this") }}<span v-if="dl.title" class="dash-mut"> · {{ dl.title }}</span></span>
          <button type="button" class="dash-modal-x" @click="dl = null"><i class="mdi mdi-close"></i></button>
        </div>
        <div v-if="dl.loading" class="dash-modal-loading"><span class="dash-spin"></span></div>
        <div v-else-if="!dl.rows.length" class="dash-av-empty">{{ t("dashboard.no_downloaders", "No downloads recorded") }}</div>
        <div v-else class="dash-modal-list">
          <div v-for="(u, i) in dl.rows" :key="i" class="dash-modal-row">
            <span class="dash-modal-rank">{{ i + 1 }}</span>
            <i class="mdi mdi-account dash-modal-uico"></i>
            <span class="dash-modal-user">{{ u.username }}</span>
            <span class="dash-mut">{{ u.count }}×</span>
            <span class="dash-mut">{{ fmtBytes(u.bytes) }}</span>
            <span v-if="u.last" class="dash-mut dash-modal-last">{{ fmtDate(u.last) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "@/i18n";
import client from "@/services/api/client";
import { useAuthStore } from "@/stores/auth";
import dashboardActions, { type UserDashboard, type AdminDashboard, type DaySample, type DashboardParams, type Downloader } from "@/lib/dashboardActions";
import DashStat from "@/components/DashStat.vue";
import DashSparkline from "@/components/DashSparkline.vue";
import GameSavesPanel from "@/components/GameSavesPanel.vue";
import DashRequests from "@/components/DashRequests.vue";
import DashCoverStrip from "@/components/DashCoverStrip.vue";
import DashDownloadQueue from "@/components/DashDownloadQueue.vue";
import { formatBytes as fmtBytes, formatDateShort } from '@/utils/format'
const fmtDate = (iso: string | null | undefined) => formatDateShort(iso, "")

interface Card { id: string; title: string; value?: unknown; subtitle?: string; icon?: string; link?: string; }
type PeriodKey = "24h" | "7d" | "30d" | "custom";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const me = ref<UserDashboard | null>(null);
const admin = ref<AdminDashboard | null>(null);
const cards = ref<Card[]>([]);
const loading = ref(true);
const refreshing = ref(false);
const logoFail = ref(new Set<string>()); // platform wordmarks that failed to load -> show text

const periods: Array<{ key: PeriodKey; label: string }> = [
  { key: "24h", label: "24h" }, { key: "7d", label: "7d" }, { key: "30d", label: "30d" }, { key: "custom", label: t("dashboard.period_custom", "Custom") },
];
const period = ref<PeriodKey>((localStorage.getItem("gd_dash_period") as PeriodKey) || "30d");
const customStart = ref(localStorage.getItem("gd_dash_start") || "");
const customEnd = ref(localStorage.getItem("gd_dash_end") || "");

const collapsed = ref<Record<string, boolean>>((() => {
  try { return JSON.parse(localStorage.getItem("gd_dash_collapsed") || "{}"); } catch { return {}; }
})());

// ── Customizable layout: reorder (drag) + show/hide each block, saved per user ──
// Continue playing and Recently played used to live here; they moved to the
// home page, where "jump back into a game" belongs, leaving the dashboard as the
// stats and operations console. mergeOrder() drops their saved ids for users who
// had reordered them.
const ACTIVITY_BLOCKS = ["a_cards", "a_dl", "a_saves", "a_reqs"];
// Each server panel is now its own block, so any single one can be moved or
// hidden independently (hiding Security no longer takes Health with it). Wide
// blocks span both columns; the rest tile two-per-row in the .dash-srv grid.
const SERVER_BLOCKS = ["s_stats", "s_queue", "s_recent", "s_dl_chart", "s_email_chart", "s_top_downloaded", "s_platforms", "s_health", "s_security", "s_antivirus", "s_disk", "s_reqs"];
const SERVER_WIDE = new Set(["s_stats", "s_queue", "s_recent", "s_reqs"]);
const editLayout = ref(false);
const layoutActivity = ref<string[]>([...ACTIVITY_BLOCKS]);
const layoutServer = ref<string[]>([...SERVER_BLOCKS]);
const hiddenBlocks = ref<Set<string>>(new Set());
const layoutKey = (): string => "gd_dash_layout_" + (auth.user?.id ?? "x");

function mergeOrder(def: string[], saved: unknown): string[] {
  if (!Array.isArray(saved)) return [...def];
  const known = new Set(def);
  const out = (saved as string[]).filter((id) => known.has(id));
  for (const id of def) if (!out.includes(id)) out.push(id); // append newly-added blocks
  return out;
}
function loadLayout(): void {
  try {
    const raw = JSON.parse(localStorage.getItem(layoutKey()) || "{}");
    layoutActivity.value = mergeOrder(ACTIVITY_BLOCKS, raw.activity);
    layoutServer.value = mergeOrder(SERVER_BLOCKS, raw.server);
    hiddenBlocks.value = new Set(Array.isArray(raw.hidden) ? raw.hidden : []);
  } catch { /* keep defaults */ }
}
function saveLayout(): void {
  try {
    localStorage.setItem(layoutKey(), JSON.stringify({
      activity: layoutActivity.value, server: layoutServer.value, hidden: [...hiddenBlocks.value],
    }));
  } catch { /* ignore */ }
}
function blockLabel(id: string): string {
  const m: Record<string, [string, string]> = {
    a_cards: ["dashboard.blk_overview", "Overview"], a_dl: ["dashboard.download_activity", "Download activity"],
    a_saves: ["profile.game_saves", "Game saves"],
    a_reqs: ["dashboard.your_requests", "Your requests"], s_stats: ["dashboard.blk_overview", "Overview"],
    s_queue: ["dashboard.blk_transfers", "Live transfers"], s_recent: ["dashboard.recently_added", "Recently added"],
    s_dl_chart: ["dashboard.downloads", "Downloads"], s_email_chart: ["dashboard.email_activity", "Email activity"],
    s_top_downloaded: ["dashboard.top_downloaded", "Top downloaded"], s_platforms: ["dashboard.top_platforms", "Top ROM platforms"],
    s_health: ["dashboard.server_health", "Server health"], s_security: ["dashboard.security", "Security"],
    s_antivirus: ["dashboard.antivirus", "Antivirus"], s_disk: ["dashboard.disk_space", "Disk space"],
    s_reqs: ["requests.title", "Game requests"],
  };
  const e = m[id];
  return e ? t(e[0], e[1]) : id;
}
function isHidden(id: string): boolean { return hiddenBlocks.value.has(id); }
function isWide(id: string): boolean { return SERVER_WIDE.has(id); } // spans both grid columns
function toggleHide(id: string): void {
  const h = new Set(hiddenBlocks.value);
  if (h.has(id)) h.delete(id); else h.add(id);
  hiddenBlocks.value = h;
  saveLayout();
}
function resetLayout(): void {
  layoutActivity.value = [...ACTIVITY_BLOCKS];
  layoutServer.value = [...SERVER_BLOCKS];
  hiddenBlocks.value = new Set();
  saveLayout();
}
let _dragId: string | null = null;
let _dragList: "activity" | "server" | null = null;
function onDragStart(list: "activity" | "server", id: string, e?: DragEvent): void {
  if (!editLayout.value) return;
  _dragId = id; _dragList = list;
  try { e?.dataTransfer?.setData("text/plain", id); } catch { /* Firefox needs some data set */ }
}
function onDrop(list: "activity" | "server", targetId: string): void {
  if (editLayout.value && _dragId && _dragList === list && _dragId !== targetId) {
    const target = list === "activity" ? layoutActivity : layoutServer;
    const arr = [...target.value];
    const from = arr.indexOf(_dragId), to = arr.indexOf(targetId);
    if (from >= 0 && to >= 0) { arr.splice(from, 1); arr.splice(to, 0, _dragId); target.value = arr; saveLayout(); }
  }
  _dragId = null; _dragList = null;
}

const periodLabel = computed(() => {
  if (period.value === "custom") return customStart.value && customEnd.value ? `${customStart.value} → ${customEnd.value}` : t("dashboard.period_custom", "Custom");
  return period.value;
});

const myReqTotal = computed(() =>
  me.value ? Object.values(me.value.requests.counts).reduce((a, b) => a + b, 0) : 0,
);
const topUserAvatar = computed(() => avatarUrl(admin.value?.top_user?.avatar_path));
const raItems = computed(() => (admin.value?.recently_added || []).map((it) => ({
  key: it.kind + it.id, cover: it.cover, title: it.title,
  kind: it.kind === "rom" ? "ROM" : it.kind === "gog" ? "GOG" : undefined,
  rkind: it.kind, id: it.id, platform_slug: it.platform_slug, // routing to the game detail
})));
// Recently-added tile -> its game detail. ROMs go to the emulation detail (needs
// the platform slug); GOG/custom library games go to the unified games detail.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function onRaSelect(it: any): void {
  const id = Number(it?.id ?? 0);
  if (!id) return;
  if (it?.rkind === "rom") {
    const slug = String(it?.platform_slug ?? "");
    if (slug) router.push(`/emulation/${slug}/${id}`);
  } else {
    router.push({ name: "games-detail", params: { id } });
  }
}
const avStatus = computed(() => {
  const a = admin.value?.antivirus;
  if (!a || !a.enabled) return t("dashboard.av_off", "Scanning off");
  return a.running ? t("dashboard.av_protected", "Protected") : t("dashboard.av_offline", "Daemon offline");
});
const avClass = computed(() => {
  const a = admin.value?.antivirus;
  if (!a || !a.enabled) return "off";
  return a.running ? "ok" : "warn";
});

function fmtSpeed(bps: number): string { return fmtBytes(bps) + "/s"; }
function pct(v: number, max: number): string { return (max > 0 ? Math.max(3, Math.round((v / max) * 100)) : 0) + "%"; }
function seriesTotal(s: DaySample[]): number { return s.reduce((a, d) => a + (d.count || 0), 0); }
function seriesBytes(s: DaySample[]): number { return s.reduce((a, d) => a + (d.bytes || 0), 0); }
function fmtUptime(sec: number): string {
  if (!sec) return "-";
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}
function imgErr(e: Event): void { (e.target as HTMLImageElement).style.display = "none"; }

// Interaction: drill down into a top-downloaded game / jump to a platform library.
const dl = ref<{ title: string | null; rows: Downloader[]; loading: boolean } | null>(null);
function openDownloaders(gameId: number, title: string): void {
  dl.value = { title, rows: [], loading: true };
  dashboardActions.gameDownloaders(gameId)
    .then((d) => { if (dl.value) { dl.value.rows = d.downloaders; dl.value.title = d.title || title; dl.value.loading = false; } })
    .catch(() => { if (dl.value) dl.value.loading = false; });
}
function goPlatform(slug: string): void { if (slug) router.push(`/emulation/${slug}`); }
const memPct = computed(() => {
  const h = admin.value?.server_health;
  return h && h.mem_total ? Math.round((h.mem_used / h.mem_total) * 100) : 0;
});
function avatarUrl(p?: string | null): string {
  if (!p) return "";
  if (p.startsWith("http")) return p;
  const fn = p.split(/[\\/]/).pop() || "";
  return fn ? `/resources/avatars/${fn}` : "";
}
function isMdi(icon?: string): boolean { return !!icon && icon.startsWith("mdi-"); }
function isInternal(link?: string): boolean { return !!link && link.startsWith("/"); }
function go(link?: string): void { if (isInternal(link)) router.push(link as string); }

function toggle(id: string): void {
  collapsed.value = { ...collapsed.value, [id]: !collapsed.value[id] };
  localStorage.setItem("gd_dash_collapsed", JSON.stringify(collapsed.value));
}

function currentParams(): DashboardParams {
  if (period.value === "custom") {
    return customStart.value && customEnd.value ? { start: customStart.value, end: customEnd.value } : { days: 30 };
  }
  return { days: period.value === "24h" ? 1 : period.value === "7d" ? 7 : 30 };
}

async function load(): Promise<void> {
  refreshing.value = true;
  const p = currentParams();
  const jobs: Promise<unknown>[] = [
    // The play strips moved to the home page, so this console no longer draws
    // them and should not pay for them either.
    dashboardActions.me({ ...p, sections: ["downloads", "requests"] })
      .then((d) => { me.value = d; }).catch(() => {}),
  ];
  if (auth.user?.role === "admin") {
    jobs.push(dashboardActions.admin(p).then((d) => { admin.value = d; }).catch(() => {}));
  }
  await Promise.all(jobs);
  refreshing.value = false;
  loading.value = false;
}

function setPeriod(k: PeriodKey): void {
  period.value = k;
  localStorage.setItem("gd_dash_period", k);
  if (k !== "custom" || (customStart.value && customEnd.value)) load();
}
function onCustom(): void {
  localStorage.setItem("gd_dash_start", customStart.value);
  localStorage.setItem("gd_dash_end", customEnd.value);
  if (customStart.value && customEnd.value) load();
}

// Live server-health heartbeat over Socket.IO (admin): keeps the health panel
// current without a page reload. Cheap - just /proc, shares the queue's socket.
let offHealth: (() => void) | undefined;
onMounted(() => {
  loadLayout();
  client.get("/plugins/dashboard/cards").then((r) => { cards.value = Array.isArray(r.data) ? r.data : []; }).catch(() => {});
  // Subscribe before the first await, not after. load() reads /proc, disk stats,
  // ClamAV and several aggregates, so it routinely takes over a second - and
  // leaving the page inside that window ran onUnmounted while offHealth was
  // still undefined, stranding the subscription that landed a moment later on a
  // dead component. The refcount then never reached zero and the server kept
  // pushing frames at a tab that was gone.
  if (auth.user?.role === "admin") {
    offHealth = dashboardActions.onHealth((h) => { if (admin.value) admin.value.server_health = h; });
  }
  load();
});
onUnmounted(() => { offHealth?.(); offHealth = undefined; });
</script>

<style scoped>
.dash { width: 100%; box-sizing: border-box; padding: 24px 28px; max-width: 1200px; margin: 0 auto; }
.dash-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
.dash-title { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; color: var(--text, #eee); }
.dash-title-ico { font-size: 24px; opacity: 0.85; color: var(--accent, #38d3db); }
.dash-period { display: flex; align-items: center; gap: 4px; padding: 3px; border-radius: 10px; background: color-mix(in srgb, var(--text, #888) 8%, transparent); }
.dash-per { font-size: 12px; font-weight: 600; padding: 5px 12px; border: 0; border-radius: 7px; cursor: pointer; background: transparent; color: var(--text, #eee); opacity: 0.6; transition: opacity 0.15s ease, background 0.15s ease; }
.dash-per:hover { opacity: 0.9; }
.dash-per.active { opacity: 1; background: color-mix(in srgb, var(--accent, #38d3db) 22%, transparent); }
.dash-refresh { width: 12px; height: 12px; margin: 0 4px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.25); border-top-color: var(--accent, #38d3db); animation: dashSpin 0.7s linear infinite; }
.dash-custom { display: flex; align-items: center; gap: 8px; margin: -6px 0 18px; }
.dash-date { background: color-mix(in srgb, var(--text, #888) 10%, transparent); border: 1px solid color-mix(in srgb, var(--text, #888) 18%, transparent); border-radius: 7px; color: var(--text, #eee); padding: 5px 8px; font-size: 12.5px; color-scheme: dark light; }
.dash-custom-sep { opacity: 0.5; }
.dash-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dash-edit-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; padding: 6px 12px; border: 0; border-radius: 8px; cursor: pointer; background: color-mix(in srgb, var(--text, #888) 8%, transparent); color: var(--text, #eee); opacity: 0.8; transition: opacity 0.15s ease, background 0.15s ease; }
.dash-edit-btn:hover { opacity: 1; }
.dash-edit-btn.active { background: color-mix(in srgb, var(--accent, #38d3db) 22%, transparent); opacity: 1; }
.dash-edit-btn i { font-size: 17px; }
.dash-edit-btn--ghost { padding: 6px 9px; }
.dash-edit-btn--ghost .dash-edit-lbl { display: none; }
/* Customizable blocks (drag to reorder, eye to hide) */
.dash-block-body > .dash-grid { margin-top: 14px; }
.dash-block.is-edit { border: 1px dashed color-mix(in srgb, var(--accent, #38d3db) 45%, transparent); border-radius: 12px; padding: 8px 10px 10px; margin-top: 12px; cursor: grab; background: color-mix(in srgb, var(--accent, #38d3db) 4%, transparent); }
.dash-block.is-edit:active { cursor: grabbing; }
.dash-block.is-edit .dash-block-body { pointer-events: none; }
.dash-block.is-edit .dash-block-body > * { margin-top: 6px; }
.dash-block.is-edit.is-hidden { opacity: 0.45; }
.dash-block-bar { display: flex; align-items: center; gap: 8px; padding: 2px 2px 4px; }
.dash-block-grip { font-size: 20px; opacity: 0.5; }
.dash-block-name { font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; opacity: 0.7; }
.dash-block-eye { margin-left: auto; background: transparent; border: 0; color: var(--text, #eee); cursor: pointer; font-size: 18px; opacity: 0.7; padding: 2px 6px; border-radius: 6px; }
.dash-block-eye:hover { opacity: 1; background: rgba(255,255,255,0.08); }
/* Clickable rows (drill-down) */
.dash-td-row--click, .dash-bar--click { cursor: pointer; border-radius: 6px; transition: background 0.12s ease; }
.dash-td-row--click:hover, .dash-bar--click:hover { background: color-mix(in srgb, var(--accent, #38d3db) 10%, transparent); }
/* Drill-down modal */
.dash-modal { position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center; padding: 20px; }
.dash-modal-box { width: min(480px, 100%); max-height: 80vh; overflow-y: auto; border-radius: 14px; padding: 16px 18px; }
.dash-modal-h { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; font-size: 13px; font-weight: 600; }
.dash-modal-ico { font-size: 22px; color: var(--accent, #38d3db); }
.dash-modal-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-modal-x { background: transparent; border: 0; color: var(--text, #eee); cursor: pointer; font-size: 20px; opacity: 0.7; }
.dash-modal-x:hover { opacity: 1; }
.dash-modal-loading { display: flex; justify-content: center; padding: 24px 0; }
.dash-modal-list { display: flex; flex-direction: column; gap: 2px; }
.dash-modal-row { display: flex; align-items: center; gap: 9px; font-size: 12.5px; padding: 6px 4px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.dash-modal-row:last-child { border-bottom: 0; }
.dash-modal-rank { width: 16px; text-align: center; opacity: 0.5; font-weight: 700; }
.dash-modal-uico { font-size: 16px; opacity: 0.6; }
.dash-modal-user { flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-modal-last { flex: 0 0 auto; }
.dash-sect { margin-bottom: 24px; }
.dash-h2 { display: flex; align-items: center; gap: 7px; width: 100%; text-align: left; background: transparent; border: 0; cursor: pointer; font-size: 12.5px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; color: var(--text, #eee); opacity: 0.6; margin: 0 0 12px; padding: 2px 0; transition: opacity 0.15s ease; }
.dash-h2:hover { opacity: 0.85; }
.dash-h2-ico { font-size: 22px; opacity: 0.9; }
.dash-chev { font-size: 17px; opacity: 0.8; transition: transform 0.2s ease; }
.dash-chev.collapsed { transform: rotate(-90deg); }
.dash-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.dash-card { border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; min-width: 0; transition: transform 0.16s ease, filter 0.16s ease; }
.dash-card:hover { transform: translateY(-2px); }
.dash-card--link { cursor: pointer; }
.dash-card--link:hover { filter: brightness(1.08); }
.dash-card-top { display: flex; align-items: center; gap: 8px; }
.dash-card-ico { font-size: 30px; opacity: 0.9; color: var(--accent, #38d3db); }
.dash-card-ico-img { width: 18px; height: 18px; }
.dash-card-title { font-size: 12px; font-weight: 600; letter-spacing: 0.3px; opacity: 0.75; text-transform: uppercase; }
.dash-card-value { font-size: 26px; font-weight: 700; color: var(--text, #eee); font-variant-numeric: tabular-nums; }
.dash-card-value--sm { font-size: 18px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-card-sub { font-size: 12px; opacity: 0.65; }
.dash-user { display: flex; align-items: center; gap: 10px; }
.dash-avatar { width: 40px; height: 40px; flex: 0 0 auto; border-radius: 50%; overflow: hidden; background: color-mix(in srgb, var(--accent, #38d3db) 18%, transparent); display: flex; align-items: center; justify-content: center; font-size: 20px; color: var(--accent, #38d3db); }
.dash-avatar img { width: 100%; height: 100%; object-fit: cover; }
.dash-user-txt { min-width: 0; }
.dash-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.dash-cols--av { margin-top: 0; gap: 18px; }
.dash-panel { border-radius: 12px; padding: 14px 16px; margin-top: 14px; min-width: 0; }
.dash-cols .dash-panel { margin-top: 0; }
/* Server overview: each panel is its own block tiled two-per-row, so any single
   one can be dragged or hidden. Wide blocks (cards, live queue, recently added,
   requests) span both columns. */
.dash-srv { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start; margin-top: 14px; }
.dash-srv > .dash-block { margin-top: 0; min-width: 0; }
.dash-srv > .dash-block.is-edit { margin-top: 0; }
.dash-srv > .dash-block--wide { grid-column: 1 / -1; }
.dash-srv > .dash-block > .dash-block-body > .dash-panel,
.dash-srv > .dash-block > .dash-block-body > .dash-grid { margin-top: 0; }
@media (max-width: 720px) { .dash-srv { grid-template-columns: 1fr; } }
.dash-panel-h { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; margin-bottom: 10px; }
.dash-panel-ico { font-size: 26px; opacity: 0.9; color: var(--accent, #38d3db); }
.dash-av-badge { margin-left: auto; font-size: 10px; padding: 2px 9px; border-radius: 20px; text-transform: none; letter-spacing: 0; font-weight: 600; }
.dash-av-badge.ok { background: color-mix(in srgb, #4ade80 20%, transparent); color: #4ade80; }
.dash-av-badge.warn { background: color-mix(in srgb, #fbbf24 22%, transparent); color: #fbbf24; }
.dash-av-badge.off { background: rgba(255,255,255,0.1); opacity: 0.7; }
.dash-av-empty { display: flex; align-items: center; gap: 7px; font-size: 12.5px; opacity: 0.6; padding: 6px 0; }
.dash-av-empty i { color: #4ade80; font-size: 16px; }
.dash-av-list { display: flex; flex-direction: column; gap: 6px; }
.dash-av-row { display: flex; align-items: center; gap: 9px; }
.dash-av-ico { color: #f87171; font-size: 16px; flex: 0 0 auto; }
.dash-av-txt { min-width: 0; }
.dash-av-name { font-size: 12.5px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-av-meta { font-size: 11px; opacity: 0.75; color: #f87171; }
.dash-spark-cap { font-size: 11.5px; opacity: 0.6; margin-top: 8px; text-align: right; }
.dash-strip { display: flex; gap: 12px; overflow-x: auto; padding: 2px 2px 8px; }
.dash-tile { flex: 0 0 auto; width: 92px; background: transparent; border: 0; padding: 0; cursor: pointer; text-align: left; color: var(--text, #eee); display: flex; flex-direction: column; gap: 4px; }
.dash-tile--static { cursor: default; }
.dash-tile-cover { position: relative; width: 92px; height: 122px; border-radius: 8px; overflow: hidden; background: color-mix(in srgb, var(--text, #888) 10%, transparent); display: flex; align-items: center; justify-content: center; }
.dash-tile-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.dash-tile-ph { font-size: 40px; opacity: 0.3; }
.dash-tile-play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.15s ease; font-size: 30px; color: #fff; }
.dash-tile:hover .dash-tile-play { opacity: 1; }
.dash-tile:hover .dash-tile-cover { filter: brightness(1.05); }
.dash-tile-kind { position: absolute; top: 5px; left: 5px; font-size: 8.5px; font-weight: 700; letter-spacing: 0.4px; padding: 1px 5px; border-radius: 4px; background: rgba(0,0,0,0.6); color: #fff; }
.dash-tile-name { font-size: 11.5px; font-weight: 500; line-height: 1.2; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
.dash-tile-sub { font-size: 10.5px; opacity: 0.55; }
.dash-td-list { display: flex; flex-direction: column; gap: 6px; }
.dash-td-row { display: flex; align-items: center; gap: 9px; }
.dash-td-rank { width: 16px; text-align: center; font-size: 12px; font-weight: 700; opacity: 0.5; flex: 0 0 auto; }
.dash-td-cover { position: relative; width: 30px; height: 40px; flex: 0 0 auto; border-radius: 4px; overflow: hidden; background: color-mix(in srgb, var(--text, #888) 10%, transparent); display: flex; align-items: center; justify-content: center; }
.dash-td-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.dash-td-cover i { font-size: 20px; opacity: 0.3; }
.dash-td-title { flex: 1; min-width: 0; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-td-n { flex: 0 0 auto; font-size: 12px; opacity: 0.7; display: inline-flex; align-items: center; gap: 3px; font-variant-numeric: tabular-nums; }
.dash-td-n i { font-size: 13px; opacity: 0.6; }
.dash-req { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.07); font-size: 13px; }
.dash-req:last-child { border-bottom: 0; }
.dash-req-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dash-badge { flex: 0 0 auto; margin-left: 10px; font-size: 10.5px; padding: 2px 8px; border-radius: 20px; text-transform: capitalize; font-weight: 600; background: rgba(255,255,255,0.1); }
.st-pending { background: color-mix(in srgb, #fbbf24 22%, transparent); color: #fbbf24; }
.st-approved, .st-available, .st-fulfilled, .st-done { background: color-mix(in srgb, #4ade80 20%, transparent); color: #4ade80; }
.st-rejected, .st-denied { background: color-mix(in srgb, #f87171 20%, transparent); color: #f87171; }
.dash-bar { display: flex; align-items: center; gap: 10px; font-size: 12.5px; padding: 4px 0; }
.dash-bar-nm { width: 156px; flex: 0 0 auto; opacity: 0.9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: flex; align-items: center; justify-content: center; }
.dash-plat-logo { max-height: 30px; max-width: 150px; object-fit: contain; opacity: 0.95; }
.dash-bar-track { flex: 1; height: 8px; border-radius: 6px; background: rgba(255,255,255,0.08); overflow: hidden; display: block; }
.dash-bar-fill { display: block; height: 100%; border-radius: 6px; background: var(--accent, #38d3db); transform-origin: left; }
.dash-bar-fill.warn { background: #fbbf24; }
.dash-bar-n { flex: 0 0 auto; min-width: 40px; text-align: right; opacity: 0.7; font-variant-numeric: tabular-nums; white-space: nowrap; }
.dash-kv { display: flex; align-items: center; justify-content: space-between; font-size: 13px; padding: 5px 0; }
.dash-kv > span:first-child { display: inline-flex; align-items: center; gap: 7px; }
.dash-kv-ico { font-size: 30px; opacity: 0.7; }
.dash-kv--sub { font-size: 11.5px; opacity: 0.8; }
.dash-kv b.warn { color: #fbbf24; }
.dash-kv b.ok { color: #4ade80; }
.dash-kv b.off { opacity: 0.55; font-weight: 500; }
.dash-mut { opacity: 0.55; font-size: 11px; text-transform: none; letter-spacing: 0; }
.dash-disk { margin-bottom: 12px; }
.dash-disk:last-child { margin-bottom: 0; }
.dash-disk-top { display: flex; justify-content: space-between; font-size: 12.5px; margin-bottom: 6px; }
.dash-empty { display: flex; align-items: center; gap: 10px; opacity: 0.6; font-size: 14px; padding: 40px 0; }
.dash-spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.25); border-top-color: var(--accent, #38d3db); animation: dashSpin 0.7s linear infinite; }
@keyframes dashSpin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: no-preference) {
  .dash-card, .dash-panel { animation: dashIn 0.42s ease backwards; }
  .dash-grid .dash-card:nth-child(2) { animation-delay: 0.05s; }
  .dash-grid .dash-card:nth-child(3) { animation-delay: 0.1s; }
  .dash-grid .dash-card:nth-child(4) { animation-delay: 0.15s; }
  .dash-grid .dash-card:nth-child(5) { animation-delay: 0.2s; }
  .dash-grid .dash-card:nth-child(6) { animation-delay: 0.25s; }
  .dash-bar-fill { animation: barGrow 0.8s cubic-bezier(0.22, 1, 0.36, 1) backwards; }
}
@keyframes dashIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes barGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

.is-refreshing .dash-sect { opacity: 0.7; transition: opacity 0.2s ease; }
@media (max-width: 720px) { .dash-cols { grid-template-columns: 1fr; } }
</style>
