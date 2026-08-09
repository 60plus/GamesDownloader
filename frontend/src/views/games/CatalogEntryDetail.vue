<template>
  <div class="ced-root">

    <!-- ── Skeleton ─────────────────────────────────────────────────────────── -->
    <template v-if="loading">
      <div class="ced-sk-hero" />
      <div class="ced-sk-body">
        <div class="ced-sk-line ced-sk-line--xl" /><div class="ced-sk-line ced-sk-line--md" />
        <div class="ced-sk-line ced-sk-line--sm" /><div class="ced-sk-line ced-sk-line--lg" />
      </div>
    </template>

    <!-- ── Not found ────────────────────────────────────────────────────────── -->
    <div v-else-if="!entry" class="ced-empty">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.18">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
      <p>{{ t('detail.game_not_found') }}</p>
      <button class="ced-back-pill" @click="goBack">{{ t('detail.back_to_library') }}</button>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN                                                                    -->
    <!-- ════════════════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- ── HERO ─────────────────────────────────────────────────────────── -->
      <div class="ced-hero">
        <HeroBackground
          :src="bgSrc"
          :anim-style="themeStore.heroAnimStyle"
          :anim-enabled="themeStore.heroAnim && themeStore.animations"
        />

        <button class="ced-back-pill" @click="goBack">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ storeName }}
        </button>

        <div class="ced-hero-inner">
          <!-- Cover with 3D tilt effect -->
          <div class="ced-cover-col">
            <div
              class="ced-cover-frame"
              :style="{ transform: coverTilt, willChange: 'transform' }"
              @mousemove="onCoverMove"
              @mouseleave="onCoverLeave"
            >
              <img
                v-if="!coverFailed && entry.cover_path"
                :src="entry.cover_path"
                :alt="entry.title"
                class="ced-cover-img"
                @error="coverFailed = true"
              />
              <div v-else class="ced-cover-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                </svg>
              </div>
              <div class="ced-cover-sheen" :style="sheenStyle" />
            </div>
          </div>

          <!-- Info -->
          <div class="ced-info-col">

            <img v-if="entry.logo_path" :src="entry.logo_path" :alt="entry.title" class="ced-logo-img" />
            <h1 v-else class="ced-title">{{ entry.title }}</h1>
            <!-- Outside the v-else on purpose: which build this is stays worth
                 saying even when a logo replaces the title. -->
            <div v-if="entry.subtitle" class="ced-subtitle">{{ entry.subtitle }}</div>

            <div class="ced-badge-row">
              <!-- The catalogue this came from stands where a game shows GOG or
                   Custom: an entry has no `source` column to badge. -->
              <span class="ced-source-badge">{{ storeName }}</span>
              <span v-if="entry.downloaded" class="ced-owned-badge">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                {{ t('detail.in_library') }}
              </span>
              <!-- Version facts are data, so they read as chips rather than as
                   labelled rows nothing else in the design would match. -->
              <span v-if="entry.release_tag" class="ced-ver-chip">{{ entry.release_tag }}</span>
              <span v-if="entry.is_prerelease" class="ced-ver-chip ced-ver-chip--warn">pre-release</span>
            </div>

            <div class="ced-meta-row">
              <span v-if="entry.developer" class="ced-meta-item">{{ entry.developer }}</span>
              <span v-if="entry.publisher && entry.publisher !== entry.developer" class="ced-meta-sep">·</span>
              <span v-if="entry.publisher && entry.publisher !== entry.developer" class="ced-meta-item">{{ entry.publisher }}</span>
              <span v-if="releaseYear" class="ced-meta-sep">·</span>
              <span v-if="releaseYear" class="ced-meta-item">{{ releaseYear }}</span>
            </div>

            <!-- Stars come from the entry's own 0-5 rating. There is no blended
                 rating_agg here, and no GOG chip: a copied RAWG/IGDB score under
                 the GOG mark would invent a rating this listing never had. -->
            <div v-if="ratingVal(entry.rating) > 0" class="ced-rating-row">
              <svg v-for="i in 5" :key="i" width="16" height="16" viewBox="0 0 24 24"
                :fill="i <= Math.round(ratingVal(entry.rating)) ? '#f59e0b' : 'rgba(255,255,255,.12)'"
                :stroke="i <= Math.round(ratingVal(entry.rating)) ? '#f59e0b' : 'rgba(255,255,255,.2)'"
                stroke-width="1"
              >
                <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
              </svg>
              <span class="ced-rating-num">{{ ratingVal(entry.rating).toFixed(1) }}</span>
            </div>

            <!-- Per-source scores (RAWG / IGDB / Metacritic / plugin providers) -->
            <div v-if="externalRatings.rawg || externalRatings.igdb || externalRatings.steam || pluginRatings.length" class="ced-ext-ratings">
              <div v-if="externalRatings.rawg" class="ced-ext-score">
                <img src="/icons/RAWG.ico" class="ced-ext-ico" width="42" height="42" alt="RAWG" />
                <div class="ced-ext-info">
                  <span class="ced-ext-val">{{ ratingVal(externalRatings.rawg).toFixed(1) }}<span class="ced-ext-max">/5</span></span>
                  <span class="ced-ext-lbl">RAWG</span>
                </div>
              </div>
              <div v-if="externalRatings.igdb" class="ced-ext-score">
                <img src="/icons/igdb.ico" class="ced-ext-ico" width="42" height="42" alt="IGDB" />
                <div class="ced-ext-info">
                  <span class="ced-ext-val">{{ Math.round(ratingVal(externalRatings.igdb)) }}<span class="ced-ext-max">/100</span></span>
                  <span class="ced-ext-lbl">IGDB</span>
                </div>
              </div>
              <div v-if="externalRatings.steam" class="ced-ext-score">
                <img src="/icons/metacritic.svg" class="ced-ext-ico" width="42" height="42" alt="Metacritic" />
                <div class="ced-ext-info">
                  <span class="ced-ext-val">{{ Math.round(ratingVal(externalRatings.steam) * 10) }}<span class="ced-ext-max">/100</span></span>
                  <span class="ced-ext-lbl">Metacritic</span>
                </div>
              </div>
              <div v-for="pr in pluginRatings" :key="pr.id" class="ced-ext-score">
                <img :src="pr.logo" class="ced-ext-ico" width="42" height="42" :alt="pr.name" @error="hideImg" />
                <div class="ced-ext-info">
                  <span class="ced-ext-val">{{ ratingVal(pr.rating).toFixed(1) }}<span class="ced-ext-max">/10</span></span>
                  <span class="ced-ext-lbl">{{ pr.name }}</span>
                </div>
              </div>
            </div>

            <!-- Genres -->
            <div v-if="(entry.genres || []).length" class="ced-tag-row">
              <span v-for="g in (entry.genres || []).slice(0, 5)" :key="g" class="ced-genre-tag">{{ g }}</span>
            </div>

            <!-- Platforms. An entry has no os_* flags, so the builds on offer are
                 the only honest source for this row. -->
            <div v-if="assetOses.length" class="ced-os-row">
              <span v-for="os in assetOses" :key="os" class="ced-os-chip">
                <svg v-if="os === 'windows'" width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"/>
                </svg>
                <svg v-else-if="os === 'mac'" width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.71,19.5C17.88,20.74 17,21.95 15.66,21.97C14.32,22 13.89,21.18 12.37,21.18C10.84,21.18 10.37,21.95 9.1,22C7.78,22.05 6.8,20.68 5.96,19.47C4.25,17 2.94,12.45 4.7,9.39C5.57,7.87 7.13,6.91 8.82,6.88C10.1,6.86 11.32,7.75 12.11,7.75C12.89,7.75 14.37,6.68 15.92,6.84C16.57,6.87 18.39,7.1 19.56,8.82C19.47,8.88 17.39,10.1 17.41,12.63C17.44,15.65 20.06,16.66 20.09,16.67C20.06,16.74 19.67,18.11 18.71,19.5M13,3.5C13.73,2.67 14.94,2.04 15.94,2C16.07,3.17 15.6,4.35 14.9,5.19C14.21,6.04 13.07,6.7 11.95,6.61C11.8,5.46 12.36,4.26 13,3.5Z"/>
                </svg>
                <img v-else-if="os === 'linux'" src="/icons/os-linux.svg" width="28" height="28" alt="Linux" style="flex-shrink:0" />
                {{ osLabel(os) }}
              </span>
            </div>

            <!-- Action buttons -->
            <div class="ced-actions">
              <!-- Once the game is here, going to it leads and downloading it
                   again follows, so the store and the game page agree on which
                   action is the loud one. -->
              <button v-if="entry.downloaded && entry.library_game_id" class="ced-btn-dl" @click="openGame">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                {{ t('detail.open_in_library') }}
              </button>

              <!-- Just queued from this page: a marker so the page does not read
                   as "nothing happened" the instant a download starts. Transient
                   (justQueued), not derived from library_game_id, because a game
                   with no files can equally be a download that failed - which the
                   store treats as on offer again, not as forever downloading. -->
              <button v-else-if="justQueued" class="ced-btn-ghost" disabled>
                <svg class="ced-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                {{ t('detail.downloading') }}
              </button>

              <!-- Opens the picker; the queuing, its spinner and its errors all
                   belong to the dialog now. Loud when nothing is on the server yet
                   (on offer, or a download that failed); a ghost re-download once
                   the game has files or a download was just queued. -->
              <button
                v-if="entry.available && assets.length"
                :class="(entry.downloaded || justQueued) ? 'ced-btn-ghost' : 'ced-btn-dl'"
                @click="download"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M12 2v10m0 0l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.56 21H19.44a2 2 0 0 0 1.94-1.515L22 17"/>
                </svg>
                {{ t('detail.download') }}
                <span class="ced-btn-count">{{ t('detail.file_count', { count: assets.length }) }}</span>
              </button>
              <span v-else-if="!entry.available" class="ced-no-files">{{ entry.unavailable_reason || t('detail.unavailable') }}</span>
              <span v-else class="ced-no-files">{{ t('detail.no_files') }}</span>

              <!-- The catalogue's own page for this listing. Labelled with its
                   host, which needs no translation. -->
              <!-- href takes a string or nothing; the field is nullable, and the
                   v-if only proves the host parsed, not that TypeScript knows. -->
              <a v-if="homepageHost" class="ced-btn-ghost" :href="entry.homepage || undefined" target="_blank" rel="noopener noreferrer">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                {{ homepageHost }}
              </a>

              <button v-if="isAdmin" class="ced-btn-ghost" @click="showMetaPanel = true">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t('detail.edit_metadata') }}
              </button>
              <button v-if="isAdmin" class="ced-btn-ghost" :disabled="scraping" @click="refreshMeta">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :class="{ 'ced-spin': scraping }">
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                {{ scraping ? t('detail.scraping') : t('detail.refresh_metadata') }}
              </button>
              <!-- No standalone "search term": the editor's every tab carries
                   its own "title to search" field, so a wrong match is fixed
                   there, the way a GOG game's editor already works. -->
            </div>
          </div>
        </div>
      </div>

      <!-- ── Hero → body separator ──────────────────────────────────────── -->
      <div class="ced-separator" />

      <!-- ── BODY ─────────────────────────────────────────────────────────── -->
      <div class="ced-body">

        <!-- ── Media: screenshots carousel ──────────────────────────────── -->
        <div v-if="screenshots.length" class="ced-media-section">
          <div class="ced-section-label">{{ t('detail.media') }}</div>
          <div class="ced-carousel-wrap">
            <button class="ced-carr-btn ced-carr-btn--left" :disabled="carouselIdx === 0" @click="slideTo(carouselIdx - 1)">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <div class="ced-carousel" ref="carouselEl" :style="{ '--ced-per-view': perView }">
              <div
                v-for="(src, idx) in screenshots"
                :key="idx"
                class="ced-slide"
                :class="{ 'ced-slide--active': idx === carouselIdx }"
                @click="lightboxIdx = idx"
              >
                <img :src="src" :alt="`Screenshot ${idx + 1}`" loading="lazy" />
              </div>
            </div>
            <button class="ced-carr-btn ced-carr-btn--right"
              :disabled="screenshots.length <= perView || carouselIdx >= screenshots.length - perView"
              @click="slideTo(carouselIdx + 1)">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <!-- One dot per scroll POSITION, not per screenshot: the strip stops
               scrolling once the last slide is flush right, so a dot per image
               left the final ones permanently unreachable. -->
          <div v-if="dotCount > 1" class="ced-dots">
            <span
              v-for="i in dotCount"
              :key="i"
              class="ced-dot-item"
              :class="{ active: i - 1 === carouselIdx }"
              @click="slideTo(i - 1)"
            />
          </div>
        </div>

        <!-- ── Two-column: description + facts and builds ───────────────── -->
        <!-- A never-scraped entry is the common case in a store, so the left
             column has to disappear rather than sit there empty beside a 340px
             box with the rest of the width blank. -->
        <div class="ced-cols" :class="{ 'ced-cols--single': !entry.description }">

          <!-- Left: description -->
          <div v-if="entry.description" class="ced-col-left">
            <div class="ced-section-label">{{ t('detail.about') }}</div>
            <div class="ced-desc-wrap" :class="{ 'ced-desc--collapsed': !descExpanded && descOverflow }">
              <div class="ced-desc-html" v-html="sanitizeHtml(entry.description)" />
            </div>
            <button v-if="descOverflow" class="ced-readmore" @click="descExpanded = !descExpanded">
              {{ descExpanded ? t('detail.read_less') : t('detail.read_more') }}
            </button>
          </div>

          <!-- Right: details, builds, requirements -->
          <div class="ced-col-right">

            <div class="ced-section-label">{{ t('detail.details') }}</div>
            <div class="ced-dlist">
              <template v-if="entry.release_date">
                <span class="ced-dk">{{ t('detail.released') }}</span>
                <span class="ced-dv">{{ formatDate(entry.release_date) }}</span>
              </template>
              <template v-if="totalSize">
                <span class="ced-dk">{{ t('detail.size') }}</span>
                <span class="ced-dv ced-mono">{{ totalSize }}</span>
              </template>
              <template v-if="entry.developer">
                <span class="ced-dk">{{ t('detail.developer') }}</span>
                <span class="ced-dv">{{ entry.developer }}</span>
              </template>
              <template v-if="entry.publisher && entry.publisher !== entry.developer">
                <span class="ced-dk">{{ t('detail.publisher') }}</span>
                <span class="ced-dv">{{ entry.publisher }}</span>
              </template>
              <template v-if="(entry.genres || []).length">
                <span class="ced-dk">{{ t('detail.genres') }}</span>
                <div class="ced-dv ced-tag-inline">
                  <span v-for="g in (entry.genres || [])" :key="g" class="ced-itag">{{ g }}</span>
                </div>
              </template>
              <template v-if="entryLangs.length">
                <span class="ced-dk">{{ t('detail.languages') }}</span>
                <div class="ced-dv ced-lang-flags">
                  <span v-for="l in entryLangs" :key="l.name" class="ced-lang-flag" :title="l.name">
                    <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span>
                    <span v-else>{{ l.name }}</span>
                  </span>
                </div>
              </template>
              <template v-if="entry.hltb_main_s || entry.hltb_complete_s">
                <span class="ced-dk">{{ t('detail.time_to_beat') }}</span>
                <span class="ced-dv" style="display:flex;flex-direction:column;gap:1px">
                  <span v-if="entry.hltb_main_s">{{ t('detail.hltb_main') }} {{ fmtHltb(entry.hltb_main_s) }}</span>
                  <span v-if="entry.hltb_complete_s">{{ t('detail.hltb_complete') }} {{ fmtHltb(entry.hltb_complete_s) }}</span>
                </span>
              </template>
              <template v-if="entry.category">
                <span class="ced-dk">{{ t('detail.category') }}</span>
                <span class="ced-dv">{{ entry.category }}</span>
              </template>
              <!-- Unguarded on purpose: the catalogue an entry came from is
                   the one fact that always exists, so the grid can never
                   render as an empty bordered box. -->
              <span class="ced-dk">{{ t('detail.source') }}</span>
              <span class="ced-dv">{{ storeName }}</span>

              <!-- Rows contributed by plugins through registerDetailRow. A
                   listing is PC-game metadata that becomes a Games entry once
                   pulled, so it resolves against the same 'games' library the
                   game page uses - otherwise every such plugin would go blank
                   the moment you looked at the store instead of the library. -->
              <template v-for="prow in pluginRows" :key="prow.id">
                <span v-if="prow.fullWidth" class="ced-dv" style="grid-column:1 / -1">
                  <PluginDetailValue :row="prow" :game="pluginGame" library="games" variant="dlist" />
                </span>
                <template v-else>
                  <span class="ced-dk">{{ prow.label }}</span>
                  <span class="ced-dv"><PluginDetailValue :row="prow" :game="pluginGame" library="games" variant="dlist" /></span>
                </template>
              </template>
            </div>

            <!-- ── Builds on offer ───────────────────────────────────────── -->
            <!-- Owning one build never meant the others stopped existing:
                 hiding the list left no way to add a second platform or to
                 fetch a build again, which a GOG game has always allowed. So
                 the gate is only "is there anything to offer" - never
                 "downloaded". With nothing on offer the header goes too: the
                 hero row is the one place that says why.
                 The list reads, it does not pick: choosing which builds to pull
                 belongs to the download dialog, the way a GOG game lists its
                 installers here and picks them there. -->
            <template v-if="entry.available && assets.length">
              <div class="ced-section-label" style="margin-top:28px">
                {{ entry.downloaded ? t('detail.builds_more') : t('detail.builds') }}
              </div>
              <div class="ced-builds">
                <div v-for="group in buildsByOs" :key="group.os" class="ced-build-group">
                  <div class="ced-build-os-head">{{ group.label }}</div>
                  <div v-for="a in group.entries" :key="a.name" class="ced-build-row">
                    <span class="ced-build-name">{{ a.name }}</span>
                    <span class="ced-build-meta">
                      <span v-if="a.arch" class="ced-build-arch">{{ a.arch }}</span>
                      <span v-if="a.size" class="ced-build-size">{{ fmtSize(a.size) }}</span>
                    </span>
                  </div>
                </div>
                <!-- Where the download lands, the way the GOG dialog names its
                     save location instead of leaving it a mystery. -->
                <div v-if="entry.save_root" class="ced-save-root">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="ced-mono">{{ entry.save_root }}</span>
                </div>
              </div>
            </template>

            <!-- Minimum requirements -->
            <template v-if="reqRows.length">
              <div class="ced-section-label" style="margin-top:28px">{{ t('detail.min_requirements') }}</div>
              <div class="ced-dlist">
                <template v-for="[k, v] in reqRows" :key="k">
                  <span class="ced-dk">{{ formatReqKey(k) }}</span>
                  <span class="ced-dv">{{ v }}</span>
                </template>
              </div>
            </template>

          </div>

        </div><!-- /ced-cols -->

        <!-- ── Admin: which match this listing got ──────────────────────── -->
        <!-- A wrong match is only fixable once it is visible, so the source and
             the title it matched sit next to the search term that produced it. -->
        <section v-if="isAdmin && hasMatchRows" class="ced-section ced-admin-section">
          <h2 class="ced-section-title">
            {{ t('detail.edit_metadata') }}
            <span class="ced-admin-badge">Admin</span>
          </h2>
          <div class="ced-dlist">
            <template v-if="entry.meta_source">
              <span class="ced-dk">{{ t('detail.source') }}</span>
              <span class="ced-dv">{{ entry.meta_source }}</span>
            </template>
            <template v-if="entry.meta_matched_title">
              <span class="ced-dk">{{ t('detail.also_known_as') }}</span>
              <span class="ced-dv ced-match-cell">
                {{ entry.meta_matched_title }}
                <span v-if="entry.meta_confidence" class="ced-itag" :class="{ 'ced-itag--warn': entry.meta_confidence === 'low' }">{{ entry.meta_confidence }}</span>
              </span>
            </template>
            <template v-if="entry.meta_search_term">
              <span class="ced-dk">{{ t('detail.search_term') }}</span>
              <span class="ced-dv ced-mono">{{ entry.meta_search_term }}</span>
            </template>
          </div>
        </section>

      </div>

    </template>

    <!-- ── Lightbox ────────────────────────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="lightboxIdx !== null" class="ced-lb" @click.self="lightboxIdx = null">
        <button class="ced-lb-close" @click="lightboxIdx = null">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <button v-if="lightboxIdx > 0" class="ced-lb-arrow ced-lb-arrow--l" @click="lightboxIdx--">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <img :src="screenshots[lightboxIdx]" class="ced-lb-img" />
        <button v-if="lightboxIdx < screenshots.length - 1" class="ced-lb-arrow ced-lb-arrow--r" @click="lightboxIdx++">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <div class="ced-lb-counter">{{ lightboxIdx + 1 }} / {{ screenshots.length }}</div>
      </div>
    </Teleport>

    <!-- ── Metadata editor ─────────────────────────────────────────────────── -->
    <!-- The same panel a GOG game gets, pointed at the catalog_entries row.
         The three endpoints behind that prefix were written for exactly this;
         nothing here needed a store-specific editor. -->
    <Teleport to="body">
      <LibraryMetadataPanel
        v-if="entry && showMetaPanel"
        :game="(entry as any)"
        api-prefix="/plugins/library/catalog-entries"
        @close="showMetaPanel = false"
        @saved="onMetadataSaved"
      />
    </Teleport>

    <!-- ── Download dialog ─────────────────────────────────────────────────── -->
    <!-- The same shape a GOG download gets: platform, builds, save location,
         then a footer that commits. -->
    <CatalogDownloadDialog
      v-if="entry"
      v-model="showDownload"
      :entry-id="entry.id"
      :title="entry.title"
      :assets="assets"
      :save-root="entry.save_root"
      @started="onDownloadStarted"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useLibrariesStore } from '@/stores/libraries'
