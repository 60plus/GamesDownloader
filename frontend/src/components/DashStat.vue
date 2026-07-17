<!--
  DashStat - a single stat value that counts up from 0 to its target on mount
  (and re-animates when the target changes). `format` turns the animated raw
  number into the displayed string (bytes, speed, etc.); without it the number
  is shown with locale grouping. Honours prefers-reduced-motion by jumping
  straight to the final value.
-->
<template>
  <span class="dash-num">{{ display }}</span>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";

const props = defineProps<{
  value: number;
  format?: (n: number) => string;
  duration?: number;
}>();

const display = ref("");
let raf = 0;
let cur = 0;

function fmt(n: number): string {
  return props.format ? props.format(n) : Math.round(n).toLocaleString();
}

function reducedMotion(): boolean {
  return typeof window !== "undefined"
    && !!window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function animate(to: number): void {
  cancelAnimationFrame(raf);
  const from = cur;
  if (reducedMotion() || from === to) {
    cur = to;
    display.value = fmt(to);
    return;
  }
  const dur = props.duration ?? 900;
  const t0 = performance.now();
  const step = (now: number): void => {
    const p = Math.min(1, (now - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
    cur = from + (to - from) * eased;
    display.value = fmt(cur);
    if (p < 1) {
      raf = requestAnimationFrame(step);
    } else {
      cur = to;
      display.value = fmt(to);
    }
  };
  raf = requestAnimationFrame(step);
}

watch(() => props.value, (v) => animate(v || 0), { immediate: true });
onUnmounted(() => cancelAnimationFrame(raf));
</script>
