<template>
  <div class="appearance-page">
    <theme-switcher />

    <!-- ── Card Effects ──────────────────────────────────────────────────── -->
    <div class="ap-section">
      <div class="ap-title">{{ t('appearance.card_effects') }}</div>
      <div class="ap-desc">{{ t('appearance.card_effects_desc') }}</div>

      <div class="ap-option-list">

        <!-- 3D Tilt -->
        <AppearanceOptionRow
          effect="cardTilt" type="toggle"
          label="appearance.tilt" hint="appearance.tilt_hint" hint-body="hint.tilt"
          :model-value="themeStore.cardTilt"
          @update:model-value="themeStore.toggleCardTilt()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M2 12L12 2l10 10M4 10v10h6v-6h4v6h6V10"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Specular Shine -->
        <AppearanceOptionRow
          effect="cardShine" type="toggle"
          label="appearance.shine" hint="appearance.shine_hint" hint-body="hint.shine"
          :model-value="themeStore.cardShine"
          @update:model-value="themeStore.toggleCardShine()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Zoom -->
        <AppearanceOptionRow
          effect="cardZoom" type="toggle"
          label="appearance.zoom" hint="appearance.zoom_hint" hint-body="hint.zoom"
          :model-value="themeStore.cardZoom"
          @update:model-value="themeStore.toggleCardZoom()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
              <line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Glow -->
        <AppearanceOptionRow
          effect="cardGlow" type="toggle"
          label="appearance.glow" hint="appearance.glow_hint" hint-body="hint.glow"
          :model-value="themeStore.cardGlow"
          @update:model-value="themeStore.toggleCardGlow()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="3"/>
              <path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke-opacity=".3"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Lift shadow -->
        <AppearanceOptionRow
          effect="cardLift" type="toggle"
          label="appearance.lift" hint="appearance.lift_hint" hint-body="hint.lift"
          :model-value="themeStore.cardLift"
          @update:model-value="themeStore.toggleCardLift()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="4" y="4" width="16" height="16" rx="2"/>
              <line x1="4" y1="20" x2="20" y2="20" stroke-opacity=".3" stroke-width="3"/>
            </svg>
          </template>
        </AppearanceOptionRow>

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
        <AppearanceOptionRow
          effect="classicHero" type="toggle"
          label="appearance.hero_classic" hint="appearance.hero_classic_hint" hint-body="hint.hero_classic"
          :model-value="themeStore.classicHero"
          @update:model-value="themeStore.toggleClassicHero()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="3" width="20" height="18" rx="2"/>
              <path d="M2 9h20" stroke-opacity=".4"/>
              <path d="M7 14h2m3 0h5" stroke-opacity=".6"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Hero blur -->
        <AppearanceOptionRow
          effect="heroBlur" type="range"
          label="appearance.hero_blur" hint="appearance.hero_blur_hint"
          :min="0" :max="40" :step="1" unit="px"
          :model-value="themeStore.heroBlur"
          @update:model-value="v => themeStore.setHeroBlur(Number(v))"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2" opacity=".4"/>
              <rect x="6" y="6" width="12" height="12" rx="1.5" opacity=".7"/>
              <rect x="9" y="9" width="6" height="6" rx="1"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Hero animation toggle -->
        <AppearanceOptionRow
          effect="heroAnim" type="toggle"
          label="appearance.hero_anim" hint="appearance.hero_anim_hint" hint-body="hint.hero_anim"
          :model-value="themeStore.heroAnim"
          @update:model-value="themeStore.toggleHeroAnim()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
              <polyline points="10 17 15 12 10 7"/>
              <line x1="15" y1="12" x2="3" y2="12"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Animation style -->
        <AppearanceOptionRow
          effect="heroAnimStyle" type="segmented"
          label="appearance.anim_style" hint="appearance.anim_style_hint"
          :options="heroAnimStyles"
          :disabled="!themeStore.heroAnim"
          :model-value="themeStore.heroAnimStyle"
          @update:model-value="v => themeStore.setHeroAnimStyle(String(v))"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Animation speed -->
        <AppearanceOptionRow
          effect="heroAnimStyle" type="segmented"
          label="appearance.anim_speed" hint="appearance.anim_speed_hint"
          :options="heroAnimSpeeds"
          :disabled="!themeStore.heroAnim"
          :model-value="themeStore.heroAnimSpeed"
          @update:model-value="v => themeStore.setHeroAnimSpeed(String(v))"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </template>
        </AppearanceOptionRow>

        <!-- Hero → body transition fade -->
        <AppearanceOptionRow
          effect="heroFade" type="range"
          label="appearance.hero_fade" hint="appearance.hero_fade_hint" hint-body="hint.hero_fade"
          :min="0" :max="200" :step="10" unit="px"
          :model-value="themeStore.heroFadeHeight"
          @update:model-value="v => themeStore.setHeroFadeHeight(Number(v))"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M2 20h20M2 12h20M2 4h20" stroke-opacity=".25"/>
              <path d="M2 20h20" stroke-opacity="1"/>
              <path d="M2 14h20" stroke-opacity=".6"/>
              <path d="M2 8h20" stroke-opacity=".2"/>
            </svg>
          </template>
        </AppearanceOptionRow>

      </div>

    </div>

    <!-- ── Emulation Library ─────────────────────────────────────────────── -->
    <div class="ap-section">
      <div class="ap-title">{{ t('appearance.emulation_library') }}</div>
      <div class="ap-desc">{{ t('appearance.emulation_library_desc') }}</div>

      <div class="ap-option-list">

        <!-- Platform Photo Header -->
        <AppearanceOptionRow
          effect="platformPhoto" type="toggle"
          label="appearance.platform_photo" hint="appearance.platform_photo_hint" hint-body="hint.platform_photo"
          :model-value="themeStore.platformPhotoHeader"
          @update:model-value="themeStore.togglePlatformPhotoHeader()"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="5" width="20" height="14" rx="2"/>
              <circle cx="8.5" cy="12" r="2.5"/>
              <path d="M14 10h5M14 14h3" stroke-opacity=".6"/>
            </svg>
          </template>
        </AppearanceOptionRow>

      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import AppearanceOptionRow from '@/components/common/AppearanceOptionRow.vue'
import { useThemeStore } from '@/stores/theme'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()
const { gdConfirm } = useDialog()

const themeStore = useThemeStore()

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

/* ── Option list - the row itself lives in AppearanceOptionRow.vue ───────── */
.ap-option-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
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

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .appearance-page { padding: var(--space-3, 12px); gap: var(--space-6, 24px); }
  .ap-title { font-size: var(--fs-md, 14px); }
}
</style>
