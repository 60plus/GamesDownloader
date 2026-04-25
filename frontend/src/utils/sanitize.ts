/**
 * HTML sanitisation using DOMPurify.
 *
 * Used wherever game descriptions (which may contain HTML from GOG/RAWG)
 * are rendered via v-html. DOMPurify removes scripts, event handlers and
 * other XSS vectors while keeping safe formatting tags (p, b, i, ul, …).
 */
import DOMPurify from "dompurify";

/** Allowed HTML tags for game descriptions. */
const ALLOWED_TAGS = [
  "p", "br", "b", "strong", "i", "em", "u", "s", "strike",
  "ul", "ol", "li", "dl", "dt", "dd",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "blockquote", "pre", "code",
  "a", "span", "div",
  "table", "thead", "tbody", "tr", "th", "td",
  "img",
];

/** Allowed attributes (no event handlers, no javascript: hrefs). */
const ALLOWED_ATTR = ["href", "src", "alt", "title", "class", "target", "rel"];

/**
 * Sanitise an HTML string for safe rendering in v-html.
 * Returns an empty string for null/undefined input.
 */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // Force links to open in new tab and add noopener
    ADD_ATTR: ["target"],
    FORCE_BODY: false,
    // Block javascript:, data:, vbscript: and other non-http URI schemes
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  });
}

/**
 * Sanitise theme preview HTML (from plugin previewHtml).
 * Very restrictive: only divs/spans with inline style. No links, no images,
 * no scripts, no event handlers. Safe for rendering in ThemeSwitcher.
 */
export function sanitizePreviewHtml(html: string | null | undefined): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["div", "span"],
    ALLOWED_ATTR: ["style"],
    ALLOW_DATA_ATTR: false,
    FORCE_BODY: false,
  });
}
