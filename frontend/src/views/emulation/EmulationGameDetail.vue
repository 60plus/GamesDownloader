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
              <!-- Play starts the game the way it was last told to. The caret
                   beside it reopens the question, which is the only way back
                   once "remember my choice" has been ticked, and the only way
                   to reach the bezel toggle that lives in the same dialog. -->
              <div v-if="ejsCore" class="gd-play-split">
                <button class="gd-btn-play gd-btn-play--cover" @click="requestPlay()">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                    <polygon points="5,3 19,12 5,21"/>
                  </svg>
                  {{ t('detail.play') }}
                </button>
                <button
                  class="gd-btn-play gd-btn-play--more"
                  :title="t('detail.choose_display')"
                  :aria-label="t('detail.choose_display')"
                  @click="openDisplayOptions()"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
              </div>
              <button class="gd-btn-dl gd-btn-dl--cover" @click="downloadRom()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {{ t('detail.download_rom') }}
              </button>
              <!-- The booklet from the box. Shown only when a scrape fetched
                   one; the component decides that, and every theme uses it. -->
              <RomManualButton :rom-id="rom?.id" :available="rom?.has_manual" class="gd-manual-cover" />
              <!-- What the game is on disk, listed the way a GOG or custom game
                   lists its files: every disc on its own line, then the extras
                   and mods beside it, which Download offers with the game.
                   Always there to open - this page names the files nowhere else. -->
              <RomFilesList v-if="rom" :game-label="romGameLabel" :game-size="titleBytes"
                            :discs="diskSet" always :rom-id="rom.id" @changed="refreshRom"
                            :extras="rom.extras || []" class="gd-files-cover" />
              <RomDownloadDialog v-if="rom" v-model="showRomDownload" :rom-id="rom.id"
                                 :title="rom.name || rom.fs_name" :game-label="romGameLabel"
                                 :game-size="titleBytes" :whole-set="diskSet.length > 1"
                                 :extras="rom.extras || []" />
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

            <!-- Blended rating stars (every source this ROM carries, 0-5).
                 ScreenScraper's own note keeps its /20 scale in the row below. -->
            <div v-if="rom.rating_agg != null" class="gd-rating-row">
              <svg v-for="i in 5" :key="i" width="16" height="16" viewBox="0 0 24 24"
                :fill="i <= Math.round(ratingVal(rom.rating_agg)) ? '#f59e0b' : 'rgba(255,255,255,.12)'"
                :stroke="i <= Math.round(ratingVal(rom.rating_agg)) ? '#f59e0b' : 'rgba(255,255,255,.2)'"
                stroke-width="1"
              >
                <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
              </svg>
              <span class="gd-rating-num">{{ ratingVal(rom.rating_agg).toFixed(1) }}<span style="font-size:11px;opacity:.5">/5</span></span>
            </div>

            <!-- Per-source scores (ScreenScraper, IGDB, LaunchBox, plugins) -->
            <div v-if="rom.ss_score != null || rom.igdb_rating != null || rom.lb_rating != null || Object.keys(rom.plugin_ratings || {}).length" class="gd-ext-ratings">
              <div v-if="rom.ss_score != null" class="gd-ext-score">
                <img src="/icons/ScreenScraper.ico" class="gd-ext-ico" width="42" height="42" alt="ScreenScraper" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ ratingVal(rom.ss_score).toFixed(1) }}<span class="gd-ext-max">/20</span></span>
                  <span class="gd-ext-lbl">ScreenScraper</span>
                </div>
              </div>
              <div v-if="rom.igdb_rating != null" class="gd-ext-score">
                <img src="/icons/igdb.ico" class="gd-ext-ico" width="42" height="42" alt="IGDB" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ Math.round(ratingVal(rom.igdb_rating)) }}<span class="gd-ext-max">/100</span></span>
                  <span class="gd-ext-lbl">IGDB</span>
                </div>
              </div>
              <div v-if="rom.lb_rating != null" class="gd-ext-score">
                <img src="/icons/launchbox.ico" class="gd-ext-ico" width="42" height="42" alt="LaunchBox" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ ratingVal(rom.lb_rating).toFixed(1) }}<span class="gd-ext-max">/10</span></span>
                  <span class="gd-ext-lbl">LB</span>
                </div>
              </div>
              <!-- The name and the logo are read from what was stored, and an
                   entry saved from the metadata editor used to carry neither:
                   the tile then showed a bare number beside an empty square.
                   The editor fills both in now, and these fall back for rows
                   written before it did. -->
              <div v-for="(pr, pid) in (rom.plugin_ratings || {})" :key="pid" class="gd-ext-score">
                <img v-if="pr.logo_url" :src="pr.logo_url" class="gd-ext-ico" width="42" height="42" :alt="pr.name || String(pid)" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <div class="gd-ext-info">
                  <span class="gd-ext-val">{{ ratingVal(pr.rating).toFixed(1) }}<span class="gd-ext-max">/10</span></span>
                  <span class="gd-ext-lbl">{{ pr.name || String(pid).toUpperCase() }}</span>
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

            <!-- What only an administrator, an uploader or an editor may do,
                 under one "Manage" menu (the owner, 2026-09-18). Play,
                 Download and the manual are under the cover, for everyone. -->
            <div class="gd-actions">
              <ManageMenu :items="manageItems" />
            </div>

            <!-- Disks of a title split across floppies. Playing always inserts
                 the whole set, so these choose which disk the machine starts
                 from - which matters for the sets that put a level editor or a
                 second scenario on a later disk. -->
            <div v-if="diskSet.length" class="gd-disks">
              <span class="gd-disks-label">{{ t('detail.disks') }}</span>
              <div
                v-for="d in diskSet"
                :key="d.id"
                class="gd-disk"
                :class="{ 'gd-disk--current': d.current }"
                :title="d.name"
              >
                <button v-if="ejsCore" class="gd-disk-btn" :title="t('detail.play_disk')" @click="requestPlay(d.id, false)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
                  </svg>
                  {{ t('detail.disk_n', { n: d.number }) }}
                </button>
                <span v-else class="gd-disk-btn gd-disk-btn--static">{{ t('detail.disk_n', { n: d.number }) }}</span>
                <button class="gd-disk-dl" :title="t('detail.download_disk')" @click="downloadRom(d.id)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                </button>
              </div>

              <!-- Writing one and converting to CHD are in the Manage menu. -->
              <span v-if="rom?.playlist" class="gd-disk-m3u gd-disk-m3u--have" :title="rom.playlist">
                {{ t('detail.has_playlist') }}
              </span>

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
              <!-- Who owns this ROM and, once an admin has claimed it, who
                   fetched it. Most ROMs were found on the disk by a scan and
                   have neither, so both rows simply stay away for those. -->
              <template v-if="rom.owner_username">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M5 16L3 5l5.5 5L12 4l3.5 6L21 5l-2 11H5zm0 2h14v2H5v-2z"/></svg></span>
                <span class="gd-dk">{{ t('detail.owner') }}</span>
                <span class="gd-dv gd-owner-cell">
                  {{ rom.owner_username }}
                </span>
              </template>
              <template v-if="rom.uploader_username">
                <span class="gd-di"><i class="mdi mdi-tray-arrow-up"></i></span>
                <span class="gd-dk">{{ t('detail.uploader') }}</span>
                <span class="gd-dv">{{ rom.uploader_username }}</span>
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
              <span class="gd-dv gd-mono">{{ formatSize(titleBytes) }}</span>
              <!-- What a dump is checked against. For an archive these are the
                   ROM inside it, which is what the databases are keyed on. -->
              <template v-if="rom.has_hashes">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 9h16M4 15h16M10 3L8 21M16 3l-2 18"/></svg></span>
                <span class="gd-dk">{{ t('detail.checksums') }}</span>
                <span class="gd-dv gd-mono gd-checksums">
                  <span v-if="rom.crc_hash"><b>CRC32</b> {{ rom.crc_hash }}</span>
                  <span v-if="rom.md5_hash"><b>MD5</b> {{ rom.md5_hash }}</span>
                  <span v-if="rom.sha1_hash"><b>SHA1</b> {{ rom.sha1_hash }}</span>
                </span>
              </template>
              <template v-if="rom.platform_name">
                <span class="gd-di"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="13" rx="5"/><path d="M7 12.5h2m-1-1v2M15.5 12.5h2"/><path d="M7 7l1.5-3h7L17 7"/></svg></span>
                <span class="gd-dk">{{ t('library.platform_label') }}</span>
                <span class="gd-dv">{{ rom.platform_name }}</span>
              </template>
              <template v-for="prow in pluginRows" :key="prow.id">
                <span v-if="prow.fullWidth" class="gd-dv" style="grid-column:1 / -1">
                  <PluginDetailValue :row="prow" :game="rom" library="roms" variant="dlist" />
                </span>
                <template v-else>
                  <span class="gd-di"></span>
                  <span class="gd-dk">{{ prow.label }}</span>
                  <span class="gd-dv"><PluginDetailValue :row="prow" :game="rom" library="roms" variant="dlist" /></span>
                </template>
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
import { romActions } from '@/lib/romSourceActions'
import { useNotifications } from '@/composables/useNotifications'
const { error: notifyError, success: notifySuccess } = useNotifications()
import { useCoverTilt } from '@/composables/useCoverTilt'
const { coverTilt, sheenStyle, onCoverMove, onCoverLeave } = useCoverTilt()
import { useI18n } from '@/i18n'
import EmulationRomMetadataPanel from './EmulationRomMetadataPanel.vue'
import PluginDetailValue from '@/components/games/PluginDetailValue.vue'
import { resolveDetailRows } from '@/themes/index'
import HeroBackground from '@/components/common/HeroBackground.vue'
import RomManualButton from '@/components/roms/RomManualButton.vue'
import RomDownloadDialog, { type RomExtra } from '@/components/roms/RomDownloadDialog.vue'
import RomFilesList from '@/components/roms/RomFilesList.vue'
import ManageMenu from '@/components/common/ManageMenu.vue'
import type { ManageItem } from '@/lib/manageMenu'
import { openRomAddFileDialog } from '@/lib/pluginUi'
import { getEjsCore } from '@/utils/ejsCores'
import { ratingVal } from '@/utils/rating'
import { formatBytes } from '@/utils/format'
const formatSize = (b: number | null | undefined) => formatBytes(b, '-')

