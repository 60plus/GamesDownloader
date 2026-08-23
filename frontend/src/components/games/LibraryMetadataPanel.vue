<template>
  <!-- Fullscreen overlay -->
  <div class="mep-overlay mep-std" @click.self="$emit('close')">
    <div class="mep-panel" @click.stop>

      <!-- ── Header ──────────────────────────────────────────────────────────── -->
      <div class="mep-header">
        <div class="mep-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <span>{{ t('meta.edit_title') }}</span>
          <span class="mep-game-name">- {{ game.title }}</span>
        </div>
        <button class="mep-close" @click="$emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- ── Body ────────────────────────────────────────────────────────────── -->
      <div class="mep-body">

        <!-- LEFT: Previews sidebar -->
        <div class="mep-left">

          <!-- Cover -->
          <div class="mep-label">{{ t('meta.tab_cover') }}</div>
          <div class="mep-cover-current" @click="switchTab('cover')" style="cursor:pointer">
            <img v-if="selectedCoverThumb || selectedCover" :src="selectedCoverThumb || selectedCover" :alt="t('meta.tab_cover')" class="mep-cover-img" @error="onThumbError" />
            <div v-else class="mep-cover-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="2" y="6" width="20" height="12" rx="2"/></svg>
            </div>
            <div v-if="selectedCoverAnimated" class="mep-anim-badge">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
              ANIM
            </div>
          </div>

          <!-- Hero -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_hero') }}</div>
          <div class="mep-cover-current mep-cover-current--wide" @click="switchTab('background')" style="cursor:pointer">
            <img v-if="selectedBackground" :src="selectedBackground" :alt="t('meta.tab_hero')" class="mep-cover-img" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="1" y="5" width="22" height="14" rx="2"/></svg>
            </div>
          </div>

          <!-- Logo -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_logo') }}</div>
          <div class="mep-cover-current mep-cover-current--logo" @click="switchTab('logo')" style="cursor:pointer">
            <img v-if="selectedLogo" :src="selectedLogo" :alt="t('meta.tab_logo')" style="width:100%;height:100%;object-fit:contain;padding:6px" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
          </div>

          <!-- Icon -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_icon') }}</div>
          <div class="mep-cover-current mep-cover-current--icon" @click="switchTab('icon')" style="cursor:pointer">
            <img v-if="selectedIcon" :src="selectedIcon" :alt="t('meta.tab_icon')" style="width:100%;height:100%;object-fit:contain;padding:6px" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="3" y="3" width="18" height="18" rx="3"/></svg>
            </div>
          </div>
        </div>

        <!-- RIGHT: Category tabs + content -->
        <div class="mep-right">

          <!-- Tabs -->
          <div class="mep-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              class="mep-tab"
              :class="{ active: activeTab === tab.id }"
              @click="switchTab(tab.id)"
            >{{ tab.label }}</button>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- COVER TAB                                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'cover'" class="mep-tab-content">

            <!-- Unified cover search -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img v-if="isCatalog" src="/icons/ScreenScraper.ico" width="14" height="14" alt="ScreenScraper" title="ScreenScraper" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.cover_sources', 'All Sources') }}</span>
                <div class="mep-chip-bar" style="margin-left:auto">
                  <button class="mep-chip-btn" :class="{ active: coverFilter === 'all' }" @click="setCoverFilter('all')">{{ t('meta.all') }}</button>
                  <button class="mep-chip-btn" :class="{ active: coverFilter === 'static' }" @click="setCoverFilter('static')">{{ t('meta.static') }}</button>
                  <button class="mep-chip-btn" :class="{ active: coverFilter === 'animated' }" @click="setCoverFilter('animated')">
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                    {{ t('meta.animated') }}
                  </button>
                </div>
              </div>
              <div class="mep-search-row">
                <input v-model="coverSearchQuery" class="mep-search-input" :placeholder="t('meta.search_covers', 'Search all sources for covers...')" @keydown.enter="searchAllCovers" />
                <button class="mep-search-btn" :disabled="coverSearching" @click="searchAllCovers">
                  <div v-if="coverSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="coverSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="coverSearchDone && !filteredCoverResults.length" class="mep-empty-state-sm">{{ t('meta.no_results') }}</div>
              <div v-else-if="!coverSearchDone" class="mep-empty-state-sm">{{ t('meta.search_covers_hint', 'Search to find covers from GOG, IGDB and SteamGridDB.') }}</div>
              <div v-else class="mep-covers-grid">
                <div
                  v-for="cover in filteredCoverResults"
                  :key="cover.url"
                  class="mep-cover-option"
                  :class="{ selected: selectedCover === cover.url }"
                  @click="selectCover(cover)"
                >
                  <div class="mep-cover-option-img">
                    <img
                      :src="cover.type === 'animated' ? cover.url : (cover.thumb || cover.url)"
                      :alt="cover.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display = 'none')"
                    />
                    <div v-if="cover.type === 'animated'" class="mep-anim-badge-grid">ANIM</div>
                    <div v-if="selectedCover === cover.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div class="mep-source-badge" :title="cover._source">
                      <img :src="(cover._sourceIcon || '').startsWith('/') ? cover._sourceIcon : '/icons/' + (cover._sourceIcon || 'gog.ico')" width="12" height="12" alt="" />
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ cover.label }}</div>
                  <div v-if="cover.author" class="mep-cover-author">{{ cover.author }}</div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- HERO (BACKGROUND) TAB                                             -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'background'" class="mep-tab-content">

            <!-- Unified hero/background search -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/RAWG.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.cover_sources', 'All Sources') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="heroSearchQuery" class="mep-search-input" :placeholder="t('meta.search_heroes', 'Search all sources for backgrounds...')" @keydown.enter="searchAllHeroes" />
                <button class="mep-search-btn" :disabled="heroSearching" @click="searchAllHeroes">
                  <div v-if="heroSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="heroSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="heroSearchDone && !allHeroResults.length" class="mep-empty-state-sm">{{ t('meta.no_results') }}</div>
              <div v-else-if="!heroSearchDone" class="mep-empty-state-sm">{{ t('meta.search_heroes_hint', 'Search to find backgrounds from GOG, RAWG and SteamGridDB.') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="cover in allHeroResults"
                  :key="cover.url"
                  class="mep-cover-option"
                  :class="{ selected: selectedBackground === cover.url }"
                  @click="selectedBackground = cover.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--hero">
                    <img
                      :src="cover.type === 'animated' ? cover.url : (cover.thumb || cover.url)"
                      :alt="cover.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display = 'none')"
                    />
                    <div v-if="cover.type === 'animated'" class="mep-anim-badge-grid">ANIM</div>
                    <div v-if="selectedBackground === cover.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div class="mep-source-badge" :title="cover._source">
                      <img :src="(cover._sourceIcon || '').startsWith('/') ? cover._sourceIcon : '/icons/' + (cover._sourceIcon || 'gog.ico')" width="12" height="12" alt="" />
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ cover.label }}</div>
                  <div v-if="cover.author" class="mep-cover-author">{{ cover.author }}</div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- LOGO TAB                                                           -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'logo'" class="mep-tab-content">

            <!-- Unified logo search -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.cover_sources', 'All Sources') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="logoSearchQuery" class="mep-search-input" :placeholder="t('meta.search_logos', 'Search all sources for logos...')" @keydown.enter="searchAllLogos" />
                <button class="mep-search-btn" :disabled="logoSearching" @click="searchAllLogos">
                  <div v-if="logoSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="logoSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="logoSearchDone && !allLogoResults.length" class="mep-empty-state-sm">{{ t('meta.no_results') }}</div>
              <div v-else-if="!logoSearchDone" class="mep-empty-state-sm">{{ t('meta.search_logos_hint', 'Search to find logos from GOG, SteamGridDB and LaunchBox.') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="cover in allLogoResults"
                  :key="cover.url"
                  class="mep-cover-option"
                  :class="{ selected: selectedLogo === cover.url }"
                  @click="selectedLogo = cover.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--logo">
                    <img :src="cover.thumb || cover.url" :alt="cover.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display = 'none')" />
                    <div v-if="selectedLogo === cover.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div class="mep-source-badge mep-source-badge--lg" :title="cover._source">
                      <img :src="(cover._sourceIcon || '').startsWith('/') ? cover._sourceIcon : '/icons/' + (cover._sourceIcon || 'gog.ico')" width="16" height="16" alt="" />
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ cover.label }}</div>
                  <div v-if="cover.author" class="mep-cover-author">{{ cover.author }}</div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- ICON TAB                                                            -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'icon'" class="mep-tab-content">
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.cover_sources', 'All Sources') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="iconSearchQuery" class="mep-search-input" :placeholder="t('meta.search_icons', 'Search all sources for icons...')" @keydown.enter="searchAllIcons" />
                <button class="mep-search-btn" :disabled="iconSearching" @click="searchAllIcons">
                  <div v-if="iconSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="iconSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="iconSearchDone && !allIconResults.length" class="mep-empty-state-sm">{{ t('meta.no_results') }}</div>
              <div v-else-if="!iconSearchDone" class="mep-empty-state-sm">{{ t('meta.search_icons_hint', 'Search to find icons from GOG and SteamGridDB.') }}</div>
              <div v-else class="mep-covers-grid">
                <div
                  v-for="icon in allIconResults"
                  :key="icon.url"
                  class="mep-cover-option"
                  :class="{ selected: selectedIcon === icon.url }"
                  @click="selectedIcon = icon.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--icon">
                    <img :src="icon.thumb || icon.url" :alt="icon.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display = 'none')" />
                    <div v-if="selectedIcon === icon.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div class="mep-source-badge" :title="icon._source">
                      <img :src="(icon._sourceIcon || '').startsWith('/') ? icon._sourceIcon : '/icons/' + (icon._sourceIcon || 'gog.ico')" width="12" height="12" alt="" />
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ icon.label }}</div>
                  <div v-if="icon.author" class="mep-cover-author">{{ icon.author }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- SCREENSHOTS TAB                                                    -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'screenshots'" class="mep-tab-content">

            <!-- Current list with reorder -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.current_screenshots') }}</span>
                <div class="mep-chip-bar" style="margin-left:auto">
                  <button class="mep-chip-btn" :class="{ active: screenshotsMode === 'add' }" @click="screenshotsMode = 'add'">{{ t('meta.add') }}</button>
                  <button class="mep-chip-btn" :class="{ active: screenshotsMode === 'replace' }" @click="screenshotsMode = 'replace'">{{ t('meta.replace_all') }}</button>
                </div>
              </div>
              <div v-if="!editScreenshots.length" class="mep-empty-state-sm">{{ t('meta.no_screenshots') }}</div>
              <div v-else class="mep-ss-list">
                <div v-for="(ss, idx) in editScreenshots" :key="ss + idx" class="mep-ss-item">
                  <img :src="ss" class="mep-ss-item-thumb" loading="lazy"
                    @error="(e) => ((e.target as HTMLImageElement).style.opacity = '0.15')" />
                  <div class="mep-ss-order-col">
                    <button class="mep-ss-ord-btn" :disabled="idx === 0" @click="moveScreenshot(idx, idx - 1)" :title="t('common.move_up')">▲</button>
                    <span class="mep-ss-num">{{ idx + 1 }}</span>
                    <button class="mep-ss-ord-btn" :disabled="idx === editScreenshots.length - 1" @click="moveScreenshot(idx, idx + 1)" :title="t('common.move_down')">▼</button>
                  </div>
                  <button class="mep-ss-remove--list" @click="removeScreenshot(idx)" :title="t('common.remove')">✕</button>
                </div>
              </div>
              <!-- Manual URL add -->
              <div class="mep-search-row" style="margin-top:14px">
                <input v-model="ssNewUrl" class="mep-search-input" :placeholder="t('meta.screenshot_url_ph')" @keydown.enter="addScreenshotUrl" />
                <button class="mep-search-btn" @click="addScreenshotUrl">{{ screenshotsMode === 'replace' ? t('meta.replace') : t('meta.add_url') }}</button>
              </div>
            </div>

            <!-- Unified screenshot search -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/RAWG.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/Steam.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img v-if="isCatalog" src="/icons/ScreenScraper.ico" width="14" height="14" alt="ScreenScraper" title="ScreenScraper" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img v-for="mp in metadataProviders" :key="mp.id" :src="mp.logo_url" width="14" height="14" :alt="mp.name" :title="mp.name" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.find_screenshots', 'Find Screenshots') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="ssSearchQuery" class="mep-search-input" :placeholder="t('meta.search_screenshots', 'Search all sources for screenshots...')" @keydown.enter="searchAllScreenshots" />
                <button class="mep-search-btn" :disabled="ssAllSearching" @click="searchAllScreenshots">
                  <div v-if="ssAllSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="ssAllSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="ssAllSearchDone && !ssAllResults.length" class="mep-empty-state-sm">{{ t('meta.no_screenshots_found') }}</div>
              <div v-else-if="!ssAllSearchDone" class="mep-empty-state-sm">{{ t('meta.search_screenshots_hint', 'Search to find screenshots from all sources.') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="ss in ssAllResults"
                  :key="ss.url"
                  class="mep-cover-option"
                  :class="{ selected: editScreenshots.includes(ss.url) }"
                  :title="editScreenshots.includes(ss.url) ? 'Added - click to remove' : 'Click to add'"
                  @click="addScreenshotFromSource(ss.url)"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide">
                    <img :src="ss.thumb || ss.url" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display = 'none')" />
                    <div v-if="editScreenshots.includes(ss.url)" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div class="mep-source-badge" :title="ss._source">
                      <img :src="(ss._sourceIcon || '').startsWith('/') ? ss._sourceIcon : '/icons/' + (ss._sourceIcon || 'gog.ico')" width="12" height="12" alt="" />
                    </div>
                  </div>
                  <div v-if="ss.author" class="mep-cover-author">{{ ss.author }}</div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- VIDEO TAB                                                           -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'video'" class="mep-tab-content">

            <!-- Current video -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.current_video') }}</span>
              </div>
              <div v-if="editVideoId" class="mep-video-preview">
                <img :src="`https://img.youtube.com/vi/${editVideoId}/hqdefault.jpg`" class="mep-video-thumb" :alt="t('meta.video_thumb')" />
                <div class="mep-video-info">
                  <span class="mep-video-yt-id">youtube.com/watch?v={{ editVideoId }}</span>
                  <a :href="`https://www.youtube.com/watch?v=${editVideoId}`" target="_blank" rel="noopener" class="mep-video-link">▶ {{ t('meta.open_youtube') }}</a>
                  <button class="mep-clear-btn" style="margin-top:8px" @click="editVideoId = ''">✕ {{ t('meta.remove_video') }}</button>
                </div>
              </div>
              <div v-else class="mep-empty-state-sm">{{ t('meta.no_video') }}</div>
              <!-- Manual URL input -->
              <div class="mep-search-row" style="margin-top:14px">
                <input v-model="editVideoUrl" class="mep-search-input" :placeholder="t('meta.video_url_ph')" @keydown.enter="applyVideo" />
                <button class="mep-search-btn" @click="applyVideo">{{ t('meta.set') }}</button>
              </div>
            </div>

            <!-- Local copy: download the trailer to the server or upload a
                 file. Stored like covers and served from /resources; players
                 prefer it over YouTube when present. The endpoints live on the
                 games library id space, so the section hides in GOG context
                 (published GOG games get the copy via the shared write-through). -->
            <div v-if="libraryKind === 'games'" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.local_video') }}</span>
              </div>
              <div v-if="localVideoPath" class="mep-video-preview">
                <video :src="localVideoPath" class="mep-video-thumb" controls preload="metadata" />
                <div class="mep-video-info">
                  <span class="mep-video-yt-id">{{ t('meta.local_video_present') }}</span>
                  <button class="mep-clear-btn" style="margin-top:8px" @click="removeLocalVideo">✕ {{ t('meta.remove_video') }}</button>
                </div>
              </div>
              <div v-else class="mep-empty-state-sm">{{ t('meta.no_local_video') }}</div>
              <div class="mep-search-row" style="margin-top:14px">
                <select v-model="videoQuality" class="mep-search-input" style="flex:0 0 110px" :title="t('meta.video_quality')">
                  <option value="best">{{ t('meta.quality_best') }}</option>
                  <option value="2160">2160p</option>
                  <option value="1440">1440p</option>
                  <option value="1080">1080p</option>
                  <option value="720">720p</option>
                  <option value="480">480p</option>
                </select>
                <button class="mep-search-btn" :disabled="!editVideoId || videoDownloading" @click="downloadLocalVideo">
                  {{ videoDownloading ? t('meta.video_downloading') : t('meta.video_download') }}
                </button>
                <label class="mep-search-btn" style="cursor:pointer">
                  {{ videoUploading ? t('meta.video_downloading') : t('meta.video_upload') }}
                  <input type="file" accept="video/mp4,video/webm" style="display:none" :disabled="videoUploading" @change="onLocalVideoFile" />
                </label>
              </div>
              <!-- YouTube refuses plenty of trailers (age gates above all). The
                   button used to sit on "Downloading" for five minutes and then
                   go quiet, so say what happened. -->
              <div v-if="videoError" class="mep-err" style="margin-top:10px">{{ videoError }}</div>
            </div>

            <!-- Unified video search -->
            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/gog.ico" width="14" height="14" alt="" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.find_trailers', 'Find Trailers') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="vidSearchQuery" class="mep-search-input" :placeholder="t('meta.search_trailers', 'Search all sources for trailers...')" @keydown.enter="searchAllVideos" />
                <button class="mep-search-btn" :disabled="vidAllSearching" @click="searchAllVideos">
                  <div v-if="vidAllSearching" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="vidAllSearching" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="vidAllSearchDone && !vidAllResults.length" class="mep-empty-state-sm">{{ t('meta.no_trailers') }}</div>
              <div v-else-if="!vidAllSearchDone" class="mep-empty-state-sm">{{ t('meta.search_trailers_hint', 'Search to find trailers from GOG and IGDB.') }}</div>
              <div v-else class="mep-vid-results">
                <div
                  v-for="vid in vidAllResults"
                  :key="vid.video_id"
                  class="mep-vid-option"
                  :class="{ selected: editVideoId === vid.video_id }"
                  @click="editVideoId = vid.video_id"
                >
                  <img :src="vid.thumb" class="mep-vid-opt-thumb" loading="lazy"
                    @error="(e) => ((e.target as HTMLImageElement).style.opacity = '0.2')" />
                  <div class="mep-vid-opt-info">
                    <div class="mep-vid-opt-label">{{ vid.label }}</div>
                    <div class="mep-vid-opt-author">{{ vid.author }}</div>
                  </div>
                  <div v-if="editVideoId === vid.video_id" class="mep-vid-selected-check">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                  </div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- DESCRIPTION TAB                                                    -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'description'" class="mep-tab-content">

            <!-- Fetch row -->
            <div class="mep-search-row">
              <input v-model="descQuery" class="mep-search-input" :placeholder="t('meta.search_title_ph')" @keydown.enter="loadDescriptions(true)" />
              <button class="mep-search-btn" :disabled="descLoading" @click="loadDescriptions(true)">
                <div v-if="descLoading" class="mep-spinner mep-spinner--sm" />
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                {{ t('meta.fetch') }}
              </button>
            </div>

            <!-- Source cards -->
            <div v-if="descLoading" class="mep-loading">
              <div class="mep-spinner" /> {{ t('meta.fetching_descriptions') }}
            </div>
            <div v-else-if="descFetched && !descSources.length" class="mep-empty-state-sm">
              {{ t('meta.no_desc_found') }}
            </div>
            <div v-else-if="!descFetched" class="mep-empty-state-sm">
              {{ t('meta.enter_title_hint') }}
            </div>
            <div v-else class="mep-desc-list">
              <div v-for="src in descSources" :key="src.source + src.name" class="mep-desc-source">
                <div class="mep-desc-source-header">
                  <div class="mep-desc-source-icon">
                    <img v-if="src.source === 'gog'"   src="/icons/gog.ico"   width="16" height="16" alt="GOG"   @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'steam'"  src="/icons/Steam.ico" width="16" height="16" alt="Steam" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'rawg'"   src="/icons/RAWG.ico"  width="16" height="16" alt="RAWG"  @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'igdb'"   src="/icons/igdb.ico"  width="16" height="16" alt="IGDB"  @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else :src="pluginLogoUrl(src.source)" width="16" height="16" :alt="src.source" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  </div>
                  <div class="mep-desc-source-name">{{ src.name }}</div>
                  <button class="mep-desc-apply-btn" @click="applyDescription(src)">{{ t('meta.use_description') }}</button>
                </div>
                <div class="mep-desc-preview">
                  {{ src.description.replace(/<[^>]+>/g, ' ').slice(0, 400) }}{{ src.description.length > 400 ? '…' : '' }}
                </div>
              </div>
            </div>

            <!-- Manual edit (always visible below sources) -->
            <div class="mep-form" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--glass-border)">
              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.full_desc') }} <span class="mep-field-hint">({{ t('meta.html_hint') }})</span> <TranslateButton :text="editFields.description || ''" @translated="tr => editFields.description = tr" /></label>
                <textarea v-model="editFields.description" class="mep-textarea" rows="7" :placeholder="t('meta.full_desc_ph')" />
              </div>
              <div class="mep-field" style="margin-top:10px">
                <label class="mep-field-label">{{ t('meta.short_desc') }} <TranslateButton :text="editFields.description_short || ''" @translated="tr => editFields.description_short = tr" /></label>
                <textarea v-model="editFields.description_short" class="mep-textarea" rows="3" :placeholder="t('meta.short_desc_ph')" />
              </div>
            </div>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- DETAILS TAB (manual edit)                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'details'" class="mep-tab-content">

            <!-- Search & Fill section -->
            <div class="mep-search-row">
              <input v-model="detailQuery" class="mep-search-input" :placeholder="t('meta.search_title_ph')" @keydown.enter="loadDetails(true)" />
              <button class="mep-search-btn" :disabled="detailLoading" @click="loadDetails(true)">
                <div v-if="detailLoading" class="mep-spinner mep-spinner--sm" />
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                {{ t('meta.fetch') }}
              </button>
            </div>

            <div v-if="detailLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.fetching_details') }}</div>
            <div v-else-if="detailFetched && !detailSources.length" class="mep-empty-state-sm">{{ t('meta.no_detail_results') }}</div>
            <div v-else-if="!detailFetched" class="mep-empty-state-sm">{{ t('meta.enter_title_fetch') }}</div>
            <div v-else class="mep-detail-sources">
              <div v-if="detailSources.some(s => s.rating != null)" style="display:flex;justify-content:flex-end;margin-bottom:6px">
                <button class="mep-desc-apply-btn" @click="applyAllRatings" :title="t('meta.apply_all_ratings')">⭐ {{ t('meta.apply_all_ratings') }}</button>
              </div>
              <div v-for="src in detailSources" :key="src.source + src.name" class="mep-detail-source">
                <div class="mep-desc-source-header">
                  <div class="mep-desc-source-icon">
                    <img v-if="src.source === 'gog'"   src="/icons/gog.ico"   width="16" height="16" alt="GOG"   @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'steam'"  src="/icons/Steam.ico" width="16" height="16" alt="Steam" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'rawg'"   src="/icons/RAWG.ico"  width="16" height="16" alt="RAWG"  @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else-if="src.source === 'igdb'"   src="/icons/igdb.ico"  width="16" height="16" alt="IGDB"  @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    <img v-else :src="pluginLogoUrl(src.source)" width="16" height="16" :alt="src.source" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  </div>
                  <div class="mep-desc-source-name">{{ src.name }}</div>
                  <button class="mep-desc-apply-btn" @click="applyDetails(src)">{{ t('meta.apply') }}</button>
                </div>
                <div class="mep-detail-grid">
                  <span v-if="src.developer" class="mep-detail-chip"><b>{{ t('meta.developer') }}:</b> {{ src.developer }}</span>
                  <span v-if="src.publisher" class="mep-detail-chip"><b>{{ t('meta.publisher') }}:</b> {{ src.publisher }}</span>
                  <span v-if="src.release_date" class="mep-detail-chip"><b>{{ t('meta.release_date') }}:</b> {{ src.release_date }}</span>
                  <span v-if="src.source === 'gog'   && src.rating != null" class="mep-detail-chip"><b>GOG:</b> {{ src.rating.toFixed(1) }}/5</span>
                  <span v-if="src.source === 'rawg'  && src.rating != null" class="mep-detail-chip"><b>RAWG:</b> {{ (src.rating/2).toFixed(1) }}/5</span>
                  <span v-if="src.source === 'igdb'  && src.rating != null" class="mep-detail-chip"><b>IGDB:</b> {{ Math.round(src.rating) }}/100</span>
                  <span v-if="src.source === 'steam' && src.rating != null" class="mep-detail-chip"><b>Metacritic:</b> {{ Math.round(src.rating * 10) }}/100</span>
                  <span v-if="src.os_windows || src.os_mac || src.os_linux" class="mep-detail-chip">
                    <b>OS:</b> {{ [src.os_windows && 'Win', src.os_mac && 'Mac', src.os_linux && 'Linux'].filter(Boolean).join(', ') }}
                  </span>
                  <span v-if="Object.keys(src.languages).length" class="mep-detail-chip">
                    <b>{{ t('meta.languages') }}:</b> {{ Object.values(src.languages).slice(0, 5).join(', ') }}{{ Object.keys(src.languages).length > 5 ? '…' : '' }}
                  </span>
                  <span v-if="src.genres?.length" class="mep-detail-chip"><b>{{ t('meta.genres') }}:</b> {{ src.genres.slice(0,4).join(', ') }}</span>
                </div>
              </div>
            </div>

            <div class="mep-form" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--glass-border)">


              <div class="mep-form-section-label">{{ t('meta.cover_images') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.cover_url') }}</label>
                <div class="mep-field-row">
                  <input v-model="manualCoverUrl" class="mep-input" placeholder="https://…" />
                  <button class="mep-apply-btn" :disabled="!manualCoverUrl" @click="applyManualCover">{{ t('meta.apply') }}</button>
                </div>
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.hero_url') }}</label>
                <div class="mep-field-row">
                  <input v-model="selectedBackground" class="mep-input" :placeholder="t('meta.hero_url_ph')" />
                </div>
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.logo_url') }}</label>
                <div class="mep-field-row">
                  <input v-model="selectedLogo" class="mep-input" :placeholder="t('meta.logo_url_ph')" />
                </div>
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.info') }}</div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.developer') }}</label>
                  <input v-model="editFields.developer" class="mep-input" :placeholder="t('meta.developer_ph')" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.publisher') }}</label>
                  <input v-model="editFields.publisher" class="mep-input" :placeholder="t('meta.publisher_ph')" />
                </div>
              </div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.release_date') }}</label>
                  <input v-model="editFields.release_date" class="mep-input" placeholder="YYYY-MM-DD" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.gog_rating') }} <span class="mep-field-hint">(0–5)</span></label>
                  <input v-model.number="editFields.rating" class="mep-input" type="number" min="0" max="5" step="0.1" />
                </div>
              </div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.ttb_main') }} <span class="mep-field-hint">(h)</span></label>
                  <input v-model.number="editFields.hltb_main_h" class="mep-input" type="number" min="0" step="0.1" placeholder="e.g. 20.5" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.ttb_complete') }} <span class="mep-field-hint">(h)</span></label>
                  <input v-model.number="editFields.hltb_complete_h" class="mep-input" type="number" min="0" step="0.1" placeholder="e.g. 51" />
                </div>
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.external_ratings') }}</div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">RAWG <span class="mep-field-hint">(0–5)</span></label>
                  <input v-model.number="editFields.meta_rawg" class="mep-input" type="number" min="0" max="5" step="0.01" placeholder="e.g. 4.2" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">IGDB <span class="mep-field-hint">(0–100)</span></label>
                  <input v-model.number="editFields.meta_igdb" class="mep-input" type="number" min="0" max="100" step="0.1" placeholder="e.g. 87" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">Metacritic <span class="mep-field-hint">(0–100)</span></label>
                  <input
                    :value="editFields.meta_steam != null ? Math.round(editFields.meta_steam * 10) : ''"
                    @input="(e) => { const v = parseFloat((e.target as HTMLInputElement).value); editFields.meta_steam = isNaN(v) ? null : v / 10 }"
                    class="mep-input" type="number" min="0" max="100" step="1" placeholder="e.g. 85"
                  />
                </div>
              </div>

              <template v-if="pluginRatingRows.length">
                <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.plugin_ratings') }}</div>

                <div class="mep-form-row" style="flex-wrap:wrap;">
                  <div v-for="r in pluginRatingRows" :key="r.key" class="mep-field">
                    <label class="mep-field-label">{{ pluginProviderName(r.key) }} <span class="mep-field-hint">(0–10)</span></label>
                    <input v-model.number="r.value" class="mep-input" type="number" min="0" max="10" step="0.1" placeholder="e.g. 8.5" />
                  </div>
                </div>
              </template>

              <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.platform_languages') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.os') }}</label>
                <div class="mep-os-checks">
                  <label class="mep-os-check-label"><input type="checkbox" v-model="editFields.os_windows" /><span>Windows</span></label>
                  <label class="mep-os-check-label"><input type="checkbox" v-model="editFields.os_mac" /><span>macOS</span></label>
                  <label class="mep-os-check-label"><input type="checkbox" v-model="editFields.os_linux" /><span>Linux</span></label>
                </div>
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.languages') }} <span class="mep-field-hint">({{ t('meta.lang_hint') }})</span></label>
                <input v-model="editFields.languages" class="mep-input" placeholder="en, pl, de, fr, es…" />
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.categories') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.genres') }} <span class="mep-field-hint">({{ t('meta.comma_hint') }})</span></label>
                <input v-model="editFields.genres" class="mep-input" placeholder="Action, RPG, Strategy…" />
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.themes') }} <span class="mep-field-hint">({{ t('meta.comma_hint') }})</span></label>
                <input v-model="editFields.tags" class="mep-input" placeholder="Open World, Multiplayer, Co-op…" />
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.features') }} <span class="mep-field-hint">({{ t('meta.comma_hint') }})</span></label>
                <input v-model="editFields.features" class="mep-input" placeholder="Achievements, Controller Support, Cloud Saves…" />
              </div>

              <template v-if="libraryKind === 'games'">
                <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.libraries') }}</div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.libraries') }} <span class="mep-field-hint">({{ t('meta.libraries_hint') }})</span></label>
                  <div style="display:flex;flex-direction:column;gap:9px;margin-top:4px;">
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">
                      <input type="checkbox" v-model="inDefaultLibrary" />
                      <span style="width:10px;height:10px;border-radius:3px;background:var(--pl);flex-shrink:0;"></span>
                      <span>{{ t('libraries.kind_custom') }}</span>
                    </label>
                    <label v-for="c in collectionLibs" :key="c.slug" style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">
                      <input type="checkbox" :value="c.slug" v-model="selectedCollections" />
                      <span :style="{ width:'10px', height:'10px', borderRadius:'3px', background: c.color || 'var(--pl)', flexShrink: 0 }"></span>
                      <span>{{ c.name }}</span>
                    </label>
                    <span v-if="!collectionLibs.length" class="mep-field-hint">{{ t('meta.no_collections') }}</span>
                  </div>
                </div>
              </template>

              <!-- Collections - admin-curated groupings. Games library only:
                   GOG catalog games live on GOG's servers, not locally, so they
                   are not collectable (only games in the local library are). -->
              <template v-if="libraryKind === 'games'">
                <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.collections') }}</div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.collections') }} <span class="mep-field-hint">({{ t('meta.collections_hint') }})</span></label>
                  <div style="display:flex;flex-direction:column;gap:9px;margin-top:4px;">
                    <label v-for="c in allCollections" :key="c.slug" style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">
                      <input type="checkbox" :value="c.slug" v-model="gameCollections" />
                      <span style="width:10px;height:10px;border-radius:3px;background:var(--pl);flex-shrink:0;"></span>
                      <span>{{ c.name }}<span v-if="c.library" class="mep-field-hint"> · {{ collectionLibLabel(c.library) }}</span></span>
                    </label>
                    <span v-if="!allCollections.length" class="mep-field-hint">{{ t('meta.no_collections_yet') }}</span>
                  </div>
                </div>
              </template>

              <!-- Per-game access (admin only): allow-list presentation. Every
                   user is ticked (has access) by default; un-ticking removes
                   their access - e.g. keep a title out of a child's account. -->
              <template v-if="libraryKind === 'games' && isAdmin">
                <div class="mep-form-section-label" style="margin-top:4px;">{{ t('meta.access') }}</div>
                <div class="mep-field">
                  <label class="mep-field-label"><span class="mep-field-hint">{{ t('meta.access_hint') }}</span></label>
                  <div style="display:flex;flex-direction:column;gap:9px;margin-top:4px;">
                    <label v-for="u in accessUsers" :key="u.id" style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">
                      <input type="checkbox" :value="u.id" v-model="allowedUserIds" />
                      <span>{{ u.username }} <span class="mep-field-hint">({{ u.role }})</span></span>
                    </label>
                    <span v-if="!accessUsers.length" class="mep-field-hint">{{ t('meta.access_no_users') }}</span>
                  </div>
                </div>
              </template>

            </div>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- REQUIREMENTS TAB                                                   -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'requirements'" class="mep-tab-content">

            <!-- Current requirements -->
            <div v-if="currentReqRows.length" class="mep-source-section">
              <div class="mep-source-head">{{ t('meta.current_min_reqs') }}</div>
              <div class="srl-req-table">
                <div v-for="row in currentReqRows" :key="row.key" class="srl-req-row">
                  <span class="srl-req-key">{{ row.key }}</span>
                  <span class="srl-req-val">{{ row.val }}</span>
                </div>
              </div>
              <button class="mep-ghost-btn srl-clear-btn" @click="clearRequirements">{{ t('meta.clear_reqs') }}</button>
            </div>
            <div v-else class="mep-source-section">
              <div class="mep-source-head">{{ t('meta.current_reqs') }}</div>
              <span class="srl-no-data">{{ t('meta.no_reqs') }}</span>
            </div>

            <!-- SRL Search -->
            <div class="mep-source-section">
              <div class="mep-source-head">
                <img src="/icons/srl.ico" width="14" height="14" style="border-radius:2px;flex-shrink:0" />
                {{ t('meta.srl') }}
              </div>
              <div class="srl-search-row">
                <input v-model="srlQuery" class="mep-input" placeholder="Game title…" @keydown.enter="srlSearch" />
                <button class="mep-apply-btn" :disabled="srlSearching || !srlQuery.trim()" @click="srlSearch">
                  <div v-if="srlSearching" class="mep-spinner mep-spinner--sm" />
                  <span v-else>{{ t('meta.search') }}</span>
                </button>
              </div>
              <div v-if="srlError" class="srl-error">{{ srlError }}</div>
              <div v-if="srlMatches.length" class="srl-matches">
                <div
                  v-for="m in srlMatches" :key="m.url"
                  class="srl-match-row"
                  :class="{ 'srl-match-row--active': srlSelectedUrl === m.url }"
                  @click="srlSelectMatch(m.url)"
                >
                  <span class="srl-match-score">{{ Math.round(m.score * 100) }}%</span>
                  <span class="srl-match-title">{{ m.title }}</span>
                  <button class="mep-apply-btn srl-fetch-btn" :disabled="srlFetching" @click.stop="srlFetchUrl(m.url)">
                    <div v-if="srlFetching && srlSelectedUrl === m.url" class="mep-spinner mep-spinner--sm" />
                    <span v-else>{{ t('meta.fetch') }}</span>
                  </button>
                </div>
              </div>
              <div v-if="srlPreview" class="srl-preview">
                <div class="srl-preview-head">{{ t('meta.preview_min') }}</div>
                <div class="srl-req-table">
                  <div v-for="(val, key) in srlPreview.minimum" :key="key" class="srl-req-row">
                    <span class="srl-req-key">{{ srlKeyLabel(String(key)) }}</span>
                    <span class="srl-req-val">{{ val }}</span>
                  </div>
                </div>
                <div class="srl-apply-row">
                  <button class="mep-apply-btn" @click="applyReqPreview(srlPreview!); srlPreview = null">{{ t('meta.apply_to_game') }}</button>
                  <button class="mep-ghost-btn" @click="srlPreview = null">{{ t('meta.discard') }}</button>
                </div>
              </div>
            </div>

            <!-- Steam Requirements -->
            <div class="mep-source-section">
              <div class="mep-source-head">
                <img src="/icons/Steam.ico" width="14" height="14" style="border-radius:2px;flex-shrink:0" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                {{ t('meta.steam_reqs') }}
              </div>
              <div class="srl-search-row">
                <input v-model="steamReqQuery" class="mep-input" placeholder="Title, App ID or Steam URL…" @keydown.enter="fetchSteamReqs" />
                <button class="mep-apply-btn" :disabled="steamReqLoading || !steamReqQuery.trim()" @click="fetchSteamReqs">
                  <div v-if="steamReqLoading" class="mep-spinner mep-spinner--sm" />
                  <span v-else>{{ t('meta.search') }}</span>
                </button>
              </div>
              <div v-if="steamReqError" class="srl-error">{{ steamReqError }}</div>
              <div v-if="steamReqPreview" class="srl-preview">
                <div class="srl-preview-head">{{ t('meta.preview_min') }}</div>
                <div class="srl-req-table">
                  <div v-for="(val, key) in steamReqPreview.minimum" :key="key" class="srl-req-row">
                    <span class="srl-req-key">{{ srlKeyLabel(String(key)) }}</span>
                    <span class="srl-req-val">{{ val }}</span>
                  </div>
                </div>
                <div class="srl-apply-row">
                  <button class="mep-apply-btn" @click="applyReqPreview(steamReqPreview!); steamReqPreview = null">{{ t('meta.apply_to_game') }}</button>
                  <button class="mep-ghost-btn" @click="steamReqPreview = null">{{ t('meta.discard') }}</button>
                </div>
              </div>
            </div>

            <!-- Manual entry -->
            <div class="mep-source-section">
              <div class="mep-source-head">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;opacity:.7"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                {{ t('meta.manual_entry') }}
              </div>
              <div class="srl-manual-grid">
                <template v-for="field in manualFields" :key="field.key">
                  <label class="srl-req-key" style="padding-top:5px">{{ field.label }}</label>
                  <input v-model="manualMin[field.key]" class="mep-input mep-input--sm" placeholder="Minimum…" />
                </template>
              </div>
              <div class="srl-apply-row" style="margin-top:8px">
                <button class="mep-apply-btn" @click="applyManualReqs">{{ t('meta.apply_to_game') }}</button>
              </div>
            </div>

          </div>

          <!-- Plugin-registered tabs (e.g. Steam Deck Compatibility) -->
          <div v-if="isPluginTab(activeTab)" class="mep-tab-content">
            <div ref="pluginTabHost" class="mep-plugin-tab"></div>
          </div>

        </div>
      </div>

      <!-- ── Footer ──────────────────────────────────────────────────────────── -->
      <div class="mep-footer">
        <div class="mep-save-status">
          <span v-if="saveError" class="mep-err">{{ saveError }}</span>
          <span v-else-if="saveOk" class="mep-ok">✓ {{ t('meta.saved') }}</span>
          <span v-else-if="notifyMsg" :class="notifyOk ? 'mep-ok' : 'mep-err'">{{ notifyMsg }}</span>
        </div>
        <div class="mep-footer-actions">
          <button v-if="notifyEnabled" class="mep-btn-notify" :disabled="notifying" @click="resendNotification" :title="t('meta.resend_notification_hint')">
            <div v-if="notifying" class="mep-spinner mep-spinner--sm" />
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            {{ t('meta.resend_notification') }}
          </button>
          <button class="mep-btn-cancel" @click="$emit('close')">{{ t('meta.cancel') }}</button>
          <button class="mep-btn-save btn-save-action" :disabled="saving || !hasChanges" @click="save">
            <div v-if="saving" class="mep-spinner mep-spinner--sm" />
            {{ saving ? t('meta.saving') : t('meta.save_changes') }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useLibrariesStore } from '@/stores/libraries'