import { useSocketStore } from '@/stores/socket'
import HeroBackground from '@/components/common/HeroBackground.vue'
import PluginDetailValue from '@/components/games/PluginDetailValue.vue'
import CatalogDownloadDialog from '@/components/games/CatalogDownloadDialog.vue'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import { resolveDetailRows } from '@/themes/index'
import { sanitizeHtml } from '@/utils/sanitize'
import { buildLanguageList } from '@/utils/langMap'
import { ratingVal } from '@/utils/rating'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const librariesStore = useLibrariesStore()
const socketStore = useSocketStore()

const isAdmin = computed(() => auth.user?.role === 'admin')

interface EntryAsset { name: string; os?: string; size?: number; arch?: string | null }

/** One row of GET /plugins/library/catalog-entries/{id}. Everything past `id`
 *  and `title` is optional: an entry that was never scraped carries little more
 *  than its name. */
interface Entry {
  id: number
  title: string
  subtitle?: string | null
  catalog_title?: string | null
  category?: string | null
  homepage?: string | null
  cover_path?: string | null
  background_path?: string | null
  logo_path?: string | null
  screenshots?: string[] | null
  description?: string | null
  developer?: string | null
  publisher?: string | null
  release_date?: string | null
  rating?: number | null
  genres?: string[] | null
  meta_ratings?: Record<string, number> | null
  languages?: Record<string, string> | null
  requirements?: Record<string, unknown> | null
  hltb_main_s?: number | null
  hltb_complete_s?: number | null
  available?: boolean
  unavailable_reason?: string | null
  assets?: EntryAsset[] | null
  release_tag?: string | null
  released_at?: string | null
  is_prerelease?: boolean
  save_root?: string | null
  downloaded?: boolean
  library_game_id?: number | null
  meta_source?: string | null
  meta_search_term?: string | null
  meta_matched_title?: string | null
  meta_confidence?: string | null
}

