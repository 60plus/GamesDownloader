<template>
  <div class="cd-wrap">

    <!-- Loading -->
    <div v-if="loading" class="cd-loading">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="cd-spin" style="opacity:.4">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="cd-error">{{ error }}</div>

    <!-- Game content -->
    <template v-else-if="game">

      <!-- ── COVER HERO ─────────────────────────────────────────────────────── -->
      <div class="cover-hero">
        <!-- Hero background (toggled by Settings → Classic Layout → Hero Background) -->
        <template v-if="themeStore.classicHero">
          <div class="hero-bg">
            <div class="hero-bg-inner" :class="heroAnimClass" :style="{ ...heroBgStyle, filter: `blur(${themeStore.heroBlur}px) saturate(.6) brightness(.4)` }" />
            <div class="hero-bg-overlay" />
          </div>
          <div class="hero-vignette" />
        </template>

        <!-- Cover image + tilt + sheen + action overlay -->
        <div class="cover-wrap"
          :style="themeStore.cardTilt ? { transform: coverTilt, transition: 'transform .1s ease-out' } : {}"
          @mousemove="onCoverMove"
          @mouseleave="onCoverLeave"
        >
          <img
            v-if="coverSrc && !coverFailed"
            :src="coverSrc"
            class="cover-img"
            :class="{ 'cover-img--rom': activeLib === 'roms' }"
            :alt="game.title"
            @error="onCoverError"
          />
          <div v-else class="cover-ph" :class="{ 'cover-ph--rom': activeLib === 'roms' }">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.3">
              <rect x="2" y="6" width="20" height="12" rx="2"/>
              <circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/>
            </svg>
          </div>
          <!-- Specular sheen (respects themeStore.cardShine) -->
          <div v-if="themeStore.cardShine" class="cover-sheen" :style="sheenStyle" />
          <!-- Hover overlay: Play + Download + Edit metadata -->
          <div class="cover-overlay">
            <!-- ROM play -->
            <button v-if="activeLib === 'roms' && ejsCore" class="cov-btn cov-btn--play" title="Play" @click="requestPlay">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5,3 19,12 5,21"/></svg>
            </button>
            <!-- ROM download -->
            <button v-if="activeLib === 'roms'" class="cov-btn" title="Download ROM" @click="downloadRom">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <!-- GOG download -->
            <button v-else-if="activeLib !== 'games'" class="cov-btn" title="Download" @click="dlOpen = true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <!-- GAMES library download -->
            <button v-else-if="libAvailableFiles.length" class="cov-btn" title="Download" @click="showLibDownload = true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <button v-if="isAdmin" class="cov-btn" @click="metaOpen = true" :title="t('detail.edit_metadata')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </button>
            <button v-if="activeLib !== 'games'" class="cov-btn" :class="{ 'cov-btn--spin': scraping }" :disabled="scraping" @click="onScrapeClick" :title="activeLib === 'roms' ? 'Scrape ROM metadata' : 'Refresh data from GOG'">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
            <button v-if="isAdmin" class="cov-btn cov-btn--danger" :disabled="clearing" @click="onClearClick" :title="t('detail.clear_metadata')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
            </button>
          </div>
        </div>

        <!-- Wheel logo (ROMs) / GOG logo / text title fallback -->
        <img
          v-if="logoSrc && !logoFailed"
          :src="logoSrc"
          :alt="game.title"
          :class="activeLib === 'roms' ? 'game-wheel' : 'game-logo'"
          @error="logoFailed = true"
        />
        <div v-else class="game-title">{{ game.title }}</div>

        <!-- Ratings row (below title, above chips) -->
        <div v-if="activeLib === 'roms' && game.ss_score != null" class="cover-ratings">
          <div class="crating">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            <span>{{ game.ss_score }}<small>/20</small></span>
          </div>
        </div>
        <div v-else-if="activeLib !== 'roms' && hasRatings" class="cover-ratings">
          <div v-if="game.rating" class="crating">
            <img src="/icons/gog.ico" class="crating-ico" title="GOG" />
            <span>{{ game.rating.toFixed(1) }}<small>/5</small></span>
          </div>
          <div v-if="game.meta_ratings?.rawg != null" class="crating">
            <img src="/icons/RAWG.ico" class="crating-ico" title="RAWG" />
            <span>{{ game.meta_ratings.rawg?.toFixed(1) }}<small>/5</small></span>
          </div>
          <div v-if="game.meta_ratings?.igdb != null" class="crating">
            <img src="/icons/igdb.ico" class="crating-ico" title="IGDB" />
            <span>{{ Math.round(game.meta_ratings.igdb ?? 0) }}<small>/100</small></span>
          </div>
          <div v-if="game.meta_ratings?.steam != null" class="crating">
            <img src="/icons/metacritic.svg" class="crating-ico" title="Metacritic" />
            <span>{{ Math.round((game.meta_ratings.steam ?? 0) * 10) }}<small>/100</small></span>
          </div>
        </div>

        <!-- Meta chips: release year only (developer & genres removed) -->
        <div class="meta-chips">
          <div v-if="releaseYear" class="chip">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span>{{ releaseYear }}</span>
          </div>
        </div>
      </div>

      <!-- ── MEDIA STRIP: video first, then all screenshots ─────────────────── -->
      <!-- Same mechanism as Modern theme: nav arrows + scrollTo() + flex:1 strip -->
      <div v-if="videoItem || screenshotUrls.length" class="shots-wrap">

        <!-- Prev arrow -->
        <button class="shots-nav" :disabled="slideIdx === 0" @click="slideTo(slideIdx - 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>

        <div class="shots-strip" ref="stripEl">
          <!-- Video (first) - index 0 -->
          <div v-if="videoItem" class="shot-item shot-item--video" @click="openLightbox(0)">
            <img v-if="videoItem.thumb" :src="videoItem.thumb" class="shot-thumb-img" alt="Video"
              @error="($event.target as HTMLImageElement).style.display='none'" />
            <div v-else class="shot-thumb-img shot-thumb-img--dark" />
            <div class="shot-play-btn">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </div>
          </div>
          <!-- Screenshots - offset by 1 if video present -->
          <div
            v-for="(shot, i) in screenshotUrls"
            :key="i"
            class="shot-item"
            @click="openLightbox((videoItem ? 1 : 0) + i)"
          >
            <img :src="shot" class="shot-thumb-img" loading="lazy"
              @error="(e) => (e.target as HTMLImageElement).parentElement!.style.display='none'" />
          </div>
        </div>

        <!-- Next arrow -->
        <button class="shots-nav" :disabled="totalSlides <= 4 || slideIdx >= totalSlides - 4" @click="slideTo(slideIdx + 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>

      </div>

      <!-- ── INFO CARDS ──────────────────────────────────────────────────────── -->
      <div class="info-cards">

        <!-- Card 1: Developer / Publisher / Genres -->
        <div class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            <span>{{ t('detail.developer') }} &amp; {{ t('detail.publisher') }}</span>
          </div>
          <div class="icard-row"><span class="icard-label">{{ t('detail.developer') }}: </span><span class="icard-val">{{ game.developer || '-' }}</span></div>
          <div class="icard-row"><span class="icard-label">{{ t('detail.publisher') }}: </span><span class="icard-val">{{ game.publisher || '-' }}</span></div>
          <template v-if="game.genres?.length">
            <div class="icard-head" style="margin-top:10px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
              <span>{{ t('detail.genres') }}</span>
            </div>
            <div class="genre-tags">
              <span v-for="g in game.genres" :key="g" class="genre-tag">{{ g }}</span>
            </div>
          </template>
        </div>

        <!-- Card 2: for ROMs = ROM Info; for GOG/Games = Languages & OS -->
        <div class="icard">
          <template v-if="activeLib === 'roms'">
            <div class="icard-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="14" rx="2"/><circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/><path d="M6 10h4M8 8v4M14 11h4"/></svg>
              <span>ROM Info</span>
            </div>
            <div class="icard-row"><span class="icard-label">Platform: </span><span class="icard-val">{{ game.platform_name || '-' }}</span></div>
            <div class="icard-row"><span class="icard-label">File: </span><span class="icard-val">{{ (game as any).fs_name || game.fs_name_no_ext || '-' }}</span></div>
            <div class="icard-row"><span class="icard-label">Extension: </span><span class="icard-val">{{ game.fs_extension || '-' }}</span></div>
            <div class="icard-row"><span class="icard-label">{{ t('detail.size') }}: </span><span class="icard-val">{{ game.fs_size_bytes ? formatSize(game.fs_size_bytes) : '-' }}</span></div>
            <div class="icard-row"><span class="icard-label">{{ t('detail.players') }}: </span><span class="icard-val">{{ game.player_count || '-' }}</span></div>
            <template v-if="game.regions?.length">
              <div class="icard-head" style="margin-top:10px">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <span>Regions</span>
              </div>
              <div class="genre-tags">
                <span v-for="r in game.regions" :key="r" class="genre-tag">{{ r }}</span>
              </div>
            </template>
          </template>
          <template v-else>
            <div class="icard-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              <span>{{ t('detail.languages') }}</span>
            </div>
            <div class="icard-row" style="margin-bottom:4px"><span class="icard-label">{{ t('detail.languages') }}: </span></div>
            <div v-if="languageFlags.length" class="lang-flags">
              <span v-for="l in languageFlags" :key="l.name" class="lang-flag-em" :title="l.name">{{ l.flag }}</span>
            </div>
            <div v-else class="icard-row"><span class="icard-val">-</span></div>
            <div class="icard-row" style="margin-top:6px">
              <span class="icard-label">{{ t('library.platform_label') }}: </span>
              <div class="os-icons">
                <span class="os-icon" :class="{ active: game.os_windows }" title="Windows">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.75L11,11.91V5.21L20,3M3,13L9,13.09V19.9L3,18.75V13M20,13.25V22L11,20.5V13.09L20,13.25Z"/></svg>
                </span>
                <span class="os-icon" :class="{ active: game.os_mac }" title="macOS">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.78 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5M13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z"/></svg>
                </span>
                <span class="os-icon" :class="{ active: game.os_linux }" title="Linux">
                  <img src="/icons/os-linux.svg" class="os-icon-linux" alt="Linux" />
                </span>
              </div>
            </div>
          </template>
        </div>

        <!-- Card 3: for ROMs = HLTB + Details; for GOG/Games = System Requirements -->
        <div class="icard">
          <template v-if="activeLib === 'roms'">
            <div class="icard-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span>{{ t('detail.time_to_beat') }}</span>
            </div>
            <div v-if="game.hltb_main_s" class="icard-row">
              <span class="icard-label">{{ t('detail.hltb_main') }} </span>
              <span class="icard-val">{{ Math.round((game.hltb_main_s || 0) / 3600) }}h {{ Math.round(((game.hltb_main_s || 0) % 3600) / 60) }}m</span>
            </div>
            <div v-if="game.hltb_complete_s" class="icard-row">
              <span class="icard-label">100%: </span>
              <span class="icard-val">{{ Math.round((game.hltb_complete_s || 0) / 3600) }}h {{ Math.round(((game.hltb_complete_s || 0) % 3600) / 60) }}m</span>
            </div>
            <div v-if="!game.hltb_main_s && !game.hltb_complete_s" class="req-none">No HLTB data</div>
            <template v-if="game.franchises?.length">
              <div class="icard-head" style="margin-top:10px">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                <span>{{ t('detail.franchise') }}</span>
              </div>
              <div class="genre-tags">
                <span v-for="f in game.franchises" :key="f" class="genre-tag">{{ f }}</span>
              </div>
            </template>
            <template v-if="game.alternative_names?.length">
              <div class="icard-head" style="margin-top:10px">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
                <span>{{ t('detail.also_known_as') }}</span>
              </div>
              <div style="font-size:11px;color:var(--muted);margin-top:4px;line-height:1.6">{{ game.alternative_names.join(' · ') }}</div>
            </template>
          </template>
          <template v-else>
            <div class="icard-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
              <span>{{ t('detail.min_requirements') }}</span>
            </div>
            <template v-if="reqRows.length">
              <table class="req-table">
                <tr v-for="[k, v] in reqRows" :key="k">
                  <td class="req-name">{{ formatReqKey(k) }}</td>
                  <td class="req-min">{{ v }}</td>
                </tr>
              </table>
            </template>
            <div v-else class="req-none">No requirements data</div>
          </template>
        </div>

      </div>

      <!-- ── DESCRIPTION ─────────────────────────────────────────────────────── -->
      <div v-if="descHtml" class="desc-section">
        <div class="section-head">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
          <span>{{ t('detail.about') }}</span>
        </div>
        <div class="desc-body" v-html="sanitizeHtml(descHtml)" />
      </div>

    </template>

    <!-- Metadata edit panel - ROM library -->
    <EmulationRomMetadataPanel
      v-if="metaOpen && game && activeLib === 'roms'"
      :rom="(game as any)"
      @close="metaOpen = false"
      @saved="onMetaSaved"
    />
    <!-- Metadata edit panel - GOG library -->
    <library-metadata-panel
      v-if="metaOpen && game && activeLib !== 'games' && activeLib !== 'roms'"
      :game="(game as any)"
      api-prefix="/gog/library/games"
      @close="metaOpen = false"
      @saved="onMetaSaved"
    />
    <!-- Metadata edit panel - Games/Custom library -->
    <library-metadata-panel
      v-if="metaOpen && game && activeLib === 'games'"
      :game="(game as any)"
      @close="metaOpen = false"
      @saved="onLibMetaSaved"
    />

    <!-- Download dialog (GOG library only) -->
    <DownloadDialog
      v-if="game && activeLib !== 'games'"
      v-model="dlOpen"
      :gog-id="game.gog_id ?? 0"
      :game-title="game.title"
      @publish-library="onPublishLibrary"
    />

  </div>

  <!-- ── SCRAPE DIALOG (same as Modern theme) ──────────────────────────── -->
  <teleport to="body">
    <div v-if="showScrapeDialog" class="gd-confirm-overlay" @click.self="showScrapeDialog = false">
      <div class="gd-confirm-box">
        <div class="gd-confirm-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div class="gd-confirm-title">{{ t('detail.refresh_metadata') }}</div>
        <div class="gd-confirm-body">
          {{ t('classic.refresh_meta_body') }}
        </div>
        <div class="gd-confirm-actions">
          <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="scrapeGame(true)">{{ t('classic.gog_only') }}</button>
          <button class="gd-confirm-btn gd-confirm-btn--primary" @click="scrapeGame(false)">{{ t('classic.refresh_all') }}</button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── CLEAR METADATA DIALOG ─────────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="showClearDialog" class="gd-confirm-overlay" @click.self="showClearDialog = false">
      <div class="gd-confirm-box">
        <div class="gd-confirm-icon gd-confirm-icon--danger">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </div>
        <div class="gd-confirm-title">{{ t('detail.clear_metadata') }}</div>
        <div class="gd-confirm-body">
          {{ t('classic.clear_game_body', { title: game?.title || '' }) }}
        </div>
        <div class="gd-confirm-actions">
          <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="showClearDialog = false">{{ t('common.cancel') }}</button>
          <button class="gd-confirm-btn gd-confirm-btn--danger" @click="clearMetadata">{{ t('detail.clear_metadata') }}</button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── GAMES LIBRARY DOWNLOAD DIALOG ─────────────────────────────────── -->
  <teleport to="body">
    <div v-if="showLibDownload && game" class="cd-dl-overlay" @click.self="showLibDownload = false">
      <div class="cd-dl-dialog">
        <div class="cd-dl-header">
          <span class="cd-dl-title">{{ t('detail.download_title', { title: game.title }) }}</span>
          <button class="cd-dl-close" @click="showLibDownload = false">×</button>
        </div>
        <!-- OS tabs -->
        <div class="cd-dl-tabs">
          <button
            v-for="os in libAvailableOSes"
            :key="os"
            class="cd-dl-tab"
            :class="{ active: libDlOs === os }"
            @click="libDlOs = os"
          >{{ osLabel(os) }}</button>
        </div>
        <!-- Files -->
        <div class="cd-dl-files">
          <div v-if="!libFilesByOsAndType.length" class="cd-dl-empty">{{ t('detail.no_files') }}</div>
          <div v-for="group in libFilesByOsAndType" :key="group.type" class="cd-dl-type-section">
            <div class="cd-dl-type-head">{{ group.type === 'game' ? t('detail.type_game') : group.type === 'extra' ? t('detail.type_extras') : t('detail.type_dlc') }}</div>
            <label v-for="f in group.files" :key="f.id" class="cd-dl-row">
              <input type="checkbox" :checked="libDlSelected.has(f.id)" @change="libToggleSelect(f.id)" />
              <span class="cd-dl-name">{{ f.display_name || f.filename }}</span>
              <span v-if="f.version" class="cd-dl-ver">v{{ f.version }}</span>
              <span class="cd-dl-size">{{ formatSize(f.size_bytes) }}</span>
            </label>
          </div>
        </div>
        <div class="cd-dl-footer">
          <span class="cd-dl-count">{{ t('detail.files_selected', { count: libDlSelected.size }) }}</span>
          <button class="cd-dl-btn" :disabled="libDlSelected.size === 0 || libDownloading" @click="startLibDownload">
            <svg v-if="!libDownloading" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {{ libDownloading ? t('download.downloading') : t('detail.download_selected') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- ── LIGHTBOX (teleported to body) ──────────────────────────────────── -->
  <teleport to="body">
    <div v-if="lightboxIdx !== null" class="cd-lightbox" @click.self="lightboxIdx = null">
      <!-- Close -->
      <button class="cd-lb-close" @click="lightboxIdx = null">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
      <!-- Prev -->
      <button v-if="lightboxIdx > 0" class="cd-lb-arrow cd-lb-arrow--l" @click="lightboxIdx--">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <!-- Content -->
      <img v-if="lightboxCurrent?.type === 'image'" :src="lightboxCurrent.src" class="cd-lb-img" @click.stop />
      <!-- Local ROM video file -->
      <video
        v-else-if="lightboxCurrent?.type === 'video' && lightboxCurrent.kind === 'local'"
        :src="lightboxCurrent.src"
        controls autoplay
        class="cd-lb-video"
        @click.stop
      />
      <!-- YouTube embed -->
      <iframe
        v-else-if="lightboxCurrent?.type === 'video'"
        :src="lightboxCurrent.src"
        class="cd-lb-video"
        frameborder="0"
        allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
        allowfullscreen
        @click.stop
      />
      <!-- Next -->
      <button v-if="lightboxIdx < lightboxItems.length - 1" class="cd-lb-arrow cd-lb-arrow--r" @click="lightboxIdx++">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <!-- Counter -->
      <div class="cd-lb-counter">{{ (lightboxIdx ?? 0) + 1 }} / {{ lightboxItems.length }}</div>
    </div>
  </teleport>

  <!-- ── EMULATOR - fullscreen / window iframe ──────────────────────────── -->
  <teleport to="body">
    <div v-if="playerOpen" class="cd-player-wrap" :class="playerMode === 'full' ? 'cd-player--full' : 'cd-player--window'">
      <button class="cd-player-close" @click="closePlayer" title="Close emulator">✕</button>
      <iframe
        ref="playerIframe"
        :src="playerUrl"
        class="cd-player-frame"
        allow="gamepad; fullscreen"
        tabindex="0"
      />
    </div>
  </teleport>

  <!-- ── PLAY MODE DIALOG (identical to Modern/Emulation theme) ──────────── -->
  <teleport to="body">
    <div v-if="showPlayerDialog" class="gd-play-dialog-backdrop" @click.self="showPlayerDialog = false">
      <div class="gd-play-dialog">
        <div class="gd-play-dialog-title">Choose display mode</div>
        <div class="gd-play-dialog-sub">How would you like to open the emulator?</div>

        <div class="gd-play-mode-grid gd-play-mode-grid--3">
          <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'full' }" @click="pendingMode = 'full'">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
            </svg>
            <span class="gd-play-mode-name">Fullscreen</span>
            <span class="gd-play-mode-desc">Covers the entire screen</span>
          </button>
          <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'window' }" @click="pendingMode = 'window'">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <circle cx="7" cy="6" r="1" fill="currentColor"/>
              <circle cx="10" cy="6" r="1" fill="currentColor"/>
            </svg>
            <span class="gd-play-mode-name">Window</span>
            <span class="gd-play-mode-desc">Floating panel within the page</span>
          </button>
          <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'tab' }" @click="pendingMode = 'tab'">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="5" width="20" height="16" rx="2"/>
              <line x1="2" y1="10" x2="22" y2="10"/>
              <line x1="7" y1="5" x2="7" y2="10"/>
              <line x1="13" y1="5" x2="13" y2="10"/>
            </svg>
            <span class="gd-play-mode-name">New Tab</span>
            <span class="gd-play-mode-desc">Best gamepad support</span>
          </button>
        </div>

        <!-- Bezel toggle - only shown when this game has a bezel -->
        <div v-if="game?.bezel_path" class="gd-play-bezel-row">
          <div class="gd-play-bezel-info">
            <span class="gd-play-bezel-label">Bezel</span>
            <span class="gd-play-bezel-desc">Decorative frame overlay</span>
          </div>
          <button
            class="gd-play-bezel-toggle"
            :class="{ on: bezelEnabled }"
            @click="bezelEnabled = !bezelEnabled"
            :title="bezelEnabled ? 'Disable bezel' : 'Enable bezel'"
          >
            <span class="gd-play-bezel-knob" />
          </button>
        </div>

        <label class="gd-play-remember">
          <input type="checkbox" v-model="rememberMode" />
          <span>Remember my choice</span>
        </label>

        <div class="gd-play-dialog-actions">
          <button class="gd-play-cancel" @click="showPlayerDialog = false">Cancel</button>
          <button class="gd-play-confirm" @click="launchPlayer">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <polygon points="5,3 19,12 5,21"/>
            </svg>
            Play
          </button>
        </div>
      </div>
    </div>
  </teleport>