import { useAuthStore } from '@/stores/auth'
import { useCollectionsStore } from '@/stores/collections'
import client from '@/services/api/client'
import TranslateButton from '@/components/common/TranslateButton.vue'
import { useI18n } from '@/i18n'
import { LANG_MAP, resolveLang } from '@/utils/langMap'
import { getMetadataTabs, type MetadataTab, type MetadataTabContext } from '@/themes/index'

const { t } = useI18n()

interface LibGame {
  id: number
  title: string
  gog_id?: number
  gog_game_id?: number | null
  cover_path: string | null
  cover_url?: string | null
  background_path: string | null
  background_url?: string | null
  logo_path: string | null
  logo_url?: string | null
  icon_path: string | null
  icon_url?: string | null
  video_path?: string | null
  developer: string | null
  publisher: string | null
  release_date: string | null
  rating: number | null
  meta_ratings: Record<string, number> | null
  hltb_main_s?: number | null
  hltb_complete_s?: number | null
  description: string | null
  description_short: string | null
  genres: string[] | null
  tags: string[] | null
  features: string[] | null
  os_windows: boolean
  os_mac: boolean
  os_linux: boolean
  languages: Record<string, string> | null
  screenshots: string[] | null
  videos: { provider: string; video_id: string; thumbnail_id?: string }[] | null
  requirements: Record<string, any> | null
}