const entry = ref<Entry | null>(null)
const loading = ref(true)
const showDownload = ref(false)
// Set the instant a download is queued from this page; component-local, so it
// resets on navigation. It drives the transient "Downloading..." marker. The
// persistent server state (library_game_id set, no file yet) also describes a
// download that FAILED, which must read as on offer again - not as a spinner
// stuck forever - so the marker is not derived from that state.
const justQueued = ref(false)
const showMetaPanel = ref(false)
const scraping = ref(false)
const coverFailed = ref(false)

const bgSrc = computed(() => entry.value?.background_path || entry.value?.cover_path || '')
const assets = computed<EntryAsset[]>(() => entry.value?.assets || [])
const screenshots = computed<string[]>(() => entry.value?.screenshots || [])
const releaseYear = computed(() => (String(entry.value?.release_date || '').match(/(\d{4})/) || [])[1] || '')
const entryLangs = computed(() => buildLanguageList(entry.value?.languages))

// The library's REAL display name, from the registry. Title-casing the slug
// only ever produced "Pc Ports", and this name now stands in three places at
// once (back pill, hero badge, Source row). The de-slugified form survives as
// the last resort for a registry that has not loaded yet.
const storeName = computed(() => {
  const slug = String(route.params.slug || '')
  if (!slug) return t('nav.store')
  const lib = librariesStore.bySlug(slug)
  if (lib) return librariesStore.label(lib)
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
})

