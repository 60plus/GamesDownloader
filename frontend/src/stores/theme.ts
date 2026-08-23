/**
 * Theme & skin store - persists to localStorage, applies to <html> attributes.
 *
 * Controls:
 *  - data-theme       → CSS theme file
 *  - data-skin        → color palette
 *  - data-animations  → enable/disable animations
 *  - data-ambient     → ambient background orbs
 *
 * Per-theme settings are stored as CSS custom properties on :root,
 * overriding the skin defaults. Each theme declares its own settings
 * in the Theme.settings array.
 */

import { defineStore } from "pinia";
import { ref, watch, computed } from "vue";
import { getTheme, getAllThemes, type Theme, type Skin } from "@/themes";

const LS_THEME          = "gd3_theme";
const LS_SKIN           = "gd3_skin";
const LS_ANIMATIONS     = "gd3_animations";
const LS_AMBIENT        = "gd3_ambient";
const LS_ORB_MOTION     = "gd3_orb_motion";
const LS_THEME_SETTINGS = "gd3_theme_settings";
const LS_HIDDEN_LIBS    = "gd3_hidden_libraries";
const LS_LIBRARY_ORDER  = "gd3_library_order";
// Card effects
const LS_CARD_TILT      = "gd3_card_tilt";
const LS_CARD_SHINE     = "gd3_card_shine";
const LS_CARD_ZOOM      = "gd3_card_zoom";
const LS_CARD_GLOW      = "gd3_card_glow";
const LS_CARD_LIFT      = "gd3_card_lift";
// Cover size (library grid)
const LS_COVER_SIZE       = "gd3_cover_size";
// Hero blur (game detail page background)
const LS_HERO_BLUR        = "gd3_hero_blur";
// Hero animation
const LS_HERO_ANIM        = "gd3_hero_anim";
const LS_HERO_ANIM_STYLE  = "gd3_hero_anim_style";
const LS_HERO_ANIM_SPEED  = "gd3_hero_anim_speed";
// Hero body transition fade
const LS_HERO_FADE_H      = "gd3_hero_fade_h";
// Classic Layout settings
const LS_CLASSIC_HERO     = "gd3_classic_hero";
// Emulation Library platform photo header
const LS_PLATFORM_PHOTO_HEADER = "gd3_platform_photo_header";

