<template>
  <div class="shell-v1" :class="{ 'sidebar-is-open': sidebarOpen }">
    <ambient-background />

    <!-- Mobile sidebar backdrop -->
    <div v-if="sidebarOpen" class="mobile-backdrop" @click="sidebarOpen = false" />

    <!-- ══ LEFT: Library ══════════════════════════════════════════════════════ -->
    <aside class="panel-left">

      <!-- Library header -->
      <div class="lib-head">
        <img v-if="activeLib === 'roms' && activePlatformFsSlug" :src="`/platforms/icons/${activePlatformFsSlug}.png`" class="lib-head-icon" :alt="activePlatformFsSlug" @error="($event.target as HTMLImageElement).src = '/icons/gamepad.svg'" />
        <img v-else-if="activeLibObj?.icon.startsWith('/')" :src="activeLibObj.icon" class="lib-head-icon" :alt="activeLibObj?.name" />
        <span class="lib-head-name">{{ libDisplayName }}</span>
        <span class="game-count">{{ libraries.find(l => l.id === activeLib)?.count ?? 0 }} {{ activeLib === 'roms' ? t('emulation.roms_count') : t('library.games') }}</span>
      </div>

      <!-- Library switcher -->
      <div class="lib-switcher">
        <button class="lib-sw-btn" @click="stepLib(-1)" :disabled="libraries.length <= 1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <div class="lib-sw-center">
          <span class="lib-sw-label">{{ activeLibObj?.name }}</span>
          <button
            class="lib-sw-sync"
            :class="{ 'lib-sw-sync--spinning': syncing.has(activeLib) }"
            @click="openSyncDialog()"
            :title="t('library.sync')"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/>
              <polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </button>
        </div>
        <button class="lib-sw-btn" @click="stepLib(1)" :disabled="libraries.length <= 1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>

      <!-- Platform switcher (Emulation only) -->
      <div v-if="activeLib === 'roms'" class="plat-switcher">
        <button class="lib-sw-btn" @click="stepPlatform(-1)" :disabled="romPlatforms.length <= 1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <div class="plat-sw-center" ref="platDropRef">
          <button class="plat-sw-name" @click="platDropdownOpen = !platDropdownOpen">
            <img
              v-if="activePlatformFsSlug && !platLogoFailed[activePlatformFsSlug]"
              :src="`/platforms/names/${activePlatformFsSlug}.svg`"
              class="plat-sw-logo"
              @error="platLogoFailed[activePlatformFsSlug] = true"
            />
            <span v-else class="plat-sw-text">{{ romPlatforms.find(p => p.slug === activePlatformSlug)?.name || activePlatformSlug }}</span>
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :style="platDropdownOpen ? 'transform:rotate(180deg)' : ''"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div v-if="platDropdownOpen" class="plat-drop">
            <button
              v-for="p in romPlatforms"
              :key="p.fs_slug"
              class="plat-drop-item"
              :class="{ active: p.slug === activePlatformSlug }"
              @click="selectPlatform(p.slug)"
            >
              <img
                :src="`/platforms/names/${p.fs_slug}.svg`"
                class="plat-drop-logo"
                @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLImageElement).nextElementSibling?.removeAttribute('style')"
              />
              <span class="plat-drop-name" style="display:none">{{ p.name }}</span>
              <span class="plat-drop-count">{{ p.rom_count }}</span>
            </button>
          </div>
        </div>
        <button class="lib-sw-btn" @click="stepPlatform(1)" :disabled="romPlatforms.length <= 1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>

      <!-- Search -->
      <div class="search-box">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color:var(--muted);flex-shrink:0">
          <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
        </svg>
        <input v-model="searchQuery" class="search-input" :placeholder="t('nav.search')" />
        <button v-if="searchQuery" class="search-x" @click="searchQuery = ''">×</button>
        <button class="filter-owned-btn" :class="{ active: filterOwned }" @click="filterOwned = !filterOwned" :title="t('classic.downloaded_only')">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
        </button>
      </div>

      <!-- Sort row -->
      <div class="sort-row">
        <select v-model="sortBy" class="sort-select">
          <option value="title">{{ t('library.a_to_z') }}</option>
          <option value="title_desc">{{ t('library.z_to_a') }}</option>
          <option value="release">{{ t('library.newest') }}</option>
          <option value="release_asc">{{ t('library.oldest') }}</option>
          <option value="rating">{{ t('library.top_rated') }}</option>
          <option value="purchased">{{ t('library.recent') }}</option>
        </select>
      </div>

      <!-- Game list -->
      <div class="game-list" ref="gameListRef">
        <div v-if="loading" class="no-games">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-icon" style="opacity:.3">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
        </div>

        <div
          v-for="game in filteredGames"
          :key="game.id"
          class="game-item"
          :class="{ 'active': activeGameId === String(game.id), 'downloaded': game.downloaded }"
          @click="selectGame(game)"
        >
          <div class="gi-dot" />
          <!-- Icon: uses icon_path/icon_url → cover fallback → gamepad emoji (like V1) -->
          <div class="gi-icon-wrap">
            <img
              v-if="game.icon"
              :src="game.icon"
              loading="lazy"
              class="gi-icon"
              @error="(e) => { (e.target as HTMLImageElement).style.display='none'; (e.target as HTMLImageElement).nextElementSibling?.removeAttribute('style') }"
            />
            <span class="gi-icon-fb" style="display:none">🎮</span>
          </div>
          <span class="gi-title"><span class="gi-title-scroll">{{ game.title }}</span></span>
        </div>

        <div v-if="!loading && !filteredGames.length" class="no-games">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.15;display:block;margin-bottom:8px">
            <rect x="2" y="6" width="20" height="12" rx="2"/>
            <circle cx="7.5" cy="12" r="1.5"/><circle cx="16.5" cy="12" r="1.5"/>
          </svg>
          {{ searchQuery ? t('classic.no_results') : t('classic.library_empty') }}
        </div>
      </div>

      <!-- Bottom: download manager + user menu -->
      <div class="panel-bottom">
        <DownloadManager v-if="isAdmin" :inline="true" />
        <div class="user-area" ref="userAreaRef">
          <button class="user-btn" @click.stop="menuOpen = !menuOpen" :class="{ open: menuOpen }">
            <div class="user-avatar" style="position:relative">
              <img v-if="userAvatarUrl" :src="userAvatarUrl" class="user-avatar-img" :alt="initials" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
              <span v-else>{{ initials }}</span>
              <span v-if="notifStore.hasBadge" class="user-chip-badge" @click.stop="menuOpen = !menuOpen">{{ notifStore.totalCount }}</span>
            </div>
            <div class="user-info">
              <span class="user-name">{{ (authStore.user?.username as string) || 'Guest' }}</span>
              <span class="user-role">{{ userRole }}</span>
            </div>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
              :style="menuOpen ? 'transform:rotate(180deg);transition:.15s' : 'transition:.15s'">
              <polyline points="18 15 12 9 6 15"/>
            </svg>
          </button>
          <transition name="menu-up">
            <div v-if="menuOpen" class="user-menu">
              <div class="menu-header">
                <div class="menu-header-avatar">
                  <img v-if="userAvatarUrl" :src="userAvatarUrl" class="user-avatar-img" :alt="initials" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  <span v-else>{{ initials }}</span>
                </div>
                <div class="menu-header-info">
                  <span class="menu-header-name">{{ (authStore.user?.username as string) || 'Guest' }}</span>
                  <span class="menu-header-role">{{ userRole }}</span>
                </div>
              </div>
              <template v-if="notifStore.active.length">
                <div v-for="n in notifStore.active" :key="n.id" class="notif-item" @click.stop>
                  <div class="notif-header">
                    <span class="notif-dot" />
                    <span class="notif-label">{{ n.label }}</span>
                    <button class="notif-dismiss" @click="notifStore.dismiss(n.id)">&times;</button>
                  </div>
                  <div v-if="n.details" class="notif-details">
                    <div v-for="(d, i) in n.details" :key="i" class="notif-detail">{{ d }}</div>
                  </div>
                  <button v-if="n.action" class="notif-action" @click="menuOpen = false; $router.push(n.action); notifStore.dismiss(n.id)">{{ n.actionLabel }}</button>
                </div>
                <div class="menu-sep" />
              </template>
              <div class="menu-sep" />
              <router-link to="/couch" class="menu-item" @click="menuOpen = false">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="14" rx="3"/><circle cx="8" cy="13" r="1.5" fill="currentColor" stroke="none"/><circle cx="16" cy="13" r="1.5" fill="currentColor" stroke="none"/><path d="M6 10h4M8 8v4M14 11h4" stroke-width="2"/></svg>
                {{ t('couch.title') }}
              </router-link>
              <router-link to="/profile" class="menu-item" @click="menuOpen = false">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                {{ t('nav.profile') }}
              </router-link>
              <router-link to="/settings" class="menu-item" @click="menuOpen = false">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                {{ t('nav.settings') }}
              </router-link>
              <template v-if="isUploader">
                <div class="menu-sep" />
                <!-- Emulation: Add ROMs only -->
                <template v-if="activeLib === 'roms'">
                  <button class="menu-item" @click="openAddRomsModal">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
                    {{ t('library.add_roms') }}
                  </button>
                </template>
                <!-- Other libs: Upload File + Torrent -->
                <template v-else>
                  <button class="menu-item" @click="openUploadModal">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
                    {{ t('library.upload_file') }}
                  </button>
                  <button class="menu-item" @click="openTorrentModal">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/><path d="M8 12l2 2 4-4"/></svg>
                    {{ t('library.add_via_torrent') }}
                  </button>
                </template>
              </template>
              <div class="menu-sep" />
              <button v-if="isAdmin" class="menu-item menu-item--danger" @click="menuOpen = false; showClearAllDialog = true">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                {{ t('library.clear_metadata') }}
              </button>
              <button class="menu-item menu-item--danger" @click="doLogout">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                {{ t('nav.logout') }}
              </button>
            </div>
          </transition>
        </div>
      </div>
    </aside>

    <!-- ══ CENTER: Content + Log ══════════════════════════════════════════════ -->
    <main class="panel-center">

      <!-- Mobile top bar (hamburger) -->
      <div class="mobile-topbar">
        <button class="hamburger-btn" @click="sidebarOpen = !sidebarOpen" aria-label="Menu">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <span class="mobile-topbar-title">{{ libDisplayName }}</span>
      </div>

      <!-- Main scrollable area -->
      <div class="center-main">

        <!-- Non-library routes (profile, settings, etc.) -->
        <template v-if="isNonLibraryRoute">
          <router-view />
        </template>

        <!-- Library: empty state -->
        <div v-else-if="!activeGameId" class="empty-state">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width=".7">
            <rect x="2" y="7" width="20" height="14" rx="3"/>
            <circle cx="8" cy="14" r="1.5"/><circle cx="16" cy="14" r="1.5"/>
            <path d="M16 9h2M18 7v4" stroke-width="1.4"/>
            <path d="M6 7V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2" stroke-width="1"/>
          </svg>
          <div class="empty-text">{{ t('classic.select_game') }}</div>
          <div class="empty-sub">{{ t('classic.select_game_sub') }}</div>
        </div>

        <!-- Library: V1-style game detail -->
        <ClassicGameDetail v-else :game-id="activeGameId" :active-lib="activeLib" :refresh-tick="detailRefreshTick" />

      </div>

    </main>

  </div>

  <!-- Global notifications (same component as Modern theme) -->
  <notification-snackbar />

  <!-- ── SYNC DIALOG ─────────────────────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="showSyncDialog" class="cl-sync-overlay" @click.self="showSyncDialog = false">
      <div class="cl-sync-dialog">
        <div class="cl-sync-header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          {{ t('library.sync') }} {{ activeLibObj?.name }}
        </div>
        <div class="cl-sync-body">
          <label class="cl-sync-opt">
            <div class="cl-sync-check-wrap">
              <input type="checkbox" v-model="syncAutoScrape" />
              <div class="cl-sync-checkmark" :class="{ checked: syncAutoScrape }">
                <svg v-if="syncAutoScrape" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
            </div>
            <div>
              <div class="cl-sync-opt-title">{{ t('library.sync_auto_meta') }}</div>
              <div class="cl-sync-opt-desc">{{ t('library.sync_auto_meta_desc') }}</div>
            </div>
          </label>
          <label class="cl-sync-opt" :class="{ 'cl-sync-opt--disabled': !syncAutoScrape }" style="margin-top:12px;padding-top:12px;border-top:1px solid var(--glass-border)">
            <div class="cl-sync-check-wrap">
              <input type="checkbox" v-model="syncForceRescrape" :disabled="!syncAutoScrape" />
              <div class="cl-sync-checkmark" :class="{ checked: syncForceRescrape && syncAutoScrape, disabled: !syncAutoScrape }">
                <svg v-if="syncForceRescrape && syncAutoScrape" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
            </div>
            <div>
              <div class="cl-sync-opt-title">{{ t('library.sync_overwrite') }}</div>
              <div class="cl-sync-opt-desc">{{ t('library.sync_overwrite_desc') }}</div>
            </div>
          </label>
        </div>
        <div class="cl-sync-footer">
          <button class="cl-sync-cancel" @click="showSyncDialog = false">{{ t('common.cancel') }}</button>
          <button class="cl-sync-ok" @click="confirmSync">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ t('library.start_sync') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── CLEAR ALL METADATA DIALOG ──────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="showClearAllDialog" class="cl-confirm-overlay" @click.self="showClearAllDialog = false">
      <div class="cl-confirm-box">
        <div class="cl-confirm-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </div>
        <div class="cl-confirm-title">{{ t('classic.clear_confirm_title') }}</div>
        <div class="cl-confirm-body">
          {{ t('classic.clear_confirm_body') }}
        </div>
        <div class="cl-confirm-actions">
          <button class="cl-confirm-btn cl-confirm-btn--ghost" @click="showClearAllDialog = false">{{ t('common.cancel') }}</button>
          <button class="cl-confirm-btn cl-confirm-btn--danger" :disabled="clearingAll" @click="clearAllMetadata">
            {{ clearingAll ? t('library.clearing') : t('classic.clear_confirm_title') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── UPLOAD MODAL ───────────────────────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="uploadModal" class="cl-modal-backdrop" @mousedown.self="uploadModal = false">
      <div class="cl-modal">
        <div class="cl-modal-header">
          <span>{{ t('upload.title') }}</span>
          <button class="cl-modal-close" @click="uploadModal = false">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="cl-modal-body">
          <div class="cl-field">
            <label class="cl-label">{{ t('upload.game_title') }}</label>
            <input v-model="uForm.title" type="text" class="cl-input" placeholder="e.g. Half-Life 2" />
          </div>
          <div class="cl-field-row">
            <div class="cl-field">
              <label class="cl-label">{{ t('upload.platform') }}</label>
              <select v-model="uForm.os" class="cl-input">
                <option value="windows">Windows</option>
                <option value="mac">macOS</option>
                <option value="linux">Linux</option>
                <option value="all">All</option>
              </select>
            </div>
            <div class="cl-field">
              <label class="cl-label">{{ t('upload.file_type') }}</label>
              <select v-model="uForm.file_type" class="cl-input">
                <option value="game">Game</option>
                <option value="dlc">DLC</option>
                <option value="extra">Extra</option>
              </select>
            </div>
          </div>
          <div class="cl-field">
            <label class="cl-label">{{ t('upload.file') }}</label>
            <input type="file" class="cl-input cl-input--file" ref="uploadFileInput" @change="onUploadFileChange" />
            <div v-if="uForm.fileName" class="cl-file-name">{{ uForm.fileName }} ({{ uForm.fileSize }})</div>
          </div>
          <div v-if="uProgress !== null" class="cl-progress-wrap">
            <div class="cl-progress-bar" :style="{ width: uProgress + '%' }" />
            <span class="cl-progress-label">{{ uProgress }}%</span>
          </div>
          <div v-if="uError"   class="cl-msg cl-msg--error">{{ uError }}</div>
          <div v-if="uSuccess" class="cl-msg cl-msg--ok">{{ uSuccess }}</div>
        </div>
        <div class="cl-modal-footer">
          <button class="cl-btn cl-btn--ghost" @click="uploadModal = false">{{ t('common.cancel') }}</button>
          <button class="cl-btn cl-btn--primary" :disabled="uUploading || !uForm.title.trim() || !uForm.file" @click="submitUpload">
            <span v-if="uUploading" class="cl-spinner" />
            {{ t('upload.upload') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── TORRENT MODAL ──────────────────────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="torrentModal" class="cl-modal-backdrop" @mousedown.self="() => { if (!tDownloadId) { _stopTorrentListeners(); torrentModal = false } }">
      <div class="cl-modal">
        <div class="cl-modal-header">
          <span>{{ t('torrent.title') }}</span>
          <button class="cl-modal-close" @click="() => { _stopTorrentListeners(); torrentModal = false }">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="cl-modal-body">
          <template v-if="!tDownloadId">
            <div class="cl-field-row">
              <div class="cl-field">
                <label class="cl-label">{{ t('torrent.game_title') }}</label>
                <input v-model="tForm.title" type="text" class="cl-input" placeholder="e.g. Half-Life 2" />
              </div>
              <div class="cl-field" style="max-width:130px">
                <label class="cl-label">{{ t('upload.platform') }}</label>
                <select v-model="tForm.os" class="cl-input">
                  <option value="windows">Windows</option>
                  <option value="mac">macOS</option>
                  <option value="linux">Linux</option>
                  <option value="all">All</option>
                </select>
              </div>
            </div>
            <div class="cl-tabs">
              <button :class="['cl-tab', { 'cl-tab--active': tTab === 'url' }]" @click="tTab = 'url'">{{ t('torrent.magnet_url') }}</button>
              <button :class="['cl-tab', { 'cl-tab--active': tTab === 'file' }]" @click="tTab = 'file'">{{ t('torrent.torrent_file') }}</button>
            </div>
            <div v-if="tTab === 'url'" class="cl-field">
              <label class="cl-label">{{ t('torrent.magnet_label') }}</label>
              <input v-model="tForm.url" type="text" class="cl-input" placeholder="magnet:?xt=urn:btih:…" />
            </div>
            <div v-else class="cl-field">
              <label class="cl-label">{{ t('torrent.file_label') }}</label>
              <input type="file" accept=".torrent" class="cl-input cl-input--file" ref="torrentFileInput" @change="onTorrentFileChange" />
              <div v-if="tForm.fileName" class="cl-file-name">{{ tForm.fileName }}</div>
            </div>
          </template>
          <div v-if="tDownloadId" class="cl-torrent-progress">
            <div class="cl-tp-title">
              {{ tDlComplete ? t('torrent.download_complete') : t('torrent.downloading', { title: tForm.title }) }}
            </div>
            <div class="cl-tp-bar-wrap">
              <div class="cl-tp-bar" :style="{ width: tDlPercent + '%' }" :class="{ 'cl-tp-bar--done': tDlComplete }" />
            </div>
            <div class="cl-tp-meta">
              <span class="cl-tp-pct">{{ tDlPercent }}%</span>
              <span v-if="!tDlComplete">{{ fmtSpeed(tDlSpeed) }}</span>
              <span v-if="!tDlComplete && tDlEta >= 0">ETA {{ fmtEta(tDlEta) }}</span>
            </div>
            <div v-if="tDlComplete" class="cl-msg cl-msg--ok" style="margin-top:10px">{{ t('torrent.game_added') }}</div>
          </div>
          <div v-if="tError" class="cl-msg cl-msg--error">{{ tError }}</div>
        </div>
        <div class="cl-modal-footer">
          <button class="cl-btn cl-btn--ghost" @click="() => { _stopTorrentListeners(); torrentModal = false }">
            {{ tDownloadId && !tDlComplete ? t('torrent.close_bg') : t('common.cancel') }}
          </button>
          <button v-if="!tDownloadId" class="cl-btn cl-btn--primary" :disabled="tAdding || !tForm.title.trim() || (tTab === 'url' ? !tForm.url.trim() : !tForm.file)" @click="submitTorrent">
            <span v-if="tAdding" class="cl-spinner" />
            {{ t('torrent.add_to_queue') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── ADD ROMs MODAL ────────────────────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="addRomsModal" class="cl-modal-backdrop" @mousedown.self="!addRomsUploading && (addRomsModal = false)">
      <div class="cl-modal cl-modal--roms">

        <!-- Step 1: platform picker -->
        <template v-if="addRomsStep === 1">
          <div class="cl-modal-header">
            <span>{{ t('library.select_platform') }}</span>
            <button class="cl-modal-close" @click="addRomsModal = false">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="cl-modal-body" style="padding-top:8px">
            <div class="cl-rom-search-wrap">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="position:absolute;left:10px;top:50%;transform:translateY(-50%);opacity:.4"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input v-model="addRomsPlatformSearch" class="cl-input" style="padding-left:30px" :placeholder="t('library.search_platforms')" autofocus />
            </div>
            <div class="cl-plat-picker">
              <button
                v-for="p in filteredPickerPlatforms"
                :key="p.fs_slug"
                class="cl-plat-row"
                @click="selectAddPlatform(p)"
              >
                <img :src="`/platforms/icons/${p.fs_slug}.png`" class="cl-plat-icon" @error="($event.target as HTMLImageElement).style.display='none'" />
                <span class="cl-plat-name">{{ p.name }}</span>
                <span v-if="p.inDb" class="cl-plat-count">{{ p.rom_count }} ROM{{ p.rom_count !== 1 ? 's' : '' }}</span>
                <span v-else class="cl-plat-new">{{ t('library.new_platform') }}</span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="opacity:.3;flex-shrink:0"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
              <p v-if="!filteredPickerPlatforms.length" style="text-align:center;color:var(--muted);font-size: var(--fs-sm, 12px);padding:20px 0">{{ t('library.no_platforms') }}</p>
            </div>
          </div>
        </template>

        <!-- Step 2: file upload -->
        <template v-else-if="addRomsStep === 2">
          <div class="cl-modal-header">
            <button class="cl-modal-close" style="margin-right:auto;font-size: var(--fs-sm, 12px);display:flex;align-items:center;gap:4px" @click="addRomsStep = 1; addRomsFiles = []">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>{{ t('common.back') }}
            </button>
            <span>{{ t('library.upload_roms_title', { name: addRomsSelectedPlatform?.name ?? '' }) }}</span>
            <button class="cl-modal-close" @click="!addRomsUploading && (addRomsModal = false)">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="cl-modal-body">
            <div
              class="cl-drop-zone"
              :class="{ 'cl-drop-zone--over': addRomsDragOver }"
              @dragover.prevent="addRomsDragOver = true"
              @dragleave="addRomsDragOver = false"
              @drop.prevent="addRomsOnDrop"
              @click="addRomsFileInput?.click()"
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.3"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
              <span style="font-size: var(--fs-sm, 12px);color:var(--muted)">{{ t('classic.drop_roms') }}</span>
              <input ref="addRomsFileInput" type="file" multiple style="display:none" @change="addRomsOnFileChange" />
            </div>
            <div v-if="addRomsFiles.length" class="cl-rom-file-list">
              <div v-for="(f,i) in addRomsFiles" :key="i" class="cl-rom-file-row">
                <span class="cl-rom-file-name">{{ f.name }}</span>
                <span class="cl-rom-file-size">{{ _fmtBytesRom(f.size) }}</span>
                <div v-if="addRomsUploading" class="cl-rom-prog-wrap">
                  <div class="cl-rom-prog-bar" :style="{ width: (addRomsProgress[i] ?? 0) + '%' }" />
                </div>
                <button v-else class="cl-modal-close" style="flex-shrink:0" @click.stop="addRomsFiles.splice(i,1)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
            <div v-if="addRomsError"  class="cl-msg cl-msg--error">{{ addRomsError }}</div>
            <div v-if="addRomsDone"   class="cl-msg cl-msg--ok">{{ t('library.uploaded_ok', { count: addRomsSavedCount }) }}</div>
          </div>
          <div class="cl-modal-footer">
            <button class="cl-btn cl-btn--ghost" @click="!addRomsUploading && (addRomsModal = false)" :disabled="addRomsUploading">{{ t('common.cancel') }}</button>
            <button class="cl-btn cl-btn--primary" :disabled="!addRomsFiles.length || addRomsUploading" @click="submitAddRoms">
              <span v-if="addRomsUploading" class="cl-spinner" />
              {{ addRomsUploading ? t('library.uploading') : t('library.upload_files', { count: addRomsFiles.length }) }}
            </button>
          </div>
        </template>

      </div>
    </div>
  </teleport>


</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSocketStore } from '@/stores/socket'
import client from '@/services/api/client'
import AmbientBackground from '@/components/common/AmbientBackground.vue'
import ClassicGameDetail from './ClassicGameDetail.vue'
import NotificationSnackbar from '@/components/common/NotificationSnackbar.vue'
import DownloadManager from '@/components/gog/DownloadManager.vue'
import { useNotifications } from '@/composables/useNotifications'
import { useI18n } from '@/i18n'
import { useNotificationStore } from '@/stores/notifications'

const { success: notifySuccess, error: notifyError } = useNotifications()
const { t } = useI18n()
const notifStore = useNotificationStore()

interface Game {
  id: number | string
  title: string
  icon?: string            // 36×36 icon (icon_path / icon_url)
  cover?: string           // large cover fallback if no icon
  downloaded?: boolean
  rating?: number
  release_date?: string
}
interface Library { id: string; name: string; icon: string; color: string; count: number }

const authStore = useAuthStore()
const router    = useRouter()
const route     = useRoute()

// ── State ──────────────────────────────────────────────────────────────────────
const menuOpen     = ref(false)
const sidebarOpen  = ref(false)
const searchQuery  = ref('')
const sortBy       = ref('title')
const filterOwned  = ref(false)
const activeLib    = ref('games')
const activeGameId      = ref('')
const detailRefreshTick = ref(0)
const userAreaRef  = ref<HTMLElement>()
const logRef       = ref<HTMLElement>()
const loading      = ref(false)
const isSyncing    = ref(false)
const syncing      = ref<Set<string>>(new Set())
const logLines     = ref<string[]>([])
const gameListRef  = ref<HTMLElement>()

// Sync dialog
const showSyncDialog    = ref(false)
const syncAutoScrape    = ref(true)
const syncForceRescrape = ref(false)

// Clear all metadata
const showClearAllDialog = ref(false)
const clearingAll        = ref(false)

const allLibraries: Library[] = [
  { id: 'games', name: 'Games',     icon: '/GDLOGO.png',     color: '#14b8a6', count: 0 },
  { id: 'gog',   name: 'GOG',       icon: '/icons/gog.ico',  color: '#7c3aed', count: 0 },
  { id: 'roms',  name: 'Emulation', icon: '/icons/gamepad.svg', color: '#14b8a6', count: 0 },
]

const libraries = ref<Library[]>(allLibraries.filter(l => l.id !== 'gog'))

// ── ROM platform state ─────────────────────────────────────────────────────────
interface RomPlatform { id: number; slug: string; fs_slug: string; name: string; rom_count: number }
const romPlatforms       = ref<RomPlatform[]>([])
const activePlatformSlug = ref('')   // stores platform.slug (URL slug, used for API calls + routes)
const platDropdownOpen   = ref(false)
const platDropRef        = ref<HTMLElement>()
const platLogoFailed     = ref<Record<string, boolean>>({})

// fs_slug for icon/image paths (derived from active platform)
const activePlatformFsSlug = computed(() => {
  const p = romPlatforms.value.find(p => p.slug === activePlatformSlug.value)
  return p?.fs_slug || ''
})

// ── Add ROMs modal (two-step) ───────────────────────────────────────────────────
interface KnownPlatform { fs_slug: string; name: string }
interface PickerPlatform { fs_slug: string; name: string; rom_count: number; inDb: boolean }
const knownPlatforms = ref<KnownPlatform[]>([])
const addRomsModal = ref(false)
const addRomsStep  = ref<1|2>(1)
const addRomsPlatformSearch = ref('')
const addRomsSelectedPlatform = ref<PickerPlatform | null>(null)
const addRomsFiles   = ref<File[]>([])
const addRomsDragOver = ref(false)
const addRomsUploading = ref(false)
const addRomsProgress  = ref<number[]>([])
const addRomsError     = ref('')
const addRomsDone      = ref(false)
const addRomsSavedCount = ref(0)
const addRomsFileInput = ref<HTMLInputElement>()

const allPickerPlatforms = computed<PickerPlatform[]>(() => {
  const dbMap = new Map(romPlatforms.value.map(p => [p.fs_slug, p]))
  return knownPlatforms.value.map(kp => {
    const db = dbMap.get(kp.fs_slug)
    return { fs_slug: kp.fs_slug, name: kp.name, rom_count: db?.rom_count ?? 0, inDb: !!db }
  })
})

const filteredPickerPlatforms = computed(() => {
  const q = addRomsPlatformSearch.value.trim().toLowerCase()
  if (!q) return allPickerPlatforms.value
  return allPickerPlatforms.value.filter(p => p.name.toLowerCase().includes(q) || p.fs_slug.includes(q))
})

const games = ref<Game[]>([])

// ── Helpers ────────────────────────────────────────────────────────────────────

// NOTE: *_path fields from backend are already web-relative paths like
//   /resources/gog/{id}/covers/cover_auto.jpg - use directly, no reconstruction.

function resolveCover(g: any): string {
  if (g.cover_path) return g.cover_path as string   // direct - includes gog/{id}/
  return (g.cover_url as string) || ''
}

function resolveIcon(g: any): string {
  if (g.icon_path) return g.icon_path as string     // direct - includes gog/{id}/
  if (g.icon_url)  return g.icon_url  as string
  return resolveCover(g)                            // fallback to cover thumbnail
}

function pushLog(msg: string) {
  const ts = new Date().toLocaleTimeString('en-GB', { hour12: false })
  logLines.value.push(`[${ts}] ${msg}`)
  nextTick(() => {
    if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
  })
}

// ── Computed ───────────────────────────────────────────────────────────────────

const activeLibObj = computed(() => libraries.value.find(l => l.id === activeLib.value))

const libDisplayName = computed(() => {
  const map: Record<string, string> = { gog: t('nav.gog_library'), games: t('nav.games_library'), roms: t('nav.emulation') }
  return map[activeLib.value] ?? activeLibObj.value?.name ?? ''
})

const isNonLibraryRoute = computed(() =>
  !['library', 'game-detail', 'games-library', 'games-detail',
    'emulation-home', 'emulation-library', 'emulation-detail'].includes(route.name as string)
)

const initials = computed(() => {
  const n = (authStore.user?.username as string) || 'GD'
  return n.slice(0, 2).toUpperCase()
})

const userAvatarUrl = computed(() => {
  const ap = (authStore.user as any)?.avatar_path as string | undefined
  if (!ap) return ''
  if (ap.startsWith('http')) return ap
  const filename = ap.split(/[\\/]/).pop() || ''
  return filename ? `/resources/avatars/${filename}` : ''
})

const userRole = computed(() => {
  const r = (authStore.user?.role as string) || 'viewer'
  return r.charAt(0).toUpperCase() + r.slice(1).toLowerCase()
})

const isAdmin    = computed(() => authStore.user?.role === 'admin')
const isUploader = computed(() => ['admin', 'uploader'].includes(authStore.user?.role as string))

const filteredGames = computed(() => {
  let list = [...games.value]
  if (filterOwned.value) list = list.filter(g => g.downloaded)
  const q = searchQuery.value.toLowerCase()
  if (q) list = list.filter(g => g.title.toLowerCase().includes(q))
  switch (sortBy.value) {
    case 'title':       list.sort((a, b) => a.title.localeCompare(b.title)); break
    case 'title_desc':  list.sort((a, b) => b.title.localeCompare(a.title)); break
    case 'release':     list.sort((a, b) => (b.release_date || '').localeCompare(a.release_date || '')); break
    case 'release_asc': list.sort((a, b) => (a.release_date || '').localeCompare(b.release_date || '')); break
    case 'rating':      list.sort((a, b) => (b.rating || 0) - (a.rating || 0)); break
  }
  return list
})

// ── API calls ──────────────────────────────────────────────────────────────────

async function fetchRomPlatforms() {
  try {
    const { data } = await client.get('/roms/platforms')
    romPlatforms.value = data
    if (!activePlatformSlug.value && data.length) {
      activePlatformSlug.value = data[0].slug
    }
  } catch { romPlatforms.value = [] }
}

async function fetchKnownPlatforms() {
  try {
    const { data } = await client.get('/roms/platforms/known')
    knownPlatforms.value = data
  } catch { knownPlatforms.value = [] }
}

async function fetchGames() {
  loading.value = true
  try {
    if (activeLib.value === 'roms') {
      if (!romPlatforms.value.length) await fetchRomPlatforms()
      if (!activePlatformSlug.value) { loading.value = false; return }
      const { data } = await client.get('/roms', { params: { platform_slug: activePlatformSlug.value, limit: 999 } })
      games.value = (data.items as any[]).map((g: any) => ({
        id:           g.id,
        title:        g.name || g.fs_name_no_ext,
        downloaded:   false,
        rating:       g.ss_score,
        release_date: g.release_year ? String(g.release_year) : '',
        icon:         g.steamgrid_path || g.cover_path || `/platforms/icons/${activePlatformFsSlug.value}.png`,
        cover:        g.cover_path || '',
      }))
      const libIdx = libraries.value.findIndex(l => l.id === 'roms')
      if (libIdx >= 0) libraries.value[libIdx].count = games.value.length
      return
    }
    if (activeLib.value === 'games') {
      const { data } = await client.get('/library/games', { params: { limit: 500 } })
      games.value = (data.items as any[]).map((g: any) => ({
        id:           g.id,
        title:        g.title,
        downloaded:   (g.files as any[])?.some((f: any) => f.is_available) ?? false,
        rating:       g.rating,
        release_date: g.release_date,
        icon:         g.icon_path || g.cover_path || '',
        cover:        g.cover_path || '',
      }))
      const libIdx = libraries.value.findIndex(l => l.id === 'games')
      if (libIdx >= 0) libraries.value[libIdx].count = games.value.length
      return
    }
    const { data } = await client.get('/gog/library/games')
    games.value = (data as any[]).map(g => ({
      id: g.id,
      title: g.title,
      downloaded: g.is_downloaded,
      rating: g.rating,
      release_date: g.release_date,
      icon: resolveIcon(g),
      cover: resolveCover(g),
    }))
    const gogIdx = libraries.value.findIndex(l => l.id === 'gog')
    if (gogIdx >= 0) libraries.value[gogIdx].count = games.value.length
  } catch (e) {
    console.error('Failed to fetch games', e)
  } finally {
    loading.value = false
  }
}

function openSyncDialog() {
  if (syncing.value.has(activeLib.value)) return
  if (activeLib.value === 'games') { scanCustomLibrary(); return }
  if (activeLib.value === 'roms')  { scanRomLibrary();   return }
  showSyncDialog.value = true
}

async function scanRomLibrary() {
  const id = 'roms'
  if (syncing.value.has(id)) return
  const next = new Set(syncing.value); next.add(id); syncing.value = next
  pushLog('Scanning ROM library…')
  try {
    await client.post('/roms/scan')
    const poll = setInterval(async () => {
      try {
        const { data } = await client.get('/roms/scan/status')
        if (!data.running) {
          clearInterval(poll)
          await fetchRomPlatforms()
          await fetchGames()
          detailRefreshTick.value++
          pushLog('ROM scan complete.')
          const after = new Set(syncing.value); after.delete(id); syncing.value = after
        }
      } catch { clearInterval(poll); const after = new Set(syncing.value); after.delete(id); syncing.value = after }
    }, 2000)
  } catch (e) {
    pushLog(`ROM scan error: ${e}`)
    const after = new Set(syncing.value); after.delete(id); syncing.value = after
  }
}

async function scanCustomLibrary() {
  const id = 'games'
  if (syncing.value.has(id)) return
  const next = new Set(syncing.value); next.add(id); syncing.value = next
  pushLog('Scanning Games library (CUSTOM folder)…')
  try {
    const { data } = await client.post('/library/scan')
    await fetchGames()
    detailRefreshTick.value++
    pushLog(`Scan complete. Created: ${data.created}, updated: ${data.updated}. ${data.errors?.length ? data.errors.join(', ') : ''}`)
  } catch (e) {
    pushLog(`Scan error: ${e}`)
  } finally {
    const after = new Set(syncing.value); after.delete(id); syncing.value = after
  }
}

function startSyncPoller(id: string) {
  const poll = setInterval(async () => {
    try {
      const { data } = await client.get('/gog/library/sync/status')
      if (data.synced) pushLog(`Synced ${data.synced} games…`)
      if (!data.running) {
        clearInterval(poll)
        await fetchGames()
        detailRefreshTick.value++
        pushLog(`Sync complete. ${libraries.value.find(l => l.id === 'gog')?.count ?? 0} games in library.`)
        const after = new Set(syncing.value); after.delete(id); syncing.value = after
        isSyncing.value = false
      }
    } catch {
      clearInterval(poll)
      const after = new Set(syncing.value); after.delete(id); syncing.value = after
      isSyncing.value = false
    }
  }, 2000)
}

async function confirmSync() {
  showSyncDialog.value = false
  const id = activeLib.value
  if (syncing.value.has(id)) return
  const next = new Set(syncing.value); next.add(id); syncing.value = next
  isSyncing.value = true
  pushLog(`Syncing ${activeLibObj.value?.name ?? id} library…`)
  try {
    const params = new URLSearchParams()
    if (!syncAutoScrape.value)    params.set('auto_scrape', 'false')
    if (syncForceRescrape.value)  params.set('force_rescrape', 'true')
    const qs = params.toString()
    await client.post(`/gog/library/sync${qs ? '?' + qs : ''}`)
    startSyncPoller(id)
  } catch (e) {
    pushLog(`Sync error: ${e}`)
    const after = new Set(syncing.value); after.delete(id); syncing.value = after
    isSyncing.value = false
  }
}

async function clearAllMetadata() {
  if (clearingAll.value) return
  showClearAllDialog.value = false
  clearingAll.value = true
  pushLog('Clearing all metadata…')
  try {
    await Promise.allSettled([
      client.delete('/gog/library/metadata'),
      client.delete('/library/metadata'),
      client.delete('/roms/metadata'),
    ])
    await fetchGames()
    detailRefreshTick.value++
    pushLog('All metadata cleared.')
    notifySuccess('All metadata cleared successfully.')
  } catch (e) {
    pushLog(`Clear error: ${e}`)
    notifyError('Failed to clear metadata.')
  } finally {
    clearingAll.value = false
  }
}

// ── Navigation ─────────────────────────────────────────────────────────────────

function stepLib(dir: number) {
  const idx = libraries.value.findIndex(l => l.id === activeLib.value)
  const next = (idx + dir + libraries.value.length) % libraries.value.length
  switchLib(libraries.value[next].id)
}

function switchLib(id: string) {
  activeLib.value = id
  const routes: Record<string, string> = { gog: '/library', games: '/games', roms: '/emulation' }
  router.push(routes[id] ?? '/')
}

function selectGame(game: Game) {
  activeGameId.value = String(game.id)
  sidebarOpen.value = false  // close drawer on mobile after selection
  if (activeLib.value === 'roms') {
    router.push({ name: 'emulation-detail', params: { platform: activePlatformSlug.value, id: game.id } })
    return
  }
  const detailRoute = activeLib.value === 'games' ? 'games-detail' : 'game-detail'
  router.push({ name: detailRoute, params: { id: game.id } })
}

// ── Platform switcher (Emulation) ─────────────────────────────────────────────
function stepPlatform(dir: number) {
  const idx = romPlatforms.value.findIndex(p => p.slug === activePlatformSlug.value)
  if (idx < 0 && romPlatforms.value.length) { selectPlatform(romPlatforms.value[0].slug); return }
  const next = (idx + dir + romPlatforms.value.length) % romPlatforms.value.length
  selectPlatform(romPlatforms.value[next].slug)
}

function selectPlatform(slug: string) {
  activePlatformSlug.value = slug
  platDropdownOpen.value = false
  activeGameId.value = ''
  router.push({ name: 'emulation-library', params: { platform: slug } })
  fetchGames()
}

// ── Add ROMs modal ────────────────────────────────────────────────────────────
async function openAddRomsModal() {
  menuOpen.value = false
  if (!knownPlatforms.value.length) await fetchKnownPlatforms()
  addRomsStep.value = 1
  addRomsPlatformSearch.value = ''
  addRomsSelectedPlatform.value = null
  addRomsFiles.value = []
  addRomsDragOver.value = false
  addRomsUploading.value = false
  addRomsProgress.value = []
  addRomsError.value = ''
  addRomsDone.value = false
  addRomsSavedCount.value = 0
  addRomsModal.value = true
}

function selectAddPlatform(p: PickerPlatform) {
  addRomsSelectedPlatform.value = p
  addRomsStep.value = 2
  addRomsFiles.value = []
  addRomsError.value = ''
  addRomsDone.value = false
}

function addRomsAddFiles(fl: FileList | null) {
  if (!fl) return
  for (const f of Array.from(fl)) {
    if (!addRomsFiles.value.find(x => x.name === f.name && x.size === f.size)) addRomsFiles.value.push(f)
  }
}

function addRomsOnDrop(e: DragEvent) { addRomsDragOver.value = false; addRomsAddFiles(e.dataTransfer?.files ?? null) }
function addRomsOnFileChange(e: Event) { addRomsAddFiles((e.target as HTMLInputElement).files) }

function _fmtBytesRom(b: number): string {
  if (b >= 1073741824) return (b / 1073741824).toFixed(2) + ' GB'
  if (b >= 1048576)    return (b / 1048576).toFixed(1) + ' MB'
  return (b / 1024).toFixed(0) + ' KB'
}

async function submitAddRoms() {
  if (!addRomsSelectedPlatform.value || !addRomsFiles.value.length) return
  addRomsUploading.value = true; addRomsError.value = ''; addRomsDone.value = false
  addRomsProgress.value = addRomsFiles.value.map(() => 0)
  const slug = addRomsSelectedPlatform.value.fs_slug
  const fd = new FormData()
  addRomsFiles.value.forEach(f => fd.append('files', f))
  try {
    const { data } = await client.post(`/roms/platforms/${slug}/upload`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev) => {
        const pct = ev.total ? Math.round(ev.loaded / ev.total * 100) : 0
        addRomsProgress.value = addRomsFiles.value.map(() => pct)
      },
    })
    addRomsSavedCount.value = data.saved?.length ?? addRomsFiles.value.length
    addRomsDone.value = true
    addRomsUploading.value = false
    await fetchRomPlatforms()
    await fetchGames()
  } catch (e: any) {
    addRomsError.value = e?.response?.data?.detail || 'Upload failed'
    addRomsUploading.value = false
  }
}

function onPlatDropOutside(e: MouseEvent) {
  if (platDropRef.value && !platDropRef.value.contains(e.target as Node)) platDropdownOpen.value = false
}

function doLogout() {
  menuOpen.value = false
  authStore.logout()
  router.push('/login')
}

// ── Upload modal ────────────────────────────────────────────────────────────────

const uploadModal    = ref(false)
const uUploading     = ref(false)
const uError         = ref('')
const uSuccess       = ref('')
const uProgress      = ref<number | null>(null)
const uploadFileInput = ref<HTMLInputElement>()
const uForm = ref({ title: '', os: 'windows', file_type: 'game', file: null as File | null, fileName: '', fileSize: '' })

function openUploadModal() {
  menuOpen.value = false
  uError.value = ''; uSuccess.value = ''; uProgress.value = null
  uForm.value = { title: '', os: 'windows', file_type: 'game', file: null, fileName: '', fileSize: '' }
  uploadModal.value = true
}

function _fmtBytes(b: number): string {
  if (b >= 1073741824) return (b / 1073741824).toFixed(1) + ' GB'
  if (b >= 1048576)    return (b / 1048576).toFixed(0) + ' MB'
  return (b / 1024).toFixed(0) + ' KB'
}

function onUploadFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  uForm.value.file = f
  uForm.value.fileName = f?.name ?? ''
  uForm.value.fileSize = f ? _fmtBytes(f.size) : ''
  if (f && !uForm.value.title.trim()) uForm.value.title = f.name.replace(/\.[^.]+$/, '')
}

async function submitUpload() {
  uError.value = ''; uSuccess.value = ''; uProgress.value = 0; uUploading.value = true
  try {
    const gameRes = await client.post('/library/games', { title: uForm.value.title.trim() })
    const gameId = gameRes.data.id
    const fd = new FormData()
    fd.append('os', uForm.value.os)
    fd.append('file_type', uForm.value.file_type)
    fd.append('file', uForm.value.file as File)
    await client.post(`/library/games/${gameId}/upload`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev) => { if (ev.total) uProgress.value = Math.round(ev.loaded / ev.total * 100) },
    })
    uSuccess.value = t('upload.success')
    await fetchGames()
    setTimeout(() => { uploadModal.value = false }, 2000)
  } catch (e: any) {
    uError.value = e?.response?.data?.detail || 'Upload failed.'
  } finally {
    uUploading.value = false
  }
}

