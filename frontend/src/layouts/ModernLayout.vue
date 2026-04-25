<template>
  <div class="shell-modern">
    <ambient-background />

    <!-- ── Top Navbar ──────────────────────────────────────────────────── -->
    <nav class="navbar glass">
      <div class="navbar-left">
        <router-link to="/" class="navbar-logo">
          <div class="logo-glow" />
          <img src="/GDLOGO.png" class="logo-img" alt="GamesDownloaderV3" />
        </router-link>
      </div>

      <div class="navbar-center">
        <div class="search-wrap" :class="{ focused: searchFocused }">
          <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
          <input
            v-model="searchQuery"
            class="search-input"
            :placeholder="t('nav.search')"
            @focus="searchFocused = true"
            @blur="searchFocused = false"
          />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">×</button>
        </div>
        <RandomGamePicker />
      </div>

      <div class="navbar-right">
        <!-- User chip -->
        <div class="user-chip-wrap" @click="showUserMenu = !showUserMenu" v-click-outside="() => showUserMenu = false">
          <div class="user-chip">
            <img v-if="avatarSrc" :src="avatarSrc" class="user-avatar-img" alt="Avatar" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
            <div v-else class="user-avatar-placeholder">{{ initials }}</div>
            <span v-if="notifStore.hasBadge" class="user-chip-badge" @click.stop="showNotifPopup = !showNotifPopup">{{ notifStore.totalCount }}</span>
          </div>

          <!-- Notification popup -->
          <transition name="menu-drop">
            <div v-if="showNotifPopup && notifStore.active.length" class="notif-popup glass" v-click-outside="() => showNotifPopup = false">
              <div class="notif-popup-title">{{ t('pstore.updates_badge') }}</div>
              <div v-for="n in notifStore.active" :key="n.id" class="notif-popup-item">
                <div v-if="n.details" class="notif-popup-details">
                  <div v-for="(d, i) in n.details" :key="i" class="notif-popup-detail">{{ d }}</div>
                </div>
                <div class="notif-popup-actions">
                  <button v-if="n.action" class="notif-action" @click="showNotifPopup = false; $router.push(n.action); notifStore.dismiss(n.id)">{{ n.actionLabel }}</button>
                  <button class="notif-dismiss" @click="notifStore.dismiss(n.id)">&times;</button>
                </div>
              </div>
            </div>
          </transition>
          <transition name="menu-drop">
            <div v-if="showUserMenu" class="user-menu glass">
              <div class="user-menu-header">
                <div class="user-menu-avatar">
                  <img v-if="avatarSrc" :src="avatarSrc" class="user-menu-avatar-img" alt="Avatar" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  <div v-else class="user-avatar-placeholder small">{{ initials }}</div>
                </div>
                <div class="user-menu-info">
                  <div class="user-menu-name">{{ auth.user?.username || 'User' }}</div>
                  <div class="user-menu-role">{{ userRole }}</div>
                </div>
              </div>
              <div class="menu-sep" />
              <button class="menu-item" @click="showUserMenu = false; $router.push('/profile')">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                {{ t('nav.profile') }}
              </button>
              <button class="menu-item" @click="showUserMenu = false; $router.push('/settings')">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                {{ t('nav.settings') }}
              </button>
              <div class="menu-sep" />
              <button class="menu-item menu-item--danger" @click="handleLogout">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                {{ t('nav.logout') }}
              </button>
            </div>
          </transition>
        </div>
      </div>
    </nav>

    <!-- ── Sync progress bar ───────────────────────────────────────────── -->
    <div v-if="socketStore.syncProgress.progress > 0 && socketStore.syncProgress.progress < 100" class="sync-topbar">
      <div class="sync-topbar-fill" :style="{ width: socketStore.syncProgress.progress + '%' }" />
    </div>

    <!-- ── Main content ────────────────────────────────────────────────── -->
    <main class="main-content" :class="{ 'main-content--full': $route.meta.fullBleed }">
      <router-view v-slot="{ Component }">
        <template v-if="$route.meta.fullBleed">
          <component :is="Component" :key="$route.path" />
        </template>
        <transition v-else name="page">
          <component :is="Component" :key="$route.path" />
        </transition>
      </router-view>
    </main>
  </div>

  <!-- ── Download Manager tray (fixed bottom-right, admin only) ──────── -->
  <DownloadManager v-if="isAdmin" />
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useSocketStore } from "@/stores/socket";
import AmbientBackground from "@/components/common/AmbientBackground.vue";
import DownloadManager from "@/components/gog/DownloadManager.vue";
import RandomGamePicker from "@/components/RandomGamePicker.vue";
import { useI18n } from "@/i18n";
import { useNotificationStore } from "@/stores/notifications";

