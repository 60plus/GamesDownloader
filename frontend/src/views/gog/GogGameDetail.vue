<template>
  <div class="gd-root">

    <!-- ── Skeleton ──────────────────────────────────────────────────────────── -->
    <template v-if="loading">
      <div class="sk-hero" />
      <div class="sk-body">
        <div class="sk-line sk-line--xl" /><div class="sk-line sk-line--md" />
        <div class="sk-line sk-line--sm" /><div class="sk-line sk-line--lg" />
      </div>
    </template>

    <!-- ── Not found ─────────────────────────────────────────────────────────── -->
    <div v-else-if="!game" class="gd-empty">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.18">
        <rect x="2" y="6" width="20" height="12" rx="2"/>
      </svg>
      <p>{{ t('detail.game_not_found') }}</p>
      <button class="gd-back-pill" @click="router.back()">{{ t('detail.back_to_library') }}</button>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN                                                                  -->
    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- ── HERO ──────────────────────────────────────────────────────────── -->
      <div class="gd-hero">

        <!-- Blurred background with optional cinematic animation -->
        <HeroBackground
          :src="bgSrc"
          :anim-style="themeStore.heroAnimStyle"
          :anim-enabled="themeStore.heroAnim && themeStore.animations"
        />

        <!-- Back button -->
        <button class="gd-back-pill" @click="router.back()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('common.back') }}
        </button>

        <!-- Hero content - centered -->
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
                v-if="!coverFailed && (game.cover_path || game.cover_url)"
                :src="heroCoverSrc"
                :alt="game.title"
                class="gd-cover-img"
                @error="onCoverError"
              />
              <div v-else class="gd-cover-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
                  <rect x="2" y="6" width="20" height="12" rx="2"/>
                </svg>
              </div>
              <!-- Specular sheen that follows the mouse -->
              <div class="gd-cover-sheen" :style="sheenStyle" />
              <div v-if="game.is_downloaded" class="gd-owned-chip">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                OWNED
              </div>
            </div>
          </div>

          <!-- Info -->
          <div class="gd-info-col">

            <!-- Logo image (SteamGridDB transparent logo) or text title -->
            <img
              v-if="game.logo_path || game.logo_url"
              :src="game.logo_path || game.logo_url"
              :alt="game.title"
              class="gd-logo-img"
            />
            <h1 v-else class="gd-title">{{ game.title }}</h1>

            <!-- Developer · Publisher · Year -->
            <div class="gd-byline">
              <span v-if="game.developer">{{ game.developer }}</span>
              <span v-if="game.developer && game.publisher && game.developer !== game.publisher" class="gd-dot">·</span>
              <span v-if="game.publisher && game.publisher !== game.developer">{{ game.publisher }}</span>
              <span v-if="releaseYear" class="gd-dot">·</span>
              <span v-if="releaseYear">{{ releaseYear }}</span>
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
              <img src="/icons/gog.ico" width="32" height="32" alt="GOG" class="gd-rating-ico" />
            </div>

            <!-- External ratings (RAWG / IGDB / Metacritic via Steam) -->
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
            <div v-if="(game.genres || []).length" class="gd-tag-row">
              <span v-for="g in (game.genres || []).slice(0, 5)" :key="g" class="gd-genre-tag">{{ g }}</span>
            </div>

            <!-- OS platform chips (MDI-style, simple) -->
            <div class="gd-os-row">
              <span v-if="game.os_windows" class="gd-os-chip">
                <!-- mdi-microsoft-windows -->
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                </svg>
                Windows
              </span>
              <span v-if="game.os_mac" class="gd-os-chip">
                <!-- mdi-apple -->
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
              <button class="gd-btn-dl" @click="dlOpen = true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M12 2v10m0 0l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.56 21H19.44a2 2 0 0 0 1.94-1.515L22 17"/>
                </svg>
                {{ t('detail.download') }}
              </button>
              <button class="gd-btn-ghost" @click="showMetadataPanel = true" :title="t('detail.edit_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t('detail.edit_metadata') }}
              </button>
              <button class="gd-btn-ghost" :disabled="scraping" @click="onScrapeClick" :title="t('detail.refresh_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ spin: scraping }">
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                {{ scraping ? t('common.loading') : t('detail.refresh_metadata') }}
              </button>
              <button class="gd-btn-danger" :disabled="clearing" @click="onClearMetadataClick" :title="t('detail.clear_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                  <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
                </svg>
                {{ clearing ? t('common.loading') : t('detail.clear_metadata') }}
              </button>
              <!-- Publish / Unpublish / Re-sync Library -->
              <template v-if="isAdmin">
                <!-- When published: show Re-sync + Unpublish -->
                <template v-if="publishedId">
                  <button
                    class="gd-btn-publish"
                    :disabled="publishLoading"
                    @click="() => publishToLibrary()"
                    title="Re-sync files from disk into the Games Library"
                  >
                    <svg v-if="publishLoading" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin">
                      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                    </svg>
                    <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    {{ publishLoading ? t('common.loading') : t('detail.resync_library') }}
                  </button>
                  <button
                    class="gd-btn-unpublish"
                    :disabled="publishLoading"
                    @click="unpublishFromLibrary"
                    title="Remove this game from the Games Library"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                    </svg>
                    Unpublish
                  </button>
                </template>
                <!-- When not published: show Publish button -->
                <button
                  v-else
                  class="gd-btn-publish"
                  :disabled="publishLoading"
                  @click="() => publishToLibrary()"
                  title="Publish this game to the Games Library"
                >
                  <svg v-if="publishLoading" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                  </svg>
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                  </svg>
                  {{ publishLoading ? t('common.loading') : t('detail.publish_to_library') }}
                </button>
                <span v-if="publishMsg" class="gd-publish-msg" :class="{ ok: !publishMsg.includes('fail') && !publishMsg.includes('error') }">
                  {{ publishMsg }}
                </span>
              </template>
            </div>

          </div>
        </div>
      </div><!-- /hero -->

      <!-- ── Hero → body transition separator ──────────────────────────────── -->
      <div class="gd-separator" />

      <!-- ── BODY ───────────────────────────────────────────────────────────── -->
      <div class="gd-body">

        <!-- ── Media: Unified carousel (video first, then screenshots) ────── -->
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
                <!-- Video slide: YouTube thumbnail + play button -->
                <template v-if="slide.type === 'video'">
                  <img :src="slide.src" class="gd-slide-video-thumb" alt="Trailer" loading="lazy"
                    @error="(e) => ((e.target as HTMLImageElement).src = `https://img.youtube.com/vi/${slide.videoId}/hqdefault.jpg`)" />
                  <div class="gd-slide-play">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="white"><polygon points="5,3 19,12 5,21"/></svg>
                  </div>
                  <div class="gd-slide-video-badge">▶ {{ t('detail.trailer') }}</div>
                </template>
                <!-- Screenshot slide -->
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

        <!-- ── Two-column: Summary + Details ─────────────────────────────────── -->
        <div class="gd-cols">

          <!-- Left: Summary -->
          <div class="gd-col-left">
            <div v-if="game.description || game.description_short || game.summary">
              <div class="gd-section-label">{{ t('detail.summary') }}</div>
              <div class="gd-desc-wrap" :class="{ 'gd-desc--collapsed': !descExpanded && descOverflow }">
                <div v-if="game.description" class="gd-desc-html" v-html="sanitizeHtml(game.description)" />
                <p v-else class="gd-desc-plain">{{ game.description_short || game.summary }}</p>
              </div>
              <button v-if="descOverflow" class="gd-readmore" @click="descExpanded = !descExpanded">
                {{ descExpanded ? t('detail.read_less') : t('detail.read_more') }}
              </button>
            </div>
          </div>

          <!-- Right: Details -->
          <div class="gd-col-right">

            <!-- Details grid (includes release, size, languages, dev, pub…) -->
            <div class="gd-section-label">{{ t('detail.details') }}</div>
            <div class="gd-dlist">
              <template v-if="game.release_date">
                <span class="gd-dk">{{ t('detail.released') }}</span>
                <span class="gd-dv">{{ formatDate(game.release_date) }}</span>
              </template>
              <template v-if="downloadSize">
                <span class="gd-dk">{{ t('detail.size') }}</span>
                <span class="gd-dv gd-mono">{{ downloadSize }}</span>
              </template>
              <template v-if="installerLanguages.length">
                <span class="gd-dk">{{ t('detail.languages') }}</span>
                <div class="gd-dv gd-lang-flags">
                  <span v-for="lang in installerLanguages" :key="lang.code" class="gd-lang-flag" :title="lang.name">
                    <span v-if="lang.flag" class="fi" :class="`fi-${lang.flag}`"></span>
                    <span v-else>{{ lang.name }}</span>
                  </span>
                </div>
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
                  <svg v-if="game.is_admin_game" class="gd-owner-crown" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M5 16L3 5l5.5 5L12 4l3.5 6L21 5l-2 11H5zm0 2h14v2H5v-2z"/></svg>
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
                <span class="gd-dk">{{ t('detail.themes') }}</span>
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
              <template v-if="game.version">
                <span class="gd-dk">Version</span>
                <span class="gd-dv gd-mono">{{ game.version }}</span>
              </template>
              <template v-if="installersTotalCount > 0">
                <span class="gd-dk">{{ t('detail.installers') }}</span>
                <div class="gd-dv">
                  <div v-for="group in installersByOs" :key="group.os" class="gd-inst-group">
                    <div class="gd-inst-os">{{ group.os }}</div>
                    <template v-for="(inst, idx) in group.entries" :key="idx">
                      <div v-if="installersExpanded || idx < 2" class="gd-extra-row">
                        <span class="gd-extra-name">{{ inst.name || inst.language }}</span>
                        <span v-if="inst.language" class="gd-extra-type">{{ inst.language }}</span>
                      </div>
                    </template>
                  </div>
                  <button
                    v-if="installersTotalCount > 2"
                    class="gd-extras-toggle"
                    @click.stop="installersExpanded = !installersExpanded"
                  >
                    {{ installersExpanded ? '▲ Show less' : `▼ Show all ${installersTotalCount}` }}
                  </button>
                </div>
              </template>
              <template v-if="(game.extras || []).length">
                <span class="gd-dk">Extras</span>
                <div class="gd-dv">
                  <div v-for="ex in extrasVisible" :key="ex.name" class="gd-extra-row">
                    <span class="gd-extra-name">{{ ex.name }}</span>
                    <span v-if="ex.type" class="gd-extra-type">{{ ex.type }}</span>
                  </div>
                  <button v-if="(game.extras || []).length > 4" class="gd-extras-toggle" @click.stop="extrasExpanded = !extrasExpanded">
                    {{ extrasExpanded ? '▲ Show less' : `▼ Show all ${(game.extras || []).length}` }}
                  </button>
                </div>
              </template>
              <template v-if="game.hltb_main_s || game.hltb_complete_s">
                <span class="gd-dk">Time to Beat</span>
                <span class="gd-dv" style="display:flex;flex-direction:column;gap:1px">
                  <span v-if="game.hltb_main_s">Main: {{ fmtHltb(game.hltb_main_s) }}</span>
                  <span v-if="game.hltb_complete_s">100%: {{ fmtHltb(game.hltb_complete_s) }}</span>
                </span>
              </template>
              <span class="gd-dk">GOG ID</span>
              <span class="gd-dv gd-mono">{{ game.gog_id }}</span>
            </div>

            <!-- ── System Requirements ──────────────────────────────────────── -->
            <template v-if="hasRequirements">
              <div class="gd-section-label" style="margin-top:18px">{{ t('detail.system_requirements') }}</div>
              <div class="gd-reqs-grid">

                <!-- Format A: flat { minimum, recommended } dict (GOG single-OS) -->
                <template v-if="game.requirements?.minimum">
                  <div v-if="filterReqEntries(game.requirements.minimum).length" class="gd-req-card">
                    <div class="gd-req-card-title">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="gd-req-os-icon gd-req-os-icon--win">
                        <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                      </svg>
                      Minimum
                    </div>
                    <div class="gd-dlist">
                      <template v-for="[k, v] in filterReqEntries(game.requirements.minimum)" :key="k">
                        <span class="gd-dk">{{ formatReqKey(k) }}</span><span class="gd-dv">{{ v }}</span>
                      </template>
                    </div>
                  </div>
                </template>

                <!-- Format B: per_os array (GOG native or GOG D-formats) -->
                <template v-else-if="game.requirements?.per_os">
                  <template v-for="(osReq, idx) in game.requirements.per_os" :key="idx">
                    <div v-if="hasPerOsContent(osReq)" class="gd-req-card">
                      <div class="gd-req-card-title">
                        <img v-if="reqOsType(osReq.type || osReq.system || '') === 'linux'"
                          src="/icons/os-linux.svg" width="14" height="14" alt="Linux" class="gd-req-os-icon" />
                        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="gd-req-os-icon"
                          :class="reqOsType(osReq.type || osReq.system || '') === 'mac' ? 'gd-req-os-icon--mac' : 'gd-req-os-icon--win'"
                        >
                          <path v-if="reqOsType(osReq.type || osReq.system || '') === 'mac'"
                            d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                          <path v-else d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                        </svg>
                        {{ (osReq.type || osReq.system || ('Platform ' + (idx + 1))) }}
                      </div>
                      <template v-if="osReq.minimum">
                        <template v-if="Array.isArray(osReq.minimum) && filterReqRequirements(osReq.minimum).length">
                          <div class="gd-req-sub">Minimum</div>
                          <div class="gd-dlist">
                            <template v-for="r in filterReqRequirements(osReq.minimum)" :key="r.id || r.name">
                              <span class="gd-dk">{{ formatReqKey(r.id || r.name) }}</span><span class="gd-dv">{{ r.description || r.value }}</span>
                            </template>
                          </div>
                        </template>
                        <template v-else-if="!Array.isArray(osReq.minimum) && filterReqEntries(osReq.minimum).length">
                          <div class="gd-req-sub">Minimum</div>
                          <div class="gd-dlist">
                            <template v-for="[k, v] in filterReqEntries(osReq.minimum)" :key="k">
                              <span class="gd-dk">{{ formatReqKey(k) }}</span><span class="gd-dv">{{ v }}</span>
                            </template>
                          </div>
                        </template>
                      </template>
                      <template v-if="osReq.requirement_groups">
                        <template v-for="grp in (osReq.requirement_groups as any[])" :key="grp.type">
                          <template v-if="!(grp.type||'').toLowerCase().includes('rec') && filterReqRequirements(grp.requirements || []).length">
                            <div class="gd-dlist">
                              <template v-for="r in filterReqRequirements(grp.requirements)" :key="r.id || r.name">
                                <span class="gd-dk">{{ formatReqKey(r.id || r.name) }}</span><span class="gd-dv">{{ r.description || r.value }}</span>
                              </template>
                            </div>
                          </template>
                        </template>
                      </template>
                    </div>
                  </template>
                </template>

                <!-- Format C: {osName: {minimum, recommended}} - RAWG / Steam -->
                <template v-else>
                  <template v-for="(osReqs, osName) in game.requirements" :key="osName">
                    <div v-if="typeof osReqs === 'object' && hasOsReqContent(osReqs)" class="gd-req-card">
                      <div class="gd-req-card-title">
                        <img v-if="reqOsType(String(osName)) === 'linux'"
                          src="/icons/os-linux.svg" width="14" height="14" alt="Linux" class="gd-req-os-icon" />
                        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="gd-req-os-icon"
                          :class="reqOsType(String(osName)) === 'mac' ? 'gd-req-os-icon--mac' : 'gd-req-os-icon--win'"
                        >
                          <path v-if="reqOsType(String(osName)) === 'mac'"
                            d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                          <path v-else d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                        </svg>
                        {{ osName }}
                      </div>
                      <template v-if="osReqs.minimum && filterReqEntries(osReqs.minimum).length">
                        <div class="gd-req-sub">Minimum</div>
                        <div class="gd-dlist">
                          <template v-for="[k, v] in filterReqEntries(osReqs.minimum)" :key="k">
                            <span class="gd-dk">{{ formatReqKey(k) }}</span><span class="gd-dv">{{ v }}</span>
                          </template>
                        </div>
                      </template>
                    </div>
                  </template>
                </template>

              </div>
            </template>

          </div>

        </div>

      </div><!-- /body -->

    </template>

    <!-- ── Video modal ────────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="videoModalOpen && ytVideos.length > 0" class="gd-video-modal" @click.self="videoModalOpen = false">
        <button class="gd-lb-close" @click="videoModalOpen = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <div class="gd-video-modal-frame">
          <iframe
            :src="`https://www.youtube.com/embed/${ytVideos[0].video_id}?rel=0&modestbranding=1&autoplay=1`"
            frameborder="0"
            allowfullscreen
            allow="autoplay; accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>
      </div>
    </Teleport>

    <!-- ── Lightbox ───────────────────────────────────────────────────────────── -->
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

    <!-- ── Metadata Edit Panel ─────────────────────────────────────────────── -->
    <Teleport to="body">
      <LibraryMetadataPanel
        v-if="game && showMetadataPanel"
        :game="(game as any)"
        api-prefix="/gog/library/games"
        @close="showMetadataPanel = false"
        @saved="onMetadataSaved"
      />
    </Teleport>

    <!-- ── Download Dialog ────────────────────────────────────────────────── -->
    <DownloadDialog
      v-if="game"
      v-model="dlOpen"
      :gog-id="game.gog_id"
      :game-title="game.title"
      @publish-library="onPublishLibrary"
    />

    <!-- ── Scrape confirmation (when external data exists) ──────────────────── -->
    <Teleport to="body">
      <div v-if="showScrapeDialog" class="gd-confirm-overlay" @click.self="showScrapeDialog = false">
        <div class="gd-confirm-box">
          <div class="gd-confirm-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div class="gd-confirm-title">Refresh Metadata</div>
          <div class="gd-confirm-body">
            This game has ratings from external sources (RAWG / IGDB).<br/>
            Do you also want to refresh them, or refresh GOG data only?
          </div>
          <div class="gd-confirm-actions">
            <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="scrapeGame(true)">GOG data only</button>
            <button class="gd-confirm-btn gd-confirm-btn--primary" @click="scrapeGame(false)">Refresh everything</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Clear metadata confirmation ─────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showClearDialog" class="gd-confirm-overlay" @click.self="showClearDialog = false">
        <div class="gd-confirm-box gd-confirm-box--danger">
          <div class="gd-confirm-icon gd-confirm-icon--danger">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
            </svg>
          </div>
          <div class="gd-confirm-title">Clear Metadata?</div>
          <div class="gd-confirm-body">
            This will remove all scraped data for <strong>{{ game?.title }}</strong> - descriptions, covers, ratings, screenshots, system requirements and more.<br/>
            The game will remain in your library. This cannot be undone.
          </div>
          <div class="gd-confirm-actions">
            <button class="gd-confirm-btn gd-confirm-btn--ghost" @click="showClearDialog = false">Cancel</button>
            <button class="gd-confirm-btn gd-confirm-btn--danger" @click="clearMetadata">Clear Metadata</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import client from '@/services/api/client'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import DownloadDialog from '@/components/gog/DownloadDialog.vue'