const { gdConfirm, gdAlert } = useDialog()
const { t } = useI18n()

const route      = useRoute()
const router     = useRouter()
const auth       = useAuthStore()
const themeStore = useThemeStore()

const isAdmin  = computed(() => auth.user?.role === 'admin')
const canEdit  = computed(() => ['admin', 'uploader', 'editor'].includes(auth.user?.role as string))
// Who may add a file beside the game: the accounts that may upload at all.
const canUpload = computed(() => ['admin', 'uploader'].includes(auth.user?.role as string))
// A locked entry is the admin's alone, so there is nothing here for anyone
// else to open. Refusing at the button matters beyond tidiness: opening the
// editor fires searches at the metadata providers, and some of them charge
// for the request.
const metaLocked = computed(() => !isAdmin.value && !!(rom.value as any)?.metadata_locked)

// Only a ROM that belongs to a disk set is ever listed here, and the scanner
// assigns the group and the number together - so a disk always has both.
interface RomDisk {
  id: number
  number: number
  name: string
  /** Bytes on disk. Only used to put the weight of the whole set on the
   *  button that loads it. */
  size?: number | null
  current: boolean
}

interface RomDetail {
  id: number
  // Who owns this ROM, and who fetched it. Both absent for anything the disk
  // scanner merely found, which is most of them; the uploader is sent only once
  // a claim has parted the two.
  published_by?: number | null
  owner_username?: string | null
  uploaded_by?: number | null
  uploader_username?: string | null
  disks?: RomDisk[]
  platform_slug: string
  platform_fs_slug: string | null
  platform_name: string
  fs_name: string
  fs_name_no_ext: string | null
  fs_extension: string
  fs_size_bytes: number
  /** What the tracks of a disc kept as a sheet add: fs_size_bytes is the
   *  sheet alone, a few kilobytes of text. */
  tracks_bytes?: number
  /** Whether this file is identified by checksum at all. False when the scan
   *  skipped it for its size, or when its format carries none. */
  has_hashes?: boolean
  /** The name of an .m3u in the library that names these discs, or null when
   *  they have none. Only ever set for a title with discs to switch between. */
  playlist?: string | null
  /** Whether the player can put every disc of the set into the emulator.
   *  True for a bare image and for a zip, which it unpacks on the way in;
   *  false for a .7z it cannot open and for a sheet whose tracks are not
   *  library rows and so would not be fetched with it. */
  set_loads_whole?: boolean
  /** Whether every disc is something chdman can be handed. Asked of the files
   *  rather than of their names, so a zipped cartridge ROM says no. */
  chd_convertible?: boolean
  /** The files in the game's extras/ and mods/, read off its folder. */
  extras?: RomExtra[]
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
  rating: number | null       // ScreenScraper note / 20 - a 0-1 fraction, never shown
  rating_agg: number | null   // blended 0-5 score - the one shown as stars
  ss_score: number | null
  igdb_rating: number | null
  lb_rating: number | null
  // Optional on purpose: an entry saved from the metadata editor before it
  // learned to carry them has the rating and nothing else.
  plugin_ratings: Record<string, { name?: string; rating?: number; logo_url?: string }> | null
  crc_hash: string | null
  md5_hash: string | null
  sha1_hash: string | null
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
  has_manual?:     boolean
  igdb_id:         number | null
  ss_id:           string | null
  launchbox_id:    string | null
}

