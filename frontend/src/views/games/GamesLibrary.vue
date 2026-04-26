<template>
  <!-- Classic layout: game list lives in the sidebar -->
  <div v-if="isClassic" class="classic-placeholder">
    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.12">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
    </svg>
    <p>{{ t('library.select_game') }}</p>
  </div>

  <div v-else class="library-view">

    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <!-- LIBRARY VIEW - title bar + grid/list                                   -->
    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <template v-if="true">

    <!-- ── Title bar ──────────────────────────────────────────────────────── -->
    <div class="title-bar">
      <div class="title-left">
        <button class="lib-back-btn" @click="router.push('/')" :title="t('library.back_to_libraries')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('library.libraries') }}
        </button>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" class="title-ico-svg">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
        <div>
          <h1 class="title-text">{{ t('nav.games_library') }}</h1>
          <p class="title-sub">{{ displayedGames.length }} {{ t('library.games') }}</p>
        </div>
      </div>

      <div class="title-right">
        <!-- Add Game (admin/uploader only) -->
        <div v-if="isUploader" class="add-game-wrap" ref="addMenuRef">
          <button class="add-game-btn" @click="addMenuOpen = !addMenuOpen">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            {{ t('library.add_game') }}
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :style="{ transform: addMenuOpen ? 'rotate(180deg)' : '', transition: 'transform .15s' }">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          <div v-if="addMenuOpen" class="add-game-dropdown">
            <button class="add-game-option" @click="openUploadModal">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
              </svg>
              {{ t('library.upload_file') }}
            </button>
            <button v-if="transmissionEnabled" class="add-game-option" @click="openTorrentModal">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                <path d="M12 8v4l3 3"/>
              </svg>
              {{ t('library.add_via_torrent') }}
            </button>
          </div>
        </div>

        <!-- Scan (admin/uploader only) -->
        <div v-if="isUploader" class="sync-wrap">
          <button class="sync-btn" :class="{ 'sync-btn--running': scanning }" @click="scanLibrary" :disabled="scanning" :title="t('library.scan_custom')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ 'spin': scanning }">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ scanning ? t('library.scanning') : t('library.scan') }}
          </button>
          <span v-if="scanMsg && !scanning" class="sync-msg">{{ scanMsg }}</span>
        </div>

        <!-- Sort -->
        <select v-model="sortBy" class="sort-select">
          <option value="title">{{ t('library.a_to_z') }}</option>
          <option value="title_desc">{{ t('library.z_to_a') }}</option>
          <option value="release">{{ t('library.newest') }}</option>
          <option value="release_asc">{{ t('library.oldest') }}</option>
          <option value="rating">{{ t('library.top_rated') }}</option>
          <option value="newest">{{ t('library.recent') }}</option>
        </select>

        <!-- Filter: has files -->
        <button class="filter-btn" :class="{ active: filterAvailable }" @click="filterAvailable = !filterAvailable" :title="t('library.show_available')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {{ t('library.available_filter') }}
        </button>

        <!-- Cover size selector (cover mode only) -->
        <div v-if="viewMode === 'cover'" class="size-group" :title="t('library.cover_size')">
          <button v-for="sz in coverSizes" :key="sz.id" class="size-btn" :class="{ active: currentCoverSize === sz.id }" @click="currentCoverSize = sz.id">{{ sz.label }}</button>
        </div>

        <!-- Request a game -->
        <button class="req-btn" @click="requestDialogOpen = true" :title="t('library.request_game')" style="position:relative">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
          {{ t('library.request') }}
          <span v-if="reqBadge > 0" class="req-notify-dot">{{ reqBadge > 99 ? '99+' : reqBadge }}</span>
        </button>

        <!-- View toggle -->
        <div class="view-toggle">
          <button :class="{ active: viewMode === 'cover' }" @click="viewMode = 'cover'" :title="t('library.cover_grid')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          </button>
          <button :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'" :title="t('library.list_view')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- ── Loading ──────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="state-empty">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin" style="opacity:.3">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </div>

    <!-- ── Empty state ──────────────────────────────────────────────────────── -->
    <div v-else-if="!displayedGames.length" class="state-empty">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
      <p>{{ t('library.no_games') }}</p>
      <p v-if="isUploader && !games.length" style="font-size: var(--fs-sm, 12px);color:var(--muted);margin-top:4px">
        {{ t('library.empty_hint') }}
      </p>
    </div>

    <!-- ── MAIN AREA (grid + alpha sidebar) ──────────────────────────────── -->
    <div v-else class="library-main">

      <!-- Scrollable grid area -->
      <div class="grid-scroll" ref="gridScrollEl">

        <!-- ── COVER GRID ─────────────────────────────────────────────────── -->
        <div
          v-if="viewMode === 'cover'"
          class="cover-grid"
          :style="{ '--cover-min': coverSizeMap[currentCoverSize] + 'px' }"
        >
          <div
            v-for="(game, idx) in displayedGames"
            :key="game.id"
            class="cover-wrap"
            :data-alpha-idx="idx"
            @click="openGame(game)"
            @mousemove="onCardMove($event)"
            @mouseleave="onCardLeave($event)"
            @mouseenter="onCardEnter($event)"
          >
            <div class="cover-img-wrap">
              <img
                v-if="game.cover_path"
                :src="game.cover_path"
                :alt="game.title"
                class="cover-img"
                loading="lazy"
              />
              <div v-else class="cover-fallback">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.25">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                </svg>
              </div>

              <!-- Sheen overlay -->
              <div class="cover-sheen" />

              <!-- Available files badge -->
              <div v-if="game.file_count > 0" class="badge badge--owned">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                {{ game.file_count !== 1 ? t('library.file_count_plural', { count: game.file_count }) : t('library.file_count', { count: game.file_count }) }}
              </div>

              <!-- Source badge (GOG / CUSTOM) -->
              <div v-if="game.source === 'gog'" class="badge badge--src badge--gog" style="top:auto;bottom:6px;">GOG</div>
              <div v-else-if="game.source === 'custom'" class="badge badge--src badge--custom" style="top:auto;bottom:6px;">CUSTOM</div>

              <!-- Hover overlay -->
              <div class="cover-overlay">
                <div class="overlay-title">{{ game.title }}</div>
              </div>
            </div>

            <div class="cover-title">{{ game.title }}</div>
            <div class="cover-scores">
              <div v-if="game.rating" class="cover-score" title="Rating">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color:#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                {{ game.rating.toFixed(1) }}
              </div>
              <div v-if="game.meta_ratings?.rawg" class="cover-score" title="RAWG Rating">
                <img src="/icons/RAWG.ico" width="11" height="11" alt="RAWG" class="score-ico" />
                {{ (game.meta_ratings.rawg).toFixed(1) }}
              </div>
              <div v-if="game.meta_ratings?.steam" class="cover-score" title="Metacritic">
                <img src="/icons/metacritic.svg" width="11" height="11" alt="MC" class="score-ico" />
                {{ Math.round(game.meta_ratings.steam * 10) }}
              </div>
            </div>
          </div>
        </div>

        <!-- ── LIST VIEW ────────────────────────────────────────────────── -->
        <div v-else class="list-view">
          <div
            v-for="(game, idx) in displayedGames"
            :key="game.id"
            class="list-row"
            @click="openGame(game)"
          >
            <!-- Cover -->
            <div
              class="list-cover-wrap"
              @mousemove="onCardMove($event)"
              @mouseleave="onCardLeave($event)"
              @mouseenter="onCardEnter($event)"
            >
              <div class="cover-img-wrap">
                <img v-if="game.cover_path" :src="game.cover_path" class="list-cover-img" loading="lazy" />
                <div v-else class="list-cover-fallback" />
                <div class="cover-sheen" />
                <div class="cover-overlay" />
              </div>
            </div>

            <!-- Info -->
            <div class="list-info">
              <div class="list-title">
                <span>{{ game.title }}</span>
              </div>
              <div class="list-meta">
                <span v-if="game.developer">{{ game.developer }}</span>
                <span v-if="game.developer && game.release_date" class="meta-sep" />
                <span v-if="game.release_date">{{ releaseYear(game.release_date) }}</span>
              </div>
            </div>

            <!-- Hero art + description overlay -->
            <div class="list-hero">
              <img
                v-if="game.background_path || game.cover_path"
                :src="game.background_path || game.cover_path || ''"
                :alt="game.title"
                :class="['list-hero-img', listHeroAnimClass]"
                :style="{ animationDelay: (idx * -7) + 's' }"
                loading="lazy"
              />
              <div class="list-hero-overlay" />
              <div v-if="game.description_short || game.description" class="list-hero-desc">
                <p class="list-hero-desc-text">{{ listDescText(game) }}</p>
              </div>
            </div>

            <!-- Quickfacts -->
            <div class="list-qf-col">
              <div class="list-qf">
                <div v-if="game.developer" class="list-qf-row">
                  <span class="list-qf-label">{{ t('detail.developer') }}</span>
                  <span class="list-qf-val">{{ game.developer }}</span>
                </div>
                <div v-if="game.publisher && game.publisher !== game.developer" class="list-qf-row">
                  <span class="list-qf-label">{{ t('detail.publisher') }}</span>
                  <span class="list-qf-val">{{ game.publisher }}</span>
                </div>
                <div v-if="(game.genres || []).length" class="list-qf-row">
                  <span class="list-qf-label">{{ t('library.genre') }}</span>
                  <span class="list-qf-val">
                    <span v-for="g in (game.genres || []).slice(0, 3)" :key="g" class="genre-chip">{{ g }}</span>
                  </span>
                </div>
                <div v-if="game.release_date" class="list-qf-row">
                  <span class="list-qf-label">{{ t('detail.released') }}</span>
                  <span class="list-qf-val">{{ releaseYear(game.release_date) }}</span>
                </div>
                <div v-if="game.os_windows || game.os_mac || game.os_linux" class="list-qf-row">
                  <span class="list-qf-label">{{ t('library.platform_label') }}</span>
                  <span class="list-qf-val list-qf-os">
                    <span v-if="game.os_windows" class="list-os-chip list-os-chip--win" title="Windows">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/></svg>
                    </span>
                    <span v-if="game.os_mac" class="list-os-chip list-os-chip--mac" title="macOS">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>
                    </span>
                    <span v-if="game.os_linux" class="list-os-chip list-os-chip--linux" title="Linux">
                      <img src="/icons/os-linux.svg" width="14" height="14" alt="Linux" />
                    </span>
                  </span>
                </div>
                <div v-if="game.file_count !== undefined" class="list-qf-row">
                  <span class="list-qf-label">{{ t('library.files') }}</span>
                  <span class="list-qf-val">{{ t('library.files_available', { count: game.file_count }) }}</span>
                </div>
                <div v-if="game.source" class="list-qf-row">
                  <span class="list-qf-label">{{ t('detail.source') }}</span>
                  <span class="list-qf-val" :class="game.source === 'gog' ? 'src-gog' : 'src-custom'">{{ game.source.toUpperCase() }}</span>
                </div>
              </div>
            </div>

            <!-- Right column: ratings -->
            <div class="list-right">
              <div v-if="game.rating || game.meta_ratings?.rawg || game.meta_ratings?.igdb || game.meta_ratings?.steam" class="list-scores">
                <div v-if="game.rating" class="list-score" title="Rating">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="1"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>
                  {{ game.rating.toFixed(1) }}
                </div>
                <div v-if="game.meta_ratings?.rawg" class="list-score" title="RAWG">
                  <img src="/icons/RAWG.ico" width="20" height="20" alt="RAWG" class="score-ico" />
                  {{ (game.meta_ratings.rawg).toFixed(1) }}
                </div>
                <div v-if="game.meta_ratings?.igdb" class="list-score" title="IGDB">
                  <img src="/icons/igdb.ico" width="20" height="20" alt="IGDB" class="score-ico" />
                  {{ Math.round(game.meta_ratings.igdb) }}
                </div>
                <div v-if="game.meta_ratings?.steam" class="list-score" title="Metacritic">
                  <img src="/icons/metacritic.svg" width="20" height="20" alt="Metacritic" class="score-ico" />
                  {{ Math.round(game.meta_ratings.steam * 10) }}
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /grid-scroll -->

      <!-- Alphabet sidebar -->
      <div class="alpha-nav">
        <button
          v-for="letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ#'.split('')"
          :key="letter"
          class="alpha-btn"
          :class="{ available: availableLetters.has(letter), active: activeLetter === letter }"
          @click="scrollToLetter(letter)"
        >{{ letter }}</button>
      </div>

    </div><!-- /library-main -->

    </template><!-- /library-view template -->

  </div>

  <!-- ── Add via Torrent modal ─────────────────────────────────────────────── -->
  <Teleport to="body">
    <div v-if="torrentModal" class="gl-modal-backdrop" @mousedown.self="() => { if (!tDownloadId) { _stopTorrentListeners(); torrentModal = false } }">
      <div class="gl-modal">
        <div class="gl-modal-header">
          <span class="gl-modal-title">{{ t('torrent.title') }}</span>
          <button class="gl-modal-close" @click="() => { _stopTorrentListeners(); torrentModal = false }">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div class="gl-modal-body">
          <!-- Form - hidden while downloading -->
          <template v-if="!tDownloadId">
            <!-- Title + OS -->
            <div class="gl-field-row">
              <div class="gl-field">
                <label class="gl-label">{{ t('torrent.game_title') }}</label>
                <input v-model="tForm.title" type="text" class="gl-input" placeholder="e.g. Half-Life 2" />
              </div>
              <div class="gl-field gl-field--sm">
                <label class="gl-label">{{ t('upload.platform') }}</label>
                <select v-model="tForm.os" class="gl-input">
                  <option value="windows">Windows</option>
                  <option value="mac">macOS</option>
                  <option value="linux">Linux</option>
                  <option value="all">All</option>
                </select>
              </div>
            </div>

            <!-- Source tabs -->
            <div class="gl-tabs">
              <button :class="['gl-tab', { 'gl-tab--active': tTab === 'url' }]" @click="tTab = 'url'">{{ t('torrent.magnet_url') }}</button>
              <button :class="['gl-tab', { 'gl-tab--active': tTab === 'file' }]" @click="tTab = 'file'">{{ t('torrent.torrent_file') }}</button>
            </div>

            <div v-if="tTab === 'url'" class="gl-field">
              <label class="gl-label">{{ t('torrent.magnet_label') }}</label>
              <input v-model="tForm.url" type="text" class="gl-input" placeholder="magnet:?xt=urn:btih:… or https://…" />
            </div>

            <div v-else class="gl-field">
              <label class="gl-label">{{ t('torrent.file_label') }}</label>
              <input type="file" accept=".torrent" class="gl-input gl-input--file" ref="torrentFileInput" @change="onTorrentFileChange" />
              <div v-if="tForm.fileName" class="gl-file-name">{{ tForm.fileName }}</div>
            </div>
          </template>

          <!-- Progress panel - shown after torrent is queued -->
          <div v-if="tDownloadId" class="gl-torrent-progress">
            <div class="gl-tp-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                <path d="M8 12l2 2 4-4"/>
              </svg>
              {{ tDlComplete ? t('torrent.download_complete') : t('torrent.downloading', { title: tForm.title }) }}
            </div>
            <div class="gl-tp-bar-wrap">
              <div class="gl-tp-bar" :style="{ width: tDlPercent + '%' }" :class="{ 'gl-tp-bar--done': tDlComplete }" />
            </div>
            <div class="gl-tp-meta">
              <span class="gl-tp-pct">{{ tDlPercent }}%</span>
              <span v-if="!tDlComplete" class="gl-tp-speed">{{ fmtSpeed(tDlSpeed) }}</span>
              <span v-if="!tDlComplete && tDlEta >= 0" class="gl-tp-eta">ETA {{ fmtEta(tDlEta) }}</span>
              <span v-if="tDlStatus && !tDlComplete" class="gl-tp-status">{{ tDlStatus }}</span>
            </div>
            <div v-if="tDlComplete" class="gl-success" style="margin-top:10px">{{ t('torrent.game_added') }}</div>
          </div>

          <div v-if="tError" class="gl-error">{{ tError }}</div>
        </div>

        <div class="gl-modal-footer">
          <button class="gl-btn gl-btn--ghost" @click="() => { _stopTorrentListeners(); torrentModal = false }">
            {{ tDownloadId && !tDlComplete ? t('torrent.close_bg') : t('common.cancel') }}
          </button>
          <button v-if="!tDownloadId" class="gl-btn gl-btn--primary" :disabled="tAdding || !tForm.title.trim() || (tTab === 'url' ? !tForm.url.trim() : !tForm.file)" @click="submitTorrent">
            <span v-if="tAdding" class="gl-spinner" />
            {{ t('torrent.add_to_queue') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- ── Upload modal (simple redirect to existing upload flow) ─────────────── -->
  <Teleport to="body">
    <div v-if="uploadModal" class="gl-modal-backdrop" @mousedown.self="uploadModal = false">
      <div class="gl-modal">
        <div class="gl-modal-header">
          <span class="gl-modal-title">{{ t('upload.title') }}</span>
          <button class="gl-modal-close" @click="uploadModal = false">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="gl-modal-body">
          <div class="gl-field">
            <label class="gl-label">{{ t('upload.game_title') }}</label>
            <input v-model="uForm.title" type="text" class="gl-input" placeholder="e.g. Half-Life 2" />
          </div>
          <div class="gl-field-row">
            <div class="gl-field gl-field--sm">
              <label class="gl-label">{{ t('upload.platform') }}</label>
              <select v-model="uForm.os" class="gl-input">
                <option value="windows">Windows</option>
                <option value="mac">macOS</option>
                <option value="linux">Linux</option>
                <option value="all">All</option>
              </select>
            </div>
            <div class="gl-field gl-field--sm">
              <label class="gl-label">{{ t('upload.file_type') }}</label>
              <select v-model="uForm.file_type" class="gl-input">
                <option value="game">Game</option>
                <option value="dlc">DLC</option>
                <option value="extra">Extra</option>
              </select>
            </div>
          </div>
          <div class="gl-field">
            <label class="gl-label">{{ t('upload.file') }}</label>
            <input type="file" class="gl-input gl-input--file" ref="uploadFileInput" @change="onUploadFileChange" />
            <div v-if="uForm.fileName" class="gl-file-name">{{ uForm.fileName }} ({{ uForm.fileSize }})</div>
          </div>
          <div v-if="uProgress !== null" class="gl-progress-wrap">
            <div class="gl-progress-bar" :style="{ width: uProgress + '%' }" />
            <span class="gl-progress-label">{{ uProgress }}%</span>
          </div>
          <div v-if="uError"   class="gl-error">{{ uError }}</div>
          <div v-if="uSuccess" class="gl-success">{{ uSuccess }}</div>
        </div>
        <div class="gl-modal-footer">
          <button class="gl-btn gl-btn--ghost" @click="uploadModal = false">{{ t('common.cancel') }}</button>
          <button class="gl-btn gl-btn--primary" :disabled="uUploading || !uForm.title.trim() || !uForm.file" @click="submitUpload">
            <span v-if="uUploading" class="gl-spinner" />
            {{ t('upload.upload') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <GameRequestDialog
    :visible="requestDialogOpen"
    default-platform="games"
    @close="requestDialogOpen = false; refreshReqBadge()"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from '@/i18n'
import { useSocketStore } from '@/stores/socket'

const { t } = useI18n()

function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: any[]) => {
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => { fn(...args) }, ms)
  }) as T
}
import { useRouter, useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import client from '@/services/api/client'
import GameRequestDialog from '@/components/GameRequestDialog.vue'
import { useRequestNotify } from '@/composables/useRequestNotify'

interface LibGame {
  id: number
  title: string
  slug: string
  source: string
  cover_path: string | null
  background_path: string | null
  developer: string | null
  publisher: string | null
  rating: number | null
  meta_ratings: { rawg?: number; igdb?: number; steam?: number } | null
  genres: string[] | null
  os_windows: boolean
  os_mac: boolean
  os_linux: boolean
  file_count: number
  release_date: string | null
  description: string | null
  description_short: string | null
  is_active: boolean
}

const router      = useRouter()
const route       = useRoute()
const themeStore  = useThemeStore()
const auth        = useAuthStore()
const socketStore = useSocketStore()

const isClassic  = computed(() => themeStore.currentLayout === 'classic')
const listHeroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `list-hero-img--${themeStore.heroAnimStyle}`
})
const isUploader = computed(() => ['admin', 'uploader'].includes(auth.user?.role as string))

