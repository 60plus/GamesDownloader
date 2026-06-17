<script lang="ts">
/**
 * Renders the VALUE content of a plugin-registered detail row
 * (window.__GD__.registerDetailRow). The native row container - Modern
 * `.gd-dk`/`.gd-dv`, Classic `.icard-row` - is rendered by the host detail
 * view so it keeps the theme's own scoped styling; this component only fills
 * the value cell.
 *
 * Supports the full declarative segment vocabulary (text / badge / icon / bar /
 * link / image / sep), an optional expandable details section, and a
 * `render(el, ctx)` escape hatch for unlimited custom content. A render
 * function (not a template) so the per-segment renderer is shared between the
 * main value and the detail lines.
 */
import { defineComponent, h, ref, watch, onBeforeUnmount, type PropType, type VNode } from "vue";
import type { DetailSegment, ResolvedDetailRow } from "../../themes/index";

function gd(): any {
  return (window as any).__GD__;
}
function tr(key: string, fallback?: string): string {
  const fb = fallback ?? key;
  try {
    const g = gd();
    return g && g.i18n && g.i18n.t ? g.i18n.t(key, fb) : fb;
  } catch {
    return fb;
  }
}

function maskStyle(icon: string, color?: string, size?: number): Record<string, string> {
  const m = `url("${icon}") center / contain no-repeat`;
  const px = (size || 16) + "px";
  return {
    "-webkit-mask": m,
    mask: m,
    "background-color": color || "currentColor",
    width: px,
    height: px,
  };
}

export default defineComponent({
  name: "PluginDetailValue",
  props: {
    row: { type: Object as PropType<ResolvedDetailRow>, required: true },
    game: { type: Object as PropType<Record<string, unknown>>, required: true },
    library: { type: String, default: "games" },
    variant: { type: String, default: "dlist" },
  },
  setup(props) {
    const expanded = ref(false);

    // Escape-hatch lifecycle: mount the plugin's render() into a host element,
    // re-running when the row or game changes, cleaning up on unmount.
    let mountEl: HTMLElement | null = null;
    let cleanup: (() => void) | null = null;

    function runRender() {
      if (!mountEl || typeof props.row.render !== "function") return;
      if (cleanup) {
        try { cleanup(); } catch { /* ignore */ }
        cleanup = null;
      }
      mountEl.innerHTML = "";
      try {
        const ret = props.row.render(mountEl, {
          game: props.game,
          library: props.library,
          variant: props.variant,
          t: tr,
          api: gd() && gd().api,
        });
        if (typeof ret === "function") cleanup = ret;
      } catch { /* plugin render failed - leave the cell empty */ }
    }

    function setMount(el: any) {
      mountEl = (el as HTMLElement) || null;
      if (mountEl) runRender();
    }

    watch(
      () => [props.row.id, (props.game as any)?.id],
      () => { if (mountEl) runRender(); },
    );
    onBeforeUnmount(() => {
      if (cleanup) { try { cleanup(); } catch { /* ignore */ } }
    });

    function segStyle(seg: DetailSegment): Record<string, string> {
      const s: Record<string, string> = { ...(seg.style || {}) };
      if (seg.muted) s.color = "var(--muted)";
      else if (seg.color) s.color = seg.color;
      if (seg.bold) s["font-weight"] = "700";
      return s;
    }

    function renderSeg(seg: DetailSegment, key: string | number): VNode {
      const type = seg.type || "text";
      const clickable = typeof seg.onClick === "function";
      const on = clickable ? { onClick: seg.onClick, role: "button", tabindex: 0 } : {};

      if (type === "sep") {
        return h("span", { key, class: "gd-pdr-sep" });
      }
      if (type === "image") {
        return h("img", {
          key,
          class: "gd-pdr-img",
          src: seg.src,
          alt: seg.text || "",
          title: seg.title,
          style: { height: (seg.size || 16) + "px" },
        });
      }
      if (type === "icon") {
        return h("span", {
          key,
          class: ["gd-pdr-ic", seg.class],
          title: seg.title,
          style: maskStyle(seg.icon || "", seg.color, seg.size),
        });
      }
      if (type === "bar") {
        const pct = Math.max(0, Math.min(1, seg.value ?? 0)) * 100;
        return h("span", { key, class: "gd-pdr-bar", title: seg.title }, [
          h("span", { class: "gd-pdr-bar-fill", style: { width: pct + "%", background: seg.color || "var(--pl)" } }),
        ]);
      }
      if (type === "link") {
        return h(
          "a",
          { key, class: ["gd-pdr-link", seg.class], href: seg.href, target: "_blank", rel: "noopener", title: seg.title, style: segStyle(seg) },
          seg.text,
        );
      }
      const inner: VNode[] = [];
      if (seg.icon) {
        inner.push(h("span", { class: "gd-pdr-ic gd-pdr-ic--inline", style: maskStyle(seg.icon, seg.color, seg.size || 14) }));
      }
      if (seg.text != null) inner.push(h("span", { class: "gd-pdr-t" }, seg.text));

      if (type === "badge") {
        const style: Record<string, string> = { ...(seg.style || {}) };
        if (seg.color) style.color = seg.color;
        if (seg.bg) style.background = seg.bg;
        return h("span", { key, class: ["gd-pdr-badge", { "gd-pdr-clk": clickable }, seg.class], title: seg.title, style, ...on }, inner);
      }
      // default: text
      return h("span", { key, class: ["gd-pdr-txt", { "gd-pdr-clk": clickable }, seg.class], title: seg.title, style: segStyle(seg), ...on }, inner);
    }

    return () => {
      const row = props.row;

      // Escape hatch wins.
      if (typeof row.render === "function") {
        return h("span", { class: "gd-pdr-mount", ref: setMount });
      }

      const children: VNode[] = [];
      const segs = row.segments || [];
      children.push(h("span", { class: "gd-pdr-val" }, segs.map((s, i) => renderSeg(s, i))));

      const details = row.details;
      if (details && details.items && details.items.length) {
        children.push(
          h(
            "button",
            {
              type: "button",
              class: "gd-pdr-toggle",
              "aria-expanded": expanded.value ? "true" : "false",
              onClick: () => { expanded.value = !expanded.value; },
            },
            expanded.value
              ? tr("detail.hide_details", "Hide details")
              : details.toggleLabel || tr("detail.show_details", "Show details"),
          ),
        );
        if (expanded.value) {
          children.push(
            h(
              "div",
              { class: "gd-pdr-details" },
              details.items.map((line, li) =>
                h("div", { class: "gd-pdr-dline", key: li }, line.map((s, si) => renderSeg(s, si))),
              ),
            ),
          );
        }
      }
      return h("span", { class: "gd-pdr-wrap" }, children);
    };
  },
});
</script>