interface CoverOption {
  url: string; thumb?: string; type: 'static' | 'animated'; label: string; author?: string; asset_type?: string
  _source?: string; _sourceIcon?: string
}

const props = defineProps<{ game: LibGame; apiPrefix?: string }>()
const emit  = defineEmits<{
  (e: 'close'): void
  (e: 'saved', data: Record<string, unknown>): void
}>()

// API prefix - /library/games for Games Library, /gog/library/games for GOG Library
const baseApi = computed(() => props.apiPrefix || '/library/games')

// Plugin-registered tabs that target this panel's library (games / gog / all).
// A catalogue entry (PC Ports store) reuses this panel with its own apiPrefix;
// it is not a game, so the game-only sections (library membership, collections,
// per-game access) gate off it the same way the GOG library already does.
const libraryKind = computed(() =>
  baseApi.value.includes('catalog-entries') ? 'catalog'
  : baseApi.value.includes('/gog/') ? 'gog'
  : 'games',
)
const isCatalog = computed(() => libraryKind.value === 'catalog')

// ── Library membership (Games library + user-created libraries) ───────────────
const libsStore = useLibrariesStore()
const collectionLibs = computed(() => libsStore.libraries.filter(l => l.kind === 'custom_lib'))
const inDefaultLibrary = ref(true)
const selectedCollections = ref<string[]>([])
const initialInDefault = ref(true)
const initialCollections = ref<string[]>([])
// Membership is a separate save target, so it must count towards "has changes"
// for the Save button to enable when the user only edits library checkboxes.
const membershipChanged = computed(() =>
  inDefaultLibrary.value !== initialInDefault.value ||
  [...selectedCollections.value].sort().join(',') !== [...initialCollections.value].sort().join(','),
)
function _snapshotMembership() {
  initialInDefault.value = inDefaultLibrary.value
  initialCollections.value = [...selectedCollections.value]
}
async function loadMemberships() {
  libsStore.fetch()
  try {
    const { data } = await client.get(`/libraries/membership/${props.game.id}`)
    inDefaultLibrary.value = data.in_default_library !== false
    selectedCollections.value = Array.isArray(data.collections) ? data.collections : []
  } catch { /* ignore - leave defaults */ }
  _snapshotMembership()
}

