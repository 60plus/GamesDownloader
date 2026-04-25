<template>
  <div class="gd-root">

    <!-- ── Skeleton ────────────────────────────────────────────────────────── -->
    <template v-if="loading">
      <div class="sk-hero" />
      <div class="sk-body">
        <div class="sk-line sk-line--xl" /><div class="sk-line sk-line--md" />
        <div class="sk-line sk-line--sm" /><div class="sk-line sk-line--lg" />
      </div>
    </template>

    <!-- ── Not found ───────────────────────────────────────────────────────── -->
    <div v-else-if="!rom" class="gd-empty">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.18">
        <rect x="2" y="6" width="20" height="14" rx="2"/><circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
      </svg>
      <p>{{ t('detail.rom_not_found') }}</p>
      <button class="gd-back-pill" @click="router.back()">← {{ t('common.back') }}</button>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN                                                                    -->
    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- ── HERO ──────────────────────────────────────────────────────────── -->
      <div class="gd-hero">
        <HeroBackground
          :src="bgSrc"
          :anim-style="themeStore.heroAnimStyle"
          :anim-enabled="themeStore.heroAnim && themeStore.animations"
        />

        <button class="gd-back-pill" @click="router.push({ name: 'emulation-library', params: { platform: rom.platform_slug } })">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          <img
            :src="`/platforms/names/${rom.platform_fs_slug}.svg`"
            class="gd-pill-name-logo"
            @error="backPillLogoFailed = true"
            v-show="!backPillLogoFailed"
          />
          <span v-if="backPillLogoFailed">{{ rom.platform_name }}</span>
        </button>

        <div class="gd-hero-inner">
          <!-- Cover with 3D tilt + action buttons below -->
          <div class="gd-cover-col">
            <div
              class="gd-cover-frame"
              :style="{ transform: coverTilt, aspectRatio: coverAspect }"
              @mousemove="onCoverMove"
              @mouseleave="onCoverLeave"
              @mouseenter="onCoverEnter"
            >
              <img
                v-if="!coverFailed && rom.cover_path"
                :src="rom.cover_path"
                :alt="rom.name"
                class="gd-cover-img"
                @error="coverFailed = true"
              />
              <div v-else class="gd-cover-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
                  <rect x="2" y="6" width="20" height="14" rx="2"/><circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
                </svg>
              </div>
              <div class="gd-cover-sheen" :style="sheenStyle" />
            </div>

            <!-- Action buttons below the cover -->
            <div class="gd-cover-actions">
              <button v-if="ejsCore" class="gd-btn-play gd-btn-play--cover" @click="requestPlay">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                  <polygon points="5,3 19,12 5,21"/>
                </svg>
                {{ t('detail.play') }}
              </button>
              <button class="gd-btn-dl gd-btn-dl--cover" @click="downloadRom">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {{ t('detail.download_rom') }}
              </button>
            </div>
          </div>

          <!-- Info column -->
          <div class="gd-info-col">

            <!-- Platform logo / name -->
