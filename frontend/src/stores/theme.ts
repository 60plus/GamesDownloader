/**
 * Theme & skin store - persists to localStorage, applies to <html> attributes.
 *
 * Controls:
 *  - data-theme       → CSS theme file
 *  - data-skin        → color palette
 *  - data-animations  → enable/disable animations
 *  - data-ambient     → ambient background orbs
 *  - data-grid        → grid overlay pattern
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
const LS_GRID           = "gd3_grid";
const LS_ORB_MOTION     = "gd3_orb_motion";
const LS_THEME_SETTINGS = "gd3_theme_settings";
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
  const grid       = ref(localStorage.getItem(LS_GRID)       !== "false");
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

  // ── Apply to DOM ───────────────────────────────────────────────────────
  function applyToDOM() {
    const root = document.documentElement;
    root.setAttribute("data-theme",      themeId.value);
    root.setAttribute("data-skin",       skinId.value);
    root.setAttribute("data-animations", String(animations.value));
    root.setAttribute("data-ambient",    String(ambient.value));
    root.setAttribute("data-grid",       String(grid.value));

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
  function toggleGrid()       { grid.value       = !grid.value;       }
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

  // ── Persist + apply on change ──────────────────────────────────────────
  watch(themeId,    (v) => { localStorage.setItem(LS_THEME,      v);          applyToDOM(); schedulePreferencesSave(); });
  watch(skinId,     (v) => { localStorage.setItem(LS_SKIN,       v);          applyToDOM(); schedulePreferencesSave(); });
  watch(animations, (v) => { localStorage.setItem(LS_ANIMATIONS, String(v));  applyToDOM(); schedulePreferencesSave(); });
  watch(ambient,    (v) => { localStorage.setItem(LS_AMBIENT,    String(v));  applyToDOM(); schedulePreferencesSave(); });
  watch(grid,       (v) => { localStorage.setItem(LS_GRID,       String(v));  applyToDOM(); schedulePreferencesSave(); });
  watch(orbMotion,  (v) => { localStorage.setItem(LS_ORB_MOTION, String(v));  applyToDOM(); schedulePreferencesSave(); });

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
    if (typeof prefs.grid       === "boolean") { grid.value          = prefs.grid;        localStorage.setItem(LS_GRID,       String(prefs.grid)); }
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
    applyToDOM();
    _loading = false;
  }

  /** Collect all current settings into a plain object for persistence. */
  function _snapshot(): Record<string, unknown> {
    return {
      theme: themeId.value, skin: skinId.value,
      animations: animations.value, ambient: ambient.value,
      grid: grid.value, orbMotion: orbMotion.value,
      cardTilt: cardTilt.value, cardShine: cardShine.value,
      cardZoom: cardZoom.value, cardGlow: cardGlow.value,
      cardLift: cardLift.value, coverSize: coverSize.value,
      heroBlur: heroBlur.value, heroAnim: heroAnim.value,
      heroAnimStyle: heroAnimStyle.value, heroAnimSpeed: heroAnimSpeed.value,
      heroFadeHeight: heroFadeHeight.value, classicHero: classicHero.value,
      platformPhotoHeader: platformPhotoHeader.value,
      themeSettings: themeSettings.value,
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
    themeId, skinId, animations, ambient, grid, orbMotion,
    currentTheme, currentLayout, currentSkins, themes,
    setTheme, setSkin, toggleAnimations, toggleAmbient, toggleGrid, toggleOrbMotion,
    getThemeSettingValue, setThemeSettingValue, resetThemeSettings,
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
