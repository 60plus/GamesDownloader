/**
 * Theme & Skin registry.
 *
 * THEMES change the entire layout structure + visual style.
 * SKINS change the color palette within a theme.
 * Each theme declares which skins are available.
 * Each theme can also declare configurable settings applied as CSS variables.
 *
 * To create a custom theme, build an object matching the Theme interface
 * and call registerTheme(). No other changes needed.
 */

export interface Skin {
  id: string;
  name: string;
  preview: string; // hex OR CSS gradient for UI preview swatch
  dual?: boolean;  // true = dual-color skin (shown in second row)
}

export interface ThemeSetting {
  key: string;         // unique key within the theme
  label: string;       // display name in settings UI
  hint?: string;       // short description shown below label
  description?: string; // detailed description shown in hover panel
  section?: string;    // grouping key (e.g. 'orb' groups into Display Options)
  motion?: boolean;    // true = only relevant when Orb Motion is enabled
  type: "range" | "toggle" | "select";
  default: number | boolean | string;
  options?: string[];        // for select: available values
  optionLabels?: string[];   // for select: display labels (same order as options)
  // range-specific
  min?: number;
  max?: number;
  step?: number;
  unit?: string;       // appended to value when setting CSS var (e.g. 'px', '%')
  // CSS output
  cssVar: string;      // CSS custom property name to set on :root (e.g. '--glass-blur-px')
}

export interface Theme {
  id: string;
  name: string;
  description: string;
  layout: string; // "modern", "classic", or plugin-defined layout id
  skins: Skin[];
  defaultSkin: string;
  cssFile: string;     // path to theme CSS (dynamic import)
  font?: string;       // Google Fonts import URL
  previewHtml?: string; // optional inline HTML for ThemeSwitcher preview card (plugin-provided)
  settings?: ThemeSetting[]; // per-theme configurable options applied as CSS vars
}

// ── Default skins (shared by both default themes) ───────────────────────────

const NEON_SKINS: Skin[] = [
  // ── Row 1: Solid skins ────────────────────────────────────────────────────
  { id: "purple", name: "ts.skin.purple",       preview: "#7c3aed" },
  { id: "blue",   name: "ts.skin.blue",         preview: "#2563eb" },
  { id: "teal",   name: "ts.skin.teal",         preview: "#0891b2" },
  { id: "pink",   name: "ts.skin.pink",         preview: "#db2777" },
  { id: "green",  name: "ts.skin.green",        preview: "#16a34a" },
  { id: "red",    name: "ts.skin.red",          preview: "#dc2626" },
  { id: "orange", name: "ts.skin.orange",       preview: "#ea580c" },
  // ── Row 2: Dual-color skins ───────────────────────────────────────────────
  { id: "magenta-cyan",  name: "ts.skin.neonDusk",  preview: "linear-gradient(135deg,#d946ef,#22d3ee)", dual: true },
  { id: "violet-cyan",   name: "ts.skin.synthwave", preview: "linear-gradient(135deg,#8b5cf6,#06b6d4)", dual: true },
  { id: "orange-pink",   name: "ts.skin.sunset",    preview: "linear-gradient(135deg,#f97316,#ec4899)", dual: true },
  { id: "emerald-sky",   name: "ts.skin.aurora",    preview: "linear-gradient(135deg,#10b981,#60a5fa)", dual: true },
  { id: "red-orange",    name: "ts.skin.vulcan",    preview: "linear-gradient(135deg,#ef4444,#fb923c)", dual: true },
  { id: "blue-violet",   name: "ts.skin.midnight",  preview: "linear-gradient(135deg,#2563eb,#a78bfa)", dual: true },
  { id: "indigo-rose",   name: "ts.skin.cosmic",    preview: "linear-gradient(135deg,#4f46e5,#fb7185)", dual: true },
];