<!-- Wheel logo or plain title -->
            <img
              v-if="rom.wheel_path && !wheelFailed"
              :src="rom.wheel_path"
              :alt="rom.name"
              class="gd-wheel-logo"
              @error="wheelFailed = true"
            />
            <h1 v-if="!rom.wheel_path || wheelFailed" class="gd-title">{{ rom.name }}</h1>

            <!-- Developer / Publisher / Year -->
            <div class="gd-meta-row">
              <span v-if="rom.developer" class="gd-meta-item">
                <img v-if="rom.developer_ss_id && !devLogoFailed"
                  :src="`https://screenscraper.fr/image.php?companyid=${rom.developer_ss_id}&media=logo-monochrome&maxwidth=110`"
                  class="gd-meta-company-logo" :title="rom.developer" @error="devLogoFailed = true"
                />
                <span v-if="!rom.developer_ss_id || devLogoFailed">{{ rom.developer }}</span>
              </span>
              <span v-if="rom.publisher && rom.publisher !== rom.developer" class="gd-meta-sep">·</span>
              <span v-if="rom.publisher && rom.publisher !== rom.developer" class="gd-meta-item">
                <img v-if="rom.publisher_ss_id && !pubLogoFailed"
                  :src="`https://screenscraper.fr/image.php?companyid=${rom.publisher_ss_id}&media=logo-monochrome&maxwidth=110`"
                  class="gd-meta-company-logo" :title="rom.publisher" @error="pubLogoFailed = true"
                />
                <span v-if="!rom.publisher_ss_id || pubLogoFailed">{{ rom.publisher }}</span>
              </span>
              <span v-if="rom.release_year" class="gd-meta-sep">·</span>
              <span v-if="rom.release_year" class="gd-meta-item">{{ rom.release_year }}</span>
            </div>

            <!-- Rating stars (SS score 0–20, map to 0–5 stars) -->
            <div v-if="rom.ss_score != null" class="gd-rating-row">
              <svg v-for="i in 5" :key="i" width="16" height="16" viewBox="0 0 24 24"
                :fill="i <= Math.round(rom.ss_score / 4) ? '#f59e0b' : 'rgba(255,255,255,.12)'"
                :stroke="i <= Math.round(rom.ss_score / 4) ? '#f59e0b' : 'rgba(255,255,255,.2)'"
                stroke-width="1"
              >
                <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
              </svg>
              <span class="gd-rating-num">{{ rom.ss_score }}<span style="font-size:11px;opacity:.5">/20</span></span>
            </div>

            <!-- External ratings (IGDB, LaunchBox, plugins) -->
            <div v-if="rom.igdb_rating != null || rom.lb_rating != null || Object.keys(rom.plugin_ratings || {}).length" class="gd-ext-ratings">
              <div v-if="rom.igdb_rating != null" class="gd-ext-score">
                <img src="/icons/igdb.ico" class="gd-ext-ico" width="42" height="42" alt="IGDB" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ Math.round(rom.igdb_rating) }}<span class="gd-ext-max">/100</span></span>
                  <span class="gd-ext-lbl">IGDB</span>
                </div>
              </div>
              <div v-if="rom.lb_rating != null" class="gd-ext-score">
                <img src="/icons/launchbox.ico" class="gd-ext-ico" width="42" height="42" alt="LaunchBox" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ rom.lb_rating.toFixed(1) }}<span class="gd-ext-max">/10</span></span>
                  <span class="gd-ext-lbl">LB</span>
                </div>
              </div>
              <div v-for="(pr, pid) in (rom.plugin_ratings || {})" :key="pid" class="gd-ext-score">
                <img :src="pr.logo_url" class="gd-ext-ico" width="42" height="42" :alt="pr.name" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ pr.rating.toFixed(1) }}<span class="gd-ext-max">/10</span></span>
                  <span class="gd-ext-lbl">{{ pr.name }}</span>
                </div>
              </div>
            </div>

            <!-- Genre chips -->
            <div v-if="rom.genres?.length" class="gd-tag-row">
              <span v-for="g in (rom.genres || []).slice(0, 5)" :key="g" class="gd-genre-tag">{{ g }}</span>
              <span v-if="rom.player_count" class="gd-genre-tag gd-tag--players">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                  <circle cx="12" cy="7" r="4"/>
                  <path d="M5.5 21a6.5 6.5 0 0 1 13 0H5.5z"/>
                </svg>
                {{ rom.player_count }}
              </span>
            </div>

            <!-- Region + language chips -->
            <div v-if="rom.regions?.length || rom.languages?.length" class="gd-tag-row" style="margin-top:-4px">
              <span v-for="r in (rom.regions || []).slice(0, 3)" :key="r" class="gd-region-tag">{{ r.toUpperCase() }}</span>
              <span v-for="l in (rom.languages || []).slice(0, 4)" :key="l" class="gd-region-tag gd-tag--lang">{{ l }}</span>
            </div>

            <!-- Actions (edit controls only - Play/Download are under the cover) -->
            <div class="gd-actions">
              <button v-if="canEdit" class="gd-btn-ghost" @click="showEditPanel = true" :title="t('detail.edit_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t('detail.edit_metadata') }}
              </button>

              <button v-if="canEdit" class="gd-btn-ghost" :disabled="scraping" @click="triggerScrape" :title="t('detail.scrape')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ spin: scraping }">
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                {{ scraping ? t('detail.scraping') : t('detail.scrape') }}
              </button>

              <button v-if="canEdit" class="gd-btn-danger" :disabled="clearing" @click="onClearMetadata" :title="t('detail.clear_metadata')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                  <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
                </svg>
                {{ clearing ? t('detail.clearing') : t('detail.clear') }}
              </button>
            </div>

            <!-- File info row -->
            <div class="gd-file-info-row">
              <span class="gd-file-name">{{ rom.fs_name }}</span>
              <span class="gd-file-size">{{ formatSize(rom.fs_size_bytes) }}</span>
            </div>

          </div>
        </div>
      </div>

      <!-- ── Hero/body separator ───────────────────────────────────────────── -->
      <div class="gd-separator" />

      <!-- ── BODY ──────────────────────────────────────────────────────────── -->
      <div class="gd-body">

        <!-- Media carousel (video first, then screenshots) -->
        <div v-if="carouselSlides.length" class="gd-media-section">
          <div class="gd-section-label">{{ rom.video_path ? t('detail.media') : t('detail.screenshots') }}</div>
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
                  <img :src="slide.src" :alt="t('detail.trailer')" loading="lazy" />
                  <div class="gd-slide-play">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="white"><polygon points="5,3 19,12 5,21"/></svg>
                  </div>
                  <div class="gd-slide-badge">▶ {{ t('detail.trailer') }}</div>
                </template>
                <img v-else :src="slide.src" :alt="`${t('detail.screenshots')} ${idx}`" loading="lazy" />
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

        <!-- Two-column: Description + Details -->
        <div class="gd-cols">

          <!-- Left: Description + Achievements -->
          <div class="gd-col-left">
            <div v-if="rom.summary">
              <div class="gd-section-label">{{ t('detail.about') }}</div>
              <div class="gd-desc-wrap" :class="{ 'gd-desc--collapsed': !descExpanded && descOverflow }">
                <p class="gd-desc-text">{{ rom.summary }}</p>
              </div>
              <button v-if="descOverflow" class="gd-readmore" @click="descExpanded = !descExpanded">
                {{ descExpanded ? t('detail.read_less') : t('detail.read_more') }}
              </button>
            </div>

          </div>

          <!-- Right: Details -->
          <div class="gd-col-right">
            <div class="gd-section-label">{{ t('detail.details') }}</div>
            <div class="gd-dlist">
              <template v-if="rom.developer">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></span>
                <span class="gd-dk">{{ t('detail.developer') }}</span>
                <span class="gd-dv">{{ rom.developer }}</span>
              </template>
              <template v-if="rom.publisher && rom.publisher !== rom.developer">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg></span>
                <span class="gd-dk">{{ t('detail.publisher') }}</span>
                <span class="gd-dv">{{ rom.publisher }}</span>
              </template>
              <template v-if="rom.release_year">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg></span>
                <span class="gd-dk">{{ t('detail.released') }}</span>
                <span class="gd-dv">{{ rom.release_year }}</span>
              </template>
              <template v-if="rom.genres?.length">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg></span>
                <span class="gd-dk">{{ t('detail.genres') }}</span>
                <div class="gd-dv gd-tag-inline"><span v-for="g in rom.genres" :key="g" class="gd-itag">{{ g }}</span></div>
              </template>
              <template v-if="rom.franchises?.length">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg></span>
                <span class="gd-dk">{{ t('detail.franchise') }}</span>
                <span class="gd-dv">{{ (rom.franchises || []).join(', ') }}</span>
              </template>
              <template v-if="rom.regions?.length">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>
                <span class="gd-dk">{{ t('detail.regions') }}</span>
                <span class="gd-dv">{{ (rom.regions || []).join(', ') }}</span>
              </template>
              <template v-if="rom.languages?.length">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>
                <span class="gd-dk">{{ t('detail.languages') }}</span>
                <span class="gd-dv">{{ (rom.languages || []).join(', ') }}</span>
              </template>
              <template v-if="rom.player_count">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="12" cy="7" r="4"/><path d="M5.5 21a6.5 6.5 0 0 1 13 0H5.5z"/></svg></span>
                <span class="gd-dk">{{ t('detail.players') }}</span>
                <span class="gd-dv">{{ rom.player_count }}</span>
              </template>
              <template v-if="rom.hltb_main_s || rom.hltb_complete_s">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></span>
                <span class="gd-dk">{{ t('detail.time_to_beat') }}</span>
                <span class="gd-dv" style="display:flex;flex-direction:column;gap:1px">
                  <span v-if="rom.hltb_main_s">{{ t('detail.hltb_main') }} {{ fmtHltb(rom.hltb_main_s) }}</span>
                  <span v-if="rom.hltb_complete_s">{{ t('detail.hltb_complete') }} {{ fmtHltb(rom.hltb_complete_s) }}</span>
                </span>
              </template>
              <template v-if="rom.ss_score != null">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="1"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg></span>
                <span class="gd-dk">{{ t('detail.ss_score') }}</span>
                <span class="gd-dv">{{ rom.ss_score }}<span style="font-size:11px;opacity:.45">/20</span></span>
              </template>
              <template v-if="rom.alternative_names?.length">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg></span>
                <span class="gd-dk">{{ t('detail.also_known_as') }}</span>
                <span class="gd-dv" style="font-size: var(--fs-sm, 12px);opacity:.7">{{ (rom.alternative_names || []).slice(0,3).join(' · ') }}</span>
              </template>
              <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>
              <span class="gd-dk">{{ t('detail.format') }}</span>
              <span class="gd-dv gd-mono">{{ rom.fs_extension.toUpperCase() }}</span>
              <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg></span>
              <span class="gd-dk">{{ t('detail.file_size') }}</span>
              <span class="gd-dv gd-mono">{{ formatSize(rom.fs_size_bytes) }}</span>
              <template v-if="rom.platform_name">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="13" rx="5"/><path d="M7 12.5h2m-1-1v2M15.5 12.5h2"/><path d="M7 7l1.5-3h7L17 7"/></svg></span>
                <span class="gd-dk">{{ t('library.platform_label') }}</span>
                <span class="gd-dv">{{ rom.platform_name }}</span>
              </template>
            </div>
          </div>

        </div>
      </div>

    </template>

    <!-- ── Lightbox ─────────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="lightboxIdx !== null && rom" class="gd-lb" @click.self="lightboxIdx = null">
        <button class="gd-lb-close" @click="lightboxIdx = null">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <button v-if="lightboxIdx > 0" class="gd-lb-arrow gd-lb-arrow--l" @click="lightboxIdx--">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <img :src="(rom.screenshots || [])[lightboxIdx]" class="gd-lb-img" />
        <button v-if="lightboxIdx < (rom.screenshots || []).length - 1" class="gd-lb-arrow gd-lb-arrow--r" @click="lightboxIdx++">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="gd-lb-counter">{{ lightboxIdx + 1 }} / {{ (rom.screenshots || []).length }}</div>
      </div>
    </Teleport>

    <!-- ── Video modal ──────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="videoModalOpen && rom?.video_path" class="gd-lb" @click.self="videoModalOpen = false">
        <button class="gd-lb-close" @click="videoModalOpen = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <video :src="rom.video_path" controls autoplay class="gd-lb-img" style="max-height:80vh;max-width:90vw;border-radius:8px" />
      </div>
    </Teleport>

    <!-- ── Edit Metadata Panel ──────────────────────────────────────────────── -->
    <Teleport to="body">
      <EmulationRomMetadataPanel
        v-if="showEditPanel && rom"
        :rom="rom"
        @close="showEditPanel = false"
        @saved="onMetadataSaved"
      />
    </Teleport>

    <!-- ── Play mode dialog ───────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showPlayerDialog" class="gd-play-dialog-backdrop" @click.self="showPlayerDialog = false">
        <div class="gd-play-dialog">
          <div class="gd-play-dialog-title">{{ t('detail.choose_display') }}</div>
          <div class="gd-play-dialog-sub">{{ t('detail.choose_display_sub') }}</div>

          <div class="gd-play-mode-grid gd-play-mode-grid--3">
            <!-- Fullscreen option -->
            <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'full' }" @click="pendingMode = 'full'">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
              </svg>
              <span class="gd-play-mode-name">{{ t('detail.mode_fullscreen') }}</span>
              <span class="gd-play-mode-desc">{{ t('detail.mode_fullscreen_desc') }}</span>
            </button>

            <!-- Windowed option -->
            <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'window' }" @click="pendingMode = 'window'">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <line x1="3" y1="9" x2="21" y2="9"/>
                <circle cx="7" cy="6" r="1" fill="currentColor"/>
                <circle cx="10" cy="6" r="1" fill="currentColor"/>
              </svg>
              <span class="gd-play-mode-name">{{ t('detail.mode_window') }}</span>
              <span class="gd-play-mode-desc">{{ t('detail.mode_window_desc') }}</span>
            </button>

            <!-- New Tab option -->
            <button class="gd-play-mode-card" :class="{ selected: pendingMode === 'tab' }" @click="pendingMode = 'tab'">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="5" width="20" height="16" rx="2"/>
                <line x1="2" y1="10" x2="22" y2="10"/>
                <line x1="7" y1="5" x2="7" y2="10"/>
                <line x1="13" y1="5" x2="13" y2="10"/>
              </svg>
              <span class="gd-play-mode-name">{{ t('detail.mode_tab') }}</span>
              <span class="gd-play-mode-desc">{{ t('detail.mode_tab_desc') }}</span>
            </button>
          </div>

          <!-- Bezel toggle - only shown when this game has a bezel -->
          <div v-if="rom?.bezel_path" class="gd-play-bezel-row">
            <div class="gd-play-bezel-info">
              <span class="gd-play-bezel-label">{{ t('detail.bezel') }}</span>
              <span class="gd-play-bezel-desc">{{ t('detail.bezel_desc') }}</span>
            </div>
            <button
              class="gd-play-bezel-toggle"
              :class="{ on: bezelEnabled }"
              @click="bezelEnabled = !bezelEnabled"
              :title="bezelEnabled ? t('common.disable') + ' ' + t('detail.bezel').toLowerCase() : t('common.enable') + ' ' + t('detail.bezel').toLowerCase()"
            >
              <span class="gd-play-bezel-knob" />
            </button>
          </div>

          <label class="gd-play-remember">
            <input type="checkbox" v-model="rememberMode" />
            <span>{{ t('detail.remember_choice') }}</span>
          </label>

          <div class="gd-play-hint">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01" stroke-linecap="round"/></svg>
            {{ t('detail.start_select_hint') }}
          </div>

          <div class="gd-play-dialog-actions">
            <button class="gd-play-cancel" @click="showPlayerDialog = false">{{ t('common.cancel') }}</button>
            <button class="gd-play-confirm" @click="launchPlayer">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <polygon points="5,3 19,12 5,21"/>
              </svg>
              {{ t('detail.play') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Player overlay ─────────────────────────────────────────────────── -->
    <Teleport to="body">
      <!-- Fullscreen overlay -->
      <!-- Windowed overlay (iframe) -->
      <div v-if="playerOpen" class="gd-player-overlay gd-player-overlay--window">
        <div class="gd-player-window">
          <div class="gd-player-window-bar">
            <span class="gd-player-window-title">{{ rom?.name || rom?.fs_name }}</span>
            <button class="gd-player-window-close" @click="closePlayer" :title="t('common.close')">✕</button>
          </div>
          <iframe
            :src="playerUrl"
            class="gd-player-iframe"
            allow="autoplay; fullscreen; gamepad"
            allowfullscreen
            ref="playerIframe"
          />
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import client from '@/services/api/client'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'
import EmulationRomMetadataPanel from './EmulationRomMetadataPanel.vue'
import TranslateButton from '@/components/common/TranslateButton.vue'
import HeroBackground from '@/components/common/HeroBackground.vue'
import { getEjsCore } from '@/utils/ejsCores'

const { gdConfirm } = useDialog()
const { t } = useI18n()

const route      = useRoute()
const router     = useRouter()
const auth       = useAuthStore()
const themeStore = useThemeStore()

const isAdmin  = computed(() => auth.user?.role === 'admin')
const canEdit  = computed(() => ['admin', 'uploader', 'editor'].includes(auth.user?.role as string))

interface RomDetail {
  id: number
  platform_slug: string
  platform_fs_slug: string | null
  platform_name: string
  fs_name: string
  fs_name_no_ext: string | null
  fs_extension: string
  fs_size_bytes: number
  name: string
  slug: string | null
  summary: string | null
  developer: string | null
  developer_ss_id: number | null
  publisher: string | null
  publisher_ss_id: number | null
  release_year: number | null
  genres: string[] | null
  regions: string[] | null
  languages: string[] | null
  tags: string[] | null
  rating: number | null
  ss_score: number | null
  igdb_rating: number | null
  lb_rating: number | null
  plugin_ratings: Record<string, { name: string; rating: number; logo_url: string }> | null
  player_count: string | null
  hltb_main_s:     number | null
  hltb_extra_s:    number | null
  hltb_complete_s: number | null
  alternative_names: string[] | null
  franchises: string[] | null
  cover_path:      string | null
  cover_type:      string | null
  cover_aspect:    string
  background_path: string | null
  screenshots:     string[] | null
  support_path:    string | null
  wheel_path:      string | null
  bezel_path:      string | null
  steamgrid_path:  string | null
  video_path:      string | null
  picto_path:      string | null
  igdb_id:         number | null
  ss_id:           string | null
  launchbox_id:    string | null
}

const rom              = ref<RomDetail | null>(null)
const loading          = ref(true)
const coverFailed      = ref(false)
const backPillLogoFailed = ref(false)
const devLogoFailed    = ref(false)
const pubLogoFailed    = ref(false)
const wheelFailed      = ref(false)
const scraping      = ref(false)
const clearing      = ref(false)
const showEditPanel = ref(false)

// ── Player ────────────────────────────────────────────────────────────────────
const PREF_KEY       = 'gd3_emu_display_mode'
const showPlayerDialog = ref(false)
const pendingMode    = ref<'full' | 'window' | 'tab'>('full')
const rememberMode   = ref(false)
const playerOpen     = ref(false)
const playerMode     = ref<'window'>('window')
const playerIframe   = ref<HTMLIFrameElement | null>(null)

// Bezel toggle - per-game, stored in localStorage
const bezelEnabled   = ref(true)
const bezelKey = (id: number | string) => `gd3_bezel_${id}`

watch(bezelEnabled, (val) => {
  if (rom.value?.id) localStorage.setItem(bezelKey(rom.value.id), val ? '1' : '0')
})

const ejsCore = computed(() =>
  rom.value?.platform_fs_slug ? getEjsCore(rom.value.platform_fs_slug) : null
)

const playerUrl = computed(() => {
  if (!rom.value || !ejsCore.value) return ''
  const p = new URLSearchParams({
    rom_id:   String(rom.value.id),
    rom_name: rom.value.name || rom.value.fs_name_no_ext || String(rom.value.id),
    ejs_core: ejsCore.value,
    platform: rom.value.platform_fs_slug || '',
  })
  if (rom.value.bezel_path && bezelEnabled.value) p.set('bezel_url', rom.value.bezel_path)
  return `/player.html?${p.toString()}`
})

function requestPlay() {
  const saved = localStorage.getItem(PREF_KEY) as 'full' | 'window' | 'tab' | null
  // Load bezel pref for this specific game (default on)
  if (rom.value?.bezel_path && rom.value.id) {
    const bSaved = localStorage.getItem(bezelKey(rom.value.id))
    bezelEnabled.value = bSaved === '1'
  }
  if (saved) {
    // Use saved preference directly, skip dialog
    pendingMode.value = saved
    launchPlayer()
  } else {
    pendingMode.value = 'full'
    rememberMode.value = false
    showPlayerDialog.value = true
  }
}

function launchPlayer() {
  if (rememberMode.value) {
    localStorage.setItem(PREF_KEY, pendingMode.value)
  }
  showPlayerDialog.value = false

  if (pendingMode.value === 'full') {
    // Fullscreen: same-tab navigation (like Couch Mode) - enables COOP/COEP + auto-fullscreen
    const returnTo = window.location.pathname + window.location.search
    window.location.href = playerUrl.value + '&returnTo=' + encodeURIComponent(returnTo) + '&autoFullscreen=1'
    return
  }

  if (pendingMode.value === 'tab') {
    window.open(playerUrl.value, '_blank')
    return
  }

  // Window mode: disable EJS threads (SharedArrayBuffer not available in iframe)
  _savedEjsThreads = localStorage.getItem('gd_ejs_threads')
  localStorage.setItem('gd_ejs_threads', '0')

  playerMode.value = 'window'
  playerOpen.value = true
}

let _savedEjsThreads: string | null = null

function closePlayer() {
  playerOpen.value = false
  // Restore EJS threads setting after window mode
  if (_savedEjsThreads !== null) {
    localStorage.setItem('gd_ejs_threads', _savedEjsThreads)
    _savedEjsThreads = null
  }
}

// Focus iframe when player opens so gamepad events reach EmulatorJS
watch(playerOpen, (val) => {
  if (val) {
    nextTick(() => playerIframe.value?.focus())
  }
})

const lightboxIdx   = ref<number | null>(null)
const videoModalOpen = ref(false)
const carouselEl    = ref<HTMLElement | null>(null)
const carouselIdx   = ref(0)

// ── Carousel slides: video first, then screenshots ───────────────────────────
const carouselSlides = computed(() => {
  const slides: { type: 'image' | 'video'; src: string }[] = []
  if (rom.value?.video_path) {
    // Use first screenshot or cover as video thumbnail
    const thumb = (rom.value.screenshots || [])[0] || rom.value.cover_path || ''
    slides.push({ type: 'video', src: thumb })
  }
  for (const ss of (rom.value?.screenshots || [])) {
    slides.push({ type: 'image', src: ss })
  }
  return slides
})

function onSlideClick(slide: { type: string }, idx: number) {
  if (slide.type === 'video') {
    videoModalOpen.value = true
  } else {
    // Offset lightbox index by video count
    const videoCount = rom.value?.video_path ? 1 : 0
    lightboxIdx.value = idx - videoCount
  }
}
const descExpanded  = ref(false)
const descOverflow  = ref(false)

// ── Background source ─────────────────────────────────────────────────────────
const bgSrc = computed(() => (
  rom.value?.background_path || rom.value?.cover_path || ''
))

// ── Cover aspect ratio (per cover_type first, then platform config) ──────────
const coverAspect = computed(() => {
  if (rom.value?.cover_type === 'box-3D') return '16/9'
  return rom.value?.cover_aspect || '3/4'
})

// ── 3D tilt ────────────────────────────────────────────────────────────────────
const coverTilt  = ref('perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)')
const sheenStyle = ref('')

function onCoverEnter() { /* active on mousemove */ }
function onCoverMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.width / 2, cy = rect.height / 2
  const dx = e.clientX - rect.left - cx, dy = e.clientY - rect.top - cy
  const rotY = (dx / cx) * 10, rotX = -(dy / cy) * 7
  coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
  const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
  const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
  sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
}
function onCoverLeave() {
  coverTilt.value  = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
  sheenStyle.value = 'opacity:0;'
}

// ── Carousel ───────────────────────────────────────────────────────────────────
function slideTo(idx: number) {
  const max = Math.max(0, (rom.value?.screenshots || []).length - 3)
  carouselIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = carouselEl.value
    if (!el) return
    const child = el.children[carouselIdx.value] as HTMLElement
    if (child) el.scrollTo({ left: child.offsetLeft - 2, behavior: 'smooth' })
  })
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchRom() {
  const id = route.params.id
  if (!id || id === 'undefined') return
  loading.value = true
  try {
    const { data } = await client.get(`/roms/${id}`)
    rom.value = data
    descOverflow.value = !!(data.summary && data.summary.length > 400)
  } catch {
    rom.value = null
  } finally {
    loading.value = false
  }
}

