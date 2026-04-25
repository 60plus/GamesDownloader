<template>
  <!-- Fullscreen overlay -->
  <div class="mep-overlay" @click.self="$emit('close')">
    <div class="mep-panel" @click.stop>

      <!-- ── Header ─────────────────────────────────────────────────────────── -->
      <div class="mep-header">
        <div class="mep-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <span>{{ t('meta.edit_title') }}</span>
          <span class="mep-game-name">- {{ rom.name }}</span>
        </div>
        <button class="mep-close" @click="$emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- ── Body ───────────────────────────────────────────────────────────── -->
      <div class="mep-body">

        <!-- LEFT: Previews sidebar -->
        <div class="mep-left">

          <!-- Cover -->
          <div class="mep-label">{{ t('meta.tab_cover') }}</div>
          <div class="mep-cover-current" @click="switchTab('cover')" style="cursor:pointer">
            <img v-if="selectedCover || rom.cover_path" :src="selectedCover || rom.cover_path || ''" alt="Cover" class="mep-cover-img" />
            <div v-else class="mep-cover-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="2" y="6" width="20" height="12" rx="2"/></svg>
            </div>
          </div>

          <!-- Hero -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_hero') }}</div>
          <div class="mep-cover-current mep-cover-current--wide" @click="switchTab('hero')" style="cursor:pointer">
            <img v-if="selectedHero" :src="selectedHero" alt="Hero" class="mep-cover-img" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="1" y="5" width="22" height="14" rx="2"/></svg>
            </div>
          </div>

          <!-- Support -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_support') }}</div>
          <div class="mep-cover-current" @click="switchTab('support')" style="cursor:pointer">
            <img v-if="selectedSupport" :src="selectedSupport" alt="Support" class="mep-cover-img" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><circle cx="12" cy="12" r="9"/></svg>
            </div>
          </div>

          <!-- Wheel -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_wheel') }}</div>
          <div class="mep-cover-current mep-cover-current--wide" @click="switchTab('wheel')" style="cursor:pointer">
            <img v-if="selectedWheel" :src="selectedWheel" alt="Wheel" style="width:100%;height:100%;object-fit:contain;padding:4px" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
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
              @click="switchTab(tab.id as TabId)"
            >{{ tab.label }}</button>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- COVER TAB                                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'cover'" class="mep-tab-content">

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img v-for="mp in metadataProviders" :key="mp.id" :src="mp.logo_url" width="14" height="14" :alt="mp.name" :title="mp.name" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.search_ss_igdb_lb') }}</span>
              </div>
              <div class="mep-search-row">
                <input v-model="ssQuery" class="mep-search-input" placeholder="Search games…" @keydown.enter="searchGames" />
                <button class="mep-search-btn" :disabled="ssLoading" @click="searchGames">
                  <div v-if="ssLoading" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
                  {{ t('meta.search') }}
                </button>
              </div>
              <div v-if="ssLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.searching') }}</div>
              <div v-else-if="ssSearched && !ssResults.length" class="mep-empty-state-sm">{{ t('meta.no_results_check') }}</div>
              <div v-else-if="!ssSearched" class="mep-empty-state-sm">{{ t('meta.search_rom_hint') }}</div>
              <template v-else>
                <!-- Source filter -->
                <div class="mep-source-filter">
                  <button
                    v-for="f in searchFilters"
                    :key="f.key"
                    class="mep-filter-btn"
                    :class="{ active: searchFilter === f.key }"
                    @click="searchFilter = f.key"
                  >
                    <img v-if="f.icon" :src="f.icon" width="12" height="12" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                    {{ f.label }}
                    <span class="mep-filter-count">{{ f.count }}</span>
                  </button>
                </div>
                <!-- Results grid -->
                <div class="mep-covers-grid" style="position:relative">
                  <div
                    v-for="result in filteredResults"
                    :key="(result.ss_id || result.igdb_id || (result as any).launchbox_id || result.sgdb_id || '') + result.name"
                    class="mep-cover-option"
                    :class="{ selected: isResultSelected(result) }"
                    @click="selectResult(result)"
                  >
                    <div class="mep-cover-option-img" style="position:relative">
                      <img
                        v-if="result.cover_url"
                        :src="result.cover_url"
                        :alt="result.name"
                        loading="lazy"
                        @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.3')"
                      />
                      <div v-else class="mep-cover-no-img">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="2" y="6" width="20" height="14" rx="2"/></svg>
                      </div>
                      <div class="mep-source-badge" :title="result.source">
                        <img :src="sourceIcon(result.source)" width="12" height="12" alt="" />
                      </div>
                      <div v-if="isResultSelected(result)" class="mep-selected-check">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                      </div>
                    </div>
                    <div class="mep-cover-label">{{ result.name }}</div>
                    <div v-if="result.year" class="mep-cover-author">{{ result.year }}</div>
                  </div>
                </div>
              </template>
            </div>

            <!-- Selected version card - shown when SS or LB result is selected -->
            <div v-if="scrapeableResult" class="mep-source-section mep-scrape-version-box">
              <div class="mep-source-header">
                <img :src="sourceIcon(scrapeableResult.source)" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.scrape_version') }}</span>
              </div>
              <div class="mep-scrape-version-card">
                <div class="mep-scrape-version-cover">
                  <img v-if="scrapeableResult.cover_url" :src="scrapeableResult.cover_url" alt="" />
                  <svg v-else width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="2" y="6" width="20" height="14" rx="2"/></svg>
                </div>
                <div class="mep-scrape-version-meta">
                  <div class="mep-scrape-version-name">{{ scrapeableResult.name }}</div>
                  <div class="mep-scrape-version-details">
                    <span v-if="scrapeableResult.year">{{ scrapeableResult.year }}</span>
                    <span v-if="scrapeableResult.developer" class="mep-scrape-version-dev">{{ scrapeableResult.developer }}</span>
                    <span v-if="scrapeableResult.regions?.length" class="mep-scrape-version-regions">
                      {{ scrapeableResult.regions.join(' - ').toUpperCase() }}
                    </span>
                    <span class="mep-scrape-ssid">{{ scrapeableResult.source === 'ss' ? 'SS' : 'LB' }} #{{ scrapeableResult.source === 'ss' ? selectedSsId : selectedLaunchboxId }}</span>
                  </div>
                </div>
              </div>
              <div class="mep-scrape-version-actions">
                <button
                  class="mep-scrape-version-btn"
                  :disabled="scrapeVersionLoading"
                  @click="scrapeThisVersion"
                >
                  <div v-if="scrapeVersionLoading" class="mep-spinner mep-spinner--sm" />
                  <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                  {{ scrapeVersionLoading ? t('meta.scrape_starting') : t('meta.scrape_this') }}
                </button>
                <div v-if="scrapeVersionOk" class="mep-scrape-version-ok">
                  &#10003; {{ t('meta.scrape_started') }}
                </div>
              </div>
            </div>

            <!-- Box Art variants - shown after selecting a game -->
            <div v-if="selectedSsId || selectedIgdbId || selectedLaunchboxId" class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.box_art_variants') }}</span>
                <span class="mep-source-hint">{{ t('meta.box_art_hint') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_box_art') }}</div>
              <div v-else-if="!allMedia.covers.length" class="mep-empty-state-sm">{{ t('meta.no_box_art') }}</div>
              <div v-else class="mep-covers-grid">
                <div
                  v-for="(cover, idx) in allMedia.covers"
                  :key="cover.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedCover === cover.url }"
                  @click="selectedCover = cover.url"
                >
                  <div class="mep-cover-option-img" :class="coverAspectClass(cover.type)" style="position:relative">
                    <img
                      :src="cover.url"
                      :alt="cover.label"
                      loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.2')"
                    />
                    <div class="mep-source-badge" :title="cover.source">
                      <img :src="sourceIcon(cover.source)" width="12" height="12" alt="" />
                    </div>
                    <div v-if="selectedCover === cover.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ cover.label }}</div>
                  <div class="mep-cover-author">{{ cover.region }}</div>
                </div>
              </div>
            </div>

            <!-- Manual URL -->
            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="manualCoverUrl" class="mep-input" placeholder="https://… (cover image URL)" @keydown.enter="applyManualCover" />
                <button class="mep-apply-btn" :disabled="!manualCoverUrl.trim()" @click="applyManualCover">{{ t('meta.apply') }}</button>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- HERO TAB                                                           -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'hero'" class="mep-tab-content">

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.fanart_bg') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!selectedSsId && !selectedIgdbId && !selectedLaunchboxId" class="mep-empty-state-sm">{{ t('meta.select_game_first') }}</div>
              <div v-else-if="!allMedia.fanarts.length" class="mep-empty-state-sm">{{ t('meta.no_bg_art') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(fanart, idx) in allMedia.fanarts"
                  :key="fanart.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedHero === fanart.url }"
                  @click="selectedHero = fanart.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide" style="position:relative">
                    <img :src="fanart.url" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display='none')" />
                    <div class="mep-source-badge" :title="fanart.source">
                      <img :src="sourceIcon(fanart.source)" width="12" height="12" alt="" />
                    </div>
                    <div v-if="selectedHero === fanart.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ fanart.label || fanart.type }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedHero" class="mep-input" placeholder="https://… (hero/background image)" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- SCREENSHOTS TAB                                                    -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'screenshots'" class="mep-tab-content">

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.current_screenshots_rom') }}</span></div>
              <div v-if="!editScreenshots.length" class="mep-empty-state-sm">{{ t('meta.no_screenshots_rom') }}</div>
              <div v-else class="mep-ss-list">
                <div v-for="(ss, idx) in editScreenshots" :key="ss + idx" class="mep-ss-item">
                  <img :src="ss" class="mep-ss-item-thumb" loading="lazy" @error="(e) => ((e.target as HTMLImageElement).style.opacity='0.15')" />
                  <div class="mep-ss-order-col">
                    <button class="mep-ss-ord-btn" :disabled="idx === 0" @click="moveSS(idx, idx-1)">▲</button>
                    <span class="mep-ss-num">{{ idx + 1 }}</span>
                    <button class="mep-ss-ord-btn" :disabled="idx === editScreenshots.length-1" @click="moveSS(idx, idx+1)">▼</button>
                  </div>
                  <button class="mep-ss-remove--list" @click="editScreenshots.splice(idx, 1)">✕</button>
                </div>
              </div>
              <div class="mep-search-row" style="margin-top:12px">
                <input v-model="ssNewUrl" class="mep-search-input" placeholder="Paste screenshot URL…" @keydown.enter="addSSUrl" />
                <button class="mep-search-btn" @click="addSSUrl">{{ t('meta.add_url') }}</button>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/igdb.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.screenshots_source') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!selectedSsId && !selectedIgdbId && !selectedLaunchboxId" class="mep-empty-state-sm">{{ t('meta.select_game_first') }}</div>
              <div v-else-if="!allMedia.screenshots.length" class="mep-empty-state-sm">{{ t('meta.no_ss_found_rom') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(ss, idx) in allMedia.screenshots"
                  :key="ss.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: editScreenshots.includes(ss.url) }"
                  :title="editScreenshots.includes(ss.url) ? t('meta.added_click_remove') : t('meta.click_to_add')"
                  @click="toggleSSScreenshot(ss.url)"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide" style="position:relative">
                    <img :src="ss.url" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.display='none')" />
                    <div class="mep-source-badge" :title="ss.source">
                      <img :src="sourceIcon(ss.source)" width="12" height="12" alt="" />
                    </div>
                    <div v-if="editScreenshots.includes(ss.url)" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ ss.region || ss.label || ss.type }}</div>
                </div>
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- SUPPORT TAB                                                        -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'support'" class="mep-tab-content">

            <div v-if="selectedSupport" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.selected') }}</span>
                <button class="mep-clear-btn-sm" @click="selectedSupport = ''">{{ t('meta.clear') }}</button>
              </div>
              <div class="mep-cover-selected-wrap" style="width:120px">
                <img :src="selectedSupport" class="mep-cover-img" />
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="SS" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.ss_cartridge') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!allMedia.supports.length" class="mep-empty-state-sm">{{ t('meta.no_support_art') }}</div>
              <div v-else class="mep-covers-grid">
                <div
                  v-for="(item, idx) in allMedia.supports"
                  :key="item.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedSupport === item.url }"
                  @click="selectedSupport = item.url"
                >
                  <div class="mep-cover-option-img">
                    <img :src="item.url" :alt="item.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.2')" />
                    <div v-if="selectedSupport === item.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ item.label }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedSupport" class="mep-input" placeholder="https://…" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- BEZEL TAB                                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'bezel'" class="mep-tab-content">

            <div v-if="selectedBezel" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.selected') }}</span>
                <button class="mep-clear-btn-sm" @click="selectedBezel = ''">{{ t('meta.clear') }}</button>
              </div>
              <div class="mep-cover-selected-wrap mep-cover-selected-wrap--wide" style="width:100%;max-width:300px">
                <img :src="selectedBezel" style="width:100%;height:100%;object-fit:contain;background:rgba(0,0,0,.15)" />
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="SS" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.ss_bezels') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!allMedia.bezels.length" class="mep-empty-state-sm">{{ t('meta.no_bezels') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(item, idx) in allMedia.bezels"
                  :key="item.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedBezel === item.url }"
                  @click="selectedBezel = item.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide">
                    <img :src="item.url" :alt="item.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.2')" />
                    <div v-if="selectedBezel === item.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ item.label }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedBezel" class="mep-input" placeholder="https://…" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- WHEEL TAB                                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'wheel'" class="mep-tab-content">

            <div v-if="selectedWheel" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.selected') }}</span>
                <button class="mep-clear-btn-sm" @click="selectedWheel = ''">{{ t('meta.clear') }}</button>
              </div>
              <div class="mep-cover-selected-wrap mep-cover-selected-wrap--wide" style="width:100%;max-width:260px">
                <img :src="selectedWheel" style="width:100%;height:100%;object-fit:contain;background:rgba(0,0,0,.15)" />
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="SS" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/launchbox.ico" width="14" height="14" alt="LB" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="SGDB" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.wheel_marquee') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!allMedia.wheels.length" class="mep-empty-state-sm">{{ t('meta.no_wheel') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(item, idx) in allMedia.wheels"
                  :key="item.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedWheel === item.url }"
                  @click="selectedWheel = item.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide" style="background:rgba(0,0,0,.3);position:relative">
                    <img :src="item.url" :alt="item.label" loading="lazy" style="object-fit:contain"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.2')" />
                    <div class="mep-source-badge" :title="(item as any).source || 'ss'">
                      <img :src="sourceIcon((item as any).source || 'ss')" width="12" height="12" alt="" />
                    </div>
                    <div v-if="selectedWheel === item.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ item.label }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedWheel" class="mep-input" placeholder="https://…" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- STEAM GRID TAB                                                     -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'steamgrid'" class="mep-tab-content">

            <div v-if="selectedSteamGrid" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.selected') }}</span>
                <button class="mep-clear-btn-sm" @click="selectedSteamGrid = ''">{{ t('meta.clear') }}</button>
              </div>
              <div class="mep-cover-selected-wrap" style="width:160px;aspect-ratio:460/215">
                <img :src="selectedSteamGrid" style="width:100%;height:100%;object-fit:contain;background:rgba(0,0,0,.15)" />
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="SS" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <img src="/icons/steamgriddb.ico" width="14" height="14" alt="SGDB" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.ss_steamgrid') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!allMedia.steamgrids.length" class="mep-empty-state-sm">{{ t('meta.no_steamgrid') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(item, idx) in allMedia.steamgrids"
                  :key="item.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedSteamGrid === item.url }"
                  @click="selectedSteamGrid = item.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide">
                    <img :src="item.url" :alt="item.label" loading="lazy"
                      @error="(e) => ((e.target as HTMLImageElement).parentElement!.style.opacity = '0.2')" />
                    <div v-if="selectedSteamGrid === item.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ item.label }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedSteamGrid" class="mep-input" placeholder="https://…" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- VIDEO TAB                                                          -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'video'" class="mep-tab-content">

            <div v-if="selectedVideo" class="mep-source-section">
              <div class="mep-source-header">
                <span class="mep-source-name">{{ t('meta.selected_video') }}</span>
                <button class="mep-clear-btn-sm" @click="selectedVideo = ''">{{ t('meta.clear') }}</button>
              </div>
              <video :src="selectedVideo" controls class="mep-video-preview" />
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header">
                <img src="/icons/ScreenScraper.ico" width="14" height="14" alt="SS" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                <span class="mep-source-name">{{ t('meta.ss_videos') }}</span>
              </div>
              <div v-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
              <div v-else-if="!allMedia.videos.length" class="mep-empty-state-sm">{{ t('meta.no_videos') }}</div>
              <div v-else class="mep-covers-grid mep-covers-grid--wide">
                <div
                  v-for="(v, idx) in allMedia.videos"
                  :key="v.url + idx"
                  class="mep-cover-option"
                  :class="{ selected: selectedVideo === v.url }"
                  @click="selectedVideo = v.url"
                >
                  <div class="mep-cover-option-img mep-cover-option-img--wide mep-video-thumb">
                    <video :src="v.url" muted preload="metadata" class="mep-video-mini" />
                    <div v-if="selectedVideo === v.url" class="mep-selected-check">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                  </div>
                  <div class="mep-cover-label">{{ v.label }}</div>
                </div>
              </div>
            </div>

            <div class="mep-source-section">
              <div class="mep-source-header"><span class="mep-source-name">{{ t('meta.manual_url') }}</span></div>
              <div class="mep-field-row">
                <input v-model="selectedVideo" class="mep-input" placeholder="https://… (video URL)" />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- DESCRIPTION TAB                                                    -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'description'" class="mep-tab-content">

            <div v-if="!selectedSsId && !selectedIgdbId && !selectedLaunchboxId" class="mep-empty-state-sm">{{ t('meta.select_game_desc') }}</div>
            <div v-else-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
            <div v-else-if="!allMedia.detail_sources?.length" class="mep-empty-state-sm">{{ t('meta.no_desc_rom') }}</div>
            <div v-else class="mep-desc-list">
              <div v-for="src in allMedia.detail_sources.filter((s: any) => s.description)" :key="src.source" class="mep-desc-source">
                <div class="mep-desc-source-header">
                  <div class="mep-desc-source-icon">
                    <img :src="sourceIcon(src.source)" width="16" height="16" :alt="src.source" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  </div>
                  <div class="mep-desc-source-name">{{ src.source_name }}</div>
                  <button class="mep-desc-apply-btn" @click="editFields.summary = src.description">{{ t('meta.use_this') }}</button>
                </div>
                <div class="mep-desc-preview">
                  {{ src.description.replace(/<[^>]+>/g, ' ').slice(0, 400) }}{{ src.description.length > 400 ? '...' : '' }}
                </div>
              </div>
            </div>

            <div class="mep-form" style="margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07)">
              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.summary_desc') }} <TranslateButton :text="editFields.summary || ''" @translated="tr => editFields.summary = tr" /></label>
                <textarea v-model="editFields.summary" class="mep-textarea" rows="8" placeholder="Game summary or description..." />
              </div>
            </div>

          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- DETAILS TAB                                                        -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'details'" class="mep-tab-content">

            <div v-if="!selectedSsId && !selectedIgdbId && !selectedLaunchboxId" class="mep-empty-state-sm">{{ t('meta.select_game_first') }}</div>
            <div v-else-if="mediaLoading" class="mep-loading"><div class="mep-spinner" /> {{ t('meta.loading_media') }}</div>
            <div v-else-if="!allMedia.detail_sources?.length" class="mep-empty-state-sm">{{ t('meta.no_detail_results', 'No details found') }}</div>
            <div v-else class="mep-detail-sources">
              <div v-for="src in allMedia.detail_sources" :key="src.source" class="mep-detail-source">
                <div class="mep-desc-source-header">
                  <div class="mep-desc-source-icon">
                    <img :src="sourceIcon(src.source)" width="16" height="16" :alt="src.source" @error="(e) => (e.target as HTMLImageElement).style.display='none'" />
                  </div>
                  <div class="mep-desc-source-name">{{ src.source_name }}</div>
                  <button class="mep-desc-apply-btn" @click="applyDetailSource(src)">{{ t('meta.apply') }}</button>
                </div>
                <div class="mep-detail-grid">
                  <span v-if="src.developer"    class="mep-detail-chip"><b>{{ t('meta.developer') }}:</b> {{ src.developer }}</span>
                  <span v-if="src.publisher"    class="mep-detail-chip"><b>{{ t('meta.publisher') }}:</b> {{ src.publisher }}</span>
                  <span v-if="src.release_year" class="mep-detail-chip"><b>{{ t('meta.release_year') }}:</b> {{ src.release_year }}</span>
                  <span v-if="src.rating != null" class="mep-detail-chip">
                    <b>{{ src.source === 'ss' ? 'SS' : src.source === 'igdb' ? 'IGDB' : src.source === 'lb' ? 'LB' : src.source_name }}:</b>
                    {{ src.source === 'igdb' ? Math.round(src.rating) + '/100' : src.source === 'ss' ? src.rating + '/20' : src.rating.toFixed(1) + '/10' }}
                  </span>
                  <span v-if="src.genres?.length"   class="mep-detail-chip"><b>{{ t('meta.genres') }}:</b> {{ src.genres.slice(0,4).join(', ') }}</span>
                  <span v-if="src.regions?.length"  class="mep-detail-chip"><b>{{ t('meta.regions') }}:</b> {{ src.regions.join(', ') }}</span>
                  <span v-if="src.player_count"     class="mep-detail-chip"><b>{{ t('meta.players') }}:</b> {{ src.player_count }}</span>
                </div>
              </div>
            </div>

            <div class="mep-form" style="margin-top:12px">
              <div class="mep-form-section-label">{{ t('meta.game_info') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.display_name') }}</label>
                <input v-model="editFields.name" class="mep-input" placeholder="Display name" />
              </div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.developer') }}</label>
                  <input v-model="editFields.developer" class="mep-input" placeholder="Studio" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.publisher') }}</label>
                  <input v-model="editFields.publisher" class="mep-input" placeholder="Publisher" />
                </div>
              </div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.release_year') }}</label>
                  <input v-model.number="editFields.release_year" class="mep-input" type="number" placeholder="YYYY" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.rating') }} <span class="mep-field-hint">(0–20)</span></label>
                  <input v-model.number="editFields.rating" class="mep-input" type="number" min="0" max="20" step="0.1" />
                </div>
              </div>

              <div class="mep-form-section-label" style="margin-top:4px">{{ t('meta.categories') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.genres') }} <span class="mep-field-hint">{{ t('meta.comma_hint') }}</span></label>
                <input v-model="editFields.genres" class="mep-input" placeholder="Action, RPG…" />
              </div>

              <div class="mep-form-row">
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.regions') }}</label>
                  <input v-model="editFields.regions" class="mep-input" placeholder="us, eu, jp…" />
                </div>
                <div class="mep-field">
                  <label class="mep-field-label">{{ t('meta.languages') }}</label>
                  <input v-model="editFields.languages" class="mep-input" placeholder="en, fr, de…" />
                </div>
              </div>

              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.players') }}</label>
                <input v-model="editFields.player_count" class="mep-input" placeholder="1, 1-4…" />
              </div>

            </div>
          </div>

        </div>
      </div>

      <!-- ── Footer ─────────────────────────────────────────────────────────── -->
      <div class="mep-footer">
        <div class="mep-save-status">
          <span v-if="saveError" class="mep-err">{{ saveError }}</span>
          <span v-else-if="saveOk" class="mep-ok">✓ {{ t('meta.saved') }}</span>
        </div>
        <div class="mep-footer-actions">
          <button class="mep-btn-cancel" @click="$emit('close')">{{ t('meta.cancel') }}</button>
          <button class="mep-btn-save" :disabled="saving || !hasChanges" @click="save">
            <div v-if="saving" class="mep-spinner mep-spinner--sm" />
            {{ saving ? t('meta.saving') : t('meta.save_changes') }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import TranslateButton from '@/components/common/TranslateButton.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// ── Plugin metadata providers ─────────────────────────────────────────────────
const metadataProviders = ref<{ id: string; name: string; logo_url: string }[]>([])

function pluginLogoUrl(providerId: string): string {
  const mp = metadataProviders.value.find(p => p.id === providerId)
  return mp?.logo_url || `/api/plugins/${providerId}/logo`
}

onMounted(async () => {
  try {
    const { data } = await client.get('/plugins/metadata/providers')
    metadataProviders.value = data || []
  } catch { /* no plugins */ }
})

type TabId = 'cover' | 'hero' | 'screenshots' | 'support' | 'bezel' | 'wheel' | 'steamgrid' | 'video' | 'description' | 'details'

interface RomDetail {
  id: number
  platform_slug: string
  platform_name: string
  fs_name: string
  fs_name_no_ext: string | null
  fs_extension: string
  fs_size_bytes: number
  name: string
  slug: string | null
  summary: string | null
  developer: string | null
  publisher: string | null
  release_year: number | null
  genres: string[] | null
  regions: string[] | null
  languages: string[] | null
  tags: string[] | null
  rating: number | null
  player_count: string | null
  cover_path: string | null
  background_path: string | null
  screenshots: string[] | null
  support_path: string | null
  wheel_path: string | null
  bezel_path: string | null
  steamgrid_path: string | null
  video_path: string | null
  igdb_id: number | null
  ss_id: string | null
  launchbox_id: string | null
}

interface SearchResult {
  source: 'ss' | 'igdb' | 'launchbox' | 'sgdb'
  ss_id: string | null
  igdb_id: number | null
  sgdb_id: number | null
  name: string
  year: number | string | null
  developer: string | null
  cover_url: string | null
  regions: string[]
}

interface MediaItem {
  url: string
  type: string
  region?: string
  label?: string
  source: 'ss' | 'igdb' | 'sgdb' | 'lb'
}

interface DetailSource {
  source: string
  source_name: string
  name: string | null
  description: string
  developer: string | null
  publisher: string | null
  release_year: number | null
  genres: string[]
  regions: string[]
  rating: number | null
  player_count: string | null
}

interface AllMedia {
  covers:      MediaItem[]
  fanarts:     MediaItem[]
  screenshots: MediaItem[]
  supports:    MediaItem[]
  wheels:      MediaItem[]
  bezels:      MediaItem[]
  steamgrids:  MediaItem[]
  videos:      MediaItem[]
  details: DetailSource | null
  detail_sources: DetailSource[]
}

const props = defineProps<{ rom: RomDetail }>()
const emit  = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const tabs = computed<{ id: TabId; label: string }[]>(() => [
  { id: 'cover',       label: t('meta.tab_cover')       },
  { id: 'hero',        label: t('meta.tab_hero')        },
  { id: 'screenshots', label: t('meta.tab_screenshots') },
  { id: 'support',     label: t('meta.tab_support')     },
  { id: 'bezel',       label: t('meta.tab_bezel')       },
  { id: 'wheel',       label: t('meta.tab_wheel')       },
  { id: 'steamgrid',   label: t('meta.tab_steamgrid')   },
  { id: 'video',       label: t('meta.tab_video')       },
  { id: 'description', label: t('meta.tab_description') },
  { id: 'details',     label: t('meta.tab_details')     },
])
const activeTab = ref<TabId>('cover')

// ── Search ─────────────────────────────────────────────────────────────────────
const ssQuery    = ref(props.rom.name)
const ssLoading  = ref(false)
const ssSearched = ref(false)
const ssResults  = ref<SearchResult[]>([])
type FilterKey = 'all' | 'ss' | 'igdb' | 'launchbox' | 'sgdb'
const searchFilter  = ref<FilterKey>('all')

const filteredResults = computed(() => {
  if (searchFilter.value === 'all') return ssResults.value
  return ssResults.value.filter(r => r.source === searchFilter.value)
})

const searchFilters = computed((): { key: FilterKey; label: string; count: number; icon: string }[] => {
  const counts = { ss: 0, igdb: 0, launchbox: 0, sgdb: 0 }
  for (const r of ssResults.value) {
    if (r.source === 'ss') counts.ss++
    else if (r.source === 'igdb') counts.igdb++
    else if (r.source === 'launchbox') counts.launchbox++
    else if (r.source === 'sgdb') counts.sgdb++
  }
  return ([
    { key: 'all' as FilterKey,       label: 'All',  icon: '',                          count: ssResults.value.length },
    { key: 'ss' as FilterKey,        label: 'SS',   icon: '/icons/ScreenScraper.ico',  count: counts.ss },
    { key: 'igdb' as FilterKey,      label: 'IGDB', icon: '/icons/igdb.ico',           count: counts.igdb },
    { key: 'launchbox' as FilterKey, label: 'LB',   icon: '/icons/launchbox.ico',      count: counts.launchbox },
    { key: 'sgdb' as FilterKey,      label: 'SGDB', icon: '/icons/steamgriddb.ico',    count: counts.sgdb },
  ] as { key: FilterKey; label: string; count: number; icon: string }[]).filter(f => f.key === 'all' || f.count > 0)
})

// ── Scrape this version ────────────────────────────────────────────────────────
const scrapeVersionLoading = ref(false)
const scrapeVersionOk      = ref(false)

// ── Selected game IDs ──────────────────────────────────────────────────────────
const selectedSsId         = ref<string | null>(props.rom.ss_id || null)
const selectedIgdbId       = ref<number | null>(props.rom.igdb_id || null)
const selectedLaunchboxId  = ref<string | null>((props.rom as any).launchbox_id || null)
const allMedia       = ref<AllMedia>({
  covers: [], fanarts: [], screenshots: [],
  supports: [], wheels: [], bezels: [],
  steamgrids: [], videos: [], details: null,
  detail_sources: [],
})
const mediaLoading = ref(false)

// ── Image selections ───────────────────────────────────────────────────────────
const selectedCover     = ref(props.rom.cover_path      || '')
const selectedHero      = ref(props.rom.background_path || '')
const selectedSupport   = ref(props.rom.support_path    || '')
const selectedWheel     = ref(props.rom.wheel_path      || '')
const selectedBezel     = ref(props.rom.bezel_path      || '')
const selectedSteamGrid = ref(props.rom.steamgrid_path  || '')
const selectedVideo     = ref(props.rom.video_path      || '')
const manualCoverUrl    = ref('')

// ── Screenshots edit ───────────────────────────────────────────────────────────
const editScreenshots = ref<string[]>([...(props.rom.screenshots || [])])
const ssNewUrl = ref('')

// ── Edit fields ────────────────────────────────────────────────────────────────
const editFields = ref({
  name:         props.rom.name || '',
  summary:      props.rom.summary || '',
  developer:    props.rom.developer || '',
  publisher:    props.rom.publisher || '',
  release_year: props.rom.release_year ?? (null as number | null),
  rating:       props.rom.rating ?? (null as number | null),
  genres:       (props.rom.genres    || []).join(', '),
  regions:      (props.rom.regions   || []).join(', '),
  languages:    (props.rom.languages || []).join(', '),
  player_count: props.rom.player_count || '',
})

// ── Save state ─────────────────────────────────────────────────────────────────
const saving    = ref(false)
const saveOk    = ref(false)
const saveError = ref('')

// ── Computed ───────────────────────────────────────────────────────────────────
const currentCoverSrc = computed(() => selectedCover.value || props.rom.cover_path || '')

// Returns CSS class for cover grid thumbnails based on SS media type
function coverAspectClass(type: string): string {
  if (type === 'box-2D-side') return 'ar-spine'           // very narrow spine
  if (type === 'box-2D-back' || type === 'box-texture') return 'ar-back'  // landscape
  if (type === 'steamgrid') return 'ar-wide'              // 460x215 banner
  return ''  // default: 3/4 portrait (box-2D, box-3D, etc.)
}

// Source icon mapping
function sourceIcon(source: string): string {
  const map: Record<string, string> = {
    ss:        '/icons/ScreenScraper.ico',
    igdb:      '/icons/igdb.ico',
    sgdb:      '/icons/steamgriddb.ico',
    lb:        '/icons/launchbox.ico',
    launchbox: '/icons/launchbox.ico',
    plugin:    '/icons/igdb.ico',
  }
  return map[source] || pluginLogoUrl(source)
}

function isResultSelected(result: SearchResult): boolean {
  if (result.source === 'ss' && result.ss_id) return selectedSsId.value === result.ss_id
  if (result.source === 'igdb' && result.igdb_id) return selectedIgdbId.value === result.igdb_id
  if (result.source === 'launchbox' && (result as any).launchbox_id) return selectedLaunchboxId.value === (result as any).launchbox_id
  return false
}

// The currently selected result that supports "Scrape this version" (SS or LB)
const scrapeableResult = computed(() => {
  if (selectedSsId.value) return ssResults.value.find(r => r.ss_id === selectedSsId.value) || null
  if (selectedLaunchboxId.value) return ssResults.value.find(r => (r as any).launchbox_id === selectedLaunchboxId.value) || null
  return null
})

const hasChanges = computed(() => {
  if (selectedCover.value     !== (props.rom.cover_path      || '')) return true
  if (selectedHero.value      !== (props.rom.background_path || '')) return true
  if (selectedSupport.value   !== (props.rom.support_path    || '')) return true
  if (selectedWheel.value     !== (props.rom.wheel_path      || '')) return true
  if (selectedBezel.value     !== (props.rom.bezel_path      || '')) return true
  if (selectedSteamGrid.value !== (props.rom.steamgrid_path  || '')) return true
  if (selectedVideo.value     !== (props.rom.video_path      || '')) return true
  if (JSON.stringify(editScreenshots.value) !== JSON.stringify(props.rom.screenshots || [])) return true
  const f = editFields.value
  if (f.name         !== (props.rom.name         || '')) return true
  if (f.summary      !== (props.rom.summary      || '')) return true
  if (f.developer    !== (props.rom.developer    || '')) return true
  if (f.publisher    !== (props.rom.publisher    || '')) return true
  if (f.release_year !== (props.rom.release_year ?? null)) return true
  if (f.rating       !== (props.rom.rating       ?? null)) return true
  if (f.genres    !== (props.rom.genres    || []).join(', ')) return true
  if (f.regions   !== (props.rom.regions   || []).join(', ')) return true
  if (f.languages !== (props.rom.languages || []).join(', ')) return true
  if (f.player_count !== (props.rom.player_count || '')) return true
  return false
})

// ── Tabs ───────────────────────────────────────────────────────────────────────
function switchTab(id: TabId) { activeTab.value = id }

// ── Search ─────────────────────────────────────────────────────────────────────
async function searchGames() {
  ssLoading.value = true; ssSearched.value = false; ssResults.value = []; searchFilter.value = 'all'
  try {
    const { data } = await client.get('/roms/search', {
      params: { query: ssQuery.value.trim() || props.rom.name, platform_slug: props.rom.platform_slug },
    })
    ssResults.value = data; ssSearched.value = true
  } catch {
    ssSearched.value = true
  } finally {
    ssLoading.value = false
  }
}

async function selectResult(result: SearchResult) {
  if (result.cover_url) selectedCover.value = result.cover_url
  scrapeVersionOk.value = false

  if (result.source === 'sgdb') {
    selectedSsId.value        = null
    selectedIgdbId.value      = null
    selectedLaunchboxId.value = null
  } else if (result.source === 'launchbox') {
    selectedSsId.value        = null
    selectedIgdbId.value      = null
    selectedLaunchboxId.value = (result as any).launchbox_id ?? null
  } else {
    selectedSsId.value        = result.ss_id   ?? null
    selectedIgdbId.value      = result.igdb_id ?? null
    selectedLaunchboxId.value = null
  }

  mediaLoading.value = true
  try {
    const params: Record<string, any> = { platform_slug: props.rom.platform_slug }
    if (result.source === 'sgdb') {
      if (result.sgdb_id) params.sgdb_id = result.sgdb_id
    } else if (result.source === 'launchbox') {
      if ((result as any).launchbox_id) params.launchbox_id = (result as any).launchbox_id
      params.igdb_query = result.name  // also fetch IGDB data
    } else {
      if (result.ss_id)   params.ss_id     = result.ss_id
      if (result.igdb_id) params.igdb_id   = result.igdb_id
      else                params.igdb_query = result.name
    }

    const { data } = await client.get(`/roms/${props.rom.id}/all-media`, { params })
    allMedia.value = data
  } catch {
    allMedia.value = {
      covers: [], fanarts: [], screenshots: [],
      supports: [], wheels: [], bezels: [],
      steamgrids: [], videos: [], details: null,
      detail_sources: [],
    }
  } finally {
    mediaLoading.value = false
  }
}

async function scrapeThisVersion() {
  if (!selectedSsId.value && !selectedLaunchboxId.value) return
  scrapeVersionLoading.value = true
  scrapeVersionOk.value = false
  try {
    const body: Record<string, string> = {}
    if (selectedSsId.value) body.forced_ss_id = selectedSsId.value
    if (selectedLaunchboxId.value) body.forced_launchbox_id = selectedLaunchboxId.value
    await client.post(`/roms/${props.rom.id}/scrape`, body)
    scrapeVersionOk.value = true
    // Give the user 2s to read the message then close - scrape runs in background
    setTimeout(() => {
      emit('saved')
      emit('close')
    }, 2000)
  } catch {
    // silent - user can retry
  } finally {
    scrapeVersionLoading.value = false
  }
}

function applyManualCover() {
  if (!manualCoverUrl.value.trim()) return
  selectedCover.value = manualCoverUrl.value.trim()
  manualCoverUrl.value = ''
}

// ── Screenshots ────────────────────────────────────────────────────────────────
function addSSUrl() {
  const u = ssNewUrl.value.trim()
  if (!u || editScreenshots.value.includes(u)) return
  editScreenshots.value.push(u)
  ssNewUrl.value = ''
}

function toggleSSScreenshot(url: string) {
  const idx = editScreenshots.value.indexOf(url)
  if (idx >= 0) editScreenshots.value.splice(idx, 1)
  else editScreenshots.value.push(url)
}

function moveSS(from: number, to: number) {
  const arr = editScreenshots.value
  const item = arr.splice(from, 1)[0]
  arr.splice(to, 0, item)
}

// ── Apply details from a single source ────────────────────────────────────────
function applyDetailSource(src: DetailSource) {
  if (src.developer)       editFields.value.developer    = src.developer
  if (src.publisher)       editFields.value.publisher    = src.publisher
  if (src.release_year)    editFields.value.release_year = src.release_year
  if (src.rating != null)  editFields.value.rating       = src.rating
  if (src.genres?.length)  editFields.value.genres       = src.genres.join(', ')
  if (src.regions?.length) editFields.value.regions      = src.regions.join(', ')
  if (src.player_count)    editFields.value.player_count = src.player_count
  if (src.description)     editFields.value.summary      = src.description
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function save() {
  saving.value = true; saveOk.value = false; saveError.value = ''
  try {
    const parseArr = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean)
    const payload: Record<string, unknown> = {}

    // Helper: remote URL → download via backend (*_url); local path → direct set (*_path)
    function mediaField(val: string, urlKey: string, pathKey: string, original: string) {
      if (!val || val === original) return
      if (val.startsWith('http')) payload[urlKey]  = val
      else                        payload[pathKey] = val
    }

    mediaField(selectedCover.value,     'cover_url',      'cover_path',      props.rom.cover_path      || '')
    mediaField(selectedHero.value,      'background_url', 'background_path', props.rom.background_path || '')
    mediaField(selectedSupport.value,   'support_url',    'support_path',    props.rom.support_path    || '')
    mediaField(selectedWheel.value,     'wheel_url',      'wheel_path',      props.rom.wheel_path      || '')
    mediaField(selectedBezel.value,     'bezel_url',      'bezel_path',      props.rom.bezel_path      || '')
    mediaField(selectedSteamGrid.value, 'steamgrid_url',  'steamgrid_path',  props.rom.steamgrid_path  || '')
    mediaField(selectedVideo.value,     'video_url',      'video_path',      props.rom.video_path      || '')

    if (JSON.stringify(editScreenshots.value) !== JSON.stringify(props.rom.screenshots || []))
      payload.screenshots = editScreenshots.value

    const f = editFields.value
    if (f.name         !== (props.rom.name         || '')) payload.name         = f.name
    if (f.summary      !== (props.rom.summary      || '')) payload.summary      = f.summary
    if (f.developer    !== (props.rom.developer    || '')) payload.developer    = f.developer
    if (f.publisher    !== (props.rom.publisher    || '')) payload.publisher    = f.publisher
    if (f.release_year !== (props.rom.release_year ?? null)) payload.release_year = f.release_year
    if (f.rating       !== (props.rom.rating       ?? null)) payload.rating     = f.rating
    if (f.genres    !== (props.rom.genres    || []).join(', ')) payload.genres    = parseArr(f.genres)
    if (f.regions   !== (props.rom.regions   || []).join(', ')) payload.regions   = parseArr(f.regions)
    if (f.languages !== (props.rom.languages || []).join(', ')) payload.languages = parseArr(f.languages)
    if (f.player_count !== (props.rom.player_count || '')) payload.player_count = f.player_count

    if (Object.keys(payload).length) {
      await client.patch(`/roms/${props.rom.id}`, payload)
    }
    saveOk.value = true
    emit('saved')
    setTimeout(() => emit('close'), 700)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* ── Overlay & Panel ────────────────────────────────────────────────────────── */
.mep-overlay {
  position: fixed; inset: 0; z-index: 1200;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.mep-panel {
  width: 92vw; max-width: 1260px; height: 88vh;
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  display: flex; flex-direction: column; overflow: hidden;
}

/* ── Header ─────────────────────────────────────────────────────────────────── */
.mep-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,.07);
  background: rgba(255,255,255,.03); flex-shrink: 0;
}
.mep-header-left { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: .85rem; font-weight: 600; }
.mep-game-name   { font-weight: 400; opacity: .5; font-size: .82rem; }
.mep-close {
  background: none; border: none; cursor: pointer; color: rgba(255,255,255,.4);
  display: flex; align-items: center; padding: var(--space-1, 4px);
  border-radius: var(--radius-xs, 4px); transition: color .15s, background .15s;
}
.mep-close:hover { color: #fff; background: rgba(255,255,255,.08); }

/* ── Body ───────────────────────────────────────────────────────────────────── */
.mep-body { display: flex; flex: 1; overflow: hidden; }

/* ── Left sidebar ───────────────────────────────────────────────────────────── */
.mep-left {
  width: 170px; flex-shrink: 0; padding: 14px 12px;
  border-right: 1px solid rgba(255,255,255,.07);
  overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-1, 4px);
}
.mep-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; opacity: .45; margin-bottom: 4px; }
.mep-cover-current, .mep-cover-selected-wrap {
  background: rgba(255,255,255,.04); border-radius: 6px; overflow: hidden;
  display: flex; align-items: center; justify-content: center; min-height: 60px;
  position: relative;
}
.mep-cover-current--wide { aspect-ratio: 16/9; }
.mep-cover-img { width: 100%; height: auto; max-height: 220px; object-fit: contain; display: block; background: rgba(0,0,0,.15); }
.mep-cover-empty { width: 100%; height: 80px; display: flex; align-items: center; justify-content: center; }

/* ── Right ──────────────────────────────────────────────────────────────────── */
.mep-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.mep-tabs {
  display: flex; gap: 2px; padding: 10px 14px 0;
  border-bottom: 1px solid rgba(255,255,255,.07); flex-shrink: 0; flex-wrap: wrap;
}
.mep-tab {
  background: none; border: none; color: rgba(255,255,255,.45);
  font-size: .75rem; padding: 6px 11px; border-radius: 6px 6px 0 0;
  cursor: pointer; transition: all .15s; white-space: nowrap;
}
.mep-tab:hover  { color: rgba(255,255,255,.7); background: rgba(255,255,255,.05); }
.mep-tab.active { color: #fff; background: rgba(255,255,255,.09); border-bottom: 2px solid #6366f1; }
.mep-tab-content { flex: 1; overflow-y: auto; padding: 14px; }

/* ── Source sections ────────────────────────────────────────────────────────── */
.mep-source-section { margin-bottom: 18px; }
.mep-source-header {
  display: flex; align-items: center; gap: 7px;
  font-size: .75rem; font-weight: 600; margin-bottom: 10px; opacity: .85;
}
.mep-source-name { font-weight: 600; }
.mep-source-hint { font-size: .68rem; opacity: .4; font-weight: 400; }

/* ── Scrape this version box ────────────────────────────────────────────────── */
.mep-scrape-version-box {
  border: 1px solid rgba(232,100,0,.35) !important;
  background: rgba(232,100,0,.06) !important;
  display: flex; flex-direction: column; gap: var(--space-3, 12px);
}
.mep-scrape-version-card {
  display: flex; gap: var(--space-3, 12px); align-items: flex-start;
}
.mep-scrape-version-cover {
  width: 64px; min-width: 64px; height: 88px;
  border-radius: 5px; overflow: hidden;
  background: rgba(255,255,255,.05);
  display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(255,255,255,.08);
}
.mep-scrape-version-cover img {
  width: 100%; height: 100%; object-fit: cover;
}
.mep-scrape-version-meta {
  display: flex; flex-direction: column; gap: 5px; min-width: 0;
}
.mep-scrape-version-name {
  font-size: .88rem; font-weight: 700; color: #fff;
  line-height: 1.2; word-break: break-word;
}
.mep-scrape-version-details {
  display: flex; flex-wrap: wrap; gap: 5px; align-items: center;
  font-size: .72rem; color: rgba(255,255,255,.5);
}
.mep-scrape-version-dev { color: rgba(255,255,255,.65); }
.mep-scrape-version-regions {
  letter-spacing: .04em; color: rgba(255,200,100,.7);
}
.mep-scrape-ssid {
  font-family: monospace; font-size: .68rem; opacity: .4;
}
.mep-scrape-version-actions {
  display: flex; align-items: center; gap: var(--space-3, 12px);
}
.mep-scrape-version-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 18px; border-radius: var(--radius-sm, 8px); border: none; cursor: pointer;
  background: #e86400; color: #fff; font-size: .8rem; font-weight: 700;
  font-family: inherit; transition: background .15s;
}
.mep-scrape-version-btn:hover:not(:disabled) { background: #ff7a1a; }
.mep-scrape-version-btn:disabled { opacity: .5; cursor: not-allowed; }
.mep-scrape-version-ok {
  font-size: .78rem; color: #4ade80; font-weight: 600;
}

/* ── Source badges (icon-based, matching Library panel) ─────────────────────── */
.mep-source-badge {
  position: absolute; bottom: 4px; left: 4px;
  width: 20px; height: 20px; border-radius: var(--radius-xs, 4px);
  background: rgba(0,0,0,.65); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 1;
}
.mep-source-badge img { border-radius: 2px; width: 12px !important; height: 12px !important; }

/* ── Small clear button ─────────────────────────────────────────────────────── */
.mep-clear-btn-sm {
  background: none; border: 1px solid rgba(255,255,255,.12);
  color: rgba(255,255,255,.5); font-size: .65rem; padding: 2px 6px;
  border-radius: 3px; cursor: pointer;
}
.mep-clear-btn-sm:hover { border-color: rgba(255,255,255,.3); color: rgba(255,255,255,.8); }

/* ── Search row ─────────────────────────────────────────────────────────────── */
.mep-search-row { display: flex; gap: 6px; margin-bottom: 10px; }
.mep-search-input {
  flex: 1; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  color: #fff; padding: 7px 10px; border-radius: 6px; font-size: .8rem; outline: none;
  transition: border-color .15s;
}
.mep-search-input:focus { border-color: rgba(99,102,241,.5); }
.mep-search-btn {
  display: flex; align-items: center; gap: 5px;
  background: rgba(99,102,241,.2); border: 1px solid rgba(99,102,241,.3);
  color: rgba(255,255,255,.8); padding: 7px 12px; border-radius: 6px;
  font-size: .78rem; cursor: pointer; transition: all .15s; white-space: nowrap;
}
.mep-search-btn:hover:not(:disabled) { background: rgba(99,102,241,.35); }
.mep-search-btn:disabled { opacity: .4; cursor: default; }

/* ── Cover grid ─────────────────────────────────────────────────────────────── */
.mep-covers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: var(--space-2, 8px); align-items: start; }
.mep-covers-grid--wide { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
.mep-cover-option { cursor: pointer; border-radius: 6px; overflow: hidden; position: relative; }
.mep-cover-option:hover .mep-cover-option-img { opacity: .8; }
.mep-cover-option.selected .mep-cover-option-img { outline: 2px solid #6366f1; }
.mep-cover-option-img { background: rgba(255,255,255,.04); position: relative; overflow: hidden; aspect-ratio: 3/4; }
.mep-cover-option-img.ar-spine  { aspect-ratio: 1/3; }
.mep-cover-option-img.ar-back   { aspect-ratio: 4/3; }
.mep-cover-option-img.ar-wide   { aspect-ratio: 16/9; }
.mep-cover-option-img.ar-square { aspect-ratio: 1/1; }
.mep-cover-option-img img { width: 100%; height: 100%; object-fit: contain; background: rgba(0,0,0,.15); }
.mep-cover-option-img--wide { aspect-ratio: 16/9; }
.mep-cover-no-img { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.mep-cover-label  { font-size: .66rem; opacity: .5; padding: 3px 3px 1px; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mep-cover-author { font-size: .62rem; opacity: .35; padding: 0 3px 3px; text-align: center; }
.mep-selected-check {
  position: absolute; bottom: 4px; right: 4px;
  background: #6366f1; border-radius: 50%; width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
}

/* ── Loading / empty ────────────────────────────────────────────────────────── */
.mep-loading { display: flex; align-items: center; gap: var(--space-2, 8px); font-size: .78rem; opacity: .6; padding: 8px 0; }
.mep-empty-state-sm { font-size: .75rem; opacity: .4; padding: 8px 0; font-style: italic; }

/* ── Screenshots list ───────────────────────────────────────────────────────── */
.mep-ss-list { display: flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; }
.mep-ss-item { display: flex; align-items: center; gap: var(--space-2, 8px); background: rgba(255,255,255,.04); border-radius: 6px; padding: 6px; }
.mep-ss-item-thumb { width: 80px; height: 45px; object-fit: cover; border-radius: 3px; flex-shrink: 0; }
.mep-ss-order-col { display: flex; flex-direction: column; align-items: center; gap: 2px; margin-left: auto; }
.mep-ss-ord-btn { background: none; border: none; color: rgba(255,255,255,.4); cursor: pointer; font-size: .65rem; padding: 1px 3px; }
.mep-ss-ord-btn:hover:not(:disabled) { color: #fff; }
.mep-ss-ord-btn:disabled { opacity: .2; }
.mep-ss-num { font-size: .68rem; opacity: .4; }
.mep-ss-remove--list { background: none; border: none; color: rgba(255,80,80,.5); cursor: pointer; font-size: .8rem; padding: 2px 6px; border-radius: 3px; }
.mep-ss-remove--list:hover { color: #f87171; }

/* ── Video ──────────────────────────────────────────────────────────────────── */
.mep-video-preview { width: 100%; border-radius: 6px; background: #000; max-height: 200px; }
.mep-video-thumb   { background: #000; }
.mep-video-mini    { width: 100%; height: 100%; object-fit: cover; }

/* ── Description ────────────────────────────────────────────────────────────── */
.mep-desc-list { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.mep-desc-source { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: var(--radius-sm, 8px); padding: 10px 12px; }
.mep-desc-source-header { display: flex; align-items: center; gap: var(--space-2, 8px); margin-bottom: 6px; }
.mep-desc-source-icon { flex-shrink: 0; width: 16px; height: 16px; }
.mep-desc-source-icon img { border-radius: 2px; }
.mep-desc-source-name { flex: 1; font-size: .78rem; font-weight: 600; color: rgba(255,255,255,.7); }
.mep-desc-apply-btn {
  background: rgba(99,102,241,.2); border: 1px solid rgba(99,102,241,.35);
  color: #a5b4fc; font-size: .72rem; padding: 3px 9px;
  border-radius: var(--radius-xs, 4px); cursor: pointer; white-space: nowrap; transition: background .15s; margin-left: auto;
}
.mep-desc-apply-btn:hover { background: rgba(99,102,241,.35); }
.mep-desc-preview { font-size: .73rem; color: rgba(255,255,255,.45); line-height: 1.5; max-height: 72px; overflow: hidden; }

/* ── Detail chips ───────────────────────────────────────────────────────────── */
.mep-detail-sources { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.mep-detail-source { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: var(--radius-sm, 8px); padding: 10px 12px; }
.mep-detail-grid { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.mep-detail-chip { font-size: .72rem; color: rgba(255,255,255,.65); background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); border-radius: var(--radius-xs, 4px); padding: 2px 7px; white-space: nowrap; }
.mep-detail-chip b { color: rgba(255,255,255,.4); font-weight: 600; margin-right: 3px; }

/* ── Form fields ────────────────────────────────────────────────────────────── */
.mep-form { display: flex; flex-direction: column; gap: 10px; }
.mep-form-section-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .07em; opacity: .4; padding-top: 6px; }
.mep-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.mep-field { display: flex; flex-direction: column; gap: var(--space-1, 4px); }
.mep-field-label { font-size: .72rem; opacity: .6; }
.mep-field-hint { opacity: .45; font-weight: 400; }
.mep-field-row { display: flex; gap: 6px; }
.mep-input {
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  color: #fff; padding: 7px 10px; border-radius: 6px; font-size: .8rem;
  outline: none; transition: border-color .15s; flex: 1;
}
.mep-input:focus { border-color: rgba(99,102,241,.5); }
.mep-textarea {
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  color: #fff; padding: 8px 10px; border-radius: 6px; font-size: .8rem;
  outline: none; resize: vertical; font-family: inherit; line-height: 1.5;
  transition: border-color .15s;
}
.mep-textarea:focus { border-color: rgba(99,102,241,.5); }
.mep-apply-btn {
  background: rgba(99,102,241,.18); border: 1px solid rgba(99,102,241,.3);
  color: #a5b4fc; padding: 6px 12px; border-radius: 5px; font-size: .76rem;
  cursor: pointer; transition: all .15s; white-space: nowrap; flex-shrink: 0;
}
.mep-apply-btn:hover:not(:disabled) { background: rgba(99,102,241,.3); }
.mep-apply-btn:disabled { opacity: .35; cursor: default; }

/* ── Footer ─────────────────────────────────────────────────────────────────── */
.mep-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-top: 1px solid rgba(255,255,255,.07);
  background: rgba(255,255,255,.02); flex-shrink: 0;
}
.mep-save-status { font-size: .8rem; min-height: 1.2em; }
.mep-ok  { color: #34d399; }
.mep-err { color: #f87171; }
.mep-footer-actions { display: flex; gap: var(--space-2, 8px); }
.mep-btn-cancel {
  background: none; border: 1px solid rgba(255,255,255,.12);
  color: rgba(255,255,255,.55); padding: 7px 16px; border-radius: 7px;
  font-size: .82rem; cursor: pointer; transition: all .15s;
}
.mep-btn-cancel:hover { border-color: rgba(255,255,255,.3); color: #fff; }
.mep-btn-save {
  background: #6366f1; border: none; color: #fff;
  padding: 7px 20px; border-radius: 7px; font-size: .82rem;
  cursor: pointer; display: flex; align-items: center; gap: 6px;
  transition: background .15s;
}
.mep-btn-save:hover:not(:disabled) { background: #818cf8; }
.mep-btn-save:disabled { opacity: .45; cursor: default; }

/* ── Search filter ──────────────────────────────────────────────────────────── */
.mep-source-filter {
  display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap;
}
.mep-filter-btn {
  display: flex; align-items: center; gap: var(--space-1, 4px);
  padding: 4px 10px; border-radius: 20px; border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.04); color: rgba(255,255,255,.55);
  font-size: .78rem; cursor: pointer; transition: all .15s;
}
.mep-filter-btn img { border-radius: 2px; flex-shrink: 0; }
.mep-filter-btn:hover { border-color: rgba(255,255,255,.25); color: #fff; }
.mep-filter-btn.active { background: rgba(99,102,241,.25); border-color: rgba(99,102,241,.5); color: #a5b4fc; }
.mep-filter-count {
  background: rgba(255,255,255,.1); color: rgba(255,255,255,.5);
  border-radius: 10px; padding: 0 5px; font-size: .72rem; min-width: 18px; text-align: center;
}
.mep-filter-btn.active .mep-filter-count { background: rgba(99,102,241,.3); color: #a5b4fc; }


/* ── Spinner ────────────────────────────────────────────────────────────────── */
.mep-spinner {
  width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.2);
  border-top-color: #6366f1; border-radius: 50%; animation: spin .7s linear infinite;
  flex-shrink: 0;
}
.mep-spinner--sm { width: 12px; height: 12px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .mep-panel { width: 100vw; height: 100vh; border-radius: 0; max-width: none; }
  .mep-left { display: none; }
  .mep-tabs { flex-wrap: wrap; gap: 2px; }
  .mep-tab { font-size: .68rem; padding: 6px 8px; }
  .mep-header { padding: 10px 14px; }
  .mep-tab-content { padding: 10px; }
  .mep-covers-grid { grid-template-columns: repeat(auto-fill, minmax(75px, 1fr)); gap: 6px; }
  .mep-form-row { grid-template-columns: 1fr; }
}
</style>