import { useThemeStore } from '@/stores/theme'
import { useNotifications } from '@/composables/useNotifications'
import { useAuthStore } from '@/stores/auth'
import { sanitizeHtml } from '@/utils/sanitize'
import TranslateButton from '@/components/common/TranslateButton.vue'
import HeroBackground from '@/components/common/HeroBackground.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface Game {
  id: number; gog_id: number; title: string; slug?: string
  cover_url?: string; cover_path?: string
  background_url?: string; background_path?: string; icon_url?: string
  logo_url?: string; logo_path?: string; icon_path?: string
  developer?: string; publisher?: string; release_date?: string
  genres?: string[]; tags?: string[]; rating?: number
  summary?: string; description?: string; description_short?: string
  features?: string[]; screenshots?: string[]
  videos?: { provider: string; video_id: string }[]
  meta_ratings?: { rawg?: number | null; igdb?: number | null; steam?: number | null }
  hltb_main_s?: number | null
  hltb_complete_s?: number | null
  os_windows: boolean; os_mac: boolean; os_linux: boolean
  languages?: Record<string, string>
  installers?: Record<string, { language: string; name: string; total_size: number }[]>
  extras?: { name: string; type: string }[]
  version?: string; is_downloaded: boolean; scraped: boolean; scraped_at?: string
  requirements?: Record<string, any>
  owner_user_id?: number | null
  owner_username?: string | null
  is_admin_game?: boolean
}