const rom              = ref<RomDetail | null>(null)

// Rows contributed by plugins via window.__GD__.registerDetailRow.
const pluginRows       = computed(() => rom.value ? resolveDetailRows(rom.value as any, 'roms') : [])
const loading          = ref(true)
const coverFailed      = ref(false)
const backPillLogoFailed = ref(false)
const devLogoFailed    = ref(false)
const pubLogoFailed    = ref(false)
const wheelFailed      = ref(false)
const scraping      = ref(false)
const clearing      = ref(false)
const hashing       = ref(false)
const deleting      = ref(false)
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

// Arriving from the dashboard "Continue playing" tile (?resume=1) asks the player
// to auto-load a savestate once the game boots. An optional ?save= names WHICH
// one ("state:<id>" from a slot tile's Play button); without it the player takes
// the newest. A battery save is never named here - it goes into the machine on
// every launch, resume or not.
const wantResume = computed(() => route.query.resume === '1')
const resumeSave = computed(() => String(route.query.save || ''))

// A title split across floppies is one library entry; the rest of its disks are
// hidden everywhere else and only reachable from here.
const diskSet = computed<RomDisk[]>(() => rom.value?.disks || [])
// Every disc at once is the price of letting the emulator switch between
// them, so the button says what it costs rather than finding out later.
const diskSetBytes = computed(() =>
  diskSet.value.reduce((sum, d) => sum + (d.size || 0), 0))
