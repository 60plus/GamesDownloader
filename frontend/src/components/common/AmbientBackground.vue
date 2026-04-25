<template>
  <div
    v-if="theme.ambient"
    class="ambient-bg"
    :data-pattern="orbPattern"
  >
    <div class="ambient-orb orb-1" :class="{ 'orb--static': !orbMotion }" />
    <div v-if="orbCount >= 2" class="ambient-orb orb-2" :class="{ 'orb--static': !orbMotion }" />
    <div v-if="orbCount >= 3" class="ambient-orb orb-3" :class="{ 'orb--static': !orbMotion }" />
    <div v-if="theme.grid" class="grid-pattern" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'

const theme     = useThemeStore()
const orbMotion = computed(() => theme.animations && theme.orbMotion)
const orbCount  = computed(() => Number(theme.getThemeSettingValue('orbCount')  ?? 3))
const orbPattern = computed(() => String(theme.getThemeSettingValue('orbPattern') ?? 'organic'))
</script>

<style scoped>
/* ── Container ────────────────────────────────────────────────────────────── */
.ambient-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
  /* Isolate mix-blend-mode: screen on orbs so they don't lighten elements
     stacked above ambient-bg (hero backgrounds, covers, etc.).
     Without this orbs bleed through everything as a white/light overlay. */
  isolation: isolate;
}

/* ── Base orb (all share these) ───────────────────────────────────────────── */
.ambient-orb {
  position: absolute;
  border-radius: 50%;
  mix-blend-mode: screen;
  will-change: transform, opacity;
  transform: translateZ(0);
}

/* ── Static state ─────────────────────────────────────────────────────────── */
.orb--static {
  animation: none !important;
  transform: translateZ(0) !important;
}

/* ══ ORB DEFINITIONS ════════════════════════════════════════════════════════ */

/* Orb 1 - primary glow, top-left */
.orb-1 {
  width:  calc(70vmin * var(--orb-scale, 1));
  height: calc(70vmin * var(--orb-scale, 1));
  top:  calc(-20vmin * var(--orb-scale, 1));
  left: calc(-15vmin * var(--orb-scale, 1));
  background: radial-gradient(circle at 35% 40%, var(--pglow) 0%, transparent 68%);
  filter: blur(clamp(40px, 7vmin, 110px));
  opacity: calc(0.55 * var(--orb-opacity-mult, 1));
  animation-name: orbFloat1;
  animation-duration: calc(28s / var(--orb-speed-mult, 1));
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
}

/* Orb 2 - same skin colour (pglow), bottom-right, different angle */
.orb-2 {
  width:  calc(56vmin * var(--orb-scale, 1));
  height: calc(56vmin * var(--orb-scale, 1));
  bottom: calc(-18vmin * var(--orb-scale, 1));
  right:  calc(-12vmin * var(--orb-scale, 1));
  background: radial-gradient(circle at 65% 60%, var(--pglow) 0%, transparent 65%);
  filter: blur(clamp(35px, 6vmin, 90px));
  opacity: calc(0.40 * var(--orb-opacity-mult, 1));
  animation-name: orbFloat2;
  animation-duration: calc(34s / var(--orb-speed-mult, 1));
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
  animation-delay: calc(-14s / var(--orb-speed-mult, 1));
}

/* Orb 3 - lighter skin accent (pl-light), center-right */
.orb-3 {
  width:  calc(42vmin * var(--orb-scale, 1));
  height: calc(42vmin * var(--orb-scale, 1));
  top:  38%;
  left: 48%;
  background: radial-gradient(circle at 50% 50%, var(--pglow2) 0%, transparent 70%);
  filter: blur(clamp(50px, 8vmin, 130px));
  opacity: calc(0.28 * var(--orb-opacity-mult, 1));
  animation-name: orbFloat3;
  animation-duration: calc(44s / var(--orb-speed-mult, 1));
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
  animation-delay: calc(-22s / var(--orb-speed-mult, 1));
}