const router         = useRouter()
const route          = useRoute()
const themeStore     = useThemeStore()
const { success: notifySuccess, error: notifyError } = useNotifications()

const auth           = useAuthStore()
const isAdmin        = computed(() => auth.user?.role === 'admin')

// ── Publish to Library ─────────────────────────────────────────────────────────
const publishLoading  = ref(false)
const publishedId     = ref<number | null>(null)   // library_game.id when published
const publishMsg      = ref('')
let   _publishPollTimer: ReturnType<typeof setInterval> | null = null

onUnmounted(() => {
  if (_publishPollTimer !== null) { clearInterval(_publishPollTimer); _publishPollTimer = null }
})

/** Called from DownloadDialog when "Add to Games Library" is ON and downloads are queued.
 *  Phase 1: publish immediately (creates library entry).
 *  Phase 2: poll job statuses; when all complete, re-sync to pick up downloaded files. */
async function onPublishLibrary({ gogId: _gogId, jobIds }: { gogId: number; jobIds: number[] }) {
  // Phase 1 - create library entry right away (may have 0 files initially)
  await publishToLibrary(jobIds.length > 0)

  if (!jobIds.length) return

  // Phase 2 - poll until all jobs reach a terminal state, then re-scan to pick up files
  const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
  let failCount = 0
  if (_publishPollTimer !== null) clearInterval(_publishPollTimer)
  _publishPollTimer = setInterval(async () => {
    try {
      const statuses = await Promise.all(
        jobIds.map(id => client.get(`/gog/downloads/${id}`).then(r => r.data.status as string))
      )
      failCount = 0
      if (statuses.every(s => TERMINAL.has(s))) {
        clearInterval(_publishPollTimer!); _publishPollTimer = null
        if (statuses.some(s => s === 'completed')) {
          await publishToLibrary()
        }
      }
    } catch {
      failCount++
      if (failCount >= 5) { clearInterval(_publishPollTimer!); _publishPollTimer = null }
    }
  }, 6000)
}

async function checkPublishStatus(gogGameId: number) {
  try {
    const { data } = await client.get(`/library/games/gog/${gogGameId}`)
    if (data?.id) publishedId.value = data.id
  } catch { /* 404 = not published yet */ }
}