const requestDialogOpen = ref(false)
const { totalBadge: reqBadge, refresh: refreshReqBadge } = useRequestNotify()

const games         = ref<LibGame[]>([])
const loading       = ref(false)
const viewMode      = ref<'cover' | 'list'>((localStorage.getItem('games_view_mode') as 'cover' | 'list') || 'cover')
watch(viewMode, v => localStorage.setItem('games_view_mode', v))
const sortBy        = ref(localStorage.getItem('games_sort_by') || 'title')
watch(sortBy, v => localStorage.setItem('games_sort_by', v))
const scanning      = ref(false)
const scanMsg       = ref('')
const searchQuery   = ref('')
const filterAvailable = ref(false)
const activeLetter  = ref('')
const gridScrollEl  = ref<HTMLElement>()


// Cover size - shared via themeStore (global, per-user, same as GOG Library)
const coverSizes = [
  { id: 'xs', label: 'XS' }, { id: 's', label: 'S' }, { id: 'm', label: 'M' },
  { id: 'l', label: 'L' },   { id: 'xl', label: 'XL' }, { id: 'xxl', label: 'XXL' },
]
const currentCoverSize = ref(localStorage.getItem('games-lib-card-size') || 'm')
watch(currentCoverSize, v => localStorage.setItem('games-lib-card-size', v))
const coverSizeMap: Record<string, number> = { xs: 115, s: 145, m: 175, l: 215, xl: 265, xxl: 310 }

