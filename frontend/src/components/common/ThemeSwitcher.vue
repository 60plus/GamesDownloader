<template>
  <!-- ── COMPACT mode (sidebar bottom) ──────────────────────────────────── -->
  <div v-if="compact" class="ts-compact">
    <button class="ts-compact-btn" @click.stop="open = !open" :title="t('theme.switcher_title')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 2a7 7 0 0 1 7 7c0 3.87-3.13 7-7 7S5 12.87 5 9a7 7 0 0 1 7-7z" opacity=".4"/>
        <circle cx="12" cy="12" r="3" fill="var(--pl)" stroke="none"/>
      </svg>
      <span>{{ t('settings.appearance') }}</span>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
        :style="open ? 'transform:rotate(180deg)' : ''" style="transition:transform .15s; margin-left:auto;">
        <polyline points="18 15 12 9 6 15"/>
      </svg>
    </button>

    <transition name="slide-down">
      <div v-if="open" class="ts-compact-panel glass-panel">
        <!-- Theme -->
        <div class="ts-section-label">{{ t('theme.layout') }}</div>
        <div class="ts-theme-row">
          <button
            v-for="t in themes"
            :key="t.id"
            class="ts-theme-btn"
            :class="{ active: themeStore.themeId === t.id }"
            @click="themeStore.setTheme(t.id)"
            :title="ts(t.name)"
          >
            <span class="ts-theme-ico">{{ t.layout === 'modern' ? '⬛' : '▤' }}</span>
            <span>{{ ts(t.name) }}</span>
          </button>
        </div>

        <!-- Skin swatches -->
        <div class="ts-section-label" style="margin-top:8px">{{ t('theme.skin') }}</div>
        <div class="ts-skin-row">
          <button
            v-for="s in skins"
            :key="s.id"
            class="ts-swatch"
            :class="{ active: themeStore.skinId === s.id }"
            :style="{ background: s.preview }"
            @click="themeStore.setSkin(s.id)"
            :title="ts(s.name)"
          />
        </div>

        <!-- Toggles -->
        <div class="ts-toggles">
          <button class="ts-toggle" :class="{ on: themeStore.animations }" @click="themeStore.toggleAnimations()">
            <span class="ts-toggle-dot" />
            {{ t('theme.animations') }}
          </button>
          <button class="ts-toggle" :class="{ on: themeStore.ambient }" @click="themeStore.toggleAmbient()">
            <span class="ts-toggle-dot" />
            {{ t('theme.orbs') }}
          </button>
          <button
            v-if="themeStore.ambient"
            class="ts-toggle ts-toggle--sub"
            :class="{ on: themeStore.orbMotion }"
            @click="themeStore.toggleOrbMotion()"
          >
            <span class="ts-toggle-dot" />
            {{ t('theme.orb_motion') }}
          </button>
        </div>
      </div>
    </transition>
  </div>

  <!-- ── FULL mode (Settings > Appearance) ──────────────────────────────── -->
  <div v-else class="ts-full">

    <!-- Themes -->
    <div class="ts-section">
      <div class="ts-title">{{ t('theme.layout') }}</div>
      <div class="ts-desc">{{ t('theme.layout_desc') }}</div>
      <div class="ts-theme-cards">
        <button
          v-for="t in themes"
          :key="t.id"
          class="ts-theme-card"
          :class="{ active: themeStore.themeId === t.id }"
          @click="themeStore.setTheme(t.id)"
          @mouseenter="setHint(ts('ts.hint.layout') + ': ' + ts(t.name), ts(t.description))"
          @mouseleave="clearHint()"
        >
          <!-- Mini preview -->
          <div class="ts-card-preview" :class="`preview--${t.layout}`">
            <div v-if="t.layout === 'modern'" class="prev-modern">
              <div class="prev-navbar">
                <div class="prev-logo" />
                <div class="prev-nav-chip" />
                <div class="prev-nav-spacer" />
                <div class="prev-nav-avatar" />
              </div>
              <div class="prev-content">
                <div class="prev-card" v-for="n in 8" :key="n" />
              </div>
            </div>
            <div v-else-if="t.layout === 'classic'" class="prev-classic">
              <div class="prev-sidebar">
                <div class="prev-shead">
                  <div class="prev-shead-ico" />
                  <div class="prev-shead-label" />
                </div>
                <div class="prev-sitem" v-for="n in 6" :key="n" :class="n === 3 ? 'prev-sitem--active' : ''" />
              </div>
              <div class="prev-detail">
                <div class="prev-hero-bg" />
                <div class="prev-cover-box" />
              </div>
            </div>
            <!-- Plugin themes: custom preview from plugin, or generic fallback -->
            <div v-else-if="t.previewHtml" class="prev-plugin" v-html="sanitizePreview(t.previewHtml)" />
            <div v-else class="prev-plugin">
              <div class="prev-plugin-nav">
                <div class="prev-plugin-logo" />
                <div class="prev-plugin-tab" />
                <div class="prev-plugin-tab prev-plugin-tab--active" />
                <div class="prev-plugin-tab" />
              </div>
              <div class="prev-plugin-hero" />
              <div class="prev-plugin-row">
                <div class="prev-plugin-tile" v-for="n in 5" :key="n" />
              </div>
            </div>
          </div>
          <div class="ts-card-footer">
            <span class="ts-card-name">{{ ts(t.name) }}</span>
            <span v-if="themeStore.themeId === t.id" class="ts-card-active-dot" />
          </div>
          <div class="ts-card-desc">{{ ts(t.description) }}</div>
        </button>
      </div>
    </div>

    <!-- Skins -->
    <div class="ts-section">
      <div class="ts-title">{{ t('theme.skin') }}</div>
      <div class="ts-desc">{{ t('theme.skin_desc') }}</div>
      <!-- Row 1: Solid skins -->
      <div class="ts-skin-row-label">{{ t('theme.solid') }}</div>
      <div class="ts-skin-grid">
        <button
          v-for="s in solidSkins"
          :key="s.id"
          class="ts-skin-item"
          :class="{ active: themeStore.skinId === s.id }"
          @click="themeStore.setSkin(s.id)"
          @mouseenter="setHint(t('ts.hint.skin', 'Skin') + ': ' + ts(s.name), t('ts.hint.skinSolid', 'Switches the color palette. All accent colors, glows, active states, and toggle highlights will update to match.'))"
          @mouseleave="clearHint()"
        >
          <div class="ts-skin-swatch" :style="{ background: s.preview }" />
          <span class="ts-skin-name">{{ ts(s.name) }}</span>
        </button>
      </div>
      <!-- Row 2: Dual-color skins -->
      <div class="ts-skin-row-label" style="margin-top:10px">{{ t('theme.dual') }}</div>
      <div class="ts-skin-grid">
        <button
          v-for="s in dualSkins"
          :key="s.id"
          class="ts-skin-item"
          :class="{ active: themeStore.skinId === s.id }"
          @click="themeStore.setSkin(s.id)"
          @mouseenter="setHint(t('ts.hint.skin', 'Skin') + ': ' + ts(s.name), t('ts.hint.skinDual', 'Two-color gradient skin: accent and glow use two distinct hues for a vivid dual-tone look.'))"
          @mouseleave="clearHint()"
        >
          <div class="ts-skin-swatch" :style="{ background: s.preview }" />
          <span class="ts-skin-name">{{ ts(s.name) }}</span>
        </button>
      </div>
    </div>

    <!-- Display Options -->
    <div class="ts-section">
      <div class="ts-title">{{ t('theme.display') }}</div>
      <div class="ts-desc">{{ t('theme.display_desc') }}</div>
      <div class="ts-option-list">

        <!-- Animations -->
        <ThemeOptionRow
          label="theme.animations"
          hint="theme.animations_hint"
          hint-body="hint.animations"
          type="toggle"
          :model-value="themeStore.animations"
          @update:model-value="themeStore.toggleAnimations()"
        />

        <!-- Ambient Orbs -->
        <ThemeOptionRow
          label="theme.orbs"
          hint="theme.orbs_hint"
          hint-body="hint.orbs"
          type="toggle"
          :model-value="themeStore.ambient"
          :disabled="!themeStore.supportsEffect('ambient')"
          :unavailable="!themeStore.supportsEffect('ambient')"
          @update:model-value="themeStore.toggleAmbient()"
        />

        <!-- Orb Motion (sub) -->
        <ThemeOptionRow
          label="theme.orb_motion"
          hint="theme.orb_motion_hint"
          hint-body="hint.orb_motion"
          type="toggle"
          sub
          :model-value="themeStore.orbMotion && themeStore.ambient"
          :disabled="!themeStore.ambient || !themeStore.supportsEffect('orbMotion')"
          :unavailable="!themeStore.supportsEffect('orbMotion')"
          @update:model-value="themeStore.toggleOrbMotion()"
        />

        <!-- Static orb settings (always visible when ambient on) -->
        <ThemeOptionRow
          v-for="setting in (themeStore.ambient ? staticOrbSettings : [])"
          :key="setting.key"
          v-bind="rowProps(setting)"
          sub
          orb
          :model-value="themeStore.getThemeSettingValue(setting.key)"
          @update:model-value="v => themeStore.setThemeSettingValue(setting.key, v)"
        />

        <!-- Motion orb settings (visible only when ambient AND orbMotion on) -->
        <ThemeOptionRow
          v-for="setting in (themeStore.ambient && themeStore.orbMotion ? motionOrbSettings : [])"
          :key="setting.key"
          v-bind="rowProps(setting)"
          sub
          orb
          :model-value="themeStore.getThemeSettingValue(setting.key)"
          @update:model-value="v => themeStore.setThemeSettingValue(setting.key, v)"
        />

      </div>
    </div>

    <!-- Per-theme settings (non-orb only) -->
    <div v-if="nonOrbSettings.length" class="ts-section">
      <div class="ts-title-row">
        <div>
          <div class="ts-title">{{ t('theme.settings_title').replace('{name}', ts(currentTheme?.name || '')) }}</div>
          <div class="ts-desc">{{ t('theme.settings_desc').replace('{name}', ts(currentTheme?.name || '')) }}</div>
        </div>
        <button class="ts-reset-btn" @click="themeStore.resetThemeSettings()" :title="t('theme.reset')">
          {{ t('theme.reset') }}
        </button>
      </div>
      <div class="ts-option-list">
        <ThemeOptionRow
          v-for="setting in nonOrbSettings"
          :key="setting.key"
          v-bind="rowProps(setting)"
          :model-value="themeStore.getThemeSettingValue(setting.key)"
          @update:model-value="v => themeStore.setThemeSettingValue(setting.key, v)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { sanitizePreviewHtml } from '@/utils/sanitize'