async function publishToLibrary(pendingDownload = false) {
  if (!game.value || publishLoading.value) return
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

async function unpublishFromLibrary() {
  if (!game.value || publishLoading.value) return
  publishLoading.value = true
  publishMsg.value = ''
  try {
    await client.post(`/library/games/unpublish/${game.value.id}`)
    publishedId.value = null
    publishMsg.value = 'Removed from library'
    setTimeout(() => publishMsg.value = '', 4000)
  } catch (e: any) {
    publishMsg.value = e?.response?.data?.detail || 'Unpublish failed'
  } finally {
    publishLoading.value = false
  }
}

const game           = ref<Game | null>(null)
const loading        = ref(true)
const scraping          = ref(false)
const clearing          = ref(false)
const showScrapeDialog  = ref(false)
const showClearDialog   = ref(false)
const coverFailed       = ref(false)
const descExpanded   = ref(false)
const descOverflow   = ref(false)
const carouselIdx    = ref(0)
const carouselEl     = ref<HTMLElement | null>(null)
const lightboxIdx    = ref<number | null>(null)
const videoModalOpen = ref(false)
const showMetadataPanel = ref(false)
const dlOpen            = ref(false)
const extrasExpanded = ref(false)

// External ratings (lazy-fetched after game loads)
const externalRatings = ref<{ rawg?: number; igdb?: number; steam?: number; plugins?: { id: string; name: string; rating: number; logo: string }[] }>({})

// Language code -> { flag country code (ISO 3166-1 alpha-2 lowercase), full name }.
// `flag` is consumed as `<span class="fi" :class="`fi-${flag}`">` so the
// rendered glyph comes from the flag-icons CSS sprite, not a regional-
// indicator emoji (which fails to render on Windows Chrome / Edge).
//
// Includes both ISO 639-1 codes AND GOG-specific non-standard codes:
//   cn=Simplified Chinese, zh=Traditional Chinese, br=Brazilian Portuguese,
//   cz=Czech, jp=Japanese (GOG uses these instead of standard ISO codes)
const LANG_MAP: Record<string, { flag: string; name: string }> = {
  en:       { flag: 'gb', name: 'English' },
  'en-US':  { flag: 'us', name: 'English (US)' },
  pl:       { flag: 'pl', name: 'Polish' },
  de:       { flag: 'de', name: 'German' },
  fr:       { flag: 'fr', name: 'French' },
  es:       { flag: 'es', name: 'Spanish' },
  'es-419': { flag: 'mx', name: 'Spanish (Latin America)' },
  it:       { flag: 'it', name: 'Italian' },
  ru:       { flag: 'ru', name: 'Russian' },
  // Chinese - GOG uses 'cn' for Simplified, 'zh' for Traditional
  cn:       { flag: 'cn', name: 'Chinese (Simplified)' },  // GOG code
  zh:       { flag: 'tw', name: 'Chinese (Traditional)' }, // GOG code
  'zh-Hans':{ flag: 'cn', name: 'Chinese (Simplified)' },  // ISO
  'zh-Hant':{ flag: 'tw', name: 'Chinese (Traditional)' }, // ISO
  jp:       { flag: 'jp', name: 'Japanese' },   // GOG code (ISO: ja)
  ja:       { flag: 'jp', name: 'Japanese' },   // ISO
  ko:       { flag: 'kr', name: 'Korean' },
  pt:       { flag: 'pt', name: 'Portuguese' },
  br:       { flag: 'br', name: 'Portuguese (Brazil)' }, // GOG code (ISO: pt-BR)
  'pt-BR':  { flag: 'br', name: 'Portuguese (Brazil)' }, // ISO
  nl:       { flag: 'nl', name: 'Dutch' },
  cz:       { flag: 'cz', name: 'Czech' },  // GOG code (ISO: cs)
  cs:       { flag: 'cz', name: 'Czech' },  // ISO
  hu:       { flag: 'hu', name: 'Hungarian' },
  ro:       { flag: 'ro', name: 'Romanian' },
  sk:       { flag: 'sk', name: 'Slovak' },
  sv:       { flag: 'se', name: 'Swedish' },
  fi:       { flag: 'fi', name: 'Finnish' },
  da:       { flag: 'dk', name: 'Danish' },
  no:       { flag: 'no', name: 'Norwegian' },
  tr:       { flag: 'tr', name: 'Turkish' },
  uk:       { flag: 'ua', name: 'Ukrainian' },
  ar:       { flag: 'sa', name: 'Arabic' },
  el:       { flag: 'gr', name: 'Greek' },
  he:       { flag: 'il', name: 'Hebrew' },
  th:       { flag: 'th', name: 'Thai' },
}

// ── 3D tilt effect ────────────────────────────────────────────────────────────
const coverTilt  = ref('perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)')
const sheenStyle = ref('')
const tiltActive = ref(false)

function onCoverEnter() {
  tiltActive.value = true
}
function onCoverMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.width / 2
  const cy = rect.height / 2
  const dx = e.clientX - rect.left - cx
  const dy = e.clientY - rect.top - cy
  const rotY =  (dx / cx) * 10   // max ±10°
  const rotX = -(dy / cy) *  7   // max ±7°
  coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
  // Specular sheen - follows mouse position
  const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
  const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
  sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
}
function onCoverLeave() {
  tiltActive.value = false
  coverTilt.value  = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
  sheenStyle.value = 'opacity:0;'
}

// ─────────────────────────────────────────────────────────────────────────────

// ── Game languages ────────────────────────────────────────────────────────────
const installerLanguages = computed(() => {
  // Primary: game.languages - GOG API per-game dict {code: name}
  const langs = game.value?.languages
  if (langs) {
    let keys: string[]
    if (Array.isArray(langs))           keys = langs.map(String)
    else if (typeof langs === 'object') keys = Object.keys(langs)
    else keys = []
    if (keys.length > 0) return keys.map(code => ({
      code,
      flag: LANG_MAP[code]?.flag || '',
      name: LANG_MAP[code]?.name || code,
    }))
  }
  // Fallback: derive unique language codes from installer entries
  const inst = game.value?.installers
  if (!inst) return []
  const codes = new Set<string>()
  for (const os of Object.values(inst)) {
    for (const entry of (os as any[])) {
      const c = (entry.language || '').trim()
      if (c) codes.add(c)
    }
  }
  return [...codes].map(code => ({
    code,
    flag: LANG_MAP[code]?.flag || '',
    name: LANG_MAP[code]?.name || code,
  }))
})

// ── Min requirements summary (CPU / GPU / RAM) ────────────────────────────────
const minReqSummary = computed(() => {
  const req = game.value?.requirements
  if (!req) return []

  // Resolve minimum requirements object from various GOG API storage formats:
  //   Format 1: { minimum: { processor, memory, ... } }  - from GOG API dict response
  //   Format 2: { per_os: [{ type:'windows', minimum:{...}, recommended:{...} }] }
  //   Format 3: { per_os: [{ requirement_groups: [{ type:'minimum', requirements:[{name,description}] }] }] }
  let minObj: Record<string, any> | null = null

  if (req.minimum && typeof req.minimum === 'object') {
    minObj = req.minimum
  } else if (Array.isArray(req.per_os) && req.per_os.length) {
    // Prefer Windows, fall back to first entry
    const osEntry = req.per_os.find((r: any) =>
      (r.type || r.system || r.description || '').toLowerCase().includes('window')
    ) ?? req.per_os[0]

    if (osEntry?.minimum && typeof osEntry.minimum === 'object') {
      // Format 2
      minObj = osEntry.minimum
    } else if (Array.isArray(osEntry?.requirement_groups)) {
      // Format 3 - requirement_groups = [{ type:'minimum', requirements:[{name,description}] }]
      const minGroup = (osEntry.requirement_groups as any[]).find((g: any) =>
        (g.type || '').toLowerCase().includes('min')
      )
      if (minGroup?.requirements) {
        minObj = {}
        for (const r of minGroup.requirements as any[]) {
          const key = (r.name || '').toLowerCase().replace(/\s+/g, '_')
          minObj[key] = r.description || r.value || ''
        }
      }
    }
  }

  if (!minObj) return []

  const KEY_MAP: Record<string, string> = {
    processor: 'CPU', cpu: 'CPU', graphics: 'GPU', gpu: 'GPU',
    memory: 'RAM', ram: 'RAM', os: 'OS', system: 'OS',
    storage: 'Storage', disk: 'Storage', disk_space: 'Storage',
    directx: 'DirectX', directX: 'DirectX', network: 'Network',
  }
  const ORDER = ['os', 'system', 'processor', 'cpu', 'memory', 'ram', 'graphics', 'gpu', 'storage', 'disk', 'disk_space', 'directx', 'directX']
  const result: { key: string; val: string }[] = []
  const seen = new Set<string>()
  for (const k of ORDER) {
    const v = minObj[k]
    if (v) {
      const label = KEY_MAP[k] || k
      if (!seen.has(label)) { seen.add(label); result.push({ key: label, val: String(v) }) }
    }
  }
  return result
})

