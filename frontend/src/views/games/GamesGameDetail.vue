<template>
  <div class="gd-root">

    <!-- ── Skeleton ─────────────────────────────────────────────────────────── -->
    <template v-if="loading">
      <div class="sk-hero" />
      <div class="sk-body">
        <div class="sk-line sk-line--xl" /><div class="sk-line sk-line--md" />
        <div class="sk-line sk-line--sm" /><div class="sk-line sk-line--lg" />
      </div>
    </template>

    <!-- ── Not found ────────────────────────────────────────────────────────── -->
    <div v-else-if="!game" class="gd-empty">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.18">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
      <p>{{ t('detail.game_not_found') }}</p>
      <button class="gd-back-pill" @click="router.back()">{{ t('detail.back_to_library') }}</button>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN                                                                    -->
    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- ── HERO ─────────────────────────────────────────────────────────── -->
      <div class="gd-hero">
        <HeroBackground
          :src="bgSrc"
          :anim-style="themeStore.heroAnimStyle"
          :anim-enabled="themeStore.heroAnim && themeStore.animations"
        />

        <button class="gd-back-pill" @click="router.back()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('nav.games_library') }}
        </button>

        <div class="gd-hero-inner">
          <!-- Cover with 3D tilt effect -->
          <div class="gd-cover-col">
            <div
              class="gd-cover-frame"
              :style="{ transform: coverTilt, willChange: 'transform' }"
              @mousemove="onCoverMove"
              @mouseleave="onCoverLeave"
              @mouseenter="onCoverEnter"
            >
              <img
                v-if="!coverFailed && game.cover_path"
                :src="game.cover_path"
                :alt="game.title"
                class="gd-cover-img"
                @error="coverFailed = true"
              />
              <div v-else class="gd-cover-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                </svg>
              </div>
              <!-- Specular sheen following mouse -->
              <div class="gd-cover-sheen" :style="sheenStyle" />
            </div>
          </div>

          <!-- Info -->
          <div class="gd-info-col">

            <!-- Logo image (SteamGridDB transparent logo) or text title -->
            <img
              v-if="game.logo_path"
              :src="game.logo_path"
              :alt="game.title"
              class="gd-logo-img"
            />
            <h1 v-else class="gd-title">{{ game.title }}</h1>

            <!-- Source badge -->
            <div class="source-badge" :class="'source-' + game.source">
              {{ game.source === 'gog' ? 'GOG' : 'Custom' }}
            </div>

            <div class="gd-meta-row">
              <span v-if="game.developer" class="gd-meta-item">{{ game.developer }}</span>
              <span v-if="game.publisher && game.publisher !== game.developer" class="gd-meta-sep">·</span>
              <span v-if="game.publisher && game.publisher !== game.developer" class="gd-meta-item">{{ game.publisher }}</span>
              <span v-if="game.release_date" class="gd-meta-sep">·</span>
              <span v-if="game.release_date" class="gd-meta-item">{{ game.release_date.slice(0, 4) }}</span>
            </div>

            <!-- GOG Rating stars -->
            <div v-if="game.rating" class="gd-rating-row">
              <svg v-for="i in 5" :key="i" width="16" height="16" viewBox="0 0 24 24"
                :fill="i <= Math.round(game.rating) ? '#f59e0b' : 'rgba(255,255,255,.12)'"
                :stroke="i <= Math.round(game.rating) ? '#f59e0b' : 'rgba(255,255,255,.2)'"
                stroke-width="1"
              >
                <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
              </svg>
              <span class="gd-rating-num">{{ game.rating.toFixed(1) }}</span>
            </div>

            <!-- External ratings (RAWG / IGDB / Metacritic) -->
            <div v-if="externalRatings.rawg || externalRatings.igdb || externalRatings.steam || externalRatings.plugins?.length" class="gd-ext-ratings">
              <div v-if="externalRatings.rawg" class="gd-ext-score">
                <img src="/icons/RAWG.ico" class="gd-ext-ico" width="42" height="42" alt="RAWG" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ externalRatings.rawg.toFixed(1) }}<span class="gd-ext-max">/5</span></span>
                  <span class="gd-ext-lbl">RAWG</span>
                </div>
              </div>
              <div v-if="externalRatings.igdb" class="gd-ext-score">
                <img src="/icons/igdb.ico" class="gd-ext-ico" width="42" height="42" alt="IGDB" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ Math.round(externalRatings.igdb) }}<span class="gd-ext-max">/100</span></span>
                  <span class="gd-ext-lbl">IGDB</span>
                </div>
              </div>
              <div v-if="externalRatings.steam" class="gd-ext-score">
                <img src="/icons/metacritic.svg" class="gd-ext-ico" width="42" height="42" alt="Metacritic" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ Math.round(externalRatings.steam * 10) }}<span class="gd-ext-max">/100</span></span>
                  <span class="gd-ext-lbl">Metacritic</span>
                </div>
              </div>
              <div v-for="pr in (externalRatings.plugins || [])" :key="pr.id" class="gd-ext-score">
                <img :src="pr.logo" class="gd-ext-ico" width="42" height="42" :alt="pr.name" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ pr.rating.toFixed(1) }}<span class="gd-ext-max">/10</span></span>
                  <span class="gd-ext-lbl">{{ pr.name }}</span>
                </div>
              </div>
            </div>

            <!-- Genres -->
            <div v-if="game.genres?.length" class="gd-tag-row">
              <span v-for="g in (game.genres || []).slice(0, 5)" :key="g" class="gd-genre-tag">{{ g }}</span>
            </div>

            <!-- OS chips -->
            <div class="gd-os-row">
              <span v-if="game.os_windows" class="gd-os-chip">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                </svg>
                Windows
              </span>
              <span v-if="game.os_mac" class="gd-os-chip">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.71,19.5C17.88,20.74 17,21.95 15.66,21.97C14.32,22 13.89,21.18 12.37,21.18C10.84,21.18 10.37,21.95 9.1,22C7.78,22.05 6.8,20.68 5.96,19.47C4.25,17 2.94,12.45 4.7,9.39C5.57,7.87 7.13,6.91 8.82,6.88C10.1,6.86 11.32,7.75 12.11,7.75C12.89,7.75 14.37,6.68 15.92,6.84C16.57,6.87 18.39,7.1 19.56,8.82C19.47,8.88 17.39,10.1 17.41,12.63C17.44,15.65 20.06,16.66 20.09,16.67C20.06,16.74 19.67,18.11 18.71,19.5M13,3.5C13.73,2.67 14.94,2.04 15.94,2C16.07,3.17 15.6,4.35 14.9,5.19C14.21,6.04 13.07,6.7 11.95,6.61C11.8,5.46 12.36,4.26 13,3.5Z"/>
                </svg>
                macOS
              </span>
              <span v-if="game.os_linux" class="gd-os-chip">
                <img src="/icons/os-linux.svg" width="28" height="28" alt="Linux" style="flex-shrink:0" />
                Linux
              </span>
            </div>

            <!-- Action buttons -->
            <div class="gd-actions">
              <!-- Download -->
              <button
                v-if="availableFiles.length"
                class="gd-btn-dl"
                @click="showDownload = true"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M12 2v10m0 0l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.56 21H19.44a2 2 0 0 0 1.94-1.515L22 17"/>
                </svg>
                {{ t('detail.download') }}
                <span class="btn-file-count">{{ t('detail.file_count', { count: availableFiles.length }) }}</span>
              </button>
              <span v-else class="gd-no-files">{{ t('detail.no_files') }}</span>

              <!-- Torrent -->
              <button
                v-if="availableFiles.length && transmissionEnabled"
                class="gd-btn-torrent"
                :disabled="heroTorrentBusy"
                @click="openTorrentPicker"
                title="Download via torrent"
              >
                <span v-if="heroTorrentBusy" class="gd-spinner" />
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>
                </svg>
                Torrent
              </button>

              <!-- Edit Metadata -->
              <button v-if="canEdit" class="gd-btn-ghost" @click="showEditPanel = !showEditPanel" :title="t('detail.edit_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t('detail.edit_metadata') }}
              </button>

              <!-- Refresh Metadata (scrape) -->
              <button v-if="canEdit" class="gd-btn-ghost" :disabled="scraping" @click="onScrapeClick" title="Fetch metadata from GOG, Steam, RAWG, IGDB">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ spin: scraping }">
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                {{ scraping ? t('detail.scraping') : t('detail.refresh_metadata') }}
              </button>

              <!-- Clear Metadata -->
              <button v-if="isAdmin" class="gd-btn-danger" :disabled="clearing" @click="onClearMetadataClick" title="Remove all scraped metadata">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                  <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
                </svg>
                {{ clearing ? t('detail.clearing') : t('detail.clear_metadata') }}
              </button>

              <!-- Unpublish / Republish / Delete -->
              <button v-if="isAdmin && game.is_active" class="gd-btn-unpublish" @click="unpublishGame" :title="t('detail.unpublish')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                {{ t('detail.unpublish') }}
              </button>
              <button v-if="isAdmin && !game.is_active" class="gd-btn-publish" @click="republishGame" :title="t('detail.publish')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                {{ t('detail.publish') }}
              </button>
              <button v-if="isAdmin" class="gd-btn-danger" @click="deleteGame" :title="t('common.delete')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                {{ t('common.delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Hero → body separator ──────────────────────────────────────── -->
      <div class="gd-separator" />

      <!-- ── BODY ─────────────────────────────────────────────────────────── -->
      <div class="gd-body">

        <!-- ── Media: Screenshots carousel ──────────────────────────────── -->
        <div v-if="hasMedia" class="gd-media-section">
          <div class="gd-section-label">{{ t('detail.media') }}</div>
          <div class="gd-carousel-wrap">
            <button class="gd-carr-btn gd-carr-btn--left" :disabled="carouselIdx === 0" @click="slideTo(carouselIdx - 1)">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <div class="gd-carousel" ref="carouselEl">
              <div
                v-for="(slide, idx) in carouselSlides"
                :key="idx"
                class="gd-slide"
                :class="{ 'gd-slide--active': idx === carouselIdx }"
                @click="onSlideClick(slide, idx)"
              >
                <template v-if="slide.type === 'video'">
                  <img :src="slide.src" :alt="'Trailer'" loading="lazy" />
                  <div class="gd-slide-play">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="white"><polygon points="5,3 19,12 5,21"/></svg>
                  </div>
                  <div class="gd-slide-badge">▶ {{ t('detail.trailer') }}</div>
                </template>
                <img v-else :src="slide.src" :alt="`Screenshot ${idx}`" loading="lazy" />
              </div>
            </div>
            <button class="gd-carr-btn gd-carr-btn--right"
              :disabled="carouselSlides.length <= 3 || carouselIdx >= carouselSlides.length - 3"
              @click="slideTo(carouselIdx + 1)">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <div class="gd-dots">
            <span
              v-for="(_, i) in carouselSlides"
              :key="i"
              class="gd-dot-item"
              :class="{ active: i === carouselIdx }"
              @click="slideTo(i)"
            />
          </div>
        </div>

        <!-- ── Two-column: Description + Files ──────────────────────────── -->
        <div class="gd-cols">

          <!-- Left: Description -->
          <div class="gd-col-left">
            <div v-if="game.description">
              <div class="gd-section-label">{{ t('detail.about') }}</div>
              <div class="gd-desc-wrap" :class="{ 'gd-desc--collapsed': !descExpanded && descOverflow }">
                <div class="gd-desc-html" v-html="sanitizeHtml(game.description)" />
              </div>
              <button v-if="descOverflow" class="gd-readmore" @click="descExpanded = !descExpanded">
                {{ descExpanded ? t('detail.read_less') : t('detail.read_more') }}
              </button>
            </div>
          </div>

          <!-- Right: Details + Files -->
          <div class="gd-col-right">

            <!-- Details grid -->
            <div class="gd-section-label">{{ t('detail.details') }}</div>
            <div class="gd-dlist">
              <template v-if="game.release_date">
                <span class="gd-dk">{{ t('detail.released') }}</span>
                <span class="gd-dv">{{ formatDate(game.release_date) }}</span>
              </template>
              <template v-if="totalSize">
                <span class="gd-dk">{{ t('detail.size') }}</span>
                <span class="gd-dv gd-mono">{{ totalSize }}</span>
              </template>
              <template v-if="game.developer">
                <span class="gd-dk">{{ t('detail.developer') }}</span>
                <span class="gd-dv">{{ game.developer }}</span>
              </template>
              <template v-if="game.publisher && game.publisher !== game.developer">
                <span class="gd-dk">{{ t('detail.publisher') }}</span>
                <span class="gd-dv">{{ game.publisher }}</span>
              </template>
              <template v-if="game.owner_username">
                <span class="gd-dk">{{ t('detail.owner') }}</span>
                <span class="gd-dv gd-owner-cell">
                  <svg class="gd-owner-crown" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M5 16L3 5l5.5 5L12 4l3.5 6L21 5l-2 11H5zm0 2h14v2H5v-2z"/></svg>
                  {{ game.owner_username }}
                </span>
              </template>
              <template v-if="(game.genres || []).length">
                <span class="gd-dk">{{ t('detail.genres') }}</span>
                <div class="gd-dv gd-tag-inline">
                  <span v-for="g in (game.genres || [])" :key="g" class="gd-itag">{{ g }}</span>
                </div>
              </template>
              <template v-if="(game.tags || []).length">
                <span class="gd-dk">{{ t('detail.tags') }}</span>
                <div class="gd-dv gd-tag-inline">
                  <span v-for="t in (game.tags || []).slice(0, 8)" :key="t" class="gd-itag">{{ t }}</span>
                </div>
              </template>
              <template v-if="(game.features || []).length">
                <span class="gd-dk">{{ t('detail.features') }}</span>
                <div class="gd-dv gd-tag-inline">
                  <span v-for="f in (game.features || [])" :key="f" class="gd-itag">{{ f }}</span>
                </div>
              </template>
              <template v-if="gameLangs.length">
                <span class="gd-dk">{{ t('detail.languages') }}</span>
                <div class="gd-dv gd-lang-flags">
                  <span v-for="l in gameLangs" :key="l.name" class="gd-lang-flag" :title="l.name">
                    <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span>
                    <span v-else>{{ l.name }}</span>
                  </span>
                </div>
              </template>
              <template v-if="game.hltb_main_s || game.hltb_complete_s">
                <span class="gd-dk">{{ t('detail.time_to_beat') }}</span>
                <span class="gd-dv" style="display:flex;flex-direction:column;gap:1px">
                  <span v-if="game.hltb_main_s">{{ t('detail.hltb_main') }} {{ fmtHltb(game.hltb_main_s) }}</span>
                  <span v-if="game.hltb_complete_s">{{ t('detail.hltb_complete') }} {{ fmtHltb(game.hltb_complete_s) }}</span>
                </span>
              </template>
              <template v-if="game.source">
                <span class="gd-dk">{{ t('detail.source') }}</span>
                <span class="gd-dv">{{ game.source === 'gog' ? 'GOG' : 'Custom' }}</span>
              </template>
            </div>

            <!-- Minimum Requirements (Windows) -->
            <template v-if="reqRows.length">
              <div class="gd-section-label" style="margin-top:28px">{{ t('detail.min_requirements') }}</div>
              <div class="gd-dlist">
                <template v-for="[k, v] in reqRows" :key="k">
                  <span class="gd-dk">{{ formatReqKey(k) }}</span>
                  <span class="gd-dv">{{ v }}</span>
                </template>
              </div>
            </template>

          </div>

        </div><!-- /gd-cols -->

        <!-- Admin: file management -->
        <section v-if="isAdmin" class="gd-section gd-admin-section">
          <h2 class="gd-section-title">
            {{ t('detail.file_management') }}
            <span class="admin-badge">Admin</span>
          </h2>
          <div class="admin-files-list">
            <div v-for="f in game.files" :key="f.id" class="admin-file-row">
              <div class="admin-file-info">
                <span class="admin-file-name">{{ f.filename }}</span>
                <span class="files-type-badge" :class="'type-' + f.file_type">{{ f.file_type }}</span>
                <span class="admin-file-os">{{ f.os }}</span>
                <span class="files-size">{{ formatSize(f.size_bytes) }}</span>
                <span class="source-micro">{{ f.source }}</span>
              </div>
              <div class="admin-file-actions">
                <button
                  class="toggle-avail-btn"
                  :class="{ available: f.is_available }"
                  @click="toggleFileAvailability(f)"
                  :title="f.is_available ? 'Disable' : 'Enable'"
                >
                  {{ f.is_available ? t('detail.available') : t('detail.hidden') }}
                </button>
              </div>
            </div>
          </div>

        </section>

      </div>

    </template>

    <!-- ── Download Dialog ─────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showDownload && game" class="dl-overlay" @click.self="showDownload = false">
        <div class="dl-dialog glass">
          <div class="dl-header">
            <div class="dl-title">{{ t('detail.download_title', { title: game.title }) }}</div>
            <button class="dl-close" @click="showDownload = false">×</button>
          </div>

          <!-- OS selector tabs -->
          <div class="dl-os-tabs">
            <button
              v-for="os in availableOSes"
              :key="os"
              class="dl-os-tab"
              :class="{ active: selectedOs === os }"
              @click="selectedOs = os"
            >
              {{ osLabel(os) }}
            </button>
          </div>

          <!-- Files for selected OS -->
          <div class="dl-files">
            <div v-for="typeGroup in filesByOsAndType" :key="typeGroup.type" class="dl-type-section">
              <div class="dl-type-head">{{ typeGroup.type === 'game' ? t('detail.type_game') : typeGroup.type === 'extra' ? t('detail.type_extras') : t('detail.type_dlc') }}</div>
              <div
                v-for="f in typeGroup.files"
                :key="f.id"
                class="dl-file-row"
              >
                <label class="dl-file-check">
                  <input type="checkbox" :checked="selectedFiles.has(f.id)" @change="toggleSelect(f.id)" />
                  <span class="dl-file-name">{{ f.display_name || f.filename }}</span>
                </label>
                <div class="dl-file-meta">
                  <span v-if="f.version" class="dl-file-ver">v{{ f.version }}</span>
                  <span class="dl-file-size">{{ formatSize(f.size_bytes) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="dl-footer">
            <span class="dl-selected-info">{{ t('detail.files_selected', { count: selectedFiles.size }) }}</span>
            <button class="dl-btn" :disabled="selectedFiles.size === 0 || downloading" @click="startDownload">
              <div v-if="downloading" class="btn-spinner btn-spinner--sm" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              {{ t('detail.download_selected') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Torrent file picker ─────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showTorrentPicker && game" class="dl-overlay" @click.self="showTorrentPicker = false">
        <div class="dl-dialog glass">
          <div class="dl-header">
            <div class="dl-title">{{ t('detail.torrent_title', { title: game.title }) }}</div>
            <button class="dl-close" @click="showTorrentPicker = false">×</button>
          </div>

          <div class="dl-os-tabs">
            <button
              v-for="os in availableOSes"
              :key="os"
              class="dl-os-tab"
              :class="{ active: selectedOs === os }"
              @click="selectedOs = os"
            >{{ osLabel(os) }}</button>
          </div>

          <div class="dl-files">
            <div v-for="typeGroup in filesByOsAndType" :key="typeGroup.type" class="dl-type-section">
              <div class="dl-type-head">{{ typeGroup.type === 'game' ? t('detail.type_game') : typeGroup.type === 'extra' ? t('detail.type_extras') : t('detail.type_dlc') }}</div>
              <div v-for="f in typeGroup.files" :key="f.id" class="dl-file-row">
                <label class="dl-file-check">
                  <input type="checkbox" :checked="torrentPickerSel.has(f.id)" @change="toggleTorrentFile(f.id)" />
                  <span class="dl-file-name">{{ f.display_name || f.filename }}</span>
                </label>
                <div class="dl-file-meta">
                  <span v-if="f.version" class="dl-file-ver">v{{ f.version }}</span>
                  <span class="dl-file-size">{{ formatSize(f.size_bytes) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="dl-footer">
            <span class="dl-selected-info">{{ t('detail.files_selected', { count: torrentPickerSel.size }) }}</span>
            <button class="dl-btn dl-btn--torrent" :disabled="torrentPickerSel.size === 0 || heroTorrentBusy" @click="downloadTorrentHero">
              <span v-if="heroTorrentBusy" class="btn-spinner btn-spinner--sm" />
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/></svg>
              {{ t('detail.download_torrent') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Lightbox ────────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="lightboxIdx !== null" class="gd-lb" @click.self="lightboxIdx = null">
        <button class="gd-lb-close" @click="lightboxIdx = null">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <button v-if="lightboxIdx > 0" class="gd-lb-arrow gd-lb-arrow--l" @click="lightboxIdx--">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <img :src="(game?.screenshots || [])[lightboxIdx]" class="gd-lb-img" />
        <button v-if="lightboxIdx < (game?.screenshots || []).length - 1" class="gd-lb-arrow gd-lb-arrow--r" @click="lightboxIdx++">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="gd-lb-counter">{{ lightboxIdx + 1 }} / {{ (game?.screenshots || []).length }}</div>
      </div>
    </Teleport>

    <!-- ── Video modal ────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="videoModalOpen && ytVideos[0]" class="gd-lb" @click.self="videoModalOpen = false" @keydown.esc="videoModalOpen = false">
        <button class="gd-lb-close" @click="videoModalOpen = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <div class="gd-video-frame">
          <iframe
            :src="`https://www.youtube.com/embed/${ytVideos[0].video_id}?autoplay=1`"
            frameborder="0"
            allow="autoplay; encrypted-media"
            allowfullscreen
          />
        </div>
      </div>
    </Teleport>

    <!-- ── Edit Metadata panel ─────────────────────────────────────────────── -->
    <Teleport to="body">
      <LibraryMetadataPanel
        v-if="showEditPanel && game"
        :game="game"
        @close="showEditPanel = false"
        @saved="onMetadataSaved"
      />
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import client from '@/services/api/client'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import { sanitizeHtml } from '@/utils/sanitize'
import TranslateButton from '@/components/common/TranslateButton.vue'
import HeroBackground from '@/components/common/HeroBackground.vue'
import { useDialog } from '@/composables/useDialog'
import { buildLanguageList } from '@/utils/langMap'
import { useI18n } from '@/i18n'

interface LibFile {
  id: number
  filename: string
  display_name: string
  file_type: string
  os: string
  language: string | null
  version: string | null
  size_bytes: number | null
  file_path: string
  source: string
  is_available: boolean
}

interface LibGame {
  id: number
  title: string
  slug: string
  source: string
  description: string | null
  description_short: string | null
  developer: string | null
  publisher: string | null
  release_date: string | null
  cover_path: string | null
  background_path: string | null
  logo_path: string | null
  icon_path: string | null
  genres: string[] | null
  tags: string[] | null
  features: string[] | null
  rating: number | null
  meta_ratings: Record<string, number> | null
  os_windows: boolean
  os_mac: boolean
  os_linux: boolean
  languages: Record<string, string> | null
  requirements: Record<string, any> | null
  screenshots: string[] | null
  videos: { provider: string; video_id: string; thumbnail_id?: string }[] | null
  hltb_main_s: number | null
  hltb_complete_s: number | null
  is_active: boolean
  owner_username: string | null
  files: LibFile[]
}

const route       = useRoute()
const router      = useRouter()
const auth        = useAuthStore()
const themeStore  = useThemeStore()
const { gdConfirm, gdAlert } = useDialog()
const { t }       = useI18n()

const isAdmin    = computed(() => auth.user?.role === 'admin')

const isUploader = computed(() => ['admin','uploader'].includes(auth.user?.role as string))
const canEdit    = computed(() => ['admin','uploader','editor'].includes(auth.user?.role as string))

const game       = ref<LibGame | null>(null)
const loading    = ref(true)
const coverFailed = ref(false)
const scraping   = ref(false)
const clearing   = ref(false)

// ── Languages (deduplicated, with flags) ─────────────────────────────────────
const gameLangs = computed(() => buildLanguageList(game.value?.languages))

// ── Background / hero ─────────────────────────────────────────────────────────

const bgSrc = computed(() => (
  game.value?.background_path || game.value?.cover_path || ''
))

// ── Files ─────────────────────────────────────────────────────────────────────

const availableFiles = computed(() =>
  (game.value?.files ?? []).filter(f => f.is_available)
)

// ── Download dialog ───────────────────────────────────────────────────────────

const showDownload  = ref(false)
const selectedOs    = ref('windows')
const selectedFiles = ref<Set<number>>(new Set())
const downloading   = ref(false)

const availableOSes = computed(() => {
  const oses = new Set(availableFiles.value.map(f => f.os))
  const order = ['windows', 'mac', 'linux', 'all']
  return order.filter(o => oses.has(o))
})

const filesByOsAndType = computed(() => {
  const os = selectedOs.value
  const files = availableFiles.value.filter(f => f.os === os || f.os === 'all')
  const byType: Record<string, LibFile[]> = {}
  for (const f of files) {
    if (!byType[f.file_type]) byType[f.file_type] = []
    byType[f.file_type].push(f)
  }
  const typeOrder = ['game', 'dlc', 'extra']
  return typeOrder.filter(t => byType[t]).map(t => ({ type: t, files: byType[t] }))
})

watch(availableOSes, (oses) => {
  if (oses.length && !oses.includes(selectedOs.value)) {
    selectedOs.value = oses[0]
  }
}, { immediate: true })

watch(selectedOs, () => selectedFiles.value.clear())

watch(showDownload, (open) => {
  if (open) {
    selectedFiles.value.clear()
    // Pre-select game files for current OS
    const gameFiles = filesByOsAndType.value.find(g => g.type === 'game')?.files ?? []
    gameFiles.forEach(f => selectedFiles.value.add(f.id))
  }
})

function toggleSelect(id: number) {
  if (selectedFiles.value.has(id)) selectedFiles.value.delete(id)
  else selectedFiles.value.add(id)
}

async function startDownload() {
  downloading.value = true
  const ids = [...selectedFiles.value]
  // Two-step native download: get a short-lived one-time token, then open it
  // as a plain <a href> so the browser handles streaming + progress natively.
  for (const id of ids) {
    try {
      const { data } = await client.post(`/library/download/${id}/token`)
      const url = `/api/library/dl/${id}?dl_token=${encodeURIComponent(data.token)}`
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', '')
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (e) {
      console.error('Download failed for file', id, e)
    }
  }
  downloading.value = false
  showDownload.value = false
}

// ── Torrent download ──────────────────────────────────────────────────────────

const heroTorrentBusy  = ref(false)

// ── Torrent picker dialog ─────────────────────────────────────────────────────

const showTorrentPicker  = ref(false)
const torrentPickerSel   = ref(new Set<number>())

function openTorrentPicker() {
  // Default: all files selected
  torrentPickerSel.value = new Set(availableFiles.value.map(f => f.id))
  showTorrentPicker.value = true
}

function toggleTorrentFile(id: number) {
  if (torrentPickerSel.value.has(id)) torrentPickerSel.value.delete(id)
  else torrentPickerSel.value.add(id)
}

async function downloadTorrentHero() {
  showTorrentPicker.value = false
  if (!game.value) return
  heroTorrentBusy.value = true
  try {
    const response = await client.post(
      `/torrents/seed/game/${game.value.id}`,
      { file_ids: [...torrentPickerSel.value] },
      { responseType: 'blob' },
    )
    _saveTorrentBlob(response)
  } catch (e: any) {
    console.error('Game torrent generation failed', e)
  } finally {
    heroTorrentBusy.value = false
    torrentPickerSel.value.clear()
  }
}

function _saveTorrentBlob(response: any) {
  const blob = response.data as Blob
  const cd   = (response.headers['content-disposition'] as string | undefined) || ''
  const rfc5987 = cd.match(/filename\*=UTF-8''([^;\s]+)/i)
  const simple  = cd.match(/filename=["']?([^"';\n]+)["']?/)
  const fname   = rfc5987 ? decodeURIComponent(rfc5987[1]) : simple ? simple[1].trim() : 'game.torrent'
  const url  = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fname
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

const lightboxIdx = ref<number | null>(null)

// ── Carousel & description ────────────────────────────────────────────────────

const carouselEl   = ref<HTMLElement | null>(null)
const carouselIdx  = ref(0)
const descExpanded = ref(false)
const descOverflow = ref(false)

const videoModalOpen = ref(false)

const ytVideos = computed(() =>
  (game.value?.videos || []).filter(v => v.provider === 'youtube')
)

const carouselSlides = computed(() => {
  const slides: { type: 'image' | 'video'; src: string; videoId?: string }[] = []
  for (const v of ytVideos.value.slice(0, 1)) {
    const thumb = v.thumbnail_id
      ? `https://img.youtube.com/vi/${v.thumbnail_id}/maxresdefault.jpg`
      : `https://img.youtube.com/vi/${v.video_id}/maxresdefault.jpg`
    slides.push({ type: 'video', src: thumb, videoId: v.video_id })
  }
  for (const src of (game.value?.screenshots || [])) {
    slides.push({ type: 'image', src })
  }
  return slides
})

const hasMedia = computed(() => carouselSlides.value.length > 0)

// ── Requirements (Windows Minimum only) ───────────────────────────────────────
const REQ_SHOW = new Set(['processor', 'cpu', 'memory', 'ram', 'graphics', 'gpu', 'video', 'os', 'storage', 'directx'])

function formatReqKey(k: string): string {
  const key = k.toLowerCase()
  if (['processor', 'cpu'].includes(key))          return 'CPU'
  if (['memory', 'ram'].includes(key))             return 'RAM'
  if (['graphics', 'gpu', 'video'].includes(key))  return 'GPU'
  if (key === 'os')                                return 'OS'
  if (key === 'storage')                           return 'Storage'
  if (key === 'directx')                           return 'DirectX'
  return k
}

const reqRows = computed((): [string, string][] => {
  const reqs = game.value?.requirements
  if (!reqs) return []
  // Try Windows first, then fallback to first available OS
  let minimum: any =
    reqs.minimum ??
    reqs.Windows?.minimum ??
    reqs.windows?.minimum ??
    (reqs.per_os as any[] | undefined)?.find((o: any) => (o.os || '').toLowerCase().includes('win'))?.minimum ??
    (Object.values(reqs)[0] as any)?.minimum ?? null
  if (!minimum) return []
  if (Array.isArray(minimum)) {
    return minimum
      .filter((r: any) => REQ_SHOW.has((r.name || r.id || '').toLowerCase()) && (r.description || r.value))
      .map((r: any) => [r.name || r.id, r.description || r.value] as [string, string])
  }
  if (typeof minimum === 'object') {
    return Object.entries(minimum)
      .filter(([k, v]) => REQ_SHOW.has(k.toLowerCase()) && v)
      .map(([k, v]) => [k, String(v)] as [string, string])
  }
  return []
})

function slideTo(idx: number) {
  const max = Math.max(0, carouselSlides.value.length - 3)
  carouselIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = carouselEl.value
    if (!el) return
    const child = el.children[carouselIdx.value] as HTMLElement
    if (child) el.scrollTo({ left: child.offsetLeft - 2, behavior: 'smooth' })
  })
}

function onSlideClick(slide: { type: 'image' | 'video'; src: string; videoId?: string }, idx: number) {
  if (slide.type === 'video') {
    videoModalOpen.value = true
  } else {
    // lightbox index counts only image slides
    const imageOffset = ytVideos.value.length > 0 ? 1 : 0
    lightboxIdx.value = idx - imageOffset
  }
}

// ── External ratings ──────────────────────────────────────────────────────────

const pluginRatings = ref<{ id: string; name: string; rating: number; logo: string }[]>([])

const externalRatings = computed(() => ({
  rawg:  game.value?.meta_ratings?.['rawg']  ?? undefined,
  igdb:  game.value?.meta_ratings?.['igdb']  ?? undefined,
  steam: game.value?.meta_ratings?.['steam'] ?? undefined,
  plugins: pluginRatings.value,
}))

async function fetchPluginRatings(title: string) {
  // Check DB cache first (meta_ratings has plugin keys like "ppe")
  const cached = game.value?.meta_ratings || {}
  for (const [k, v] of Object.entries(cached)) {
    if (k !== 'rawg' && k !== 'igdb' && k !== 'steam' && typeof v === 'number') {
      pluginRatings.value.push({ id: k, name: k.toUpperCase(), rating: v, logo: `/api/plugins/${k}-metadata/logo` })
    }
  }
  if (pluginRatings.value.length) return  // already cached

  // Fetch live and persist
  try {
    const { data } = await client.get(`/plugins/metadata/search?q=${encodeURIComponent(title)}`)
    if (!Array.isArray(data) || !data.length) return
    for (const pr of data.slice(0, 3)) {
      try {
        const { data: detail } = await client.get(
          `/plugins/metadata/fetch?provider_id=${encodeURIComponent(pr.provider_id)}&game_id=${encodeURIComponent(pr.provider_game_id)}`
        )
        if (detail?.rating) {
          pluginRatings.value.push({
            id: detail.provider_id,
            name: (detail.provider_id || 'plugin').toUpperCase(),
            rating: detail.rating,
            logo: `/api/plugins/${detail.provider_id}-metadata/logo`,
          })
          // Persist to DB
          if (game.value) {
            const meta = { ...(game.value.meta_ratings || {}), [detail.provider_id]: detail.rating }
            client.patch(`/library/games/${game.value.id}`, { meta_ratings: meta }).catch(() => {})
          }
          break
        }
      } catch { /* skip */ }
    }
  } catch { /* plugins unavailable */ }
}

// sanitizeHtml imported from @/utils/sanitize (DOMPurify-based)

// ── 3D tilt effect ─────────────────────────────────────────────────────────────

const coverTilt  = ref('perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)')
const sheenStyle = ref('')

function onCoverEnter() {
  // tilt becomes active on first mousemove
}
function onCoverMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.width / 2
  const cy = rect.height / 2
  const dx = e.clientX - rect.left - cx
  const dy = e.clientY - rect.top - cy
  const rotY =  (dx / cx) * 10
  const rotX = -(dy / cy) * 7
  coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
  const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
  const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
  sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
}
function onCoverLeave() {
  coverTilt.value  = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
  sheenStyle.value = 'opacity:0;'
}

// ── Scrape metadata ────────────────────────────────────────────────────────────

async function onScrapeClick() {
  if (!game.value || scraping.value) return
  scraping.value = true
  try {
    const { data } = await client.post(`/library/games/${game.value.id}/scrape`)
    const sources = Object.entries(data.sources || {})
      .filter(([, ok]) => ok)
      .map(([s]) => s.toUpperCase())
      .join(', ')
    const applied = (data.applied || []).length
    await gdAlert(
      applied > 0
        ? `Scraped ${applied} field(s) from: ${sources || 'none'}`
        : `Nothing new found (sources tried: GOG, Steam, RAWG, IGDB)`
    )
    await fetchGame()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Scrape failed')
  } finally {
    scraping.value = false
  }
}

async function onClearMetadataClick() {
  if (!game.value) return
  if (!await gdConfirm('Clear all scraped metadata? Title, source and files are preserved.')) return
  clearing.value = true
  try {
    await client.post(`/library/games/${game.value.id}/clear-metadata`)
    await fetchGame()
  } catch (e: any) {
    await gdAlert(e?.response?.data?.detail || 'Clear failed')
  } finally {
    clearing.value = false
  }
}

// ── Edit Metadata panel ────────────────────────────────────────────────────────

const showEditPanel = ref(false)

// ── Metadata saved callback ────────────────────────────────────────────────────

async function onMetadataSaved(_payload: Record<string, unknown>) {
  await fetchGame()
}

// ── Admin game actions ─────────────────────────────────────────────────────────

async function unpublishGame() {
  if (!game.value) return
  if (!await gdConfirm('Unpublish this game? It will be hidden from users.')) return
  try {
    await client.patch(`/library/games/${game.value.id}`, { is_active: false })
    router.push({ name: 'games-library' })
  } catch (e) { console.error('Unpublish failed', e) }
}

async function republishGame() {
  if (!game.value) return
  try {
    await client.patch(`/library/games/${game.value.id}`, { is_active: true })
    await fetchGame()
  } catch (e) { console.error('Publish failed', e) }
}

async function deleteGame() {
  if (!game.value) return
  if (!await gdConfirm(`Delete "${game.value.title}"? This cannot be undone. Files on disk are NOT deleted.`, { danger: true })) return
  try {
    await client.delete(`/library/games/${game.value.id}`)
    router.push({ name: 'games-library' })
  } catch (e) { console.error('Delete failed', e) }
}

async function toggleFileAvailability(f: LibFile) {
  try {
    await client.patch(`/library/files/${f.id}`, { is_available: !f.is_available })
    await fetchGame()
  } catch (e) {
    console.error('Toggle failed', e)
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function osLabel(os: string): string {
  return { windows: 'Windows', mac: 'macOS', linux: 'Linux', all: 'All Platforms' }[os] ?? os
}

function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

function formatDate(raw: string): string {
  const d = new Date(raw)
  if (!isNaN(d.getTime())) {
    const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
    return d.toLocaleDateString(loc, { year: 'numeric', month: 'long', day: 'numeric' })
  }
  return raw.length <= 10 ? raw : raw.slice(0, 10)
}

const totalSize = computed(() => {
  const bytes = availableFiles.value.reduce((n, f) => n + (f.size_bytes ?? 0), 0)
  if (!bytes) return null
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2) + ' GB'
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
})

function formatSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 ** 3) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 ** 3).toFixed(2) + ' GB'
}

// ── Transmission enabled flag ──────────────────────────────────────────────────

const transmissionEnabled = ref(false)

async function fetchTransmissionEnabled() {
  try {
    const { data } = await client.get('/torrents/enabled')
    transmissionEnabled.value = !!data.enabled
  } catch {
    transmissionEnabled.value = false
  }
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

async function fetchGame() {
  loading.value = true
  try {
    const id = route.params.id
    const { data } = await client.get(`/library/games/${id}`)
    game.value = data
    descOverflow.value = !!(data.description && data.description.length > 600)
    // Lazy-load plugin ratings
    if (data.title) fetchPluginRatings(data.title)
  } catch {
    game.value = null
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, fetchGame)
onMounted(() => { fetchGame(); fetchTransmissionEnabled() })
</script>

<style scoped>
/* ══ ROOT ══════════════════════════════════════════════════════════════════════ */
.gd-root {
  display: flex; flex-direction: column;
  background: transparent;
  width: 100%;
  min-height: 100%;
  overflow-x: hidden;
}

/* ══ SKELETON ══════════════════════════════════════════════════════════════════ */
.sk-hero {
  height: 420px;
  background: linear-gradient(90deg, var(--bg2) 25%, var(--bg3) 50%, var(--bg2) 75%);
  background-size: 400% 100%; animation: shimmer 1.4s ease infinite;
}
.sk-body { padding: 36px 40px; display: flex; flex-direction: column; gap: var(--space-4, 16px); }
.sk-line {
  height: 16px; border-radius: 6px;
  background: linear-gradient(90deg, var(--bg2) 25%, var(--bg3) 50%, var(--bg2) 75%);
  background-size: 400% 100%; animation: shimmer 1.4s ease infinite;
}
.sk-line--xl { width: 70%; height: 32px; }
.sk-line--lg { width: 55%; }
.sk-line--md { width: 42%; }
.sk-line--sm { width: 28%; }
@keyframes shimmer { to { background-position: -400% 0; } }

/* ══ EMPTY ═════════════════════════════════════════════════════════════════════ */
.gd-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 14px; color: var(--muted); font-size: var(--fs-md, 14px);
}

/* ══ BACK PILL ═════════════════════════════════════════════════════════════════ */
.gd-back-pill {
  position: fixed; top: 130px; left: 20px; z-index: 200;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 14px 7px 10px; border-radius: 20px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(0,0,0,.42); backdrop-filter: blur(8px);
  color: rgba(255,255,255,.85);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.gd-back-pill:hover { background: rgba(0,0,0,.65); border-color: rgba(255,255,255,.35); color: #fff; }

/* ══ HERO ══════════════════════════════════════════════════════════════════════ */
.gd-hero {
  position: relative;
  min-height: 420px;
  display: flex; align-items: flex-end; justify-content: center;
  overflow: hidden; flex-shrink: 0;
}
/* Hero background + vignette moved to shared <HeroBackground> component. */
.gd-hero-inner {
  position: relative; z-index: 2;
  display: flex; align-items: flex-end; gap: var(--space-10, 40px);
  padding: 60px 44px 40px; width: 100%;
  max-width: 1140px; margin: 0 auto;
}

/* ══ COVER ═════════════════════════════════════════════════════════════════════ */
.gd-cover-col { flex-shrink: 0; }
.gd-cover-frame {
  position: relative;
  width: 360px; aspect-ratio: 3/4;
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,.85), 0 0 0 1px rgba(255,255,255,.09);
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.35s ease;
  cursor: default;
}
.gd-cover-frame:hover {
  box-shadow: 0 28px 70px rgba(0,0,0,.9), 0 0 0 1px rgba(255,255,255,.15), 0 0 40px var(--pglow2);
}
.gd-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.gd-cover-empty {
  width: 100%; height: 100%; background: rgba(255,255,255,.04);
  display: flex; align-items: center; justify-content: center;
}

/* ══ INFO COL ══════════════════════════════════════════════════════════════════ */
.gd-info-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 13px; }

.source-badge {
  display: inline-block; font-size: var(--fs-xs, 10px); font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  letter-spacing: .5px; text-transform: uppercase; align-self: flex-start;
}
.source-gog    { background: color-mix(in srgb, var(--pl) 30%, transparent); color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); }
.source-custom { background: rgba(20,184,166,.2); color: #2dd4bf; border: 1px solid rgba(20,184,166,.3); }

.gd-title {
  font-size: clamp(26px, 4vw, 46px);
  font-weight: 900; color: #fff; margin: 0;
  line-height: 1.08; text-shadow: 0 2px 30px rgba(0,0,0,.7); letter-spacing: -.5px;
}

.gd-meta-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  font-size: var(--fs-md, 14px); color: rgba(255,255,255,.58); font-weight: 500;
}
.gd-meta-item { /* inherits */ }
.gd-meta-sep { opacity: .3; }

.gd-stars { display: flex; align-items: center; gap: 3px; }
.star { font-size: 17px; color: rgba(255,255,255,.12); line-height: 1; }
.star.filled { color: #f59e0b; }
.gd-rating-num { font-size: 15px; font-weight: 700; color: #f59e0b; margin-left: 6px; }

.gd-os-row { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }
.os-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14);
  color: rgba(255,255,255,.7); font-size: var(--fs-sm, 12px); font-weight: 600; transition: all .15s;
}
.os-chip:hover { background: rgba(255,255,255,.12); color: #fff; }
.os-chip--win { background: rgba(0,120,212,.15); border-color: rgba(0,120,212,.25); color: #60a5fa; }
.os-chip--mac { background: rgba(156,163,175,.1); border-color: rgba(156,163,175,.15); color: #d1d5db; }
.os-chip--lin { background: rgba(234,179,8,.1); border-color: rgba(234,179,8,.15); color: #fde047; }

.gd-genres { display: flex; flex-wrap: wrap; gap: 6px; }
.genre-chip {
  padding: 4px 12px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(167,139,250,.16); border: 1px solid rgba(167,139,250,.35); color: #c4b5fd;
}

.gd-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }
/* Specular sheen layer */
.gd-cover-sheen {
  position: absolute; inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s;
}

/* Logo image (transparent SteamGridDB logo above title) */
.gd-logo-img {
  max-width: min(460px, 100%);
  max-height: 140px;
  object-fit: contain;
  object-position: left center;
  filter: drop-shadow(0 2px 18px rgba(0,0,0,.75));
}

.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Unified button styles (same as GOG view) ─────────────────────────────── */
.gd-btn-dl {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 18px var(--pglow2);
}
.gd-btn-dl:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; transform: translateY(-1px); }
.gd-btn-dl:disabled { opacity: .4; cursor: not-allowed; }

.gd-btn-torrent {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 20px; border-radius: var(--radius-sm);
  background: rgba(20,184,166,.18); border: 1px solid rgba(20,184,166,.4);
  color: #2dd4bf; font-size: var(--fs-md, 14px); font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.gd-btn-torrent:not(:disabled):hover { background: rgba(20,184,166,.32); transform: translateY(-1px); }
.gd-btn-torrent:disabled { opacity: .5; cursor: not-allowed; }

.dl-btn--torrent { background: rgba(20,184,166,.25); color: #2dd4bf; border: 1px solid rgba(20,184,166,.4); }
.dl-btn--torrent:not(:disabled):hover { background: rgba(20,184,166,.4); }

.gd-btn-ghost {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.16);
  color: rgba(255,255,255,.68); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-btn-ghost:not(:disabled):hover { background: rgba(255,255,255,.13); color: #fff; border-color: rgba(255,255,255,.3); }
.gd-btn-ghost:disabled { opacity: .5; cursor: not-allowed; }

.gd-btn-danger {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm);
  background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.35);
  color: #fca5a5; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-btn-danger:not(:disabled):hover { background: rgba(239,68,68,.24); border-color: rgba(239,68,68,.6); color: #fecaca; }
.gd-btn-danger:disabled { opacity: .5; cursor: not-allowed; }

.gd-btn-publish {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm);
  background: rgba(20,184,166,.12); border: 1px solid rgba(20,184,166,.35);
  color: #2dd4bf; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-btn-publish:not(:disabled):hover { background: rgba(20,184,166,.24); border-color: rgba(20,184,166,.6); color: #5eead4; }
.gd-btn-publish:disabled { opacity: .5; cursor: not-allowed; }

.gd-btn-unpublish {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm);
  background: rgba(239,68,68,.10); border: 1px solid rgba(239,68,68,.3);
  color: #f87171; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-btn-unpublish:not(:disabled):hover { background: rgba(239,68,68,.22); border-color: rgba(239,68,68,.55); color: #fca5a5; }
.gd-btn-unpublish:disabled { opacity: .5; cursor: not-allowed; }

/* legacy alias - kept for upload panel */
.gd-download-btn {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm, 6px);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 18px var(--pglow2);
}
.gd-download-btn:hover { background: var(--pl-light); transform: translateY(-1px); }
.btn-file-count {
  font-size: 11px; font-weight: 400; opacity: .75;
  background: rgba(255,255,255,.15); padding: 1px 7px; border-radius: 10px;
}
.gd-no-files { font-size: var(--fs-sm, 12px); color: var(--muted); font-style: italic; }
.gd-edit-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.16);
  color: rgba(255,255,255,.68); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-edit-btn:hover { background: rgba(255,255,255,.13); color: #fff; border-color: rgba(255,255,255,.3); }

/* ══ BODY ══════════════════════════════════════════════════════════════════════ */
.gd-body {
  flex: 1; max-width: 1140px; width: 100%; margin: 0 auto;
  padding: 40px 44px 70px; display: flex; flex-direction: column; gap: 44px;
}
.gd-section { display: flex; flex-direction: column; gap: 14px; }
.gd-section-title {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px; margin-bottom: 4px;
  display: flex; align-items: center; gap: var(--space-2, 8px);
}
.admin-badge {
  font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 10px;
  background: rgba(239,68,68,.2); color: #f87171; border: 1px solid rgba(239,68,68,.3);
  text-transform: uppercase; letter-spacing: .5px;
}
.gd-desc { font-size: var(--fs-md, 14px); line-height: 1.75; color: rgba(255,255,255,.65); }
.gd-screenshots { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }
.gd-ss-img {
  width: 200px; height: 112px; object-fit: cover; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--glass-border); transition: transform .15s;
}
.gd-ss-img:hover { transform: scale(1.03); }

/* ── Files badges (shared: admin section) ────────────────────────────────────── */
.files-type-badge {
  font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: var(--radius-sm, 8px);
  text-transform: uppercase; flex-shrink: 0;
}
.type-game  { background: color-mix(in srgb, var(--pl) 20%, transparent); color: var(--pl-light); border: 1px solid color-mix(in srgb, var(--pl) 30%, transparent); }
.type-extra { background: rgba(20,184,166,.2); color: #2dd4bf; border: 1px solid rgba(20,184,166,.3); }
.type-dlc   { background: rgba(234,179,8,.2); color: #fde047; border: 1px solid rgba(234,179,8,.3); }
.files-size { font-size: 11px; color: var(--muted); white-space: nowrap; }
.gd-spinner {
  width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor; border-radius: 50%;
  animation: gd-spin .7s linear infinite; display: inline-block; flex-shrink: 0;
}
@keyframes gd-spin { to { transform: rotate(360deg); } }

/* ── Admin file management ───────────────────────────────────────────────────── */
.gd-admin-section { border: 1px solid rgba(239,68,68,.15); border-radius: 10px; padding: var(--space-5, 20px); }
.admin-files-list { display: flex; flex-direction: column; gap: 6px; }
.admin-file-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 6px;
}
.admin-file-info { display: flex; align-items: center; gap: var(--space-2, 8px); flex: 1; min-width: 0; }
.admin-file-name { font-size: var(--fs-sm, 12px); color: var(--text); flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.admin-file-os, .source-micro { font-size: var(--fs-xs, 10px); color: var(--muted); }
.admin-file-actions { display: flex; gap: 6px; }
.toggle-avail-btn {
  font-size: var(--fs-xs, 10px); padding: 3px 10px; border-radius: 10px; cursor: pointer; border: 1px solid;
  transition: all var(--transition);
  color: var(--muted); background: rgba(255,255,255,.04); border-color: rgba(255,255,255,.1);
}
.toggle-avail-btn.available { color: #4ade80; background: rgba(74,222,128,.1); border-color: rgba(74,222,128,.25); }

/* ── Download dialog ──────────────────────────────────────────────────────────── */
/* ── Download / Torrent dialog (GOG Classic style) ───────────────────────── */
.dl-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.dl-dialog {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  width: 100%; max-width: 560px; max-height: 85vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
}
.dl-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 24px; border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.dl-title { font-size: 15px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: var(--space-2, 8px); }
.dl-close {
  background: none; border: none; color: var(--muted); font-size: 20px;
  cursor: pointer; padding: var(--space-1, 4px); border-radius: 6px; transition: all .15s;
}
.dl-close:hover { color: var(--text); background: rgba(255,255,255,.08); }

/* OS tabs */
.dl-os-tabs {
  display: flex; gap: 6px; padding: 16px 24px 0; flex-wrap: wrap;
}
.dl-os-tab {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.04);
  font-size: 13px; font-weight: 600; cursor: pointer;
  color: var(--muted); transition: all .15s;
}
.dl-os-tab:hover { border-color: rgba(255,255,255,.2); color: var(--text); }
.dl-os-tab.active {
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light);
}

/* Section label */
.dl-type-head {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .8px; color: var(--pl-light); margin-bottom: 6px; margin-top: 4px;
}

/* File list */
.dl-files {
  flex: 1; overflow-y: auto; padding: 16px 24px 20px;
  display: flex; flex-direction: column; gap: 18px;
}
.dl-type-section { display: flex; flex-direction: column; gap: 6px; }
.dl-file-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.07);
  transition: background .12s;
}
.dl-file-row:hover { background: rgba(255,255,255,.07); }
.dl-file-check { display: flex; align-items: center; gap: 10px; flex: 1; cursor: pointer; }
.dl-file-check input { width: 16px; height: 16px; cursor: pointer; accent-color: var(--pl); }
.dl-file-name { font-size: 13px; color: var(--text); }
.dl-file-meta { display: flex; align-items: center; gap: var(--space-2, 8px); }
.dl-file-ver { font-size: var(--fs-xs, 10px); color: var(--muted); font-family: monospace; }
.dl-file-size { font-size: var(--fs-sm, 12px); color: var(--muted); font-weight: 500; }

/* Footer */
.dl-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.dl-selected-info { font-size: var(--fs-sm, 12px); color: var(--muted); }
.dl-btn {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 10px 22px; border-radius: var(--radius-sm, 8px);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 12px var(--pglow2);
}
.dl-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 35%, transparent);
  border-color: var(--pl); color: #fff;
}
.dl-btn:disabled { opacity: .4; cursor: not-allowed; }

/* ── Lightbox ─────────────────────────────────────────────────────────────────── */
.lightbox-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.9); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
}
.lightbox-img { max-width: 90vw; max-height: 90vh; border-radius: var(--radius-sm, 8px); }
.lightbox-close {
  position: absolute; top: 20px; right: 24px; background: none; border: none;
  color: rgba(255,255,255,.7); font-size: var(--fs-3xl, 28px); cursor: pointer;
}

/* ── Spinners ─────────────────────────────────────────────────────────────────── */
.btn-spinner {
  width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite;
}
.btn-spinner--sm { width: 11px; height: 11px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Hero animations now in <HeroBackground>. */

/* ══ SEPARATOR ════════════════════════════════════════════════════════════════ */
.gd-separator {
  width: 100%;
  height: 80px;
  margin-top: -80px;
  background: linear-gradient(to bottom, transparent, var(--bg1, rgba(8,7,18,1)));
  pointer-events: none;
  flex-shrink: 0;
  position: relative;
  z-index: 0;
}

/* ══ RATING ROW ══════════════════════════════════════════════════════════════ */
.gd-rating-row { display: flex; align-items: center; gap: 3px; }
.gd-rating-num { font-size: 15px; font-weight: 700; color: #f59e0b; margin-left: 6px; }

/* ══ TAGS / GENRES ═══════════════════════════════════════════════════════════ */
.gd-tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.gd-genre-tag {
  padding: 4px 12px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(167,139,250,.16); border: 1px solid rgba(167,139,250,.35);
  color: #c4b5fd;
}

/* ══ OS CHIPS ════════════════════════════════════════════════════════════════ */
.gd-os-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14);
  color: rgba(255,255,255,.7); font-size: var(--fs-sm, 12px); font-weight: 600;
  transition: all .15s;
}
.gd-os-chip:hover { background: rgba(255,255,255,.12); color: #fff; }

/* ══ EXTERNAL RATINGS ════════════════════════════════════════════════════════ */
.gd-ext-ratings { display: flex; gap: 10px; flex-wrap: wrap; }
.gd-ext-score {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
}
.gd-ext-ico { flex-shrink: 0; image-rendering: pixelated; border-radius: 6px; }
.gd-ext-info { display: flex; flex-direction: column; gap: 2px; }
.gd-ext-val { font-size: var(--fs-lg, 16px); font-weight: 800; color: #fff; line-height: 1; }
.gd-ext-max { font-size: var(--fs-xs, 10px); color: var(--muted); font-weight: 500; }
.gd-ext-lbl {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px;
}

/* ══ DETAILS LIST (right column grid) ════════════════════════════════════════ */
.gd-dlist {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 6px);
  overflow: hidden;
}
.gd-dk, .gd-dv { padding: 10px 14px; font-size: 13px; }
.gd-dk {
  color: var(--muted); font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px;
  white-space: nowrap; border-right: 1px solid var(--glass-border);
  border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
}
.gd-dv { color: var(--text); }
.gd-dk + .gd-dv { border-bottom: 1px solid var(--glass-border); }
.gd-dk:last-of-type + .gd-dv { border-bottom: none; }
.gd-mono { font-family: monospace; font-size: var(--fs-sm, 12px); }
.gd-owner-cell { display: flex; align-items: center; gap: 6px; }
.gd-owner-crown { color: #f59e0b; flex-shrink: 0; filter: drop-shadow(0 0 4px rgba(245,158,11,.4)); }

.gd-tag-inline { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); }
.gd-itag {
  padding: 2px 9px; border-radius: var(--radius-xs, 4px); font-size: 11px; font-weight: 600;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: rgba(255,255,255,.58);
}
.gd-lang-flags { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); }
.gd-lang-flag {
  display: inline-flex; align-items: center;
  font-size: 20px; line-height: 1; cursor: default;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,.3));
  transition: transform .12s;
}
.gd-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.gd-lang-flag:hover { transform: scale(1.25); }