// What the game weighs, which for a title split across discs is all of them.
// The row names disc one, so showing its size alone answered a question
// nobody asked: a four disc set read as 480 MB when it is nearer 1.5 GB.
const titleBytes = computed(() =>
  diskSet.value.length > 1 ? diskSetBytes.value
    : (rom.value?.fs_size_bytes || 0) + (rom.value?.tracks_bytes || 0))
// The game as one entry in its file list and download picker, however many
// discs it came on: they download together, as one archive.
const romGameLabel = computed(() =>
  diskSet.value.length > 1
    ? t('detail.all_discs', { n: diskSet.value.length })
    : (rom.value?.fs_name || ''))
const showRomDownload = ref(false)

// Which disk the machine should start from, chosen from that list. Null means
// the one the entry itself names, which is disk 1 for every ordinary set.
const pendingDisk = ref<number | null>(null)
// Whether to load every disc of the set rather than the one that was clicked.
// Opt in per launch: it is what makes the emulator able to switch discs on its
// own, and it is also well over a gigabyte held in the tab for a four disc
// PlayStation title, which is comfortable on a desktop and hopeless on a phone.
const pendingWholeSet = ref(false)

const playerUrl = computed(() => {
  if (!rom.value || !ejsCore.value) return ''
  const p = new URLSearchParams({
    rom_id:   String(rom.value.id),
    rom_name: rom.value.name || rom.value.fs_name_no_ext || String(rom.value.id),
    ejs_core: ejsCore.value,
    platform: rom.value.platform_fs_slug || '',
  })
  if (rom.value.bezel_path && bezelEnabled.value) p.set('bezel_url', rom.value.bezel_path)
  if (wantResume.value) p.set('resume', '1')
  if (wantResume.value && resumeSave.value) p.set('save', resumeSave.value)
  if (pendingDisk.value) p.set('disk', String(pendingDisk.value))
  if (pendingWholeSet.value) p.set('discs', 'all')
  return `/player.html?${p.toString()}`
})

// Play, for a title split across discs, means the whole title. Nobody wants
// disc one of four on its own, and the discs are listed right below for the
// sets that put a level editor or a second scenario on a later one. Being the
// default rather than a second button beside it is what keeps the page from
// growing a control for every way of starting the same game.
//
// wholeSet is still a parameter, because the per-disc buttons pass false: they
// exist precisely to start from one disc. A set that cannot be loaded whole
// falls back to a single disc on its own, which is what set_loads_whole says.
function requestPlay(diskId?: number, wholeSet?: boolean) {
  pendingDisk.value = diskId ?? null
  pendingWholeSet.value = wholeSet ?? (
    diskId === undefined && diskSet.value.length > 1 && !!rom.value?.set_loads_whole
  )
  const saved = localStorage.getItem(PREF_KEY) as 'full' | 'window' | 'tab' | null
  // This game's answer about the bezel, and shown when there is none. Reading
  // it as "not switched off" rather than "switched on" is what makes the art a
  // game was scraped with actually appear: the key is written the first time
  // somebody answers, so === '1' hid every bezel nobody had found the toggle
  // for yet.
  if (rom.value?.bezel_path && rom.value.id) {
    bezelEnabled.value = localStorage.getItem(bezelKey(rom.value.id)) !== '0'
  }
  if (saved) {
    // Use saved preference directly, skip dialog
    pendingMode.value = saved
    launchPlayer()
  } else {
    // Ask for the display mode (fullscreen / window / tab + bezel). This applies
    // to Continue-playing resume too - only the SAVE is auto-loaded, the window
    // choice still belongs to the user (resume=1 rides on playerUrl regardless).
    pendingMode.value = 'full'
    rememberMode.value = false
    showPlayerDialog.value = true
  }
}

