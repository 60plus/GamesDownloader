// Shared open/close state for the About dialog. Module-level so every layout
// (built-in or theme-plugin via __GD__.ui.openAbout) drives the same instance
// mounted once in App.vue.
import { ref } from "vue";

export const aboutOpen = ref(false);

export function openAbout(): void {
  aboutOpen.value = true;
}

export function closeAbout(): void {
  aboutOpen.value = false;
}