// ── Torrent modal ───────────────────────────────────────────────────────────────

const socketStore = useSocketStore()

const torrentModal     = ref(false)
const tTab             = ref<'url' | 'file'>('url')
const tAdding          = ref(false)
const tError           = ref('')
const torrentFileInput = ref<HTMLInputElement>()
const tDownloadId      = ref<number | null>(null)
const tDlPercent       = ref(0)
const tDlSpeed         = ref(0)
const tDlEta           = ref(-1)
const tDlStatus        = ref('')
const tDlComplete      = ref(false)
const tForm = ref({ title: '', os: 'windows', url: '', file: null as File | null, fileName: '' })

function openTorrentModal() {
  menuOpen.value = false
  tTab.value = 'url'; tError.value = ''
  tDownloadId.value = null; tDlPercent.value = 0; tDlSpeed.value = 0
  tDlEta.value = -1; tDlStatus.value = ''; tDlComplete.value = false
  tForm.value = { title: '', os: 'windows', url: '', file: null, fileName: '' }
  torrentModal.value = true
}

function _stopTorrentListeners() {
  socketStore.socket?.off('torrent:download_progress', _onTorrentProgress)
  socketStore.socket?.off('torrent:download_complete', _onTorrentComplete)
  socketStore.socket?.off('torrent:download_error',    _onTorrentError)
}