/* ══ SECTION LABEL ═══════════════════════════════════════════════════════════ */
.gd-section-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px;
  margin-bottom: 16px;
}

/* ══ MEDIA / CAROUSEL ════════════════════════════════════════════════════════ */
.gd-media-section {
  display: flex; flex-direction: column; gap: var(--space-6, 24px);
  padding: 0 24px;
}
.gd-carousel-wrap {
  position: relative;
  display: flex; align-items: center;
}
.gd-carousel {
  flex: 1;
  display: flex;
  gap: var(--space-3, 12px);
  overflow-x: auto;
  overflow-y: hidden;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  padding: 4px 2px 8px;
}
.gd-carousel::-webkit-scrollbar { display: none; }
.gd-slide {
  flex: 0 0 calc((100% - 24px) / 3);
  aspect-ratio: 16/9;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  scroll-snap-align: start;
  border: 1px solid rgba(255,255,255,.08);
  transition: border-color .2s, box-shadow .2s, transform .2s;
  background: var(--bg2);
  position: relative;
}
.gd-slide > img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform .3s ease;
}
.gd-slide:hover { border-color: var(--pl); box-shadow: 0 0 24px var(--pglow2); transform: translateY(-2px); }
.gd-slide:hover > img { transform: scale(1.04); }
.gd-slide--active { border-color: rgba(255,255,255,.18); }
.gd-slide-play {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.35);
}
.gd-slide-play svg { filter: drop-shadow(0 0 6px rgba(0,0,0,.6)); }
.gd-slide-badge {
  position: absolute; bottom: 8px; left: 8px;
  font-size: var(--fs-xs, 10px); font-weight: 600; letter-spacing: .05em;
  background: rgba(0,0,0,.55); color: #fff; border-radius: var(--radius-xs, 4px); padding: 2px 7px;
}
.gd-video-frame {
  width: min(900px, 90vw); aspect-ratio: 16/9;
  border-radius: 10px; overflow: hidden; box-shadow: 0 8px 48px rgba(0,0,0,.8);
}
.gd-video-frame iframe { width: 100%; height: 100%; }
.gd-carr-btn {
  position: absolute;
  top: 50%; transform: translateY(-50%);
  width: 46px; height: 46px; border-radius: 50%; z-index: 2;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.62); border: 1px solid rgba(255,255,255,.22);
  color: #fff; cursor: pointer; transition: all .15s;
  backdrop-filter: blur(8px);
}
.gd-carr-btn:not(:disabled):hover { background: rgba(0,0,0,.88); border-color: rgba(255,255,255,.5); }
.gd-carr-btn:disabled { opacity: 0; pointer-events: none; }
.gd-carr-btn--left  { left: -20px; }
.gd-carr-btn--right { right: -20px; }
.gd-dots {
  display: flex; justify-content: center; gap: 6px;
  padding-top: 14px;
}
.gd-dot-item {
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,.18); cursor: pointer;
  transition: all .22s;
}
.gd-dot-item.active { background: color-mix(in srgb, var(--pl) 30%, transparent); width: 22px; border-radius: 3px; }

