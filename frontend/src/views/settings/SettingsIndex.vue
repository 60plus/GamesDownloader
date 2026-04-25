<template>
  <div class="settings-root">

    <!-- ── Header ──────────────────────────────────────────────────────────── -->
    <div class="settings-header">
      <button class="back-btn" @click="router.back()" title="Go back">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        {{ t('common.back') }}
      </button>
      <h1 class="settings-title">{{ t('settings.title') }}</h1>
    </div>

    <!-- ── Tabs ────────────────────────────────────────────────────────────── -->
    <div class="settings-tabs">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        class="stab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <component :is="tab.icon" />
        {{ t('settings.' + tab.key) || tab.label }}
      </button>
    </div>

    <!-- ── Content ─────────────────────────────────────────────────────────── -->
    <div class="settings-body">
      <div class="settings-content">
        <component :is="activeComponent" />
      </div>
      <aside class="settings-hint" :class="{ 'settings-hint--active': hintTitle }">
        <div v-if="hintTitle" class="hint-card">
          <transition name="hint-fade">
            <div class="hint-inner">
              <div class="hint-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>
                  <line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>
                  <line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>
                  <line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>
                  <line x1="17" y1="16" x2="23" y2="16"/>
                </svg>
              </div>
              <div class="hint-title">{{ hintTitle }}</div>
              <p class="hint-body">{{ hintBody }}</p>
            </div>
          </transition>
        </div>
        <div v-else class="hint-placeholder">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.15">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4m0-4h.01" stroke-linecap="round"/>
          </svg>
          <span>{{ t('settings.hint') }}</span>
        </div>
      </aside>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const router    = useRouter()
const auth      = useAuthStore()
const isAdmin   = computed(() => auth.user?.role === 'admin')
const route     = useRoute()
const activeTab = ref((route.query.tab as string) || 'appearance')
const { hintTitle, hintBody } = useSettingsHint()

// ── Inline SVG icon helpers ───────────────────────────────────────────────
const icons = {
  appearance: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('circle', { cx:12, cy:12, r:10 }),
    h('circle', { cx:12, cy:12, r:3, fill:'currentColor', stroke:'none' }),
  ]),
  security: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('path', { d:'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' }),
  ]),
  metadata: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('circle', { cx:11, cy:11, r:7 }), h('path', { d:'M21 21l-4.35-4.35' }),
  ]),
  downloads: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('path', { d:'M12 2v10m0 0l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.56 21H19.44a2 2 0 0 0 1.94-1.515L22 17' }),
  ]),
  notifications: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('path', { d:'M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9' }),
    h('path', { d:'M13.73 21a2 2 0 0 1-3.46 0' }),
  ]),
  plugins: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('path', { d:'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z' }),
  ]),
  gog: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('circle', { cx:12, cy:12, r:9 }),
    h('path', { d:'M12 8v4l3 3' }),
    h('path', { d:'M15 12h-3' }),
  ]),
  roms: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('rect', { x:2, y:6, width:20, height:14, rx:2 }),
    h('circle', { cx:8, cy:13, r:1.5 }),
    h('circle', { cx:16, cy:13, r:1.5 }),
    h('path', { d:'M6 10h4M8 8v4M14 11h4' }),
  ]),
  users: () => h('svg', { width:14, height:14, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':2 }, [
    h('path', { d:'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2' }),
    h('circle', { cx:9, cy:7, r:4 }),
    h('path', { d:'M23 21v-2a4 4 0 0 0-3-3.87' }),
    h('path', { d:'M16 3.13a4 4 0 0 1 0 7.75' }),
  ]),
}

const ALL_TABS = [
  { key: 'appearance',    label: 'Appearance',    icon: icons.appearance,    adminOnly: false },
  { key: 'security',      label: 'Security',      icon: icons.security,      adminOnly: true  },
  { key: 'gog',           label: 'GOG',           icon: icons.gog,           adminOnly: true  },
  { key: 'metadata',      label: 'Metadata',      icon: icons.metadata,      adminOnly: true  },
  { key: 'downloads',     label: 'Downloads',     icon: icons.downloads,     adminOnly: true  },
  { key: 'roms',          label: 'ROMs',          icon: icons.roms,          adminOnly: true  },
  { key: 'notifications', label: 'Notifications', icon: icons.notifications, adminOnly: true  },
  { key: 'plugins',       label: 'Plugins',       icon: icons.plugins,       adminOnly: true  },
  { key: 'pluginstore',   label: 'Plugin Store',  icon: icons.plugins,       adminOnly: true  },
  { key: 'users',         label: 'Users',         icon: icons.users,         adminOnly: true  },
]