function _onTorrentProgress(data: any) {
  if (data.id !== tDownloadId.value) return
  tDlPercent.value = data.percent ?? 0; tDlSpeed.value = data.speed ?? 0
  tDlEta.value = data.eta ?? -1; tDlStatus.value = data.status ?? ''
}

function _onTorrentComplete(data: any) {
  if (data.id !== tDownloadId.value) return
  _stopTorrentListeners()
  tDlPercent.value = 100; tDlComplete.value = true
  fetchGames()
  setTimeout(() => { torrentModal.value = false }, 2500)
}

function _onTorrentError(data: any) {
  if (data.id !== tDownloadId.value) return
  _stopTorrentListeners()
  tError.value = data.error || 'Download failed.'
  tDownloadId.value = null
}

function onTorrentFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  tForm.value.file = f; tForm.value.fileName = f?.name ?? ''
}

function fmtSpeed(bps: number): string {
  if (bps >= 1048576) return (bps / 1048576).toFixed(1) + ' MB/s'
  if (bps >= 1024)    return (bps / 1024).toFixed(0) + ' KB/s'
  return bps + ' B/s'
}

function fmtEta(secs: number): string {
  if (secs < 0) return '-'
  if (secs < 60) return secs + 's'
  if (secs < 3600) return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's'
  return Math.floor(secs / 3600) + 'h ' + Math.floor((secs % 3600) / 60) + 'm'
}