</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import client from '@/services/api/client'
import { buildLanguageList } from '@/utils/langMap'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import EmulationRomMetadataPanel from '@/views/emulation/EmulationRomMetadataPanel.vue'
import DownloadDialog from '@/components/gog/DownloadDialog.vue'
import { useThemeStore } from '@/stores/theme'
import { useNotifications } from '@/composables/useNotifications'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from '@/i18n'
import { sanitizeHtml } from '@/utils/sanitize'
import { getEjsCore } from '@/utils/ejsCores'

const themeStore = useThemeStore()
const { success: notifySuccess, error: notifyError } = useNotifications()
const authStore = useAuthStore()
const { t } = useI18n()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const props = defineProps<{ gameId: string | number; refreshTick?: number; activeLib?: string }>()

interface LibFile {
  id: number; filename: string; display_name: string
  file_type: string; os: string; version: string | null
  size_bytes: number | null; file_path: string; source: string; is_available: boolean
}

interface GameData {
  id: number; title: string; developer?: string; publisher?: string
  release_date?: string; rating?: number; genres?: string[]; tags?: string[]
  cover_url?: string; cover_path?: string; background_url?: string; background_path?: string
  logo_url?: string; logo_path?: string
  description?: string; description_short?: string
  screenshots?: any[]; videos?: any[]
  os_windows?: boolean; os_mac?: boolean; os_linux?: boolean
  languages?: Record<string, string> | string[]
  installers?: Record<string, { language: string; name: string; total_size: number }[]>
  requirements?: any
  meta_ratings?: { rawg?: number | null; igdb?: number | null; steam?: number | null }
  features?: string[]; file_size?: number; slug?: string; gog_id?: number
  // GAMES library fields
  files?: LibFile[]
  // ROM fields
  name?: string; fs_name_no_ext?: string; fs_extension?: string; fs_size_bytes?: number
  platform_name?: string; platform_slug?: string; platform_fs_slug?: string
  release_year?: number; regions?: string[]; languages_list?: string[]
  ss_score?: number; player_count?: string
  alternative_names?: string[]; franchises?: string[]
  hltb_main_s?: number; hltb_complete_s?: number
  summary?: string; wheel_path?: string; video_path?: string
  support_path?: string; bezel_path?: string; steamgrid_path?: string
}