// ── External ratings (lazy fetch + persist) ────────────────────────────────────
async function fetchExternalRatings(gameId: number, title: string) {
  // If we already have cached ratings from DB, use them immediately
  const cached = game.value?.meta_ratings
  if (cached) {
    const plugins: { id: string; name: string; rating: number; logo: string }[] = []
    for (const [k, v] of Object.entries(cached)) {
      if (k !== 'rawg' && k !== 'igdb' && k !== 'steam' && typeof v === 'number') {
        plugins.push({ id: k, name: k.toUpperCase(), rating: v, logo: `/api/plugins/${k}-metadata/logo` })
      }
    }
    externalRatings.value = {
      rawg:    cached.rawg  ?? undefined,
      igdb:    cached.igdb  ?? undefined,
      steam:   cached.steam ?? undefined,
      plugins: plugins.length ? plugins : undefined,
    }
  }

  try {
    const [rawgRes, igdbRes] = await Promise.allSettled([
      client.get(`/gog/library/games/${gameId}/meta-sources?source=rawg&q=${encodeURIComponent(title)}`),
      client.get(`/gog/library/games/${gameId}/meta-sources?source=igdb&q=${encodeURIComponent(title)}`),
    ])
    const ratings: { rawg?: number; igdb?: number; steam?: number } = {
      // Preserve steam - it comes from the backend scraper, not from live fetch here
      steam: externalRatings.value.steam,
    }
    if (rawgRes.status === 'fulfilled') {
      const candidates = rawgRes.value.data?.candidates || []
      if (candidates[0]?.rating) ratings.rawg = candidates[0].rating
    }
    if (igdbRes.status === 'fulfilled') {
      const candidates = igdbRes.value.data?.candidates || []
      if (candidates[0]?.rating) ratings.igdb = candidates[0].rating
    }
    externalRatings.value = { ...ratings, plugins: externalRatings.value.plugins }

    // Persist to DB so they appear in the library list without re-fetching
    // Preserve existing steam rating - it is written by the backend scraper, not the frontend
    if ((ratings.rawg || ratings.igdb) && game.value) {
      const existing = game.value.meta_ratings
      const newMeta = {
        ...(existing || {}),
        rawg: ratings.rawg ?? null,
        igdb: ratings.igdb ?? null,
      }
      const changed = !existing || existing.rawg !== newMeta.rawg || existing.igdb !== newMeta.igdb
      if (changed) {
        client.patch(`/gog/library/games/${game.value.id}`, { meta_ratings: newMeta }).catch(() => {})
      }
    }

    // Plugin ratings (PPE.pl etc.) - read from DB cache first, fetch if missing
    const cachedPlugins = game.value?.meta_ratings || {}
    const cachedPluginRatings: { id: string; name: string; rating: number; logo: string }[] = []
    for (const [k, v] of Object.entries(cachedPlugins)) {
      if (k !== 'rawg' && k !== 'igdb' && k !== 'steam' && typeof v === 'number') {
        cachedPluginRatings.push({ id: k, name: k.toUpperCase(), rating: v, logo: `/api/plugins/${k}-metadata/logo` })
      }
    }
    if (cachedPluginRatings.length) {
      externalRatings.value = { ...externalRatings.value, plugins: cachedPluginRatings }
    } else {
      // No cached plugin ratings - fetch live and persist
      try {
        const { data: pluginResults } = await client.get(`/plugins/metadata/search?q=${encodeURIComponent(title)}`)
        if (Array.isArray(pluginResults) && pluginResults.length) {
          const newPluginRatings: { id: string; name: string; rating: number; logo: string }[] = []
          for (const pr of pluginResults.slice(0, 3)) {
            try {
              const { data: detail } = await client.get(
                `/plugins/metadata/fetch?provider_id=${encodeURIComponent(pr.provider_id)}&game_id=${encodeURIComponent(pr.provider_game_id)}`
              )
              if (detail?.rating) {
                newPluginRatings.push({
                  id: detail.provider_id,
                  name: (detail.provider_id || 'plugin').toUpperCase(),
                  rating: detail.rating,
                  logo: `/api/plugins/${detail.provider_id}-metadata/logo`,
                })
                break
              }
            } catch { /* skip */ }
          }
          if (newPluginRatings.length) {
            externalRatings.value = { ...externalRatings.value, plugins: newPluginRatings }
            // Persist to DB
            if (game.value) {
              const meta: Record<string, any> = { ...(game.value.meta_ratings || {}) }
              for (const pr of newPluginRatings) meta[pr.id] = pr.rating
              client.patch(`/gog/library/games/${game.value.id}`, { meta_ratings: meta }).catch(() => {})
            }
          }
        }
      } catch { /* plugins unavailable */ }
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  coverFailed.value = false
  try {
    const { data } = await client.get(`/gog/library/games/${Number(route.params.id)}`)
    game.value = data
    descOverflow.value = !!(data.description && data.description.length > 600)
    // Lazy-load external ratings without blocking page render
    fetchExternalRatings(data.id, data.title)
    // Check if this GOG game is already published in the Games library
    if (isAdmin.value) checkPublishStatus(data.id)
  } catch { /* not found */ }
  finally { loading.value = false }
})

const bgSrc = computed(() => {
  const rawCover = game.value?.cover_path
    || (game.value?.cover_url
      ? (!/\.\w{2,5}(\?|$)/.test(game.value.cover_url)
          ? game.value.cover_url + '.jpg'
          : game.value.cover_url)
      : '')
  return game.value?.background_path || game.value?.background_url || rawCover || ''
})

const releaseYear = computed(() => {
  const d = game.value?.release_date || ''
  // Only return 4-digit year portion; guards against stored dicts / garbage
  const m = d.match(/\b(\d{4})\b/)
  return m ? m[1] : ''
})

const extrasCount   = computed(() => (game.value?.extras || []).length)
const extrasVisible = computed(() => {
  const all = game.value?.extras || []
  return extrasExpanded.value ? all : all.slice(0, 4)
})

const heroCoverSrc = computed(() => {
  if (game.value?.cover_path) return game.value.cover_path
  const url = game.value?.cover_url || ''
  // NOTE: _product_card.jpg is deprecated on GOG CDN - use plain .jpg
  if (url && !/\.\w{2,5}(\?|$)/.test(url)) return url + '.jpg'
  return url
})

const ytVideos = computed(() =>
  (game.value?.videos || [])
    .filter(v => v.provider === 'youtube' && v.video_id)
    .slice(0, 1)   // only one video shown
)

// Unified carousel slides: video first (as thumbnail), then screenshots
const carouselSlides = computed(() => {
  const slides: Array<{ type: 'video' | 'image'; src: string; videoId?: string }> = []
  if (ytVideos.value.length > 0) {
    const v = ytVideos.value[0]
    slides.push({
      type: 'video',
      src: `https://img.youtube.com/vi/${v.video_id}/maxresdefault.jpg`,
      videoId: v.video_id,
    })
  }
  for (const ss of (game.value?.screenshots || [])) {
    slides.push({ type: 'image', src: ss })
  }
  return slides
})

const hasMedia = computed(() => carouselSlides.value.length > 0)

const hasRequirements = computed(() => {
  const r = game.value?.requirements
  if (!r) return false
  return Object.keys(r).length > 0
})

function formatReqKey(key: string): string {
  const k = (key || '').toLowerCase().trim()
  const map: Record<string, string> = {
    // OS
    system: 'OS', os: 'OS',
    // CPU
    processor: 'CPU', cpu: 'CPU',
    // RAM
    memory: 'RAM', ram: 'RAM',
    // GPU
    graphics: 'GPU', gpu: 'GPU', video: 'GPU', 'video card': 'GPU',
    // Storage
    storage: 'Storage', disk_space: 'Storage', 'hard drive': 'Storage', 'hard disk': 'Storage',
    // DirectX
    directx: 'DirectX',
    // Network
    network: 'Network', internet: 'Network',
    // Sound
    sound: 'Sound', 'sound card': 'Sound', audio: 'Sound',
    // Notes
    notes: 'Notes', additional_notes: 'Notes', 'additional notes': 'Notes', other: 'Notes',
  }
  return map[k] ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ── Requirements helpers ───────────────────────────────────────────────────────

function reqOsType(name: string): 'win' | 'mac' | 'linux' {
  const n = (name || '').toLowerCase()
  if (n.includes('mac') || n.includes('osx') || n.includes('apple')) return 'mac'
  if (n.includes('linux')) return 'linux'
  return 'win'
}

function parseReqString(s: string): [string, any][] {
  // Parse GOG requirements string format: "Key: Value\nKey2: Value2\n..."
  return s.split('\n')
    .map(l => l.trim())
    .filter(l => l.includes(':'))
    .map(l => {
      const idx = l.indexOf(':')
      return [l.slice(0, idx).trim(), l.slice(idx + 1).trim()] as [string, any]
    })
    .filter(([, v]) => v !== '')
}

const REQ_SHOW_KEYS = new Set(['processor', 'cpu', 'memory', 'ram', 'graphics', 'gpu', 'video'])

function filterReqEntries(obj: any): [string, any][] {
  if (!obj) return []
  if (typeof obj === 'string') {
    return parseReqString(obj).filter(([k]) => REQ_SHOW_KEYS.has(k.toLowerCase()))
  }
  if (Array.isArray(obj)) return []   // arrays handled by filterReqRequirements
  if (typeof obj !== 'object') return []
  return Object.entries(obj).filter(([k, v]) =>
    REQ_SHOW_KEYS.has(k.toLowerCase()) && v != null && v !== ''
  )
}

function filterReqRequirements(reqs: any[]): any[] {
  return (reqs || []).filter((r: any) =>
    REQ_SHOW_KEYS.has(((r.id || r.name || '')).toLowerCase()) && (r.description || r.value)
  )
}

function hasPerOsContent(osReq: any): boolean {
  // Only check minimum - recommended is not displayed
  if (osReq.minimum) {
    if (Array.isArray(osReq.minimum) && filterReqRequirements(osReq.minimum).length) return true
    if (!Array.isArray(osReq.minimum) && filterReqEntries(osReq.minimum).length) return true
  }
  if (osReq.requirement_groups) {
    for (const grp of (osReq.requirement_groups as any[] || [])) {
      if (!(grp.type || '').toLowerCase().includes('rec') && filterReqRequirements(grp.requirements || []).length) return true
    }
  }
  return false
}

function hasOsReqContent(osReqs: any): boolean {
  // Only check minimum - recommended is not displayed
  return !!(osReqs.minimum && filterReqEntries(osReqs.minimum).length)
}
const installersInfo = computed(() => {
  const inst = game.value?.installers
  if (!inst || !Object.keys(inst).length) return ''
  return Object.keys(inst).map(k => k.charAt(0).toUpperCase() + k.slice(1)).join(', ')
})

// Per-OS installer breakdown for the details table
const installersByOs = computed(() => {
  const inst = game.value?.installers
  if (!inst) return []
  return Object.entries(inst).map(([os, entries]) => ({
    os: os.charAt(0).toUpperCase() + os.slice(1),
    entries: entries as { language: string; name: string; total_size: number }[],
  }))
})

const installersExpanded = ref(false)
const installersTotalCount = computed(() =>
  installersByOs.value.reduce((n, g) => n + g.entries.length, 0)
)

// Total download size across all installers
const downloadSize = computed(() => {
  const inst = game.value?.installers
  if (!inst) return null
  let total = 0
  for (const entries of Object.values(inst)) {
    for (const e of (entries as { total_size?: number }[])) {
      total += e.total_size || 0
    }
  }
  if (!total) return null
  if (total >= 1024 * 1024 * 1024) return (total / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  if (total >= 1024 * 1024) return (total / (1024 * 1024)).toFixed(1) + ' MB'
  return (total / 1024).toFixed(0) + ' KB'
})

function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

function formatDate(raw: string): string {
  // Handle ISO strings, date-only strings, and garbage
  const d = new Date(raw)
  if (!isNaN(d.getTime())) {
    const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
    return d.toLocaleDateString(loc, { year: 'numeric', month: 'long', day: 'numeric' })
  }
  // Fallback: show raw if it looks like a date
  return raw.length <= 10 ? raw : raw.slice(0, 10)
}

// sanitizeHtml imported from @/utils/sanitize (DOMPurify-based)

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

// Slide click handler: video → open modal; image → open lightbox
function onSlideClick(slide: { type: 'video' | 'image'; src: string; videoId?: string }, idx: number) {
  if (slide.type === 'video') {
    videoModalOpen.value = true
  } else {
    // Offset by video count to get screenshot index
    const ssOffset = ytVideos.value.length > 0 ? 1 : 0
    openLightbox(idx - ssOffset)
  }
}

function openLightbox(idx: number) { lightboxIdx.value = idx }
function openMetadataPanel() { showMetadataPanel.value = true }

async function onMetadataSaved(updated: Partial<Game>) {
  coverFailed.value = false
  if (game.value) Object.assign(game.value, updated)
  showMetadataPanel.value = false
  // Re-fetch to get latest
  try {
    const { data } = await client.get(`/gog/library/games/${Number(route.params.id)}`)
    game.value = data
  } catch { /* ignore */ }
}

function onCoverError() {
  coverFailed.value = true
}

// ── Scrape flow ───────────────────────────────────────────────────────────────

function onScrapeClick() {
  if (!game.value || scraping.value) return
  // If game has external (RAWG/IGDB) ratings, ask what to do
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
    const params = preserveExternal ? '?preserve_external=true' : ''
    await client.post(`/gog/library/games/${game.value.id}/scrape${params}`)
    let n = 0
    const poll = setInterval(async () => {
      if (++n > 20) { clearInterval(poll); scraping.value = false; return }
      try {
        const { data } = await client.get(`/gog/library/games/${game.value!.id}`)
        if (data.scraped) { clearInterval(poll); scraping.value = false; game.value = data }
      } catch { clearInterval(poll); scraping.value = false }
    }, 1500)
  } catch { scraping.value = false }
}

// ── Clear metadata flow ───────────────────────────────────────────────────────

function onClearMetadataClick() {
  if (!game.value || clearing.value) return
  showClearDialog.value = true
}

async function clearMetadata() {
  if (!game.value || clearing.value) return
  showClearDialog.value = false
  clearing.value = true
  const title = game.value.title
  try {
    await client.delete(`/gog/library/games/${game.value.id}/metadata`)
    const { data } = await client.get(`/gog/library/games/${game.value.id}`)
    game.value = data
    coverFailed.value = false
    externalRatings.value = {}
    notifySuccess(`Metadata cleared for "${title}".`)
  } catch {
    notifyError(`Failed to clear metadata for "${title}".`)
  } finally { clearing.value = false }
}
</script>

<style scoped>
/* ── Root ─────────────────────────────────────────────────────────────────── */
.gd-root {
  display: flex; flex-direction: column;
  background: transparent;   /* let the layout's ambient background show through */
  width: 100%;
  min-height: 100%;
  overflow-x: hidden;
}

/* ── Skeleton ─────────────────────────────────────────────────────────────── */
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

/* ── Empty ────────────────────────────────────────────────────────────────── */
.gd-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 14px; color: var(--muted); font-size: var(--fs-md, 14px);
}

/* ── Back pill ────────────────────────────────────────────────────────────── */
.gd-back-pill {
  position: fixed; top: 130px; left: 20px; z-index: 200;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 14px 7px 10px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(0,0,0,.42);
  backdrop-filter: blur(8px);
  color: rgba(255,255,255,.85);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.gd-back-pill:hover { background: rgba(0,0,0,.65); border-color: rgba(255,255,255,.35); color: #fff; }

/* ══════════════════════════════════════════════════════════════════════════ */
/* HERO                                                                       */
/* ══════════════════════════════════════════════════════════════════════════ */
.gd-hero {
  position: relative;
  min-height: 420px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}

/* Hero background - blur intensity controlled by --gd-hero-blur CSS variable */
/* Hero background + vignette moved to shared <HeroBackground> component. */

/* ── Hero → body separator (configurable fade) ───────────────────────────── */
.gd-separator {
  width: 100%;
  height: var(--gd-hero-fade-h, 80px);
  margin-top: calc(-1 * var(--gd-hero-fade-h, 80px));
  background: linear-gradient(to bottom, transparent, var(--bg1, rgba(8,7,18,1)));
  pointer-events: none;
  flex-shrink: 0;
  position: relative;
  z-index: 0; /* renders after hero in DOM order, overlaps hero bottom naturally */
}

/* Content row - centered */
.gd-hero-inner {
  position: relative; z-index: 2;
  display: flex; align-items: flex-end; gap: var(--space-10, 40px);
  padding: 60px 44px 40px;
  width: 100%;
  max-width: 1140px;
  margin: 0 auto;
}

/* ── Cover ──────────────────────────────────────────────────────────────── */
.gd-cover-col { flex-shrink: 0; }

.gd-cover-frame {
  position: relative;
  width: 360px;
  aspect-ratio: 3/4;
  border-radius: 14px;
  overflow: hidden;
  box-shadow:
    0 20px 60px rgba(0,0,0,.85),
    0  0   0 1px rgba(255,255,255,.09);
  /* transition only for the return-to-flat animation */
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.35s ease;
  transform-style: preserve-3d;
  cursor: default;
}
.gd-cover-frame:hover {
  box-shadow:
    0 28px 70px rgba(0,0,0,.9),
    0  0   0 1px rgba(255,255,255,.15),
    0  0  40px var(--pglow2);
  /* during mousemove: JS overrides transition via will-change; keep transition for leave */
}
.gd-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.gd-cover-empty {
  width: 100%; height: 100%; background: rgba(255,255,255,.04);
  display: flex; align-items: center; justify-content: center;
}

/* Specular sheen layer */
.gd-cover-sheen {
  position: absolute; inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s;
}

.gd-owned-chip {
  position: absolute; top: 8px; right: 8px;
  display: flex; align-items: center; gap: 3px;
  padding: 3px 8px; border-radius: 5px;
  background: rgba(74,222,128,.15); border: 1px solid rgba(74,222,128,.35);
  color: #4ade80; font-size: 9px; font-weight: 700; letter-spacing: .5px;
  z-index: 2;
}

/* ── Info ───────────────────────────────────────────────────────────────── */
.gd-info-col {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; gap: 13px;
}

.gd-title {
  font-size: clamp(26px, 4vw, 46px);
  font-weight: 900; color: #fff; margin: 0;
  line-height: 1.08;
  text-shadow: 0 2px 30px rgba(0,0,0,.7);
  letter-spacing: -.5px;
}

/* SteamGridDB transparent logo as title */
.gd-logo-img {
  max-width: min(460px, 100%);
  max-height: 140px;
  object-fit: contain;
  object-position: left center;
  filter: drop-shadow(0 2px 18px rgba(0,0,0,.75));
}

.gd-byline {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  font-size: var(--fs-md, 14px); color: rgba(255,255,255,.58); font-weight: 500;
}
.gd-dot { opacity: .3; }

.gd-rating-row { display: flex; align-items: center; gap: 3px; }
.gd-rating-num { font-size: 15px; font-weight: 700; color: #f59e0b; margin-left: 6px; }

.gd-tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.gd-genre-tag {
  padding: 4px 12px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(167,139,250,.16); border: 1px solid rgba(167,139,250,.35);
  color: #c4b5fd;
}

.gd-os-row { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }
.gd-os-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14);
  color: rgba(255,255,255,.7); font-size: var(--fs-sm, 12px); font-weight: 600;
  transition: all .15s;
}
.gd-os-chip:hover { background: rgba(255,255,255,.12); color: #fff; }

/* External ratings row */
.gd-ext-ratings { display: flex; gap: 10px; flex-wrap: wrap; }
.gd-ext-score {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
}
.gd-ext-ico { flex-shrink: 0; image-rendering: pixelated; border-radius: 6px; }
.gd-ext-info { display: flex; flex-direction: column; gap: 2px; }
.gd-ext-val {
  font-size: var(--fs-lg, 16px); font-weight: 800; color: #fff; line-height: 1;
}
.gd-ext-max { font-size: var(--fs-xs, 10px); color: var(--muted); font-weight: 500; }
.gd-ext-lbl {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px;
}
/* GOG rating row icon */
.gd-rating-ico {
  image-rendering: pixelated;
  opacity: .85;
  flex-shrink: 0;
  margin-left: 4px;
  align-self: center;
}

.gd-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }

.gd-btn-dl {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 18px var(--pglow2);
}
.gd-btn-dl:not(:disabled):hover { background: var(--pl-light); transform: translateY(-1px); }
.gd-btn-dl:disabled { opacity: .4; cursor: not-allowed; }

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
.gd-publish-msg {
  font-size: 11px; color: #f87171; align-self: center;
}
.gd-publish-msg.ok { color: #4ade80; }

/* ── Confirm dialogs ─────────────────────────────────────────────────────── */
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
  padding: 32px 36px;
  max-width: 440px; width: 90%;
  display: flex; flex-direction: column; gap: 14px;
}
.gd-confirm-box--danger { border-color: rgba(239,68,68,.35); }
.gd-confirm-icon {
  width: 48px; height: 48px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 15%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 30%, transparent);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light);
}
.gd-confirm-icon--danger {
  background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35);
  color: #fca5a5;
}
.gd-confirm-title { font-size: 17px; font-weight: 700; color: var(--text); }
.gd-confirm-body { font-size: 13px; color: var(--muted); line-height: 1.6; }
.gd-confirm-body strong { color: var(--text); }
.gd-confirm-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 6px; }
.gd-confirm-btn {
  padding: 9px 20px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: all .15s;
}
.gd-confirm-btn--ghost {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted);
}
.gd-confirm-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.gd-confirm-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  box-shadow: 0 0 14px var(--pglow2);
}
.gd-confirm-btn--primary:hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; }
.gd-confirm-btn--danger {
  background: rgba(239,68,68,.2); border: 1px solid rgba(239,68,68,.5); color: #fca5a5;
}
.gd-confirm-btn--danger:hover { background: rgba(239,68,68,.35); border-color: rgba(239,68,68,.8); color: #fecaca; }

/* ══════════════════════════════════════════════════════════════════════════ */
/* BODY                                                                       */
/* ══════════════════════════════════════════════════════════════════════════ */
.gd-body {
  flex: 1;
  max-width: 1140px;
  width: 100%;
  margin: 0 auto;
  padding: 40px 44px 70px;
  display: flex; flex-direction: column; gap: 44px;
}

.gd-section-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px;
  margin-bottom: 16px;
}