/* ══ TWO COLUMNS ═════════════════════════════════════════════════════════════ */
.gd-cols {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 52px;
  align-items: start;
}
@media (max-width: 900px) {
  .gd-cols { grid-template-columns: 1fr; }
}

/* ══ DESCRIPTION ═════════════════════════════════════════════════════════════ */
.gd-desc-wrap {
  font-size: var(--fs-md, 14px); line-height: 1.85; color: rgba(255,255,255,.72);
  overflow: hidden;
}
.gd-desc--collapsed {
  max-height: 9em;
  mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
}
.gd-desc-html :deep(h1),
.gd-desc-html :deep(h2),
.gd-desc-html :deep(h3) { font-size: 15px; font-weight: 700; margin: 14px 0 7px; color: var(--text); }
.gd-desc-html :deep(p)  { margin: 0 0 10px; }
.gd-desc-html :deep(ul),
.gd-desc-html :deep(ol) { padding-left: 20px; margin: 6px 0; }
.gd-desc-html :deep(a)  { color: var(--pl-light); }
.gd-desc-html :deep(img) { max-width: 100%; height: auto; border-radius: 6px; display: block; margin: 8px 0; }
.gd-readmore {
  margin-top: 12px; background: none; border: none;
  color: var(--pl-light); font-size: var(--fs-sm, 12px); font-weight: 600;
  font-family: inherit; cursor: pointer; padding: 0;
  opacity: .85;
}
.gd-readmore:hover { opacity: 1; }

