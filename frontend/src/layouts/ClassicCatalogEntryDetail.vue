<template>
  <div class="cd-wrap">

    <!-- Loading -->
    <div v-if="loading" class="cd-loading">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="cd-spin" style="opacity:.4">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </div>

    <!-- Not found. A failed load never throws at the reader, so this is also
         where a deleted or forbidden entry lands. -->
    <div v-else-if="!entry" class="cd-empty">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.18">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
      <div class="cd-empty-text">{{ t('detail.game_not_found') }}</div>
      <button class="cea-btn cea-btn--ghost" @click="goBack">{{ t('detail.back_to_library') }}</button>
    </div>

    <!-- Entry content -->
    <template v-else>

      <!-- ── COVER HERO ─────────────────────────────────────────────────────── -->
      <div class="cover-hero">
        <!-- Hero background (toggled by Settings -> Classic Layout -> Hero Background) -->
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
            v-if="entry.cover_path && !coverFailed"
            :src="entry.cover_path"
            class="cover-img"
            :class="{ 'cover-img--nat': coverIsSquarish }"
            :alt="entry.title"
            @load="onCoverLoad"
            @error="coverFailed = true"
          />
          <div v-else class="cover-ph">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.3">
              <rect x="2" y="6" width="20" height="12" rx="2"/>
              <circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/>
            </svg>
          </div>
          <!-- Specular sheen (respects themeStore.cardShine) -->
          <div v-if="themeStore.cardShine" class="cover-sheen" :style="sheenStyle" />
          <!-- Hover overlay, the way ClassicGameDetail does it: every action on
               this page is a round button on the cover. There is no "open in
               Games" among them - in this skin the game is one click away in
               the sidebar, so the shortcut earned nothing, and downloading is
               the only thing the store page is for. With one action left there
               is no hierarchy to express, which is what had forced these out
               into a row of their own. -->
          <div class="cover-overlay">
            <button v-if="entry.available && assets.length" class="cov-btn" :title="t('detail.download')" @click="showDownload = true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <a v-if="homepageHost" class="cov-btn" :href="entry.homepage || undefined" target="_blank" rel="noopener noreferrer" :title="homepageHost">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
            <button v-if="isAdmin" class="cov-btn" @click="showMetaPanel = true" :title="t('detail.edit_metadata')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button v-if="isAdmin" class="cov-btn" :class="{ 'cov-btn--spin': scraping }" :disabled="scraping" @click="refreshMeta" :title="scraping ? t('detail.scraping') : t('detail.refresh_metadata')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
            <!-- No standalone "search term": every editor tab has its own
                 "title to search" field, so a wrong match is fixed there. -->
          </div>
        </div>

        <!-- Catalogue logo / text title fallback -->
        <img
          v-if="entry.logo_path && !logoFailed"
          :src="entry.logo_path"
          :alt="entry.title"
          class="game-logo"
          @error="logoFailed = true"
        />
        <div v-else class="game-title">{{ entry.title }}</div>
        <!-- Which build this is stays worth saying even when a logo replaces
             the title, so it hangs off the entry, not off the fallback. -->
        <div v-if="entry.subtitle" class="game-subtitle">{{ entry.subtitle }}</div>

        <!-- Ratings. The listing's own 0-5 mark leads; then each source on its
             own scale. There is no blended rating_agg here and no GOG chip: a
             copied RAWG or IGDB score under either mark would invent a rating
             this listing never had. -->
        <div v-if="hasRatings" class="cover-ratings">
          <div v-if="ratingVal(entry.rating) > 0" class="crating">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#facc15"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            <span>{{ ratingVal(entry.rating).toFixed(1) }}<small>/5</small></span>
          </div>
          <div v-if="externalRatings.rawg" class="crating">
            <img src="/icons/RAWG.ico" class="crating-ico" title="RAWG" />
            <span>{{ ratingVal(externalRatings.rawg).toFixed(1) }}<small>/5</small></span>
          </div>
          <div v-if="externalRatings.igdb" class="crating">
            <img src="/icons/igdb.ico" class="crating-ico" title="IGDB" />
            <span>{{ Math.round(ratingVal(externalRatings.igdb)) }}<small>/100</small></span>
          </div>
          <div v-if="externalRatings.steam" class="crating">
            <img src="/icons/metacritic.svg" class="crating-ico" title="Metacritic" />
            <span>{{ Math.round(ratingVal(externalRatings.steam) * 10) }}<small>/100</small></span>
          </div>
          <div v-for="pr in pluginRatings" :key="pr.id" class="crating">
            <img :src="pr.logo" class="crating-ico" :title="pr.name" @error="hideImg" />
            <span>{{ pr.rating.toFixed(1) }}<small>/10</small></span>
          </div>
        </div>

        <!-- Chips: the catalogue, ownership, the year, and the version facts.
             Version facts are data, so they read as chips rather than as
             labelled rows nothing else in this layout would match. -->
        <div class="meta-chips">
          <div class="chip chip--store"><span>{{ storeName }}</span></div>
          <div v-if="entry.downloaded" class="chip chip--owned">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            <span>{{ t('detail.in_library') }}</span>
          </div>
          <div v-if="releaseYear" class="chip">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span>{{ releaseYear }}</span>
          </div>
          <div v-if="entry.release_tag" class="chip chip--ver"><span>{{ entry.release_tag }}</span></div>
          <div v-if="entry.is_prerelease" class="chip chip--warn"><span>{{ t('detail.pre_release') }}</span></div>
        </div>

        <!-- A listing that offers nothing still owes the reader a reason, and
             unavailable_reason is the only one there is. Nothing else lives
             here: the actions are on the cover. -->
        <div v-if="!entry.available || !assets.length" class="cea-no-files">
          {{ !entry.available ? (entry.unavailable_reason || t('detail.unavailable')) : t('detail.no_files') }}
        </div>
      </div>

      <!-- ── MEDIA STRIP ─────────────────────────────────────────────────────── -->
      <!-- Four visible at a time, like the game page. An entry carries no video,
           so there is no leading slide and no index offset. -->
      <div v-if="screenshots.length" class="shots-wrap">
        <button class="shots-nav" :disabled="slideIdx === 0" @click="slideTo(slideIdx - 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>

        <div class="shots-strip" ref="stripEl">
          <div v-for="(shot, i) in screenshots" :key="i" class="shot-item" @click="lightboxIdx = i">
            <img :src="shot" class="shot-thumb-img" loading="lazy"
              @error="(e) => (e.target as HTMLImageElement).parentElement!.style.display='none'" />
          </div>
        </div>

        <button class="shots-nav" :disabled="screenshots.length <= 4 || slideIdx >= screenshots.length - 4" @click="slideTo(slideIdx + 1)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>

      <!-- ── INFO CARDS ──────────────────────────────────────────────────────── -->
      <!-- Every card here is conditional, so the column count follows the cards
           that actually exist. A fixed three-column grid left a visible hole
           beside a listing that was never scraped, which is the common case in
           a store. -->
      <div class="info-cards" :style="{ gridTemplateColumns: `repeat(${Math.min(cardCount, 3)}, 1fr)` }">

        <!-- Card: developer / publisher / genres / plugin rows -->
        <div v-if="showCredits" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            <span>{{ t('detail.developer') }} &amp; {{ t('detail.publisher') }}</span>
          </div>
          <!-- No "-" fallbacks: on an entry the missing half is the norm, and a
               wall of dashes is what makes a store page look broken. -->
          <div v-if="entry.developer" class="icard-row"><span class="icard-label">{{ t('detail.developer') }}: </span><span class="icard-val">{{ entry.developer }}</span></div>
          <div v-if="entry.publisher" class="icard-row"><span class="icard-label">{{ t('detail.publisher') }}: </span><span class="icard-val">{{ entry.publisher }}</span></div>
          <template v-if="(entry.genres || []).length">
            <div class="icard-head" style="margin-top:10px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
              <span>{{ t('detail.genres') }}</span>
            </div>
            <div class="genre-tags">
              <span v-for="g in (entry.genres || [])" :key="g" class="genre-tag">{{ g }}</span>
            </div>
          </template>
          <!-- Rows contributed by plugins through registerDetailRow. A listing
               is PC-game metadata that becomes a Games entry once pulled, so it
               resolves against the same 'games' library the game page uses -
               otherwise every such plugin would go blank the moment you looked
               at the store instead of the library. -->
          <div v-for="prow in pluginRows" :key="prow.id" class="icard-row gd-pdr-icard">
            <span v-if="prow.label" class="icard-label">{{ prow.label }}: </span>
            <span class="icard-val"><PluginDetailValue :row="prow" :game="pluginGame" library="games" variant="icard" /></span>
          </div>
        </div>

        <!-- Card: languages -->
        <div v-if="entryLangs.length" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span>{{ t('detail.languages') }}</span>
          </div>
          <div class="lang-flags">
            <span v-for="l in entryLangs" :key="l.name" class="lang-flag-em" :title="l.name">
              <span v-if="l.flag" class="fi" :class="`fi-${l.flag}`"></span>
              <span v-else>{{ l.name }}</span>
            </span>
          </div>
        </div>

        <!-- Card: platforms. An entry has no os_* flags, so the builds on offer
             are the only honest source for this row - which is also why the
             glyphs are never drawn dimmed: an icon here means a build exists. -->
        <div v-if="assetOses.length" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            <span>{{ t('library.platform_label') }}</span>
          </div>
          <div class="os-icons">
            <span v-for="os in assetOses" :key="os" class="os-icon active" :title="osLabel(os)">
              <svg v-if="os === 'windows'" width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.75L11,11.91V5.21L20,3M3,13L9,13.09V19.9L3,18.75V13M20,13.25V22L11,20.5V13.09L20,13.25Z"/></svg>
              <svg v-else-if="os === 'mac'" width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.78 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5M13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z"/></svg>
              <img v-else-if="os === 'linux'" src="/icons/os-linux.svg" class="os-icon-linux" alt="Linux" />
              <span v-else class="os-icon-other">{{ osLabel(os) }}</span>
            </span>
          </div>
        </div>

        <!-- Card: the listing's own facts. Unconditional on purpose - the
             catalogue an entry came from always exists, so the grid can never
             render with nothing in it. -->
        <div class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            <span>{{ t('detail.details') }}</span>
          </div>
          <div class="icard-row"><span class="icard-label">{{ t('detail.source') }}: </span><span class="icard-val">{{ storeName }}</span></div>
          <div v-if="entry.release_date" class="icard-row"><span class="icard-label">{{ t('detail.released') }}: </span><span class="icard-val">{{ formatDate(entry.release_date) }}</span></div>
          <div v-if="totalSize" class="icard-row"><span class="icard-label">{{ t('detail.size') }}: </span><span class="icard-val">{{ totalSize }}</span></div>
          <div v-if="entry.category" class="icard-row"><span class="icard-label">{{ t('detail.category') }}: </span><span class="icard-val">{{ entry.category }}</span></div>
          <!-- HowLongToBeat has no home of its own in this layout, and the ROM
               card that used to carry it does not apply to a listing. -->
          <template v-if="entry.hltb_main_s || entry.hltb_complete_s">
            <div class="icard-head" style="margin-top:10px">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span>{{ t('detail.time_to_beat') }}</span>
            </div>
            <div v-if="entry.hltb_main_s" class="icard-row"><span class="icard-label">{{ t('detail.hltb_main') }} </span><span class="icard-val">{{ fmtHltb(entry.hltb_main_s) }}</span></div>
            <div v-if="entry.hltb_complete_s" class="icard-row"><span class="icard-label">{{ t('detail.hltb_complete') }} </span><span class="icard-val">{{ fmtHltb(entry.hltb_complete_s) }}</span></div>
          </template>
        </div>

        <!-- Card: minimum requirements. No "no data" placeholder - the card
             simply does not exist when nothing was scraped. -->
        <div v-if="reqRows.length" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            <span>{{ t('detail.min_requirements') }}</span>
          </div>
          <table class="req-table">
            <tr v-for="[k, v] in reqRows" :key="k">
              <td class="req-name">{{ formatReqKey(k) }}</td>
              <td class="req-min">{{ v }}</td>
            </tr>
          </table>
        </div>

        <!-- Card: builds on offer. Owning one build never meant the others
             stopped existing: hiding the list left no way to add a second
             platform or to fetch a build again. So the gate is only "is there
             anything to offer" - never "downloaded", which changes the heading
             alone.
             The card reads, it does not pick: choosing builds belongs to the
             download dialog, exactly as it does for a GOG game in this skin. -->
        <div v-if="entry.available && assets.length" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8v13H3V8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
            <span>{{ entry.downloaded ? t('detail.builds_more') : t('detail.builds') }}</span>
          </div>
          <template v-for="group in buildsByOs" :key="group.os">
            <div class="cd-dl-os">{{ group.label }}</div>
            <div v-for="a in group.entries" :key="a.name" class="cd-dl-row">
              <span class="cd-dl-name" :title="a.name">{{ a.name }}</span>
              <span v-if="a.arch" class="cd-dl-ver">{{ a.arch }}</span>
              <span v-if="a.size" class="cd-dl-size">{{ fmtSize(a.size) }}</span>
            </div>
          </template>
          <!-- Where a download lands. The core store page has always said so;
               this skin left it out, which made the one fact a reader actually
               needs before pulling 30 GB the one fact it did not show. -->
          <div v-if="entry.save_root" class="cd-dl-root">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="cea-mono">{{ entry.save_root }}</span>
          </div>
        </div>

        <!-- Card: which match this listing got. A wrong match is only fixable
             once it is visible, so the source and the title it matched sit next
             to the search term that produced them. -->
        <div v-if="isAdmin && hasMatchRows" class="icard">
          <div class="icard-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <span>{{ t('detail.edit_metadata') }}</span>
          </div>
          <div v-if="entry.meta_source" class="icard-row"><span class="icard-label">{{ t('detail.source') }}: </span><span class="icard-val">{{ entry.meta_source }}</span></div>
          <div v-if="entry.meta_matched_title" class="icard-row">
            <span class="icard-label">{{ t('detail.also_known_as') }}: </span>
            <span class="icard-val">{{ entry.meta_matched_title }}</span>
            <span v-if="entry.meta_confidence" class="genre-tag" :class="{ 'genre-tag--warn': entry.meta_confidence === 'low' }">{{ entry.meta_confidence }}</span>
          </div>
          <div v-if="entry.meta_search_term" class="icard-row">
            <span class="icard-label">{{ t('detail.search_term') }}: </span>
            <span class="icard-val cea-mono">{{ entry.meta_search_term }}</span>
          </div>
        </div>

      </div>

      <!-- ── DESCRIPTION ─────────────────────────────────────────────────────── -->
      <div v-if="entry.description" class="desc-section">
        <div class="section-head">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--pl)"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
          <span>{{ t('detail.about') }}</span>
        </div>
        <div class="desc-body" v-html="sanitizeHtml(entry.description)" />
      </div>

    </template>

  </div>

  <!-- ── LIGHTBOX (teleported to body) ──────────────────────────────────────── -->
  <teleport to="body">
    <div v-if="lightboxIdx !== null" class="cd-lightbox" @click.self="lightboxIdx = null">
      <button class="cd-lb-close" @click="lightboxIdx = null">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
      <button v-if="lightboxIdx > 0" class="cd-lb-arrow cd-lb-arrow--l" @click="lightboxIdx--">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <img :src="screenshots[lightboxIdx]" class="cd-lb-img" @click.stop />
      <button v-if="lightboxIdx < screenshots.length - 1" class="cd-lb-arrow cd-lb-arrow--r" @click="lightboxIdx++">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <div class="cd-lb-counter">{{ lightboxIdx + 1 }} / {{ screenshots.length }}</div>
    </div>
  </teleport>

  <!-- ── METADATA EDITOR ───────────────────────────────────────────────────── -->
  <!-- The same panel a game gets in this skin, pointed at the catalog_entries
       row. The endpoints behind that prefix were written for exactly this. -->
  <teleport to="body">
    <LibraryMetadataPanel
      v-if="entry && showMetaPanel"
      :game="(entry as any)"
      api-prefix="/plugins/library/catalog-entries"
      @close="showMetaPanel = false"
      @saved="onMetadataSaved"
    />
  </teleport>

  <!-- ── DOWNLOAD DIALOG ───────────────────────────────────────────────────── -->
  <!-- The shared store picker, the same one Modern and Neon Horizon open - this
       skin already shares the GOG download dialog the same way. -->
  <CatalogDownloadDialog
    v-if="entry"
    v-model="showDownload"
    :entry-id="entry.id"
    :title="entry.title"
    :assets="assets"
    :save-root="entry.save_root"
    @started="onDownloadStarted"
  />