/* ── Screenshots / Carousel ───────────────────────────────────────────────── */
.gd-media-section {
  display: flex; flex-direction: column; gap: var(--space-6, 24px);
  padding: 0 24px;  /* room for carousel nav arrows */
}

/* ── Unified carousel (video + screenshots, 3-per-view) ──────────────────── */
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
  flex: 0 0 calc((100% - 24px) / 3);  /* always show exactly 3 slides */
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

/* Video slide inner */
.gd-slide-video-thumb {
  width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform .3s ease;
}
.gd-slide:hover .gd-slide-video-thumb { transform: scale(1.04); }

.gd-slide-play {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 54px; height: 54px; border-radius: 50%;
  background: rgba(0,0,0,.65); border: 2.5px solid rgba(255,255,255,.85);
  display: flex; align-items: center; justify-content: center;
  transition: background .2s, transform .2s;
}
.gd-slide:hover .gd-slide-play {
  background: rgba(220,40,40,.85); border-color: #fff;
  transform: translate(-50%, -50%) scale(1.1);
}

.gd-slide-video-badge {
  position: absolute; bottom: 8px; left: 8px;
  padding: 3px 9px; border-radius: var(--radius-xs, 4px);
  background: rgba(0,0,0,.68); backdrop-filter: blur(4px);
  color: rgba(255,255,255,.9);
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .6px;
}

