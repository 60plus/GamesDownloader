# GamesDownloaderV3 — Design System Handoff

**Status:** Living document. Update when tokens, components, or system-level patterns change.
**Last significant update:** 2026-04-19 (commit `b92d4b0`)

---

## Overview

Self-hosted gaming launcher combining **GOG library + custom games + ROM emulation + couch mode**. Glass/ambient aesthetics inspired by Steam and GOG Galaxy. **12 colour skins** per-user (storage in `localStorage.gd3_skin` + Pinia `theme` store).

**Stack:** Vue 3 + TypeScript + Vite. **No UI framework.** Custom design system built on CSS variables + scoped component styles.

- `frontend/src/styles/base.css` — non-skin tokens (radius, typography, spacing, motion, layout, glass defaults, behavior toggles, focus ring)
- `frontend/src/styles/skins.css` — 12 skin definitions, each overriding ~20 colour/glass tokens
- Per-component scoped `<style>` — local styling using tokens

Vuetify is imported in `plugins/vuetify.ts` but practically unused outside of 1–2 legacy spots.

---

## Layout

### Breakpoints

Single mobile breakpoint: `@media (max-width: 600px)`. Everything above is the desktop grid.

### Global shell

```
┌─ LayoutShell.vue ─────────────────────────────────────┐
│  <AmbientBackground />  ← position: fixed, inset: 0   │
│  <navbar> or <sidebar>  ← --navbar-height: 62px       │
│  <router-view />        ← main content                │
└────────────────────────────────────────────────────────┘
```

Navigation: 5 top-level tabs — Home / GOG Library / Games Library / Emulation / Couch Mode.

### Stacking context (CRITICAL — do not break)

`.ambient-bg` has `isolation: isolate`. Without this, the `mix-blend-mode: screen` on `.ambient-orb` leaks through the entire root stacking context and lightens every element above it — hero backgrounds, covers, everything. This was the root cause of "white fog on every hero" that cost an entire debugging session (session 31). **Never remove it.**

---

## Design Tokens (`frontend/src/styles/base.css`)

### Radius scale

| Token           | Value | Usage                              |
|-----------------|-------|------------------------------------|
| `--radius-xs`   | 4px   | Chips, badges, tags                |
| `--radius-sm`   | 8px   | Inputs, small cards, list-qf table |
| `--radius`      | 12px  | Cards, dialogs, cover images       |
| `--radius-lg`   | 18px  | Hero cards, large panels           |
| `--radius-pill` | 999px | Pills, round buttons               |

### Typography scale

| Token      | Value | Usage                                       |
|------------|-------|---------------------------------------------|
| `--fs-xs`  | 10px  | Tiny labels, overlay titles                 |
| `--fs-sm`  | 12px  | Body text, list descriptions, qf labels     |
| `--fs-md`  | 14px  | Default UI text, buttons                    |
| `--fs-lg`  | 16px  | Prominent labels, section heads             |
| `--fs-xl`  | 18px  | Subheads                                    |
| `--fs-2xl` | 22px  | Page titles, dialog heads                   |
| `--fs-3xl` | 28px  | Hero titles                                 |

### Spacing scale (4px base grid)

| Token        | Value | Common usage              |
|--------------|-------|---------------------------|
| `--space-0`  | 0     | —                         |
| `--space-1`  | 4px   | Chip gap, tight spacing   |
| `--space-2`  | 8px   | Button padding, list gaps |
| `--space-3`  | 12px  | Card inner padding        |
| `--space-4`  | 16px  | Section padding           |
| `--space-5`  | 20px  | Between major sections    |
| `--space-6`  | 24px  | Page padding              |
| `--space-8`  | 32px  | Large vertical rhythm     |
| `--space-10` | 40px  | Hero padding              |
| `--space-12` | 48px  | Page-level spacing        |

### Motion

| Token                | Value         | Usage                                           |
|----------------------|---------------|-------------------------------------------------|
| `--transition`       | `0.16s ease`  | Hover states, buttons, inputs                   |
| `--transition-slow`  | `0.32s ease`  | Panel slides, modal fades                       |
| `--hero-anim-speed`  | skin-tuned    | Ken Burns / Drift / Pulse duration divisor      |

### Layout

| Token              | Value | Usage                    |
|--------------------|-------|--------------------------|
| `--sidebar-width`  | 272px | Classic layout sidebar   |
| `--navbar-height`  | 62px  | Top navbar height        |

### Glass

