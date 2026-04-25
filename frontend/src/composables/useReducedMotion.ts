/**
 * Reactive read of the user's `prefers-reduced-motion` setting.
 *
 * Use this when you have a JS-driven animation (auto-rotating carousel,
 * setInterval-based timer, RAF loop) that CSS alone cannot stop. CSS
 * animations are already neutralised globally in `styles/base.css`.
 *
 * Example:
 *   const reduceMotion = useReducedMotion();
 *   if (reduceMotion.value) clearInterval(carouselTimer);
 */
import { onBeforeUnmount, ref } from "vue";

export function useReducedMotion() {
  const prefers = ref(false);

  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    prefers.value = mq.matches;

    const onChange = (e: MediaQueryListEvent) => {
      prefers.value = e.matches;
    };

    // Older Safari uses addListener / removeListener (deprecated since 14)
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
      onBeforeUnmount(() => mq.removeEventListener("change", onChange));
    } else {
      // Fallback for very old browsers - signature is the same listener
      type LegacyListener = (this: MediaQueryList, ev: MediaQueryListEvent) => unknown;
      const legacy = mq as unknown as {
        addListener?:    (l: LegacyListener) => void;
        removeListener?: (l: LegacyListener) => void;
      };
      legacy.addListener?.(onChange as unknown as LegacyListener);
      onBeforeUnmount(() => legacy.removeListener?.(onChange as unknown as LegacyListener));
    }
  }

  return prefers;
}