</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import PluginDetailValue from '@/components/games/PluginDetailValue.vue'
import CatalogDownloadDialog from '@/components/games/CatalogDownloadDialog.vue'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import { useThemeStore } from '@/stores/theme'
import { useI18n } from '@/i18n'
import { sanitizeHtml } from '@/utils/sanitize'
import { ratingVal } from '@/utils/rating'
import { formatReqKey } from '@/utils/requirements'
import { formatDate } from '@/utils/format'
import { useCoverTilt } from '@/composables/useCoverTilt'
import { useCatalogEntry, osLabel, fmtHltb } from '@/composables/useCatalogEntry'

const { coverTilt, sheenStyle, onCoverMove, onCoverLeave } = useCoverTilt()

const { t } = useI18n()
const themeStore = useThemeStore()

const logoFailed = ref(false)

// ── Media strip / lightbox ────────────────────────────────────────────────────

const stripEl     = ref<HTMLElement | null>(null)
const slideIdx    = ref(0)
const lightboxIdx = ref<number | null>(null)

// ── Cover ─────────────────────────────────────────────────────────────────────

const coverIsSquarish = ref(false)

const {
  entry, loading, showDownload, showMetaPanel, scraping, coverFailed,
  isAdmin, assets, screenshots, entryLangs, releaseYear, storeName,
  pluginRows, pluginGame, homepageHost, assetOses, buildsByOs,
  externalRatings, pluginRatings, hasRatings, hasMatchRows, totalSize, reqRows,
  fmtSize, hideImg, load, onMetadataSaved, refreshMeta, goBack,
} = useCatalogEntry({
  onLoaded: () => {
    logoFailed.value      = false
    coverIsSquarish.value = false
    slideIdx.value        = 0
  },
})