// ── Fetch ───────────────────────────────────────────────────────────────────

async function fetchGames() {
  loading.value = true
  try {
    const params: Record<string, string> = { limit: '500' }
    if (searchQuery.value.trim()) params.search = searchQuery.value.trim()
    const { data } = await client.get('/library/games', { params })
    games.value = (data.items as any[]).map(g => ({
      id:               g.id,
      title:            g.title,
      slug:             g.slug,
      source:           g.source,
      cover_path:       g.cover_path,
      background_path:  g.background_path,
      developer:        g.developer,
      publisher:        g.publisher,
      rating:           g.rating,
      meta_ratings:     g.meta_ratings,
      genres:           g.genres,
      os_windows:       g.os_windows,
      os_mac:           g.os_mac,
      os_linux:         g.os_linux,
      file_count:       (g.files as any[])?.filter((f: any) => f.is_available).length ?? 0,
      release_date:     g.release_date,
      description:      g.description,
      description_short: g.description_short,
      is_active:        g.is_active,
    }))
  } catch (e) {
    console.error('Failed to fetch library games', e)
  } finally {
    loading.value = false
  }
}

// Sync searchQuery ↔ route.query.q (same pattern as GogLibrary)
watch(() => route.query.q, (q) => {
  const val = (Array.isArray(q) ? q[0] : q) || ''
  if (searchQuery.value !== val) searchQuery.value = val
}, { immediate: true })
watch(searchQuery, (q) => {
  const cur = (Array.isArray(route.query.q) ? route.query.q[0] : route.query.q) || ''
  if (q !== cur) router.replace({ query: { ...route.query, q: q || undefined } })
})

