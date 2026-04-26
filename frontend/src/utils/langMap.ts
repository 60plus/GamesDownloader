/**
 * Shared language code -> flag + display name mapping.
 * Used by GOG Detail, Games Detail, Classic Detail for consistent language display.
 *
 * The `flag` field carries an ISO 3166-1 alpha-2 country code (lowercase),
 * not a Unicode emoji. Templates render it as
 *   <span class="fi" :class="`fi-${entry.flag}`"></span>
 * so the CSS sprite from `flag-icons` shows on every platform - the bare
 * regional-indicator emoji used to display as letters on Windows Chrome / Edge.
 *
 * Normalization groups (deduplication):
 *   Portuguese (Brazil) + Portuguese -> Portuguese
 *   Chinese (Simplified) + Chinese (Traditional) -> Chinese
 *   English (US) + English -> English
 *   Spanish (Latin America) + Spanish -> Spanish
 */

export interface LangEntry {
  flag: string;   // ISO 3166-1 alpha-2 (lowercase) for `<span class="fi fi-XX">`
  name: string;
  /** If set, this code is a variant of `group` - deduplicated to group in simplified display */
  group?: string;
}

export const LANG_MAP: Record<string, LangEntry> = {
  en:       { flag: 'gb', name: 'English' },
  'en-US':  { flag: 'us', name: 'English (US)', group: 'en' },
  pl:       { flag: 'pl', name: 'Polish' },
  de:       { flag: 'de', name: 'German' },
  fr:       { flag: 'fr', name: 'French' },
  es:       { flag: 'es', name: 'Spanish' },
  'es-419': { flag: 'mx', name: 'Spanish (Latin America)', group: 'es' },
  it:       { flag: 'it', name: 'Italian' },
  ru:       { flag: 'ru', name: 'Russian' },
  cn:       { flag: 'cn', name: 'Chinese', group: 'zh-group' },    // GOG code
  zh:       { flag: 'cn', name: 'Chinese', group: 'zh-group' },    // GOG code
  'zh-Hans':{ flag: 'cn', name: 'Chinese', group: 'zh-group' },    // ISO
  'zh-Hant':{ flag: 'tw', name: 'Chinese', group: 'zh-group' },    // ISO
  jp:       { flag: 'jp', name: 'Japanese' },   // GOG code
  ja:       { flag: 'jp', name: 'Japanese', group: 'jp' },   // ISO
  ko:       { flag: 'kr', name: 'Korean' },
  pt:       { flag: 'pt', name: 'Portuguese' },
  br:       { flag: 'br', name: 'Portuguese', group: 'pt' }, // GOG code
  'pt-BR':  { flag: 'br', name: 'Portuguese', group: 'pt' }, // ISO
  nl:       { flag: 'nl', name: 'Dutch' },
  cz:       { flag: 'cz', name: 'Czech' },  // GOG code
  cs:       { flag: 'cz', name: 'Czech', group: 'cz' },  // ISO
  hu:       { flag: 'hu', name: 'Hungarian' },
  ro:       { flag: 'ro', name: 'Romanian' },
  sk:       { flag: 'sk', name: 'Slovak' },
  sv:       { flag: 'se', name: 'Swedish' },
  fi:       { flag: 'fi', name: 'Finnish' },
  da:       { flag: 'dk', name: 'Danish' },
  no:       { flag: 'no', name: 'Norwegian' },
  tr:       { flag: 'tr', name: 'Turkish' },
  uk:       { flag: 'ua', name: 'Ukrainian' },
  ar:       { flag: 'sa', name: 'Arabic' },
  el:       { flag: 'gr', name: 'Greek' },
  he:       { flag: 'il', name: 'Hebrew' },
  th:       { flag: 'th', name: 'Thai' },
  // GOG non-standard codes
  es_mx:    { flag: 'mx', name: 'Spanish', group: 'es' },
  gk:       { flag: 'gr', name: 'Greek',   group: 'el' },
  sb:       { flag: 'rs', name: 'Serbian' },
};

/**
 * Normalize full language names to simplified base form.
 * "Spanish - Spain" -> "Spanish", "Portuguese - Brazil" -> "Portuguese",
 * "Simplified Chinese" -> "Chinese", "Traditional Chinese" -> "Chinese", etc.
 */
