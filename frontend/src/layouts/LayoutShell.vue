<template>
  <component :is="activeLayout" :key="themeStore.currentLayout" />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { getPluginLayout } from '@/themes/index'

const themeStore = useThemeStore()

const BUILTIN_LAYOUTS: Record<string, ReturnType<typeof defineAsyncComponent>> = {
  modern:  defineAsyncComponent(() => import('./ModernLayout.vue')),
  classic: defineAsyncComponent(() => import('./ClassicLayout.vue')),
}

const activeLayout = computed(() => {
  const id = themeStore.currentLayout
  // Built-in layout?
  if (BUILTIN_LAYOUTS[id]) return BUILTIN_LAYOUTS[id]
  // Plugin-compiled layout?
  const pluginLayout = getPluginLayout(id)
  if (pluginLayout) return pluginLayout
  // Fallback
  return BUILTIN_LAYOUTS.modern
})
</script>