watch(searchQuery, debounce(() => fetchGames(), 350))


// ── Scan ────────────────────────────────────────────────────────────────────

async function scanLibrary() {
  if (scanning.value) return
  scanning.value = true
  scanMsg.value = ''
  try {
    const { data } = await client.post('/library/scan')
    scanMsg.value = `Done - ${data.created} new, ${data.updated} updated`
    if (data.errors?.length) scanMsg.value += `, ${data.errors.length} error(s)`
    await fetchGames()
    setTimeout(() => { scanMsg.value = '' }, 5000)
  } catch (e: any) {
    scanMsg.value = e?.response?.data?.detail || 'Scan failed'
  } finally {
    scanning.value = false
  }
}

// ── Display + sort ───────────────────────────────────────────────────────────

const displayedGames = computed(() => {
  let list = [...games.value]
  if (filterAvailable.value) list = list.filter(g => g.file_count > 0)
  switch (sortBy.value) {
    case 'title':       list.sort((a, b) => a.title.localeCompare(b.title)); break
    case 'title_desc':  list.sort((a, b) => b.title.localeCompare(a.title)); break
    case 'release':     list.sort((a, b) => (b.release_date || '').localeCompare(a.release_date || '')); break
    case 'release_asc': list.sort((a, b) => (a.release_date || '').localeCompare(b.release_date || '')); break
    case 'rating':      list.sort((a, b) => (b.rating || 0) - (a.rating || 0)); break
    case 'newest':      list.sort((a, b) => b.id - a.id); break
  }
  return list
})

// ── Alphabet sidebar ─────────────────────────────────────────────────────────

const availableLetters = computed(() => {
  const set = new Set<string>()
  for (const g of displayedGames.value) {
    const t = g.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    set.add(/[A-Z]/.test(t) ? t : '#')
  }
  return set
})