/* Video modal */
.gd-video-modal {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.9); backdrop-filter: blur(10px);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-5, 20px);
}
.gd-video-modal-frame {
  position: relative;
  width: min(1000px, 100%);
  aspect-ratio: 16/9;
  border-radius: var(--radius, 12px);
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.15);
  box-shadow: 0 32px 80px rgba(0,0,0,.8);
}
.gd-video-modal-frame iframe {
  position: absolute; inset: 0; width: 100%; height: 100%; border: none;
}

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
.gd-dot-item.active {
  background: color-mix(in srgb, var(--pl) 30%, transparent); width: 22px; border-radius: 3px;
}

/* ── Two columns ──────────────────────────────────────────────────────────── */
.gd-cols {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 52px;
  align-items: start;
}
@media (max-width: 900px) {
  .gd-cols { grid-template-columns: 1fr; }
}

/* ── Description ──────────────────────────────────────────────────────────── */
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
/* Contain images and media from GOG HTML descriptions */
.gd-desc-html :deep(img) { max-width: 100%; height: auto; border-radius: 6px; display: block; margin: 8px 0; }
.gd-desc-html :deep(video) { max-width: 100%; }
.gd-desc-html :deep(div[class*="embed"]) { display: none; } /* hide embedded promos */
.gd-desc-plain { margin: 0; }

