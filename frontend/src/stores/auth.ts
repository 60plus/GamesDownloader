import { defineStore } from "pinia";
import { ref, computed } from "vue";
import client from "@/services/api/client";
import { useThemeStore } from "@/stores/theme";

const TOKEN_KEY = "gd3_token";
const REFRESH_KEY = "gd3_refresh";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || "");
  const user = ref<Record<string, unknown> | null>(null);

  const isAuthenticated = computed(() => !!token.value);
  const isAdmin = computed(() => user.value?.role === "admin");

  async function login(username: string, password: string) {
    const { data } = await client.post("/auth/login", { username, password });
    token.value = data.access_token;
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    await fetchUser();
  }

  async function fetchUser() {
    try {
      const { data } = await client.get("/users/me");
      user.value = data;
      // Load per-user appearance preferences
      if (data.preferences && typeof data.preferences === "object") {
        const themeStore = useThemeStore();
        themeStore.loadPreferences(data.preferences as Record<string, unknown>);
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        // Token is invalid or expired - clear session so user is sent to login
        logout();
      } else {
        // Network error or server issue - don't force logout, keep existing state
        user.value = null;
      }
    }
  }

  async function loginWithTokens(accessToken: string, refreshToken: string) {
    token.value = accessToken;
    localStorage.setItem(TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_KEY, refreshToken);
    await fetchUser();
  }

  function logout() {
    token.value = "";
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  return { token, user, isAuthenticated, isAdmin, login, loginWithTokens, fetchUser, logout };
});