import ThemeOptionRow from '@/components/common/ThemeOptionRow.vue'
import type { ThemeSetting } from '@/themes'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// Translate theme setting labels/hints - tries t(key), falls back to raw string
function ts(val: string): string { const r = t(val, val); return r }

function sanitizePreview(html: string): string {
  return sanitizePreviewHtml(html)
}

defineProps<{ compact?: boolean }>()

const themeStore   = useThemeStore()
const open         = ref(false)

const themes       = computed(() => themeStore.themes)
const skins        = computed(() => themeStore.currentSkins)
const solidSkins   = computed(() => skins.value.filter(s => !s.dual))
const dualSkins    = computed(() => skins.value.filter(s => s.dual))
const currentTheme = computed(() => themeStore.currentTheme)

// Split settings: orb-section (shown in Display Options) vs the rest (Theme Settings)
const staticOrbSettings = computed(() => currentTheme.value?.settings?.filter(s => s.section === 'orb' && !s.motion) ?? [])
const motionOrbSettings  = computed(() => currentTheme.value?.settings?.filter(s => s.section === 'orb' && s.motion)  ?? [])
const nonOrbSettings    = computed(() => currentTheme.value?.settings?.filter(s => s.section !== 'orb') ?? [])

// The one place that knows which field of a theme setting feeds which part of
// a row. Everything a theme declares goes through here, so a select, a slider
// and a switch cannot drift apart.
function rowProps(s: ThemeSetting) {
  return {
    label: s.label,
    hint: s.hint,
    hintBody: s.description ?? s.hint ?? '',
    type: s.type,
    options: s.options,
    optionLabels: s.optionLabels,
    min: s.min,
    max: s.max,
    step: s.step,
    unit: s.unit,
  }
}

