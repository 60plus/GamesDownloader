import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  // Cache key for the translation files, which are served from public/ rather
  // than bundled. Changes every build, so a release cannot be read with a
  // previous release's strings, and stays put in between.
  define: {
    __I18N_BUILD__: JSON.stringify(Date.now().toString(36)),
  },
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/resources": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/socket.io": {
        target: "http://localhost:8080",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          "vue-vendor":   ["vue", "vue-router", "pinia"],
          "vuetify-core": ["vuetify"],
          "axios":        ["axios"],
          "socket-io":    ["socket.io-client"],
        },
      },
    },
    cssCodeSplit: true,
  },
});