// cover_path is already `cover_path or icon_path` server-side, and there is no
// CDN pair to fall back to, so the chain is this short.
const heroBgStyle = computed(() => {
  const url = entry.value?.background_path || entry.value?.cover_path || ''
  return url ? { backgroundImage: `url("${url}")` } : {}
})

// Hero animation class - same keyframes and kill switch as the game page.
const heroAnimClass = computed(() => {
  if (!themeStore.heroAnim || !themeStore.animations) return ''
  return `cd-hero--${themeStore.heroAnimStyle}`   // cd- prefix = ClassicDetail
})

// ── Card count ────────────────────────────────────────────────────────────────

const showCredits = computed(() => !!(
  entry.value?.developer || entry.value?.publisher
  || (entry.value?.genres || []).length || pluginRows.value.length
))

// The facts card is always drawn, so this is never zero.
const cardCount = computed(() =>
  1
  + (showCredits.value ? 1 : 0)
  + (entryLangs.value.length ? 1 : 0)
  + (assetOses.value.length ? 1 : 0)
  + (reqRows.value.length ? 1 : 0)
  + (entry.value?.available && assets.value.length ? 1 : 0)
  + (isAdmin.value && hasMatchRows.value ? 1 : 0),
)

// Four visible at a time. That number lives here, in the next arrow's disabled
// test and in .shot-item's flex-basis - move them together.
function slideTo(idx: number) {
  const max = Math.max(0, screenshots.value.length - 4)
  slideIdx.value = Math.max(0, Math.min(idx, max))
  nextTick(() => {
    const el = stripEl.value
    if (!el) return
    const child = el.children[slideIdx.value] as HTMLElement
    if (child) el.scrollTo({ left: child.offsetLeft, behavior: 'smooth' })
  })
}