| Token               | Value        | Usage                                   |
|---------------------|--------------|-----------------------------------------|
| `--glass-blur-px`   | 22px         | `backdrop-filter: blur()` for panels    |
| `--glass-sat`       | 180%         | `saturate()` paired with blur           |
| `--navbar-blur-px`  | 28px         | Stronger blur for navbar                |
| `--glass-bg`        | per-skin rgba| Panel fill (dialogs, menus)             |
| `--glass-border`    | per-skin rgba| Panel border (~15% alpha of `--pl`)     |
| `--glass-highlight` | per-skin rgba| Light wash on top edge                  |

### Behavior toggles (skin-controlled)

| Token              | Values   | Usage                                 |
|--------------------|----------|---------------------------------------|
| `--card-glow`      | `0 \| 1` | Toggle glow around library cards      |
| `--hover-lift`     | `0 \| 1` | Toggle `translateY` on hover          |
| `--logo-glow`      | `0 \| 1` | Toggle logo shadow/glow               |
| `--ui-glow-mult`   | `0..2`   | Multiplier for UI accent glows        |
| `--tab-glow`       | `0..2`   | Multiplier for active tab glow        |

### Skin tokens (overridden by every skin)

| Token              | Role                                            |
|--------------------|-------------------------------------------------|
| `--bg`             | Primary background (deep dark)                  |
| `--bg2`, `--bg3`   | Gradient stops for bg variations                |
| `--text`           | Primary text (~`#e8e2f4`)                       |
| `--muted`          | Secondary text — `rgba(..., 0.55)` (WCAG AA)    |
| `--pl`             | Primary accent (skin hue)                       |
| `--pl2`            | Darker accent                                   |
| `--pl-light`       | Lighter accent                                  |
| `--pl-dim`         | 12% tint for subtle backgrounds                 |
| `--pglow`          | 50% tint for ambient orbs                       |
| `--pglow2`         | 25% tint for secondary orbs                     |
| `--border`         | Default border color (18% `--pl`)               |
| `--ok` / `--ok-glow` | Success states                                |
| `--danger`         | Error states                                    |
| `--warning`        | Warning states                                  |
| `--info` / `--info-glow` | Info states                               |
| `--scrollbar-thumb` | Scrollbar fill                                 |

**Skins shipped:** Dark Purple (default), Deep Blue, Ocean Teal, Rose Pink, Forest Green, Crimson Red, Electric Magenta, Violet Cyan, Orange Pink, Emerald Blue, Red Orange, Indigo, Indigo-Rose, Burnt Orange.

---

## Reusable Components

### `<HeroBackground>` (`components/common/HeroBackground.vue`)

Shared hero background used by **every game detail view** (GOG / Games / Emulation).

| Prop           | Type                                              | Default       | Description                               |
|----------------|---------------------------------------------------|---------------|-------------------------------------------|
| `src`          | `string \| null`                                  | —             | URL/path to the hero image                |
| `animStyle`    | `'kenburns' \| 'drift' \| 'pulse' \| null`        | `'kenburns'`  | Animation type (comes from theme store)   |
| `animEnabled`  | `boolean`                                         | `true`        | Global animation switch                   |
| `showVignette` | `boolean`                                         | `true`        | Render dark vignette mask                 |

**Encapsulated CSS:**

- Filter: `blur(var(--gd-hero-blur, 14px)) saturate(120%) brightness(.48)`
- Three animation keyframes: `gd-kenburns` / `gd-drift` / `gd-pulse`
- Vignette: three-gradient dark mask into `var(--bg)`

**Do not use** for home-lib-cards or list-hero-img — those have different brightness values (`.30`, `.35`, `.55`) and remain inline. Could be migrated later with optional `brightness` / `showVignette` props, but that's a follow-up task.

### `<AmbientBackground>` (`components/common/AmbientBackground.vue`)

Global ambient orbs rendered from the top-level layout.

**Props:** none. Everything is pulled from the theme store via `getThemeSettingValue('orbCount' / 'orbPattern')`.

**Animation patterns:** `organic` (default) / `drift` / `pulse` / `vortex`.

**Orb count:** 1–3, scalable via `--orb-scale` (0.5..2), speed via `--orb-speed-mult` (0.1..3).

### Other frequently used components

- `<GdDialog>` — glass modal (backdrop + close button)
- `<LibraryMetadataPanel>` — Edit Metadata panel (Cover / Hero / Logo / Icon / Screenshots / Video / Description / Details / Requirements tabs)
- `<ThemeSwitcher>` — skin & layout picker
- `<TranslateButton>` — i18n translate for description fields

---

## Skin System

### How skins work

- `document.documentElement.setAttribute('data-skin', 'deep-blue')` (stored in `localStorage.gd3_skin`)
- In `skins.css`: `[data-skin="deep-blue"] { --pl: ...; --bg: ...; }`
- Every skin overrides ~20 tokens
- Default skin is `dark-purple`, declared under the bare `:root`

### Adding a new skin