// Orb settings shared by all themes (both use AmbientBackground)
const ORB_SETTINGS: ThemeSetting[] = [
  {
    key: "orbCount",
    section: "orb",
    label: "ts.orbCount.label",
    hint: "ts.orbCount.hint",
    description: "ts.orbCount.desc",
    type: "select",
    default: "3",
    options: ["1", "2", "3"],
    optionLabels: ["1", "2", "3"],
    cssVar: "--orb-count",
  },
  {
    key: "orbSpeed",
    section: "orb",
    label: "ts.orbSpeed.label",
    hint: "ts.orbSpeed.hint",
    description: "ts.orbSpeed.desc",
    type: "range",
    default: 1,
    min: 0.3,
    max: 3,
    step: 0.1,
    cssVar: "--orb-speed-mult",
    motion: true,
  },
  {
    key: "orbSize",
    section: "orb",
    label: "ts.orbSize.label",
    hint: "ts.orbSize.hint",
    description: "ts.orbSize.desc",
    type: "range",
    default: 1,
    min: 0.4,
    max: 2.0,
    step: 0.05,
    cssVar: "--orb-scale",
  },
  {
    key: "orbGlow",
    section: "orb",
    label: "ts.orbGlow.label",
    hint: "ts.orbGlow.hint",
    description: "ts.orbGlow.desc",
    type: "range",
    default: 1,
    min: 0.2,
    max: 2.5,
    step: 0.05,
    cssVar: "--orb-opacity-mult",
  },
  {
    key: "orbPattern",
    section: "orb",
    label: "ts.orbPattern.label",
    hint: "ts.orbPattern.hint",
    description: "ts.orbPattern.desc",
    type: "select",
    default: "organic",
    options: ["organic", "drift", "pulse", "vortex"],
    optionLabels: ["ts.orbPattern.organic", "ts.orbPattern.drift", "ts.orbPattern.pulse", "ts.orbPattern.vortex"],
    cssVar: "--orb-pattern",
    motion: true,
  },
  {
    key: "orbTravel",
    section: "orb",
    label: "ts.orbTravel.label",
    hint: "ts.orbTravel.hint",
    description: "ts.orbTravel.desc",
    type: "range",
    default: 1,
    min: 0.2,
    max: 3.0,
    step: 0.1,
    cssVar: "--orb-travel",
    motion: true,
  },
];

// Glow settings shared by all themes
const GLOW_SETTINGS: ThemeSetting[] = [
  {
    key: "logoGlow",
    label: "ts.logoGlow.label",
    hint: "ts.logoGlow.hint",
    description: "ts.logoGlow.desc",
    type: "toggle",
    default: true,
    cssVar: "--logo-glow",
  },
  {
    key: "uiGlow",
    label: "ts.uiGlow.label",
    hint: "ts.uiGlow.hint",
    description: "ts.uiGlow.desc",
    type: "range",
    default: 1,
    min: 0,
    max: 2,
    step: 0.1,
    cssVar: "--ui-glow-mult",
  },
];

// ── Built-in themes ─────────────────────────────────────────────────────────