function onKeydown(e: KeyboardEvent) {
  if (lightboxIdx.value === null) return
  if (e.key === 'Escape')      { lightboxIdx.value = null }
  else if (e.key === 'ArrowLeft'  && lightboxIdx.value > 0)                             { lightboxIdx.value-- }
  else if (e.key === 'ArrowRight' && lightboxIdx.value < screenshots.value.length - 1)  { lightboxIdx.value++ }
}

/** A catalogue often has only a square icon where a game has a 2:3 poster, and
 *  cropping one to poster shape cut the artwork in half. Measure what actually
 *  arrived and let anything squarer than a poster keep its own shape. */
function onCoverLoad(e: Event) {
  const img = e.target as HTMLImageElement
  coverIsSquarish.value = !!img.naturalHeight && (img.naturalWidth / img.naturalHeight) > 0.8
}

/** Re-read rather than flip a local flag: `downloaded` and `library_game_id`
 *  are what turn this into the owned state, and the server decides both. */
async function onDownloadStarted() {
  await load()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.cd-wrap {
  display: flex; flex-direction: column;
  flex: 1; overflow-y: auto; overflow-x: hidden;
  /* Reserve scrollbar gutter so width stays constant when content overflows. */
  scrollbar-gutter: stable;
}

/* Loading / empty */
.cd-loading { flex: 1; display: flex; align-items: center; justify-content: center; }
.cd-spin { animation: cd-spin-anim 1s linear infinite; }

.cd-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 14px;
  color: var(--muted); font-size: var(--fs-md, 14px);
}
.cd-empty-text { font-family: 'Rajdhani', var(--font); font-size: 17px; font-weight: 600; }