const { t } = useI18n();

const auth = useAuthStore();
const notifStore = useNotificationStore();
const showNotifPopup = ref(false);
const socketStore = useSocketStore();
const router = useRouter();
const route  = useRoute();

const searchQuery = ref("");
const searchFocused = ref(false);
const showUserMenu = ref(false);

const initials = computed(() => {
  const name = (auth.user?.username as string) || "?";
  return name.slice(0, 2).toUpperCase();
});

const avatarSrc = computed(() => {
  const p = auth.user?.avatar_path as string | undefined
  if (!p) return ''
  if (p.startsWith('http')) return p
  const filename = p.split(/[\\/]/).pop() || ''
  return filename ? `/resources/avatars/${filename}` : ''
});

const userRole = computed(() => {
  const r = (auth.user?.role as string) || 'viewer'
  return r.charAt(0).toUpperCase() + r.slice(1).toLowerCase()
});

const isAdmin = computed(() => auth.user?.role === 'admin');

// ── Sync navbar searchQuery ↔ route.query.q ─────────────────────────────────
const isLibraryRoute = computed(() =>
  route.path.startsWith("/games") ||
  route.path.startsWith("/library") ||
  route.path.startsWith("/emulation")
);

watch(searchQuery, (q) => {
  if (!isLibraryRoute.value) return;
  const cur = Array.isArray(route.query.q) ? route.query.q[0] : route.query.q;
  if (q !== (cur || "")) {
    router.replace({ query: { ...route.query, q: q || undefined } });
  }
});

watch(() => route.query.q, (q) => {
  const val = (Array.isArray(q) ? q[0] : q) || "";
  if (searchQuery.value !== val) searchQuery.value = val;
}, { immediate: true });

// Clear search when leaving library routes
watch(isLibraryRoute, (is) => {
  if (!is) searchQuery.value = "";
});


function handleLogout() {
  showUserMenu.value = false;
  auth.logout();
  router.push("/login");
}

// Connect WebSocket
socketStore.connect();

// v-click-outside directive
type ElWithHandler = HTMLElement & { _clickOutside?: (e: Event) => void }
const vClickOutside = {
  mounted(el: ElWithHandler, binding: { value: () => void }) {
    el._clickOutside = (e: Event) => {
      if (!el.contains(e.target as Node)) binding.value();
    };
    document.addEventListener("click", el._clickOutside);
  },
  unmounted(el: ElWithHandler) {
    if (el._clickOutside) document.removeEventListener("click", el._clickOutside);
  },
};
</script>

<style scoped>
/* ── Shell ────────────────────────────────────────────────────────────────── */
.shell-modern {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  position: relative;
  background: var(--bg, #0a0618);
  font-family: 'Inter', 'Segoe UI', sans-serif;
  color: var(--text);
}

/* ── Navbar ───────────────────────────────────────────────────────────────── */
.navbar {
  display: flex;
  align-items: center;
  height: 120px;
  padding: 0 28px;
  gap: var(--space-5, 20px);
  flex-shrink: 0;
  z-index: 100;
  position: relative;
  border-top: none;
  border-left: none;
  border-right: none;
  border-radius: 0;
  backdrop-filter: blur(var(--navbar-blur-px, 28px)) saturate(var(--glass-sat, 180%)) !important;
  -webkit-backdrop-filter: blur(var(--navbar-blur-px, 28px)) saturate(var(--glass-sat, 180%)) !important;
  box-shadow: 0 1px 0 var(--glass-border), 0 4px 32px rgba(0,0,0,0.35);
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-5, 20px);
}