// ── Collection membership (admin-curated game groupings) ─────────────────────
// Independent of library membership above: a game keeps its home library and
// can additionally belong to any number of collections. Applies to both the
// Games and GOG libraries (any LibraryGame row), unlike user-library membership
// which is Games-only.
const collectionsStore = useCollectionsStore()
const allCollections = computed(() => collectionsStore.list)
// Container library name shown next to each collection (collections can live in
// several containers, so the name alone may be ambiguous).
function collectionLibLabel(slug: string | null): string { return slug ? libsStore.label(slug) : '' }
const gameCollections = ref<string[]>([])          // collection slugs this game is in
const initialGameCollections = ref<string[]>([])
const gameCollectionsChanged = computed(() =>
  [...gameCollections.value].sort().join(',') !== [...initialGameCollections.value].sort().join(','),
)
function _snapshotGameCollections() {
  initialGameCollections.value = [...gameCollections.value]
}
async function loadGameCollections() {
  if (!collectionsStore.loaded) collectionsStore.fetch()
  try {
    const { data } = await client.get(`/collections/membership/${props.game.id}`)
    gameCollections.value = Array.isArray(data.collections) ? data.collections : []
  } catch { /* ignore - leave empty */ }
  _snapshotGameCollections()
}
// ── Per-game access (admin: control which users can see this game) ────────────
// Allow-list presentation: every non-admin user is ticked (has access) by
// default; un-ticking a user removes their access to this game (e.g. keep a
// title out of a child's account). Stored server-side as a deny list; admins
// always keep access.
const _authStore = useAuthStore()
const isAdmin = computed(() => _authStore.user?.role === 'admin')
const accessUsers = ref<{ id: number; username: string; role: string }[]>([])
const allowedUserIds = ref<number[]>([])   // ticked = has access
const initialAllowed = ref<number[]>([])
const accessChanged = computed(() =>
  [...allowedUserIds.value].sort().join(',') !== [...initialAllowed.value].sort().join(','),
)
// Deny list sent to the server = every listed (non-admin) user who is NOT ticked.
const deniedUserIds = computed(() =>
  accessUsers.value.map(u => u.id).filter(id => !allowedUserIds.value.includes(id)),
)
function _snapshotAccess() { initialAllowed.value = [...allowedUserIds.value] }
async function loadGameAccess() {
  if (!isAdmin.value) return
  try {
    const [ar, ur] = await Promise.all([
      client.get(`/library/games/${props.game.id}/access`),
      client.get('/users'),
    ])
    const denied: number[] = Array.isArray(ar.data?.denied_user_ids) ? ar.data.denied_user_ids : []
    accessUsers.value = (Array.isArray(ur.data) ? ur.data : [])
      .filter((u: any) => u.role !== 'admin')   // admins always have access
      .map((u: any) => ({ id: u.id, username: u.username, role: u.role }))
    // Everyone starts ticked (has access) except those on the deny list.
    allowedUserIds.value = accessUsers.value.map(u => u.id).filter(id => !denied.includes(id))
  } catch { /* ignore */ }
  _snapshotAccess()
}

const pluginTabs = computed<MetadataTab[]>(() =>
  getMetadataTabs().filter(tb => !tb.library || tb.library === 'all' || tb.library === libraryKind.value)
)
function isPluginTab(id: string): boolean {
  return pluginTabs.value.some(tb => tb.id === id)
}

const tabs = computed(() => [
  { id: 'cover',        label: t('meta.tab_cover')        },
  { id: 'background',   label: t('meta.tab_hero')         },
  { id: 'logo',         label: t('meta.tab_logo')         },
  { id: 'icon',         label: t('meta.tab_icon')         },
  { id: 'screenshots',  label: t('meta.tab_screenshots')  },
  // A catalogue entry has no trailer column, so the video tab would save
  // nothing - drop it there while keeping it for real games.
  ...(isCatalog.value ? [] : [{ id: 'video', label: t('meta.tab_video') }]),
  { id: 'description',  label: t('meta.tab_description')  },
  { id: 'details',      label: t('meta.tab_details')      },
  { id: 'requirements', label: t('meta.tab_requirements') },
  ...pluginTabs.value.map(tb => ({ id: tb.id, label: tb.label })),
])
const activeTab = ref('cover')

// ── Plugin tab mounting (vanilla DOM via registerMetadataTab) ────────────────
const pluginTabHost = ref<HTMLElement | null>(null)
let _pluginCleanup: (() => void) | null = null
// A plugin tab can flag unsaved changes (enables Save) and register a handler
// that contributes a partial payload to the panel's Save request.
const pluginDirty = ref(false)
let _pluginSaveHandler:
  | (() => Promise<Record<string, unknown> | void> | Record<string, unknown> | void)
  | null = null

function _mountPluginTab() {
  if (_pluginCleanup) { try { _pluginCleanup() } catch { /* ignore */ } _pluginCleanup = null }
  _pluginSaveHandler = null
  pluginDirty.value = false
  const host = pluginTabHost.value
  if (!host || !isPluginTab(activeTab.value)) return
  const tab = pluginTabs.value.find(tb => tb.id === activeTab.value)
  if (!tab) return
  host.innerHTML = ''
  const ctx: MetadataTabContext = {
    game: props.game as unknown as Record<string, unknown>,
    apiPrefix: baseApi.value,
    close: () => emit('close'),
    save: (d) => emit('saved', d || {}),
    markDirty: () => { pluginDirty.value = true },
    onSave: (handler) => { _pluginSaveHandler = handler },
  }
  try {
    const ret = tab.mount(host, ctx)
    if (typeof ret === 'function') _pluginCleanup = ret
  } catch (e) { console.error('Metadata tab mount failed', e) }
}

watch([activeTab, pluginTabHost], () => nextTick(_mountPluginTab))
onUnmounted(() => {
  if (_pluginCleanup) { try { _pluginCleanup() } catch { /* ignore */ } }
  _stopVideoPoll()
})

// ── Cover selection ────────────────────────────────────────────────────────────
const selectedCover         = ref(props.game.cover_path || props.game.cover_url || '')
const selectedCoverThumb    = ref('')
const selectedCoverAnimated = ref(false)
const selectedBackground    = ref(props.game.background_path || props.game.background_url || '')
const selectedLogo          = ref(props.game.logo_path || props.game.logo_url || '')
const selectedIcon          = ref(props.game.icon_path || props.game.icon_url || '')

// ── IGDB covers ───────────────────────────────────────────────────────────────
const igdbQuery    = ref(props.game.title)
const igdbLoading  = ref(false)
const igdbSearched = ref(false)
const igdbCovers   = ref<CoverOption[]>([])

// ── RAWG backgrounds ──────────────────────────────────────────────────────────
const rawgQuery    = ref(props.game.title)
const rawgLoading  = ref(false)
const rawgSearched = ref(false)
const rawgCovers   = ref<CoverOption[]>([])

// ── SGDB Covers (grids) ───────────────────────────────────────────────────────
const sgdbCoverQuery    = ref(props.game.title)
const sgdbCoverLoading  = ref(false)
const sgdbCoverSearched = ref(false)
const sgdbCoverResults  = ref<CoverOption[]>([])
const sgdbCoverAnimated = ref<'any' | 'only' | 'exclude'>('any')

// ── Unified cover search ─────────────────────────────────────────────────────
const coverSearchQuery  = ref(props.game.title)
const coverSearching    = ref(false)
const coverSearchDone   = ref(false)
const coverFilter       = ref<'all' | 'static' | 'animated'>('all')
const allCoverResults   = ref<CoverOption[]>([])

const filteredCoverResults = computed(() => {
  if (coverFilter.value === 'all') return allCoverResults.value
  if (coverFilter.value === 'animated') return allCoverResults.value.filter(c => c.type === 'animated')
  return allCoverResults.value.filter(c => c.type !== 'animated')
})

function setCoverFilter(val: typeof coverFilter.value) {
  coverFilter.value = val
}

// ── SGDB Backgrounds (heroes) ─────────────────────────────────────────────────
const sgdbBgQuery    = ref(props.game.title)
const sgdbBgLoading  = ref(false)
const sgdbBgSearched = ref(false)
const sgdbBgResults  = ref<CoverOption[]>([])

// ── Unified hero/background search ───────────────────────────────────────────
const heroSearchQuery = ref(props.game.title)
const heroSearching   = ref(false)
const heroSearchDone  = ref(false)
const allHeroResults  = ref<CoverOption[]>([])

// ── Unified video search ────────────────────────────────────────────────────
const vidAllSearching = ref(false)
const vidAllSearchDone = ref(false)
const vidAllResults = ref<{video_id: string; provider: string; thumb: string; label: string; author: string}[]>([])