/* ── COVER HERO ────────────────────────────────────────────────────────────── */
.cover-hero {
  display: flex; flex-direction: column; align-items: center;
  padding: 28px 20px 20px; flex-shrink: 0;
  position: relative; overflow: hidden;
}
.hero-vignette {
  position: absolute; top: 0; left: 0; right: 0; height: 100%;
  background: transparent; pointer-events: none; z-index: 2;
}
.hero-bg { position: absolute; inset: 0; z-index: 0; overflow: hidden; }
.hero-bg-inner {
  position: absolute; inset: -10%;
  background-size: cover; background-position: center center;
  /* filter applied via :style binding (uses themeStore.heroBlur) */
  /* animation applied via :class heroAnimClass (heroAnimStyle / heroAnim) */
  transform-origin: center center;
  transform: scale(1.06);
  will-change: transform;
}
.hero-bg-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to bottom,
    color-mix(in srgb, var(--bg) 15%, transparent) 0%,
    color-mix(in srgb, var(--bg) 50%, transparent) 40%,
    color-mix(in srgb, var(--bg) 85%, transparent) 72%,
    var(--bg) 100%);
}

/* ── Hero animation keyframes - same names as the game page, so the global
      animations kill switch below reaches them too ─────────────────────────── */

.cd-hero--kenburns { animation: cd-kenburns calc(44s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
.cd-hero--drift    { animation: cd-drift    calc(28s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite alternate; }
.cd-hero--pulse    { animation: cd-pulse    calc(10s / max(var(--hero-anim-speed, 1), 0.1)) ease-in-out infinite; }
[data-animations="false"] .cd-hero--kenburns,
[data-animations="false"] .cd-hero--drift,
[data-animations="false"] .cd-hero--pulse { animation: none; }

/* Cover. The hero backdrop is absolute at z-index 0, so everything that sits
   over it has to be positioned - anything new added here needs the same. */
.cover-wrap { position: relative; z-index: 3; transform-style: preserve-3d; }
.game-logo, .game-title, .game-subtitle,
.cover-ratings, .meta-chips, .cea-no-files { position: relative; z-index: 4; }

.cover-img {
  width: calc(var(--cd-cover-h, 525px) * 2 / 3); height: var(--cd-cover-h, 525px);
  object-fit: cover; border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--pl-light) 40%, transparent);
  box-shadow: 0 20px 60px rgba(0,0,0,.8), 0 0 0 1px rgba(255,255,255,.04), 0 0 40px var(--pglow2);
  display: block;
}
/* Square catalogue icons keep their own shape rather than being cropped to a
   poster they never were. */
.cover-img--nat {
  width: auto; height: auto;
  max-height: var(--cd-cover-h, 525px); max-width: 420px;
  object-fit: unset;
}
.cover-ph {
  width: calc(var(--cd-cover-h, 525px) * 2 / 3); height: var(--cd-cover-h, 525px);
  border-radius: 14px; border: 1px dashed var(--pglow2);
  display: flex; align-items: center; justify-content: center;
  background: var(--glass-highlight);
}
.cover-sheen {
  position: absolute; inset: 0; border-radius: 14px;
  pointer-events: none; z-index: 4; transition: opacity .25s;
}

/* Cover action overlay */
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
  background: color-mix(in srgb, var(--pl) 55%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl-light) 60%, transparent);
  color: #fff; cursor: pointer; text-decoration: none;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s, transform .15s;
}
.cov-btn:hover { background: color-mix(in srgb, var(--pl) 85%, transparent); transform: scale(1.1); }
.cov-btn--spin { opacity: .7; cursor: default; }
.cov-btn--spin svg { animation: cov-spin 1s linear infinite; }