/* Logo */
.navbar-logo {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  text-decoration: none;
  position: relative;
  flex-shrink: 0;
}
.logo-glow {
  position: absolute;
  inset: -20px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--pglow) 0%, transparent 65%);
  opacity: calc(0.4 * var(--logo-glow, 1));
  animation: pulse-glow 3s ease-in-out infinite;
  pointer-events: none;
}
.logo-img {
  height: 100px;
  width: auto;
  object-fit: contain;
  position: relative;
  z-index: 1;
  filter: drop-shadow(0 0 calc(10px * var(--logo-glow, 1)) var(--pglow))
          drop-shadow(0 0 calc(24px * var(--logo-glow, 1)) var(--pglow2));
  transition: filter var(--transition);
}
.navbar-logo:hover .logo-img {
  filter: drop-shadow(0 0 calc(16px * var(--logo-glow, 1)) var(--pglow))
          drop-shadow(0 0 calc(40px * var(--logo-glow, 1)) var(--pglow))
          saturate(calc(1 + 0.15 * var(--logo-glow, 1)));
}
.lib-tab-ico-img {
  width: 18px;
  height: 18px;
  object-fit: contain;
  border-radius: 3px;
  flex-shrink: 0;
}

/* Library tabs */
.navbar-libs {
  display: flex;
  gap: 2px;
}
.lib-tab {
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: all var(--transition);
}
.lib-tab:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
}
.lib-tab--active {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text);
  box-shadow: inset 0 -2px 0 var(--lib-color, var(--pl));
}
.lib-tab-ico {
  font-size: var(--fs-md, 14px);
}
.lib-tab-count {
  font-size: var(--fs-xs, 10px);
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--lib-color, var(--pl));
  color: #fff;
}

/* Center - search: absolutely centered in navbar */
.navbar-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
}
.search-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 9px 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  transition: all 0.2s;
  width: 380px;
}
.search-wrap.focused {
  background: rgba(255, 255, 255, 0.09);
  border-color: var(--pl);
  box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15);
}
.search-icon {
  color: var(--muted);
  flex-shrink: 0;
}
.search-input {
  flex: 1;
  font-size: var(--fs-md, 14px);
  color: var(--text);
  background: none;
  border: none;
  outline: none;
}
.search-input::placeholder {
  color: var(--muted);
}
.search-clear {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: var(--fs-lg, 16px);
  padding: 0 2px;
}

/* Right - buttons */
.navbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  margin-left: auto;
}
.nav-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition);
}
.nav-btn:hover {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}
.nav-btn.spinning svg {
  animation: spin 0.8s linear infinite;
}

/* User chip */
.user-chip-wrap {
  position: relative;
}
.user-chip {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 2px solid var(--pl);
  overflow: hidden;
  cursor: pointer;
  box-shadow: 0 0 10px var(--pglow2);
  transition: all 0.15s;
}
.user-chip:hover {
  box-shadow: 0 0 16px var(--pglow);
  transform: scale(1.05);
}
.user-avatar-img {
  width: 100%; height: 100%;
  object-fit: cover; border-radius: 50%; display: block;
}
.user-avatar-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, var(--pl), var(--pl2));
  font-size: var(--fs-md, 14px);
  font-weight: 700;
  color: #fff;
}
.user-avatar-placeholder.small {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-size: 13px;
}
.user-menu-avatar {
  width: 32px; height: 32px;
  border-radius: 50%; overflow: hidden; flex-shrink: 0;
  border: 1px solid var(--glass-border);
}
.user-menu-avatar-img {
  width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 50%;
}

/* User menu */
.user-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 200px;
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.6);
  z-index: 200;
}
.user-menu-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: rgba(124, 58, 237, 0.08);
}
.user-menu-name {
  font-size: var(--fs-md, 14px);
  font-weight: 700;
  color: var(--text);
}
.user-menu-role {
  font-size: 11px;
  color: var(--muted);
  text-transform: capitalize;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 16px;
  font-size: var(--fs-md, 14px);
  font-weight: 600;
  color: var(--text);
  background: none;
  border: none;
  width: 100%;
  cursor: pointer;
  transition: background var(--transition);
}
.menu-item:hover {
  background: rgba(255, 255, 255, 0.06);
}
.menu-item--danger {
  color: var(--danger, #ef4444);
}
.menu-item--danger:hover {
  background: rgba(239, 68, 68, 0.08);
}
.menu-sep {
  height: 1px;
  background: var(--glass-border);
  margin: 2px 0;
}
.menu-theme-inline {
  padding: 4px 8px;
}

/* ── Sync progress bar ───────────────────────────────────────────────────── */
.sync-topbar {
  height: 2px;
  background: rgba(124, 58, 237, 0.15);
  flex-shrink: 0;
}
.sync-topbar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--pl), var(--pl-light));
  box-shadow: 0 0 8px var(--pglow);
  transition: width 0.3s ease;
}