const game        = ref<GameData | null>(null)
const loading     = ref(false)
const error       = ref('')
const coverFailed = ref(false)
const coverTried  = ref(0)   // 0=path, 1=url, 2=failed
const logoFailed  = ref(false)
const metaOpen    = ref(false)
const dlOpen      = ref(false)
const scraping         = ref(false)
// GAMES library download dialog
const showLibDownload  = ref(false)
const libDlOs          = ref('windows')
const libDlSelected    = ref<Set<number>>(new Set())
const libDownloading   = ref(false)
const showScrapeDialog = ref(false)
const clearing         = ref(false)
const showClearDialog  = ref(false)

// Lightbox - index-based (0 = video if present, then screenshots)
const lightboxIdx   = ref<number | null>(null)
const lightboxItems = computed<Array<{ type: 'image' | 'video'; src: string; kind?: string }>>(() => {
  const items: Array<{ type: 'image' | 'video'; src: string; kind?: string }> = []
  if (videoItem.value) items.push({ type: 'video', src: videoItem.value.embedUrl, kind: videoItem.value.kind })
  screenshotUrls.value.forEach(url => items.push({ type: 'image', src: url }))
  return items
})
const lightboxCurrent = computed(() =>
  lightboxIdx.value !== null ? lightboxItems.value[lightboxIdx.value] : null
)

// Media strip navigation (same mechanism as Modern theme)
const stripEl   = ref<HTMLElement | null>(null)
const slideIdx  = ref(0)
const totalSlides = computed(() => (videoItem.value ? 1 : 0) + screenshotUrls.value.length)

// ── URL helpers ──────────────────────────────────────────────────────────────