const { setHint, clearHint } = useSettingsHint()
</script>

<style scoped>
/* ════════════════════ COMPACT MODE ════════════════════ */
.ts-compact { position: relative; }

.ts-compact-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  width: 100%;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 8px);
  background: none;
  cursor: pointer;
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  font-family: inherit;
  transition: all var(--transition);
}
.ts-compact-btn:hover {
  background: var(--glass-highlight);
  border-color: var(--glass-border);
  color: var(--text);
}

.ts-compact-panel {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  padding: 10px;
  border-radius: 10px;
  box-shadow: 0 -12px 32px rgba(0, 0, 0, 0.5);
  z-index: 200;
}

.ts-section-label {
  font-size: var(--fs-xs, 10px);
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 5px;
}

.ts-theme-row {
  display: flex;
  gap: var(--space-1, 4px);
}
.ts-theme-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--glass-border);
  background: none;
  cursor: pointer;
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  color: var(--muted);
  font-family: inherit;
  transition: all var(--transition);
}
.ts-theme-btn.active {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}
.ts-theme-btn:hover:not(.active) {
  background: var(--glass-highlight);
  color: var(--text);
}
.ts-theme-ico { font-size: var(--fs-xs, 10px); }

.ts-skin-row {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
.ts-swatch {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition);
  flex-shrink: 0;
}
.ts-swatch.active {
  border-color: var(--text);
  box-shadow: 0 0 0 2px var(--pl);
  transform: scale(1.15);
}
.ts-swatch:hover:not(.active) { transform: scale(1.1); }

