import { defineStore } from "pinia";
import { ref, computed } from "vue";
import client from "@/services/api/client";
import { useThemeStore } from "@/stores/theme";
import { useLibrariesStore } from "@/stores/libraries";
import { useCollectionsStore } from "@/stores/collections";

const TOKEN_KEY = "gd3_token";
const REFRESH_KEY = "gd3_refresh";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || "");
  const user = ref<Record<string, unknown> | null>(null);

  const isAuthenticated = computed(() => !!token.value);
  const isAdmin = computed(() => user.value?.role === "admin");

  /**
   * What this account effectively holds, role and per-account chips together.
   *
   * The skins can only see the role and the overrides, so every screen that
   * asks a permission question has to work this out - and each of them working
   * it out separately is how they came to disagree. `canUseStores` below read
   * the role and the store chip and never the upload chip, though
   * `_PERM_REVOKE` takes LIBRARY_UPLOAD away without touching the role and
   * every store route requires it: an account with the upload chip switched
   * off was offered a storefront that then refuses it.
   *
   * Mirrors the server's two tables. A chip set to `false` REVOKES, which is
   * not the same as an absent key; a chip set to `true` GRANTS, which can hand
   * a scope to a role that does not have it by default. Those two distinctions
   * are the whole of the mapping.
   */
  function heldScopes(u: { role?: string; permissions?: Record<string, unknown> } | null) {
    const p = (u?.permissions || {}) as Record<string, unknown>;
    const role = u?.role;
    return {
      // In UPLOADER_SCOPES, so an uploader and an admin have it by role.
      upload: p.upload === true
        || ((role === "admin" || role === "uploader") && p.upload !== false),
      // Held by default only by an admin; everybody else is granted it one
      // account at a time, which is what "an admin hands out store access" means.
      store: p.store_access === true || (role === "admin" && p.store_access !== false),
      // ROMS_READ is in USER_SCOPES, so everybody has it until it is revoked.
      emulation: p.access_emulation !== false,
    };
  }

  /**
   * Whether this account may fetch new content onto the server from a store
   * plugin. Not the same question as which libraries it can see: that is
   * curation and lives in Settings > Libraries.
   *
   * The server decides this by requiring two permissions on every store route,
   * the upload one and the store one, so an account that cannot upload is
   * refused whatever the switch says. The same shape is spelled out here
   * because a skin has only the role and the overrides to work from, and the
   * three skins that draw this screen each keep their own copy of it. One
   * sentence in one place is what stops them disagreeing.
   */
  const canUseStores = computed(() => {
    const u = user.value as { role?: string; permissions?: Record<string, unknown> } | null;
    if (!u) return false;
    const held = heldScopes(u);
    return held.upload && held.store;
  });

  /**
   * Whether to show this account the transfer tray.
   *
   * Written once here for the same reason as `canUseStores` above: four
   * layouts draw this tray - the two built-in ones and both themes - and each
   * of them was asking `role === "admin"`. The server had already decided
   * otherwise: `GET /rom-sources/downloads` admits an uploader and narrows the
   * answer to the jobs that account started. So the one account the route was
   * narrowed FOR could not see a tray at all, and could not tell whether their
   * own download was still running.
   *
   * All three permissions the route lists, OVERRIDES INCLUDED. `_PERM_REVOKE`
   * can take a scope away without touching the role - `upload` removes
   * LIBRARY_UPLOAD, `access_emulation` removes ROMS_READ - so reading the role
   * alone would offer a tray the route then refuses, which is the same
   * bar-that-cannot-be-filled this release spent a round removing.
   */
  const canSeeTransfers = computed(() => {
    const u = user.value as { role?: string; permissions?: Record<string, unknown> } | null;
    if (!u) return false;
    const held = heldScopes(u);
    // The store's two, plus the emulation one: fetching a ROM onto the server
    // is an emulation act, and `GET /rom-sources/downloads` says so by naming
    // ROMS_READ alongside the other two.
    return held.upload && held.store && held.emulation;
  });

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
      // Refresh the data-driven library registry now that we're authenticated.
      useLibrariesStore().fetch();
      useCollectionsStore().fetch();
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

  return { token, user, isAuthenticated, isAdmin, canUseStores, canSeeTransfers, login, loginTotp, loginWithTokens, fetchUser, logout };
});