// Hero animation class - identical logic to Modern theme (GogGameDetail.vue)
const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `cd-hero--${themeStore.heroAnimStyle}`   // cd- prefix = ClassicDetail
})

/** Strip deprecated GOG CDN formatter suffixes, normalise // prefix */
function fixGogUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('//')) url = 'https:' + url
  // e.g. _product_card.jpg → .jpg
  url = url.replace(/(_[a-z0-9_]+)(\.(?:jpg|png|webp))$/i, '$2')
  return url
}

// ── Computed ─────────────────────────────────────────────────────────────────
// NOTE: *_path fields from the backend are already web-relative paths like
//       /resources/gog/{id}/covers/cover_auto.jpg  - use them DIRECTLY.
//       Do NOT extract just the filename (loses the gog/{id}/ subdirectory).
//       Only apply fixGogUrl() to raw CDN urls (cover_url, background_url etc.)

const coverSrc = computed(() => {
  if (!game.value) return ''
  const g = game.value
  if (coverTried.value === 0 && g.cover_path) return g.cover_path          // direct - same as Modern theme
  if (coverTried.value <= 1 && g.cover_url)   return fixGogUrl(g.cover_url)
  return ''
})

const heroBgStyle = computed(() => {
  if (!game.value) return {}
  const g = game.value
  // Exact same fallback chain as Modern theme (GogGameDetail.vue bgStyle):
  //   local background → CDN background → local cover → CDN cover
  const url = g.background_path
    || fixGogUrl(g.background_url || '')
    || g.cover_path
    || fixGogUrl(g.cover_url || '')
  return url ? { backgroundImage: `url("${url}")` } : {}
})

const releaseYear = computed(() => game.value?.release_date?.slice(0, 4) || '')

const logoSrc = computed(() => {
  const g = game.value
  if (!g) return ''
  if (g.logo_path) return g.logo_path
  if (g.logo_url)  return fixGogUrl(g.logo_url)
  // ROMs: use wheel as title logo
  if (props.activeLib === 'roms' && g.wheel_path) return g.wheel_path
  return ''
})

// ── 3D tilt (same as Modern theme, respects themeStore.cardTilt/cardShine) ──
const coverTilt  = ref('perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)')
const sheenStyle = ref('opacity:0')

function onCoverMove(e: MouseEvent) {
  if (!themeStore.cardTilt) return
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.width / 2; const cy = rect.height / 2
  const dx = e.clientX - rect.left - cx
  const dy = e.clientY - rect.top  - cy
  const rotY =  (dx / cx) * 10
  const rotX = -(dy / cy) *  7
  coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
  if (themeStore.cardShine) {
    const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
    const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
    sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
  }
}
function onCoverLeave() {
  coverTilt.value = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
  sheenStyle.value = 'opacity:0'
}

const screenshotUrls = computed(() => {
  const shots = game.value?.screenshots || []
  return shots
    .map((s: any) => (typeof s === 'string' ? s : s.url || s.thumb || ''))
    .filter(Boolean)
})

const videoItem = computed(() => {
  const g = game.value
  if (!g) return null

  // ROMs: local video file (video_path is a web-relative path like /resources/roms/...)
  if (props.activeLib === 'roms' && g.video_path) {
    const shots = g.screenshots as string[] | undefined
    const thumb = shots?.[0] || g.cover_path || ''
    return { thumb, embedUrl: g.video_path, kind: 'local' as const }
  }

  // GOG/Games: YouTube video
  const vids = g.videos as any[] | undefined
  if (!vids?.length) return null
  const v = vids.find((v: any) => v.provider === 'youtube' && v.video_id) || vids[0]
  if (!v) return null
  let videoId: string = v.video_id || ''
  if (!videoId) {
    const rawUrl: string = v.video_url || v.url || v.videoUrl || ''
    const ytMatch = rawUrl.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/)
    videoId = ytMatch?.[1] || ''
  }
  if (!videoId) return null
  return {
    thumb: `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,
    embedUrl: `https://www.youtube.com/embed/${videoId}?rel=0&modestbranding=1&autoplay=1`,
    kind: 'youtube' as const,
  }
})

// Language code → { flag emoji, display name }
// Language flags - use shared utility with deduplication
  // Try Intl as fallback
const languageFlags = computed(() => buildLanguageList(game.value?.languages))

const hasRatings = computed(() =>
  !!(game.value?.rating
    || game.value?.meta_ratings?.rawg != null
    || game.value?.meta_ratings?.igdb != null
    || game.value?.meta_ratings?.steam != null)
)

const descHtml = computed(() => game.value?.description || game.value?.description_short || '')

// ── Requirements ─────────────────────────────────────────────────────────────

const REQ_SHOW = new Set(['processor', 'cpu', 'memory', 'ram', 'graphics', 'gpu', 'video'])

function formatReqKey(k: string): string {
  const key = k.toLowerCase()
  if (['processor', 'cpu'].includes(key))       return 'CPU'
  if (['memory', 'ram'].includes(key))           return 'RAM'
  if (['graphics', 'gpu', 'video'].includes(key)) return 'GPU'
  return k
}

const reqRows = computed((): [string, string][] => {
  const reqs = game.value?.requirements
  if (!reqs) return []
  let minimum: any = null
  if (reqs.minimum) minimum = reqs.minimum
  else if (reqs.Windows?.minimum) minimum = reqs.Windows.minimum
  else if (reqs.windows?.minimum) minimum = reqs.windows.minimum
  else if (reqs.per_os) {
    const win = (reqs.per_os as any[]).find((o: any) => (o.os || '').toLowerCase().includes('win'))
    minimum = win?.minimum
  } else {
    const first = Object.values(reqs)[0] as any
    if (first?.minimum) minimum = first.minimum
  }
  if (!minimum) return []
  if (Array.isArray(minimum)) {
    return minimum
      .filter((r: any) => REQ_SHOW.has((r.name || r.id || '').toLowerCase()) && (r.description || r.value))
      .map((r: any) => [r.name || r.id, r.description || r.value] as [string, string])
  }
  if (typeof minimum === 'string') {
    const rows: [string, string][] = []
    for (const line of minimum.split(/\n/)) {
      const m = line.match(/^([^:]+):\s*(.+)/)
      if (m && REQ_SHOW.has(m[1].trim().toLowerCase())) rows.push([m[1].trim(), m[2].trim()])
    }
    return rows
  }
  if (typeof minimum === 'object') {
    return Object.entries(minimum)
      .filter(([k, v]) => REQ_SHOW.has(k.toLowerCase()) && v)
      .map(([k, v]) => [k, String(v)] as [string, string])
  }
  return []
})

// ── GAMES library download helpers ───────────────────────────────────────────

const libAvailableFiles = computed(() =>
  (game.value?.files ?? []).filter(f => f.is_available)
)

const libAvailableOSes = computed(() => {
  const oses = new Set(libAvailableFiles.value.map(f => f.os))
  return (['windows', 'mac', 'linux', 'all'] as const).filter(o => oses.has(o))
})

const libFilesByOsAndType = computed(() => {
  const os = libDlOs.value
  const files = libAvailableFiles.value.filter(f => f.os === os || f.os === 'all')
  const byType: Record<string, LibFile[]> = {}
  for (const f of files) {
    if (!byType[f.file_type]) byType[f.file_type] = []
    byType[f.file_type].push(f)
  }
  return (['game', 'dlc', 'extra'] as const).filter(t => byType[t]).map(t => ({ type: t, files: byType[t] }))
})

watch(libAvailableOSes, (oses) => {
  if (oses.length && !oses.includes(libDlOs.value as any)) libDlOs.value = oses[0]
}, { immediate: true })

watch(libDlOs, () => libDlSelected.value.clear())

watch(showLibDownload, (open) => {
  if (!open) return
  libDlSelected.value.clear()
  const gameFiles = libFilesByOsAndType.value.find(g => g.type === 'game')?.files ?? []
  gameFiles.forEach(f => libDlSelected.value.add(f.id))
})

function libToggleSelect(id: number) {
  if (libDlSelected.value.has(id)) libDlSelected.value.delete(id)
  else libDlSelected.value.add(id)
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function osLabel(os: string) {
  return os === 'windows' ? 'Windows' : os === 'mac' ? 'macOS' : os === 'linux' ? 'Linux' : 'All'
}

async function startLibDownload() {
  libDownloading.value = true
  const token = localStorage.getItem('gd3_token') || ''
  for (const id of libDlSelected.value) {
    try {
      const url = `/api/library/download/${id}`
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) continue
      const blob = await resp.blob()
      const cd = resp.headers.get('Content-Disposition') || ''
      const nameMatch = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      const filename = nameMatch ? nameMatch[1].replace(/['"]/g, '') : `file_${id}`
      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl; a.download = filename; a.click()
      setTimeout(() => URL.revokeObjectURL(objUrl), 10000)
    } catch { /* skip failed file */ }
  }
  libDownloading.value = false
  showLibDownload.value = false
}

// ── Events ───────────────────────────────────────────────────────────────────

// ── Lightbox ─────────────────────────────────────────────────────────────────

function slideTo(idx: number) {
  const max = Math.max(0, totalSlides.value - 4)
  slideIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = stripEl.value
    if (!el) return
    const child = el.children[slideIdx.value] as HTMLElement
    if (child) el.scrollTo({ left: child.offsetLeft, behavior: 'smooth' })
  })
}