<style scoped>
.gd-pdr-wrap {
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  max-width: 100%;
}
.gd-pdr-val {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.gd-pdr-txt,
.gd-pdr-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.gd-pdr-link { text-decoration: none; }
.gd-pdr-link:hover { text-decoration: underline; }
.gd-pdr-clk { cursor: pointer; }

.gd-pdr-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text, #fff) 8%, transparent);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, .12));
  white-space: nowrap;
}

/* Masked icon recolored via background-color. */
.gd-pdr-ic {
  display: inline-block;
  flex: 0 0 auto;
  background-color: currentColor;
}
.gd-pdr-ic--inline { width: 14px; height: 14px; }

.gd-pdr-img { display: inline-block; object-fit: contain; vertical-align: middle; border-radius: 3px; }

.gd-pdr-sep {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--muted);
  opacity: .5;
  flex: 0 0 auto;
}

.gd-pdr-bar {
  position: relative;
  display: inline-block;
  width: 90px;
  height: 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text, #fff) 12%, transparent);
  overflow: hidden;
  vertical-align: middle;
}
.gd-pdr-bar-fill { position: absolute; inset: 0 auto 0 0; border-radius: 999px; }

/* "Show details" expander - glass per house style. */
.gd-pdr-toggle {
  align-self: flex-start;
  padding: 2px 8px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
  background: color-mix(in srgb, var(--pl, #7c3aed) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl, #7c3aed) 30%, transparent);
  border-radius: var(--radius-xs, 4px);
  cursor: pointer;
  white-space: nowrap;
}
.gd-pdr-toggle:hover { background: color-mix(in srgb, var(--pl, #7c3aed) 24%, transparent); }

.gd-pdr-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--text, #fff) 4%, transparent);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, .12));
  border-radius: var(--radius-sm, 6px);
}
.gd-pdr-dline {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12.5px;
  line-height: 1.4;
}
</style>