// ── Unified screenshots search ──────────────────────────────────────────────
const ssAllSearching = ref(false)
const ssAllSearchDone = ref(false)
const ssAllResults = ref<{url: string; thumb?: string; author?: string; _source?: string; _sourceIcon?: string}[]>([])

// ── Unified icon search ─────────────────────────────────────────────────────
const iconSearchQuery = ref(props.game.title)
const iconSearching   = ref(false)
const iconSearchDone  = ref(false)
const allIconResults  = ref<CoverOption[]>([])

// ── Unified logo search ─────────────────────────────────────────────────────
const logoSearchQuery = ref(props.game.title)
const logoSearching   = ref(false)
const logoSearchDone  = ref(false)
const allLogoResults  = ref<CoverOption[]>([])

// ── SGDB Logos/Icons ──────────────────────────────────────────────────────────
const sgdbLogoType     = ref<'logos' | 'icons'>('logos')
const sgdbLogoQuery    = ref(props.game.title)
const sgdbLogoLoading  = ref(false)
const sgdbLogoSearched = ref(false)
const sgdbLogoResults  = ref<CoverOption[]>([])

// ── SGDB Icons (separate tab) ─────────────────────────────────────────────────
const sgdbIconQuery    = ref(props.game.title)
const sgdbIconLoading  = ref(false)
const sgdbIconSearched = ref(false)
const sgdbIconResults  = ref<CoverOption[]>([])

async function searchSgdbIcons() {
  sgdbIconLoading.value = true; sgdbIconSearched.value = false; sgdbIconResults.value = []
  try {
    const q = encodeURIComponent(sgdbIconQuery.value || props.game.title)
    const { data } = await client.get(
      `${baseApi.value}/${props.game.id}/covers?source=steamgriddb&q=${q}&asset_type=icons&animated=any`
    )
    sgdbIconResults.value = data; sgdbIconSearched.value = true
  } catch { sgdbIconSearched.value = true }
  finally { sgdbIconLoading.value = false }
}

// ── Screenshots ───────────────────────────────────────────────────────────────
const editScreenshots  = ref<string[]>([...(props.game.screenshots || [])])
const screenshotsMode  = ref<'add' | 'replace'>('add')
const ssNewUrl         = ref('')
const ssSource         = ref<string>('igdb')
const pluginProviders = ref<{ id: string; name: string; logo: string }[]>([])

;(async () => {
  try {
    const { data } = await client.get('/plugins')
    if (Array.isArray(data)) {
      for (const p of data) {
        if (p.enabled && p.plugin_type === 'metadata') {
          const pid = p.plugin_id.replace(/-metadata$/, '')
          pluginProviders.value.push({
            id: pid,
            name: p.name.replace(/ Metadata.*$/i, '').replace(/ Scraper$/i, ''),
            logo: `/api/plugins/${p.plugin_id}/logo`,
          })
        }
      }
    }
  } catch {}
})()
const ssSearchQuery    = ref(props.game.title)
const ssSearchLoading  = ref(false)
const ssSearched       = ref(false)
const ssSearchResults  = ref<{ url: string; thumb?: string; author?: string }[]>([])

// ── Video ─────────────────────────────────────────────────────────────────────
const _firstVideoId = () => {
  const videos = props.game.videos || []
  const first = videos[0]
  if (!first) return ''
  if (typeof first === 'string') return ''
  return (first as any).video_id || ''
}
const editVideoId     = ref(_firstVideoId())
const editVideoUrl    = ref('')
const vidSearchQuery  = ref(props.game.title)
const vidSearchLoading = ref(false)
const vidSearched      = ref(false)
const vidSearchResults = ref<{ video_id: string; provider: string; thumb: string; label: string; author: string }[]>([])

// ── Local trailer copy (downloaded via yt-dlp or uploaded; served from
// /resources like covers - players prefer it over YouTube when present) ──────
const localVideoPath   = ref<string>(props.game.video_path || '')
const videoDownloading = ref(false)
const videoUploading   = ref(false)
const videoQuality     = ref('1080')
const videoError       = ref('')
let _videoPoll: ReturnType<typeof setInterval> | null = null

function _stopVideoPoll() {
  if (_videoPoll) clearInterval(_videoPoll)
  _videoPoll = null
  videoDownloading.value = false
}

// The server reports why a fetch failed as a stable code rather than yt-dlp's
// own text, which is three lines of links about exporting browser cookies.
function _videoErrorText(code: string): string {
  const known = [
    'age_restricted', 'private', 'unavailable', 'geo_blocked',
    'no_format', 'bot_check', 'network', 'no_file',
  ]
  return known.includes(code)
    ? t(`meta.video_err_${code}`)
    : t('meta.video_err_failed')
}

async function downloadLocalVideo() {
  if (!editVideoId.value || videoDownloading.value) return
  videoDownloading.value = true
  videoError.value = ''
  try {
    await client.post(`${baseApi.value}/${props.game.id}/video/download`, { video_id: editVideoId.value, quality: videoQuality.value })
  } catch (e: any) {
    videoDownloading.value = false
    videoError.value = e?.response?.data?.detail || t('meta.video_err_failed')
    return
  }
  // yt-dlp runs server-side in a background task, so the outcome comes back
  // from the status endpoint. Polling the game detail for a video_path could
  // only ever see success: a refusal looked exactly like "still working".
  let tries = 0
  _videoPoll = setInterval(async () => {
    tries++
    try {
      const r = await client.get(`${baseApi.value}/${props.game.id}/video/status`)
      const st = r.data?.state
      if (st === 'done' && r.data?.url) {
        localVideoPath.value = r.data.url
        _stopVideoPoll()
        emit('saved', { video_path: r.data.url })
        return
      }
      if (st === 'failed') {
        videoError.value = _videoErrorText(String(r.data?.error || ''))
        _stopVideoPoll()
        return
      }
    } catch { /* transient */ }
    if (tries > 60) {                    // give up after ~5 min
      videoError.value = t('meta.video_err_timeout')
      _stopVideoPoll()
    }
  }, 5000)
}

async function onLocalVideoFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || videoUploading.value) return
  videoUploading.value = true
  videoError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const r = await client.post(`${baseApi.value}/${props.game.id}/video/upload`, fd)
    if (r.data?.video_path) {
      localVideoPath.value = r.data.video_path
      emit('saved', { video_path: r.data.video_path })
    }
  } catch (e: any) {
    // The server rejects the wrong format with a 400 and anything over a
    // gigabyte with a 413, and both used to vanish: the file picker closed and
    // nothing at all happened on screen.
    videoError.value = e?.response?.data?.detail || t('meta.video_upload_failed')
  }
  videoUploading.value = false
}

async function removeLocalVideo() {
  try {
    await client.patch(`${baseApi.value}/${props.game.id}`, { video_path: null })
    localVideoPath.value = ''
    emit('saved', { video_path: null })
  } catch { /* permission */ }
}

// ── Details search (developer / publisher / OS / languages / rating) ──────────
interface DetailSource {
  source: string; name: string
  developer: string; publisher: string
  release_date: string; genres: string[]
  rating: number | null
  os_windows: boolean; os_mac: boolean; os_linux: boolean
  languages: Record<string, string>
}
const detailQuery   = ref(props.game.title || '')
const detailLoading = ref(false)
const detailFetched = ref(false)
const detailSources = ref<DetailSource[]>([])

async function loadDetails(force = false) {
  if (detailLoading.value) return
  if (detailFetched.value && !force) return
  detailLoading.value = true
  detailFetched.value = false
  detailSources.value = []
  const q   = encodeURIComponent(detailQuery.value.trim() || props.game.title || '')
  const id  = props.game.id

  const toSource = (src: string, label: string, d: any): DetailSource => ({
    source:       src,
    name:         label,
    developer:    d.developer   || '',
    publisher:    d.publisher   || '',
    release_date: d.release_date || '',
    genres:       d.genres      || [],
    rating:       d.rating ?? null,
    os_windows:   !!d.os_windows,
    os_mac:       !!d.os_mac,
    os_linux:     !!d.os_linux,
    languages:    d.languages   || {},
  })

  await Promise.allSettled([
    client.get(`${baseApi.value}/${id}/meta-sources?source=gog&q=${q}`)
      .then(({ data }) => { if (data.found) detailSources.value.push(toSource('gog', `GOG - ${data.name || detailQuery.value}`, data)) })
      .catch(() => {}),
    client.get(`${baseApi.value}/${id}/meta-sources?source=steam&q=${q}`)
      .then(({ data }) => { if (data.found) detailSources.value.push(toSource('steam', `Steam - ${data.name || detailQuery.value}`, data)) })
      .catch(() => {}),
    client.get(`${baseApi.value}/${id}/meta-sources?source=rawg&q=${q}`)
      .then(async ({ data }) => {
        if (!data.found || !data.candidates?.length) return
        const best = (data.candidates as any[]).find(c => _isTitleSimilar(detailQuery.value || props.game.title, c.name || ''))
        if (!best) return
        const { data: detail } = await client.get(`${baseApi.value}/${id}/meta-sources?source=rawg-detail&q=${best.slug || best.id}`)
        if (detail.found) detailSources.value.push(toSource('rawg', `RAWG - ${detail.name || best.name}`, detail))
      })
      .catch(() => {}),
    client.get(`${baseApi.value}/${id}/meta-sources?source=igdb&q=${q}`)
      .then(({ data }) => {
        if (!data.found || !data.candidates?.length) return
        const filtered = (data.candidates as any[]).filter(c => _isTitleSimilar(detailQuery.value || props.game.title, c.name || '')).slice(0, 1)
        for (const c of filtered) detailSources.value.push(toSource('igdb', `IGDB - ${c.name}`, c))
      })
      .catch(() => {}),
  ])

  detailFetched.value = true
  detailLoading.value = false
}

function applyDetails(src: DetailSource) {
  if (src.developer)      editFields.value.developer    = src.developer
  if (src.publisher)      editFields.value.publisher    = src.publisher
  if (src.release_date)   editFields.value.release_date = src.release_date
  if (src.genres?.length) editFields.value.genres       = src.genres.join(', ')
  if (src.os_windows)     editFields.value.os_windows   = true
  if (src.os_mac)         editFields.value.os_mac       = true
  if (src.os_linux)       editFields.value.os_linux     = true
  if (Object.keys(src.languages).length)
    editFields.value.languages = Object.keys(src.languages).join(', ')
  if (src.rating != null) {
    if (src.source === 'gog')   editFields.value.rating     = src.rating          // 0-5
    if (src.source === 'steam') editFields.value.meta_steam = src.rating          // 0-10 (MC/10)
    if (src.source === 'rawg')  editFields.value.meta_rawg  = src.rating / 2      // rawg-detail returns *2; store as 0-5
    if (src.source === 'igdb')  editFields.value.meta_igdb  = src.rating          // 0-100
  }
}

/** Apply ALL collected ratings from all loaded sources at once. */
function applyAllRatings() {
  for (const src of detailSources.value) {
    if (src.rating == null) continue
    if (src.source === 'gog')   editFields.value.rating     = src.rating
    if (src.source === 'steam') editFields.value.meta_steam = src.rating
    if (src.source === 'rawg')  editFields.value.meta_rawg  = src.rating / 2
    if (src.source === 'igdb')  editFields.value.meta_igdb  = src.rating
  }
}

// ── Description sources ────────────────────────────────────────────────────────
const descQuery   = ref(props.game.title || '')
const descLoading = ref(false)
const descFetched = ref(false)
interface DescSource { source: string; name: string; description: string; description_short: string; rating?: number | null }
const descSources = ref<DescSource[]>([])

/** Word-overlap similarity check - keeps unrelated results out (like in GOG panel). */
function _isTitleSimilar(query: string, result: string, threshold = 0.55): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(Boolean)
  const qWords = new Set(norm(query))
  const rWords = new Set(norm(result))
  if (!qWords.size || !rWords.size) return false
  const qStr = [...qWords].sort().join(' ')
  const rStr = [...rWords].sort().join(' ')
  if (qStr === rStr || qStr.includes(rStr) || rStr.includes(qStr)) return true
  const overlap = [...qWords].filter(w => rWords.has(w)).length
  const shorter = Math.min(qWords.size, rWords.size)
  return shorter > 0 ? overlap / shorter >= threshold : false
}