/* Title */
.game-logo {
  max-width: 320px; max-height: 110px; width: auto; height: auto;
  object-fit: contain; filter: drop-shadow(0 4px 16px rgba(0,0,0,.8));
  margin-top: 6px;
}
.game-title {
  margin-top: 18px;
  font-family: 'Rajdhani', var(--font); font-size: 34px; font-weight: 700; letter-spacing: .5px;
  text-align: center; line-height: 1.1;
  color: var(--text); text-shadow: 0 2px 20px var(--pglow);
}
.game-subtitle {
  font-family: 'Rajdhani', var(--font); font-size: 17px; font-weight: 600;
  text-align: center; letter-spacing: .4px; margin-top: 4px; color: var(--muted);
}

/* Ratings row */
.cover-ratings { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 10px; }
.crating {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.crating-ico { width: 35px; height: 35px; object-fit: contain; }
.crating small { color: var(--muted); font-size: 11px; font-weight: 400; }

/* Meta chips */
.meta-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 5px; margin-top: 8px; }
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 12px; border-radius: 20px; font-size: 13px;
  background: var(--pl-dim); border: 1px solid var(--glass-border);
  color: var(--muted); white-space: nowrap; backdrop-filter: blur(8px);
}
.chip span { color: var(--text); }
/* The store's own name takes the skin accent, the way a game page tints the
   badge naming where a title came from. */
