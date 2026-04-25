<template>
  <div class="cw-root">
    <!-- Animated background stars for all themes -->
    <div class="cw-stars" />

    <div class="cw-inner">
      <div class="cw-logo">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <rect x="2" y="6" width="20" height="14" rx="3"/>
          <circle cx="8" cy="13" r="1.5" fill="currentColor" stroke="none"/>
          <circle cx="16" cy="13" r="1.5" fill="currentColor" stroke="none"/>
          <path d="M6 10h4M8 8v4M14 11h4" stroke-width="2"/>
          <path d="M8 6V4M16 6V4" stroke-width="1.5"/>
        </svg>
      </div>
      <h1 class="cw-title">{{ t('couch.title') }}</h1>
      <p class="cw-subtitle">{{ t('couch.choose_theme') }}</p>

      <div class="cw-themes">
        <!-- NOIR -->
        <button
          class="cw-theme-card cw-theme-card--noir"
          :class="{ selected: pick === 'noir' }"
          @click="pick = 'noir'"
        >
          <div class="cw-card-preview cw-preview--noir">
            <div class="cw-prev-bar" />
            <div class="cw-prev-list">
              <div class="cw-prev-item cw-prev-item--active" />
              <div class="cw-prev-item" />
              <div class="cw-prev-item" />
            </div>
            <div class="cw-prev-art cw-prev-art--noir" />
          </div>
          <div class="cw-card-label">
            <span class="cw-card-name">Noir</span>
            <span class="cw-card-desc">{{ t('couch.theme_noir_desc') }}</span>
          </div>
          <div class="cw-card-check">
            <svg v-if="pick === 'noir'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </button>

        <!-- AURA -->
        <button
          class="cw-theme-card cw-theme-card--aura"
          :class="{ selected: pick === 'aura' }"
          @click="pick = 'aura'"
        >
          <div class="cw-card-preview cw-preview--aura">
            <div class="cw-prev-bar" />
            <div class="cw-prev-list">
              <div class="cw-prev-item cw-prev-item--active" />
              <div class="cw-prev-item" />
              <div class="cw-prev-item" />
            </div>
            <div class="cw-prev-art cw-prev-art--aura" />
          </div>
          <div class="cw-card-label">
            <span class="cw-card-name">Aura</span>
            <span class="cw-card-desc">{{ t('couch.theme_aura_desc') }}</span>
          </div>
          <div class="cw-card-check">
            <svg v-if="pick === 'aura'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </button>

        <!-- SLICK -->
        <button
          class="cw-theme-card cw-theme-card--slick"
          :class="{ selected: pick === 'slick' }"
          @click="pick = 'slick'"
        >
          <div class="cw-card-preview cw-preview--slick">
            <div class="cw-prev-bar" />
            <div class="cw-prev-list">
              <div class="cw-prev-item cw-prev-item--active" />
              <div class="cw-prev-item" />
              <div class="cw-prev-item" />
            </div>
            <div class="cw-prev-art cw-prev-art--slick" />
          </div>
          <div class="cw-card-label">
            <span class="cw-card-name">Slick</span>
            <span class="cw-card-desc">{{ t('couch.theme_slick_desc') }}</span>
          </div>
          <div class="cw-card-check">
            <svg v-if="pick === 'slick'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </button>
      </div>

      <button class="cw-go" :disabled="!pick" @click="confirm">
        {{ t('couch.enter') }}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>

      <p class="cw-hint">{{ t('couch.theme_change_hint') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from '@/i18n'
import type { CouchTheme } from '@/composables/useCouchTheme'

const { t } = useI18n()

const emit = defineEmits<{ done: [theme: CouchTheme] }>()
const pick = ref<CouchTheme>('noir')

function confirm() {
  if (pick.value) emit('done', pick.value)
}
</script>

<style scoped>
.cw-root {
  position: fixed; inset: 0; background: #050508; z-index: 10;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}

/* Animated starfield */
.cw-stars {
  position: absolute; inset: 0; pointer-events: none;
  background-image:
    radial-gradient(1px 1px at 10% 20%, rgba(255,255,255,.6) 0, transparent 0),
    radial-gradient(1px 1px at 35% 55%, rgba(255,255,255,.4) 0, transparent 0),
    radial-gradient(1px 1px at 70% 15%, rgba(255,255,255,.5) 0, transparent 0),
    radial-gradient(1px 1px at 85% 70%, rgba(255,255,255,.3) 0, transparent 0),
    radial-gradient(1.5px 1.5px at 55% 40%, rgba(255,255,255,.5) 0, transparent 0),
    radial-gradient(1px 1px at 20% 80%, rgba(255,255,255,.4) 0, transparent 0),
    radial-gradient(1px 1px at 92% 30%, rgba(255,255,255,.6) 0, transparent 0);
  background-size: 400px 400px;
  animation: cw-stars 60s linear infinite;
}
@keyframes cw-stars { to { background-position: 400px 400px; } }

.cw-inner {
  position: relative; z-index: 1; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 0;
  padding: 40px 32px; max-width: 900px; width: 100%;
}

.cw-logo {
  color: rgba(255,255,255,.3); margin-bottom: 16px;
  animation: cw-pulse 3s ease-in-out infinite;
}
@keyframes cw-pulse { 0%,100% { opacity:.3 } 50% { opacity:.7 } }

.cw-title {
  font-size: 48px; font-weight: 800; color: #fff; margin: 0 0 8px;
  letter-spacing: -.02em;
  text-shadow: 0 0 60px rgba(255,255,255,.15);
}
.cw-subtitle {
  font-size: var(--fs-lg, 16px); color: rgba(255,255,255,.4); margin: 0 0 40px;
  letter-spacing: .1em; text-transform: uppercase;
}

/* Theme cards */
.cw-themes {
  display: flex; gap: var(--space-5, 20px); margin-bottom: 40px; width: 100%;
  justify-content: center;
}

.cw-theme-card {
  flex: 1; max-width: 240px; background: rgba(255,255,255,.04);
  border: 2px solid rgba(255,255,255,.08); border-radius: 16px;
  cursor: pointer; padding: 0 0 16px; overflow: hidden; transition: all .25s;
  display: flex; flex-direction: column; position: relative;
  text-align: left;
}
.cw-theme-card:hover { transform: translateY(-4px); border-color: rgba(255,255,255,.2); }
.cw-theme-card.selected { transform: translateY(-6px); }
.cw-theme-card--noir.selected  { border-color: #c9a84c; box-shadow: 0 0 40px rgba(201,168,76,.2); }
.cw-theme-card--aura.selected  { border-color: #7c3aed; box-shadow: 0 0 40px rgba(124,58,237,.3); }
.cw-theme-card--slick.selected { border-color: #cc0000; box-shadow: 0 0 40px rgba(204,0,0,.25); }

/* Theme preview thumbnails */
.cw-card-preview {
  width: 100%; aspect-ratio: 16/9; position: relative; overflow: hidden; margin-bottom: 14px;
  display: flex; gap: var(--space-2, 8px); padding: var(--space-3, 12px);
}
.cw-preview--noir  { background: linear-gradient(135deg, #0a0a0f 0%, #1a1510 100%); }
.cw-preview--aura  { background: linear-gradient(135deg, #0f0f1a 0%, #1a1040 100%); }
.cw-preview--slick { background: linear-gradient(135deg, #000 0%, #0a000a 100%); }

.cw-prev-bar {
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.cw-preview--noir  .cw-prev-bar { background: #c9a84c; }
.cw-preview--aura  .cw-prev-bar { background: linear-gradient(90deg, #7c3aed, #06b6d4); }
.cw-preview--slick .cw-prev-bar { background: #cc0000; }

.cw-prev-list { display: flex; flex-direction: column; gap: 5px; padding-top: 8px; flex: 1; }
.cw-prev-item { height: 8px; border-radius: 2px; background: rgba(255,255,255,.12); }
.cw-prev-item--active { background: rgba(255,255,255,.35); }

.cw-prev-art { flex: 1; border-radius: 6px; }
.cw-prev-art--noir  { background: linear-gradient(135deg, #2a1f0e, #4a3520); border: 1px solid rgba(201,168,76,.3); }
.cw-prev-art--aura  { background: linear-gradient(135deg, #1a0a30, #0a1540); border: 1px solid rgba(124,58,237,.3); }
.cw-prev-art--slick { background: linear-gradient(135deg, #1a0000, #0a0010); border: 1px solid rgba(204,0,0,.3); }

.cw-card-label { padding: 0 16px; display: flex; flex-direction: column; gap: 3px; flex: 1; }
.cw-card-name { font-size: var(--fs-lg, 16px); font-weight: 700; color: #fff; }
.cw-card-desc { font-size: 11px; color: rgba(255,255,255,.4); }

.cw-card-check {
  position: absolute; top: 12px; right: 12px;
  width: 24px; height: 24px; border-radius: 50%;
  background: rgba(255,255,255,.05); display: flex; align-items: center; justify-content: center;
}
.cw-theme-card--noir.selected  .cw-card-check { background: #c9a84c; color: #000; }
.cw-theme-card--aura.selected  .cw-card-check { background: #7c3aed; color: #fff; }
.cw-theme-card--slick.selected .cw-card-check { background: #cc0000; color: #fff; }

/* Go button */
.cw-go {
  display: flex; align-items: center; gap: 10px;
  background: linear-gradient(135deg, #7c3aed, #5b21b6);
  color: #fff; border: none; border-radius: var(--radius, 12px);
  padding: 14px 32px; font-size: var(--fs-lg, 16px); font-weight: 700; cursor: pointer;
  transition: all .2s; letter-spacing: .02em;
  box-shadow: 0 4px 24px rgba(124,58,237,.4);
}
.cw-go:hover:not(:disabled) { transform: scale(1.04); box-shadow: 0 8px 32px rgba(124,58,237,.5); }
.cw-go:disabled { opacity: .4; cursor: not-allowed; }

.cw-hint { margin-top: 16px; font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.25); letter-spacing: .05em; }
</style>