async function loadDescriptions(force = false) {
  if (descLoading.value) return
  if (descFetched.value && !force) return
  descLoading.value = true
  descFetched.value = false
  descSources.value = []
  const q = encodeURIComponent(descQuery.value.trim() || props.game.title || '')
  const id = props.game.id

  // ── GOG public API ────────────────────────────────────────────────────────
  try {
    const { data } = await client.get(`${baseApi.value}/${id}/meta-sources?source=gog&q=${q}`)
    if (data.found && data.description) {
      const ratingStr = data.rating ? ` · ${data.rating.toFixed(1)}/5` : ''
      descSources.value.push({
        source: 'gog', name: `GOG - ${data.name || descQuery.value}${ratingStr}`,
        description: data.description, description_short: data.description_short || '',
        rating: data.rating ?? null,
      })
    }
  } catch { /* GOG not available or no match */ }

  // ── Steam ─────────────────────────────────────────────────────────────────
  try {
    const { data } = await client.get(`${baseApi.value}/${id}/meta-sources?source=steam&q=${q}`)
    if (data.found && data.description) {
      const mcStr = data.rating != null ? ` · Metacritic: ${Math.round((data.rating ?? 0) * 10)}/100` : ''
      descSources.value.push({
        source: 'steam', name: `Steam${mcStr}`,
        description: data.description, description_short: data.description_short || '',
        rating: data.rating ?? null,
      })
    }
  } catch { /* Steam not available */ }

  // ── RAWG ──────────────────────────────────────────────────────────────────
  try {
    const { data: rawgSearch } = await client.get(`${baseApi.value}/${id}/meta-sources?source=rawg&q=${q}`)
    if (rawgSearch.found && rawgSearch.candidates?.length) {
      const best = (rawgSearch.candidates as any[]).find(
        c => _isTitleSimilar(descQuery.value || props.game.title, c.name || c.slug || '')
      )
      if (best) {
        const { data: rawgDetail } = await client.get(
          `${baseApi.value}/${id}/meta-sources?source=rawg-detail&q=${best.slug || best.id}`
        )
        if (rawgDetail.found && rawgDetail.description) {
          const rStr = rawgDetail.rating ? ` · Score: ${rawgDetail.rating.toFixed(1)}/10` : ''
          descSources.value.push({
            source: 'rawg', name: `RAWG - ${rawgDetail.name || best.name}${rStr}`,
            description: rawgDetail.description, description_short: '',
            rating: rawgDetail.rating ?? null,
          })
        }
      }
    }
  } catch { /* RAWG not available */ }

  // ── IGDB ──────────────────────────────────────────────────────────────────
  try {
    const { data: igdbData } = await client.get(`${baseApi.value}/${id}/meta-sources?source=igdb&q=${q}`)
    if (igdbData.found && igdbData.candidates?.length) {
      const filtered = (igdbData.candidates as any[])
        .filter(c => _isTitleSimilar(descQuery.value || props.game.title, c.name || ''))
        .slice(0, 3)
      for (const c of filtered) {
        if (c.description || c.summary) {
          descSources.value.push({
            source: 'igdb', name: `IGDB - ${c.name}`,
            description: c.description || c.summary || '',
            description_short: c.description_short || '',
          })
        }
      }
    }
  } catch { /* IGDB not available */ }

  // Plugin metadata providers (PPE.pl, etc.)
  try {
    const { data: pluginResults } = await client.get(`/plugins/metadata/search?q=${encodeURIComponent(descQuery.value.trim() || props.game.title || '')}`)
    if (Array.isArray(pluginResults) && pluginResults.length) {
      for (const pr of pluginResults) {
        try {
          const { data: detail } = await client.get(
            `/plugins/metadata/fetch?provider_id=${encodeURIComponent(pr.provider_id)}&game_id=${encodeURIComponent(pr.provider_game_id)}`
          )
          if (detail && detail.description) {
            const ratingStr = detail.rating ? ` - ${detail.rating}/10` : ''
            descSources.value.push({
              source: detail.provider_id || 'plugin',
              name: `${(detail.provider_id || 'Plugin').toUpperCase()} - ${detail.title || pr.name}${ratingStr}`,
              description: detail.description,
              description_short: '',
            })
          }
        } catch { /* individual plugin fetch failed */ }
      }
    }
  } catch { /* plugin search unavailable */ }

  descFetched.value = true
  descLoading.value = false
}

function applyDescription(src: DescSource) {
  editFields.value.description       = src.description
  editFields.value.description_short = src.description_short || ''
  if (src.rating != null) editFields.value.rating = src.rating
}

// ── Manual edit fields ─────────────────────────────────────────────────────────
const manualCoverUrl = ref('')
const editFields = ref({
  developer:         props.game.developer         || '',
  publisher:         props.game.publisher         || '',
  release_date:      props.game.release_date      || '',
  rating:            props.game.rating            ?? (null as number | null),
  hltb_main_h:       props.game.hltb_main_s     != null ? Math.round(props.game.hltb_main_s / 360) / 10 : (null as number | null),
  hltb_complete_h:   props.game.hltb_complete_s != null ? Math.round(props.game.hltb_complete_s / 360) / 10 : (null as number | null),
  meta_rawg:         props.game.meta_ratings?.['rawg']  ?? (null as number | null),
  meta_igdb:         props.game.meta_ratings?.['igdb']  ?? (null as number | null),
  meta_steam:        props.game.meta_ratings?.['steam'] ?? (null as number | null),
  description:       props.game.description       || '',
  description_short: props.game.description_short || '',
  os_windows:        props.game.os_windows  ?? false,
  os_mac:            props.game.os_mac      ?? false,
  os_linux:          props.game.os_linux    ?? false,
  genres:            (props.game.genres   || []).join(', '),
  tags:              (props.game.tags     || []).join(', '),
  features:          (props.game.features || []).join(', '),
  languages:         Object.keys(props.game.languages || {}).join(', '),
})

// Plugin scraper scores: every numeric meta_ratings key besides the built-in
// sources (0-10 convention). Non-numeric keys (plugin bookkeeping) are
// preserved untouched on save. Rows appear automatically: stored keys first,
// then every installed metadata PROVIDER plugin (its provider id is the
// meta_ratings key), each with a fillable score like GOG/RAWG/IGDB. Badge
// plugins (e.g. Steam Deck) implement no provider hooks and stay out.
const EXT_RATING_KEYS = ['rawg', 'igdb', 'steam', 'metacritic']
const pluginRatingRows = ref<{ key: string; value: number | null }[]>(
  Object.entries(props.game.meta_ratings || {})
    .filter(([k, v]) => !EXT_RATING_KEYS.includes(k) && typeof v === 'number')
    .map(([k, v]) => ({ key: k, value: v as number }))
)
let origPluginRows = JSON.stringify(pluginRatingRows.value)
async function loadRatingProviders() {
  try {
    const { data } = await client.get('/plugins/metadata/providers')
    const appended: { key: string; value: null }[] = []
    for (const p of (Array.isArray(data) ? data : [])) {
      const key = String(p.id || '')
      if (p.ratings === false) continue // badge-style provider, no numeric score
      if (!key || EXT_RATING_KEYS.includes(key) || pluginRatingRows.value.some(r => r.key === key)) continue
      pluginRatingRows.value.push({ key, value: null })
      appended.push({ key, value: null })
    }
    // The auto-added empty rows are pristine, not edits.
    origPluginRows = JSON.stringify([...JSON.parse(origPluginRows), ...appended])
  } catch { /* providers unavailable - stored keys still show */ }
}
loadRatingProviders()

// ── Save state ────────────────────────────────────────────────────────────────
const saving    = ref(false)
const saveOk    = ref(false)
const saveError = ref('')
const notifying = ref(false)
const notifyMsg = ref('')
const notifyOk  = ref(true)
// Show "Send notification" only when at least one channel (Discord/email) is on.
const notifyEnabled = ref(false)

// ── Requirements ──────────────────────────────────────────────────────────────
interface SrlMatch { title: string; url: string; score: number }
interface SrlReqs  { minimum: Record<string, string>; recommended: Record<string, string> }

const srlQuery         = ref(props.game.title)
const srlSearching     = ref(false)
const srlFetching      = ref(false)
const srlMatches       = ref<SrlMatch[]>([])
const srlSelectedUrl   = ref('')
const srlPreview       = ref<SrlReqs | null>(null)
const srlError         = ref('')
const pendingRequirements = ref<SrlReqs | null>(null)

const SRL_KEY_LABELS: Record<string, string> = {
  processor: 'CPU', memory: 'RAM', graphics: 'GPU',
  os: 'OS', storage: 'Storage', directx: 'DirectX',
  sound: 'Sound Card', network: 'Network',
}
function srlKeyLabel(k: string): string { return SRL_KEY_LABELS[k] || k }

const currentReqRows = computed(() => {
  const reqs = (pendingRequirements.value ?? props.game.requirements) as any
  if (!reqs?.minimum) return []
  const ORDER = ['processor', 'memory', 'graphics', 'os', 'storage', 'directx', 'sound', 'network']
  const result: { key: string; val: string }[] = []
  for (const k of ORDER) {
    if (reqs.minimum[k]) result.push({ key: srlKeyLabel(k), val: reqs.minimum[k] })
  }
  return result
})

const manualFields = [
  { key: 'processor', label: 'CPU' },
  { key: 'memory',    label: 'RAM' },
  { key: 'graphics',  label: 'GPU' },
] as const
type ManualKey = typeof manualFields[number]['key']
const manualMin = ref<Record<ManualKey, string>>({ processor: '', memory: '', graphics: '' })

// ── Computed ──────────────────────────────────────────────────────────────────
const currentCoverSrc = computed(() => selectedCover.value || props.game.cover_path || props.game.cover_url || '')

const hasChanges = computed(() => {
  if (pluginDirty.value) return true
  if (libraryKind.value === 'games' && membershipChanged.value) return true
  if (libraryKind.value === 'games' && gameCollectionsChanged.value) return true
  if (libraryKind.value === 'games' && isAdmin.value && accessChanged.value) return true
  if (pendingRequirements.value !== null) return true
  if (selectedCover.value      !== (props.game.cover_path      || '')) return true
  if (selectedBackground.value !== (props.game.background_path || props.game.background_url || '')) return true
  if (selectedLogo.value       !== (props.game.logo_path       || '')) return true
  if (selectedIcon.value       !== (props.game.icon_path       || '')) return true
  const f = editFields.value
  if (f.developer         !== (props.game.developer         || '')) return true
  if (f.publisher         !== (props.game.publisher         || '')) return true
  if (f.release_date      !== (props.game.release_date      || '')) return true
  if (f.description       !== (props.game.description       || '')) return true
  if (f.description_short !== (props.game.description_short || '')) return true
  if (f.rating     !== (props.game.rating                     ?? null)) return true
  if (f.hltb_main_h     !== (props.game.hltb_main_s     != null ? Math.round(props.game.hltb_main_s / 360) / 10 : null)) return true
  if (f.hltb_complete_h !== (props.game.hltb_complete_s != null ? Math.round(props.game.hltb_complete_s / 360) / 10 : null)) return true
  if (f.meta_rawg  !== (props.game.meta_ratings?.['rawg']  ?? null)) return true
  if (f.meta_igdb  !== (props.game.meta_ratings?.['igdb']  ?? null)) return true
  if (f.meta_steam !== (props.game.meta_ratings?.['steam'] ?? null)) return true
  if (JSON.stringify(pluginRatingRows.value) !== origPluginRows) return true
  if (f.os_windows        !== (props.game.os_windows  ?? false)) return true
  if (f.os_mac            !== (props.game.os_mac      ?? false)) return true
  if (f.os_linux          !== (props.game.os_linux    ?? false)) return true
  if (f.genres    !== (props.game.genres   || []).join(', ')) return true
  if (f.tags      !== (props.game.tags     || []).join(', ')) return true
  if (f.features  !== (props.game.features || []).join(', ')) return true
  if (f.languages !== Object.keys(props.game.languages || {}).join(', ')) return true
  if (JSON.stringify(editScreenshots.value) !== JSON.stringify(props.game.screenshots || [])) return true
  if (editVideoId.value !== _firstVideoId()) return true
  return false
})

// ── Cover actions ─────────────────────────────────────────────────────────────
function selectCover(cover: CoverOption) {
  selectedCover.value         = cover.url
  selectedCoverThumb.value    = cover.thumb || cover.url
  selectedCoverAnimated.value = cover.type === 'animated'
}

function clearCover() {
  selectedCover.value         = props.game.cover_path || props.game.cover_url || ''
  selectedCoverThumb.value    = ''
  selectedCoverAnimated.value = false
}

function applyManualCover() {
  if (!manualCoverUrl.value) return
  selectCover({ url: manualCoverUrl.value, thumb: manualCoverUrl.value, type: 'static', label: 'Manual URL' })
  manualCoverUrl.value = ''
}

function onThumbError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img.src !== selectedCover.value) img.src = selectedCover.value
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(id: string) {
  activeTab.value = id
  if (id === 'cover'       && !coverSearchDone.value)        searchAllCovers()
  if (id === 'background'  && !heroSearchDone.value)         searchAllHeroes()
  if (id === 'logo'        && !logoSearchDone.value)         searchAllLogos()
  if (id === 'icon'        && !iconSearchDone.value)         searchAllIcons()
  if (id === 'screenshots' && !ssAllSearchDone.value)         searchAllScreenshots()
  if (id === 'video'       && !vidAllSearchDone.value)        searchAllVideos()
  if (id === 'description' && !descFetched.value) loadDescriptions()
  if (id === 'details'     && !detailFetched.value) loadDetails()
}

// ── Loaders: IGDB covers ──────────────────────────────────────────────────────
async function searchIgdb() {
  igdbLoading.value = true; igdbSearched.value = false; igdbCovers.value = []
  try {
    const q = encodeURIComponent(igdbQuery.value || props.game.title)
    const { data } = await client.get(`${baseApi.value}/${props.game.id}/covers?source=igdb&q=${q}`)
    igdbCovers.value = data; igdbSearched.value = true
  } catch { igdbSearched.value = true }
  finally { igdbLoading.value = false }
}