// Rows contributed by plugins via window.__GD__.registerDetailRow. Resolved
// against 'games' - see the note in the template.
const pluginRows = computed(() => (entry.value ? resolveDetailRows(entry.value as unknown as Record<string, unknown>, 'games') : []))
// PluginDetailValue requires a non-null game object; an entry is always the
// thing being described, so an empty object only ever stands in pre-load.
const pluginGame = computed<Record<string, unknown>>(() => (entry.value || {}) as unknown as Record<string, unknown>)

// The catalogue's own page for this listing, named by its host so the button
// carries no label that would need translating.
const homepageHost = computed(() => {
  const url = entry.value?.homepage
  if (!url) return ''
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return '' }
})

// ── Platforms ─────────────────────────────────────────────────────────────────

/** Collapse a build's free-form os string onto the three chips we can draw. */
function osKey(os?: string | null): string {
  const k = String(os || '').toLowerCase()
  if (!k) return ''
  if (k.includes('win')) return 'windows'
  if (k.includes('mac') || k.includes('osx') || k.includes('darwin')) return 'mac'
  if (k.includes('linux')) return 'linux'
  return k
}

function osLabel(os: string): string {
  if (os === 'windows') return 'Windows'
  if (os === 'mac') return 'macOS'
  if (os === 'linux') return 'Linux'
  return os
}

const assetOses = computed(() => {
  const seen: string[] = []
  for (const a of assets.value) {
    const k = osKey(a.os)
    if (k && !seen.includes(k)) seen.push(k)
  }
  const order = ['windows', 'mac', 'linux']
  return [...order.filter(o => seen.includes(o)), ...seen.filter(o => !order.includes(o))]
})

/** Builds grouped under the platform they are for, the way a GOG game lists
 *  its installers. A build marked for every platform - the catalogue's "all" -
 *  gets its own group rather than being repeated under each one, which is how
 *  it lands on disk too: in the title folder, not under an os. */
const buildsByOs = computed(() => {
  const groups = new Map<string, EntryAsset[]>()
  for (const a of assets.value) {
    const k = osKey(a.os) || 'all'
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(a)
  }
  const order = ['windows', 'mac', 'linux', 'all']
  const keys = [
    ...order.filter(o => groups.has(o)),
    ...Array.from(groups.keys()).filter(o => !order.includes(o)),
  ]
  return keys.map(os => ({
    os,
    label: os === 'all' ? t('detail.dl_any_os') : osLabel(os),
    entries: groups.get(os)!,
  }))
})

// ── External ratings ──────────────────────────────────────────────────────────

