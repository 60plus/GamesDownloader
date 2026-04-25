/**
 * Shared language code → flag + display name mapping.
 * Used by GOG Detail, Games Detail, Classic Detail for consistent language display.
 *
 * Normalization groups (deduplication):
 *   Portuguese (Brazil) + Portuguese → Portuguese
 *   Chinese (Simplified) + Chinese (Traditional) → Chinese
 *   English (US) + English → English
 *   Spanish (Latin America) + Spanish → Spanish
 */

export interface LangEntry {
  flag: string;
  name: string;
  /** If set, this code is a variant of `group` - deduplicated to group in simplified display */
  group?: string;
}

export const LANG_MAP: Record<string, LangEntry> = {
  en:       { flag: '🇬🇧', name: 'English' },
  'en-US':  { flag: '🇺🇸', name: 'English (US)', group: 'en' },
  pl:       { flag: '🇵🇱', name: 'Polish' },
  de:       { flag: '🇩🇪', name: 'German' },
  fr:       { flag: '🇫🇷', name: 'French' },
  es:       { flag: '🇪🇸', name: 'Spanish' },
  'es-419': { flag: '🇲🇽', name: 'Spanish (Latin America)', group: 'es' },
  it:       { flag: '🇮🇹', name: 'Italian' },
  ru:       { flag: '🇷🇺', name: 'Russian' },
  cn:       { flag: '🇨🇳', name: 'Chinese', group: 'zh-group' },    // GOG code
  zh:       { flag: '🇨🇳', name: 'Chinese', group: 'zh-group' },    // GOG code
  'zh-Hans':{ flag: '🇨🇳', name: 'Chinese', group: 'zh-group' },    // ISO
  'zh-Hant':{ flag: '🇹🇼', name: 'Chinese', group: 'zh-group' },    // ISO
  jp:       { flag: '🇯🇵', name: 'Japanese' },   // GOG code
  ja:       { flag: '🇯🇵', name: 'Japanese', group: 'jp' },   // ISO
  ko:       { flag: '🇰🇷', name: 'Korean' },
  pt:       { flag: '🇵🇹', name: 'Portuguese' },
  br:       { flag: '🇧🇷', name: 'Portuguese', group: 'pt' }, // GOG code
  'pt-BR':  { flag: '🇧🇷', name: 'Portuguese', group: 'pt' }, // ISO
  nl:       { flag: '🇳🇱', name: 'Dutch' },
  cz:       { flag: '🇨🇿', name: 'Czech' },  // GOG code
  cs:       { flag: '🇨🇿', name: 'Czech', group: 'cz' },  // ISO
  hu:       { flag: '🇭🇺', name: 'Hungarian' },
  ro:       { flag: '🇷🇴', name: 'Romanian' },
  sk:       { flag: '🇸🇰', name: 'Slovak' },
  sv:       { flag: '🇸🇪', name: 'Swedish' },
  fi:       { flag: '🇫🇮', name: 'Finnish' },
  da:       { flag: '🇩🇰', name: 'Danish' },
  no:       { flag: '🇳🇴', name: 'Norwegian' },
  tr:       { flag: '🇹🇷', name: 'Turkish' },
  uk:       { flag: '🇺🇦', name: 'Ukrainian' },
  ar:       { flag: '🇸🇦', name: 'Arabic' },
  el:       { flag: '🇬🇷', name: 'Greek' },
  he:       { flag: '🇮🇱', name: 'Hebrew' },
  th:       { flag: '🇹🇭', name: 'Thai' },
  // GOG non-standard codes
  es_mx:    { flag: '🇲🇽', name: 'Spanish', group: 'es' },
  gk:       { flag: '🇬🇷', name: 'Greek',   group: 'el' },
  sb:       { flag: '🇷🇸', name: 'Serbian' },
};

/**
 * Normalize full language names to simplified base form.
 * "Spanish - Spain" → "Spanish", "Portuguese - Brazil" → "Portuguese",
 * "Simplified Chinese" → "Chinese", "Traditional Chinese" → "Chinese", etc.
 */