async function submitTorrent() {
  tError.value = ''; tAdding.value = true
  try {
    let res: any
    if (tTab.value === 'url') {
      res = await client.post('/torrents/download/url', { url: tForm.value.url.trim(), title: tForm.value.title.trim(), os: tForm.value.os })
    } else {
      const fd = new FormData()
      fd.append('title', tForm.value.title.trim())
      fd.append('target_os', tForm.value.os)
      fd.append('file', tForm.value.file as File)
      res = await client.post('/torrents/download/file', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    }
    tDownloadId.value = res.data.id
    tDlPercent.value  = res.data.percent ?? 0
    socketStore.socket?.on('torrent:download_progress', _onTorrentProgress)
    socketStore.socket?.on('torrent:download_complete', _onTorrentComplete)
    socketStore.socket?.on('torrent:download_error',    _onTorrentError)
  } catch (e: any) {
    tError.value = e?.response?.data?.detail || 'Failed to add torrent.'
  } finally {
    tAdding.value = false
  }
}

function onClickOutside(e: MouseEvent) {
  if (userAreaRef.value && !userAreaRef.value.contains(e.target as Node)) menuOpen.value = false
  onPlatDropOutside(e)
}

// ── Title overflow (V1-style hover scroll animation) ──────────────────────────

function calcTitleOverflows() {
  nextTick(() => {
    if (!gameListRef.value) return
    gameListRef.value.querySelectorAll<HTMLElement>('.gi-title-scroll').forEach(el => {
      const parent = el.parentElement
      if (!parent) return
      const overflow = el.scrollWidth - parent.clientWidth
      if (overflow > 2) el.style.setProperty('--gi-overflow', `-${overflow + 4}px`)
      else el.style.removeProperty('--gi-overflow')
    })
  })
}

// ── Watchers ───────────────────────────────────────────────────────────────────

watch(() => route.params.id, id => {
  activeGameId.value = id ? String(id) : ''
}, { immediate: true })

watch(() => route.name, name => {
  // List pages → set lib AND reload game list
  if (name === 'library')          { activeLib.value = 'gog';   fetchGames() }
  if (name === 'games-library')    { activeLib.value = 'games'; fetchGames() }
  if (name === 'emulation-home' || name === 'emulation-library') {
    activeLib.value = 'roms'
    if (route.params.platform) activePlatformSlug.value = route.params.platform as string
    fetchGames()
  }
  // Detail pages → keep lib in sync without reloading the list
  if (name === 'game-detail')      { activeLib.value = 'gog' }
  if (name === 'games-detail')     { activeLib.value = 'games' }
  if (name === 'emulation-detail') {
    activeLib.value = 'roms'
    if (route.params.platform) activePlatformSlug.value = route.params.platform as string
  }
}, { immediate: true })

watch(isAdmin, (admin) => {
  libraries.value = allLibraries.filter(l => l.id !== 'gog' || admin)
  if (!admin && activeLib.value === 'gog') {
    activeLib.value = 'games'
  }
}, { immediate: true })

watch(filteredGames, () => calcTitleOverflows())

// ── Lifecycle ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  document.addEventListener('click', onClickOutside)
  // Reconnect to a sync that was already running before this page load/refresh
  try {
    const { data } = await client.get('/gog/library/sync/status')
    if (data.running) {
      const id = activeLib.value
      const next = new Set(syncing.value); next.add(id); syncing.value = next
      isSyncing.value = true
      pushLog(`Sync in progress - reconnecting…`)
      startSyncPoller(id)
    }
  } catch { /* best-effort */ }
  await fetchGames()
  const activeCount = libraries.value.find(l => l.id === activeLib.value)?.count ?? 0
  pushLog(`Library loaded. ${activeCount} games found.`)
})
onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  _stopTorrentListeners()
})
</script>