const externalRatings = computed(() => ({
  rawg: entry.value?.meta_ratings?.['rawg'] ?? undefined,
  igdb: entry.value?.meta_ratings?.['igdb'] ?? undefined,
  steam: entry.value?.meta_ratings?.['steam'] ?? undefined,
}))

// meta_ratings is keyed by provider id ("ppe"), which is not what the provider
// calls itself ("PPE.pl"). Ask the plugins for their own names and fall back to
// the shouted id when the list cannot be read.
const providerNames = ref<Record<string, string>>({})

const pluginRatings = computed(() => {
  const out: { id: string; name: string; rating: number; logo: string }[] = []
  for (const [k, v] of Object.entries(entry.value?.meta_ratings || {})) {
    if (k === 'rawg' || k === 'igdb' || k === 'steam') continue
    if (!ratingVal(v)) continue
    out.push({
      id: k,
      name: providerNames.value[k] || k.toUpperCase(),
      rating: ratingVal(v),
      logo: `/api/plugins/${k}-metadata/logo`,
    })
  }
  return out
})

async function loadProviderNames() {
  try {
    const { data } = await client.get('/plugins/metadata/providers')
    if (!Array.isArray(data)) return
    const out: Record<string, string> = {}
    for (const p of data) if (p?.id && p?.name) out[p.id] = p.name
    providerNames.value = out
  } catch { /* no read access to plugins: the id stands in */ }
}

function hideImg(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

// ── Details grid ──────────────────────────────────────────────────────────────

const hasMatchRows = computed(() => !!(
  entry.value?.meta_source || entry.value?.meta_matched_title || entry.value?.meta_search_term
))

const totalSize = computed(() => {
  const bytes = assets.value.reduce((n, a) => n + (a.size ?? 0), 0)
  return bytes ? fmtSize(bytes) : ''
})

function fmtSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 ** 3) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 ** 3).toFixed(2) + ' GB'
}

function fmtHltb(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

// release_date is free-form on an entry (a catalogue may store "2019" or a full
// ISO date), so anything Date cannot parse is printed as it arrived.
function formatDate(raw: string): string {
  const d = new Date(raw)
  if (!isNaN(d.getTime())) {
    const loc = localStorage.getItem('gd3_locale') || navigator.language || 'en'
    return d.toLocaleDateString(loc, { year: 'numeric', month: 'long', day: 'numeric' })
  }
  return raw.length <= 10 ? raw : raw.slice(0, 10)
}

// ── Requirements ──────────────────────────────────────────────────────────────

const REQ_SHOW = new Set(['processor', 'cpu', 'memory', 'ram', 'graphics', 'gpu', 'video', 'os', 'storage', 'directx'])

function formatReqKey(k: string): string {
  const key = k.toLowerCase()
  if (['processor', 'cpu'].includes(key))         return 'CPU'
  if (['memory', 'ram'].includes(key))            return 'RAM'
  if (['graphics', 'gpu', 'video'].includes(key)) return 'GPU'
  if (key === 'os')                               return 'OS'
  if (key === 'storage')                          return 'Storage'
  if (key === 'directx')                          return 'DirectX'
  return k
}

const reqRows = computed((): [string, string][] => {
  const reqs = entry.value?.requirements as Record<string, any> | null | undefined
  if (!reqs) return []
  const minimum: any =
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

// ── Carousel, lightbox, description ───────────────────────────────────────────

const carouselEl = ref<HTMLElement | null>(null)
const carouselIdx = ref(0)
const lightboxIdx = ref<number | null>(null)
const descExpanded = ref(false)
const descOverflow = ref(false)

// How many slides are visible at once. The clamp below, the right arrow's
// disabled test, the dot count and the slide's flex-basis all read this one
// value (the width via a CSS custom property on the strip), so they can no
// longer drift apart. Three up on a 375px phone left ~100px thumbnails.
function slidesPerView(): number {
  const w = typeof window === 'undefined' ? 1200 : window.innerWidth
  if (w <= 600) return 1
  if (w <= 900) return 2
  return 3
}
const perView = ref(slidesPerView())

/** One dot per reachable scroll position, not per screenshot. */
const dotCount = computed(() => Math.max(1, screenshots.value.length - perView.value + 1))

function onViewportResize() {
  const next = slidesPerView()
  if (next === perView.value) return
  perView.value = next
  slideTo(carouselIdx.value)   // re-clamp: fewer positions exist at 1-up
}

function slideTo(idx: number) {
  const max = Math.max(0, screenshots.value.length - perView.value)
  carouselIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = carouselEl.value
    if (!el) return
    const child = el.children[carouselIdx.value] as HTMLElement
    if (child) el.scrollTo({ left: child.offsetLeft - 2, behavior: 'smooth' })
  })
}

// ── 3D tilt effect ────────────────────────────────────────────────────────────

const coverTilt = ref('perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)')
const sheenStyle = ref('')

function onCoverMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.width / 2
  const cy = rect.height / 2
  const dx = e.clientX - rect.left - cx
  const dy = e.clientY - rect.top - cy
  const rotY = (dx / cx) * 10
  const rotX = -(dy / cy) * 7
  coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
  const mx = ((e.clientX - rect.left) / rect.width * 100).toFixed(1)
  const my = ((e.clientY - rect.top) / rect.height * 100).toFixed(1)
  sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
}

function onCoverLeave() {
  coverTilt.value = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
  sheenStyle.value = 'opacity:0;'
}

/** Is the description long enough to be worth collapsing? Measured on the TEXT
 *  the reader sees, not the markup: a short blurb wrapped in heavy HTML used to
 *  earn a "Read more" that revealed almost nothing. */
function isLongDescription(html?: string | null): boolean {
  if (!html) return false
  return sanitizeHtml(html).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().length > 600
}

// ── Load / actions ────────────────────────────────────────────────────────────

async function load() {
  loading.value = true
  try {
    const { data } = await client.get(`/plugins/library/catalog-entries/${route.params.id}`)
    entry.value = data
    coverFailed.value = false
    carouselIdx.value = 0
    descExpanded.value = false
    descOverflow.value = isLongDescription(data.description)
  } catch { entry.value = null }
  finally { loading.value = false }
}

/** The dialog owns the choice of builds and the queuing; the page only opens
 *  it, the way the GOG detail hands off to its own download dialog. */
function download() {
  if (!entry.value) return
  showDownload.value = true
}

/** Re-read rather than flip a local flag: `downloaded` and `library_game_id`
 *  are the server's to decide, and the page's badge and buttons follow them. */
async function onDownloadStarted() {
  justQueued.value = true
  await load()
}

// A catalogue build landing on the server (or failing) flips this page without a
// manual refresh, the way the download tray already updates. Match on the game
// the entry became; a url upload for some other game is ignored.
let unsubDownload: (() => void) | null = null
function onCatalogDownloadEvent(kind: string, data: Record<string, unknown>) {
  if (kind === 'progress') return
  const gid = entry.value?.library_game_id
  if (gid != null && data.game_id === gid) {
    justQueued.value = false
    load()
  }
}

/** The save already pushed the new presentation onto the downloaded game
 *  server-side; this only brings the page itself back in step. */