function openLightbox(idx: number) {
  if (!lightboxItems.value[idx]?.src) return
  lightboxIdx.value = idx
}

function onKeydown(e: KeyboardEvent) {
  if (lightboxIdx.value === null) return
  if (e.key === 'Escape')      { lightboxIdx.value = null }
  else if (e.key === 'ArrowLeft'  && lightboxIdx.value > 0)                              { lightboxIdx.value-- }
  else if (e.key === 'ArrowRight' && lightboxIdx.value < lightboxItems.value.length - 1) { lightboxIdx.value++ }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (_publishPollTimer !== null) { clearInterval(_publishPollTimer); _publishPollTimer = null }
})

// ── Cover errors ──────────────────────────────────────────────────────────────

function onCoverError() {
  if (coverTried.value === 0 && game.value?.cover_url) {
    coverTried.value = 1   // try CDN url next
  } else {
    coverFailed.value = true
  }
}

function onMetaSaved() {
  metaOpen.value = false
  loadGame(props.gameId)
}

function onLibMetaSaved() {
  metaOpen.value = false
  loadGame(props.gameId)
}

function onScrapeClick() {
  if (!game.value || scraping.value) return
  // If game already has external ratings ask what to preserve (same as Modern theme)
  const hasExternal = !!(game.value.meta_ratings?.rawg || game.value.meta_ratings?.igdb)
  if (hasExternal) {
    showScrapeDialog.value = true
  } else {
    scrapeGame(false)
  }
}

async function scrapeGame(preserveExternal: boolean) {
  if (!game.value || scraping.value) return
  showScrapeDialog.value = false
  coverFailed.value = false
  scraping.value = true
  try {
    if (props.activeLib === 'roms') {
      await client.post(`/roms/${game.value.id}/scrape`)
      setTimeout(async () => { await loadGame(game.value!.id); scraping.value = false }, 4000)
    } else {
      const params = preserveExternal ? '?preserve_external=true' : ''
      await client.post(`/gog/library/games/${game.value.id}/scrape${params}`)
      let n = 0
      const poll = setInterval(async () => {
        if (++n > 30) { clearInterval(poll); scraping.value = false; return }
        try {
          const { data } = await client.get(`/gog/library/games/${game.value!.id}`)
          if (data.scraped) { clearInterval(poll); scraping.value = false; game.value = data as GameData }
        } catch { clearInterval(poll); scraping.value = false }
      }, 1500)
    }
  } catch { scraping.value = false }
}

async function downloadRom() {
  if (!game.value) return
  const token = localStorage.getItem('gd3_token') || ''
  const url = `/api/roms/${game.value.id}/download`
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!resp.ok) return
  const blob = await resp.blob()
  const cd = resp.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
  const filename = m ? m[1].replace(/['"]/g, '') : (game.value as any).fs_name || 'rom'
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = objUrl; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(objUrl), 10000)
}

function onClearClick() {
  if (!game.value || clearing.value) return
  showClearDialog.value = true
}

async function clearMetadata() {
  if (!game.value || clearing.value) return
  showClearDialog.value = false
  clearing.value = true
  const title = game.value.title
  try {
    if (props.activeLib === 'roms') {
      await client.post(`/roms/${game.value.id}/clear-metadata`)
    } else if (props.activeLib === 'games') {
      await client.post(`/library/games/${game.value.id}/clear-metadata`)
    } else {
      await client.delete(`/gog/library/games/${game.value.id}/metadata`)
    }
    coverFailed.value = false; coverTried.value = 0
    await loadGame(game.value.id)
    notifySuccess(`Metadata cleared for "${title}".`)
  } catch {
    notifyError(`Failed to clear metadata for "${title}".`)
  } finally { clearing.value = false }
}

// ── API ──────────────────────────────────────────────────────────────────────

async function loadGame(id: string | number) {
  if (!id) return
  loading.value = true
  error.value   = ''
  coverFailed.value = false
  coverTried.value  = 0
  logoFailed.value  = false
  slideIdx.value    = 0
  game.value = null
  try {
    let endpoint: string
    if (props.activeLib === 'roms')  endpoint = `/roms/${id}`
    else if (props.activeLib === 'games') endpoint = `/library/games/${id}`
    else endpoint = `/gog/library/games/${id}`
    const { data } = await client.get(endpoint)
    if (props.activeLib === 'roms') {
      // Normalize ROM data to GameData shape
      game.value = {
        ...data,
        title:          data.name || data.fs_name_no_ext || String(id),
        release_date:   data.release_year ? String(data.release_year) : undefined,
        description:    data.summary,
        languages:      data.languages_list || data.languages,
        screenshots:    (data.screenshots || []).map((s: any) => typeof s === 'string' ? s : (s.url || s.path || '')),
        videos:         data.video_path ? [{ type: 'local', path: data.video_path }] : [],
      } as GameData
    } else {
      game.value = data as GameData
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load game'
  } finally {
    loading.value = false
  }
}

watch(() => props.gameId, id => { loadGame(id) }, { immediate: true })
// Re-fetch after external sync (refreshTick incremented by ClassicLayout after syncLib)
watch(() => props.refreshTick, () => { if (props.gameId) loadGame(props.gameId) })

// ── Publish to Library ──────────────────────────────────────────────────────
const publishLoading = ref(false)
const publishedId    = ref<number | null>(null)
const publishMsg     = ref('')
let   _publishPollTimer: ReturnType<typeof setInterval> | null = null

async function checkPublishStatus(gogGameId: number) {
  try {
    const { data } = await client.get(`/library/games/gog/${gogGameId}`)
    if (data?.id) publishedId.value = data.id
  } catch { /* not published */ }
}

async function publishToLibrary(pendingDownload = false) {
  if (!game.value?.id || publishLoading.value) return
  publishLoading.value = true
  publishMsg.value = ''
  try {
    const { data } = await client.post(`/library/games/publish/${game.value.id}`)
    publishedId.value = data.id
    if (pendingDownload) {
      publishMsg.value = 'Added to library - files will sync after download'
    } else {
      publishMsg.value = data._scanned > 0
        ? `Re-synced - ${data._scanned} file(s) added`
        : `Library up to date (${data._total ?? 0} file(s))`
    }
    setTimeout(() => publishMsg.value = '', 6000)
  } catch (e: any) {
    publishMsg.value = e?.response?.data?.detail || 'Publish failed'
  } finally {
    publishLoading.value = false
  }
}

/** Called when DownloadDialog emits 'publish-library' */
async function onPublishLibrary({ jobIds }: { gogId: number; jobIds: number[] }) {
  await publishToLibrary(jobIds.length > 0)

  if (!jobIds.length) return

  const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
  let failCount = 0
  if (_publishPollTimer !== null) clearInterval(_publishPollTimer)
  _publishPollTimer = setInterval(async () => {
    try {
      const statuses = await Promise.all(
        jobIds.map((id: number) => client.get(`/gog/downloads/${id}`).then((r: any) => r.data.status as string))
      )
      failCount = 0
      if (statuses.every((s: string) => TERMINAL.has(s))) {
        clearInterval(_publishPollTimer!); _publishPollTimer = null
        if (statuses.some((s: string) => s === 'completed')) {
          await publishToLibrary()
        }
      }
    } catch {
      failCount++
      if (failCount >= 5) { clearInterval(_publishPollTimer!); _publishPollTimer = null }
    }
  }, 6000)
}

watch(() => game.value?.id, (id) => {
  publishedId.value = null
  if (id && isAdmin.value && props.activeLib !== 'games') checkPublishStatus(id)
}, { immediate: true })

// ── Emulator player (ROM library only) ───────────────────────────────────────
const PREF_KEY_EMU       = 'gd3_emu_display_mode'
const showPlayerDialog   = ref(false)
const pendingMode        = ref<'full' | 'window' | 'tab'>('full')
const rememberMode       = ref(false)
const playerOpen         = ref(false)
const playerMode         = ref<'full' | 'window'>('full')
const playerIframe       = ref<HTMLIFrameElement | null>(null)
const bezelEnabled       = ref(false)

const bezelKey = (id: number | string) => `gd3_bezel_${id}`

const ejsCore = computed(() =>
  props.activeLib === 'roms' && game.value?.platform_fs_slug
    ? getEjsCore(game.value.platform_fs_slug)
    : null
)

const playerUrl = computed(() => {
  if (!game.value || !ejsCore.value) return ''
  const g = game.value
  const p = new URLSearchParams({
    rom_id:   String(g.id),
    rom_name: g.name || g.fs_name_no_ext || String(g.id),
    ejs_core: ejsCore.value,
    platform: g.platform_fs_slug || '',
  })
  if (g.bezel_path && bezelEnabled.value) p.set('bezel_url', g.bezel_path)
  return `/player.html?${p.toString()}`
})

function requestPlay() {
  const saved = localStorage.getItem(PREF_KEY_EMU) as 'full' | 'window' | 'tab' | null
  // Load bezel pref for this specific game (default off)
  if (game.value?.bezel_path && game.value.id) {
    const bSaved = localStorage.getItem(bezelKey(game.value.id))
    bezelEnabled.value = bSaved === '1'
  }
  if (saved) {
    pendingMode.value = saved
    showPlayerDialog.value = true  // always show so bezel toggle is visible
  } else {
    pendingMode.value = 'full'
    rememberMode.value = false
    showPlayerDialog.value = true
  }
}

function launchPlayer() {
  if (rememberMode.value) localStorage.setItem(PREF_KEY_EMU, pendingMode.value)
  if (game.value?.id) localStorage.setItem(bezelKey(game.value.id), bezelEnabled.value ? '1' : '0')
  showPlayerDialog.value = false
  if (pendingMode.value === 'tab') {
    window.open(playerUrl.value, '_blank')
    return
  }
  playerMode.value = pendingMode.value
  playerOpen.value = true
}

function closePlayer() {
  playerOpen.value = false
}

// Handle postMessage from player iframe
function onPlayerMessage(e: MessageEvent) {
  if (e.data?.type === 'gd-exit') closePlayer()
}

onMounted(() => window.addEventListener('message', onPlayerMessage))
onUnmounted(() => window.removeEventListener('message', onPlayerMessage))
</script>

<style scoped>
.cd-wrap {
  display: flex; flex-direction: column;
  flex: 1; overflow-y: auto; overflow-x: hidden;
  /* Reserve scrollbar gutter so width stays constant when content overflows. */
  scrollbar-gutter: stable;
}

/* Loading / error */
.cd-loading { flex: 1; display: flex; align-items: center; justify-content: center; }
.cd-spin { animation: cd-spin-anim 1s linear infinite; }
@keyframes cd-spin-anim { to { transform: rotate(360deg); } }
.cd-error { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--danger); font-size: 13px; }