function scrollToLetter(letter: string) {
  const games = displayedGames.value
  const idx = games.findIndex(g => {
    const first = g.title.replace(/^(the|a|an)\s+/i, '').charAt(0).toUpperCase()
    return letter === '#' ? !/[A-Z]/.test(first) : first === letter
  })
  if (idx === -1) return
  activeLetter.value = letter
  const gridEl = gridScrollEl.value
  if (!gridEl) return
  const selector = viewMode.value === 'list' ? '.list-row' : '.cover-wrap'
  const cards = gridEl.querySelectorAll(selector)
  const card = cards[idx] as HTMLElement
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Card hover effects ──────────────────────────────────────────────────────

function onCardEnter(e: MouseEvent) {
  if (!themeStore.cardGlow) return
  const wrap = (e.currentTarget as HTMLElement).querySelector<HTMLElement>('.cover-img-wrap')
  wrap?.classList.add('glow-active')
}

function onCardMove(e: MouseEvent) {
  if (!themeStore.cardTilt && !themeStore.cardShine) return
  const el = e.currentTarget as HTMLElement
  const imgWrap = el.querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return
  const rect = imgWrap.getBoundingClientRect()
  if (themeStore.cardTilt) {
    const cx = rect.width / 2, cy = rect.height / 2
    const dx = e.clientX - rect.left - cx, dy = e.clientY - rect.top - cy
    const ry = (dx / cx) * 8, rx = -(dy / cy) * 5
    const zoom = themeStore.cardZoom ? 'scale3d(1.03,1.03,1.03)' : ''
    imgWrap.style.transform = `perspective(600px) rotateX(${rx}deg) rotateY(${ry}deg) ${zoom}`
  }
  const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
  if (sheen && themeStore.cardShine) {
    const mx = ((e.clientX - rect.left) / rect.width * 100).toFixed(1)
    const my = ((e.clientY - rect.top) / rect.height * 100).toFixed(1)
    sheen.style.opacity = '1'
    sheen.style.background = `radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%)`
  }
}

function onCardLeave(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const imgWrap = el.querySelector<HTMLElement>('.cover-img-wrap')
  if (!imgWrap) return
  imgWrap.style.transform = ''
  imgWrap.classList.remove('glow-active')
  const sheen = imgWrap.querySelector<HTMLElement>('.cover-sheen')
  if (sheen) sheen.style.opacity = '0'
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function listDescText(game: LibGame): string {
  const raw = (game.description_short || game.description || '').replace(/<[^>]*>/g, '').trim()
  return raw.length > 260 ? raw.slice(0, 260) + '…' : raw
}

function releaseYear(rd: string): string {
  const m = rd.match(/\b(\d{4})\b/)
  return m ? m[1] : rd.slice(0, 4)
}

// ── Navigation ───────────────────────────────────────────────────────────────

function openGame(game: LibGame) {
  router.push({ name: 'games-detail', params: { id: game.id } })
}

// ── Add Game dropdown ─────────────────────────────────────────────────────────

const addMenuOpen  = ref(false)
const addMenuRef   = ref<HTMLElement>()

function _closeAddMenu(e: MouseEvent) {
  if (!addMenuRef.value?.contains(e.target as Node)) addMenuOpen.value = false
}

// ── Torrent modal ─────────────────────────────────────────────────────────────

const torrentModal     = ref(false)
const tTab             = ref<'url' | 'file'>('url')
const tAdding          = ref(false)
const tError           = ref('')
const torrentFileInput = ref<HTMLInputElement>()

// Progress tracking after submission
const tDownloadId  = ref<number | null>(null)
const tDlPercent   = ref(0)
const tDlSpeed     = ref(0)
const tDlEta       = ref(-1)
const tDlStatus    = ref('')
const tDlComplete  = ref(false)

const tForm = ref({ title: '', os: 'windows', url: '', file: null as File | null, fileName: '' })

function openTorrentModal() {
  addMenuOpen.value = false
  tTab.value = 'url'
  tError.value = ''
  tDownloadId.value = null
  tDlPercent.value = 0
  tDlSpeed.value = 0
  tDlEta.value = -1
  tDlStatus.value = ''
  tDlComplete.value = false
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
  tDlPercent.value = data.percent ?? 0
  tDlSpeed.value   = data.speed   ?? 0
  tDlEta.value     = data.eta     ?? -1
  tDlStatus.value  = data.status  ?? ''
}

function _onTorrentComplete(data: any) {
  if (data.id !== tDownloadId.value) return
  _stopTorrentListeners()
  tDlPercent.value  = 100
  tDlComplete.value = true
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
  tForm.value.file = f
  tForm.value.fileName = f?.name ?? ''
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
  tError.value = ''
  tAdding.value = true
  try {
    let res: any
    if (tTab.value === 'url') {
      res = await client.post('/torrents/download/url', {
        url:   tForm.value.url.trim(),
        title: tForm.value.title.trim(),
        os:    tForm.value.os,
      })
    } else {
      const fd = new FormData()
      fd.append('title', tForm.value.title.trim())
      fd.append('target_os', tForm.value.os)
      fd.append('file', tForm.value.file as File)
      res = await client.post('/torrents/download/file', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    }
    tDownloadId.value = res.data.id
    tDlPercent.value  = res.data.percent ?? 0
    // Attach socket listeners for live progress
    socketStore.socket?.on('torrent:download_progress', _onTorrentProgress)
    socketStore.socket?.on('torrent:download_complete', _onTorrentComplete)
    socketStore.socket?.on('torrent:download_error',    _onTorrentError)
  } catch (e: any) {
    tError.value = e?.response?.data?.detail || 'Failed to add torrent.'
  } finally {
    tAdding.value = false
  }
}

// ── Upload modal ──────────────────────────────────────────────────────────────

const uploadModal    = ref(false)
const uUploading     = ref(false)
const uError         = ref('')
const uSuccess       = ref('')
const uProgress      = ref<number | null>(null)
const uploadFileInput = ref<HTMLInputElement>()

const uForm = ref({ title: '', os: 'windows', file_type: 'game', file: null as File | null, fileName: '', fileSize: '' })

function openUploadModal() {
  addMenuOpen.value = false
  uError.value = ''
  uSuccess.value = ''
  uProgress.value = null
  uForm.value = { title: '', os: 'windows', file_type: 'game', file: null, fileName: '', fileSize: '' }
  uploadModal.value = true
}

function fmtBytes(b: number): string {
  if (b >= 1073741824) return (b / 1073741824).toFixed(1) + ' GB'
  if (b >= 1048576)    return (b / 1048576).toFixed(0) + ' MB'
  return (b / 1024).toFixed(0) + ' KB'
}

function onUploadFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  uForm.value.file = f
  uForm.value.fileName = f?.name ?? ''
  uForm.value.fileSize = f ? fmtBytes(f.size) : ''
  if (f && !uForm.value.title.trim()) {
    uForm.value.title = f.name.replace(/\.[^.]+$/, '')
  }
}

async function submitUpload() {
  uError.value = ''
  uSuccess.value = ''
  uProgress.value = 0
  uUploading.value = true
  try {
    // Step 1: create game entry
    const gameRes = await client.post('/library/games', { title: uForm.value.title.trim() })
    const gameId = gameRes.data.id

    // Step 2: upload file to it
    const fd = new FormData()
    fd.append('os',        uForm.value.os)
    fd.append('file_type', uForm.value.file_type)
    fd.append('file',      uForm.value.file as File)
    await client.post(`/library/games/${gameId}/upload`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev) => {
        if (ev.total) uProgress.value = Math.round(ev.loaded / ev.total * 100)
      },
    })
    uSuccess.value = t('upload.success')
    await fetchGames()
    setTimeout(() => { uploadModal.value = false }, 2000)
  } catch (e: any) {
    uError.value = e?.response?.data?.detail || t('upload.failed')
  } finally {
    uUploading.value = false
  }
}

