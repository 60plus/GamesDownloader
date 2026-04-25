<template>
  <div class="appearance-page">
    <theme-switcher />

    <!-- ── Card Effects ──────────────────────────────────────────────────── -->
    <div class="ap-section">
      <div class="ap-title">{{ t('appearance.card_effects') }}</div>
      <div class="ap-desc">{{ t('appearance.card_effects_desc') }}</div>

      <div class="ap-option-list">

        <!-- 3D Tilt -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.tilt'), t('hint.tilt'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M2 12L12 2l10 10M4 10v10h6v-6h4v6h6V10"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.tilt') }}</span>
              <span class="ap-option-hint">{{ t('appearance.tilt_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.cardTilt }" @click="themeStore.toggleCardTilt()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Specular Shine -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.shine'), t('hint.shine'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="4"/>
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.shine') }}</span>
              <span class="ap-option-hint">{{ t('appearance.shine_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.cardShine }" @click="themeStore.toggleCardShine()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Zoom -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.zoom'), t('hint.zoom'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
                <line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.zoom') }}</span>
              <span class="ap-option-hint">{{ t('appearance.zoom_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.cardZoom }" @click="themeStore.toggleCardZoom()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Glow -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.glow'), t('hint.glow'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="3"/>
                <path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke-opacity=".3"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.glow') }}</span>
              <span class="ap-option-hint">{{ t('appearance.glow_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.cardGlow }" @click="themeStore.toggleCardGlow()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Lift shadow -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.lift'), t('hint.lift'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="4" y="4" width="16" height="16" rx="2"/>
                <line x1="4" y1="20" x2="20" y2="20" stroke-opacity=".3" stroke-width="3"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.lift') }}</span>
              <span class="ap-option-hint">{{ t('appearance.lift_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.cardLift }" @click="themeStore.toggleCardLift()">
            <div class="ap-pill-knob" />
          </div>
        </label>

      </div>

      <!-- Quick-reset -->
      <div class="ap-reset-row">
        <button class="ap-reset-btn" @click="resetCardEffects">{{ t('appearance.reset_effects', 'Reset card effects to defaults') }}</button>
        <span class="ap-active-count">{{ activeCount }} / 5 {{ t('appearance.effects_active', 'effects active') }}</span>
      </div>

    </div>

    <!-- ── Game Page Settings ────────────────────────────────────────────── -->
    <div class="ap-section">
      <div class="ap-title">{{ t('appearance.game_detail') }}</div>
      <div class="ap-desc">{{ t('appearance.game_detail_desc') }}</div>

      <div class="ap-option-list">

        <!-- Hero Background toggle (Classic layout) -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.hero_classic'), t('hint.hero_classic'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="3" width="20" height="18" rx="2"/>
                <path d="M2 9h20" stroke-opacity=".4"/>
                <path d="M7 14h2m3 0h5" stroke-opacity=".6"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.hero_classic') }}</span>
              <span class="ap-option-hint">{{ t('appearance.hero_classic_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.classicHero }" @click="themeStore.toggleClassicHero()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Hero blur -->
        <div class="ap-option ap-option--range">
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" opacity=".4"/>
                <rect x="6" y="6" width="12" height="12" rx="1.5" opacity=".7"/>
                <rect x="9" y="9" width="6" height="6" rx="1"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.hero_blur') }}</span>
              <span class="ap-option-hint">{{ t('appearance.hero_blur_hint') }}</span>
            </div>
          </div>
          <div class="ap-range-wrap">
            <input
              type="range" min="0" max="40" step="1"
              :value="themeStore.heroBlur"
              @input="themeStore.setHeroBlur(Number(($event.target as HTMLInputElement).value))"
              class="ap-range"
            />
            <span class="ap-range-val">{{ themeStore.heroBlur }}px</span>
          </div>
        </div>

        <!-- Hero animation toggle -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.hero_anim'), t('hint.hero_anim'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                <polyline points="10 17 15 12 10 7"/>
                <line x1="15" y1="12" x2="3" y2="12"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.hero_anim') }}</span>
              <span class="ap-option-hint">{{ t('appearance.hero_anim_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.heroAnim }" @click="themeStore.toggleHeroAnim()">
            <div class="ap-pill-knob" />
          </div>
        </label>

        <!-- Animation style -->
        <div class="ap-option ap-option--select" :class="{ 'ap-option--disabled': !themeStore.heroAnim }">
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.anim_style') }}</span>
              <span class="ap-option-hint">{{ t('appearance.anim_style_hint') }}</span>
            </div>
          </div>
          <div class="ap-segmented">
            <button v-for="s in heroAnimStyles" :key="s.id"
              class="ap-seg-btn"
              :class="{ active: themeStore.heroAnimStyle === s.id }"
              :disabled="!themeStore.heroAnim"
              @click="themeStore.setHeroAnimStyle(s.id)"
            >{{ s.label }}</button>
          </div>
        </div>

        <!-- Animation speed -->
        <div class="ap-option ap-option--select" :class="{ 'ap-option--disabled': !themeStore.heroAnim }">
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.anim_speed') }}</span>
              <span class="ap-option-hint">{{ t('appearance.anim_speed_hint') }}</span>
            </div>
          </div>
          <div class="ap-segmented">
            <button v-for="s in heroAnimSpeeds" :key="s.id"
              class="ap-seg-btn"
              :class="{ active: themeStore.heroAnimSpeed === s.id }"
              :disabled="!themeStore.heroAnim"
              @click="themeStore.setHeroAnimSpeed(s.id)"
            >{{ s.label }}</button>
          </div>
        </div>

        <!-- Hero → body transition fade -->
        <div class="ap-option ap-option--range"
          @mouseenter="setHint(t('appearance.hero_fade'), t('hint.hero_fade'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M2 20h20M2 12h20M2 4h20" stroke-opacity=".25"/>
                <path d="M2 20h20" stroke-opacity="1"/>
                <path d="M2 14h20" stroke-opacity=".6"/>
                <path d="M2 8h20" stroke-opacity=".2"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.hero_fade') }}</span>
              <span class="ap-option-hint">{{ t('appearance.hero_fade_hint') }}</span>
            </div>
          </div>
          <div class="ap-range-wrap">
            <input
              type="range" min="0" max="200" step="10"
              :value="themeStore.heroFadeHeight"
              @input="themeStore.setHeroFadeHeight(Number(($event.target as HTMLInputElement).value))"
              class="ap-range"
            />
            <span class="ap-range-val">{{ themeStore.heroFadeHeight }}px</span>
          </div>
        </div>

      </div>

    </div>

    <!-- ── Emulation Library ─────────────────────────────────────────────── -->
    <div class="ap-section">
      <div class="ap-title">{{ t('appearance.emulation_library') }}</div>
      <div class="ap-desc">{{ t('appearance.emulation_library_desc') }}</div>

      <div class="ap-option-list">

        <!-- Platform Photo Header -->
        <label class="ap-option"
          @mouseenter="setHint(t('appearance.platform_photo'), t('hint.platform_photo'))"
          @mouseleave="clearHint()"
        >
          <div class="ap-option-left">
            <div class="ap-option-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="5" width="20" height="14" rx="2"/>
                <circle cx="8.5" cy="12" r="2.5"/>
                <path d="M14 10h5M14 14h3" stroke-opacity=".6"/>
              </svg>
            </div>
            <div class="ap-option-info">
              <span class="ap-option-name">{{ t('appearance.platform_photo') }}</span>
              <span class="ap-option-hint">{{ t('appearance.platform_photo_hint') }}</span>
            </div>
          </div>
          <div class="ap-pill" :class="{ on: themeStore.platformPhotoHeader }" @click="themeStore.togglePlatformPhotoHeader()">
            <div class="ap-pill-knob" />
          </div>
        </label>

      </div>
    </div>


  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()
const { gdConfirm } = useDialog()

const themeStore = useThemeStore()
const { setHint, clearHint } = useSettingsHint()


const heroAnimStyles = [
  { id: 'kenburns', label: 'Ken Burns' },
  { id: 'drift',    label: 'Drift'     },
  { id: 'pulse',    label: 'Pulse'     },
]
const heroAnimSpeeds = [
  { id: 'slow',   label: 'Slow'   },
  { id: 'normal', label: 'Normal' },
  { id: 'fast',   label: 'Fast'   },
]

const activeCount = computed(() => [
  themeStore.cardTilt,
  themeStore.cardShine,
  themeStore.cardZoom,
  themeStore.cardGlow,
  themeStore.cardLift,
].filter(Boolean).length)

async function resetCardEffects() {
  const ok = await gdConfirm(t('appearance.reset_confirm', 'Reset all card effects to defaults?'), { title: t('appearance.card_effects', 'Card Effects'), confirmText: t('common.reset', 'Reset') })
  if (!ok) return
  if (!themeStore.cardTilt)  themeStore.toggleCardTilt()
  if (!themeStore.cardShine) themeStore.toggleCardShine()
  if (!themeStore.cardZoom)  themeStore.toggleCardZoom()
  if (!themeStore.cardGlow)  themeStore.toggleCardGlow()
  if (!themeStore.cardLift)  themeStore.toggleCardLift()
}
</script>

<style scoped>
.appearance-page {
  padding: var(--space-6, 24px);
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: 36px;
}

/* ── Section wrapper ─────────────────────────────────────────────────────── */
.ap-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
}

.ap-title {
  font-size: var(--fs-lg, 16px);
  font-weight: 700;
  color: var(--text);
}

.ap-desc {
  font-size: 13px;
  color: var(--muted);
}

/* ── Option list ─────────────────────────────────────────────────────────── */
.ap-option-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ap-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4, 16px);
  padding: 13px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  transition: background var(--transition);
  user-select: none;
}
.ap-option:hover { background: var(--glass-highlight); }

.ap-option-left {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  flex: 1;
}

.ap-option-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  flex-shrink: 0;
  transition: background var(--transition), color var(--transition), border-color var(--transition);
}
.ap-option:hover .ap-option-icon {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}

.ap-option-info { display: flex; flex-direction: column; gap: 2px; }
.ap-option-name { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); }
.ap-option-hint { font-size: var(--fs-sm, 12px); color: var(--muted); }

/* ── Toggle pill ─────────────────────────────────────────────────────────── */
.ap-pill {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: rgba(255,255,255,.1);
  border: 1px solid var(--glass-border);
  flex-shrink: 0;
  position: relative;
  cursor: pointer;
  transition: all var(--transition);
}
.ap-pill.on {
  background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1));
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  box-shadow: 0 0 10px var(--pglow2);
}
.ap-pill-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255,255,255,.4);
  transition: all var(--transition);
}
.ap-pill.on .ap-pill-knob {
  left: 21px;
  background: #fff;
}

/* ── Reset row ───────────────────────────────────────────────────────────── */
.ap-reset-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2, 8px);
}

.ap-reset-btn {
  padding: 5px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.05);
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.ap-reset-btn:hover {
  border-color: var(--pl);
  color: var(--pl-light);
  background: var(--pl-dim);
}

.ap-active-count {
  font-size: var(--fs-sm, 12px);
  color: var(--muted);
}

/* ── Range option ─────────────────────────────────────────────────────────── */
.ap-option--range {
  cursor: default;
  align-items: center;
}
.ap-option--range:hover .ap-option-icon {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}
.ap-range-wrap {
  display: flex; align-items: center; gap: 10px;
  flex-shrink: 0;
}
.ap-range {
  width: 140px;
  accent-color: var(--pl);
  cursor: pointer;
}
.ap-range-val {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--pl-light);
  min-width: 34px; text-align: right;
}

/* ── Select / segmented control ───────────────────────────────────────────── */
.ap-option--select { cursor: default; }
.ap-option--disabled { opacity: .45; pointer-events: none; }
.ap-segmented {
  display: flex;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}
.ap-seg-btn {
  padding: 5px 12px;
  background: color-mix(in srgb, var(--pl) 12%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
  white-space: nowrap;
}
.ap-seg-btn + .ap-seg-btn { border-left: 1px solid var(--glass-border); }
.ap-seg-btn:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.ap-seg-btn.active { background: var(--pl-dim); color: var(--pl-light); }
.ap-seg-btn:disabled { cursor: not-allowed; }

.ap-restart-notice {
  font-size: var(--fs-sm, 12px); color: #fbbf24; padding: 8px 12px; margin-top: 4px;
  background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.2);
  border-radius: var(--radius-sm); display: flex; align-items: center; gap: 6px;
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .appearance-page { padding: var(--space-3, 12px); gap: var(--space-6, 24px); }
  .ap-option { gap: 10px; padding: 10px 10px; }
  .ap-option-icon { width: 26px; height: 26px; border-radius: 6px; }
  .ap-option-icon svg { width: 13px; height: 13px; }
  .ap-option-name { font-size: var(--fs-sm, 12px); }
  .ap-option-hint { font-size: var(--fs-xs, 10px); }
  .ap-option-left { gap: var(--space-2, 8px); }
  .ap-range { width: 100px; }
  .ap-range-val { font-size: 11px; min-width: 32px; }
  .ap-seg-btn { padding: 5px 8px; font-size: var(--fs-xs, 10px); }
  .ap-title { font-size: var(--fs-md, 14px); }
}
</style>