/* ── COVER HERO ────────────────────────────────────────────────────────────── */
.cover-hero {
  display: flex; flex-direction: column; align-items: center;
  padding: 28px 20px 20px; flex-shrink: 0;
  position: relative; overflow: hidden;
}
.hero-vignette {
  position: absolute; top: 0; left: 0; right: 0; height: 100%;
  background: transparent;
  pointer-events: none; z-index: 2;
}
.hero-bg { position: absolute; inset: 0; z-index: 0; overflow: hidden; }
.hero-bg-inner {
  position: absolute; inset: -10%;
  background-size: cover; background-position: center center;
  /* filter applied via :style binding (uses themeStore.heroBlur)  */
  /* animation applied via :class heroAnimClass (uses themeStore.heroAnimStyle / heroAnim) */
  transform-origin: center center;
  transform: scale(1.06);
  will-change: transform;
}

/* ── Hero animation keyframes - identical to Modern theme ─────────────────── */
/* Ken Burns - classic documentary zoom + gentle pan */
@keyframes cd-kenburns {
  0%   { transform: scale(1.06) translate(0%,    0%   ); }
  20%  { transform: scale(1.12) translate(-2.5%, 1%   ); }
  45%  { transform: scale(1.09) translate( 1.5%, -1.5%); }
  70%  { transform: scale(1.14) translate(-1%,   2%   ); }
  100% { transform: scale(1.06) translate(0%,    0%   ); }
}
/* Drift - slow lateral pan with slight zoom */
@keyframes cd-drift {
  0%   { transform: scale(1.1) translateX(0%);  }
  50%  { transform: scale(1.1) translateX(-5%); }
  100% { transform: scale(1.1) translateX(0%);  }
}
/* Pulse - smooth breathing zoom */
@keyframes cd-pulse {
  0%   { transform: scale(1.04); }
  50%  { transform: scale(1.11); }
  100% { transform: scale(1.04); }
}

/* Applied via :class heroAnimClass - speed uses shared --hero-anim-speed CSS var */
.cd-hero--kenburns {
  animation: cd-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
.cd-hero--drift {
  animation: cd-drift calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate;
}
.cd-hero--pulse {
  animation: cd-pulse calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite;
}
/* Respect global animations toggle (same selector as Modern theme) */
[data-animations="false"] .cd-hero--kenburns,
[data-animations="false"] .cd-hero--drift,
[data-animations="false"] .cd-hero--pulse { animation: none; }
.hero-bg-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to bottom,
    color-mix(in srgb, var(--bg) 15%, transparent) 0%,
    color-mix(in srgb, var(--bg) 50%, transparent) 40%,
    color-mix(in srgb, var(--bg) 85%, transparent) 72%,
    var(--bg) 100%);
}

/* Cover image + overlay */
/* cover-wrap: tilt needs transform-style preserve-3d */
.cover-wrap { position: relative; z-index: 3; transform-style: preserve-3d; }

/* Elements BELOW cover-wrap in DOM flow are non-positioned → would render below
   the absolute hero-bg (z-index:0). Fix: make them positioned above. */
.game-logo, .game-wheel, .game-title, .cover-ratings, .meta-chips { position: relative; z-index: 4; }

/* Game logo (transparent, max width to not overflow) */
.game-logo {
  max-width: 320px;
  max-height: 110px;
  width: auto;
  height: auto;
  object-fit: contain;
  filter: drop-shadow(0 4px 16px rgba(0,0,0,.8));
  margin-top: 6px;
}

/* ROM wheel logo - wider allowance, left-aligned like Modern theme */
.game-wheel {
  max-height: clamp(48px, 7vw, 88px);
  max-width: 380px;
  width: auto;
  height: auto;
  object-fit: contain;
  object-position: left center;
  filter: drop-shadow(0 2px 12px rgba(0,0,0,.8));
  margin-top: 8px;
  display: block;
}

/* Specular sheen overlay */
.cover-sheen {
  position: absolute; inset: 0; border-radius: 14px;
  pointer-events: none; z-index: 4;
  transition: opacity .25s;
}
.cover-img {
  width: calc(var(--cd-cover-h, 525px) * 2 / 3); height: var(--cd-cover-h, 525px);
  object-fit: cover; border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--pl-light) 40%, transparent);
  box-shadow: 0 20px 60px rgba(0,0,0,.8), 0 0 0 1px rgba(255,255,255,.04), 0 0 40px var(--pglow2);
  display: block;
}
/* ROM covers: natural aspect ratio - no letterboxing, border wraps exact image */
.cover-img--rom {
  width: auto;
  height: auto;
  max-height: var(--cd-cover-h, 525px);
  max-width: 420px;
  object-fit: unset;
}
.cover-ph {
  width: calc(var(--cd-cover-h, 525px) * 2 / 3); height: var(--cd-cover-h, 525px); border-radius: 14px;
  border: 1px dashed var(--pglow2);
  display: flex; align-items: center; justify-content: center;
  background: var(--glass-highlight);
}
.cover-ph--rom {
  width: calc(var(--cd-cover-h, 525px) * 3 / 4);
}

/* Cover action overlay (download + edit) */
.cover-overlay {
  position: absolute; inset: 0; border-radius: 14px;
  background: linear-gradient(180deg, transparent 40%, rgba(0,0,0,.75) 100%);
  display: flex; align-items: flex-end; justify-content: center;
  gap: 10px; padding-bottom: 16px;
  opacity: 0; transition: opacity .2s;
}
.cover-wrap:hover .cover-overlay { opacity: 1; }
.cov-btn {
  width: 38px; height: 38px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 55%, transparent); border: 1px solid color-mix(in srgb, var(--pl-light) 60%, transparent);
  color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .15s, transform .15s;
}
.cov-btn:hover { background: color-mix(in srgb, var(--pl) 85%, transparent); transform: scale(1.1); }
.cov-btn--danger { background: rgba(220,38,38,.45) !important; border-color: rgba(239,68,68,.6) !important; }
.cov-btn--danger:hover { background: rgba(220,38,38,.8) !important; }