// ── Transmission enabled ──────────────────────────────────────────────────────

const transmissionEnabled = ref(false)

async function fetchTransmissionEnabled() {
  try {
    const { data } = await client.get('/torrents/enabled')
    transmissionEnabled.value = !!data.enabled
  } catch {
    transmissionEnabled.value = false
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchGames()
  fetchTransmissionEnabled()
  document.addEventListener('mousedown', _closeAddMenu)
  refreshReqBadge()
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', _closeAddMenu)
  _stopTorrentListeners()
})
</script>

<style scoped>
/* ── Classic placeholder ────────────────────────────────────────────────────── */
.classic-placeholder {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; gap: 10px; color: var(--muted); font-size: 13px;
}

/* ── Library view ────────────────────────────────────────────────────────────── */
.library-view {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  padding: 20px 28px; gap: var(--space-4, 16px);
}

/* ── Title bar ─────────────────────────────────────────────────────────────── */
.title-bar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-3, 12px); flex-shrink: 0;
  padding: 14px 20px;
  position: relative; z-index: 10;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
}
.title-left { display: flex; align-items: center; gap: var(--space-3, 12px); }
.title-ico-svg { color: #14b8a6; filter: drop-shadow(0 0 8px rgba(20,184,166,.5)); flex-shrink: 0; }
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }
.title-right { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }

/* ── Search ─────────────────────────────────────────────────────────────────── */
.search-wrap { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 9px; pointer-events: none; color: var(--muted); flex-shrink: 0; }
.search-input {
  width: 200px; padding: 6px 30px 6px 30px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px;
  font-family: inherit; outline: none; transition: all var(--transition);
}
.search-input::placeholder { color: var(--muted); }
.search-input:focus { border-color: #14b8a6; background: rgba(255,255,255,.09); width: 260px; }
.search-clear {
  position: absolute; right: 8px; background: none; border: none;
  color: var(--muted); cursor: pointer; padding: 2px;
  display: flex; align-items: center; transition: color var(--transition);
}
.search-clear:hover { color: var(--text); }

/* ── Scan button ────────────────────────────────────────────────────────────── */
.sync-wrap { display: flex; align-items: center; gap: var(--space-2, 8px); }
.sync-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition);
}
.sync-btn:not(:disabled):hover { border-color: #14b8a6; color: #2dd4bf; }
.sync-btn:disabled { opacity: .6; cursor: not-allowed; }
.sync-btn--running { border-color: #14b8a6; color: #2dd4bf; }
.sync-msg { font-size: var(--fs-sm, 12px); color: var(--muted); }
.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Sort / filter ──────────────────────────────────────────────────────────── */
.sort-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px;
  font-weight: 600; padding: 6px 10px; cursor: pointer; outline: none;
  transition: border-color var(--transition); font-family: inherit;
}
.sort-select:hover { border-color: #14b8a6; }
.sort-select option { background: var(--bg2); }

.filter-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.filter-btn:hover { border-color: #14b8a6; color: var(--text); }
.filter-btn.active { background: color-mix(in srgb, var(--pl) 15%, transparent); border-color: var(--pl); color: var(--pl-light); }
.req-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06);
  color: var(--muted); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.req-btn:hover { border-color: var(--pl); color: var(--pl-light); background: rgba(124,58,237,.1); }
.req-notify-dot {
  position: absolute; top: -5px; right: -5px;
  min-width: 17px; height: 17px; border-radius: 9px;
  background: #ef4444; color: #fff; font-size: 9px; font-weight: 800;
  display: flex; align-items: center; justify-content: center; padding: 0 4px;
  pointer-events: none; border: 2px solid var(--bg, #0f0f1a);
}

/* Cover size selector */
.size-group { display: flex; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.size-btn {
  padding: 5px 9px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
}
.size-btn + .size-btn { border-left: 1px solid var(--glass-border); }
.size-btn:hover { background: rgba(255,255,255,.1); color: var(--text); }
.size-btn.active { background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light); }

.view-toggle { display: flex; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.view-toggle button {
  padding: 6px 10px; background: rgba(255,255,255,.06); border: none;
  color: var(--muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--transition);
}
.view-toggle button:hover { background: rgba(255,255,255,.1); color: var(--text); }
.view-toggle button.active { background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light); }
.view-toggle button + button { border-left: 1px solid var(--glass-border); }

/* ── Empty / loading ────────────────────────────────────────────────────────── */
.state-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-3, 12px); color: var(--muted); font-size: var(--fs-md, 14px);
}

/* ── Main area ──────────────────────────────────────────────────────────────── */
.library-main { flex: 1; display: flex; gap: 0; overflow: hidden; min-height: 0; }
.grid-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; padding-right: 8px; min-width: 0; }

/* ── Cover grid ─────────────────────────────────────────────────────────────── */
.cover-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cover-min,175px), 1fr));
  gap: var(--space-4, 16px); padding-bottom: 20px;
}
.cover-wrap { cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.cover-img-wrap {
  position: relative; border-radius: var(--radius-sm); overflow: hidden;
  aspect-ratio: 3/4; background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.2s ease, border-color 0.2s ease;
  transform-style: preserve-3d;
}
.cover-img-wrap::after {
  content: ''; position: absolute; inset: -1px; border-radius: inherit;
  border: 1px solid #14b8a6; box-shadow: 0 0 24px rgba(20,184,166,.35), inset 0 0 16px rgba(0,0,0,.1);
  opacity: 0; transition: opacity var(--transition); pointer-events: none; z-index: 2;
}
.cover-img-wrap.glow-active::after { opacity: 1; }
.cover-sheen { position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity 0.3s; z-index: 3; }
.cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }

/* Badges */
.badge {
  position: absolute; top: 6px; right: 6px; z-index: 4;
  display: flex; align-items: center; gap: 3px;
  padding: 2px 6px; border-radius: var(--radius-xs, 4px);
  font-size: 9px; font-weight: 700; letter-spacing: .5px;
}
.badge--owned { background: rgba(74,222,128,.15); color: #4ade80; border: 1px solid rgba(74,222,128,.3); }
.badge--src { right: auto; left: 6px; }
.badge--gog { background: rgba(124,58,237,.15); color: #a78bfa; border: 1px solid rgba(124,58,237,.25); }
.badge--custom { background: rgba(20,184,166,.12); color: #2dd4bf; border: 1px solid rgba(20,184,166,.3); }

.cover-overlay {
  position: absolute; inset: 0; z-index: 5;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.2) 50%, transparent 100%);
  display: flex; flex-direction: column; justify-content: flex-end;
  padding: 10px; opacity: 0; transition: opacity .18s;
}
.cover-wrap:hover .cover-overlay,
.list-cover-wrap:hover .cover-overlay { opacity: 1; }
.overlay-title { font-size: var(--fs-sm, 12px); font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 6px; }

.cover-title { font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cover-scores { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cover-score { display: inline-flex; align-items: center; gap: var(--space-1, 4px); font-size: 11px; color: var(--muted); }
.score-ico { image-rendering: pixelated; opacity: .85; flex-shrink: 0; }

/* ── Alphabet sidebar ──────────────────────────────────────────────────────── */
.alpha-nav {
  width: 22px; flex-shrink: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 1px; padding: 6px 0; user-select: none;
}
.alpha-btn {
  width: 20px; height: 18px; display: flex; align-items: center; justify-content: center;
  font-size: var(--fs-xs, 10px); font-weight: 700; color: rgba(255,255,255,.18);
  background: none; border: none; border-radius: var(--radius-xs, 4px); cursor: pointer;
  transition: all .12s; font-family: inherit; padding: 0; line-height: 1;
}
.alpha-btn.available { color: var(--muted); }
.alpha-btn.available:hover { color: var(--text); background: rgba(255,255,255,.06); }
.alpha-btn.active { color: var(--pl-light); background: color-mix(in srgb, var(--pl) 18%, transparent); }

/* ── List view ──────────────────────────────────────────────────────────────── */
.list-view { display: flex; flex-direction: column; gap: var(--space-2, 8px); padding-bottom: 20px; }
.list-row {
  display: flex; align-items: stretch; gap: 0;
  padding: 0; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: var(--glass-bg);
  cursor: pointer; transition: all var(--transition); overflow: hidden;
  height: 260px;
}
.list-row:hover { background: var(--glass-highlight); border-color: color-mix(in srgb, var(--pl) 30%, transparent); }

.list-cover-wrap { flex-shrink: 0; width: 200px; padding: 10px; box-sizing: border-box; }
.list-cover-wrap .cover-img-wrap {
  width: 100%; height: 240px; border-radius: var(--radius-sm, 8px); overflow: hidden;
  background: var(--bg2); border: 1px solid var(--glass-border);
  box-shadow: 0 6px 24px rgba(0,0,0,0.45); position: relative;
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.2s ease;
  transform-style: preserve-3d;
}
.list-cover-wrap .cover-img-wrap::after {
  content: ''; position: absolute; inset: -1px; border-radius: inherit;
  border: 1px solid #14b8a6; box-shadow: 0 0 24px rgba(20,184,166,.3);
  opacity: 0; transition: opacity var(--transition); pointer-events: none; z-index: 2;
}
.list-cover-wrap .cover-img-wrap.glow-active::after { opacity: 1; }
.list-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.list-cover-fallback { width: 100%; height: 100%; background: var(--bg3); }

.list-info {
  flex-shrink: 0; width: 200px; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: center;
  text-align: center; align-items: center; gap: var(--space-1, 4px);
  padding: 10px 16px; border-left: 1px solid var(--glass-border);
}
.list-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); overflow: hidden; min-height: 20px; }
.list-title > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.list-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 6px; }
.meta-sep::before { content: '·'; margin-right: 6px; }

