<!--
  CollectionCover - the visual for a collection.

  * A custom `cover` (uploaded / scraped) is shown as a single image.
  * Otherwise the member covers (newest first) are rendered as a fanned hand of
    cards: the newest stands upright in front, older ones fan out behind to the
    left and right. Every card has its own frame (white border + dark ring +
    shadow) so the covers stay clearly separated instead of blending together.
    Works at any size - the component fills its parent box.
-->
<template>
  <div class="cc-wrap">
    <!-- Custom cover -->
    <img v-if="cover" :src="cover" :alt="name" class="cc-single" loading="lazy" />

    <!-- Fanned member covers -->
    <template v-else-if="fan.length">
      <div
        v-for="(src, i) in fan"
        :key="i"
        class="cc-card"
        :class="{ 'cc-card--front': i === 0 }"
        :style="cardStyle(i, fan.length)"
      >
        <img :src="src" :alt="name" loading="lazy" />
      </div>
    </template>

    <!-- Placeholder when there are no covers at all -->
    <div v-else class="cc-empty" :style="{ color: color || undefined }">
      <svg width="34%" height="34%" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3">
        <path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'

const props = withDefaults(defineProps<{
  cover?: string | null
  covers?: string[]
  name?: string
  color?: string | null
}>(), { cover: null, covers: () => [], name: '', color: null })

// Up to three cards: newest in front, two fanned behind.
const fan = computed(() => (props.covers || []).filter(Boolean).slice(0, 3))

// Fan angles by position. Index 0 is the newest (upright, front, on top);
// extra covers fan out behind it.
const ANGLES: Record<number, number[]> = {
  1: [0],
  2: [0, 15],
  3: [0, -14, 14],
}

function cardStyle(i: number, n: number): CSSProperties {
  const rot = (ANGLES[n] || ANGLES[3])[i] ?? 0
  return {
    transform: `rotate(${rot}deg)`,
    zIndex: String(10 - i),               // newest on top
    filter: i === 0 ? 'none' : 'brightness(.82)',
  }
}
</script>

<style scoped>
.cc-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  /* Keep the fanned cards in their own stacking context so a host hover overlay
     (z-index above this wrap) always renders on top of them. */
  isolation: isolate;
}
/* A custom cover keeps its own aspect ratio (covers scraped for a collection can
   be portrait, landscape or square) - contain shows the whole art with no
   side-cropping, centred in whatever slot the host gives us. */
.cc-single {
  width: 100%; height: 100%;
  object-fit: contain;
  display: block;
}

/* Each fanned cover is a framed "card" pivoting from its bottom centre. */
.cc-card {
  position: absolute;
  left: 50%;
  bottom: 7%;
  width: 56%;
  aspect-ratio: 3 / 4;               /* real cover ratio - no side-cropping */
  margin-left: -28%;                 /* centre horizontally (half of width) */
  transform-origin: 50% 100%;
  border-radius: 7px;
  overflow: hidden;
  background: var(--pl, #8b5cf6);
  /* Frame uses the active colour skin; the dark ring keeps overlapping cards
     separated regardless of their cover art. */
  border: 2.5px solid var(--pl, #8b5cf6);
  box-shadow: 0 0 0 1.5px rgba(0,0,0,.5), 0 6px 16px rgba(0,0,0,.55);
}
.cc-card--front {
  width: 64%;
  margin-left: -32%;
  box-shadow: 0 0 0 1.5px rgba(0,0,0,.55), 0 10px 22px rgba(0,0,0,.6);
}
.cc-card img { width: 100%; height: 100%; object-fit: cover; display: block; }

.cc-empty {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, currentColor 7%, transparent);
  color: var(--pl, #8b5cf6);
  opacity: .75;
}
</style>