function downloadRom() {
  if (!rom.value) return
  window.open(`/api/roms/${rom.value.id}/download`, '_blank')
}

async function triggerScrape() {
  if (!rom.value) return
  const romId = rom.value.id
  scraping.value = true
  try {
    await client.post(`/roms/${romId}/scrape`)
    setTimeout(() => { if (route.params.id) fetchRom() }, 4000)
  } catch { /* ignore */ } finally {
    scraping.value = false
  }
}

async function onMetadataSaved() {
  wheelFailed.value = false
  coverFailed.value = false
  await fetchRom()
  showEditPanel.value = false
}

async function onClearMetadata() {
  if (!rom.value) return
  if (!await gdConfirm(t('detail.clear_scraped'), { danger: true })) return
  clearing.value = true
  try {
    await client.post(`/roms/${rom.value.id}/clear-metadata`)
    await fetchRom()
  } catch { /* ignore */ } finally {
    clearing.value = false
  }
}

function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024)       return `${bytes} B`
  if (bytes < 1024 ** 2)  return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3)  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

// Handle postMessage from player iframe
function onPlayerMessage(e: MessageEvent) {
  if (e.data?.type === 'gd-exit') closePlayer()
  if (e.data?.type === 'gd-game-started') nextTick(() => playerIframe.value?.focus())
}