/* ══ ORGANIC PATTERN (default) - irregular multi-dir wandering ══════════════ */
@keyframes orbFloat1 {
  0%,100% { transform: translate(0%,0%) scale(1.00) translateZ(0); }
  15%     { transform: translate(calc( 5%*var(--orb-travel,1)),calc(-10%*var(--orb-travel,1))) scale(1.05) translateZ(0); }
  30%     { transform: translate(calc(13%*var(--orb-travel,1)),calc(  3%*var(--orb-travel,1))) scale(1.02) translateZ(0); }
  48%     { transform: translate(calc( 9%*var(--orb-travel,1)),calc( 13%*var(--orb-travel,1))) scale(1.07) translateZ(0); }
  65%     { transform: translate(calc(-7%*var(--orb-travel,1)),calc(  9%*var(--orb-travel,1))) scale(1.03) translateZ(0); }
  80%     { transform: translate(calc(-12%*var(--orb-travel,1)),calc(-6%*var(--orb-travel,1))) scale(1.05) translateZ(0); }
}
@keyframes orbFloat2 {
  0%,100% { transform: translate(0%,0%) scale(1.00) translateZ(0); }
  18%     { transform: translate(calc(-7%*var(--orb-travel,1)),calc( 10%*var(--orb-travel,1))) scale(1.05) translateZ(0); }
  35%     { transform: translate(calc(-12%*var(--orb-travel,1)),calc(-5%*var(--orb-travel,1))) scale(1.03) translateZ(0); }
  55%     { transform: translate(calc( 5%*var(--orb-travel,1)),calc(-13%*var(--orb-travel,1))) scale(1.08) translateZ(0); }
  72%     { transform: translate(calc(11%*var(--orb-travel,1)),calc(  4%*var(--orb-travel,1))) scale(1.04) translateZ(0); }
  88%     { transform: translate(calc( 4%*var(--orb-travel,1)),calc( 11%*var(--orb-travel,1))) scale(1.02) translateZ(0); }
}
@keyframes orbFloat3 {
  0%,100% { transform: translate(0%,0%) scale(1.00) translateZ(0); }
  25%     { transform: translate(calc(-9%*var(--orb-travel,1)),calc( -7%*var(--orb-travel,1))) scale(1.09) translateZ(0); }
  50%     { transform: translate(calc( 8%*var(--orb-travel,1)),calc(-12%*var(--orb-travel,1))) scale(1.05) translateZ(0); }
  75%     { transform: translate(calc(12%*var(--orb-travel,1)),calc(  7%*var(--orb-travel,1))) scale(1.07) translateZ(0); }
}

/* ══ DRIFT PATTERN - slow lazy horizontal sweep, dreamlike ══════════════════ */
.ambient-bg[data-pattern="drift"] .orb-1,
.ambient-bg[data-pattern="drift"] .orb-2,
.ambient-bg[data-pattern="drift"] .orb-3 { animation-timing-function: ease-in-out; }
.ambient-bg[data-pattern="drift"] .orb-1 { animation-name: orbDrift1; }
.ambient-bg[data-pattern="drift"] .orb-2 { animation-name: orbDrift2; }
.ambient-bg[data-pattern="drift"] .orb-3 { animation-name: orbDrift3; }

@keyframes orbDrift1 {
  0%    { transform: translate(calc(-22%*var(--orb-travel,1)),calc(  2%*var(--orb-travel,1))) translateZ(0); }
  50%   { transform: translate(calc( 22%*var(--orb-travel,1)),calc( -4%*var(--orb-travel,1))) translateZ(0); }
  100%  { transform: translate(calc(-22%*var(--orb-travel,1)),calc(  2%*var(--orb-travel,1))) translateZ(0); }
}
@keyframes orbDrift2 {
  0%    { transform: translate(calc( 20%*var(--orb-travel,1)),calc(  5%*var(--orb-travel,1))) translateZ(0); }
  50%   { transform: translate(calc(-20%*var(--orb-travel,1)),calc( -5%*var(--orb-travel,1))) translateZ(0); }
  100%  { transform: translate(calc( 20%*var(--orb-travel,1)),calc(  5%*var(--orb-travel,1))) translateZ(0); }
}
@keyframes orbDrift3 {
  0%    { transform: translate(calc(  5%*var(--orb-travel,1)),calc(-18%*var(--orb-travel,1))) translateZ(0); }
  50%   { transform: translate(calc( -5%*var(--orb-travel,1)),calc( 18%*var(--orb-travel,1))) translateZ(0); }
  100%  { transform: translate(calc(  5%*var(--orb-travel,1)),calc(-18%*var(--orb-travel,1))) translateZ(0); }
}