async function onMetadataSaved() {
  showMetaPanel.value = false
  await load()
}

async function refreshMeta() {
  if (!entry.value || scraping.value) return
  scraping.value = true
  try { await client.post(`/plugins/library/catalog-entries/${entry.value.id}/scrape-metadata`); await load() }
  catch { /* ignore */ }
  finally { scraping.value = false }
}

function openGame() {
  if (entry.value?.library_game_id) router.push(`/games/${entry.value.library_game_id}`)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push(`/lib/${route.params.slug}`)
}

onMounted(() => {
  load()
  loadProviderNames()
  // The registry carries this store's display name; a deep link can land here
  // before anything else has fetched it.
  if (!librariesStore.loaded) librariesStore.fetch()
  window.addEventListener('resize', onViewportResize)
  unsubDownload = socketStore.onUrlUpload(onCatalogDownloadEvent)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewportResize)
  if (unsubDownload) { unsubDownload(); unsubDownload = null }
})
// Moving between two offers keeps this component mounted and only swaps the
// route parameter, so loading once on mount left every pick showing whichever
// entry happened to open first. Classic reaches the page that way for its whole
// catalogue, since its list sits beside the page rather than above it.
watch(() => route.params.id, (id, prev) => { if (id && id !== prev) load() })
</script>

<style scoped>
/* ══ ROOT ══════════════════════════════════════════════════════════════════════ */
.ced-root {
  display: flex; flex-direction: column;
  background: transparent;
  width: 100%; min-height: 100%;
  overflow-x: hidden;
  color: var(--text);
}

/* ══ SKELETON ══════════════════════════════════════════════════════════════════ */
.ced-sk-hero {
  height: 420px;
  background: linear-gradient(90deg, var(--bg2) 25%, var(--bg3) 50%, var(--bg2) 75%);
  background-size: 400% 100%; animation: ced-shimmer 1.4s ease infinite;
}
.ced-sk-body { padding: 36px 40px; display: flex; flex-direction: column; gap: var(--space-4, 16px); }
.ced-sk-line {
  height: 16px; border-radius: 6px;
  background: linear-gradient(90deg, var(--bg2) 25%, var(--bg3) 50%, var(--bg2) 75%);
  background-size: 400% 100%; animation: ced-shimmer 1.4s ease infinite;
}
.ced-sk-line--xl { width: 70%; height: 32px; }
.ced-sk-line--lg { width: 55%; }
.ced-sk-line--md { width: 42%; }
.ced-sk-line--sm { width: 28%; }
@keyframes ced-shimmer { to { background-position: -400% 0; } }

/* ══ EMPTY ═════════════════════════════════════════════════════════════════════ */
.ced-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 14px; color: var(--muted); font-size: var(--fs-md, 14px);
}
.ced-empty .ced-back-pill { position: static; }

/* ══ BACK PILL ═════════════════════════════════════════════════════════════════ */
.ced-back-pill {
  position: fixed; top: 130px; left: 20px; z-index: 200;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 14px 7px 10px; border-radius: 20px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(0,0,0,.42); backdrop-filter: blur(8px);
  color: rgba(255,255,255,.85);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.ced-back-pill:hover { background: rgba(0,0,0,.65); border-color: rgba(255,255,255,.35); color: #fff; }

/* ══ HERO ══════════════════════════════════════════════════════════════════════ */
.ced-hero {
  position: relative;
  min-height: 420px;
  display: flex; align-items: flex-end; justify-content: center;
  overflow: hidden; flex-shrink: 0;
}
.ced-hero-inner {
  position: relative; z-index: 2;
  display: flex; align-items: flex-end; gap: var(--space-10, 40px);
  padding: 60px 44px 40px; width: 100%;
  max-width: 1140px; margin: 0 auto;
}

/* ══ COVER ═════════════════════════════════════════════════════════════════════ */
.ced-cover-col { flex-shrink: 0; }
.ced-cover-frame {
  position: relative;
  width: 360px; aspect-ratio: 3/4;
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,.85), 0 0 0 1px rgba(255,255,255,.09);
  transition: transform .35s cubic-bezier(.23,1,.32,1), box-shadow .35s ease;
  cursor: default;
}
.ced-cover-frame:hover {
  box-shadow: 0 28px 70px rgba(0,0,0,.9), 0 0 0 1px rgba(255,255,255,.15), 0 0 40px var(--pglow2);
}
.ced-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ced-cover-empty {
  width: 100%; height: 100%; background: rgba(255,255,255,.04);
  display: flex; align-items: center; justify-content: center;
}
.ced-cover-sheen {
  position: absolute; inset: 0; border-radius: inherit;
  pointer-events: none; opacity: 0; transition: opacity .3s;
}

/* ══ INFO COL ══════════════════════════════════════════════════════════════════ */
.ced-info-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 13px; }

.ced-logo-img {
  max-width: min(460px, 100%); max-height: 140px;
  object-fit: contain; object-position: left center;
  filter: drop-shadow(0 2px 18px rgba(0,0,0,.75));
}
.ced-title {
  font-size: clamp(26px, 4vw, 46px);
  font-weight: 900; color: #fff; margin: 0;
  line-height: 1.08; text-shadow: 0 2px 30px rgba(0,0,0,.7); letter-spacing: -.5px;
}
/* Which build this is, under the listing's name. Deliberately quiet: it
   qualifies the title, it does not compete with it. */
.ced-subtitle {
  font-size: clamp(13px, 1.4vw, 17px); font-weight: 600;
  color: rgba(255,255,255,.72); margin-top: 6px;
  text-shadow: 0 2px 18px rgba(0,0,0,.7); letter-spacing: .2px;
}

.ced-badge-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
/* This badge is always the store's name - the primary case - so it takes the
   skin's accent, the way a game page tints its GOG badge. The fixed teal it
   used to carry is the model's FALLBACK colour and never belonged here. */
.ced-source-badge {
  display: inline-block; font-size: var(--fs-xs, 10px); font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  letter-spacing: .5px; text-transform: uppercase;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  color: var(--pl-light);
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
}
.ced-owned-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--fs-xs, 10px); font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  letter-spacing: .5px; text-transform: uppercase;
  background: rgba(74,222,128,.12); color: #4ade80; border: 1px solid rgba(74,222,128,.28);
}
.ced-ver-chip {
  font-size: var(--fs-xs, 10px); font-weight: 600;
  padding: 2px 8px; border-radius: 10px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14);
  color: rgba(255,255,255,.6); font-family: monospace;
}
.ced-ver-chip--warn {
  background: rgba(251,191,36,.12); border-color: rgba(251,191,36,.35); color: #fbbf24;
  font-family: inherit; text-transform: uppercase; letter-spacing: .5px;
}

.ced-meta-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  font-size: var(--fs-md, 14px); color: rgba(255,255,255,.58); font-weight: 500;
}
.ced-meta-sep { opacity: .3; }

