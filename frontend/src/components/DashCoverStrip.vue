<!--
  DashCoverStrip - a single non-scrolling row of cover tiles. It measures its own
  width (ResizeObserver) and renders only as many whole covers as fit, so there
  is never a horizontal scrollbar or a half-clipped tile. Used for "Recently
  added" and "Continue playing". Emits `select` with the item when clickable.
-->
<template>
  <div ref="root" class="dcs">
    <component
      :is="clickable ? 'button' : 'div'"
      v-for="it in visible"
      :key="it.key"
      class="dcs-tile"
      :class="{ 'dcs-tile--btn': clickable }"
      :title="it.title"
      @click="clickable && emit('select', it)"
    >
      <span class="dcs-cover" :style="{ aspectRatio: it.aspect || '92 / 122' }">
        <i class="mdi mdi-gamepad-variant-outline dcs-ph"></i>
        <img v-if="it.cover" :src="it.cover" alt="" @error="imgErr" />
        <span v-if="it.kind" class="dcs-kind">{{ it.kind }}</span>
        <span v-if="clickable && hover === 'play'" class="dcs-play"><i class="mdi mdi-play"></i></span>
      </span>
      <span class="dcs-name">{{ it.title }}</span>
      <span v-if="it.sub || it.rating != null" class="dcs-meta">
        <span v-if="it.sub" class="dcs-sub">{{ it.sub }}</span>
        <span v-if="it.rating != null" class="dcs-rating">★ {{ Number(it.rating).toFixed(1) }}</span>
      </span>
    </component>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";

interface StripItem { key: string | number; cover: string | null; title: string; sub?: string; kind?: string; aspect?: string; rating?: number | null; [k: string]: unknown }

// Every clickable tile lifts on hover; `hover` only decides whether a play
// triangle is laid over the art ("play", for the resume tiles in Continue
// playing) or not ("lift", for tiles that merely open the game).
const props = withDefaults(defineProps<{ items: StripItem[]; clickable?: boolean; hover?: "play" | "lift" }>(), { hover: "play" });
const hover = computed(() => props.hover);
const emit = defineEmits<{ (e: "select", item: StripItem): void }>();

const TILE = 92;
const GAP = 12;
const root = ref<HTMLElement | null>(null);
const width = ref(0);

const count = computed(() => {
  if (width.value <= 0) return props.items.length;
  return Math.max(1, Math.floor((width.value + GAP) / (TILE + GAP)));
});
const visible = computed(() => props.items.slice(0, count.value));

function imgErr(e: Event): void { (e.target as HTMLImageElement).style.display = "none"; }

let ro: ResizeObserver | null = null;
onMounted(() => {
  const measure = (): void => { if (root.value) width.value = root.value.clientWidth; };
  measure();
  if (typeof ResizeObserver !== "undefined" && root.value) {
    ro = new ResizeObserver(measure);
    ro.observe(root.value);
  }
});
onUnmounted(() => { ro?.disconnect(); });
</script>

<style scoped>
/* overflow stays visible and the padding absorbs the hover growth - the tile
   count is measured to fit, so nothing needs clipping, and `hidden` would cut
   the lifted cover and its glow off at the strip's edge. */
.dcs { display: flex; gap: 12px; flex-wrap: nowrap; justify-content: center; align-items: flex-start; padding: 5px 4px 9px; }
.dcs-tile { flex: 1 1 0; min-width: 92px; max-width: 150px; background: transparent; border: 0; padding: 0; text-align: left; color: var(--text, #eee); display: flex; flex-direction: column; gap: 4px; }
.dcs-tile--btn { cursor: pointer; }
/* aspect-ratio is set inline per item (matches the ROM's cover aspect, like the
   emulation library) so landscape box art is not cropped to portrait. */
.dcs-cover { position: relative; width: 100%; border-radius: 8px; overflow: hidden; background: color-mix(in srgb, var(--text, #888) 10%, transparent); border: 1px solid rgba(0,0,0,0.3); box-shadow: 0 2px 8px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; transition: transform 0.3s ease, box-shadow 0.2s ease, border-color 0.2s ease; }
.dcs-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.dcs-ph { font-size: 40px; opacity: 0.3; }
.dcs-kind { position: absolute; top: 5px; left: 5px; font-size: 8.5px; font-weight: 700; letter-spacing: 0.4px; padding: 1px 5px; border-radius: 4px; background: rgba(0,0,0,0.6); color: #fff; }
.dcs-play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.15s ease; font-size: 30px; color: #fff; }
.dcs-tile--btn:hover .dcs-play { opacity: 1; }
/* The lift scales the FRAME, never the image inside it: frame and art grow as
   one, so the crop window is identical at rest and lifted. Scaling the img
   inside a fixed overflow:hidden frame just eats the edges of the art instead.
   Raised above its neighbours so the glow is not painted over by the next tile
   (paint order is DOM order otherwise). */
.dcs-tile--btn:hover { position: relative; z-index: 2; }
.dcs-tile--btn:hover .dcs-cover {
  transform: translateY(-2px) scale(1.04);
  border-color: var(--accent, #38d3db);
  box-shadow: 0 8px 24px rgba(0,0,0,0.55),
              0 0 18px color-mix(in srgb, var(--accent, #38d3db) 50%, transparent);
}
.dcs-name { font-size: 11.5px; font-weight: 500; line-height: 1.2; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
.dcs-meta { display: flex; align-items: center; gap: 6px; min-width: 0; }
.dcs-sub { font-size: 10.5px; opacity: 0.55; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dcs-rating { font-size: 10.5px; font-weight: 600; color: #fbbf24; flex: 0 0 auto; }
</style>