<style scoped>
/* ── Shell ─────────────────────────────────────────────────────────────────── */
.shell-v1 {
  display: grid;
  grid-template-columns: var(--sidebar-w, 280px) 1fr;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

/* ══ LEFT PANEL ══════════════════════════════════════════════════════════════ */
.panel-left {
  display: flex;
  flex-direction: column;
  min-height: 0;           /* critical: allows flex children to shrink & scroll */
  height: 100%;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 20px));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 20px));
  border-right: 1px solid var(--glass-border);
  z-index: 10;
  overflow: hidden;
}

/* Library header */
.lib-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 14px 14px 12px;
  gap: 6px;
  font-family: 'Rajdhani', var(--font);
  font-weight: 700;
  font-size: 17px;
  letter-spacing: 2px;
  color: var(--muted);
  flex-shrink: 0;
  text-transform: uppercase;
  background: linear-gradient(90deg, var(--pl-dim) 0%, transparent 100%);
  border-bottom: 1px solid var(--glass-border);
}
.lib-head-icon {
  height: 70px;
  width: auto;
  max-width: 160px;
  object-fit: contain;
  border-radius: var(--radius-sm, 8px);
  opacity: .9;
  filter: drop-shadow(0 4px 12px var(--pglow2));
}
.lib-head-name {
  line-height: 1;
}
.game-count {
  background: linear-gradient(135deg, var(--pl2), var(--pl));
  color: #fff;
  border-radius: 10px;
  padding: 2px 14px;
  font-size: var(--fs-md, 14px);
  font-weight: 700;
  box-shadow: 0 2px 8px var(--pglow2);
  letter-spacing: 1px;
}

