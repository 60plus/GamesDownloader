<!--
  Renders a library's icon. Three cases:
   - "builtin:<name>"  -> inline SVG from the built-in set, tinted with `color`
   - "/resources/..." | "http..." | "/path"  -> uploaded/static image
   - null / unknown    -> the built-in "folder" glyph, tinted with `color`
  Used in the admin list, the appearance visibility list, and home collection cards.
-->
<template>
  <img
    v-if="imgSrc"
    :src="imgSrc"
    :width="size"
    :height="size"
    class="lib-ico-img"
    :alt="alt || ''"
    loading="lazy"
  />
  <svg
    v-else
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    :stroke="color || 'currentColor'"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    class="lib-ico-svg"
    v-html="markup"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LIBRARY_ICONS, isBuiltinIcon } from '@/lib/libraryIcons'

const props = withDefaults(defineProps<{
  icon: string | null | undefined
  color?: string | null
  size?: number
  alt?: string
}>(), { color: null, size: 24, alt: '' })

// An uploaded or static image (anything that is not a builtin: token).
const imgSrc = computed(() =>
  props.icon && !isBuiltinIcon(props.icon) ? props.icon : null,
)

// Built-in glyph markup (defaults to folder when unset/unknown).
const markup = computed(() => {
  const name = isBuiltinIcon(props.icon) ? (props.icon as string).slice(8) : 'folder'
  return LIBRARY_ICONS[name] ?? LIBRARY_ICONS.folder
})
</script>

<style scoped>
.lib-ico-img { object-fit: contain; border-radius: 6px; display: block; }
.lib-ico-svg { display: block; flex-shrink: 0; }
</style>