.gd-readmore {
  margin-top: 12px; background: none; border: none;
  color: var(--pl-light); font-size: var(--fs-sm, 12px); font-weight: 600;
  font-family: inherit; cursor: pointer; padding: 0;
  opacity: .85;
}
.gd-readmore:hover { opacity: 1; }

/* ── Details list ─────────────────────────────────────────────────────────── */
.gd-dlist {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
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

/* Language flags - render flag-icons sprite via the inner `<span class="fi fi-XX">` */
.gd-lang-flags { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); align-items: center; }
.gd-lang-flag { display: inline-flex; align-items: center; font-size: 20px; line-height: 1; cursor: default; }
.gd-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }

/* Installer groups */
.gd-inst-group { margin-bottom: 6px; }
.gd-inst-group:last-child { margin-bottom: 0; }
.gd-inst-os {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: .6px; margin-bottom: 2px;
}

/* Extras list */
.gd-extra-row {
  display: flex; align-items: baseline; gap: 6px;
  font-size: var(--fs-sm, 12px); line-height: 1.7;
}
.gd-extra-name { color: var(--text); }
.gd-extra-type {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .5px;
}
.gd-extras-toggle {
  margin-top: 4px; background: none; border: none; padding: 0;
  font-size: 11px; font-weight: 600; font-family: inherit;
  color: var(--pl-light); cursor: pointer; opacity: .8;
}
.gd-extras-toggle:hover { opacity: 1; }

/* Min requirements summary */
.gd-minreq-row {
  display: flex; gap: 6px; align-items: baseline;
  font-size: var(--fs-sm, 12px); line-height: 1.7;
}
.gd-minreq-key {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .5px;
  min-width: 36px; flex-shrink: 0;
}
.gd-minreq-val { color: var(--text); flex: 1; }

/* ── Lightbox ─────────────────────────────────────────────────────────────── */
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

/* ── Spin ─────────────────────────────────────────────────────────────────── */
.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Requirements ─────────────────────────────────────────────────────────── */
.gd-reqs-section { display: flex; flex-direction: column; }
.gd-reqs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-4, 16px);
}
.gd-req-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 18px 20px;
}
.gd-req-card-title {
  font-size: 13px; font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: .7px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--glass-border);
}
.gd-req-sub {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 8px;
}
.gd-req-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 16px;
  margin: 0;
}
.gd-req-dl dt {
  font-size: 11px; font-weight: 700;
  color: var(--muted); white-space: nowrap;
  text-transform: uppercase; letter-spacing: .5px;
}
.gd-req-dl dd {
  margin: 0;
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.75);
  line-height: 1.5;
}
.gd-req-pre {
  margin: 0;
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.65);
  line-height: 1.6;
  white-space: pre-wrap; word-break: break-word;
  font-family: inherit;
}

/* OS icon in requirements card title */
.gd-req-card-title {
  display: flex; align-items: center; gap: 7px;
}
.gd-req-os-icon { flex-shrink: 0; opacity: .9; width: 56px; height: 56px; }
.gd-req-os-icon--win  { color: #60a5fa; }
.gd-req-os-icon--mac  { color: #c4b5fd; }
.gd-req-os-icon--linux { color: #fbbf24; }

/* ── Two-column layout: left / right ─────────────────────────────────────── */
.gd-col-left {
  min-width: 0;
  display: flex; flex-direction: column; gap: var(--space-4, 16px);
}
.gd-col-right {
  display: flex; flex-direction: column; gap: 0;
}

/* ── Quickfacts panel ─────────────────────────────────────────────────────── */
.gd-quickfacts {
  display: flex; flex-direction: column; gap: 0;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.gd-qf-row {
  display: flex; align-items: flex-start; gap: 0;
  border-bottom: 1px solid var(--glass-border);
  padding: 0;
}
.gd-qf-row:last-child { border-bottom: none; }
.gd-qf-label {
  flex-shrink: 0;
  min-width: 84px;
  padding: 10px 14px;
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .6px;
  border-right: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
  white-space: nowrap;
  line-height: 1.5;
}
.gd-qf-val {
  flex: 1; min-width: 0;
  padding: 10px 14px;
  font-size: 13px; color: var(--text);
  line-height: 1.5;
}

/* Platform OS chips inside quickfacts */
.gd-qf-os { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; padding-top: 7px; padding-bottom: 7px; }
.gd-qf-chip {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  padding: 3px 9px; border-radius: var(--radius-xs, 4px); font-size: 11px; font-weight: 600;
  border: 1px solid rgba(255,255,255,.12);
}
.gd-qf-chip--win   { background: rgba(96,165,250,.12);  border-color: rgba(96,165,250,.3);  color: #93c5fd; }
.gd-qf-chip--mac   { background: rgba(196,181,253,.12); border-color: rgba(196,181,253,.3); color: #c4b5fd; }
.gd-qf-chip--linux { background: rgba(251,191,36,.12);  border-color: rgba(251,191,36,.3);  color: #fcd34d; }

/* Separator between quickfacts and details */
.gd-col-sep {
  height: 1px;
  background: var(--glass-border);
  margin: 20px 0;
  border: none;
}

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