.list-hero {
  flex: 1; min-width: 0; overflow: hidden;
  position: relative; border-left: 1px solid var(--glass-border);
}
.list-hero-img {
  position: absolute; inset: 0;
  width: 100%; height: 100%; object-fit: cover; display: block;
  filter: brightness(.30);
}
.list-hero-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to right, rgba(0,0,0,.5) 0%, rgba(0,0,0,.2) 50%, rgba(0,0,0,.5) 100%);
}
.list-hero-desc {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  padding: 16px 24px; z-index: 2;
}
.list-hero-desc-text {
  margin: 0; font-size: var(--fs-sm, 12px); line-height: 1.7; color: rgba(255,255,255,.8);
  text-align: center; display: -webkit-box; -webkit-line-clamp: 7;
  -webkit-box-orient: vertical; overflow: hidden;
  text-shadow: 0 1px 4px rgba(0,0,0,.6);
}
.list-hero-img--kenburns {
  animation: list-kb calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.list-hero-img--drift {
  animation: list-drift calc(30s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.list-hero-img--pulse {
  animation: list-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
@keyframes list-kb {
  0%   { transform: scale(1.05) translateX(0); }
  50%  { transform: scale(1.12) translateX(-3%); }
  100% { transform: scale(1.05) translateX(0); }
}
@keyframes list-drift {
  0%   { transform: translateX(0) scale(1.04); }
  50%  { transform: translateX(-4%) scale(1.04); }
  100% { transform: translateX(0) scale(1.04); }
}
@keyframes list-pulse {
  0%,100% { transform: scale(1.02); }
  50%     { transform: scale(1.08); }
}
[data-animations="false"] .list-hero-img--kenburns,
[data-animations="false"] .list-hero-img--drift,
[data-animations="false"] .list-hero-img--pulse { animation: none; }
.genre-chip { padding: 1px 7px; border-radius: var(--radius-xs, 4px); font-size: var(--fs-xs, 10px); }

.list-qf-col { flex-shrink: 0; width: 230px; border-left: 1px solid var(--glass-border); padding: 10px 12px; display: flex; align-items: center; justify-content: center; }
.list-qf { display: flex; flex-direction: column; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; width: 100%; }
.list-qf-row { display: flex; align-items: center; border-bottom: 1px solid var(--glass-border); min-height: 26px; }
.list-qf-row:last-child { border-bottom: none; }
.list-qf-label { flex-shrink: 0; width: 100px; padding: 4px 8px; font-size: 9px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; border-right: 1px solid var(--glass-border); background: rgba(255,255,255,.04); white-space: nowrap; line-height: 1.3; display: flex; align-items: center; align-self: stretch; }
.list-qf-val { flex: 1; padding: 4px 8px; font-size: 11px; color: var(--text); line-height: 1.3; display: flex; flex-wrap: wrap; gap: 3px; align-items: center; justify-content: center; text-align: center; }
.list-qf-os { gap: var(--space-1, 4px); }
.list-os-chip { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 5px; background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); }
.list-os-chip--win { color: #60a5fa; }
.list-os-chip--mac { color: #c4b5fd; }
.list-os-chip--linux { color: #facc15; }
.src-gog { color: #a78bfa !important; }
.src-custom { color: #2dd4bf !important; }

.list-right { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; flex-shrink: 0; min-width: 100px; border-left: 1px solid var(--glass-border); padding: 10px 16px; }
.list-scores { display: flex; flex-direction: column; gap: var(--space-2, 8px); align-items: center; }
.list-score { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: 15px; font-weight: 700; color: var(--text); white-space: nowrap; }
.list-score .score-ico { width: 42px; height: 42px; }
.list-score svg { width: 24px; height: 24px; }

/* ── Add Game dropdown ──────────────────────────────────────────────────────── */
.add-game-wrap { position: relative; }
.add-game-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500;
  cursor: pointer; border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  background: color-mix(in srgb, var(--pl) 18%, transparent); color: var(--pl-light);
  transition: background var(--transition); font-family: inherit;
}
.add-game-btn:hover { background: color-mix(in srgb, var(--pl) 32%, transparent); }
.add-game-dropdown {
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 900;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); overflow: hidden;
  backdrop-filter: blur(var(--glass-blur-px, 20px)); min-width: 170px;
  box-shadow: 0 8px 24px rgba(0,0,0,.4);
}
.add-game-option {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 10px 14px; font-size: 13px;
  color: var(--text); background: transparent; border: none; cursor: pointer;
  font-family: inherit; transition: background .12s;
}
.add-game-option:hover { background: rgba(255,255,255,.07); }

/* ── Modals ──────────────────────────────────────────────────────────────────── */
.gl-modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.gl-modal {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius); width: 520px; max-width: 95vw;
  box-shadow: 0 20px 60px rgba(0,0,0,.6);
  display: flex; flex-direction: column;
}
.gl-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--glass-border);
}
.gl-modal-title { font-size: 15px; font-weight: 600; color: var(--text); }
.gl-modal-close {
  background: none; border: none; color: var(--muted); cursor: pointer;
  display: flex; align-items: center; padding: 2px;
  border-radius: var(--radius-xs, 4px); transition: color .15s;
}
.gl-modal-close:hover { color: var(--text); }
.gl-modal-body  { padding: var(--space-5, 20px); display: flex; flex-direction: column; gap: 14px; }
.gl-modal-footer {
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
  display: flex; justify-content: flex-end; gap: var(--space-2, 8px);
}

.gl-field-row { display: flex; gap: var(--space-3, 12px); }
.gl-field     { display: flex; flex-direction: column; gap: 5px; flex: 1; }
.gl-field--sm { flex: 0 0 140px; }
.gl-label     { font-size: 11px; font-weight: 600; color: var(--text-secondary, var(--muted)); text-transform: uppercase; letter-spacing: .4px; }
.gl-input {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 7px 10px;
  color: var(--text); font-size: 13px; outline: none; font-family: inherit;
  transition: border-color .15s; width: 100%; box-sizing: border-box;
}
.gl-input:focus { border-color: rgba(139,92,246,.6); }
.gl-input--file { cursor: pointer; }
.gl-file-name   { font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.gl-tabs { display: flex; gap: var(--space-1, 4px); border-bottom: 1px solid var(--glass-border); padding-bottom: 0; }
.gl-tab {
  padding: 6px 14px; font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: none; border: none; border-bottom: 2px solid transparent;
  cursor: pointer; font-family: inherit; margin-bottom: -1px; transition: color .15s, border-color .15s;
}
.gl-tab--active { color: var(--pl-light); border-bottom-color: var(--pl-light); }

.gl-progress-wrap {
  height: 4px; background: rgba(255,255,255,.08); border-radius: 2px; overflow: hidden; position: relative;
}
.gl-progress-bar  { height: 100%; background: #a78bfa; border-radius: 2px; transition: width .3s; }
.gl-progress-label { font-size: 11px; color: var(--muted); margin-top: 4px; display: block; }

.gl-error   { font-size: var(--fs-sm, 12px); color: #f87171; }
.gl-success { font-size: var(--fs-sm, 12px); color: #4ade80; }

/* Torrent download progress */
.gl-torrent-progress { display: flex; flex-direction: column; gap: 10px; }
.gl-tp-title { display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 600; color: var(--text); }
.gl-tp-bar-wrap { height: 6px; background: var(--glass-border); border-radius: 3px; overflow: hidden; }
.gl-tp-bar { height: 100%; background: var(--primary, #7c3aed); border-radius: 3px; transition: width .5s ease; }
.gl-tp-bar--done { background: #4ade80; }
.gl-tp-meta { display: flex; gap: var(--space-3, 12px); font-size: 11px; color: var(--muted); }
.gl-tp-pct { font-weight: 700; color: var(--text); }

.gl-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 16px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 500; cursor: pointer; border: none; font-family: inherit;
  transition: background .15s, opacity .15s;
}
.gl-btn:disabled { opacity: .5; cursor: not-allowed; }
.gl-btn--primary { background: color-mix(in srgb, var(--pl) 20%, transparent); color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 45%, transparent); }
.gl-btn--primary:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }
.gl-btn--ghost   { background: rgba(255,255,255,.05); color: var(--text); border: 1px solid var(--glass-border); }
.gl-btn--ghost:not(:disabled):hover   { background: rgba(255,255,255,.1); }

.gl-spinner {
  width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor; border-radius: 50%;
  animation: spin .7s linear infinite; display: inline-block;
}

/* ── Library back button ─────────────────────────────────────────────────────── */
.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
  cursor: pointer; font-family: inherit; transition: all var(--transition);
  margin-right: 8px; flex-shrink: 0;
}
.lib-back-btn:hover { color: var(--text); background: rgba(255,255,255,.1); }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .title-bar { padding: 10px 12px; gap: var(--space-2, 8px); }
  .title-ico { width: 36px; height: 36px; }
  .title-text { font-size: 15px; }
  .title-right { gap: 6px; }
  .sort-select { font-size: 11px; padding: 4px 6px; }
  .size-group { display: none; }
  .cover-grid { gap: 10px; --cover-min: 120px; }
}

</style>
