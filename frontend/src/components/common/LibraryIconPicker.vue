<!--
  Grid picker for the built-in library icons. Two-way binds the chosen
  "builtin:<name>" token; the selected tile is tinted with `color` so the admin
  previews exactly how the icon will look. Uploaded icons (a /resources URL in
  modelValue) leave no tile selected - re-uploading or picking a built-in
  replaces them.
-->
<template>
  <div class="lip">
    <button
      v-for="name in names"
      :key="name"
      type="button"
      class="lip-tile"
      :class="{ sel: modelValue === 'builtin:' + name }"
      @click="$emit('update:modelValue', 'builtin:' + name)"
      @mouseenter="$emit('hover', name)"
      @mouseleave="$emit('hover', null)"
    >
      <LibraryIcon
        :icon="'builtin:' + name"
        :color="modelValue === 'builtin:' + name ? (color || undefined) : undefined"
        :size="18"
      />
    </button>
  </div>
</template>

<script setup lang="ts">
import LibraryIcon from './LibraryIcon.vue'
import { LIBRARY_ICON_NAMES } from '@/lib/libraryIcons'

defineProps<{ modelValue: string | null; color?: string | null }>()
defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'hover', name: string | null): void
}>()

const names = LIBRARY_ICON_NAMES
</script>

<style scoped>
.lip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(34px, 1fr));
  gap: 6px;
}
.lip-tile {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs, 6px);
  background: rgba(255, 255, 255, .04);
  color: var(--muted);
  cursor: pointer;
  transition: all var(--transition);
}
.lip-tile:hover { color: var(--text); background: var(--glass-highlight); border-color: var(--pl); }
.lip-tile.sel {
  background: color-mix(in srgb, var(--pl) 16%, transparent);
  border-color: color-mix(in srgb, var(--pl) 55%, transparent);
}
</style>