// ── RAWG backgrounds ──────────────────────────────────────────────────────────
async function searchRawg() {
  rawgLoading.value = true; rawgSearched.value = false; rawgCovers.value = []
  try {
    const q = encodeURIComponent(rawgQuery.value || props.game.title)
    const { data } = await client.get(`${baseApi.value}/${props.game.id}/covers?source=rawg&q=${q}`)
    rawgCovers.value = data; rawgSearched.value = true
  } catch { rawgSearched.value = true }
  finally { rawgLoading.value = false }
}

// ── SGDB Covers ───────────────────────────────────────────────────────────────
async function searchSgdbCovers() {
  sgdbCoverLoading.value = true; sgdbCoverSearched.value = false; sgdbCoverResults.value = []
  try {
    const q = encodeURIComponent(sgdbCoverQuery.value || props.game.title)
    const { data } = await client.get(
      `${baseApi.value}/${props.game.id}/covers?source=steamgriddb&q=${q}&asset_type=grids&animated=${sgdbCoverAnimated.value}`
    )
    sgdbCoverResults.value = data; sgdbCoverSearched.value = true
  } catch { sgdbCoverSearched.value = true }
  finally { sgdbCoverLoading.value = false }
}

function setSgdbCoverAnimated(val: typeof sgdbCoverAnimated.value) {
  sgdbCoverAnimated.value = val
  if (sgdbCoverSearched.value) searchSgdbCovers()
}

/** Unified cover search - queries GOG + IGDB + SteamGridDB in parallel. */
async function searchAllCovers() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (coverSearching.value) return
  coverSearching.value = true
  coverSearchDone.value = false
  allCoverResults.value = []

  const q = coverSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  const baseUrl = `${baseApi.value}/${props.game.id}/covers`

  const results = await Promise.all([
    // GOG (search catalog by title)
    client.get(`${baseUrl}?source=gog&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'GOG', _sourceIcon: 'gog.ico' }))
    ).catch(() => []),
    // IGDB
    client.get(`${baseUrl}?source=igdb&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'IGDB', _sourceIcon: 'igdb.ico' }))
    ).catch(() => []),
    // SteamGridDB
    client.get(`${baseUrl}?source=steamgriddb&q=${qEnc}&asset_type=grids&animated=any`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'SteamGridDB', _sourceIcon: 'steamgriddb.ico' }))
    ).catch(() => []),
    // LaunchBox
    client.get(`${baseUrl}?source=launchbox&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).filter(c => !c.asset_type).map(c => ({ ...c, _source: 'LaunchBox', _sourceIcon: 'launchbox.ico' }))
    ).catch(() => []),
    // Metadata provider plugins (covers)
    ...(metadataProviders.value.length ? [
      client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=grids`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
    // ScreenScraper - only in the catalogue (PC Ports) editor, where console box
    // art fits. URLs come back already wrapped as credential-free proxy tokens.
    ...(isCatalog.value ? [
      client.get(`${baseUrl}?source=screenscraper&q=${qEnc}&asset_type=grids`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: 'ScreenScraper', _sourceIcon: 'ScreenScraper.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
  ])

  allCoverResults.value = results.flat()
  coverSearchDone.value = true
  coverSearching.value = false
}

/** Unified hero search - queries GOG bg + RAWG + SteamGridDB heroes in parallel. */
async function searchAllHeroes() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (heroSearching.value) return
  heroSearching.value = true
  heroSearchDone.value = false
  allHeroResults.value = []

  const q = heroSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  const baseUrl = `${baseApi.value}/${props.game.id}/covers`

  const results = await Promise.all([
    // GOG (uses gog_game_id if linked, else catalog search - returns background)
    client.get(`${baseUrl}?source=gog&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).filter(c => c.label?.includes('Background')).map(c => ({ ...c, _source: 'GOG', _sourceIcon: 'gog.ico' }))
    ).catch(() => []),
    // RAWG backgrounds
    client.get(`${baseUrl}?source=rawg&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'RAWG', _sourceIcon: 'RAWG.ico' }))
    ).catch(() => []),
    // SteamGridDB heroes
    client.get(`${baseUrl}?source=steamgriddb&q=${qEnc}&asset_type=heroes&animated=any`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'SteamGridDB', _sourceIcon: 'steamgriddb.ico' }))
    ).catch(() => []),
    // Metadata provider plugins (heroes)
    ...(metadataProviders.value.length ? [
      client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=heroes`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
    // ScreenScraper fanart as a hero, catalogue editor only (proxied URLs).
    ...(isCatalog.value ? [
      client.get(`${baseUrl}?source=screenscraper&q=${qEnc}&asset_type=heroes`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: 'ScreenScraper', _sourceIcon: 'ScreenScraper.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
  ])

  allHeroResults.value = results.flat()
  heroSearchDone.value = true
  heroSearching.value = false
}

/** Unified logo search - GOG + SteamGridDB logos + LaunchBox Clear Logo + plugins. */
async function searchAllLogos() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (logoSearching.value) return
  logoSearching.value = true
  logoSearchDone.value = false
  allLogoResults.value = []

  const q = logoSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  const baseUrl = `${baseApi.value}/${props.game.id}/covers`

  const results = await Promise.all([
    // GOG (returns logo from gog_game_id or catalog)
    client.get(`${baseUrl}?source=gog&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).filter(c => c.label?.includes('Logo')).map(c => ({ ...c, _source: 'GOG', _sourceIcon: 'gog.ico' }))
    ).catch(() => []),
    // SteamGridDB logos
    client.get(`${baseUrl}?source=steamgriddb&q=${qEnc}&asset_type=logos&animated=any`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'SteamGridDB', _sourceIcon: 'steamgriddb.ico' }))
    ).catch(() => []),
    // LaunchBox Clear Logo
    client.get(`${baseUrl}?source=launchbox&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).filter(c => c.asset_type === 'logos').map(c => ({ ...c, _source: 'LaunchBox', _sourceIcon: 'launchbox.ico' }))
    ).catch(() => []),
    // Plugins
    ...(metadataProviders.value.length ? [
      client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=logos`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
    // ScreenScraper wheel as a logo, catalogue editor only (proxied URLs).
    ...(isCatalog.value ? [
      client.get(`${baseUrl}?source=screenscraper&q=${qEnc}&asset_type=logos`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: 'ScreenScraper', _sourceIcon: 'ScreenScraper.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
  ])

  allLogoResults.value = results.flat()
  logoSearchDone.value = true
  logoSearching.value = false
}

/** Unified video search - GOG + IGDB via source=all. */
async function searchAllVideos() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (vidAllSearching.value) return
  vidAllSearching.value = true
  vidAllSearchDone.value = false
  vidAllResults.value = []
  const q = vidSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  try {
    const { data } = await client.get(`${baseApi.value}/${props.game.id}/videos?source=all&q=${qEnc}`)
    vidAllResults.value = data || []
  } catch { /* ignore */ }
  vidAllSearchDone.value = true
  vidAllSearching.value = false
}

/** Unified screenshot search - all sources via source=all. */
async function searchAllScreenshots() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (ssAllSearching.value) return
  ssAllSearching.value = true
  ssAllSearchDone.value = false
  ssAllResults.value = []
  const q = ssSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  try {
    const { data } = await client.get(`${baseApi.value}/${props.game.id}/screenshots?source=all&q=${qEnc}`)
    ssAllResults.value = data || []
  } catch { /* ignore */ }
  ssAllSearchDone.value = true
  ssAllSearching.value = false
}