const NAME_NORMALIZE: Record<string, { flag: string; name: string }> = {
  'spanish - spain':        { flag: '🇪🇸', name: 'Spanish' },
  'spanish - latin america':{ flag: '🇲🇽', name: 'Spanish' },
  'portuguese - brazil':    { flag: '🇧🇷', name: 'Portuguese' },
  'portuguese - portugal':  { flag: '🇵🇹', name: 'Portuguese' },
  'portuguese (brazil)':    { flag: '🇧🇷', name: 'Portuguese' },
  'simplified chinese':     { flag: '🇨🇳', name: 'Chinese' },
  'traditional chinese':    { flag: '🇹🇼', name: 'Chinese' },
  'chinese (simplified)':   { flag: '🇨🇳', name: 'Chinese' },
  'chinese (traditional)':  { flag: '🇹🇼', name: 'Chinese' },
  'brazilian portuguese':   { flag: '🇧🇷', name: 'Portuguese' },
  'english (us)':           { flag: '🇺🇸', name: 'English' },
  'english (uk)':           { flag: '🇬🇧', name: 'English' },
  'english - united states':{ flag: '🇺🇸', name: 'English' },
  'french - france':        { flag: '🇫🇷', name: 'French' },
  'german - germany':       { flag: '🇩🇪', name: 'German' },
  'italian - italy':        { flag: '🇮🇹', name: 'Italian' },
  'russian - russia':       { flag: '🇷🇺', name: 'Russian' },
  'japanese - japan':       { flag: '🇯🇵', name: 'Japanese' },
  'korean - korea':         { flag: '🇰🇷', name: 'Korean' },
  'polish - poland':        { flag: '🇵🇱', name: 'Polish' },
  'dutch - netherlands':    { flag: '🇳🇱', name: 'Dutch' },
  'czech - czech republic': { flag: '🇨🇿', name: 'Czech' },
  'hungarian - hungary':    { flag: '🇭🇺', name: 'Hungarian' },
  'romanian - romania':     { flag: '🇷🇴', name: 'Romanian' },
  'turkish - turkey':       { flag: '🇹🇷', name: 'Turkish' },
  'swedish - sweden':       { flag: '🇸🇪', name: 'Swedish' },
  'finnish - finland':      { flag: '🇫🇮', name: 'Finnish' },
  'danish - denmark':       { flag: '🇩🇰', name: 'Danish' },
  'norwegian - norway':     { flag: '🇳🇴', name: 'Norwegian' },
  'arabic - saudi arabia':  { flag: '🇸🇦', name: 'Arabic' },
  'thai - thailand':        { flag: '🇹🇭', name: 'Thai' },
  'greek - greece':         { flag: '🇬🇷', name: 'Greek' },
  'ukrainian - ukraine':    { flag: '🇺🇦', name: 'Ukrainian' },
  'slovak - slovakia':      { flag: '🇸🇰', name: 'Slovak' },
  'hebrew - israel':        { flag: '🇮🇱', name: 'Hebrew' },
  // Native language names (GOG API returns these as values)
  'deutsch':                { flag: '🇩🇪', name: 'German' },
  'français':               { flag: '🇫🇷', name: 'French' },
  'español':                { flag: '🇪🇸', name: 'Spanish' },
  'italiano':               { flag: '🇮🇹', name: 'Italian' },
  'português':              { flag: '🇵🇹', name: 'Portuguese' },
  'português do brasil':    { flag: '🇧🇷', name: 'Portuguese' },
  'polski':                 { flag: '🇵🇱', name: 'Polish' },
  'русский':                { flag: '🇷🇺', name: 'Russian' },
  'Nederlands':             { flag: '🇳🇱', name: 'Dutch' },
  'nederlands':              { flag: '🇳🇱', name: 'Dutch' },
  'čeština':                { flag: '🇨🇿', name: 'Czech' },
  'magyar':                 { flag: '🇭🇺', name: 'Hungarian' },
  'română':                 { flag: '🇷🇴', name: 'Romanian' },
  'slovenčina':             { flag: '🇸🇰', name: 'Slovak' },
  'svenska':                { flag: '🇸🇪', name: 'Swedish' },
  'suomi':                  { flag: '🇫🇮', name: 'Finnish' },
  'dansk':                  { flag: '🇩🇰', name: 'Danish' },
  'norsk':                  { flag: '🇳🇴', name: 'Norwegian' },
  'türkçe':                 { flag: '🇹🇷', name: 'Turkish' },
  'українська':             { flag: '🇺🇦', name: 'Ukrainian' },
  'العربية':                { flag: '🇸🇦', name: 'Arabic' },
  'ελληνικά':               { flag: '🇬🇷', name: 'Greek' },
  'עברית':                  { flag: '🇮🇱', name: 'Hebrew' },
  'ไทย':                    { flag: '🇹🇭', name: 'Thai' },
  '日本語':                  { flag: '🇯🇵', name: 'Japanese' },
  '한국어':                  { flag: '🇰🇷', name: 'Korean' },
  '中文':                    { flag: '🇨🇳', name: 'Chinese' },
  '简体中文':                { flag: '🇨🇳', name: 'Chinese' },
  '繁體中文':                { flag: '🇹🇼', name: 'Chinese' },
  '中文(简体)':              { flag: '🇨🇳', name: 'Chinese' },
  '中文(繁體)':              { flag: '🇹🇼', name: 'Chinese' },
  'český':                  { flag: '🇨🇿', name: 'Czech' },
  'español (al)':           { flag: '🇲🇽', name: 'Spanish' },
  'српска':                 { flag: '🇷🇸', name: 'Serbian' },
  'yкраїнська':             { flag: '🇺🇦', name: 'Ukrainian' },
};

/** Simple base-name lookup: "Spanish" → flag+name from LANG_MAP */
const BASE_NAME_MAP: Record<string, { flag: string; name: string }> = {};
for (const entry of Object.values(LANG_MAP)) {
  const bn = entry.name.toLowerCase();
  if (!BASE_NAME_MAP[bn]) BASE_NAME_MAP[bn] = { flag: entry.flag, name: entry.name };
}

/**
 * Resolve a language code or full name to a LangEntry.
 */
export function resolveLang(codeOrName: string): { flag: string; name: string } {
  const key = codeOrName.trim();
  // Direct code lookup
  if (LANG_MAP[key]) return { flag: LANG_MAP[key].flag, name: LANG_MAP[key].name };
  const lc = key.toLowerCase();
  if (LANG_MAP[lc]) return { flag: LANG_MAP[lc].flag, name: LANG_MAP[lc].name };
  // Full name normalization ("Spanish - Spain" → Spanish)
  if (NAME_NORMALIZE[lc]) return NAME_NORMALIZE[lc];
  // Base name match ("Spanish" → flag)
  if (BASE_NAME_MAP[lc]) return BASE_NAME_MAP[lc];
  // Strip " - Country" suffix and try again
  const stripped = lc.replace(/\s*[-–]\s*.+$/, '').trim();
  if (stripped !== lc && BASE_NAME_MAP[stripped]) return BASE_NAME_MAP[stripped];
  // Fallback
  return { flag: '🌐', name: key };
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