const TABS = computed(() => ALL_TABS.filter(t => !t.adminOnly || isAdmin.value))

const views: Record<string, ReturnType<typeof defineAsyncComponent>> = {
  appearance:    defineAsyncComponent(() => import('./SettingsAppearance.vue')),
  security:      defineAsyncComponent(() => import('./SettingsSecurity.vue')),
  gog:           defineAsyncComponent(() => import('./SettingsGog.vue')),
  metadata:      defineAsyncComponent(() => import('./SettingsMetadata.vue')),
  downloads:     defineAsyncComponent(() => import('./SettingsDownloads.vue')),
  roms:          defineAsyncComponent(() => import('./SettingsRoms.vue')),
  notifications: defineAsyncComponent(() => import('./SettingsNotifications.vue')),
  plugins:       defineAsyncComponent(() => import('./SettingsPlugins.vue')),
  pluginstore:   defineAsyncComponent(() => import('./SettingsPluginStore.vue')),
  users:         defineAsyncComponent(() => import('@/views/admin/AdminUsers.vue')),
}

// Ensure activeTab is always valid for the current role
const activeComponent = computed(() => {
  const valid = TABS.value.some(t => t.key === activeTab.value)
  if (!valid) activeTab.value = 'appearance'
  return views[activeTab.value] ?? views.appearance
})
</script>

<style scoped>
.settings-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 0;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
.settings-header {
  display: flex;
  align-items: center;
  gap: var(--space-4, 16px);
  padding: 20px 28px 16px;
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.05);
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
  flex-shrink: 0;
}
.back-btn:hover {
  background: var(--glass-highlight);
  border-color: var(--pl);
  color: var(--text);
}

.settings-title {
  font-size: var(--fs-2xl, 22px);
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

/* ── Tab bar ──────────────────────────────────────────────────────────────── */
.settings-tabs {
  display: flex;
  gap: 2px;
  padding: 0 28px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  overflow-x: auto;
}
.settings-tabs::-webkit-scrollbar { height: 0; }

.stab {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--transition);
  margin-bottom: -1px;
}
.stab:hover { color: var(--text); }
.stab.active {
  color: var(--pl-light);
  border-bottom-color: var(--pl);
}

/* ── Body ─────────────────────────────────────────────────────────────────── */
.settings-body {
  flex: 1;
  display: flex;
  justify-content: center;
  overflow: hidden;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.settings-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  overflow-x: auto;
  padding: 28px;
}

/* ── Hint panel ───────────────────────────────────────────────────────────── */
.settings-hint {
  flex: 1;
  min-width: 200px;
  max-width: 380px;
  border-left: 1px solid var(--glass-border);
  padding: 32px 32px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.hint-card {
  max-width: 340px;
  border: 1.5px solid var(--glass-border);
  border-radius: var(--radius);
  background: var(--glass-bg);
  padding: 20px 24px;
  backdrop-filter: blur(var(--glass-blur-px, 22px));
}

.hint-inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm, 8px);
  background: var(--pl-dim);
  border: 1px solid var(--pl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--pl-light);
  flex-shrink: 0;
  margin-bottom: 2px;
}

.hint-title {
  font-size: var(--fs-md, 14px);
  font-weight: 700;
  color: var(--pl-light);
  line-height: 1.3;
}

.hint-body {
  font-size: var(--fs-sm, 12px);
  color: var(--muted);
  line-height: 1.65;
  margin: 0;
}

.hint-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding-top: 24px;
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
  text-align: center;
  opacity: 0.6;
}

/* Transition */
.hint-fade-enter-active,
.hint-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.hint-fade-enter-from,
.hint-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .settings-tabs { padding: 0 6px; gap: 0; }
  .stab { padding: 6px 6px; font-size: var(--fs-xs, 10px); gap: 3px; }
  .stab svg { display: none; }
  .settings-content { padding: 14px 10px; }
  .settings-hint { display: none; }
}
</style>
