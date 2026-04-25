import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";

export const vuetify = createVuetify({
  components,
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