onMounted(() => {
  window.addEventListener('message', onPlayerMessage)
  fetchRom()
})
onUnmounted(() => {
  window.removeEventListener('message', onPlayerMessage)
})
</script>

<style scoped>
/* ══ ROOT ══════════════════════════════════════════════════════════════════════ */
.gd-root {
  display: flex; flex-direction: column;
  background: transparent; width: 100%; min-height: 100%; overflow-x: hidden;
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
  color: rgba(255,255,255,.85); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.gd-back-pill:hover { background: rgba(0,0,0,.65); border-color: rgba(255,255,255,.35); color: #fff; }
.gd-pill-name-logo { height: 22px; max-width: 130px; width: auto; object-fit: contain; filter: brightness(1.1); display: block; }

/* ══ HERO ══════════════════════════════════════════════════════════════════════ */
.gd-hero {
  position: relative; min-height: 420px;
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
.gd-cover-col { flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; }

/* Action buttons below the cover */
.gd-cover-actions {
  display: flex; flex-direction: column; gap: var(--space-2, 8px);
  width: clamp(200px, 22vw, 300px);
}
.gd-btn-play--cover {
  width: 100%; justify-content: center; font-size: var(--fs-md, 14px); padding: 10px 0;
}
.gd-btn-dl--cover {
  width: 100%; justify-content: center; font-size: 13px; padding: 9px 0;
}
.gd-cover-frame {
  position: relative; width: clamp(200px, 22vw, 300px); aspect-ratio: 3/4;
  border-radius: var(--radius, 12px); overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,.85), 0 0 0 1px rgba(255,255,255,.09);
  transition: transform 0.35s cubic-bezier(.23,1,.32,1), box-shadow 0.35s ease;
  cursor: default;
}
.gd-cover-frame:hover {
  box-shadow: 0 28px 70px rgba(0,0,0,.9), 0 0 0 1px rgba(255,255,255,.15), 0 0 40px var(--pglow2);
}
.gd-cover-img { width: 100%; height: 100%; object-fit: contain; display: block; background: rgba(0,0,0,.15); }
.gd-cover-empty {
  width: 100%; height: 100%; background: rgba(255,255,255,.04);
  display: flex; align-items: center; justify-content: center;
}
.gd-cover-sheen {
  position: absolute; inset: 0; border-radius: inherit;
  pointer-events: none; opacity: 0; transition: opacity 0.3s;
}

/* ══ INFO COL ══════════════════════════════════════════════════════════════════ */
.gd-info-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-3, 12px); }

