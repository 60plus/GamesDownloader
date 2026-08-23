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

/**
 * The card and hero effects the Appearance page offers.
 *
 * A theme lists the ones it actually draws. Anything it leaves out is shown
 * greyed out with a note, instead of offering a switch that quietly does
 * nothing - which is what happened while the list did not exist: Vapor drew
 * no highlight at all, yet its users had a Card shine switch.
 */
export type ThemeEffect =
  | "cardTilt" | "cardShine" | "cardZoom" | "cardGlow" | "cardLift"
  | "heroAnim" | "heroAnimStyle" | "heroBlur" | "heroFade"
  | "ambient" | "orbMotion"
  | "classicHero" | "platformPhoto";

/** Every effect there is. A theme that says nothing is taken to draw them all. */
export const ALL_EFFECTS: ThemeEffect[] = [
  "cardTilt", "cardShine", "cardZoom", "cardGlow", "cardLift",
  "heroAnim", "heroAnimStyle", "heroBlur", "heroFade",
  "ambient", "orbMotion", "classicHero", "platformPhoto",
];

export interface Theme {
  id: string;
  name: string;
  description: string;
  layout: string; // "modern", "classic", or plugin-defined layout id
  skins: Skin[];
  defaultSkin: string;
  cssFile: string;     // path to theme CSS (dynamic import)
  font?: string;       // stylesheet URL, injected as <link> (see stores/theme.ts)
  previewHtml?: string; // optional inline HTML for ThemeSwitcher preview card (plugin-provided)
  settings?: ThemeSetting[]; // per-theme configurable options applied as CSS vars
  /** Core effects this theme draws. Omit to mean all of them, which is what
   *  every theme meant before the field existed - so an older plugin theme
   *  keeps behaving exactly as it did. */
  effects?: ThemeEffect[];
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
    font: "/fonts/inter.css",
    // Everything but the Classic-only hero switch.
    effects: [
      "cardTilt", "cardShine", "cardZoom", "cardGlow", "cardLift",
      "heroAnim", "heroAnimStyle", "heroBlur", "heroFade",
      "ambient", "orbMotion", "platformPhoto",
    ],
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
    font: "/fonts/rajdhani.css",
    // The library grids are shared with Modern, so the card effects apply.
    // The detail views are Classic's own and have no configurable hero fade.
    effects: [
      "cardTilt", "cardShine", "cardZoom", "cardGlow", "cardLift",
      "heroAnim", "heroAnimStyle", "heroBlur",
      "ambient", "orbMotion", "classicHero", "platformPhoto",
    ],
    settings: [
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

// ── Plugin metadata-panel tabs ──────────────────────────────────────────────
// Lets any plugin (including plain-JS frontend_get_js plugins) add a tab to the
// game metadata editor (LibraryMetadataPanel). The tab content is mounted as
// vanilla DOM via the `mount(el, ctx)` callback, so no compiled Vue component
// is required. Registered through window.__GD__.registerMetadataTab().

export interface MetadataTabContext {
  /** The game record currently being edited (includes meta_ratings). */
  game: Record<string, unknown>;
  /** API base for this panel, e.g. "/library/games" or "/gog/library/games". */
  apiPrefix: string;
  /** Close the metadata panel. */
  close: () => void;
  /** Notify the host that data changed so the detail view re-fetches. */
  save: (data?: Record<string, unknown>) => void;
  /**
   * Mark the tab as having unsaved changes. Enables the panel's own Save
   * button so the user can persist tab edits through the normal Save flow.
   */
  markDirty?: () => void;
  /**
   * Register a handler invoked when the user clicks the panel's Save button.
   * Return a partial PATCH payload (e.g. `{ meta_ratings: {...} }`) to be
   * folded into the panel's single save request; `meta_ratings` is shallow
   * merged (null/undefined values delete a key), other keys are assigned.
   * Returning nothing contributes nothing. Replaces any previous handler.
   */
  onSave?: (
    handler: () =>
      | Promise<Record<string, unknown> | void>
      | Record<string, unknown>
      | void,
  ) => void;
}

export interface MetadataTab {
  id: string;
  label: string;
  /** Which library's panel to show in: "games" | "gog" | "all" (default "games"). */
  library?: string;
  /** Build the tab body into `el`. Return an optional cleanup function. */
  mount: (el: HTMLElement, ctx: MetadataTabContext) => void | (() => void);
}

const _metadataTabs: Map<string, MetadataTab> = shallowReactive(new Map());

export function registerMetadataTab(tab: MetadataTab): void {
  if (tab && tab.id && typeof tab.mount === "function") {
    _metadataTabs.set(tab.id, tab);
  }
}

export function getMetadataTabs(): MetadataTab[] {
  return Array.from(_metadataTabs.values());
}

// ── Plugin detail-page rows ─────────────────────────────────────────────────
// Lets any plugin add one or more rows to the game detail "info card" without
// hand-injecting DOM into each theme's bespoke markup. The ACTIVE THEME renders
// the row natively in its own style (Modern `.gd-dlist`, Classic `.icard`, and
// any future theme), so plugin rows always match the surrounding card.
//
// Two ways to supply the value, mix freely:
//   1. Declarative `segments` (theme-styled, auto-matches the theme): a list of
//      typed pieces (text / badge / icon / bar / link / image / sep). Maximum
//      visual freedom WITHOUT touching the theme - colors, icons, tooltips,
//      click handlers, custom classes and inline styles are all per-segment.
//   2. `render(el, ctx)` escape hatch (total control): the theme hands the
//      plugin the value cell and a context (game, library, variant, t, api);
//      the plugin draws anything. Guarantees a plugin never needs a core change
//      to render something new.
// Registered through window.__GD__.registerDetailRow().

export interface DetailSegment {
  /** Visual kind. Default "text". */
  type?: "text" | "badge" | "icon" | "bar" | "link" | "image" | "sep";
  /** Text content (text / badge / link). */
  text?: string;
  /** Foreground / accent color (any CSS color or var()). */
  color?: string;
  /** Background color (badge). */
  bg?: string;
  /** Mask icon: a data: URI or URL, recolored with `color` (icon / badge / inline). */
  icon?: string;
  /** Image source (type "image"). */
  src?: string;
  /** Pixel size for icon / image height. */
  size?: number;
  /** Bar fill 0..1 (type "bar"). */
  value?: number;
  /** Link target (type "link"). Opens in a new tab. */
  href?: string;
  bold?: boolean;
  muted?: boolean;
  /** Native title/tooltip. */
  title?: string;
  /** Extra CSS class (so a plugin's own injected CSS can target it). */
  class?: string;
  /** Inline style escape hatch. */
  style?: Record<string, string>;
  /** Click handler (makes the segment interactive). */
  onClick?: (ev: MouseEvent) => void;
}

export interface DetailRowData {
  /** Row label shown in the key column. Omit (or set fullWidth) for no label. */
  label?: string;
  /** Declarative value content. Ignored when `render` is provided. */
  segments?: DetailSegment[];
  /** Optional expandable section revealed by a "Show details" toggle. */
  details?: {
    /** Toggle text; defaults to a translated "Show details" / "Hide details". */
    toggleLabel?: string;
    /** Each entry is one detail line made of segments. */
    items: DetailSegment[][];
  };
  /** Span the whole card (no label column) - a free canvas for the value. */
  fullWidth?: boolean;
  /** Row accent color. */
  color?: string;
  /** Row tooltip. */
  title?: string;
  /** Extra CSS class on the row element. */
  class?: string;
  /**
   * Escape hatch: draw the value cell yourself. When present, `segments` is
   * ignored and the theme mounts this into the value element. Return an
   * optional cleanup function.
   */
  render?: (el: HTMLElement, ctx: DetailRowRenderContext) => void | (() => void);
}

export interface DetailRowRenderContext {
  /** The game record being shown (includes meta_ratings). */
  game: Record<string, unknown>;
  /** Which library: "games" | "gog" | "roms". */
  library: string;
  /** The active theme's row style: "dlist" (Modern) | "icard" (Classic) | custom. */
  variant: string;
  /** Translate a key with an English fallback. */
  t: (key: string, fallback?: string) => string;
  /** Authenticated axios instance (window.__GD__.api). */
  api: unknown;
}

export interface DetailRow {
  id: string;
  /** Limit to one library, or "all" (default). */
  library?: "games" | "gog" | "roms" | "all";
  /** Sort order among injected rows (ascending; default 0). */
  order?: number;
  /**
   * Build the row for a given game. Return the row data, or null to hide the
   * row for this particular game. Called reactively as the detail view renders.
   */
  resolve: (ctx: { game: Record<string, unknown>; library: string }) => DetailRowData | null;
}

const _detailRows: Map<string, DetailRow> = shallowReactive(new Map());

export function registerDetailRow(row: DetailRow): void {
  if (row && row.id && typeof row.resolve === "function") {
    _detailRows.set(row.id, row);
  }
}

export function getDetailRows(library?: string): DetailRow[] {
  return Array.from(_detailRows.values())
    .filter((r) => !library || !r.library || r.library === "all" || r.library === library)
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
}

/** A row's resolved data for a specific game, with its registration id attached. */
export interface ResolvedDetailRow extends DetailRowData {
  id: string;
}

/**
 * Resolve every registered row for one game + library. Rows whose `resolve`
 * returns null (no data for this game) or throws are skipped. Host detail views
 * iterate this and render each row in their own native row markup, putting a
 * <PluginDetailValue> in the value cell.
 */
export function resolveDetailRows(
  game: Record<string, unknown>,
  library: string,
): ResolvedDetailRow[] {
  const out: ResolvedDetailRow[] = [];
  for (const r of getDetailRows(library)) {
    try {
      const data = r.resolve({ game, library });
      if (data) out.push({ id: r.id, ...data });
    } catch {
      /* a misbehaving plugin row must not break the detail page */
    }
  }
  return out;
}

// ── Theme home sections ─────────────────────────────────────────────────────
// A theme that renders EXTRA sections on its home page (trailer shelves, genre
// tiles, top-rated rails...) registers them here so Settings -> Libraries can
// offer per-user on/off toggles next to the core library visibility. The
// hidden set is stored per-theme in the theme store (themeSettings), so each
// theme remembers its own selection. A theme layout registers on mount and
// unregisters on unmount, so only the ACTIVE layout's sections are listed.

/** A per-section switch, offered next to the section in Settings (e.g. Vapor's
 *  "big card on the left"). The theme reads it back with isOptionOn(). */
export interface ThemeHomeSectionOption {
  /** Stable id, unique within the section. */
  id: string;
  /** Display label: an i18n key when translatable, else shown verbatim. */
  label: string;
  /** On when the user has never touched it. */
  default?: boolean;
}

export interface ThemeHomeSection {
  /** Stable section id - the per-user setting key (e.g. "trailers"). */
  id: string;
  /** Display label: an i18n key when translatable, else shown verbatim. */
  label: string;
  /** Optional switches for this section alone. */
  options?: ThemeHomeSectionOption[];
  /** Whether Settings offers the reorder arrows for this section. Default true.
   *  Set false when the theme lays this section out at a fixed spot and does
   *  not route it through homeSections.order() - Settings must not show a
   *  control that saves a preference nothing reads. */
  orderable?: boolean;
}

const _homeSections = shallowReactive<ThemeHomeSection[]>([]);

/** Register a theme's togglable home sections. Returns an unregister fn. */
export function registerHomeSections(sections: ThemeHomeSection[]): () => void {
  const valid = (sections || []).filter((s) => s && s.id);
  for (const s of valid) {
    const i = _homeSections.findIndex((x) => x.id === s.id);
    if (i >= 0) _homeSections.splice(i, 1, s);
    else _homeSections.push(s);
  }
  const ids = valid.map((s) => s.id);
  return () => {
    for (const id of ids) {
      const i = _homeSections.findIndex((x) => x.id === id);
      if (i >= 0) _homeSections.splice(i, 1);
    }
  };
}

/** The active theme's registered home sections (reactive). */
export function getHomeSections(): ThemeHomeSection[] {
  return _homeSections;
}

/** Settings blocks a theme can take over. A theme that ships its own on-page
 *  editor claims the ones it covers, and Settings stops rendering its controls
 *  for them - the same state offered in two places is how the two drift apart,
 *  and how a user ends up wondering which one actually applies. */
export type ManagedSettingKey =
  | "libraryVisibility"   // Settings -> Libraries: per-user library on/off
  | "recentLibraries"     // Settings -> Libraries: which libraries feed "recently added"
  | "homeSections";       // Settings -> Libraries: theme home section order/visibility/options

const _managedSettings = shallowReactive<string[]>([]);

/** Claim settings this theme edits itself. Returns an unclaim fn, so a theme
 *  that unmounts hands the controls back to Settings. */
export function registerManagedSettings(keys: ManagedSettingKey[]): () => void {
  const added = (keys || []).filter((k) => k && !_managedSettings.includes(k));
  _managedSettings.push(...added);
  return () => {
    for (const k of added) {
      const i = _managedSettings.indexOf(k);
      if (i >= 0) _managedSettings.splice(i, 1);
    }
  };
}

/** Does the active theme edit this setting itself? (reactive) */
export function isSettingManaged(key: ManagedSettingKey | string): boolean {
  return _managedSettings.includes(key);
}

// ── Plugin route registry (custom plugin pages) ──────────────────────────────
// A plugin declares a custom page two ways that meet here:
//   1. backend hook frontend_get_routes -> nav metadata {path, label, icon}
//      (fetched in main.ts: added to the router as /x/<path> + exposed for nav).
//   2. the plugin's injected JS supplies the page CONTENT by calling
//      window.__GD__.registerRoute({ path, mount }); PluginPage.vue looks the
//      mount up by path when the /x/<path> route is active.
export interface PluginRouteMount {
  path: string;
  mount: (el: HTMLElement, ctx: { path: string; api: unknown; t: (k: string) => string }) => (() => void) | void;
}

const _pluginRouteMounts = new Map<string, PluginRouteMount["mount"]>();

/** Plugin JS -> register how a custom page renders (vanilla DOM mount). */
export function registerPluginRoute(route: PluginRouteMount): void {
  if (route && route.path && typeof route.mount === "function") {
    _pluginRouteMounts.set(String(route.path).replace(/^\/+/, ""), route.mount);
  }
}

/** PluginPage.vue -> the mount fn registered for a path (or undefined). */
export function getPluginRouteMount(path: string): PluginRouteMount["mount"] | undefined {
  return _pluginRouteMounts.get(String(path || "").replace(/^\/+/, ""));
}

/** Nav metadata for plugin pages (reactive; set from the backend hook in
 *  main.ts). Themes read this to render their own nav links. */
export const pluginNavRoutes = shallowReactive<{ path: string; label: string; icon: string }[]>([]);

export function setPluginNavRoutes(routes: { path: string; label: string; icon: string }[]): void {
  pluginNavRoutes.splice(0, pluginNavRoutes.length, ...(routes || []));
}