// Reopening the question, which pressing Play no longer does once an answer was
// remembered. It is not enough to raise the dialog: Play also records which disc
// was asked for and reads this game's bezel setting, and a dialog opened without
// both would offer the previous game's answers and then save them over this one.
function openDisplayOptions() {
  pendingDisk.value = null
  pendingWholeSet.value = diskSet.value.length > 1 && !!rom.value?.set_loads_whole
  if (rom.value?.bezel_path && rom.value.id) {
    bezelEnabled.value = localStorage.getItem(bezelKey(rom.value.id)) !== '0'
  }
  const saved = localStorage.getItem(PREF_KEY) as 'full' | 'window' | 'tab' | null
  pendingMode.value = saved ?? 'full'
  // Ticked because it is true: a mode is remembered. Unticking it here is how
  // the user asks to be given the choice again, which is what launchPlayer acts
  // on below.
  rememberMode.value = !!saved
  showPlayerDialog.value = true
}

function launchPlayer() {
  if (rememberMode.value) {
    localStorage.setItem(PREF_KEY, pendingMode.value)
  } else {
    // The half that was missing. Storing on tick but never clearing on untick
    // is what made the choice permanent: the box could be emptied and the
    // preference stayed, so the dialog never came back on its own.
    localStorage.removeItem(PREF_KEY)
  }
  showPlayerDialog.value = false

  if (pendingMode.value === 'full') {
    // Fullscreen: same-tab navigation (like Couch Mode) - enables COOP/COEP + auto-fullscreen.
    // Strip resume from returnTo so exiting the game returns to a clean detail URL
    // and does NOT re-trigger the auto-resume launch (which would trap the user in
    // an exit->relaunch loop, since a full-page reload resets the in-memory guard).
    const back = new URL(window.location.href)
    back.searchParams.delete('resume')
    back.searchParams.delete('save')
    const returnTo = back.pathname + back.search
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


// ── Carousel ───────────────────────────────────────────────────────────────────
// One whole picture per click, like Classic. The row holds the trailer's
// picture too, so the last stop counts slides, not screenshots. And a slide's
// offsetLeft counts from the wrapper, arrow and gap included, so a stop is
// measured from the first slide instead.
function slideTo(idx: number) {
  const max = Math.max(0, carouselSlides.value.length - 3)
  carouselIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = carouselEl.value
    if (!el) return
    const first = el.children[0] as HTMLElement | undefined
    const child = el.children[carouselIdx.value] as HTMLElement | undefined
    if (first && child) el.scrollTo({ left: child.offsetLeft - first.offsetLeft, behavior: 'smooth' })
  })
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
// Taking a ROM over from the account that fetched it. Worth a confirmation
// because two of its three effects land on somebody else's account rather than
// on this page: their quota frees up and their delete goes away.
const claiming = ref(false)
async function claimRom() {
  if (!rom.value || claiming.value) return
  if (!await gdConfirm(
    t('detail.claim_body').replace('{name}', (rom.value as any).owner_username || '?'),
    { title: t('detail.claim') },
  )) return
  claiming.value = true
  try {
    await client.post(`/roms/${rom.value.id}/claim`)
    await fetchRom()
  } catch {
    await gdAlert(t('detail.claim_failed'))
  } finally { claiming.value = false }
}

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

// After a file was added or binned: the ROM again, without the page going back
// to its loading state around it.
async function refreshRom() {
  const id = rom.value?.id
  if (!id) return
  try {
    const { data } = await client.get(`/roms/${id}`)
    rom.value = data
  } catch { /* the page keeps what it had */ }
}

// "Add file" (1.0.36): the core dialog every skin opens, for administrators and
// uploaders alike; the bytes count against the account that sends them.
function openAddFile() {
  if (!rom.value) return
  openRomAddFileDialog({
    rom: { id: rom.value.id, title: rom.value.name || rom.value.fs_name,
           platform_fs_slug: rom.value.platform_fs_slug },
    onAdded: refreshRom,
  })
}

function openEditPanel() {
  showEditPanel.value = true
}

// ── Manage menu ───────────────────────────────────────────────────────────────
// What a plain user is not offered, under one button (the owner, 2026-09-18).
// Each item is shown on exactly the check its button had, so an uploader or an
// editor sees the same button with fewer items in it:
//
//   edit, scrape     LIBRARY_WRITE, which an editor has
//   clear, delete    ROMS_WRITE, the admin's alone - under canEdit an editor
//                    was once shown a Clear that could only answer 403. Delete
//                    is the one action here with nothing behind it; a cleared
//                    scrape can be scraped again
//   hashes           only for a file the scan did not identify by hash: it
//                    skipped it for its size, or the format carries none
//   playlist         lets the emulator offer the disc swap itself. Only while
//                    the discs have none: one may have come down beside them,
//                    or been written by hand on a handheld
//   chd              one file per disc, about half the size, opened without
//                    unpacking. Only where it would work: a title already in
//                    CHD, or a zipped cartridge, is not offered it
//   claim            only while somebody else owns the ROM
const manageItems = computed<ManageItem[]>(() => {
  const r = rom.value
  return [
    { key: 'edit', group: 'metadata', show: canEdit.value,
      icon: metaLocked.value ? 'mdi-lock-outline' : 'mdi-pencil-outline',
      label: t('detail.edit_metadata'), disabled: metaLocked.value,
      title: metaLocked.value ? t('meta.locked_by_admin') : undefined, run: openEditPanel },
    { key: 'scrape', group: 'metadata', show: canEdit.value, icon: 'mdi-refresh', busy: scraping.value,
      label: scraping.value ? t('detail.scraping') : t('detail.scrape'), run: triggerScrape },
    { key: 'clear', group: 'metadata', show: isAdmin.value, icon: 'mdi-eraser', danger: true, busy: clearing.value,
      label: clearing.value ? t('detail.clearing') : t('detail.clear_metadata'), run: onClearMetadata },
    { key: 'add-file', group: 'files', show: canUpload.value, icon: 'mdi-file-plus-outline',
      label: t('detail.add_file'), run: openAddFile },
    { key: 'hashes', group: 'files', show: isAdmin.value && r?.has_hashes === false, icon: 'mdi-pound',
      busy: hashing.value, label: hashing.value ? t('detail.computing_hashes') : t('detail.compute_hashes'),
      title: t('detail.compute_hashes_hint'), run: computeHashes },
    { key: 'playlist', group: 'files', show: isAdmin.value && diskSet.value.length > 1 && !r?.playlist,
      icon: 'mdi-playlist-play', busy: writingPlaylist.value,
      label: writingPlaylist.value ? t('detail.writing_playlist') : t('detail.write_playlist'),
      title: t('detail.write_playlist_hint'), run: writePlaylist },
    { key: 'chd', group: 'files', show: isAdmin.value && !!r?.chd_convertible, icon: 'mdi-disc',
      busy: converting.value, label: t('detail.convert_chd'),
      title: t('detail.convert_chd_hint'), run: convertToChd },
    { key: 'claim', group: 'publishing', show: isAdmin.value && !!r?.published_by && r.published_by !== auth.user?.id,
      icon: 'mdi-account-arrow-left-outline', busy: claiming.value,
      label: t('detail.claim'), title: t('detail.claim_hint'), run: claimRom },
    { key: 'delete', group: 'danger', show: isAdmin.value, icon: 'mdi-delete-outline', danger: true,
      busy: deleting.value, label: deleting.value ? t('detail.deleting') : t('detail.delete_rom'), run: onDelete },
  ]
})

async function downloadRom(diskId?: number) {
  if (!rom.value) return
  // With extras or mods beside it, the whole game's download is a choice of
  // files, the way a GOG or custom game offers its own. One disc asked for by
  // its own button is still just that disc.
  if (!diskId && rom.value.extras?.length) {
    showRomDownload.value = true
    return
  }
  // Saving a file means navigating the browser, and a navigation sends no
  // Authorization header - pointing it straight at the authenticated route
  // only ever produced "Not authenticated". Ask for a short-lived ticket over
  // the authenticated connection first, then navigate to that.
  try {
    // Without a disk named, the whole title is wanted - which for a game
    // split across floppies means every disk, not the one the entry carries.
    const whole = !diskId && diskSet.value.length > 1 ? '?whole_set=1' : ''
    const { data } = await client.post(`/roms/${diskId ?? rom.value.id}/download-ticket${whole}`)
    window.open(data.url, '_blank')
  } catch {
    gdAlert(t('detail.download_failed'))
  }
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

// Reading a file that the scan declined to read, because this time somebody
// asked for it. It can take a while on a large image, so the button says so
// while it runs and the page reloads afterwards to drop it.
//
// The failure has to be spoken. A file can be unreadable, or be a format that
// carries no usable digest, and then the server refuses; swallowing that left
// the button sitting there after the spinner, with nothing said, and clicking
// it again did the same nothing.
const writingPlaylist = ref(false)

// Writing the playlist into the library, beside the discs. It is a real file
// rather than something assembled per launch, so it is still there when the
// shelf is copied to a handheld and when RetroArch opens the folder.
async function writePlaylist() {
  if (!rom.value) return
  writingPlaylist.value = true
  try {
    const { data } = await client.post(`/roms/${rom.value.id}/playlist`)
    await fetchRom()
    notifySuccess(t('detail.write_playlist_done', { name: data.name }))
  } catch {
    notifyError(t('detail.write_playlist_failed'))
  } finally {
    writingPlaylist.value = false
  }
}

// Asked before the work starts rather than offered afterwards. Converting a
// four disc set with both copies on disk is 3.5 GB where the answer is 1.9 GB,
// and nobody wants to find that out at the end.
//
// Two questions rather than one dialog with a checkbox, because the dialog
// GD has answers yes or no and this needs three outcomes: convert and delete,
// convert and keep, or do neither. Nothing is started until both are answered.
const converting = ref(false)

async function convertToChd() {
  if (!rom.value || converting.value) return
  if (!await gdConfirm(t('detail.convert_chd_body'), {
    title: t('detail.convert_chd_title'),
    confirmText: t('detail.convert_chd'),
  })) return

  const deleteSource = await gdConfirm(
    `${t('detail.convert_chd_delete')}\n\n${t('detail.convert_chd_keep')}`,
    {
      title: t('detail.convert_chd_title'),
      confirmText: t('common.yes'),
      cancelText: t('common.no'),
    },
  )

  converting.value = true
  try {
    // Through __GD__ rather than by URL: the themes reach the same primitive
    // and none of them has to know where the route lives.
    await romActions.convertToChd(rom.value.id, deleteSource)
    notifySuccess(t('detail.convert_chd_started'))
  } catch (err: any) {
    notifyError(err?.response?.data?.detail || t('detail.convert_chd_failed'))
  } finally {
    converting.value = false
  }
}

async function computeHashes() {
  if (!rom.value) return
  hashing.value = true
  try {
    await client.post(`/roms/${rom.value.id}/hashes`)
    await fetchRom()
    // Said out loud. The button disappearing is the only other sign that
    // anything happened, and that reads as easily like a failure as a success.
    notifySuccess(t('detail.compute_hashes_done'))
  } catch {
    notifyError(t('detail.compute_hashes_failed'))
  } finally {
    hashing.value = false
  }
}

// Removing a ROM asks twice, and the first question is built from what the
// server says would actually go. Two things make this destructive and neither
// is visible on the page: a floppy title is several entries that only work
// together, and the saves that go with them can belong to other people.
async function onDelete() {
  if (!rom.value) return
  const id = rom.value.id
  let preview: { disks: { name: string }[]; files: string[]; extras?: string[]; saves: number; on_disk: boolean }
  try {
    preview = (await client.get(`/roms/${id}/removal`)).data
  } catch {
    await gdAlert(t('detail.delete_failed', 'Could not read what would be removed.'))
    return
  }

  const lines = [t('detail.delete_body').replace('{name}', rom.value.name || rom.value.fs_name)]
  if (preview.disks.length > 1) {
    lines.push(t('detail.delete_rom_disks').replace('{n}', String(preview.disks.length)))
  }
  if (preview.saves > 0) {
    lines.push(t('detail.delete_rom_saves').replace('{n}', String(preview.saves)))
  }
  // The tick belongs on this question and not on the one about the file below.
  // Saves, scraped artwork and the entry itself go the moment this is answered,
  // whichever way the next one is answered - and a save is the one thing here
  // that cannot be fetched again from anywhere.
  if (!await gdConfirm(lines.join('\n\n'), {
    danger: true,
    title: t('detail.delete_rom'),
    requireTick: true,
  })) return

  // Only worth asking when there is a file to ask about, and the answer that
  // keeps it is the one on the cancel button.
  let withFiles = false
  if (preview.on_disk) {
    // The data files behind a sheet belong to this question and not the one
    // above: they go with the file or they stay with it, and until now the
    // count sat on the question that acts whichever way it is answered - so the
    // sentence somebody had to tick to acknowledge was untrue for every CD rip
    // in the library.
    const fileLines = [t('detail.delete_rom_files_body')]
    if (preview.files?.length) {
      fileLines.push(t('detail.delete_rom_tracks').replace('{n}', String(preview.files.length)))
    }
    // What the game keeps in extras/ and mods/ goes with the file (the owner's
    // decision D), so it is named here, a few of them, rather than counted
    // among the data files the sheets name.
    const extras = preview.extras ?? []
    if (extras.length) {
      const names = extras.slice(0, 5).join(', ') + (extras.length > 5 ? ', …' : '')
      fileLines.push(t('detail.delete_rom_extras')
        .replace('{n}', String(extras.length)).replace('{names}', names))
    }
    withFiles = await gdConfirm(fileLines.join('\n\n'), {
      danger: true,
      title: t('detail.delete_rom_files_title'),
      confirmText: t('detail.delete_files_yes'),
      cancelText: t('detail.delete_files_no'),
    })
  }

  deleting.value = true
  try {
    await client.delete(`/roms/${id}`, { params: { delete_files: withFiles } })
    router.push({ name: 'emulation-library', params: { platform: rom.value.platform_slug } })
  } catch {
    await gdAlert(t('detail.delete_failed', 'Could not delete this ROM.'))
  } finally {
    deleting.value = false
  }
}

function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}


// Handle postMessage from player iframe
function onPlayerMessage(e: MessageEvent) {
  if (e.data?.type === 'gd-exit') closePlayer()
  if (e.data?.type === 'gd-game-started') nextTick(() => playerIframe.value?.focus())
}

let _resumeLaunched = false
onMounted(async () => {
  window.addEventListener('message', onPlayerMessage)
  await fetchRom()
  // Continue playing: kick off the launch flow (asks display mode if none saved),
  // then the game auto-resumes from the save (resume=1 is on playerUrl).
  if (wantResume.value && ejsCore.value && !_resumeLaunched) {
    _resumeLaunched = true
    nextTick(() => requestPlay())
  }
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
/* Play and the caret read as one control, so they sit in one row with a hairline
   between them and only the outer corners rounded. The gap is the separator:
   the column behind it is dark, so nothing has to be drawn. */
.gd-play-split { display: flex; gap: 1px; width: 100%; }
.gd-play-split .gd-btn-play--cover {
  flex: 1; min-width: 0;
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}
.gd-btn-play--more {
  flex: none; width: 38px; padding: 10px 0; justify-content: center;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  /* The pair would otherwise cast two overlapping glows along the seam. */
  box-shadow: none;
}
.gd-btn-dl--cover {
  width: 100%; justify-content: center; font-size: 13px; padding: 9px 0;
}
/* The manual sits under the download, the same width, so the column stays one
   stack of buttons rather than two sizes of them. */
.gd-manual-cover { width: 100%; }
.gd-files-cover { width: 100%; }
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
  /* 16:9 on the picture, not on the window: the bezel inside the iframe is
     16:9 and object-fit:cover crops whatever does not match, so a window that
     were itself 16:9 would leave the picture a title bar short of it and clip
     the bezel sides anyway. Height stays what it was; the width is what 16:9
     asks for underneath the bar, so the picture widens instead of shrinking. */
  --gd-player-bar: 38px;
  width: min(96vw, calc((min(90vh, 760px) - var(--gd-player-bar)) * 16 / 9));
  border-radius: var(--radius, 12px); overflow: hidden;
  border: 1px solid #2e2e4a;
  display: flex; flex-direction: column;
  box-shadow: 0 40px 120px rgba(0,0,0,.8);
}
.gd-player-window-bar {
  display: flex; align-items: center;
  background: #12121e; border-bottom: 1px solid #2e2e4a;
  padding: 0 14px; height: var(--gd-player-bar); gap: 10px; flex-shrink: 0;
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
  width: 100%; aspect-ratio: 16 / 9; border: none; display: block;
}

.gd-btn-dl {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 18px var(--pglow2);
}
.gd-btn-dl:hover { background: var(--pl-light); transform: translateY(-1px); }

/* Disks of a multi-floppy title */
.gd-disks { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
.gd-disks-label { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,.32); margin-right: 2px; }
.gd-disk {
  display: inline-flex; align-items: stretch; border-radius: 6px; overflow: hidden;
  background: color-mix(in srgb, var(--pl) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 26%, transparent);
}
.gd-disk--current { border-color: color-mix(in srgb, var(--pl) 55%, transparent); }
.gd-disk-btn, .gd-disk-dl {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px;
  background: none; border: 0; cursor: pointer;
  color: rgba(255,255,255,.72); font-size: 11px; font-weight: 600;
  transition: background .15s, color .15s;
}
.gd-disk-btn:hover, .gd-disk-dl:hover { background: color-mix(in srgb, var(--pl) 26%, transparent); color: #fff; }
.gd-disk-btn--static { cursor: default; }
.gd-disk-btn--static:hover { background: none; color: rgba(255,255,255,.72); }
.gd-disk-dl { padding: 4px 7px; border-left: 1px solid color-mix(in srgb, var(--pl) 26%, transparent); color: rgba(255,255,255,.5); }

/* Glass like every other chip on this page, never a solid fill. */
.gd-disk-m3u {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--pl) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 26%, transparent);
  color: rgba(255,255,255,.72); font-size: 11px; font-weight: 600;
}
.gd-disk-m3u--have { cursor: default; opacity: .62; background: none; }

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
.gd-owner-cell { display: flex; align-items: center; gap: 6px; }
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
/* Three long hex strings. Stacked, each labelled, and allowed to break rather
   than pushing the details table sideways on a narrow window. */
.gd-checksums { display: flex; flex-direction: column; gap: 2px; word-break: break-all; }
.gd-checksums b { font-weight: 600; opacity: .55; margin-right: 6px; font-family: inherit; }
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
