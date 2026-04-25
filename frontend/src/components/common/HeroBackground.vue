<template>
  <!--
    Shared hero background used by every detail page (GOG/Games/Emulation).
    Responsible for:
      - blurred cover art with saturate/brightness baked in
      - Ken Burns / Drift / Pulse animations (speed via --hero-anim-speed)
      - dark vignette fading bottom+left+top into var(--bg) for seamless
        transition into body content

    Blur intensity comes from --gd-hero-blur (user setting).  Animation
    style/enabled state comes from the theme store through the parent.
  -->
  <div class="gd-hero-bg" :class="animClass" :style="bgStyle" />
  <div v-if="showVignette" class="gd-hero-vignette" />
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  /** Full URL or local /resources path to the hero/background image. */
  src: string | null | undefined
  /** One of 'kenburns' | 'drift' | 'pulse' — passed from theme store. */
  animStyle?: string | null
  /** Whether animations are enabled (falsy = static). */
  animEnabled?: boolean
  /** Render the bottom/left/top dark vignette (default: yes). */
  showVignette?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  animStyle: 'kenburns',
  animEnabled: true,
  showVignette: true,
})

const bgStyle = computed(() => (
  props.src ? { backgroundImage: `url("${props.src}")` } : {}
))

const animClass = computed(() => (
  props.animEnabled && props.animStyle ? `gd-hero-bg--${props.animStyle}` : ''
))
</script>

<style scoped>
.gd-hero-bg {
  position: absolute; inset: -20px;
  background-size: cover; background-position: center 20%;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(120%) brightness(.48);
  transform-origin: center center; transform: scale(1.06);
  z-index: 0; will-change: transform;
}

/* Ken Burns - documentary zoom + gentle pan */
@keyframes gd-kenburns {
  0%   { transform: scale(1.06) translate(0%,    0%   ); }
  20%  { transform: scale(1.12) translate(-2.5%, 1%   ); }
  45%  { transform: scale(1.09) translate( 1.5%, -1.5%); }
  70%  { transform: scale(1.14) translate(-1%,   2%   ); }
  100% { transform: scale(1.06) translate(0%,    0%   ); }
}

/* Drift - slow lateral pan with slight zoom */
@keyframes gd-drift {
  0%   { transform: scale(1.1) translateX(0%);  }
  50%  { transform: scale(1.1) translateX(-5%); }
  100% { transform: scale(1.1) translateX(0%);  }
}

/* Pulse - smooth breathing zoom */
@keyframes gd-pulse {
  0%   { transform: scale(1.04); }
  50%  { transform: scale(1.11); }
  100% { transform: scale(1.04); }
}

.gd-hero-bg--kenburns {
  animation: gd-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.gd-hero-bg--drift {
  animation: gd-drift calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate;
}
.gd-hero-bg--pulse {
  animation: gd-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}

/* Respect global animations toggle */
:global([data-animations="false"]) .gd-hero-bg--kenburns,
:global([data-animations="false"]) .gd-hero-bg--drift,
:global([data-animations="false"]) .gd-hero-bg--pulse {
  animation: none;
}

.gd-hero-vignette {
  position: absolute; inset: 0; z-index: 1;
  background:
    linear-gradient(to top,   var(--bg) 0%, color-mix(in srgb, var(--bg) 45%, transparent) 42%, transparent 72%),
    linear-gradient(to right, color-mix(in srgb, var(--bg) 72%, transparent) 0%, transparent 55%),
    linear-gradient(to bottom,color-mix(in srgb, var(--bg) 45%, transparent) 0%, transparent 28%);
}
</style>