.chip--store {
  background: color-mix(in srgb, var(--pl) 24%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
}
.chip--store span { color: var(--pl-light); font-weight: 700; letter-spacing: .5px; }
.chip--owned {
  background: color-mix(in srgb, var(--ok) 12%, transparent);
  border-color: color-mix(in srgb, var(--ok) 28%, transparent);
  color: var(--ok);
}
.chip--owned span { color: var(--ok); font-weight: 700; }
.chip--ver span { font-family: monospace; font-size: 12px; color: var(--muted); }
.chip--warn {
  background: color-mix(in srgb, var(--warning) 12%, transparent);
  border-color: color-mix(in srgb, var(--warning) 35%, transparent);
}
.chip--warn span { color: var(--warning); font-weight: 700; text-transform: uppercase; letter-spacing: .5px; font-size: 11px; }

/* ── BACK PILL / SHARED BITS ───────────────────────────────────────────────── */
/* The action row this file once carried is gone: downloading is a round button
   on the cover, the way ClassicGameDetail does it. What remains is the back
   pill and the two lines that explain an entry with nothing to offer. */
.cea-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 20px; border-radius: var(--radius-sm, 8px);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.06); color: var(--muted);
  text-decoration: none;
}
.cea-btn--ghost:hover:not(:disabled) { background: rgba(255,255,255,.12); color: var(--text); }
.cea-no-files { margin-top: 14px; font-size: 13px; color: var(--muted); font-style: italic; text-align: center; }
.cea-mono { font-family: monospace; font-size: 12px; }

/* ── MEDIA STRIP ───────────────────────────────────────────────────────────── */
/* Flex row with the arrows as siblings: flex:1 on the strip is what gives the
   thumbnails a definite width for their percentage flex-basis to resolve. */