const NAME_NORMALIZE: Record<string, { flag: string; name: string }> = {
  'spanish - spain':        { flag: 'es', name: 'Spanish' },
  'spanish - latin america':{ flag: 'mx', name: 'Spanish' },
  'portuguese - brazil':    { flag: 'br', name: 'Portuguese' },
  'portuguese - portugal':  { flag: 'pt', name: 'Portuguese' },
  'portuguese (brazil)':    { flag: 'br', name: 'Portuguese' },
  'simplified chinese':     { flag: 'cn', name: 'Chinese' },
  'traditional chinese':    { flag: 'tw', name: 'Chinese' },
  'chinese (simplified)':   { flag: 'cn', name: 'Chinese' },
  'chinese (traditional)':  { flag: 'tw', name: 'Chinese' },
  'brazilian portuguese':   { flag: 'br', name: 'Portuguese' },
  'english (us)':           { flag: 'us', name: 'English' },
  'english (uk)':           { flag: 'gb', name: 'English' },
  'english - united states':{ flag: 'us', name: 'English' },
  'french - france':        { flag: 'fr', name: 'French' },
  'german - germany':       { flag: 'de', name: 'German' },
  'italian - italy':        { flag: 'it', name: 'Italian' },
  'russian - russia':       { flag: 'ru', name: 'Russian' },
  'japanese - japan':       { flag: 'jp', name: 'Japanese' },
  'korean - korea':         { flag: 'kr', name: 'Korean' },
  'polish - poland':        { flag: 'pl', name: 'Polish' },
  'dutch - netherlands':    { flag: 'nl', name: 'Dutch' },
  'czech - czech republic': { flag: 'cz', name: 'Czech' },
  'hungarian - hungary':    { flag: 'hu', name: 'Hungarian' },
  'romanian - romania':     { flag: 'ro', name: 'Romanian' },
  'turkish - turkey':       { flag: 'tr', name: 'Turkish' },
  'swedish - sweden':       { flag: 'se', name: 'Swedish' },
  'finnish - finland':      { flag: 'fi', name: 'Finnish' },
  'danish - denmark':       { flag: 'dk', name: 'Danish' },
  'norwegian - norway':     { flag: 'no', name: 'Norwegian' },
  'arabic - saudi arabia':  { flag: 'sa', name: 'Arabic' },
  'thai - thailand':        { flag: 'th', name: 'Thai' },
  'greek - greece':         { flag: 'gr', name: 'Greek' },
  'ukrainian - ukraine':    { flag: 'ua', name: 'Ukrainian' },
  'slovak - slovakia':      { flag: 'sk', name: 'Slovak' },
  'hebrew - israel':        { flag: 'il', name: 'Hebrew' },
  // Native language names (GOG API returns these as values)
  'deutsch':                { flag: 'de', name: 'German' },
  'français':               { flag: 'fr', name: 'French' },
  'español':                { flag: 'es', name: 'Spanish' },
  'italiano':               { flag: 'it', name: 'Italian' },
  'português':              { flag: 'pt', name: 'Portuguese' },
  'português do brasil':    { flag: 'br', name: 'Portuguese' },
  'polski':                 { flag: 'pl', name: 'Polish' },
  'русский':                { flag: 'ru', name: 'Russian' },
  'Nederlands':             { flag: 'nl', name: 'Dutch' },
  'nederlands':             { flag: 'nl', name: 'Dutch' },
  'čeština':                { flag: 'cz', name: 'Czech' },
  'magyar':                 { flag: 'hu', name: 'Hungarian' },
  'română':                 { flag: 'ro', name: 'Romanian' },
  'slovenčina':             { flag: 'sk', name: 'Slovak' },
  'svenska':                { flag: 'se', name: 'Swedish' },
  'suomi':                  { flag: 'fi', name: 'Finnish' },
  'dansk':                  { flag: 'dk', name: 'Danish' },
  'norsk':                  { flag: 'no', name: 'Norwegian' },
  'türkçe':                 { flag: 'tr', name: 'Turkish' },
  'українська':             { flag: 'ua', name: 'Ukrainian' },
  'العربية':                { flag: 'sa', name: 'Arabic' },
  'ελληνικά':               { flag: 'gr', name: 'Greek' },
  'עברית':                  { flag: 'il', name: 'Hebrew' },
  'ไทย':                    { flag: 'th', name: 'Thai' },
  '日本語':                  { flag: 'jp', name: 'Japanese' },
  '한국어':                  { flag: 'kr', name: 'Korean' },
  '中文':                    { flag: 'cn', name: 'Chinese' },
  '简体中文':                { flag: 'cn', name: 'Chinese' },
  '繁體中文':                { flag: 'tw', name: 'Chinese' },
  '中文(简体)':              { flag: 'cn', name: 'Chinese' },
  '中文(繁體)':              { flag: 'tw', name: 'Chinese' },
  'český':                  { flag: 'cz', name: 'Czech' },
  'español (al)':           { flag: 'mx', name: 'Spanish' },
  'српска':                 { flag: 'rs', name: 'Serbian' },
  'yкраїнська':             { flag: 'ua', name: 'Ukrainian' },
};