.gd-platform-row { display: flex; align-items: center; gap: 10px; }

.gd-wheel-logo {
  max-height: clamp(48px, 7vw, 90px);
  max-width: 100%;
  object-fit: contain;
  object-position: left center;
  filter: drop-shadow(0 2px 12px rgba(0,0,0,.7));
}
.gd-title {
  font-size: clamp(24px, 4vw, 42px); font-weight: 900; color: #fff;
  margin: 0; line-height: 1.08; text-shadow: 0 2px 30px rgba(0,0,0,.7); letter-spacing: -.5px;
}

.gd-meta-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  font-size: var(--fs-md, 14px); color: rgba(255,255,255,.58); font-weight: 500;
}
.gd-meta-sep { opacity: .3; }

.gd-rating-row { display: flex; align-items: center; gap: var(--space-1, 4px); }

/* External ratings (IGDB, LB) */
.gd-ext-ratings { display: flex; gap: 10px; flex-wrap: wrap; }
.gd-ext-score {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
}
.gd-ext-ico { flex-shrink: 0; image-rendering: pixelated; border-radius: 6px; }
.gd-ext-info { display: flex; flex-direction: column; gap: 2px; }
.gd-ext-val { font-size: var(--fs-lg, 16px); font-weight: 800; color: #fff; line-height: 1; }
.gd-ext-max { font-size: var(--fs-xs, 10px); color: var(--muted, rgba(255,255,255,.45)); font-weight: 500; }
.gd-ext-lbl { font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted, rgba(255,255,255,.45)); text-transform: uppercase; letter-spacing: .8px; }
.gd-rating-num { font-size: 15px; font-weight: 700; color: #f59e0b; margin-left: 6px; }

.gd-tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.gd-genre-tag {
  padding: 4px 12px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(167,139,250,.16); border: 1px solid rgba(167,139,250,.35); color: #c4b5fd;
}
.gd-tag--players { background: rgba(20,184,166,.14); border-color: rgba(20,184,166,.3); color: #5eead4; display: inline-flex; align-items: center; gap: 5px; }.gd-region-tag {
  padding: 3px 9px; border-radius: 10px; font-size: 11px; font-weight: 700;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); color: rgba(255,255,255,.6);
}
.gd-tag--lang { background: rgba(99,102,241,.14); border-color: rgba(99,102,241,.25); color: #a5b4fc; }

.gd-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }

