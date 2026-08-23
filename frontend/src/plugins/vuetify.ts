import "vuetify/styles";
import { createVuetify } from "vuetify";
import { VApp, VBtn, VSnackbar } from "vuetify/components";
import * as directives from "vuetify/directives";

/**
 * Three components, named. The whole library used to be handed to
 * createVuetify through a barrel import to render exactly these: <v-app> in
 * App.vue, and a snackbar with a text button in NotificationSnackbar.vue.
 * Those are the only <v-*> tags in the app, and there are none at all in the
 * Neon Horizon or Vapor sources.
 *
 * VSnackbar pulls the overlay and defaults-provider it needs through its own
 * graph, so they do not need naming here.
 *
 * The stylesheet is deliberately left whole: `vuetify/styles` is compiled
 * all-or-nothing and trimming it needs a build plugin this project does not
 * have. Roughly a hundred kilobytes of CSS stays; this is about the JavaScript.
 *
 * Directives also stay. All three layouts define their own click-outside
 * locally, so Vuetify's are provably unused by us - but they cost very little
 * and a third-party plugin could reasonably reach for v-ripple.
 *
 * A theme plugin that used some other <v-*> tag would stop finding it. None
 * does, and both shipping themes were checked, but it is a narrowing of the
 * global component set and is written down in HOOKS.md as such.
 */
export const vuetify = createVuetify({
  components: { VApp, VBtn, VSnackbar },
  directives,
  theme: {
    defaultTheme: "dark",
    themes: {
      dark: {
        dark: true,
        colors: {
          primary: "#7c4dff",
          secondary: "#424242",
          accent: "#7c4dff",
          error: "#ff5252",
          info: "#2196f3",
          success: "#4caf50",
          warning: "#ffc107",
          background: "#0d0d0d",
          surface: "#1a1a2e",
        },
      },
    },
  },
  defaults: {
    VBtn: { variant: "flat", rounded: "lg" },
    VCard: { rounded: "lg", elevation: 0 },
    VTextField: { variant: "outlined", density: "comfortable" },
  },
});
