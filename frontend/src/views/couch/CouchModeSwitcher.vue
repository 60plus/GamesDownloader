<template>
  <component :is="activeCouchMode" />
</template>

<script setup lang="ts">
/**
 * CouchModeSwitcher - renders plugin couch mode if available for the
 * active theme, otherwise falls back to the default CouchMode.
 */
import { computed, defineAsyncComponent } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { getPluginCouchMode } from '@/themes/index'

const themeStore = useThemeStore()

const DefaultCouchMode = defineAsyncComponent(() => import('./CouchMode.vue'))

const activeCouchMode = computed(() => {
  const themeId = themeStore.themeId
  const pluginCouch = getPluginCouchMode(themeId)
  return pluginCouch ?? DefaultCouchMode
})
</script>