/* Library switcher */
.lib-switcher {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  background: var(--glass-highlight);
  gap: var(--space-1, 4px);
}
.lib-sw-btn {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  transition: all .15s;
}
.lib-sw-btn:hover:not(:disabled) { color: var(--pl-light); background: var(--glass-border); }
.lib-sw-btn:disabled { opacity: .25; cursor: default; }
.lib-sw-center {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  justify-content: center;
}
.lib-sw-label {
  font-family: 'Rajdhani', var(--font);
  font-weight: 700;
  font-size: var(--fs-sm, 12px);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--muted);
}
.lib-sw-sync {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 3px;
  border-radius: var(--radius-xs, 4px);
  display: flex;
  align-items: center;
  transition: all .15s;
}
.lib-sw-sync:hover { color: var(--pl-light); background: var(--glass-border); }
.lib-sw-sync--spinning {
  color: var(--pl-light) !important;
  animation: sync-spin 1s linear infinite;
}
@keyframes sync-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* Search box */
.search-box {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
}
.search-input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text);
  font-size: var(--fs-sm, 12px);
  font-family: inherit;
  outline: none;
}
.search-input::placeholder { color: var(--muted); }
.search-x { background: none; border: none; cursor: pointer; color: var(--muted); padding: 0; font-size: 13px; }
.filter-owned-btn {
  width: 20px; height: 20px;
  border-radius: var(--radius-xs, 4px);
  border: 1px solid var(--glass-border);
  background: none;
  color: var(--muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all .15s;
}
.filter-owned-btn:hover { border-color: var(--pl); color: var(--text); }
.filter-owned-btn.active { background: var(--pl-dim); border-color: var(--pl); color: var(--pl-light); }

/* Sort row */
.sort-row {
  display: flex;
  align-items: center;
  padding: 3px 10px 4px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.sort-select {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  font-family: 'Rajdhani', var(--font);
  letter-spacing: .5px;
  cursor: pointer;
}
.sort-select option { background: var(--bg2); }

/* Game list */
.game-list {
  flex: 1;
  min-height: 0;           /* allows list to shrink so panel-bottom stays visible */
  overflow-y: auto;
  overflow-x: visible;
  padding: 4px 0;
}
.spin-icon { animation: sync-spin 1s linear infinite; display: block; margin: 20px auto; }
.no-games {
  text-align: center;
  padding: 32px 14px;
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
}
.game-item {
  padding: 4px 10px 4px 14px;
  cursor: pointer;
  font-size: var(--fs-md, 14px);
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  border-left: 2px solid transparent;
  transition: all .15s;
  line-height: 1.3;
  user-select: none;
}
.game-item:hover { background: var(--pl-dim); color: var(--text); }
.game-item.active {
  background: linear-gradient(90deg, color-mix(in srgb, var(--pl) 20%, transparent) 0%, transparent 100%);
  color: var(--text);
  border-left-color: var(--pl);
}
/* Green dot - only shown when downloaded */
.gi-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ok);
  flex-shrink: 0;
  display: none;
  box-shadow: 0 0 5px var(--ok);
}
.game-item.downloaded .gi-dot { display: block; }
.gi-icon-wrap {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;   /* allows scale outside bounds like V1 */
  position: relative;
  z-index: 1;
}
.gi-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
  border-radius: var(--radius-xs, 4px);
  display: block;
  transition: transform .2s ease;
  transform-origin: center center;
}
.gi-icon-fb {
  font-size: var(--fs-2xl, 22px);
  line-height: 1;
  display: flex;
  align-items: center;
  transition: transform .2s ease;
  transform-origin: center center;
}
.gi-icon-wrap:hover .gi-icon,
.gi-icon-wrap:hover .gi-icon-fb { transform: scale(2.0); z-index: 10; }
.gi-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 600;
}
/* display:inline-block is REQUIRED for scrollWidth to be measurable */
.gi-title-scroll { display: inline-block; }
.game-item:hover .gi-title-scroll {
  animation: gi-scroll 6s .7s ease-in-out infinite;
}
@keyframes gi-scroll {
  0%, 15%  { transform: translateX(0); }
  45%, 55% { transform: translateX(var(--gi-overflow, 0px)); }
  85%, 100%{ transform: translateX(0); }
}

