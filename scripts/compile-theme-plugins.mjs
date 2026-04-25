#!/usr/bin/env node
/**
 * compile-theme-plugins.mjs
 *
 * Scans /data/plugins/ for theme plugins that contain .vue files.
 * For each theme plugin, compiles the Vue SFC into a single IIFE JS bundle
 * that registers the layout component via window.__GD__.registerPluginLayout().
 *
 * The compiled output is placed in /app/static/plugin-layouts/{plugin-id}/layout.js
 * and loaded by the frontend via a <script> tag.
 *
 * Dependencies: vite, @vitejs/plugin-vue (copied from frontend build stage)
 */

import { build } from 'vite';
import vue from '@vitejs/plugin-vue';
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, resolve } from 'path';

const PLUGINS_DIR = process.env.PLUGINS_DIR || '/data/plugins';
const OUTPUT_DIR = process.env.OUTPUT_DIR || '/app/static/plugin-layouts';
const MANIFEST_PATH = join(OUTPUT_DIR, 'manifest.json');

async function main() {
  if (!existsSync(PLUGINS_DIR)) {
    console.log('[plugin-compiler] No plugins directory found, skipping.');
    return;
  }

  const pluginDirs = readdirSync(PLUGINS_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => d.name);

  const manifest = {};
  let compiled = 0;

  for (const pluginId of pluginDirs) {
    // Strict ID validation — prevent injection in generated JS
    if (!/^[a-z0-9][a-z0-9._-]*$/i.test(pluginId)) {
      console.log(`[plugin-compiler] Skipping "${pluginId}" — invalid plugin ID`);
      continue;
    }

    const pluginDir = join(PLUGINS_DIR, pluginId);
    const pluginJson = join(pluginDir, 'plugin.json');

    // Must have plugin.json with type: "theme"
    if (!existsSync(pluginJson)) continue;
    let meta;
    try {
      meta = JSON.parse(readFileSync(pluginJson, 'utf-8'));
    } catch { continue; }
    if (meta.type !== 'theme') continue;

    // Must have at least one .vue file
    const vueFiles = readdirSync(pluginDir).filter(f => f.endsWith('.vue'));
    if (vueFiles.length === 0) continue;

    // Look for a layout entry point
    const layoutFile = vueFiles.find(f => /layout/i.test(f)) || vueFiles[0];
    const entryPath = join(pluginDir, layoutFile);

    // Look for optional couch mode component
    const couchFile = vueFiles.find(f => /couch/i.test(f));
    const couchPath = couchFile ? join(pluginDir, couchFile) : null;

    console.log(`[plugin-compiler] Compiling theme "${pluginId}" (${layoutFile}${couchFile ? ' + ' + couchFile : ''})...`);

    const outDir = join(OUTPUT_DIR, pluginId);
    mkdirSync(outDir, { recursive: true });

    // Create a temporary entry file that imports layout + optional couch mode
    let entryCode = `
import Layout from '${entryPath.replace(/\\/g, '/')}';
if (window.__GD__ && window.__GD__.registerPluginLayout) {
  window.__GD__.registerPluginLayout('${pluginId}', Layout);
  console.log('[plugin] Registered layout: ${pluginId}');
}
`;
    if (couchPath) {
      entryCode += `
import CouchMode from '${couchPath.replace(/\\/g, '/')}';
if (window.__GD__ && window.__GD__.registerPluginCouchMode) {
  window.__GD__.registerPluginCouchMode('${pluginId}', CouchMode);
  console.log('[plugin] Registered couch mode: ${pluginId}');
}
`;
    }
    const tmpEntry = join(outDir, '_entry.js');
    writeFileSync(tmpEntry, entryCode);

    try {
      await build({
        configFile: false,
        root: pluginDir,
        plugins: [vue()],
        build: {
          lib: {
            entry: tmpEntry,
            formats: ['iife'],
            name: `GDPlugin_${pluginId.replace(/[^a-zA-Z0-9]/g, '_')}`,
            fileName: () => 'layout.js',
            cssFileName: 'layout',
          },
          outDir,
          emptyOutDir: false,
          sourcemap: false,
          minify: true,
          // Don't process static assets (images, fonts etc.)
          assetsInlineLimit: 0,
          rollupOptions: {
            external: (id) => {
              // Externalize vue, vue-router, pinia, axios
              if (['vue', 'vue-router', 'pinia', 'axios'].includes(id)) return true;
              // Externalize static asset references (start with /)
              if (id.startsWith('/') && !id.includes('plugin')) return true;
              return false;
            },
            output: {
              globals: (id) => {
                if (id === 'vue') return 'window.__GD__.Vue';
                if (id === 'vue-router') return 'window.__GD__.VueRouter';
                if (id === 'pinia') return 'window.__GD__.Pinia';
                if (id === 'axios') return 'window.__GD__.axios';
                // Static asset paths — return empty object (won't be used at runtime)
                return '{}';
              },
              exports: 'none',
            },
          },
        },
        logLevel: 'warn',
      });

      // Clean up temp entry
      try { const { unlinkSync } = await import('fs'); unlinkSync(tmpEntry); } catch {}

      manifest[pluginId] = {
        js: `plugin-layouts/${pluginId}/layout.js`,
        css: `plugin-layouts/${pluginId}/layout.css`,
        compiledAt: new Date().toISOString(),
      };
      compiled++;
      console.log(`[plugin-compiler] ✓ ${pluginId} compiled successfully`);
    } catch (err) {
      console.error(`[plugin-compiler] ✗ ${pluginId} failed:`, err.message);
      // Clean up temp entry on failure too
      try { const { unlinkSync } = await import('fs'); unlinkSync(tmpEntry); } catch {}
    }
  }

  // Write manifest for the frontend to discover compiled layouts
  mkdirSync(OUTPUT_DIR, { recursive: true });
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
  console.log(`[plugin-compiler] Done. ${compiled} theme(s) compiled.`);
}

main().catch(err => {
  console.error('[plugin-compiler] Fatal error:', err);
  process.exit(1);
});