/* Title */
.game-title {
  margin-top: 18px;
  font-family: 'Rajdhani', var(--font); font-size: 34px; font-weight: 700; letter-spacing: .5px;
  text-align: center; line-height: 1.1; position: relative; z-index: 3;
  color: var(--text); text-shadow: 0 2px 20px var(--pglow);
}

/* Ratings row (below title) */
.cover-ratings {
  display: flex; flex-wrap: wrap; justify-content: center;
  gap: 10px; margin-top: 10px; z-index: 3; position: relative;
}
.crating {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.crating-ico { width: 35px; height: 35px; object-fit: contain; }
.crating small { color: var(--muted); font-size: 11px; font-weight: 400; }

/* Meta chips */
.meta-chips {
  display: flex; flex-wrap: wrap; justify-content: center;
  gap: 5px; margin-top: 8px; z-index: 3; position: relative;
}
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 12px; border-radius: 20px; font-size: 13px;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  color: var(--muted); white-space: nowrap; backdrop-filter: blur(8px);
}
.chip span { color: var(--text); }

/* ── MEDIA STRIP: video + screenshots, 4 visible, scrollable ─────────────── */
/* ── MEDIA STRIP - identyczny mechanizm co Modern theme ──────────────────── */
/* Kluczowa różnica vs poprzednia impl.: strips-wrap jest flex-row z przyciskami,
   shots-strip ma flex:1 → definitywna szerokość → % w shot-item działa poprawnie */
.shots-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 20px 10px;
  background: linear-gradient(145deg, var(--glass-highlight) 0%, rgba(0,0,0,.5) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border); border-top: 1px solid color-mix(in srgb, var(--pl-light) 30%, transparent);
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.03);
  padding: 10px 8px;
}
.shots-nav {
  flex-shrink: 0;
  width: 28px; height: 28px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid var(--glass-border);
  color: rgba(255,255,255,.7);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.shots-nav:hover:not(:disabled) { background: var(--pglow); color: #fff; }
.shots-nav:disabled { opacity: .25; cursor: default; }
.shots-strip {
  flex: 1;   /* ← definitywna szerokość = rodzic minus przyciski → % działa! */
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  scrollbar-width: none;   /* ukryty jak w Modern theme */
  -webkit-overflow-scrolling: touch;
}
.shots-strip::-webkit-scrollbar { display: none; }
/* 4 widoczne naraz: (100% - 3 × 6px gap) / 4  - działa bo strip ma flex:1 */
.shot-item {
  flex: 0 0 calc((100% - 18px) / 4);
  aspect-ratio: 16/9;
  border-radius: 7px;
  overflow: hidden;
  cursor: pointer;
  scroll-snap-align: start;
  border: 2px solid transparent;
  box-shadow: 0 4px 12px rgba(0,0,0,.5);
  transition: border-color .2s, box-shadow .2s;
  position: relative;
}
.shot-item:hover {
  border-color: var(--pl);
  box-shadow: 0 0 0 1px var(--pl), 0 6px 20px var(--pglow);
}
.shot-thumb-img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.shot-thumb-img--dark {
  background: rgba(0,0,0,.5);
}

/* Video play overlay */
.shot-item--video .shot-play-btn {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.4);
  color: #fff;
  transition: background .2s;
}
.shot-item--video:hover .shot-play-btn { background: color-mix(in srgb, var(--pl) 55%, transparent); }

/* ── LIGHTBOX ──────────────────────────────────────────────────────────────── */
.cd-lightbox {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.92);
  display: flex; align-items: center; justify-content: center;
  cursor: zoom-out;
  animation: lb-in .15s ease;
}
@keyframes lb-in { from { opacity: 0; } to { opacity: 1; } }
.cd-lb-close {
  position: absolute; top: 20px; right: 20px;
  width: 38px; height: 38px; border-radius: 50%;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.2);
  color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s; z-index: 1;
}
.cd-lb-close:hover { background: rgba(255,255,255,.2); }
.cd-lb-img {
  max-width: 92vw; max-height: 90vh;
  border-radius: 10px; box-shadow: 0 20px 80px rgba(0,0,0,.8);
  cursor: default; object-fit: contain;
}
.cd-lb-video {
  width: min(90vw, 1280px);
  height: min(calc(min(90vw, 1280px) * 9/16), 90vh);
  border-radius: 10px; cursor: default;
}
.cd-lb-arrow {
  position: absolute;
  top: 50%; transform: translateY(-50%);
  width: 44px; height: 44px; border-radius: 50%;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25);
  color: #fff; cursor: pointer; font-family: inherit;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s; z-index: 2;
}
.cd-lb-arrow:hover { background: rgba(255,255,255,.25); }
.cd-lb-arrow--l { left: 20px; }
.cd-lb-arrow--r { right: 20px; }
.cd-lb-counter {
  position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
  font-size: 13px; font-weight: 600; color: rgba(255,255,255,.6);
  font-variant-numeric: tabular-nums;
}

/* ── INFO CARDS ──────────────────────────────────────────────────────────── */
.info-cards {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 10px; padding: 0 20px 14px; flex-shrink: 0;
}
.icard {
  border-radius: 14px; padding: 14px 16px;
  background: linear-gradient(145deg, var(--pl-dim) 0%, rgba(0,0,0,.7) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%)); -webkit-backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border); border-top: 1px solid color-mix(in srgb, var(--pl-light) 40%, transparent);
  box-shadow: 0 8px 24px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.04);
}
.icard-head {
  display: flex; align-items: center; gap: 6px;
  font-family: 'Rajdhani', var(--font); font-size: 13px; font-weight: 700;
  letter-spacing: 1.5px; color: var(--pl-light); text-transform: uppercase;
  margin-bottom: 10px; border-bottom: 1px solid var(--glass-border); padding-bottom: 8px;
}
.icard-row { font-size: 13px; margin-bottom: 5px; line-height: 1.5; }
.icard-label { color: var(--muted); }
.icard-val { color: var(--text); }

/* Genre tags */
.genre-tags { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); padding: 2px 0; }
.genre-tag {
  display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  color: var(--muted); white-space: nowrap;
}

/* Language flags - emoji only, name on :title tooltip */
.lang-flags { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 4px; }
.lang-flag-em {
  font-size: var(--fs-xl, 18px); line-height: 1; cursor: default;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,.5));
  transition: transform .15s;
}
.lang-flag-em:hover { transform: scale(1.3); }

/* Refresh button spin animation */
.cov-btn--spin { opacity: .7; cursor: default; }
.cov-btn--spin svg { animation: cov-spin 1s linear infinite; }
@keyframes cov-spin { to { transform: rotate(360deg); } }

/* OS icons */
.os-icons { display: flex; gap: var(--space-2, 8px); margin-top: 5px; align-items: center; }
.os-icon { color: var(--pglow2); transition: color .2s; display: flex; align-items: center; }
.os-icon.active { color: var(--pl-light); filter: drop-shadow(0 0 4px color-mix(in srgb, var(--pl-light) 60%, transparent)); }
.os-icon-linux { width: 40px; height: 40px; opacity: .25; filter: invert(1) sepia(1) saturate(0) brightness(.6); transition: opacity .2s, filter .2s; }
.os-icon.active .os-icon-linux { opacity: .9; filter: invert(1) sepia(1) saturate(3) hue-rotate(220deg) brightness(1.1); }

/* Requirements */
.req-table { width: 100%; font-size: var(--fs-sm, 12px); border-collapse: collapse; }
.req-table tr { border-bottom: 1px solid var(--pl-dim); }
.req-table tr:last-child { border: none; }
.req-table td { padding: 4px 3px; vertical-align: top; line-height: 1.4; }
.req-name { color: var(--pl-light); font-weight: 700; font-family: 'Rajdhani', var(--font); letter-spacing: .4px; width: 46px; white-space: nowrap; }
.req-min { color: var(--text); font-size: 11px; }
.req-none { color: var(--muted); font-size: var(--fs-sm, 12px); font-style: italic; }

/* ── DESCRIPTION ──────────────────────────────────────────────────────────── */
.desc-section {
  padding: 0 20px 28px; flex-shrink: 0;
  max-width: 900px;      /* readable line length even on wide screens */
  width: 100%;
  margin-left: auto; margin-right: auto;
  box-sizing: border-box;
}
.section-head {
  display: flex; align-items: center; gap: 7px;
  font-family: 'Rajdhani', var(--font); font-size: var(--fs-md, 14px); font-weight: 700;
  letter-spacing: 1.5px; color: var(--muted); text-transform: uppercase;
  margin-bottom: 10px; border-bottom: 1px solid var(--glass-border); padding-bottom: 8px;
}
.desc-body { font-size: 13px; line-height: 1.8; color: var(--muted); }
.desc-body :deep(h1),.desc-body :deep(h2),.desc-body :deep(h3) { font-family: 'Rajdhani', var(--font); color: var(--text); margin: 10px 0 4px; font-size: var(--fs-md, 14px); }
.desc-body :deep(p) { margin-bottom: 8px; }
.desc-body :deep(ul),.desc-body :deep(ol) { margin: 6px 0 8px 18px; }
.desc-body :deep(li) { margin-bottom: 3px; }
.desc-body :deep(a) { color: var(--pl); text-decoration: none; }
.desc-body :deep(strong),.desc-body :deep(b) { color: var(--text); }