export const useThemeStore = defineStore("theme", () => {
  // ── State ──────────────────────────────────────────────────────────────
  const themeId    = ref(localStorage.getItem(LS_THEME)      || "gameyfin");
  const skinId     = ref(localStorage.getItem(LS_SKIN)       || "purple");
  const animations = ref(localStorage.getItem(LS_ANIMATIONS) !== "false");
  const ambient    = ref(localStorage.getItem(LS_AMBIENT)    !== "false");
  const orbMotion  = ref(localStorage.getItem(LS_ORB_MOTION) !== "false");
  // Card effects
  const cardTilt   = ref(localStorage.getItem(LS_CARD_TILT)  !== "false");
  const cardShine  = ref(localStorage.getItem(LS_CARD_SHINE) !== "false");
  const cardZoom   = ref(localStorage.getItem(LS_CARD_ZOOM)  !== "false");
  const cardGlow   = ref(localStorage.getItem(LS_CARD_GLOW)  !== "false");
  const cardLift   = ref(localStorage.getItem(LS_CARD_LIFT)  !== "false");
  // Cover size preset
  const coverSize  = ref(localStorage.getItem(LS_COVER_SIZE) || "m");
  // Hero background blur (px, 0–40, default 14)
  const heroBlur       = ref(Number(localStorage.getItem(LS_HERO_BLUR) ?? 14));
  // Hero background animation
  const heroAnim       = ref(localStorage.getItem(LS_HERO_ANIM)       !== "false");
  const heroAnimStyle  = ref(localStorage.getItem(LS_HERO_ANIM_STYLE) || "kenburns");
  const heroAnimSpeed  = ref(localStorage.getItem(LS_HERO_ANIM_SPEED) || "normal");
  // Hero → body transition fade height (px)
  const heroFadeHeight = ref(Number(localStorage.getItem(LS_HERO_FADE_H) ?? 80));
  // Classic Layout
  const classicHero    = ref(localStorage.getItem(LS_CLASSIC_HERO) !== "false");
  // Emulation Library - platform photo header
  const platformPhotoHeader = ref(localStorage.getItem(LS_PLATFORM_PHOTO_HEADER) !== "false");

  // Per-theme settings: { [themeId]: { [settingKey]: value } }
  const themeSettings = ref<Record<string, Record<string, unknown>>>(
    JSON.parse(localStorage.getItem(LS_THEME_SETTINGS) ?? "{}")
  );

  // User-hidden libraries (global per-user): slugs the user removed from their
  // own home/nav view. Independent of the admin "enabled" flag and of the
  // per-theme recentLibraries selection. Persists via /users/me/preferences.
  const hiddenLibraries = ref<string[]>(
    JSON.parse(localStorage.getItem(LS_HIDDEN_LIBS) ?? "[]")
  );

  // User-defined library order (list of slugs). Overrides the admin sort_order
  // on this user's home/nav. Empty = follow the admin order. Global per-user.
  const libraryOrder = ref<string[]>(
    JSON.parse(localStorage.getItem(LS_LIBRARY_ORDER) ?? "[]")
  );

  // ── Getters ────────────────────────────────────────────────────────────
  const currentTheme   = computed<Theme | undefined>(() => getTheme(themeId.value));
  const currentLayout  = computed(() => currentTheme.value?.layout ?? "modern");
  const currentSkins   = computed<Skin[]>(() => currentTheme.value?.skins ?? []);
  const themes         = computed(() => getAllThemes());

  function getThemeSettingValue(key: string): unknown {
    const setting = currentTheme.value?.settings?.find(s => s.key === key);
    if (!setting) return undefined;
    return themeSettings.value[themeId.value]?.[key] ?? setting.default;
  }

  /**
   * Does the theme in use actually draw this effect?
   *
   * A theme that lists nothing is taken to draw everything, which is what all
   * of them meant before the list existed - so a plugin theme built against an
   * older core keeps behaving exactly as it did.
   */
  function supportsEffect(id: string): boolean {
    const declared = currentTheme.value?.effects;
    return !Array.isArray(declared) || declared.includes(id as never);
  }

  // ── Apply to DOM ───────────────────────────────────────────────────────
  function applyToDOM() {
    const root = document.documentElement;
    root.setAttribute("data-theme",      themeId.value);
    root.setAttribute("data-skin",       skinId.value);
    root.setAttribute("data-animations", String(animations.value));
    root.setAttribute("data-ambient",    String(ambient.value));

    // The card effects, for themes that draw them in CSS rather than in
    // script. Vapor paints its accent ring and its light sweep entirely in
    // stylesheets, so reading the store was never open to it - it needs the
    // switch on the document, the same way it already reads data-animations.
    root.setAttribute("data-card-tilt",  String(cardTilt.value));
    root.setAttribute("data-card-shine", String(cardShine.value));
    root.setAttribute("data-card-zoom",  String(cardZoom.value));
    root.setAttribute("data-card-glow",  String(cardGlow.value));
    root.setAttribute("data-card-lift",  String(cardLift.value));
    // Same reason: a theme that animates its hero art in a stylesheet has no
    // other way to hear about these. The core's own hero picks its motion with
    // a class, which is no use to anyone outside this bundle.
    root.setAttribute("data-hero-anim",       String(heroAnim.value));
    root.setAttribute("data-hero-anim-style", heroAnimStyle.value);
    // A theme with a backdrop of its own needs to hear about these two as
    // well. data-ambient was already written but nothing ever read it.
    root.setAttribute("data-orb-motion", String(orbMotion.value));

    // Apply per-theme settings as CSS custom properties
    const theme = currentTheme.value;
    if (theme?.settings) {
      for (const setting of theme.settings) {
        const value = themeSettings.value[themeId.value]?.[setting.key] ?? setting.default;
        if (setting.type === "range") {
          root.style.setProperty(setting.cssVar, `${value}${setting.unit ?? ""}`);
        } else if (setting.type === "select") {
          root.style.setProperty(setting.cssVar, String(value));
        } else {
          root.style.setProperty(setting.cssVar, (value as boolean) ? "1" : "0");
        }
      }
    }

    // Hero blur + fade height CSS variables
    root.style.setProperty("--gd-hero-blur",     `${heroBlur.value}px`);
    root.style.setProperty("--gd-hero-fade-h",   `${heroFadeHeight.value}px`);
    // Hero animation speed multiplier (slow=0.5, normal=1, fast=2)
    const speedMap: Record<string, string> = { slow: "0.5", normal: "1", fast: "2" };
    root.style.setProperty("--hero-anim-speed", speedMap[heroAnimSpeed.value] ?? "1");

    // Load theme font
    if (theme?.font) {
      let link = document.getElementById("gd3-theme-font") as HTMLLinkElement | null;
      if (!link) {
        link = document.createElement("link");
        link.id = "gd3-theme-font";
        link.rel = "stylesheet";
        document.head.appendChild(link);
      }
      link.href = theme.font;
    }

    // Notify plugin JS that theme settings changed (avoids polling)
    root.dispatchEvent(new CustomEvent('gd-theme-updated'));
  }

  // ── Actions ────────────────────────────────────────────────────────────
  function setTheme(id: string) {
    const theme = getTheme(id);
    if (!theme) return;
    const oldLayout = currentLayout.value;
    themeId.value = id;
    localStorage.setItem(LS_THEME, id);
    // Reset skin to theme default if current skin not available
    if (!theme.skins.find((s) => s.id === skinId.value)) {
      skinId.value = theme.defaultSkin;
    }
    // Full reload when layout changes (Modern <-> Classic <-> Plugin)
    if (theme.layout !== oldLayout) {
      applyToDOM();
      // Save immediately (bypass debounce), then navigate
      const token = localStorage.getItem("gd3_token");
      const dest = theme.layout === "classic" ? "/library" : "/";
      const doNav = () => { window.location.href = dest; };
      if (token) {
        fetch("/api/users/me/preferences", {
          method: "PUT",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify(_snapshot()),
        }).finally(doNav);
      } else {
        doNav();
      }
    }
  }

  function setSkin(id: string) {
    skinId.value = id;
  }

  function toggleAnimations() { animations.value = !animations.value; }
  function toggleAmbient()    { ambient.value    = !ambient.value;    }
  function toggleOrbMotion()  { orbMotion.value  = !orbMotion.value;  }

  function setThemeSettingValue(key: string, value: unknown) {
    if (!themeSettings.value[themeId.value]) {
      themeSettings.value[themeId.value] = {};
    }
    themeSettings.value[themeId.value][key] = value;
    localStorage.setItem(LS_THEME_SETTINGS, JSON.stringify(themeSettings.value));
    applyToDOM();
    schedulePreferencesSave();
  }

  function resetThemeSettings() {
    delete themeSettings.value[themeId.value];
    localStorage.setItem(LS_THEME_SETTINGS, JSON.stringify(themeSettings.value));
    applyToDOM();
  }

  // Per-theme "recently added" library selection (list of slugs). Returns null
  // when unset, which the home page treats as "all libraries".
  function getRecentLibraries(): string[] | null {
    const v = themeSettings.value[themeId.value]?.recentLibraries;
    return Array.isArray(v) ? (v as string[]) : null;
  }
  function setRecentLibraries(slugs: string[]) {
    setThemeSettingValue("recentLibraries", slugs);
  }

  // Per-theme hidden home sections: ids of theme-registered home sections
  // (registerHomeSections) this user switched off. Unset = show everything.
  function getHiddenHomeSections(): string[] {
    const v = themeSettings.value[themeId.value]?.hiddenHomeSections;
    return Array.isArray(v) ? (v as string[]) : [];
  }
  function isHomeSectionHidden(id: string): boolean {
    return getHiddenHomeSections().includes(id);
  }
  function toggleHomeSection(id: string) {
    const cur = getHiddenHomeSections();
    setThemeSettingValue(
      "hiddenHomeSections",
      cur.includes(id) ? cur.filter(s => s !== id) : [...cur, id],
    );
  }
  /** Explicit set, for a checkbox or an eye toggle that knows the state it
   *  wants. Writing the value it already holds is skipped, so an editor that
   *  re-applies its whole state does not trigger a save per section. */
  function setHomeSectionHidden(id: string, hidden: boolean) {
    const cur = getHiddenHomeSections();
    if (hidden === cur.includes(id)) return;
    setThemeSettingValue(
      "hiddenHomeSections",
      hidden ? [...cur, id] : cur.filter(s => s !== id),
    );
  }

  // The order this user dragged the theme's home sections into. Ids absent from
  // the list keep the theme's own order, after the ones that are listed - so a
  // theme adding a section later does not need everyone's setting rewritten.
  function getHomeSectionOrder(): string[] {
    const v = themeSettings.value[themeId.value]?.homeSectionOrder;
    return Array.isArray(v) ? (v as string[]) : [];
  }
  /** Merges rather than replaces: a caller only ever knows the sections of the
   *  page it is drawing, and a theme may make several pages arrangeable into
   *  this one key. Replacing here would let arranging one page drop every id
   *  the caller has never heard of, silently resetting the other pages. Ids
   *  not mentioned keep their saved positions, ahead of the incoming ones -
   *  relative order across pages is meaningless, since each page only ever
   *  sorts its own ids through orderHomeSections. Settings, which passes the
   *  full registered list, is unaffected. */
  function setHomeSectionOrder(ids: string[]) {
    const incoming = new Set(ids);
    const saved = getHomeSectionOrder();
    // Refill the slots the incoming ids already held, and leave every other id
    // exactly where it was. Putting the untouched ids first instead would
    // promote a section that is merely absent right now - a collection rail
    // whose library is hidden, or one whose fetch has not landed - to the top
    // of the page the moment anything else is moved.
    const queue = [...ids];
    const out: string[] = [];
    for (const id of saved) {
      if (!incoming.has(id)) { out.push(id); continue; }
      const next = queue.shift();
      if (next !== undefined) out.push(next);   // a duplicate slot just closes up
    }
    setThemeSettingValue("homeSectionOrder", [...out, ...queue]);
  }
  // Per-section switches (e.g. which side a Vapor rail's big card sits on).
  // Stored as {sectionId: {optId: bool}} so an option the user never touched
  // can fall back to the theme's default rather than to "off".
  function getHomeSectionOptions(): Record<string, Record<string, boolean>> {
    const v = themeSettings.value[themeId.value]?.homeSectionOptions;
    return v && typeof v === "object" ? (v as Record<string, Record<string, boolean>>) : {};
  }
  function isHomeSectionOptionOn(sectionId: string, optId: string, dflt = false): boolean {
    const v = getHomeSectionOptions()[sectionId]?.[optId];
    return typeof v === "boolean" ? v : dflt;
  }
  function setHomeSectionOption(sectionId: string, optId: string, on: boolean) {
    const cur = getHomeSectionOptions();
    setThemeSettingValue("homeSectionOptions", {
      ...cur,
      [sectionId]: { ...(cur[sectionId] || {}), [optId]: on },
    });
  }

  /** Clear just this theme's section layout - order, hidden and per-section
   *  options - and leave its other settings (skin, cover size, recent
   *  libraries) alone. resetThemeSettings() wipes the lot, which is far too
   *  blunt for a "reset layout" button inside an editor. Written in one go so
   *  the page rebuilds its sections once rather than three times. */
  function resetHomeSectionLayout() {
    const cur = themeSettings.value[themeId.value];
    if (!cur) return;
    delete cur.hiddenHomeSections;
    delete cur.homeSectionOrder;
    delete cur.homeSectionOptions;
    localStorage.setItem(LS_THEME_SETTINGS, JSON.stringify(themeSettings.value));
    applyToDOM();
    schedulePreferencesSave();
  }

  /** `ids` sorted by this user's order (unlisted ids keep their relative order,
   *  at the end). Themes call this to lay their sections out. */
  function orderHomeSections(ids: string[]): string[] {
    const pref = getHomeSectionOrder();
    return [...ids].sort((a, b) => {
      const ia = pref.indexOf(a), ib = pref.indexOf(b);
      if (ia === -1 && ib === -1) return 0;      // both unlisted: keep as given
      if (ia === -1) return 1;
      if (ib === -1) return -1;
      return ia - ib;
    });
  }

  // Per-user library visibility (global across themes). Hiding a library only
  // removes it from this user's home page / nav; it does not change access.
  function getHiddenLibraries(): string[] { return hiddenLibraries.value; }
  function isLibraryHidden(slug: string): boolean { return hiddenLibraries.value.includes(slug); }
  function setHiddenLibraries(slugs: string[]) {
    hiddenLibraries.value = [...new Set(slugs)];
    localStorage.setItem(LS_HIDDEN_LIBS, JSON.stringify(hiddenLibraries.value));
    applyToDOM();              // fires gd-theme-updated so themes/plugins re-render
    schedulePreferencesSave();
  }
  function toggleHiddenLibrary(slug: string) {
    const cur = hiddenLibraries.value;
    setHiddenLibraries(cur.includes(slug) ? cur.filter(s => s !== slug) : [...cur, slug]);
  }

  // Per-user library order (global across themes). Empty list = admin order.
  function getLibraryOrder(): string[] { return libraryOrder.value; }
  function setLibraryOrder(slugs: string[]) {
    libraryOrder.value = [...slugs];
    localStorage.setItem(LS_LIBRARY_ORDER, JSON.stringify(libraryOrder.value));
    applyToDOM();              // fires gd-theme-updated so themes/plugins re-render
    schedulePreferencesSave();
  }

  // ── Persist + apply on change ──────────────────────────────────────────
  watch(themeId,    (v) => { localStorage.setItem(LS_THEME,      v);          applyToDOM(); schedulePreferencesSave(); });
  watch(skinId,     (v) => { localStorage.setItem(LS_SKIN,       v);          applyToDOM(); schedulePreferencesSave(); });
  watch(animations, (v) => { localStorage.setItem(LS_ANIMATIONS, String(v));  applyToDOM(); schedulePreferencesSave(); });
  watch(ambient,    (v) => { localStorage.setItem(LS_AMBIENT,    String(v));  applyToDOM(); schedulePreferencesSave(); });
  watch(orbMotion,  (v) => { localStorage.setItem(LS_ORB_MOTION, String(v));  applyToDOM(); schedulePreferencesSave(); });

  // The card effects reach CSS-drawn themes as document attributes, so the
  // document has to be told when one changes. Their toggles write localStorage
  // themselves; this only refreshes what the stylesheets can see.
  watch([cardTilt, cardShine, cardZoom, cardGlow, cardLift, heroAnim, heroAnimStyle],
        () => { applyToDOM(); });

  // ── Card effect actions ────────────────────────────────────────────────
  function toggleClassicHero() { classicHero.value = !classicHero.value; localStorage.setItem(LS_CLASSIC_HERO, String(classicHero.value)); schedulePreferencesSave(); }
  function togglePlatformPhotoHeader() { platformPhotoHeader.value = !platformPhotoHeader.value; localStorage.setItem(LS_PLATFORM_PHOTO_HEADER, String(platformPhotoHeader.value)); schedulePreferencesSave(); }
  function toggleCardTilt()  { cardTilt.value  = !cardTilt.value;  localStorage.setItem(LS_CARD_TILT,  String(cardTilt.value));  schedulePreferencesSave(); }
  function toggleCardShine() { cardShine.value = !cardShine.value; localStorage.setItem(LS_CARD_SHINE, String(cardShine.value)); schedulePreferencesSave(); }
  function toggleCardZoom()  { cardZoom.value  = !cardZoom.value;  localStorage.setItem(LS_CARD_ZOOM,  String(cardZoom.value));  schedulePreferencesSave(); }
  function toggleCardGlow()  { cardGlow.value  = !cardGlow.value;  localStorage.setItem(LS_CARD_GLOW,  String(cardGlow.value));  schedulePreferencesSave(); }
  function toggleCardLift()  { cardLift.value  = !cardLift.value;  localStorage.setItem(LS_CARD_LIFT,  String(cardLift.value));  schedulePreferencesSave(); }
  function setCoverSize(s: string) { coverSize.value = s; localStorage.setItem(LS_COVER_SIZE, s); schedulePreferencesSave(); }
  function setHeroBlur(v: number)  {
    heroBlur.value = v;
    localStorage.setItem(LS_HERO_BLUR, String(v));
    document.documentElement.style.setProperty("--gd-hero-blur", `${v}px`);
    schedulePreferencesSave();
  }
  function toggleHeroAnim() {
    heroAnim.value = !heroAnim.value;
    localStorage.setItem(LS_HERO_ANIM, String(heroAnim.value));
    schedulePreferencesSave();
  }
  function setHeroAnimStyle(s: string) {
    heroAnimStyle.value = s;
    localStorage.setItem(LS_HERO_ANIM_STYLE, s);
    schedulePreferencesSave();
  }
  function setHeroAnimSpeed(s: string) {
    heroAnimSpeed.value = s;
    localStorage.setItem(LS_HERO_ANIM_SPEED, s);
    const speedMap: Record<string, string> = { slow: "0.5", normal: "1", fast: "2" };
    document.documentElement.style.setProperty("--hero-anim-speed", speedMap[s] ?? "1");
    schedulePreferencesSave();
  }
  function setHeroFadeHeight(v: number) {
    heroFadeHeight.value = v;
    localStorage.setItem(LS_HERO_FADE_H, String(v));
    document.documentElement.style.setProperty("--gd-hero-fade-h", `${v}px`);
    schedulePreferencesSave();
  }

  // ── Per-user preferences sync ────────────────────────────────────────────
  // Debounce timer for API saves (avoid hammering backend on slider drag, etc.)
  let _saveTimer: ReturnType<typeof setTimeout> | null = null;
  // Guard: suppress watcher-triggered saves while loading from backend
  let _loading = false;

  /** Load preferences from backend after login. Overrides localStorage values. */
  function loadPreferences(prefs: Record<string, unknown>) {
    if (!prefs || typeof prefs !== "object") return;
    _loading = true;
    // Apply each setting if present
    if (typeof prefs.theme      === "string")  { themeId.value       = prefs.theme;       localStorage.setItem(LS_THEME, prefs.theme); }
    if (typeof prefs.skin       === "string")  { skinId.value        = prefs.skin;        localStorage.setItem(LS_SKIN, prefs.skin); }
    if (typeof prefs.animations === "boolean") { animations.value    = prefs.animations;  localStorage.setItem(LS_ANIMATIONS, String(prefs.animations)); }
    if (typeof prefs.ambient    === "boolean") { ambient.value       = prefs.ambient;     localStorage.setItem(LS_AMBIENT,    String(prefs.ambient)); }
    if (typeof prefs.orbMotion  === "boolean") { orbMotion.value     = prefs.orbMotion;   localStorage.setItem(LS_ORB_MOTION, String(prefs.orbMotion)); }
    if (typeof prefs.cardTilt   === "boolean") { cardTilt.value      = prefs.cardTilt;    localStorage.setItem(LS_CARD_TILT,  String(prefs.cardTilt)); }
    if (typeof prefs.cardShine  === "boolean") { cardShine.value     = prefs.cardShine;   localStorage.setItem(LS_CARD_SHINE, String(prefs.cardShine)); }
    if (typeof prefs.cardZoom   === "boolean") { cardZoom.value      = prefs.cardZoom;    localStorage.setItem(LS_CARD_ZOOM,  String(prefs.cardZoom)); }
    if (typeof prefs.cardGlow   === "boolean") { cardGlow.value      = prefs.cardGlow;    localStorage.setItem(LS_CARD_GLOW,  String(prefs.cardGlow)); }
    if (typeof prefs.cardLift   === "boolean") { cardLift.value      = prefs.cardLift;    localStorage.setItem(LS_CARD_LIFT,  String(prefs.cardLift)); }
    if (typeof prefs.coverSize  === "string")  { coverSize.value     = prefs.coverSize;   localStorage.setItem(LS_COVER_SIZE, prefs.coverSize); }
    if (typeof prefs.heroBlur   === "number")  { heroBlur.value      = prefs.heroBlur;    localStorage.setItem(LS_HERO_BLUR,  String(prefs.heroBlur)); }
    if (typeof prefs.heroAnim   === "boolean") { heroAnim.value      = prefs.heroAnim;    localStorage.setItem(LS_HERO_ANIM,  String(prefs.heroAnim)); }
    if (typeof prefs.heroAnimStyle  === "string") { heroAnimStyle.value  = prefs.heroAnimStyle;  localStorage.setItem(LS_HERO_ANIM_STYLE, prefs.heroAnimStyle); }
    if (typeof prefs.heroAnimSpeed  === "string") { heroAnimSpeed.value  = prefs.heroAnimSpeed;  localStorage.setItem(LS_HERO_ANIM_SPEED, prefs.heroAnimSpeed); }
    if (typeof prefs.heroFadeHeight === "number") { heroFadeHeight.value = prefs.heroFadeHeight; localStorage.setItem(LS_HERO_FADE_H,     String(prefs.heroFadeHeight)); }
    if (typeof prefs.classicHero    === "boolean") { classicHero.value   = prefs.classicHero;   localStorage.setItem(LS_CLASSIC_HERO,    String(prefs.classicHero)); }
    if (typeof prefs.platformPhotoHeader === "boolean") { platformPhotoHeader.value = prefs.platformPhotoHeader; localStorage.setItem(LS_PLATFORM_PHOTO_HEADER, String(prefs.platformPhotoHeader)); }
    if (prefs.themeSettings && typeof prefs.themeSettings === "object") {
      themeSettings.value = prefs.themeSettings as Record<string, Record<string, unknown>>;
      localStorage.setItem(LS_THEME_SETTINGS, JSON.stringify(prefs.themeSettings));
    }
    if (Array.isArray(prefs.hiddenLibraries)) {
      hiddenLibraries.value = prefs.hiddenLibraries as string[];
      localStorage.setItem(LS_HIDDEN_LIBS, JSON.stringify(prefs.hiddenLibraries));
    }
    if (Array.isArray(prefs.libraryOrder)) {
      libraryOrder.value = prefs.libraryOrder as string[];
      localStorage.setItem(LS_LIBRARY_ORDER, JSON.stringify(prefs.libraryOrder));
    }
    applyToDOM();
    _loading = false;
  }

  /** Collect all current settings into a plain object for persistence. */
  function _snapshot(): Record<string, unknown> {
    return {
      theme: themeId.value, skin: skinId.value,
      animations: animations.value, ambient: ambient.value,
      orbMotion: orbMotion.value,
      cardTilt: cardTilt.value, cardShine: cardShine.value,
      cardZoom: cardZoom.value, cardGlow: cardGlow.value,
      cardLift: cardLift.value, coverSize: coverSize.value,
      heroBlur: heroBlur.value, heroAnim: heroAnim.value,
      heroAnimStyle: heroAnimStyle.value, heroAnimSpeed: heroAnimSpeed.value,
      heroFadeHeight: heroFadeHeight.value, classicHero: classicHero.value,
      platformPhotoHeader: platformPhotoHeader.value,
      themeSettings: themeSettings.value,
      hiddenLibraries: hiddenLibraries.value,
      libraryOrder: libraryOrder.value,
    };
  }

  /** Debounced save to backend. Silently ignored if not authenticated or while loading. */
  function schedulePreferencesSave() {
    if (_loading) return;
    if (_saveTimer !== null) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(async () => {
      _saveTimer = null;
      const token = localStorage.getItem("gd3_token");
      if (!token) return;
      try {
        await fetch("/api/users/me/preferences", {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify(_snapshot()),
        });
      } catch { /* offline / not authed - silently ignore */ }
    }, 1200);
  }

  // Apply on store creation
  applyToDOM();

  return {
    themeId, skinId, animations, ambient, orbMotion,
    currentTheme, currentLayout, currentSkins, themes,
    setTheme, setSkin, toggleAnimations, toggleAmbient, toggleOrbMotion,
    getThemeSettingValue, setThemeSettingValue, resetThemeSettings, supportsEffect,
    getRecentLibraries, setRecentLibraries,
    getHiddenHomeSections, isHomeSectionHidden, toggleHomeSection, setHomeSectionHidden,
    getHomeSectionOrder, setHomeSectionOrder, orderHomeSections,
    isHomeSectionOptionOn, setHomeSectionOption, resetHomeSectionLayout,
    getHiddenLibraries, isLibraryHidden, setHiddenLibraries, toggleHiddenLibrary,
    getLibraryOrder, setLibraryOrder,
    applyToDOM,
    // Card effects
    cardTilt, cardShine, cardZoom, cardGlow, cardLift,
    toggleCardTilt, toggleCardShine, toggleCardZoom, toggleCardGlow, toggleCardLift,
    // Cover size
    coverSize, setCoverSize,
    // Hero blur
    heroBlur, setHeroBlur,
    // Hero animation
    heroAnim, heroAnimStyle, heroAnimSpeed,
    toggleHeroAnim, setHeroAnimStyle, setHeroAnimSpeed,
    // Hero → body fade
    heroFadeHeight, setHeroFadeHeight,
    // Classic Layout
    classicHero, toggleClassicHero,
    // Emulation Library
    platformPhotoHeader, togglePlatformPhotoHeader,
    // Per-user preferences
    loadPreferences,
  };
});