.ced-rating-row { display: flex; align-items: center; gap: 3px; }
.ced-rating-num { font-size: 15px; font-weight: 700; color: #f59e0b; margin-left: 6px; }

/* ══ EXTERNAL RATINGS ══════════════════════════════════════════════════════════ */
.ced-ext-ratings { display: flex; gap: 10px; flex-wrap: wrap; }
.ced-ext-score {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
}
/* The provider .ico files are low-res; smoothing them looks like a mistake. */
.ced-ext-ico { flex-shrink: 0; image-rendering: pixelated; border-radius: 6px; }
.ced-ext-info { display: flex; flex-direction: column; gap: 2px; }
.ced-ext-val { font-size: var(--fs-lg, 16px); font-weight: 800; color: #fff; line-height: 1; }
.ced-ext-max { font-size: var(--fs-xs, 10px); color: var(--muted); font-weight: 500; }
.ced-ext-lbl {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px;
}

/* ══ TAGS / GENRES / OS ════════════════════════════════════════════════════════ */
.ced-tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.ced-genre-tag {
  padding: 4px 12px; border-radius: 20px; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: rgba(167,139,250,.16); border: 1px solid rgba(167,139,250,.35); color: #c4b5fd;
}
.ced-os-row { display: flex; gap: var(--space-2, 8px); flex-wrap: wrap; }
.ced-os-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14);
  color: rgba(255,255,255,.7); font-size: var(--fs-sm, 12px); font-weight: 600;
  transition: all .15s;
}
.ced-os-chip:hover { background: rgba(255,255,255,.12); color: #fff; }

/* ══ ACTIONS ═══════════════════════════════════════════════════════════════════ */
.ced-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; align-items: center; }
.ced-btn-dl {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 11px 24px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  font-size: var(--fs-md, 14px); font-weight: 700; font-family: inherit;
  text-decoration: none; cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 18px var(--pglow2);
}
.ced-btn-dl:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 35%, transparent); border-color: var(--pl); color: #fff; transform: translateY(-1px); }
.ced-btn-dl:disabled { opacity: .4; cursor: not-allowed; }

.ced-btn-ghost {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.16);
  color: rgba(255,255,255,.68); font-size: 13px; font-weight: 600; font-family: inherit;
  text-decoration: none; cursor: pointer; transition: all .15s; backdrop-filter: blur(6px);
}
.ced-btn-ghost:not(:disabled):hover { background: rgba(255,255,255,.13); color: #fff; border-color: rgba(255,255,255,.3); }
.ced-btn-ghost:disabled { opacity: .5; cursor: not-allowed; }

.ced-btn-count {
  font-size: 11px; font-weight: 400; opacity: .75;
  background: rgba(255,255,255,.15); padding: 1px 7px; border-radius: 10px;
}
.ced-no-files { font-size: var(--fs-sm, 12px); color: var(--muted); font-style: italic; }
.ced-msg { font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.72); }

.ced-spinner {
  width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor; border-radius: 50%;
  animation: ced-spin .7s linear infinite; display: inline-block; flex-shrink: 0;
}
.ced-spin { animation: ced-spin .8s linear infinite; }
@keyframes ced-spin { to { transform: rotate(360deg); } }

/* ══ SEPARATOR ═════════════════════════════════════════════════════════════════ */
.ced-separator {
  width: 100%; height: 80px; margin-top: -80px;
  background: linear-gradient(to bottom, transparent, var(--bg1, rgba(8,7,18,1)));
  pointer-events: none; flex-shrink: 0;
  position: relative; z-index: 0;
}

/* ══ BODY ══════════════════════════════════════════════════════════════════════ */
.ced-body {
  flex: 1; max-width: 1140px; width: 100%; margin: 0 auto;
  padding: 40px 44px 70px; display: flex; flex-direction: column; gap: 44px;
}
.ced-section { display: flex; flex-direction: column; gap: 14px; }
.ced-section-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px; margin-bottom: 16px;
}
.ced-section-title {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.4px; margin: 0 0 4px;
  display: flex; align-items: center; gap: var(--space-2, 8px);
}
.ced-admin-badge {
  font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 10px;
  background: rgba(239,68,68,.2); color: #f87171; border: 1px solid rgba(239,68,68,.3);
  text-transform: uppercase; letter-spacing: .5px;
}

/* ══ MEDIA / CAROUSEL ══════════════════════════════════════════════════════════ */
/* Own horizontal padding on top of .ced-body's, so the -20px arrows do not clip. */
.ced-media-section {
  display: flex; flex-direction: column; gap: var(--space-6, 24px);
  padding: 0 24px;
}
.ced-carousel-wrap { position: relative; display: flex; align-items: center; }
.ced-carousel {
  flex: 1; display: flex; gap: var(--space-3, 12px);
  overflow-x: auto; overflow-y: hidden;
  scroll-snap-type: x mandatory; scroll-behavior: smooth;
  scrollbar-width: none; -webkit-overflow-scrolling: touch;
  padding: 4px 2px 8px;
}
.ced-carousel::-webkit-scrollbar { display: none; }
/* Width follows --ced-per-view, which slidesPerView() sets on the strip: the
   gaps are (n - 1) x 12px. slideTo(), the dot count and the right arrow's
   disabled test read the same number, so the three can no longer disagree. */
.ced-slide {
  flex: 0 0 calc((100% - (var(--ced-per-view, 3) - 1) * 12px) / var(--ced-per-view, 3));
  aspect-ratio: 16/9; border-radius: 10px; overflow: hidden; cursor: pointer;
  scroll-snap-align: start; border: 1px solid rgba(255,255,255,.08);
  transition: border-color .2s, box-shadow .2s, transform .2s;
  background: var(--bg2); position: relative;
}
.ced-slide > img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform .3s ease;
}
.ced-slide:hover { border-color: var(--pl); box-shadow: 0 0 24px var(--pglow2); transform: translateY(-2px); }
.ced-slide:hover > img { transform: scale(1.04); }
.ced-slide--active { border-color: rgba(255,255,255,.18); }
.ced-carr-btn {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 46px; height: 46px; border-radius: 50%; z-index: 2;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.62); border: 1px solid rgba(255,255,255,.22);
  color: #fff; cursor: pointer; transition: all .15s;
  backdrop-filter: blur(8px);
}
.ced-carr-btn:not(:disabled):hover { background: rgba(0,0,0,.88); border-color: rgba(255,255,255,.5); }
/* Arrows vanish rather than grey out - with two screenshots there is nowhere
   to go and a dimmed control only invites a click. */
.ced-carr-btn:disabled { opacity: 0; pointer-events: none; }
.ced-carr-btn--left { left: -20px; }
.ced-carr-btn--right { right: -20px; }
.ced-dots { display: flex; justify-content: center; gap: 6px; padding-top: 14px; }
.ced-dot-item {
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,.18); cursor: pointer; transition: all .22s;
}
.ced-dot-item.active { background: color-mix(in srgb, var(--pl) 30%, transparent); width: 22px; border-radius: 3px; }

/* ══ TWO COLUMNS ═══════════════════════════════════════════════════════════════ */
.ced-cols { display: grid; grid-template-columns: 1fr 340px; gap: 52px; align-items: start; }
/* Nothing to describe: the facts column stands alone, capped so a details
   table and a build list do not stretch across the full 1140px. */