/* Bottom user area */
.panel-bottom {
  padding: var(--space-2, 8px);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.user-area { position: relative; }
.user-btn {
  display: flex; align-items: center; gap: var(--space-2, 8px); width: 100%;
  padding: 6px 8px; border: 1px solid transparent; border-radius: 10px;
  background: none; cursor: pointer; font-family: inherit; transition: all .15s;
}
.user-btn:hover, .user-btn.open {
  background: var(--glass-highlight);
  border-color: var(--glass-border);
}
.user-avatar {
  width: 42px; height: 42px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, var(--pl), var(--pl2));
  display: flex; align-items: center; justify-content: center;
  font-size: var(--fs-sm, 12px); font-weight: 700; color: #fff;
  border: 1.5px solid var(--pl); overflow: hidden;
}
.user-avatar-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.user-info { flex: 1; text-align: left; overflow: hidden; }
.user-name { display: block; font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-role { display: block; font-size: var(--fs-xs, 10px); color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }
.user-menu {
  position: absolute; bottom: calc(100% + 6px); left: 0; right: 0;
  border-radius: 10px; overflow: hidden;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px, 20px));
  border: 1px solid var(--glass-border);
  box-shadow: 0 -12px 32px rgba(0, 0, 0, .5); z-index: 100;
}
.menu-header {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px 10px;
  background: var(--glass-highlight);
}
.menu-header-avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, var(--pl), var(--pl2));
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: #fff;
  border: 1.5px solid var(--pl); overflow: hidden;
}
.menu-header-info { display: flex; flex-direction: column; gap: 1px; overflow: hidden; }
.menu-header-name { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.menu-header-role { font-size: var(--fs-xs, 10px); color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }
.menu-item {
  display: flex; align-items: center; gap: 9px; padding: 10px 14px;
  font-size: 13px; font-weight: 600; color: var(--text);
  text-decoration: none; cursor: pointer; background: none; border: none;
  width: 100%; text-align: left; transition: background .15s; font-family: inherit;
}
.menu-item:hover { background: var(--glass-highlight); }
.menu-item--danger { color: var(--danger); }
.menu-item--danger:hover { background: rgba(239, 68, 68, .08); }
.menu-sep { height: 1px; background: var(--glass-border); }
.menu-up-enter-active, .menu-up-leave-active { transition: opacity .15s ease, transform .15s ease; }
.menu-up-enter-from, .menu-up-leave-to { opacity: 0; transform: translateY(6px); }

/* ══ CENTER PANEL ════════════════════════════════════════════════════════════ */
.panel-center {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-left: 1px solid var(--glass-border);
  position: relative;
  z-index: 1;
}

/* Main scrollable content */
.center-main {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* Always reserve scrollbar gutter so viewport width stays constant whether
     the page content overflows or not (mirrors ModernLayout's .main-content).
     Prevents flex-wrap layout shifts in headers when scrollbar appears. */
  scrollbar-gutter: stable;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted);
  padding: var(--space-10, 40px);
}
.empty-icon {
  width: 72px; height: 72px;
  opacity: .07;
  color: var(--text);
}
.empty-text {
  font-family: 'Rajdhani', var(--font);
  font-size: var(--fs-2xl, 22px);
  font-weight: 600;
  opacity: .3;
  letter-spacing: 1px;
}
.empty-sub { font-size: var(--fs-sm, 12px); opacity: .22; }

/* Game view - hide the back pill since left panel is navigation */
.game-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.game-view :deep(.gd-back-pill) { display: none !important; }

/* ── Sync dialog ─────────────────────────────────────────────────────────── */
.cl-sync-overlay {
  position: fixed; inset: 0; z-index: 7000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  animation: cl-fade .15s ease;
}
@keyframes cl-fade { from { opacity: 0; } to { opacity: 1; } }
.cl-sync-dialog {
  width: 420px;
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  animation: cl-pop .18s ease;
}
@keyframes cl-pop { from { transform: scale(.95); opacity: 0; } to { transform: none; opacity: 1; } }
.cl-sync-header {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 18px 20px;
  font-size: 15px; font-weight: 700; color: var(--text);
  border-bottom: 1px solid var(--glass-border);
}
.cl-sync-body { padding: var(--space-5, 20px); }
.cl-sync-opt { display: flex; align-items: flex-start; gap: var(--space-3, 12px); cursor: pointer; }
.cl-sync-check-wrap { position: relative; flex-shrink: 0; margin-top: 2px; }
.cl-sync-check-wrap input[type="checkbox"] { position: absolute; opacity: 0; width: 0; height: 0; }
.cl-sync-checkmark {
  width: 18px; height: 18px; border-radius: 5px;
  border: 2px solid var(--glass-border); background: rgba(255,255,255,.06);
  display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.cl-sync-checkmark.checked { background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1)); border-color: color-mix(in srgb, var(--pl) 50%, transparent); }
.cl-sync-checkmark.disabled { opacity: .5; cursor: not-allowed; }
.cl-sync-opt-title { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); margin-bottom: 4px; }
.cl-sync-opt-desc  { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }
.cl-sync-opt--disabled { opacity: .45; }
.cl-sync-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 10px;
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
}
.cl-sync-cancel {
  padding: 8px 18px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cl-sync-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cl-sync-ok {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 20px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 12px var(--pglow2);
}
.cl-sync-ok:hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }

/* ── Clear all confirm dialog ────────────────────────────────────────────── */
.cl-confirm-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  animation: cl-fade .15s ease;
}
.cl-confirm-box {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  padding: 32px 36px; max-width: 440px; width: 90%;
  display: flex; flex-direction: column; gap: 14px;
  animation: cl-pop .18s ease;
}
.cl-confirm-icon {
  width: 48px; height: 48px; border-radius: 50%;
  background: rgba(220,38,38,.15); border: 1px solid rgba(239,68,68,.3);
  display: flex; align-items: center; justify-content: center; color: #f87171;
}
.cl-confirm-title { font-size: 17px; font-weight: 700; color: var(--text); }
.cl-confirm-body  { font-size: 13px; color: var(--muted); line-height: 1.6; }
.cl-confirm-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 6px; }
.cl-confirm-btn {
  padding: 9px 20px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all .15s;
}
.cl-confirm-btn--ghost {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted);
}
.cl-confirm-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cl-confirm-btn--danger {
  background: rgba(220,38,38,.8); border: 1px solid rgba(239,68,68,.6); color: #fff;
}
.cl-confirm-btn--danger:hover { background: rgb(220,38,38); }
.cl-confirm-btn--danger:disabled { opacity: .6; cursor: not-allowed; }