.ts-toggles {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 8px;
}
.ts-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 4px;
  border-radius: 5px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  font-family: inherit;
  transition: color var(--transition);
}
.ts-toggle:hover { color: var(--text); }
.ts-toggle.on { color: var(--pl-light); }
.ts-toggle--sub {
  padding-left: 18px;
  border-left: 2px solid var(--glass-border);
  margin-left: 4px;
  font-size: var(--fs-xs, 10px);
}
.ts-toggle-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--muted);
  flex-shrink: 0;
  transition: background var(--transition);
}
.ts-toggle.on .ts-toggle-dot { background: var(--pl-light); box-shadow: 0 0 6px var(--pglow); }

/* ════════════════════ FULL MODE ════════════════════════ */
.ts-full { display: flex; flex-direction: column; gap: var(--space-8, 32px); }

.ts-section { display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.ts-title { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); }
.ts-desc { font-size: 13px; color: var(--muted); }

/* Theme cards */
.ts-theme-cards {
  display: flex;
  gap: var(--space-4, 16px);
  flex-wrap: wrap;
}
.ts-theme-card {
  flex: 1;
  min-width: 200px;
  max-width: 280px;
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
  padding: var(--space-3, 12px);
  border-radius: var(--radius);
  border: 1.5px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  transition: all var(--transition);
  font-family: inherit;
  text-align: left;
}
.ts-theme-card:hover {
  border-color: var(--pl);
  background: var(--glass-highlight);
}
.ts-theme-card.active {
  border-color: var(--pl);
  box-shadow: 0 0 0 1px var(--pl), 0 0 20px var(--pglow2);
}

.ts-card-preview {
  height: 90px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg2);
  border: 1px solid var(--glass-border);
  /* plugin previewHtml may contain position:absolute accents; without this
     they anchor to the viewport and float over the page (stray dot top-right) */
  position: relative;
}
/* ── Modern preview ── */
.prev-modern {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.prev-navbar {
  height: 18px;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-1, 4px);
  padding: 0 5px;
}
.prev-logo {
  width: 12px; height: 8px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  opacity: .8;
}
.prev-nav-chip {
  width: 18px; height: 6px;
  border-radius: 3px;
  background: rgba(255,255,255,.15);
}
.prev-nav-spacer { flex: 1; }
.prev-nav-avatar {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  opacity: .6;
}
.prev-content {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  padding: 5px;
  align-content: flex-start;
}
.prev-card {
  width: calc(25% - 3px);
  aspect-ratio: 3/4;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  flex: none;
}