.shots-wrap {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 6px;
  margin: 0 20px 10px;
  background: linear-gradient(145deg, var(--glass-highlight) 0%, rgba(0,0,0,.5) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border);
  border-top: 1px solid color-mix(in srgb, var(--pl-light) 30%, transparent);
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
  cursor: pointer; transition: background .15s, color .15s;
}
.shots-nav:hover:not(:disabled) { background: var(--pglow); color: #fff; }
.shots-nav:disabled { opacity: .25; cursor: default; }
.shots-strip {
  flex: 1;
  display: flex; gap: 6px; overflow-x: auto;
  scroll-snap-type: x mandatory; scroll-behavior: smooth;
  scrollbar-width: none; -webkit-overflow-scrolling: touch;
}
.shots-strip::-webkit-scrollbar { display: none; }
/* 4 visible: (100% - 3 gaps of 6px) / 4 */
.shot-item {
  flex: 0 0 calc((100% - 18px) / 4);
  aspect-ratio: 16/9; border-radius: 7px; overflow: hidden; cursor: pointer;
  scroll-snap-align: start; border: 2px solid transparent;
  box-shadow: 0 4px 12px rgba(0,0,0,.5);
  transition: border-color .2s, box-shadow .2s; position: relative;
}
.shot-item:hover { border-color: var(--pl); box-shadow: 0 0 0 1px var(--pl), 0 6px 20px var(--pglow); }
.shot-thumb-img { width: 100%; height: 100%; object-fit: cover; display: block; }

/* ── LIGHTBOX ──────────────────────────────────────────────────────────────── */
.cd-lightbox {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.92);
  display: flex; align-items: center; justify-content: center;
  cursor: zoom-out; animation: lb-in .15s ease;
}

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
.cd-lb-arrow {
  position: absolute; top: 50%; transform: translateY(-50%);
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

/* ── INFO CARDS ────────────────────────────────────────────────────────────── */
/* grid-template-columns is bound inline from the number of cards that survived
   their v-if - see the note in the template. */
.info-cards { display: grid; gap: 10px; padding: 0 20px 14px; flex-shrink: 0; }
.icard {
  border-radius: 14px; padding: 14px 16px;
  background: linear-gradient(145deg, var(--pl-dim) 0%, rgba(0,0,0,.7) 100%);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 180%));
  border: 1px solid var(--glass-border);
  border-top: 1px solid color-mix(in srgb, var(--pl-light) 40%, transparent);
  box-shadow: 0 8px 24px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.04);
  min-width: 0;
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
.genre-tag--warn {
  background: color-mix(in srgb, var(--warning) 12%, transparent);
  border-color: color-mix(in srgb, var(--warning) 35%, transparent);
  color: var(--warning);
}

/* Language flags - flag-icons sprite, name on the :title tooltip */
.lang-flags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.lang-flag-em {
  display: inline-flex; align-items: center;
  font-size: var(--fs-xl, 18px); line-height: 1; cursor: default;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,.5));
  transition: transform .15s;
}
.lang-flag-em .fi { width: 1.4em; height: 1em; border-radius: 2px; }
.lang-flag-em:hover { transform: scale(1.3); }

/* OS icons */
.os-icons { display: flex; gap: var(--space-2, 8px); margin-top: 5px; align-items: center; flex-wrap: wrap; }
.os-icon { color: var(--pglow2); display: flex; align-items: center; }
.os-icon.active { color: var(--pl-light); filter: drop-shadow(0 0 4px color-mix(in srgb, var(--pl-light) 60%, transparent)); }
.os-icon-linux { width: 40px; height: 40px; opacity: .9; filter: invert(1) sepia(1) saturate(3) hue-rotate(220deg) brightness(1.1); }
/* A build whose os string is none of the three still deserves naming. */
.os-icon-other { font-size: 12px; font-weight: 600; color: var(--pl-light); }

/* Requirements. Wider name column than the game page: this set also carries
   "Storage" and "DirectX", which 46px clipped. */
.req-table { width: 100%; font-size: var(--fs-sm, 12px); border-collapse: collapse; }
.req-table tr { border-bottom: 1px solid var(--pl-dim); }
.req-table tr:last-child { border: none; }
.req-table td { padding: 4px 3px; vertical-align: top; line-height: 1.4; }
.req-name {
  color: var(--pl-light); font-weight: 700; font-family: 'Rajdhani', var(--font);
  letter-spacing: .4px; width: 62px; white-space: nowrap;
}
.req-min { color: var(--text); font-size: 11px; }

/* Build rows - a reading list grouped by platform, not a picker */
.cd-dl-os {
  font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin: 10px 0 2px;
}
.cd-dl-os:first-of-type { margin-top: 2px; }
.cd-dl-row {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 5px 4px;
}
.cd-dl-name { font-size: 13px; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cd-dl-ver { font-size: 11px; color: var(--muted); flex-shrink: 0; }
.cd-dl-size { font-size: var(--fs-sm, 12px); color: var(--muted); flex-shrink: 0; }
.cd-dl-root {
  display: flex; align-items: center; gap: 6px;
  margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--glass-border);
  color: var(--muted); overflow-wrap: anywhere;
}
.cd-dl-root svg { flex-shrink: 0; }

/* ── DESCRIPTION ───────────────────────────────────────────────────────────── */
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
</style>