/* ── Main content ────────────────────────────────────────────────────────── */
.main-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* Always reserve scrollbar gutter so viewport width is constant whether
     content overflows or not. Without this, switching cover size (XS -> XL)
     makes the scrollbar appear, narrowing viewport by ~15px, which causes
     .emu-title-right to wrap to a 2nd row and the title-bar to grow taller. */
  scrollbar-gutter: stable;
  display: flex;
  flex-direction: column;
  z-index: 1;
  padding: 20px 28px;
  position: relative;
}
.main-content--full {
  padding: 0;
}

/* ── Mobile ─────────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .navbar {
    height: auto;
    padding: 8px 12px;
    flex-wrap: wrap;
    gap: 6px;
  }
  .navbar-left { flex: 1; }
  .logo-img { height: 44px; }
  .logo-glow { display: none; }
  .navbar-center {
    position: static;
    transform: none;
    width: 100%;
    order: 3;
    flex-basis: 100%;
    padding-bottom: 6px;
    gap: var(--space-2, 8px);
  }
  .search-wrap { width: 100%; }
  .navbar-libs {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .navbar-libs::-webkit-scrollbar { display: none; }
  .lib-tab-count { display: none; }
  .main-content { padding: 10px 12px; }
}
@media (max-width: 430px) {
  .user-chip { width: 44px; height: 44px; }
  .logo-img { height: 34px; }
  .lib-tab { font-size: 11px; padding: 4px 8px; }
}

/* Notification badge on avatar */
.user-chip { position: relative; }
.user-chip-badge {
  position: absolute; inset: 0;
  border-radius: 50%;
  background: rgba(239, 68, 68, .85);
  color: #fff; font-size: var(--fs-2xl, 22px); font-weight: 800;
  display: flex; align-items: center; justify-content: center;
  animation: chip-shake 3s ease-in-out infinite;
  cursor: pointer; z-index: 2;
}
@keyframes chip-shake {
  0%, 88%, 100% { transform: none; }
  90% { transform: rotate(-10deg) scale(1.15); }
  92% { transform: rotate(10deg) scale(1.15); }
  94% { transform: rotate(-6deg); }
  96% { transform: rotate(6deg); }
  98% { transform: rotate(0); }
}
.notif-popup {
  position: absolute; top: calc(100% + 8px); right: 0; z-index: 200;
  min-width: 280px; max-width: 360px; padding: 14px;
  border-radius: var(--radius, 12px); border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: var(--glass-bg, rgba(10,10,20,.85));
  backdrop-filter: blur(var(--glass-blur-px, 20px)); box-shadow: 0 12px 40px rgba(0,0,0,.5);
}
.notif-popup-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
  color: #ef4444; margin-bottom: 10px;
}
.notif-popup-item { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.notif-popup-details { display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.notif-popup-detail {
  font-size: 13px; color: var(--text); font-weight: 600;
}
.notif-popup-actions { display: flex; gap: var(--space-2, 8px); align-items: center; margin-top: 4px; }
.notif-action {
  padding: 5px 14px; border-radius: 6px; font-size: var(--fs-sm, 12px); font-weight: 600; cursor: pointer;
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
}
.notif-action:hover { background: color-mix(in srgb, var(--pl) 35%, transparent); }
.notif-dismiss {
  background: none; border: none; color: var(--muted); font-size: var(--fs-xl, 18px); cursor: pointer; padding: 0 4px; line-height: 1; margin-left: auto;
}
.notif-dismiss:hover { color: #ef4444; }
</style>