1. Add a `[data-skin="my-skin"] { ... }` block in `skins.css`
2. Define every token listed in the [Skin tokens](#skin-tokens-overridden-by-every-skin) table
3. Add an entry in `ThemeSwitcher.vue` `skins[]` array

### User controls (Settings → Appearance)

- Skin picker (12 options)
- Layout: Classic (sidebar) / Modern (navbar)
- Animations kill-switch
- Hero blur slider (0–40 px) → `--gd-hero-blur`
- Hero animation style (Ken Burns / Drift / Pulse)
- Hero animation speed (slow / normal / fast) → `--hero-anim-speed`
- Hero → body fade height (0–200 px) → `--gd-hero-fade-h`
- Classic-layout hero toggle
- Orb count, motion, pattern, scale, opacity, speed

---

## Layout Patterns

### Glass panel recipe

```css
background: var(--glass-bg);
backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
-webkit-backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
border: 1px solid var(--glass-border);
border-radius: var(--radius);
```

### `list-qf` table (library list view)

```
┌──────────┬──────────────┐
│ LABEL    │ VALUE        │
│ (100px)  │ (flex: 1)    │
└──────────┴──────────────┘
```

`--fs-xs` uppercase labels, nowrap. `.list-qf-col` width: 230 px — fits `SVILUPPATORE` / `DEVELOPPEUR` in Italian / French.

### Hero on game detail

```
┌─────────────────────────────────────────────┐
│  <HeroBackground />  (absolute, z-index: 0) │
│    ┌──────────┐                             │
│    │ Cover    │  Title / dev / year         │
│    │ (tilted) │  Ratings                    │
│    │          │  Tags + OS chips            │
│    └──────────┘  Download + Edit + Refresh  │
└─────────────────────────────────────────────┘
```

---

## Interaction Specs

### Buttons

| Variant          | Class                | Visual                                              |
|------------------|----------------------|-----------------------------------------------------|
| Primary download | `.gd-btn-dl`         | Gradient fill (`--pl` → `--pl2`)                    |
| Ghost            | `.gd-btn-ghost`      | `color-mix(var(--pl) 8%, transparent)` background   |
| Danger           | `.gd-btn-danger`     | `color-mix(var(--danger) 15%, transparent)` bg      |
| Publish (teal)   | `.gd-btn-publish`    | Teal accent for library actions                     |

**Hover states:** `transform: translateY(-1px)` if `--hover-lift: 1`, saturation bump.

### Focus ring (WCAG 2.4.7)

```css
:focus-visible {
  outline: 2px solid var(--pl) !important;
  outline-offset: 2px !important;
  border-radius: inherit;
}
```

Global rule. Only matches keyboard-triggered focus — mouse clicks will not show the ring. `!important` is used to defeat legacy `outline: none` declarations scattered across scoped component styles.

### Hero animations (driven by user setting)

| Animation | Base duration | Transform                                   |
|-----------|---------------|---------------------------------------------|
| Ken Burns | 44 s          | `scale 1.06 → 1.14` + translate             |
| Drift     | 28 s (alternate) | `scale 1.1` + `translateX(-5%)`          |
| Pulse     | 10 s          | `scale 1.04 → 1.11`                         |

Applied as `duration / max(var(--hero-anim-speed, 1), 0.1)` — slow multiplies, fast divides.

### `[data-animations="false"]` kill-switch

Root attribute disables every `animation-duration` and `transition-duration` via a `*` selector globally. Every animating component must respect it.

---

## Accessibility

- **Focus ring** — global `:focus-visible` outline in `--pl`, `outline-offset: 2px`
- **Colour contrast** — `--text` on `--bg` is ~14:1 (AAA). `--muted` is ~7.3:1 (AAA small text)
- **Ambient isolation** — `isolation: isolate` on `.ambient-bg` prevents blend-mode leak
- **i18n** — 8 locales (EN / PL / DE / FR / ES / PT / RU / IT) via the `useI18n()` composable, ~800 keys × 8 JSON files
- **Keyboard navigation** — every interactive element is a native `<button>`, visible `:focus-visible`
- **Known gap:** no focus-trap inside dialogs — Tab can escape a modal

---

## Edge Cases (known patterns)

| Scenario                                 | Handling                                                              |
|------------------------------------------|-----------------------------------------------------------------------|
| Cover / hero image 404                   | `@error` handler sets `display: none` on the `<img>`                  |
| Empty library                            | Fallback message + illustration in `home-lib-card-cover-empty`        |
| Long game titles                         | `text-overflow: ellipsis` with `-webkit-line-clamp: 2`                |
| Long description                         | `-webkit-line-clamp: 7` in `list-hero-desc-text`                      |
| Long i18n labels (SVILUPPATORE)          | `.list-qf-label` width: 100 px (fits ~12 uppercase chars)             |
| GOG v1 vs v2 background                  | v2 `galaxyBackgroundImage` takes priority (v1 has store overlay)      |
| Multiple platform aliases (atari2600/ + atari-2600/) | `_init_rom_dirs` dedupes by canonical slug; scanner tolerates both |

---

## Known Debt

### Not migrated to tokens

- **Non-canonical font sizes** (11, 13, 15, 20, 24, 30 px) — ~555 instances. No exact token. Left inline as deliberate micro-decisions.
- **Non-canonical border-radius** (5, 6, 10, 14, 16, 20, 24 px) — ~200 instances. Context-specific (chips, pills, hero cards).
- **Multi-value spacing** (`padding: 8px 12px`, etc.) — ~500 instances. Each would need a per-axis judgment call which token to use.

### Un-extracted duplication

- **`GogLibrary` + `GamesLibrary` list view** — 95 % duplicate markup and CSS. Awaits `<LibraryListRow>` extraction (2–4 h with union type + slots, deferred to a dedicated session).
- **Hero variants** — `home-lib-hero-bg`, `emu-platform-hero-bg`, `emu-title-bg`, `list-hero-img` each have their own brightness / scale. Could adopt `<HeroBackground>` with optional props.

### Misc

- **Spinner component** — three implementations (`gd-spin`, `mep-spinner`, `spin`). Should be a single `<Spinner>`.
- **Flag icons** — emoji flags do not render on Windows Chrome / Edge. Plan: `flag-icons` CSS package or inline SVG for the top 10.
- **Focus trap in dialogs** — missing, Tab can escape.
- **Unit tests** — none for UI components. Manual verification only.

---

## File Map

```
frontend/src/
├── styles/
│   ├── base.css          ← all non-skin tokens
│   ├── skins.css         ← 12 skins
│   └── glass.css         ← (legacy, unused)
├── components/
│   ├── common/
│   │   ├── AmbientBackground.vue  ← ambient orbs in the background
│   │   ├── HeroBackground.vue     ← shared hero bg for game detail
│   │   ├── ThemeSwitcher.vue
│   │   ├── SearchBar.vue
│   │   ├── UserMenu.vue
│   │   └── TranslateButton.vue
│   ├── games/LibraryMetadataPanel.vue  ← Edit Metadata
│   ├── gog/DownloadDialog.vue
│   ├── GdDialog.vue      ← generic modal
│   └── RandomGamePicker.vue
├── layouts/
│   ├── MainLayout.vue     ← root auth guard
│   ├── LayoutShell.vue    ← skin-switchable wrapper
│   ├── ModernLayout.vue   ← navbar layout
│   └── ClassicLayout.vue  ← sidebar layout
├── views/
│   ├── GamesHome.vue
│   ├── gog/{GogLibrary, GogGameDetail}.vue
│   ├── games/{GamesLibrary, GamesGameDetail}.vue
│   ├── emulation/{EmulationHome, EmulationLibrary, EmulationGameDetail, EmulationRomMetadataPanel}.vue
│   ├── couch/{CouchMode, CouchGamelist, CouchSystemView, CouchMenu, CouchWelcome}.vue
│   ├── settings/{SettingsIndex, SettingsAppearance, SettingsDownloads, SettingsRoms, ...}.vue
│   └── setup/{SetupWizard, steps/Step1-7}.vue
├── stores/theme.ts        ← Pinia: skin, layout, animations, hero blur/anim, orbs
├── i18n/{en,pl,de,fr,es,pt,ru,it}.json  ← ~800 keys × 8 locales
└── plugins/router.ts      ← routes + meta.requiresAdmin gates
```

---

## Notes for the next developer

**Before touching list view:** read [Un-extracted duplication](#un-extracted-duplication). Every fix has to land in two files (GogLibrary + GamesLibrary). When you feel it for the third time, the extraction is worth it.

**Before changing hero on a game detail page:** `<HeroBackground>` is shared across GOG / Games / Emulation detail. One edit reaches three views. That is the point.

**Before adding a skin:** copy an existing block in `skins.css`, edit the values. Nothing else — the token system does the rest automatically.

**Before removing `isolation: isolate` from `.ambient-bg`:** don't. Session 31 proved that the `mix-blend-mode: screen` on orbs otherwise leaks across the entire app (the "white fog on every hero" bug). Read the session memory if curious.

**Before a large mechanical sweep** (radius / font-size / spacing): the pattern used in sessions 31–32 is — run `sed` via Alpine container on the server, commit there, `git bundle` back to the host, `git fetch` the bundle, `git merge --ff-only`. This works around the Windows host not having `sed` or `node` available. See commits `916d883`, `21d060d`, `b92d4b0` for the exact recipe.