/* ── Classic preview ── */
.prev-classic {
  display: flex;
  height: 100%;
}
.prev-sidebar {
  width: 44px;
  background: rgba(10, 6, 24, .7);
  border-right: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
  overflow: hidden;
}
.prev-shead {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 4px 4px 3px;
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: 2px;
}
.prev-shead-ico {
  width: 16px; height: 16px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  opacity: .6;
}
.prev-shead-label {
  width: 28px; height: 3px;
  border-radius: 2px;
  background: rgba(255,255,255,.25);
}
.prev-sitem {
  height: 7px;
  margin: 0 4px;
  background: rgba(255, 255, 255, 0.07);
  border-radius: 2px;
  display: flex;
  align-items: center;
}
.prev-sitem::before {
  content: '';
  display: block;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: rgba(255,255,255,.15);
  margin-left: 2px;
  flex-shrink: 0;
}
.prev-sitem--active {
  background: var(--pl-dim);
  border-left: 2px solid var(--pl);
}
.prev-sitem--active::before {
  background: color-mix(in srgb, var(--pl) 30%, transparent);
}
.prev-detail {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.prev-hero-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(109,40,217,.25) 0%, rgba(10,6,24,.8) 100%);
}
.prev-cover-box {
  position: relative;
  z-index: 1;
  width: 26px;
  height: 38px;
  border-radius: 3px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(139,92,246,.5);
  box-shadow: 0 4px 16px rgba(0,0,0,.6);
}

/* ── Plugin theme preview (generic, works for any plugin layout) ── */
.prev-plugin {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #05050f;
}
.prev-plugin-nav {
  height: 12px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 0 4px;
  background: rgba(255,255,255,.04);
  border-bottom: 1px solid rgba(0,212,255,.15);
  flex-shrink: 0;
}
.prev-plugin-logo {
  width: 8px; height: 8px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  opacity: .7;
  flex-shrink: 0;
}
.prev-plugin-tab {
  width: 16px; height: 4px;
  border-radius: 1px;
  background: rgba(255,255,255,.12);
}
.prev-plugin-tab--active {
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  box-shadow: 0 1px 4px var(--pglow2);
}
.prev-plugin-hero {
  height: 36px;
  background: linear-gradient(135deg, rgba(0,212,255,.12) 0%, rgba(123,47,255,.15) 50%, rgba(5,5,15,.9) 100%);
  position: relative;
}
.prev-plugin-hero::after {
  content: '';
  position: absolute;
  bottom: 4px; left: 6px;
  width: 40px; height: 5px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--pl), var(--pl2, var(--pl)));
  opacity: .7;
}
.prev-plugin-row {
  display: flex;
  gap: 3px;
  padding: 4px 6px;
  flex: 1;
  align-items: flex-start;
}
.prev-plugin-tile {
  flex: 1;
  aspect-ratio: 16/9;
  border-radius: 2px;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.04);
  border-bottom: 1px solid var(--pl);
}

.ts-card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ts-card-name { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.ts-card-active-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--pl-light);
  box-shadow: 0 0 6px var(--pglow);
}
.ts-card-desc { font-size: var(--fs-sm, 12px); color: var(--muted); }

/* Skin grid */
.ts-skin-row-label {
  font-size: var(--fs-xs, 10px);
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 8px;
}
.ts-skin-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.ts-skin-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: transform var(--transition);
}
.ts-skin-item:hover { transform: translateY(-2px); }
.ts-skin-swatch {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid transparent;
  transition: all var(--transition);
}
.ts-skin-item.active .ts-skin-swatch {
  border-color: var(--text);
  box-shadow: 0 0 0 2px var(--pl), 0 0 12px var(--pglow);
  transform: scale(1.1);
}
.ts-skin-name { font-size: 11px; color: var(--muted); font-weight: 600; }
.ts-skin-item.active .ts-skin-name { color: var(--text); }

/* Options - the row itself lives in ThemeOptionRow.vue */
.ts-option-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Theme title row with reset */
.ts-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3, 12px);
}
.ts-reset-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.06);
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
  margin-top: 2px;
}
.ts-reset-btn:hover {
  border-color: var(--pl);
  color: var(--pl-light);
  background: var(--pl-dim);
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .ts-theme-cards { gap: 10px; }
  .ts-theme-card { min-width: 140px; padding: var(--space-2, 8px); }
  .ts-card-preview { height: 65px; }
  .ts-card-name { font-size: var(--fs-sm, 12px); }
  .ts-card-desc { font-size: var(--fs-xs, 10px); }
}
</style>