/* ══ LIGHTBOX (GOG-style) ════════════════════════════════════════════════════ */
.gd-lb {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.94);
  display: flex; align-items: center; justify-content: center;
  animation: lb-in .15s ease;
}
@keyframes lb-in { from { opacity: 0; } to { opacity: 1; } }
.gd-lb-img {
  max-width: 90vw; max-height: 86vh;
  border-radius: var(--radius-sm, 8px); box-shadow: 0 0 80px rgba(0,0,0,.9);
  object-fit: contain;
}
.gd-lb-close, .gd-lb-arrow {
  position: fixed;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.18);
  border-radius: var(--radius-sm, 8px); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s; padding: 10px;
}
.gd-lb-close { top: 16px; right: 16px; }
.gd-lb-arrow--l { left: 16px; top: 50%; transform: translateY(-50%); }
.gd-lb-arrow--r { right: 16px; top: 50%; transform: translateY(-50%); }
.gd-lb-close:hover, .gd-lb-arrow:hover { background: rgba(255,255,255,.22); }
.gd-lb-counter {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.48); font-weight: 600;
  background: rgba(0,0,0,.4); padding: 4px 14px; border-radius: 20px;
}

/* ══ ADMIN ACTION BUTTONS ════════════════════════════════════════════════════ */
.gd-admin-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 13px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.06);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600;
  font-family: inherit; cursor: pointer;
  transition: all var(--transition);
}
.gd-admin-btn:hover { background: rgba(255,255,255,.12); color: var(--text); }
.gd-admin-btn--warn { border-color: rgba(251,191,36,.35); color: rgba(251,191,36,.8); }
.gd-admin-btn--warn:hover { background: rgba(251,191,36,.12); border-color: rgba(251,191,36,.6); color: #fbbf24; }
.gd-admin-btn--ok { border-color: rgba(52,211,153,.35); color: rgba(52,211,153,.8); }
.gd-admin-btn--ok:hover { background: rgba(52,211,153,.12); border-color: rgba(52,211,153,.6); color: #34d399; }
.gd-admin-btn--danger { border-color: rgba(248,113,113,.35); color: rgba(248,113,113,.8); }
.gd-admin-btn--danger:hover { background: rgba(248,113,113,.12); border-color: rgba(248,113,113,.6); color: #f87171; }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .gd-hero-inner { flex-direction: column; align-items: center; gap: var(--space-4, 16px); padding: 24px 16px 20px; }
  .gd-cover-frame { width: clamp(160px, 50vw, 240px); }
  .gd-cover-col { align-items: center; }
  .gd-info-col { align-items: center; text-align: center; }
  .gd-ext-ratings { justify-content: center; }
  .gd-tag-row { justify-content: center; }
  .gd-os-row { justify-content: center; }
  .gd-actions { justify-content: center; }
  .gd-body { padding: 20px 16px 40px; }
  .gd-cols { gap: var(--space-5, 20px); }
  .gd-dlist { grid-template-columns: 30px auto 1fr; font-size: var(--fs-sm, 12px); }
}

</style>