export const BUILTIN_THEMES: Theme[] = [
  {
    id: "gameyfin",
    name: "ts.theme.modern",
    description: "ts.theme.modern.desc",
    layout: "modern",
    skins: NEON_SKINS,
    defaultSkin: "purple",
    cssFile: "gameyfin",
    font: "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
    settings: [
      {
        key: "glassBlur",
        label: "ts.glassBlur.label",
        hint: "ts.glassBlur.hint",
        description: "ts.glassBlur.desc",
        type: "range",
        default: 22,
        min: 0,
        max: 60,
        step: 1,
        unit: "px",
        cssVar: "--glass-blur-px",
      },
      {
        key: "glassSat",
        label: "ts.glassSat.label",
        hint: "ts.glassSat.hint",
        description: "ts.glassSat.desc",
        type: "range",
        default: 180,
        min: 100,
        max: 300,
        step: 10,
        unit: "%",
        cssVar: "--glass-sat",
      },
      {
        key: "navbarBlur",
        label: "ts.navbarBlur.label",
        hint: "ts.navbarBlur.hint",
        description: "ts.navbarBlur.desc",
        type: "range",
        default: 28,
        min: 0,
        max: 80,
        step: 2,
        unit: "px",
        cssVar: "--navbar-blur-px",
      },
      {
        key: "cardGlow",
        label: "ts.cardGlow.label",
        hint: "ts.cardGlow.hint",
        description: "ts.cardGlow.desc",
        type: "toggle",
        default: true,
        cssVar: "--card-glow",
      },
      {
        key: "hoverLift",
        label: "ts.hoverLift.label",
        hint: "ts.hoverLift.hint",
        description: "ts.hoverLift.desc",
        type: "toggle",
        default: true,
        cssVar: "--hover-lift",
      },
      ...GLOW_SETTINGS,
      ...ORB_SETTINGS,
    ],
  },
  {
    id: "classic",
    name: "ts.theme.classic",
    description: "ts.theme.classic.desc",
    layout: "classic",
    skins: NEON_SKINS,
    defaultSkin: "purple",
    cssFile: "classic",
    font: "https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap",
    settings: [
      {
        key: "tabGlow",
        label: "ts.tabGlow.label",
        hint: "ts.tabGlow.hint",
        description: "ts.tabGlow.desc",
        type: "toggle",
        default: true,
        cssVar: "--tab-glow",
      },
      {
        key: "sidebarWidth",
        label: "ts.sidebarWidth.label",
        hint: "ts.sidebarWidth.hint",
        description: "ts.sidebarWidth.desc",
        type: "range",
        default: 280,
        min: 180,
        max: 380,
        step: 10,
        unit: "px",
        cssVar: "--sidebar-w",
      },
      {
        key: "logPanelHeight",
        label: "ts.logPanelHeight.label",
        hint: "ts.logPanelHeight.hint",
        description: "ts.logPanelHeight.desc",
        type: "range",
        default: 140,
        min: 60,
        max: 220,
        step: 10,
        unit: "px",
        cssVar: "--log-h",
      },
      {
        key: "coverHeight",
        label: "ts.coverHeight.label",
        hint: "ts.coverHeight.hint",
        description: "ts.coverHeight.desc",
        type: "range",
        default: 525,
        min: 350,
        max: 620,
        step: 10,
        unit: "px",
        cssVar: "--cd-cover-h",
      },
      ...GLOW_SETTINGS,
      ...ORB_SETTINGS,
    ],
  },
];

// ── Registry (allows adding custom themes at runtime) ────────────────────────

// reactive() so Vue re-evaluates computeds when plugin themes are registered async
import { reactive } from 'vue';
const _themes: Map<string, Theme> = reactive(new Map<string, Theme>());

const BUILTIN_IDS = new Set(['gameyfin', 'classic']);

export function registerTheme(theme: Theme): void {
  // Prevent plugins from overwriting built-in themes
  if (BUILTIN_IDS.has(theme.id) && _themes.has(theme.id)) return;
  _themes.set(theme.id, theme);
}

export function getTheme(id: string): Theme | undefined {
  return _themes.get(id);
}

export function getAllThemes(): Theme[] {
  return Array.from(_themes.values());
}

export function getThemeSkins(themeId: string): Skin[] {
  return _themes.get(themeId)?.skins ?? [];
}

// Register built-in themes
BUILTIN_THEMES.forEach(registerTheme);

// ── Plugin layout registry ─────────────────────────────────────────────────
// Plugins compiled on container startup register their layout components here.
// LayoutShell.vue checks this map for layouts not in the built-in LAYOUTS.

import { shallowReactive, type Component } from 'vue';
const _pluginLayouts: Map<string, Component> = shallowReactive(new Map());

const BUILTIN_LAYOUT_IDS = new Set(['modern', 'classic']);

export function registerPluginLayout(id: string, component: Component): void {
  // Prevent plugins from overwriting built-in layouts
  if (BUILTIN_LAYOUT_IDS.has(id)) return;
  _pluginLayouts.set(id, component);
}

export function getPluginLayout(id: string): Component | undefined {
  return _pluginLayouts.get(id);
}

// ── Plugin couch mode registry ──────────────────────────────────────────────
// Theme plugins can register a custom Couch Mode component that replaces the
// default CouchMode.vue when the user has that theme active.
// Key = theme ID (e.g., "neon-horizon"), Value = Vue component

const _pluginCouchModes: Map<string, Component> = shallowReactive(new Map());

export function registerPluginCouchMode(themeId: string, component: Component): void {
  _pluginCouchModes.set(themeId, component);
}

export function getPluginCouchMode(themeId: string): Component | undefined {
  return _pluginCouchModes.get(themeId);
}