/* ── Upload / Torrent modals ─────────────────────────────────────────────────── */
.cl-modal-backdrop {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.cl-modal {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  width: 480px; max-width: calc(100vw - 32px);
}
.cl-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px 12px; font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
  border-bottom: 1px solid var(--glass-border);
}
.cl-modal-close {
  background: none; border: none; color: var(--muted); cursor: pointer; padding: 2px;
  border-radius: var(--radius-xs, 4px); display: flex; align-items: center; justify-content: center;
}
.cl-modal-close:hover { color: var(--text); }
.cl-modal-body   { padding: 16px 18px; display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.cl-modal-footer { display: flex; justify-content: flex-end; gap: var(--space-2, 8px); padding: 12px 18px; border-top: 1px solid var(--glass-border); }
.cl-field   { display: flex; flex-direction: column; gap: 5px; flex: 1; }
.cl-field-row { display: flex; gap: 10px; }
.cl-label   { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.cl-input   { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); border-radius: 7px; color: var(--text); font-size: 13px; padding: 7px 10px; outline: none; width: 100%; box-sizing: border-box; }
.cl-input:focus { border-color: var(--pl); }
.cl-input--file { padding: 5px 8px; cursor: pointer; }
.cl-file-name { font-size: 11px; color: var(--muted); margin-top: 3px; }
.cl-tabs { display: flex; gap: 6px; }
.cl-tab { background: rgba(255,255,255,.05); border: 1px solid var(--glass-border); border-radius: 6px; color: var(--muted); font-size: var(--fs-sm, 12px); padding: 5px 12px; cursor: pointer; }
.cl-tab--active { background: color-mix(in srgb, var(--pl) 20%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light); }
.cl-progress-wrap { position: relative; height: 8px; background: rgba(255,255,255,.08); border-radius: var(--radius-xs, 4px); overflow: hidden; }
.cl-progress-bar { height: 100%; background: color-mix(in srgb, var(--pl) 60%, transparent); border-radius: var(--radius-xs, 4px); transition: width .3s; }
.cl-progress-label { position: absolute; right: 6px; top: -1px; font-size: var(--fs-xs, 10px); color: var(--muted); }
.cl-msg { font-size: var(--fs-sm, 12px); padding: 4px 0; }
.cl-msg--error { color: #f87171; }
.cl-msg--ok    { color: #4ade80; }
.cl-btn { border: none; border-radius: 7px; cursor: pointer; font-size: 13px; font-weight: 600; padding: 7px 16px; display: flex; align-items: center; gap: 7px; }
.cl-btn--ghost   { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted); }
.cl-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cl-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); box-shadow: 0 2px 12px var(--pglow2);
}
.cl-btn--primary:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }
.cl-btn--primary:disabled { opacity: .5; cursor: not-allowed; }
.cl-spinner { width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: cl-spin .7s linear infinite; display: inline-block; }
@keyframes cl-spin { to { transform: rotate(360deg); } }
.cl-torrent-progress { display: flex; flex-direction: column; gap: 10px; }
.cl-tp-title { font-size: 13px; font-weight: 600; color: var(--text); }
.cl-tp-bar-wrap { height: 6px; background: var(--glass-border); border-radius: 3px; overflow: hidden; }
.cl-tp-bar { height: 100%; background: color-mix(in srgb, var(--pl) 60%, transparent); border-radius: 3px; transition: width .5s ease; }
.cl-tp-bar--done { background: #4ade80; }
.cl-tp-meta { display: flex; gap: var(--space-3, 12px); font-size: 11px; color: var(--muted); }
.cl-tp-pct { font-weight: 700; color: var(--text); }

/* ── Platform switcher (Emulation) ───────────────────────────────────────── */
.plat-switcher {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 8px; border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0; background: rgba(0,0,0,.15); gap: var(--space-1, 4px);
}
.plat-sw-center {
  flex: 1; display: flex; flex-direction: column; align-items: center; position: relative;
}
.plat-sw-name {
  display: flex; align-items: center; gap: 5px;
  background: none; border: none; cursor: pointer; color: var(--muted);
  padding: 3px 6px; border-radius: var(--radius-sm);
  transition: background var(--transition);
  max-width: 100%;
}
.plat-sw-name:hover { background: rgba(255,255,255,.06); }
.plat-sw-logo { height: 18px; max-width: 130px; width: auto; object-fit: contain; filter: brightness(1.1); display: block; }
.plat-sw-text { font-size: 11px; font-weight: 600; color: var(--text); }

/* Dropdown */
.plat-drop {
  position: absolute; top: calc(100% + 4px); left: 50%; transform: translateX(-50%);
  width: calc(var(--sidebar-w, 280px) - 40px); max-height: 280px; overflow-y: auto;
  background: var(--bg-card, #12101a); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); box-shadow: 0 8px 32px rgba(0,0,0,.5); z-index: 500;
}
.plat-drop-item {
  display: flex; align-items: center; gap: var(--space-2, 8px); width: 100%;
  padding: 6px 10px; background: transparent; border: none; cursor: pointer;
  border-bottom: 1px solid var(--glass-border); transition: background var(--transition);
}
.plat-drop-item:last-child { border-bottom: none; }
.plat-drop-item:hover, .plat-drop-item.active { background: rgba(255,255,255,.06); }
.plat-drop-logo { height: 14px; max-width: 100px; width: auto; object-fit: contain; filter: brightness(1.1); }
.plat-drop-name { font-size: 11px; color: var(--text); flex: 1; text-align: left; }
.plat-drop-count { font-size: var(--fs-xs, 10px); color: var(--muted); margin-left: auto; flex-shrink: 0; }

/* ── Add ROMs modal extras ───────────────────────────────────────────────── */
.cl-modal--roms { width: 480px; max-width: 96vw; }
.cl-rom-search-wrap { position: relative; margin-bottom: 8px; }
.cl-plat-picker {
  max-height: 340px; overflow-y: auto;
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
}
.cl-plat-row {
  display: flex; align-items: center; gap: var(--space-2, 8px); width: 100%;
  padding: 7px 10px; background: transparent; border: none; cursor: pointer;
  border-bottom: 1px solid var(--glass-border); transition: background var(--transition);
}
.cl-plat-row:last-child { border-bottom: none; }
.cl-plat-row:hover { background: rgba(255,255,255,.06); }
.cl-plat-icon { width: 20px; height: 20px; object-fit: contain; flex-shrink: 0; }
.cl-plat-name { flex: 1; font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--text); text-align: left; }
.cl-plat-count { font-size: 11px; color: var(--muted); flex-shrink: 0; }
.cl-plat-new {
  font-size: 9px; font-weight: 700; color: #14b8a6;
  background: rgba(20,184,166,.12); padding: 2px 5px; border-radius: 3px; flex-shrink: 0;
}
.cl-drop-zone {
  border: 2px dashed var(--glass-border); border-radius: var(--radius-sm);
  padding: var(--space-6, 24px); display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px);
  cursor: pointer; margin-bottom: 10px; transition: border-color var(--transition), background var(--transition);
}
.cl-drop-zone:hover, .cl-drop-zone--over { border-color: var(--pl); background: color-mix(in srgb, var(--pl) 6%, transparent); }
.cl-rom-file-list {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  max-height: 150px; overflow-y: auto; margin-bottom: 8px;
}
.cl-rom-file-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-bottom: 1px solid var(--glass-border);
  position: relative;
}
.cl-rom-file-row:last-child { border-bottom: none; }
.cl-rom-file-name { flex: 1; font-size: 11px; color: var(--text); word-break: break-all; }
.cl-rom-file-size { font-size: var(--fs-xs, 10px); color: var(--muted); flex-shrink: 0; }
.cl-rom-prog-wrap { position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: rgba(255,255,255,.08); }
.cl-rom-prog-bar { height: 100%; background: var(--pl-light); transition: width .2s; }

/* ── Mobile ─────────────────────────────────────────────────────────────── */
.mobile-topbar { display: none; }

@media (max-width: 768px) {
  /* Grid → single column, sidebar becomes fixed overlay drawer */
  .shell-v1 {
    grid-template-columns: 1fr;
  }

  /* Sidebar: fixed off-screen by default, slides in */
  .panel-left {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 280px;
    z-index: 500;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
  }
  .sidebar-is-open .panel-left {
    transform: translateX(0);
  }

  /* Backdrop overlay */
  .mobile-backdrop {
    position: fixed;
    inset: 0;
    z-index: 499;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(3px);
    animation: backdrop-in 0.2s ease;
  }
  @keyframes backdrop-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }

  /* Mobile top bar */
  .mobile-topbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--glass-border);
    background: var(--glass-bg);
    backdrop-filter: blur(var(--glass-blur-px, 20px));
    flex-shrink: 0;
  }
  .hamburger-btn {
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--glass-border);
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s;
  }
  .hamburger-btn:hover { background: rgba(255, 255, 255, 0.12); }
  .mobile-topbar-title {
    font-size: var(--fs-md, 14px);
    font-weight: 700;
    color: var(--text);
    letter-spacing: 0.5px;
  }

  /* Panel center fills screen */
  .panel-center {
    border-left: none;
  }

  /* Lib head - more compact */
  .lib-head {
    padding: 10px 12px 8px;
  }
  .lib-head-icon { height: 48px; }
}
.user-chip-badge {
  position: absolute; inset: 0;
  border-radius: 50%;
  background: rgba(239, 68, 68, .85);
  color: #fff; font-size: var(--fs-md, 14px); font-weight: 800;
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
.notif-item { display: flex; flex-direction: column; gap: var(--space-1, 4px); padding: 8px 12px; font-size: 11px; color: var(--text); }
.notif-header { display: flex; align-items: center; gap: 6px; }
.notif-dot { width: 6px; height: 6px; border-radius: 50%; background: #ef4444; flex-shrink: 0; }
.notif-label { flex: 1; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #ef4444; font-size: var(--fs-xs, 10px); }
.notif-details { display: flex; flex-direction: column; gap: 2px; padding-left: 12px; }
.notif-detail { font-size: var(--fs-sm, 12px); font-weight: 600; }
.notif-action { padding: 4px 10px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); font-weight: 600; cursor: pointer; background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light); align-self: flex-start; margin-top: 2px; }
.notif-dismiss { background: none; border: none; color: var(--muted); font-size: var(--fs-md, 14px); cursor: pointer; padding: 0 2px; margin-left: auto; }
</style>