/* ── Play button ─────────────────────────────────────────────── */
.gd-btn-play {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 26px; border-radius: var(--radius-sm);
  background: linear-gradient(135deg, #22c55e, #16a34a);
  border: none; color: #fff;
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 18px rgba(34,197,94,.35);
}
.gd-btn-play:hover { background: linear-gradient(135deg, #4ade80, #22c55e); transform: translateY(-1px); }

/* ── Play mode dialog ────────────────────────────────────────── */
.gd-play-dialog-backdrop {
  position: fixed; inset: 0; z-index: 2000;
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
  border-color: rgba(34,197,94,.5); background: rgba(34,197,94,.08);
  color: #4ade80;
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
.gd-play-bezel-toggle.on .gd-play-bezel-knob { left: 22px; background: #a78bfa; }

.gd-play-remember {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-sm, 12px); color: #6b6b8a; cursor: pointer;
}
.gd-play-remember input { accent-color: #a78bfa; cursor: pointer; }
.gd-play-hint {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: rgba(255,255,255,.35); margin-top: 4px;
}

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

/* ── Player overlays ─────────────────────────────────────────── */
.gd-player-overlay { position: fixed; inset: 0; z-index: 3000; }

.gd-player-overlay--full { background: #000; }
.gd-player-overlay--full .gd-player-iframe {
  width: 100%; height: 100%; border: none; display: block;
}

.gd-player-overlay--window {
  background: rgba(0,0,0,.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.gd-player-window {
  width: min(96vw, 1200px); height: min(90vh, 760px);
  border-radius: var(--radius, 12px); overflow: hidden;
  border: 1px solid #2e2e4a;
  display: flex; flex-direction: column;
  box-shadow: 0 40px 120px rgba(0,0,0,.8);
}
.gd-player-window-bar {
  display: flex; align-items: center;
  background: #12121e; border-bottom: 1px solid #2e2e4a;
  padding: 0 14px; height: 38px; gap: 10px; flex-shrink: 0;
}
.gd-player-window-title {
  flex: 1; font-size: var(--fs-sm, 12px); font-weight: 600; color: #9d9db8;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gd-player-window-close {
  background: none; border: none; color: #4a4a6a;
  cursor: pointer; font-size: var(--fs-lg, 16px); padding: 0 4px;
  transition: color .15s;
}
.gd-player-window-close:hover { color: #f87171; }
.gd-player-window .gd-player-iframe {
  flex: 1; width: 100%; border: none; display: block;
}

.gd-btn-dl {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 18px var(--pglow2);
}
.gd-btn-dl:hover { background: var(--pl-light); transform: translateY(-1px); }

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
  background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.35);
  color: #f87171; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.gd-btn-danger:not(:disabled):hover { background: rgba(239,68,68,.18); color: #fca5a5; }
.gd-btn-danger:disabled { opacity: .5; cursor: not-allowed; }

.gd-file-info-row {
  display: flex; gap: 10px; align-items: center; margin-top: 2px;
}
.gd-file-name { font-size: 11px; color: rgba(255,255,255,.3); font-family: monospace; }
.gd-file-size { font-size: 11px; color: rgba(255,255,255,.28); }

.spin { animation: gd-spin .8s linear infinite; }
@keyframes gd-spin { to { transform: rotate(360deg); } }

/* ══ SEPARATOR ═════════════════════════════════════════════════════════════════ */
.gd-separator { height: 1px; background: linear-gradient(to right, transparent, rgba(255,255,255,.07) 30%, rgba(255,255,255,.07) 70%, transparent); }

/* ══ BODY ══════════════════════════════════════════════════════════════════════ */
.gd-body {
  flex: 1; max-width: 1140px; width: 100%; margin: 0 auto;
  padding: 40px 44px 70px; display: flex; flex-direction: column; gap: 44px;
}

.gd-section-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px; margin-bottom: 14px;
}

/* ── Media carousel ──────────────────────────────────────────────────────────── */
.gd-media-section {}
.gd-carousel-wrap {
  position: relative; display: flex; align-items: center; gap: var(--space-2, 8px);
}
.gd-carousel {
  display: flex; gap: 10px; overflow: hidden;
  flex: 1; scroll-behavior: smooth;
}
.gd-slide {
  flex-shrink: 0; width: calc((100% - 20px) / 3);
  aspect-ratio: 16/9; border-radius: var(--radius-sm, 8px); overflow: hidden;
  cursor: pointer; border: 2px solid transparent; transition: border-color .15s;
}
.gd-slide:hover { border-color: rgba(255,255,255,.2); }
.gd-slide--active { border-color: var(--pl); }
.gd-slide { position: relative; }
.gd-slide img { width: 100%; height: 100%; object-fit: cover; }
.gd-slide-play {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.35); transition: background .15s;
}
.gd-slide:hover .gd-slide-play { background: rgba(0,0,0,.5); }
.gd-slide-badge {
  position: absolute; bottom: 8px; left: 8px;
  font-size: var(--fs-xs, 10px); font-weight: 600; letter-spacing: .05em;
  background: rgba(0,0,0,.55); color: #fff; border-radius: var(--radius-xs, 4px); padding: 2px 7px;
}
.gd-carr-btn {
  flex-shrink: 0; width: 36px; height: 36px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.15); background: rgba(0,0,0,.45);
  color: rgba(255,255,255,.7); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.gd-carr-btn:not(:disabled):hover { background: rgba(0,0,0,.7); color: #fff; }
.gd-carr-btn:disabled { opacity: .2; cursor: default; }
.gd-dots { display: flex; gap: 5px; margin-top: 10px; justify-content: center; }
.gd-dot-item { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,.2); cursor: pointer; transition: background .15s; }
.gd-dot-item.active { background: color-mix(in srgb, var(--pl) 30%, transparent); }

/* ── Two-column ──────────────────────────────────────────────────────────────── */
.gd-cols { display: grid; grid-template-columns: 1fr 360px; gap: 44px; align-items: start; }
@media (max-width: 860px) { .gd-cols { grid-template-columns: 1fr; } }

.gd-desc-wrap { overflow: hidden; }
.gd-desc--collapsed { max-height: 200px; -webkit-mask-image: linear-gradient(to bottom, black 60%, transparent); mask-image: linear-gradient(to bottom, black 60%, transparent); }
.gd-desc-text { font-size: var(--fs-md, 14px); line-height: 1.75; color: rgba(255,255,255,.65); margin: 0; }
.gd-readmore {
  background: none; border: none; color: var(--pl-light); font-size: var(--fs-sm, 12px); font-weight: 600;
  cursor: pointer; padding: 8px 0; font-family: inherit;
}

.gd-dlist {
  display: grid; grid-template-columns: 38px auto 1fr; gap: 0;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 6px); overflow: hidden;
}
.gd-di {
  display: flex; align-items: center; justify-content: center;
  padding: 10px 0; border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02); color: var(--muted);
}
.gd-dk, .gd-dv { padding: 10px 14px; font-size: 13px; }
.gd-dk {
  color: var(--muted); font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px;
  white-space: nowrap; border-right: 1px solid var(--glass-border);
  border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
}
.gd-dv { color: var(--text); border-bottom: 1px solid var(--glass-border); }
.gd-dlist > .gd-dk:last-of-type { border-bottom: none; }
.gd-dlist > .gd-dk:last-of-type + .gd-dv { border-bottom: none; }
.gd-mono { font-family: monospace; font-size: var(--fs-sm, 12px); }
.gd-company-cell { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }
.gd-company-logo { max-height: 22px; max-width: 100px; object-fit: contain; filter: invert(1) brightness(1.2); opacity: .85; }
.gd-meta-company-logo { max-height: 60px; max-width: 140px; object-fit: contain; filter: invert(1) brightness(1.4); opacity: .75; vertical-align: middle; }
.gd-picto-badge { max-height: 24px; max-width: 80px; object-fit: contain; opacity: .85; vertical-align: middle; margin-left: 6px; }
.gd-tag-inline { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); }
.gd-itag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: rgba(255,255,255,.6);
}

/* ══ LIGHTBOX ══════════════════════════════════════════════════════════════════ */
.gd-lb {
  position: fixed; inset: 0; z-index: 9900;
  background: rgba(0,0,0,.92); display: flex; align-items: center; justify-content: center;
}
.gd-lb-close {
  position: absolute; top: 18px; right: 22px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.15);
  color: rgba(255,255,255,.7); border-radius: 50%; width: 38px; height: 38px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s;
}
.gd-lb-close:hover { background: rgba(255,255,255,.18); color: #fff; }
.gd-lb-arrow {
  position: absolute; top: 50%; transform: translateY(-50%);
  background: rgba(0,0,0,.5); border: 1px solid rgba(255,255,255,.15);
  color: rgba(255,255,255,.8); border-radius: 50%; width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s;
}
.gd-lb-arrow:hover { background: rgba(0,0,0,.8); color: #fff; }
.gd-lb-arrow--l { left: 18px; }
.gd-lb-arrow--r { right: 18px; }
.gd-lb-img { max-width: 90vw; max-height: 85vh; border-radius: var(--radius-sm, 8px); object-fit: contain; }
.gd-lb-counter {
  position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.5);
  background: rgba(0,0,0,.5); padding: 4px 12px; border-radius: 10px;
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .gd-hero-inner { flex-direction: column; align-items: center; gap: var(--space-4, 16px); padding: 24px 16px 20px; }
  .gd-cover-frame { width: clamp(160px, 50vw, 240px); }
  .gd-cover-actions { width: 100%; }
  .gd-info-col { align-items: center; text-align: center; }
  .gd-ext-ratings { justify-content: center; }
  .gd-tag-row { justify-content: center; }
  .gd-actions { justify-content: center; }
  .gd-content { padding: var(--space-4, 16px); }
  .gd-cols { gap: var(--space-5, 20px); }
  .gd-dlist { grid-template-columns: 30px auto 1fr; font-size: var(--fs-sm, 12px); }
}

</style>
