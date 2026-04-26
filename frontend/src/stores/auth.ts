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

  /**
   * Attempt a password login.
   *
   * Returns either a final login (tokens already stored, user fetched) or a
   * "needs TOTP" handoff carrying a short-lived challenge token. The Login
   * view checks the return value to decide whether to redirect or render the
   * 6-digit code prompt.
   */
  async function login(
    username: string,
    password: string,
  ): Promise<{ requires_totp: boolean; challenge_token?: string }> {
    const { data } = await client.post("/auth/login", { username, password });
    if (data.requires_totp) {
      return { requires_totp: true, challenge_token: data.challenge_token };
    }
    token.value = data.access_token;
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    await fetchUser();
    await _reopenSocket();
    return { requires_totp: false };
  }

  /**
   * Complete a TOTP-gated login with a 6-digit code or a recovery code.
   * Throws on invalid code (caller surfaces the error).
   */
  async function loginTotp(challengeToken: string, code: string) {
    const { data } = await client.post("/auth/login-totp", {
      challenge_token: challengeToken,
      code,
    });
    token.value = data.access_token;
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    await fetchUser();
    await _reopenSocket();
  }

  async function _reopenSocket() {
    try {
      const { useSocketStore } = await import("@/stores/socket");
      useSocketStore().reconnectWithFreshToken();
    } catch { /* socket store optional */ }
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
    await _reopenSocket();
  }

  function logout() {
    token.value = "";
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    // Drop the WebSocket so the next user gets a fresh handshake
    import("@/stores/socket").then(m => m.useSocketStore().disconnect()).catch(() => {});
  }

  return { token, user, isAuthenticated, isAdmin, login, loginTotp, loginWithTokens, fetchUser, logout };
});