.ced-cols--single { grid-template-columns: minmax(0, 620px); }
@media (max-width: 900px) { .ced-cols, .ced-cols--single { grid-template-columns: 1fr; } }

/* ══ DESCRIPTION ═══════════════════════════════════════════════════════════════ */
.ced-desc-wrap {
  font-size: var(--fs-md, 14px); line-height: 1.85; color: rgba(255,255,255,.72);
  overflow: hidden;
}
.ced-desc--collapsed {
  max-height: 9em;
  mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
}
/* :deep() is required: the description arrives through v-html, so its nodes are
   not stamped with this component's scope attribute. */
.ced-desc-html :deep(h1),
.ced-desc-html :deep(h2),
.ced-desc-html :deep(h3) { font-size: 15px; font-weight: 700; margin: 14px 0 7px; color: var(--text); }
.ced-desc-html :deep(p)  { margin: 0 0 10px; }
.ced-desc-html :deep(ul),
.ced-desc-html :deep(ol) { padding-left: 20px; margin: 6px 0; }
.ced-desc-html :deep(a)  { color: var(--pl-light); }
.ced-desc-html :deep(img) { max-width: 100%; height: auto; border-radius: 6px; display: block; margin: 8px 0; }
.ced-readmore {
  margin-top: 12px; background: none; border: none;
  color: var(--pl-light); font-size: var(--fs-sm, 12px); font-weight: 600;
  font-family: inherit; cursor: pointer; padding: 0; opacity: .85;
}
.ced-readmore:hover { opacity: 1; }

/* ══ DETAILS LIST ══════════════════════════════════════════════════════════════ */
/* Two-column grid with the row borders faked per cell: each row is a bare pair
   of siblings, so no wrapper element is needed. */
.ced-dlist {
  display: grid; grid-template-columns: auto 1fr; gap: 0;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 6px); overflow: hidden;
}
.ced-dk, .ced-dv { padding: 10px 14px; font-size: 13px; }
.ced-dk {
  color: var(--muted); font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px; white-space: nowrap;
  border-right: 1px solid var(--glass-border);
  border-bottom: 1px solid var(--glass-border);
  background: rgba(255,255,255,.02);
}
.ced-dv { color: var(--text); min-width: 0; overflow-wrap: anywhere; }
.ced-dk + .ced-dv { border-bottom: 1px solid var(--glass-border); }
/* The last ROW loses its bottom border so it does not double against the
   container's. Counted from the end in pairs: `.ced-dk:last-of-type` matched
   nothing, because the final span in the grid is always a value, never a key. */
.ced-dlist > :nth-last-child(-n+2) { border-bottom: none; }
.ced-mono { font-family: monospace; font-size: var(--fs-sm, 12px); }
.ced-match-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.ced-tag-inline { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); }
.ced-itag {
  padding: 2px 9px; border-radius: var(--radius-xs, 4px); font-size: 11px; font-weight: 600;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: rgba(255,255,255,.58);
}
.ced-itag--warn { background: rgba(251,191,36,.12); border-color: rgba(251,191,36,.35); color: #fbbf24; }
.ced-lang-flags { display: flex; flex-wrap: wrap; gap: var(--space-1, 4px); }
.ced-lang-flag {
  display: inline-flex; align-items: center;
  font-size: 20px; line-height: 1; cursor: default;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,.3));
  transition: transform .12s;
}
.ced-lang-flag .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.ced-lang-flag:hover { transform: scale(1.25); }

/* ══ BUILDS ════════════════════════════════════════════════════════════════════ */
.ced-builds { display: flex; flex-direction: column; gap: 10px; }
.ced-build-group { display: flex; flex-direction: column; gap: 4px; }
.ced-build-os-head {
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 2px;
}
.ced-build-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 9px 14px; border-radius: var(--radius-sm, 6px);
  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07);
}
.ced-build-name { font-size: 13px; color: var(--text); overflow-wrap: anywhere; min-width: 0; }
.ced-build-meta { display: flex; align-items: center; gap: var(--space-2, 8px); flex-shrink: 0; }
.ced-build-arch {
  font-size: var(--fs-xs, 10px); color: var(--muted); padding: 2px 7px;
  border-radius: var(--radius-xs, 4px); background: rgba(255,255,255,.06);
}
.ced-build-size { font-size: var(--fs-sm, 12px); color: var(--muted); font-weight: 500; white-space: nowrap; }
.ced-save-root {
  display: flex; align-items: center; gap: 6px; margin-top: 4px;
  font-size: var(--fs-xs, 10px); color: var(--muted); overflow-wrap: anywhere;
}
.ced-save-root svg { flex-shrink: 0; }

/* ══ ADMIN ═════════════════════════════════════════════════════════════════════ */
.ced-admin-section { border: 1px solid rgba(239,68,68,.15); border-radius: 10px; padding: var(--space-5, 20px); }

/* ══ LIGHTBOX ══════════════════════════════════════════════════════════════════ */
.ced-lb {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.94);
  display: flex; align-items: center; justify-content: center;
  animation: ced-lb-in .15s ease;
}
@keyframes ced-lb-in { from { opacity: 0; } to { opacity: 1; } }
.ced-lb-img {
  max-width: 90vw; max-height: 86vh;
  border-radius: var(--radius-sm, 8px); box-shadow: 0 0 80px rgba(0,0,0,.9);
  object-fit: contain;
}
.ced-lb-close, .ced-lb-arrow {
  position: fixed;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.18);
  border-radius: var(--radius-sm, 8px); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s; padding: 10px;
}
.ced-lb-close { top: 16px; right: 16px; }
.ced-lb-arrow--l { left: 16px; top: 50%; transform: translateY(-50%); }
.ced-lb-arrow--r { right: 16px; top: 50%; transform: translateY(-50%); }
.ced-lb-close:hover, .ced-lb-arrow:hover { background: rgba(255,255,255,.22); }
.ced-lb-counter {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.48); font-weight: 600;
  background: rgba(0,0,0,.4); padding: 4px 14px; border-radius: 20px;
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .ced-hero-inner { flex-direction: column; align-items: center; gap: var(--space-4, 16px); padding: 24px 16px 20px; }
  .ced-cover-frame { width: clamp(160px, 50vw, 240px); }
  .ced-cover-col { align-items: center; }
  .ced-info-col { align-items: center; text-align: center; }
  .ced-badge-row, .ced-ext-ratings, .ced-tag-row, .ced-os-row, .ced-actions { justify-content: center; }
  .ced-body { padding: 20px 16px 40px; }
  .ced-cols { gap: var(--space-5, 20px); }
  /* Stays TWO columns. The rows are bare key/value sibling pairs with no row
     wrapper, so a third track made auto-placement deal them [key, value, key]
     then [value, key, value] - every pair scrambled and every faked cell
     border drawn in the wrong place. */
  .ced-dlist { grid-template-columns: auto 1fr; font-size: var(--fs-sm, 12px); }
}
</style>