/** Unified icon search - GOG + SteamGridDB icons + plugins. */
async function searchAllIcons() {
  // Enter fires this too, and that input is not disabled while a search
  // runs. Two runs race and the slower one writes last.
  if (iconSearching.value) return
  iconSearching.value = true
  iconSearchDone.value = false
  allIconResults.value = []

  const q = iconSearchQuery.value || props.game.title
  const qEnc = encodeURIComponent(q)
  const baseUrl = `${baseApi.value}/${props.game.id}/covers`

  const results = await Promise.all([
    // GOG (returns icon from gog_game_id if linked)
    client.get(`${baseUrl}?source=gog&q=${qEnc}`).then(r =>
      (r.data as CoverOption[]).filter(c => c.label?.includes('Icon') || c.label?.includes('icon')).map(c => ({ ...c, _source: 'GOG', _sourceIcon: 'gog.ico' }))
    ).catch(() => []),
    // SteamGridDB icons
    client.get(`${baseUrl}?source=steamgriddb&q=${qEnc}&asset_type=icons&animated=any`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: 'SteamGridDB', _sourceIcon: 'steamgriddb.ico' }))
    ).catch(() => []),
    // Plugins
    ...(metadataProviders.value.length ? [
      client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=icons`).then(r =>
        (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
      ).catch(() => [] as CoverOption[])
    ] : []),
  ])

  allIconResults.value = results.flat()
  iconSearchDone.value = true
  iconSearching.value = false
}

// ── SGDB Heroes ───────────────────────────────────────────────────────────────
async function searchSgdbBg() {
  sgdbBgLoading.value = true; sgdbBgSearched.value = false; sgdbBgResults.value = []
  try {
    const q = encodeURIComponent(sgdbBgQuery.value || props.game.title)
    const { data } = await client.get(
      `${baseApi.value}/${props.game.id}/covers?source=steamgriddb&q=${q}&asset_type=heroes&animated=any`
    )
    sgdbBgResults.value = data; sgdbBgSearched.value = true
  } catch { sgdbBgSearched.value = true }
  finally { sgdbBgLoading.value = false }
}

// ── SGDB Logos ────────────────────────────────────────────────────────────────
async function searchSgdbLogos() {
  sgdbLogoLoading.value = true; sgdbLogoSearched.value = false; sgdbLogoResults.value = []
  try {
    const q = encodeURIComponent(sgdbLogoQuery.value || props.game.title)
    const { data } = await client.get(
      `${baseApi.value}/${props.game.id}/covers?source=steamgriddb&q=${q}&asset_type=${sgdbLogoType.value}&animated=any`
    )
    sgdbLogoResults.value = data; sgdbLogoSearched.value = true
  } catch { sgdbLogoSearched.value = true }
  finally { sgdbLogoLoading.value = false }
}

function setSgdbLogoType(type: typeof sgdbLogoType.value) {
  sgdbLogoType.value = type
  if (sgdbLogoSearched.value) searchSgdbLogos()
}

// ── Screenshots ───────────────────────────────────────────────────────────────
function addScreenshotUrl() {
  const url = ssNewUrl.value.trim()
  if (!url) return
  if (screenshotsMode.value === 'replace') {
    editScreenshots.value = [url]; screenshotsMode.value = 'add'
  } else if (!editScreenshots.value.includes(url)) {
    editScreenshots.value.push(url)
  }
  ssNewUrl.value = ''
}

function removeScreenshot(idx: number) { editScreenshots.value.splice(idx, 1) }

function moveScreenshot(from: number, to: number) {
  const list = editScreenshots.value
  const item = list.splice(from, 1)[0]
  list.splice(to, 0, item)
}

function addScreenshotFromSource(url: string) {
  if (screenshotsMode.value === 'replace') {
    editScreenshots.value = [url]; screenshotsMode.value = 'add'; return
  }
  const idx = editScreenshots.value.indexOf(url)
  if (idx >= 0) editScreenshots.value.splice(idx, 1)
  else editScreenshots.value.push(url)
}

async function setSsSource(src: typeof ssSource.value) {
  ssSource.value = src; ssSearched.value = false; ssSearchResults.value = []
  await searchScreenshots()
}

async function searchScreenshots() {
  ssSearchLoading.value = true; ssSearched.value = false; ssSearchResults.value = []
  try {
    const q = ssSearchQuery.value || props.game.title
    const src = ssSource.value
    if (!['igdb', 'rawg'].includes(src)) {
      // Plugin source - fetch screenshots from plugin metadata API
      const { data: results } = await client.get(`/plugins/metadata/search?q=${encodeURIComponent(q)}`)
      if (Array.isArray(results)) {
        for (const pr of results.filter((r: any) => r.provider_id === src).slice(0, 3)) {
          try {
            const { data: detail } = await client.get(
              `/plugins/metadata/fetch?provider_id=${encodeURIComponent(pr.provider_id)}&game_id=${encodeURIComponent(pr.provider_game_id)}`
            )
            if (detail?.screenshots?.length) {
              for (const s of detail.screenshots) {
                      ssSearchResults.value.push(typeof s === 'string' ? { url: s, thumb: s } : s)
                    }
              break
            }
          } catch { /* skip */ }
        }
      }
      ssSearched.value = true
    } else {
      const { data } = await client.get(
        `${baseApi.value}/${props.game.id}/screenshots?source=${src}&q=${encodeURIComponent(q)}`
      )
      ssSearchResults.value = data; ssSearched.value = true
    }
  } catch { ssSearched.value = true }
  finally { ssSearchLoading.value = false }
}

// ── Video ─────────────────────────────────────────────────────────────────────
function applyVideo() {
  const raw = editVideoUrl.value.trim()
  if (!raw) return
  // Extract YouTube video ID
  const ytMatch = raw.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/)
  editVideoId.value = ytMatch ? ytMatch[1] : raw.length === 11 ? raw : ''
  editVideoUrl.value = ''
}

async function searchVideos() {
  vidSearchLoading.value = true; vidSearched.value = false; vidSearchResults.value = []
  try {
    const q = encodeURIComponent(vidSearchQuery.value || props.game.title)
    const { data } = await client.get(
      `${baseApi.value}/${props.game.id}/videos?source=igdb&q=${q}`
    )
    vidSearchResults.value = data; vidSearched.value = true
  } catch { vidSearched.value = true }
  finally { vidSearchLoading.value = false }
}

// ── Steam requirements ────────────────────────────────────────────────────────
const steamReqQuery   = ref(props.game.title)
const steamReqLoading = ref(false)
const steamReqPreview = ref<SrlReqs | null>(null)
const steamReqError   = ref('')

async function fetchSteamReqs() {
  if (!steamReqQuery.value.trim()) return
  steamReqLoading.value = true; steamReqError.value = ''; steamReqPreview.value = null
  try {
    const { data } = await client.get(`${baseApi.value}/${props.game.id}/meta-sources`, {
      params: { source: 'steam', q: steamReqQuery.value.trim() },
    })
    if (!data.found || !data.requirements || !Object.keys(data.requirements).length) {
      steamReqError.value = data.error || t('meta.no_steam_reqs')
      return
    }
    const reqs = data.requirements as Record<string, { minimum?: Record<string,string>; recommended?: Record<string,string> }>
    const winKey = Object.keys(reqs).find(k => k.toLowerCase().includes('windows')) ?? Object.keys(reqs)[0]
    const entry = reqs[winKey]
    steamReqPreview.value = {
      minimum:     filterReqKeys(entry?.minimum     ?? {}),
      recommended: filterReqKeys(entry?.recommended ?? {}),
    }
  } catch (e: any) {
    steamReqError.value = e?.response?.data?.detail || t('meta.steam_fetch_failed')
  } finally {
    steamReqLoading.value = false
  }
}

// ── Requirements ──────────────────────────────────────────────────────────────
async function srlSearch() {
  srlSearching.value = true; srlError.value = ''; srlMatches.value = []; srlPreview.value = null
  try {
    const { data } = await client.get('/gog/srl/search', { params: { q: srlQuery.value.trim() } })
    srlMatches.value = data.matches || []
    if (!srlMatches.value.length) srlError.value = t('meta.no_srl_matches')
  } catch (e: any) {
    srlError.value = e?.response?.data?.detail || t('common.search_failed')
  } finally {
    srlSearching.value = false
  }
}

function srlSelectMatch(url: string) { srlSelectedUrl.value = url }

async function srlFetchUrl(url: string) {
  srlSelectedUrl.value = url; srlFetching.value = true; srlError.value = ''
  try {
    const { data } = await client.get('/gog/srl/fetch', { params: { url } })
    srlPreview.value = { minimum: filterReqKeys(data?.minimum ?? {}), recommended: {} }
  } catch (e: any) {
    srlError.value = e?.response?.data?.detail || t('common.fetch_failed')
  } finally {
    srlFetching.value = false
  }
}

const REQ_PREVIEW_KEYS = ['processor', 'memory', 'graphics', 'os', 'storage', 'directx', 'sound', 'network'] as const
function filterReqKeys(obj: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of REQ_PREVIEW_KEYS) if (obj[k]) out[k] = obj[k]
  return out
}

function clearRequirements() { pendingRequirements.value = { minimum: {}, recommended: {} } }
function applyReqPreview(preview: SrlReqs) { pendingRequirements.value = preview }

function applyManualReqs() {
  const min: Record<string, string> = {}
  for (const f of manualFields) {
    if (manualMin.value[f.key].trim()) min[f.key] = manualMin.value[f.key].trim()
  }
  if (!Object.keys(min).length) return
  pendingRequirements.value = { minimum: min, recommended: {} }
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function resendNotification() {
  notifying.value = true; notifyMsg.value = ''; notifyOk.value = true
  try {
    const { data } = await client.post(`${baseApi.value}/${props.game.id}/announce`)
    notifyMsg.value = data?.sent ? t('meta.notification_sent') : t('meta.notification_skipped')
    setTimeout(() => { notifyMsg.value = '' }, 3500)
  } catch (e: any) {
    notifyOk.value = false
    notifyMsg.value = e?.response?.data?.detail || t('meta.notification_failed')
    setTimeout(() => { notifyMsg.value = '' }, 4500)
  } finally { notifying.value = false }
}

async function save() {
  saving.value = true; saveOk.value = false; saveError.value = ''
  try {
    const payload: Record<string, unknown> = {}
    // Images
    if (selectedCover.value      !== (props.game.cover_path      || '')) payload.cover_url      = selectedCover.value
    if (selectedBackground.value !== (props.game.background_path || props.game.background_url || '')) payload.background_url = selectedBackground.value
    if (selectedLogo.value       !== (props.game.logo_path       || '')) payload.logo_url       = selectedLogo.value
    if (selectedIcon.value       !== (props.game.icon_path       || '')) payload.icon_url       = selectedIcon.value
    // Fields
    const f = editFields.value
    if (f.developer         !== (props.game.developer         || '')) payload.developer         = f.developer
    if (f.publisher         !== (props.game.publisher         || '')) payload.publisher         = f.publisher
    if (f.release_date      !== (props.game.release_date      || '')) payload.release_date      = f.release_date
    if (f.description       !== (props.game.description       || '')) payload.description       = f.description
    if (f.description_short !== (props.game.description_short || '')) payload.description_short = f.description_short
    if (f.rating !== (props.game.rating ?? null)) payload.rating = f.rating
    // Time to beat: edited in hours, stored in seconds - only send when the
    // hour value actually changed so an untouched field never drifts.
    const origMainH = props.game.hltb_main_s     != null ? Math.round(props.game.hltb_main_s / 360) / 10 : null
    const origCompH = props.game.hltb_complete_s != null ? Math.round(props.game.hltb_complete_s / 360) / 10 : null
    if (f.hltb_main_h !== origMainH)
      payload.hltb_main_s = typeof f.hltb_main_h === 'number' && isFinite(f.hltb_main_h) ? Math.round(f.hltb_main_h * 3600) : null
    if (f.hltb_complete_h !== origCompH)
      payload.hltb_complete_s = typeof f.hltb_complete_h === 'number' && isFinite(f.hltb_complete_h) ? Math.round(f.hltb_complete_h * 3600) : null
    // meta_ratings: build merged object only when any sub-field changed
    const mrOrig = props.game.meta_ratings || {}
    const pluginRowsChanged = JSON.stringify(pluginRatingRows.value) !== origPluginRows
    if (f.meta_rawg  !== (mrOrig['rawg']  ?? null)
     || f.meta_igdb  !== (mrOrig['igdb']  ?? null)
     || f.meta_steam !== (mrOrig['steam'] ?? null)
     || pluginRowsChanged) {
      const mr: Record<string, number> = { ...mrOrig }
      if (f.meta_rawg  != null) mr['rawg']  = f.meta_rawg;  else delete mr['rawg']
      if (f.meta_igdb  != null) mr['igdb']  = f.meta_igdb;  else delete mr['igdb']
      if (f.meta_steam != null) mr['steam'] = f.meta_steam; else delete mr['steam']
      if (pluginRowsChanged) {
        // Replace the numeric plugin keys with the edited rows; anything
        // non-numeric (plugin bookkeeping objects/strings) stays as-is.
        for (const [k, v] of Object.entries(mrOrig)) {
          if (!EXT_RATING_KEYS.includes(k) && typeof v === 'number') delete mr[k]
        }
        for (const r of pluginRatingRows.value) {
          // v-model.number yields '' for a cleared field - only real numbers persist
          if (r.key && typeof r.value === 'number' && isFinite(r.value)) mr[r.key] = r.value
        }
      }
      payload.meta_ratings = mr
    }
    if (f.os_windows !== (props.game.os_windows ?? false)) payload.os_windows = f.os_windows
    if (f.os_mac     !== (props.game.os_mac     ?? false)) payload.os_mac     = f.os_mac
    if (f.os_linux   !== (props.game.os_linux   ?? false)) payload.os_linux   = f.os_linux
    const parseArr = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean)
    if (f.genres   !== (props.game.genres   || []).join(', ')) payload.genres   = parseArr(f.genres)
    if (f.tags     !== (props.game.tags     || []).join(', ')) payload.tags     = parseArr(f.tags)
    if (f.features !== (props.game.features || []).join(', ')) payload.features = parseArr(f.features)
    if (f.languages !== Object.keys(props.game.languages || {}).join(', ')) {
      const raw = parseArr(f.languages)
      // Normalize each entry to {code: name} - handles ISO codes, native names, English names
      const langObj: Record<string, string> = {}
      for (const item of raw) {
        // If it looks like a short code (en, pl, de, zh-Hans) keep it
        if (/^[a-z]{2,3}(-[A-Za-z]+)?$/.test(item)) {
          const entry = LANG_MAP[item]
          langObj[item] = entry?.name || item
        } else {
          // Native or English name - find the ISO code via reverse lookup
          const resolved = resolveLang(item)
          const code = Object.entries(LANG_MAP).find(([, e]) => e.name === resolved.name && !e.group)?.[0]
          langObj[code || item] = resolved.name
        }
      }
      payload.languages = langObj
    }
    if (JSON.stringify(editScreenshots.value) !== JSON.stringify(props.game.screenshots || []))
      payload.screenshots = editScreenshots.value
    if (editVideoId.value !== _firstVideoId())
      payload.videos = editVideoId.value
        ? [{ provider: 'youtube', video_id: editVideoId.value, thumbnail_id: '' }]
        : []
    if (pendingRequirements.value !== null) payload.requirements = pendingRequirements.value

    // Let a plugin metadata tab contribute to this save (registerMetadataTab onSave).
    if (_pluginSaveHandler) {
      const extra = await _pluginSaveHandler()
      if (extra && typeof extra === 'object') {
        for (const [k, v] of Object.entries(extra as Record<string, unknown>)) {
          if (k === 'meta_ratings' && v && typeof v === 'object') {
            const base = (payload.meta_ratings as Record<string, unknown>)
              ?? { ...(props.game.meta_ratings || {}) }
            const merged: Record<string, unknown> = { ...base, ...(v as Record<string, unknown>) }
            for (const mk of Object.keys(merged)) if (merged[mk] == null) delete merged[mk]
            payload.meta_ratings = merged
          } else if (v !== undefined) {
            payload[k] = v
          }
        }
      }
    }

    if (Object.keys(payload).length) {
      await client.patch(`${baseApi.value}/${props.game.id}`, payload)
    }
    if (libraryKind.value === 'games') {
      await client.put(`/libraries/membership/${props.game.id}`, {
        in_default_library: inDefaultLibrary.value,
        collections: selectedCollections.value,
      })
      _snapshotMembership()
    }
    if (libraryKind.value === 'games' && gameCollectionsChanged.value) {
      await client.put(`/collections/membership/${props.game.id}`, {
        collections: gameCollections.value,
      })
      _snapshotGameCollections()
    }
    if (libraryKind.value === 'games' && isAdmin.value && accessChanged.value) {
      await client.put(`/library/games/${props.game.id}/access`, {
        denied_user_ids: deniedUserIds.value,
      })
      _snapshotAccess()
    }
    pluginDirty.value = false
    saveOk.value = true
    emit('saved', payload)
    setTimeout(() => emit('close'), 800)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || t('common.save_failed')
  } finally {
    saving.value = false
  }
}

// ── Metadata provider plugins ────────────────────────────────────────────────
const metadataProviders = ref<{id: string; name: string; logo_url: string}[]>([])

/** Get plugin logo URL by provider_id (resolves via metadataProviders list). */
function pluginLogoUrl(providerId: string): string {
  const mp = metadataProviders.value.find(p => p.id === providerId)
  return mp?.logo_url || `/api/plugins/${providerId}/logo`
}

/** What the provider calls itself ("PPE.pl"), not its id shouted ("PPE"). */
function pluginProviderName(providerId: string): string {
  const mp = metadataProviders.value.find(p => p.id === providerId)
  return mp?.name || providerId.toUpperCase()
}

onMounted(async () => {
  if (libraryKind.value === 'games') { loadMemberships(); loadGameCollections(); loadGameAccess() }
  try {
    const { data } = await client.get('/plugins/metadata/providers')
    metadataProviders.value = data || []
  } catch { /* no plugins */ }
  try {
    const { data } = await client.get('/settings/notifications/added-enabled')
    notifyEnabled.value = !!data?.enabled
  } catch { notifyEnabled.value = false }
  await searchAllCovers()
})
</script>

<style scoped>
.mep-desc-apply-btn {
  padding: 5px 14px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; white-space: nowrap; transition: all .15s;
}

/* File upload button (label wraps hidden input) */
.mep-upload-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; flex-shrink: 0;
  transition: all .15s;
}
.mep-btn-notify {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 30%, var(--glass-border));
  color: var(--pl-light); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; margin-right: auto;
}
.mep-btn-notify:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 22%, transparent); border-color: color-mix(in srgb, var(--pl) 45%, transparent); color: #fff; }
.mep-btn-notify:disabled { opacity: .5; cursor: not-allowed; }
</style>