/* ══ PULSE PATTERN - breathes in place, dramatic scale+opacity, no travel ═══ */
.ambient-bg[data-pattern="pulse"] .orb-1,
.ambient-bg[data-pattern="pulse"] .orb-2,
.ambient-bg[data-pattern="pulse"] .orb-3 { animation-timing-function: ease-in-out; }
.ambient-bg[data-pattern="pulse"] .orb-1 { animation-name: orbPulse1; }
.ambient-bg[data-pattern="pulse"] .orb-2 { animation-name: orbPulse2; }
.ambient-bg[data-pattern="pulse"] .orb-3 { animation-name: orbPulse3; }

@keyframes orbPulse1 {
  0%,100% { transform: scale(0.60) translateZ(0); opacity: calc(0.20 * var(--orb-opacity-mult,1)); }
  50%     { transform: scale(1.55) translateZ(0); opacity: calc(0.85 * var(--orb-opacity-mult,1)); }
}
@keyframes orbPulse2 {
  0%,100% { transform: scale(1.50) translateZ(0); opacity: calc(0.70 * var(--orb-opacity-mult,1)); }
  50%     { transform: scale(0.55) translateZ(0); opacity: calc(0.12 * var(--orb-opacity-mult,1)); }
}
@keyframes orbPulse3 {
  0%,100% { transform: scale(0.65) translateZ(0); opacity: calc(0.10 * var(--orb-opacity-mult,1)); }
  40%     { transform: scale(1.70) translateZ(0); opacity: calc(0.75 * var(--orb-opacity-mult,1)); }
  70%     { transform: scale(1.20) translateZ(0); opacity: calc(0.45 * var(--orb-opacity-mult,1)); }
}

/* ══ VORTEX PATTERN - constant-speed circular orbit, clearly clockwise ══════ */
.ambient-bg[data-pattern="vortex"] .orb-1,
.ambient-bg[data-pattern="vortex"] .orb-2,
.ambient-bg[data-pattern="vortex"] .orb-3 { animation-timing-function: linear; }
.ambient-bg[data-pattern="vortex"] .orb-1 { animation-name: orbVortex1; }
.ambient-bg[data-pattern="vortex"] .orb-2 { animation-name: orbVortex2; }
.ambient-bg[data-pattern="vortex"] .orb-3 { animation-name: orbVortex3; }

@keyframes orbVortex1 {
  0%   { transform: translate(0%,                              calc(-20%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
  25%  { transform: translate(calc( 20%*var(--orb-travel,1)), 0%)                              scale(1.06) translateZ(0); }
  50%  { transform: translate(0%,                              calc( 20%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
  75%  { transform: translate(calc(-20%*var(--orb-travel,1)), 0%)                              scale(1.06) translateZ(0); }
  100% { transform: translate(0%,                              calc(-20%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
}
@keyframes orbVortex2 {
  0%   { transform: translate(0%,                              calc( 18%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
  25%  { transform: translate(calc(-18%*var(--orb-travel,1)), 0%)                              scale(1.05) translateZ(0); }
  50%  { transform: translate(0%,                              calc(-18%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
  75%  { transform: translate(calc( 18%*var(--orb-travel,1)), 0%)                              scale(1.05) translateZ(0); }
  100% { transform: translate(0%,                              calc( 18%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
}
@keyframes orbVortex3 {
  0%   { transform: translate(calc(-15%*var(--orb-travel,1)),calc(-15%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
  33%  { transform: translate(calc( 15%*var(--orb-travel,1)),calc(  8%*var(--orb-travel,1))) scale(1.07) translateZ(0); }
  66%  { transform: translate(calc( -8%*var(--orb-travel,1)),calc( 15%*var(--orb-travel,1))) scale(1.07) translateZ(0); }
  100% { transform: translate(calc(-15%*var(--orb-travel,1)),calc(-15%*var(--orb-travel,1))) scale(1.00) translateZ(0); }
}

/* ── Grid overlay ─────────────────────────────────────────────────────────── */
.grid-pattern {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
  background-size: 52px 52px;
  mask-image: radial-gradient(ellipse 90% 80% at 50% 40%, #000 40%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 90% 80% at 50% 40%, #000 40%, transparent 80%);
}
</style>
