<template>
  <v-app>
    <router-view />
    <GdDialog />
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { registerTheme } from '@/themes/index'
import GdDialog from '@/components/GdDialog.vue'

const themeStore = useThemeStore()
const authStore  = useAuthStore()

// ── Plugin CSS injection (async, no flash) ──────────────────────────────────
const pluginCSS = document.createElement('link')
pluginCSS.rel = 'stylesheet'
pluginCSS.href = '/api/plugins/frontend/css'
pluginCSS.id = 'gd3-plugin-css'
document.head.appendChild(pluginCSS)

// Fetch + register plugin themes (async, non-blocking)
fetch('/api/plugins/frontend/themes')
  .then(r => r.ok ? r.json() : [])
  .then((themes: any[]) => {
    themes.forEach(t => registerTheme(t))
    // Re-apply if user's saved theme was from a plugin
    const saved = localStorage.getItem('gd3_theme')
    if (saved && themes.some(t => t.id === saved)) {
      themeStore.applyToDOM()
    }
  })
  .catch(() => {})

// Load plugin JavaScript (async, non-blocking)
const pluginJS = document.createElement('script')
pluginJS.src = '/api/plugins/frontend/js'
pluginJS.id = 'gd3-plugin-js'
pluginJS.defer = true
document.head.appendChild(pluginJS)

// Load compiled plugin layout bundles (theme plugins with .vue files)
fetch('/plugin-layouts/manifest.json?_=' + Date.now())
  .then(r => r.ok ? r.json() : {})
  .then((manifest: Record<string, { js: string; css: string; compiledAt?: string }>) => {
    for (const [pluginId, info] of Object.entries(manifest)) {
      // Cache bust using compiledAt timestamp
      const bust = info.compiledAt ? '?v=' + new Date(info.compiledAt).getTime() : ''
      // Load compiled JS (registers layout component)
      const s = document.createElement('script')
      s.src = '/' + info.js + bust
      s.id = `gd3-plugin-layout-${pluginId}`
      document.head.appendChild(s)
      // Load compiled CSS (scoped styles from Vue SFC)
      if (info.css) {
        const link = document.createElement('link')
        link.rel = 'stylesheet'
        link.href = '/' + info.css + bust
        link.id = `gd3-plugin-layout-css-${pluginId}`
        document.head.appendChild(link)
      }
    }
  })
  .catch(() => {})

// Apply CSS variables synchronously before first render so that animations
// on the initial route (e.g. GamesHome) start with the correct speed/blur values.
themeStore.applyToDOM()

onMounted(async () => {
  // Restore user data (avatar, role, etc.) from token on page refresh
  if (authStore.token) {
    await authStore.fetchUser()
  }
})
</script>