/** Simple base-name lookup: "Spanish" -> flag+name from LANG_MAP */
const BASE_NAME_MAP: Record<string, { flag: string; name: string }> = {};
for (const entry of Object.values(LANG_MAP)) {
  const bn = entry.name.toLowerCase();
  if (!BASE_NAME_MAP[bn]) BASE_NAME_MAP[bn] = { flag: entry.flag, name: entry.name };
}

/**
 * Resolve a language code or full name to a LangEntry.
 *
 * The returned `flag` is an ISO 3166-1 alpha-2 country code (lowercase) -
 * empty string means "no flag known", in which case the consuming template
 * should render a fallback (globe glyph or a bordered placeholder).
 */
export function resolveLang(codeOrName: string): { flag: string; name: string } {
  const key = codeOrName.trim();
  // Direct code lookup
  if (LANG_MAP[key]) return { flag: LANG_MAP[key].flag, name: LANG_MAP[key].name };
  const lc = key.toLowerCase();
  if (LANG_MAP[lc]) return { flag: LANG_MAP[lc].flag, name: LANG_MAP[lc].name };
  // Full name normalization ("Spanish - Spain" -> Spanish)
  if (NAME_NORMALIZE[lc]) return NAME_NORMALIZE[lc];
  // Base name match ("Spanish" -> flag)
  if (BASE_NAME_MAP[lc]) return BASE_NAME_MAP[lc];
  // Strip " - Country" suffix and try again
  const stripped = lc.replace(/\s*[-–]\s*.+$/, '').trim();
  if (stripped !== lc && BASE_NAME_MAP[stripped]) return BASE_NAME_MAP[stripped];
  // Fallback - empty flag code, original key as name
  return { flag: '', name: key };
}

/**
 * Build deduplicated language list from a languages object (codes or names).
 * Handles both { "en": "English" } (GOG) and { "English": "" } or ["English"] formats.
 * Groups variants: Portuguese (Brazil) + Portuguese = Portuguese, etc.
 */
export function buildLanguageList(languages: Record<string, unknown> | string[] | null | undefined): { flag: string; name: string }[] {
  if (!languages) return [];

  // Collect all language identifiers (try both keys and values)
  const raw: string[] = [];
  if (Array.isArray(languages)) {
    raw.push(...languages.map(String));
  } else if (typeof languages === 'object') {
    for (const [k, v] of Object.entries(languages)) {
      // If value is a non-empty string and key looks like a code, use both
      // If key looks like a full name ("English"), use key
      raw.push(k);
      if (typeof v === 'string' && v.trim() && v !== k) raw.push(v);
    }
  }
  if (raw.length === 0) return [];

  const seen = new Set<string>();
  const result: { flag: string; name: string }[] = [];

  for (const item of raw) {
    const resolved = resolveLang(item);
    // Deduplicate by normalized name (Portuguese, Chinese, English, etc.)
    const dedup = resolved.name.toLowerCase();
    if (seen.has(dedup)) continue;
    seen.add(dedup);
    result.push(resolved);
  }

  return result;
}
