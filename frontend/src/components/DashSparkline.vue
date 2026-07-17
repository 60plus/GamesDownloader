<!--
  DashSparkline - a compact SVG bar chart for a per-day series ({date, count}).
  Bars grow from the baseline on mount (staggered), scale to the series max, and
  expose a per-bar tooltip. Colour comes from the theme (--accent), so it looks
  native in every theme. Falls back to a flat faint baseline when there is no
  activity yet. Respects prefers-reduced-motion.
-->
<template>
  <svg
    class="spark"
    :viewBox="`0 0 ${W} ${H}`"
    preserveAspectRatio="none"
    role="img"
    :aria-label="ariaLabel"
  >
    <line class="spark-base" :x1="0" :y1="H - 0.5" :x2="W" :y2="H - 0.5" />
    <rect
      v-for="(b, i) in bars"
      :key="i"
      class="spark-bar"
      :class="{ 'is-empty': max === 0 }"
      :x="b.x"
      :y="b.y"
      :width="b.w"
      :height="b.h"
      rx="1.5"
      :style="{ animationDelay: i * 28 + 'ms' }"
    >
      <title>{{ b.date }}: {{ b.count }}</title>
    </rect>
  </svg>
</template>

<script setup lang="ts">
import { computed } from "vue";

interface Sample { date: string; count: number; bytes?: number }

const props = defineProps<{ series: Sample[]; height?: number }>();

const W = 300;
const H = props.height ?? 44;

const max = computed(() => props.series.reduce((m, s) => Math.max(m, s.count || 0), 0));

const bars = computed(() => {
  const n = props.series.length || 1;
  const slot = W / n;
  const w = Math.max(2, slot * 0.6);
  const top = 3;                    // headroom so the tallest bar is not flush
  const usable = H - top - 1;
  const m = max.value;
  return props.series.map((s, i) => {
    const h = m > 0 ? Math.max(2, Math.round((s.count / m) * usable)) : 2;
    return {
      x: Math.round(i * slot + (slot - w) / 2),
      y: H - h,
      w: Math.round(w),
      h,
      count: s.count,
      date: s.date,
    };
  });
});

const ariaLabel = computed(() => {
  const total = props.series.reduce((a, s) => a + (s.count || 0), 0);
  return `Activity over ${props.series.length} days, ${total} total`;
});
</script>

<style scoped>
.spark { display: block; width: 100%; height: v-bind("H + 'px'"); overflow: visible; }
.spark-base { stroke: currentColor; opacity: 0.12; stroke-width: 1; }
.spark-bar {
  fill: var(--accent, #38d3db);
  transform-box: fill-box;
  transform-origin: bottom;
}
.spark-bar.is-empty { fill: currentColor; opacity: 0.18; }
@media (prefers-reduced-motion: no-preference) {
  .spark-bar { animation: sparkGrow 0.6s cubic-bezier(0.22, 1, 0.36, 1) backwards; }
}
@keyframes sparkGrow {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
}
</style>