/* ── SCRAPE CONFIRM DIALOG (mirrors Modern theme) ─────────────────────────── */
.gd-confirm-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.gd-confirm-box {
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  padding: 32px 36px; max-width: 440px; width: 90%;
  display: flex; flex-direction: column; gap: 14px;
}
.gd-confirm-icon {
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center; color: var(--pl-light);
}
.gd-confirm-title { font-size: 17px; font-weight: 700; color: var(--text); }
.gd-confirm-body  { font-size: 13px; color: var(--muted); line-height: 1.6; }
.gd-confirm-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 6px; }
.gd-confirm-btn {
  padding: 9px 20px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all .15s;
}
.gd-confirm-btn--ghost {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted);
}
.gd-confirm-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.gd-confirm-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); box-shadow: 0 0 14px var(--pglow2);
}
.gd-confirm-btn--primary:hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }
.gd-confirm-icon--danger {
  background: rgba(220,38,38,.15); border-color: rgba(239,68,68,.3); color: #f87171;
}
.gd-confirm-btn--danger {
  background: rgba(220,38,38,.8); border: 1px solid rgba(239,68,68,.6); color: #fff;
}
.gd-confirm-btn--danger:hover { background: rgb(220,38,38); }

/* ── GAMES library download dialog ──────────────────────────────────────── */
.cd-dl-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.cd-dl-dialog {
  width: min(480px, 92vw);
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  overflow: hidden;
}
.cd-dl-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid var(--glass-border);
}
.cd-dl-title { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); }
.cd-dl-close {
  background: none; border: none; color: var(--muted); font-size: var(--fs-2xl, 22px);
  cursor: pointer; line-height: 1; padding: 0 2px;
}
.cd-dl-close:hover { color: var(--text); }
.cd-dl-tabs {
  display: flex; gap: var(--space-1, 4px); padding: 10px 14px 0;
}
.cd-dl-tab {
  padding: 5px 14px; border-radius: 6px; font-size: var(--fs-sm, 12px); font-weight: 600;
  border: 1px solid var(--glass-border); background: transparent;
  color: var(--muted); cursor: pointer; transition: all .15s;
}
.cd-dl-tab.active, .cd-dl-tab:hover {
  background: color-mix(in srgb, var(--pl) 25%, transparent); border-color: color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
}
.cd-dl-files {
  padding: 10px 14px; max-height: 280px; overflow-y: auto;
}
.cd-dl-empty { font-size: 13px; color: var(--muted); padding: 8px 0; }
.cd-dl-type-section { margin-bottom: 10px; }
.cd-dl-type-head {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--pl); margin-bottom: 4px;
}
.cd-dl-row {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 6px 8px; border-radius: 6px; cursor: pointer;
  transition: background .12s;
}
.cd-dl-row:hover { background: var(--glass-highlight); }
.cd-dl-row input[type=checkbox] { accent-color: var(--pl); flex-shrink: 0; }
.cd-dl-name { font-size: 13px; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cd-dl-ver { font-size: 11px; color: var(--muted); flex-shrink: 0; }
.cd-dl-size { font-size: var(--fs-sm, 12px); color: var(--muted); flex-shrink: 0; }
.cd-dl-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-top: 1px solid var(--glass-border);
}
.cd-dl-count { font-size: var(--fs-sm, 12px); color: var(--muted); }
.cd-dl-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 16px; border-radius: var(--radius-sm, 8px); font-size: 13px; font-weight: 600;
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); cursor: pointer;
  transition: all .15s; box-shadow: 0 0 12px var(--pglow2);
}
.cd-dl-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }
.cd-dl-btn:disabled { opacity: .45; cursor: not-allowed; }

/* ── Play button in cover overlay ──────────────────────────────────────────── */
.cov-btn--play {
  background: rgba(34, 197, 94, .55) !important;
  border-color: rgba(74, 222, 128, .7) !important;
}
.cov-btn--play:hover { background: rgba(34, 197, 94, .9) !important; }

/* ── Emulator player ────────────────────────────────────────────────────────── */
.cd-player-wrap {
  position: fixed; z-index: 9000; background: #000;
}
.cd-player--full  { inset: 0; }
.cd-player--window {
  top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: min(90vw, 1200px); height: min(85vh, 800px);
  border-radius: 10px; overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.8);
}
.cd-player-frame { width: 100%; height: 100%; border: none; display: block; }
.cd-player-close {
  position: absolute; top: 10px; right: 12px; z-index: 10;
  background: rgba(0,0,0,.6); border: 1px solid rgba(255,255,255,.2);
  color: #fff; border-radius: 6px; width: 30px; height: 30px;
  cursor: pointer; font-size: var(--fs-lg, 16px); line-height: 1;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.cd-player-close:hover { background: rgba(239,68,68,.7); }

/* ── Play mode dialog (identical to Modern/Emulation theme) ─────────────────── */
.gd-play-dialog-backdrop {
  position: fixed; inset: 0; z-index: 9100;
  background: rgba(0,0,0,.72); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.gd-play-dialog {
  background: #18182a; border: 1px solid #2e2e4a;
  border-radius: 16px; padding: 28px 28px 24px;
  width: min(92vw, 500px); display: flex; flex-direction: column; gap: 18px;
}
.gd-play-dialog-title { font-size: 17px; font-weight: 700; color: #e2e2f0; }
.gd-play-dialog-sub   { font-size: 13px; color: #6b6b8a; margin-top: -12px; }
.gd-play-mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.gd-play-mode-grid--3 { grid-template-columns: 1fr 1fr 1fr; }
.gd-play-mode-card {
  display: flex; flex-direction: column; align-items: center; gap: var(--space-2, 8px);
  padding: 18px 12px; border-radius: 10px;
  border: 1px solid #2a2a40; background: #12121e;
  cursor: pointer; transition: all .15s; color: #6b6b8a;
}
.gd-play-mode-card:hover { border-color: rgba(167,139,250,.4); color: #c4b5fd; }
.gd-play-mode-card.selected {
  border-color: rgba(34,197,94,.5); background: rgba(34,197,94,.08); color: #4ade80;
}
.gd-play-mode-name { font-size: 13px; font-weight: 700; }
.gd-play-mode-desc { font-size: 11px; opacity: .6; text-align: center; }
.gd-play-bezel-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: #12121e;
  border: 1px solid #2a2a40; border-radius: var(--radius-sm, 8px);
}
.gd-play-bezel-info { display: flex; flex-direction: column; gap: 2px; }
.gd-play-bezel-label { font-size: 13px; font-weight: 600; color: #c4b5fd; }
.gd-play-bezel-desc  { font-size: 11px; color: #5a5a7a; }
.gd-play-bezel-toggle {
  position: relative; width: 42px; height: 24px; border-radius: var(--radius, 12px);
  border: none; cursor: pointer; padding: 0; flex-shrink: 0;
  background: #2a2a40; transition: background .2s;
}
.gd-play-bezel-toggle.on { background: rgba(167,139,250,.55); }
.gd-play-bezel-knob {
  position: absolute; top: 4px; left: 4px;
  width: 16px; height: 16px; border-radius: 50%;
  background: #5a5a7a; transition: left .2s, background .2s;
  display: block;
}
.gd-play-bezel-toggle.on .gd-play-bezel-knob { left: 22px; background: var(--pl-light); }

.gd-play-remember {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-sm, 12px); color: #6b6b8a; cursor: pointer;
}
.gd-play-remember input { accent-color: var(--pl); cursor: pointer; }
.gd-play-dialog-actions { display: flex; gap: 10px; justify-content: flex-end; }
.gd-play-cancel {
  padding: 9px 18px; border-radius: var(--radius-sm, 8px); font-size: 13px;
  border: 1px solid #2a2a40; background: transparent;
  color: #6b6b8a; cursor: pointer; transition: all .15s; font-family: inherit;
}
.gd-play-cancel:hover { border-color: #4a4a6a; color: #9d9db8; }
.gd-play-confirm {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 22px; border-radius: var(--radius-sm, 8px); font-size: 13px; font-weight: 700;
  border: none; background: linear-gradient(135deg, #22c55e, #16a34a);
  color: #fff; cursor: pointer; transition: all .15s; font-family: inherit;
}
.gd-play-confirm:hover { background: linear-gradient(135deg, #4ade80, #22c55e); }

</style>
