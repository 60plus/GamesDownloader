<template>
  <!-- Fullscreen overlay -->
  <div class="mep-overlay" @click.self="$emit('close')">
    <div class="mep-panel" @click.stop>

      <!-- ── Header ──────────────────────────────────────────────────────────── -->
      <div class="mep-header">
        <div class="mep-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <span>{{ t('meta.edit_title') }}</span>
          <span class="mep-game-name">- {{ collection.name }}</span>
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
            <img v-if="selectedCoverThumb || selectedCover" :src="selectedCoverThumb || selectedCover" alt="Cover" class="mep-cover-img" @error="onThumbError" />
            <div v-else class="mep-cover-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="2" y="6" width="20" height="12" rx="2"/></svg>
            </div>
            <div v-if="selectedCoverAnimated" class="mep-anim-badge">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
              ANIM
            </div>
          </div>

          <!-- Upload / revert (collections support a custom cover upload) -->
          <label class="mep-upload-btn" style="margin-top:8px">
            <input type="file" accept="image/png,image/jpeg,image/webp" class="mep-file-input" @change="onCoverFile" />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            {{ coverUploadBusy ? t('meta.saving') : t('collections.cover_upload') }}
          </label>
          <button v-if="selectedCover" class="mep-clear-btn" :disabled="coverUploadBusy" @click="revertCover">{{ t('collections.cover_revert') }}</button>
          <div v-if="coverUploadMsg" class="mep-cover-msg">{{ coverUploadMsg }}</div>

          <!-- Hero -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_hero') }}</div>
          <div class="mep-cover-current mep-cover-current--wide" @click="switchTab('background')" style="cursor:pointer">
            <img v-if="selectedBackground" :src="selectedBackground" alt="Hero" class="mep-cover-img" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><rect x="1" y="5" width="22" height="14" rx="2"/></svg>
            </div>
          </div>

          <!-- Upload / revert (same mechanics as the cover above) -->
          <label class="mep-upload-btn" style="margin-top:8px">
            <input type="file" accept="image/png,image/jpeg,image/webp" class="mep-file-input" @change="onHeroFile" />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            {{ heroUploadBusy ? t('meta.saving') : t('collections.hero_upload') }}
          </label>
          <button v-if="selectedBackground" class="mep-clear-btn" :disabled="heroUploadBusy" @click="revertHero">{{ t('collections.hero_revert') }}</button>
          <div v-if="heroUploadMsg" class="mep-cover-msg">{{ heroUploadMsg }}</div>

          <!-- Logo -->
          <div class="mep-label" style="margin-top:12px">{{ t('meta.tab_logo') }}</div>
          <div class="mep-cover-current mep-cover-current--logo" @click="switchTab('logo')" style="cursor:pointer">
            <img v-if="selectedLogo" :src="selectedLogo" alt="Logo" style="width:100%;height:100%;object-fit:contain;padding:6px" />
            <div v-else class="mep-cover-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="opacity:.2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
          </div>

          <!-- Upload / revert (same mechanics as the cover above) -->
          <label class="mep-upload-btn" style="margin-top:8px">
            <input type="file" accept="image/png,image/jpeg,image/webp" class="mep-file-input" @change="onLogoFile" />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            {{ logoUploadBusy ? t('meta.saving') : t('collections.logo_upload') }}
          </label>
          <button v-if="selectedLogo" class="mep-clear-btn" :disabled="logoUploadBusy" @click="revertLogo">{{ t('collections.logo_revert') }}</button>
          <div v-if="logoUploadMsg" class="mep-cover-msg">{{ logoUploadMsg }}</div>
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
          <!-- DESCRIPTION TAB                                                    -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'description'" class="mep-tab-content">

            <!-- Fetch row -->
            <div class="mep-search-row">
              <input v-model="descQuery" class="mep-search-input" placeholder="Collection name to search…" @keydown.enter="loadDescriptions(true)" />
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
                    <span v-else class="mep-wiki-badge">WIKIPEDIA</span>
                  </div>
                  <div class="mep-desc-source-name">{{ src.name }}</div>
                  <button class="mep-desc-apply-btn" :disabled="applyingDesc === (src.source + src.name)" @click="applyDescription(src)">
                    <div v-if="applyingDesc === (src.source + src.name)" class="mep-spinner mep-spinner--sm" />
                    <span v-else>{{ t('meta.use_description') }}</span>
                  </button>
                </div>
                <div class="mep-desc-preview">
                  <template v-if="src.description">
                    {{ src.description.replace(/<[^>]+>/g, ' ').slice(0, 400) }}{{ src.description.length > 400 ? '…' : '' }}
                  </template>
                  <template v-else-if="src._snippet">
                    {{ src._snippet.replace(/<[^>]+>/g, ' ').slice(0, 400) }}{{ src._snippet.length > 400 ? '…' : '' }}
                  </template>
                </div>
              </div>
            </div>

            <!-- Manual edit (always visible below sources) -->
            <div class="mep-form" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--glass-border)">
              <div class="mep-field">
                <label class="mep-field-label">{{ t('meta.full_desc') }} <span class="mep-field-hint">({{ t('meta.html_hint') }})</span> <TranslateButton :text="editFields.description || ''" @translated="tr => editFields.description = tr" /></label>
                <textarea v-model="editFields.description" class="mep-textarea" rows="7" placeholder="Full description…" />
              </div>
              <div class="mep-field" style="margin-top:10px">
                <label class="mep-field-label">{{ t('meta.short_desc') }} <TranslateButton :text="editFields.description_short || ''" @translated="tr => editFields.description_short = tr" /></label>
                <textarea v-model="editFields.description_short" class="mep-textarea" rows="3" placeholder="Short tagline or summary…" />
              </div>
            </div>
          </div>

          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <!-- DETAILS TAB (collection form)                                      -->
          <!-- ═══════════════════════════════════════════════════════════════════ -->
          <div v-if="activeTab === 'details'" class="mep-tab-content">

            <div class="mep-form">

              <div class="mep-form-section-label">{{ t('meta.info') }}</div>

              <div class="mep-field">
                <label class="mep-field-label">Name</label>
                <input v-model="cName" class="mep-input" placeholder="Collection name" />
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">Year range</div>

              <div class="mep-field">
                <label class="mep-os-check-label"><input type="checkbox" v-model="cYearsAuto" /><span>Auto (from games)</span></label>
                <div v-if="!cYearsAuto" class="mep-form-row" style="margin-top:8px">
                  <div class="mep-field">
                    <label class="mep-field-label">From</label>
                    <input v-model.number="cYearFrom" class="mep-input" type="number" placeholder="YYYY" />
                  </div>
                  <div class="mep-field">
                    <label class="mep-field-label">To</label>
                    <input v-model.number="cYearTo" class="mep-input" type="number" placeholder="YYYY" />
                  </div>
                </div>
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">Rating (0-5)</div>

              <div class="mep-field">
                <label class="mep-os-check-label"><input type="checkbox" v-model="cRatingAuto" /><span>Auto (average of games)</span></label>
                <input v-if="!cRatingAuto" v-model.number="cRatingManual" class="mep-input" type="number" min="0" max="5" step="0.1" style="margin-top:8px" />
                <span v-else class="mep-field-hint" style="margin-top:6px">{{ avgRatingHint }}</span>
              </div>

              <div class="mep-form-section-label" style="margin-top:4px;">Time to Beat</div>

              <div class="mep-field">
                <label class="mep-os-check-label"><input type="checkbox" v-model="cHltbAuto" /><span>Auto (from games)</span></label>
                <div v-if="!cHltbAuto" class="mep-form-row" style="margin-top:8px">
                  <div class="mep-field">
                    <label class="mep-field-label">Main (hours)</label>
                    <input v-model.number="cHltbMainH" class="mep-input" type="number" min="0" step="0.5" />
                  </div>
                  <div class="mep-field">
                    <label class="mep-field-label">Completionist (hours)</label>
                    <input v-model.number="cHltbCompleteH" class="mep-input" type="number" min="0" step="0.5" />
                  </div>
                </div>
              </div>

            </div>
          </div>

        </div>
      </div>

      <!-- ── Footer ──────────────────────────────────────────────────────────── -->
      <div class="mep-footer">
        <button class="mep-btn-delete" :disabled="saving" @click="onDelete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          {{ t('collections.delete') }}
        </button>
        <div class="mep-footer-right">
          <span v-if="saveError" class="mep-err">{{ saveError }}</span>
          <span v-else-if="saveOk" class="mep-ok">✓ {{ t('meta.saved') }}</span>
          <button class="mep-btn-cancel" @click="$emit('close')">{{ t('meta.cancel') }}</button>
          <button class="mep-btn-save" :disabled="saving" @click="save">
            <div v-if="saving" class="mep-spinner mep-spinner--sm" />
            {{ saving ? t('meta.saving') : t('meta.save_changes') }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import TranslateButton from '@/components/common/TranslateButton.vue'
import { useI18n } from '@/i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()
const { gdConfirm } = useDialog()

interface CoverOption {
  url: string; thumb?: string; type: 'static' | 'animated'; label: string; author?: string; asset_type?: string
  _source?: string; _sourceIcon?: string
}

const props = defineProps<{ collection: any }>()
const emit  = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
  (e: 'deleted', slug: string): void
}>()

const tabs = computed(() => [
  { id: 'cover',        label: t('meta.tab_cover')        },
  { id: 'background',   label: t('meta.tab_hero')         },
  { id: 'logo',         label: t('meta.tab_logo')         },
  { id: 'description',  label: t('meta.tab_description')  },
  { id: 'details',      label: t('meta.tab_details')      },
])
const activeTab = ref('cover')

// ── Cover selection ────────────────────────────────────────────────────────────
const selectedCover         = ref(props.collection.cover_path || '')
const selectedCoverThumb    = ref('')
const selectedCoverAnimated = ref(false)
const selectedBackground    = ref(props.collection.hero_path || '')
const selectedLogo          = ref(props.collection.logo_path || '')

// ── Unified cover search ─────────────────────────────────────────────────────
const coverSearchQuery  = ref(props.collection.name)
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

// ── Unified hero/background search ───────────────────────────────────────────
const heroSearchQuery = ref(props.collection.name)
const heroSearching   = ref(false)
const heroSearchDone  = ref(false)
const allHeroResults  = ref<CoverOption[]>([])

// ── Unified logo search ─────────────────────────────────────────────────────
const logoSearchQuery = ref(props.collection.name)
const logoSearching   = ref(false)
const logoSearchDone  = ref(false)
const allLogoResults  = ref<CoverOption[]>([])

// ── Cover upload (multipart) ─────────────────────────────────────────────────
const coverUploadBusy = ref(false)
const coverUploadMsg  = ref('')

async function onCoverFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  coverUploadBusy.value = true; coverUploadMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await client.post(`/collections/${props.collection.slug}/cover`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    selectedCover.value = data.cover_path
    selectedCoverThumb.value = ''
    selectedCoverAnimated.value = false
    coverUploadMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverUploadMsg.value = err?.response?.data?.detail || 'Upload failed'
  } finally {
    coverUploadBusy.value = false
    input.value = ''
  }
}

async function revertCover() {
  coverUploadBusy.value = true; coverUploadMsg.value = ''
  try {
    await client.patch(`/collections/${props.collection.slug}`, { cover_path: null })
    selectedCover.value = ''
    selectedCoverThumb.value = ''
    selectedCoverAnimated.value = false
    coverUploadMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverUploadMsg.value = err?.response?.data?.detail || 'Failed'
  } finally {
    coverUploadBusy.value = false
  }
}

// ── Hero / logo upload + revert (same mechanics as the cover above) ──────────
const heroUploadBusy = ref(false)
const heroUploadMsg  = ref('')
const logoUploadBusy = ref(false)
const logoUploadMsg  = ref('')

async function _uploadArtFile(e: Event, kind: 'hero' | 'logo') {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const busy = kind === 'hero' ? heroUploadBusy : logoUploadBusy
  const msg  = kind === 'hero' ? heroUploadMsg  : logoUploadMsg
  busy.value = true; msg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await client.post(`/collections/${props.collection.slug}/${kind}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (kind === 'hero') selectedBackground.value = data.hero_path
    else selectedLogo.value = data.logo_path
    msg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    msg.value = err?.response?.data?.detail || 'Upload failed'
  } finally {
    busy.value = false
    input.value = ''
  }
}

async function _revertArt(kind: 'hero' | 'logo') {
  const busy = kind === 'hero' ? heroUploadBusy : logoUploadBusy
  const msg  = kind === 'hero' ? heroUploadMsg  : logoUploadMsg
  busy.value = true; msg.value = ''
  try {
    await client.patch(`/collections/${props.collection.slug}`, { [`${kind}_path`]: null })
    if (kind === 'hero') selectedBackground.value = ''
    else selectedLogo.value = ''
    msg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    msg.value = err?.response?.data?.detail || 'Failed'
  } finally {
    busy.value = false
  }
}

function onHeroFile(e: Event) { _uploadArtFile(e, 'hero') }
function onLogoFile(e: Event) { _uploadArtFile(e, 'logo') }
function revertHero() { _revertArt('hero') }
function revertLogo() { _revertArt('logo') }

// ── Description sources ────────────────────────────────────────────────────────
const descQuery   = ref(props.collection.name || '')
const descLoading = ref(false)
const descFetched = ref(false)
interface DescSource {
  source: string; name: string; description: string; description_short: string
  _snippet?: string; _fetchProvider?: string; _fetchId?: string
}
const descSources = ref<DescSource[]>([])
const applyingDesc = ref('')

async function loadDescriptions(force = false) {
  if (descLoading.value) return
  if (descFetched.value && !force) return
  descLoading.value = true
  descFetched.value = false
  descSources.value = []
  const q = descQuery.value.trim() || props.collection.name || ''
  const base = `/collections/${props.collection.slug}/meta-sources`

  const igdbOut: DescSource[] = []
  const rawgOut: DescSource[] = []
  const steamOut: DescSource[] = []
  const wikiOut: DescSource[] = []

  await Promise.all([
    // ── IGDB - up to 3 candidates with a description ─────────────────────────
    client.get(base, { params: { source: 'igdb', q } }).then(({ data }) => {
      for (const c of (data?.candidates || []).slice(0, 3) as any[]) {
        if (c.description) {
          igdbOut.push({
            source: 'igdb', name: c.name || q,
            description: c.description, description_short: c.description_short || '',
          })
        }
      }
    }).catch(() => {}),
    // ── RAWG - first candidate, then detail by slug ──────────────────────────
    client.get(base, { params: { source: 'rawg', q } }).then(async ({ data }) => {
      const top = (data?.candidates || [])[0] as any
      if (!top) return
      const slug = top.slug || String(top.id)
      const detail = await client.get(base, { params: { source: 'rawg-detail', q: slug } })
        .then(r => r.data).catch(() => null)
      if (detail?.description) {
        rawgOut.push({
          source: 'rawg', name: top.name || q,
          description: detail.description, description_short: detail.description_short || '',
        })
      }
    }).catch(() => {}),
    // ── Steam ────────────────────────────────────────────────────────────────
    client.get(base, { params: { source: 'steam', q } }).then(({ data }) => {
      if (data?.found && data.description) {
        steamOut.push({
          source: 'steam', name: data.name || q,
          description: data.description, description_short: data.description_short || '',
        })
      }
    }).catch(() => {}),
    // ── Wikipedia (last) - snippet only, full text fetched on apply ──────────
    client.get('/plugins/metadata/collections/search', { params: { q } }).then(({ data }) => {
      for (const x of (Array.isArray(data) ? data : []).filter((y: any) => y.provider_id === 'wikipedia')) {
        wikiOut.push({
          source: 'wikipedia', name: x.name,
          description: '', description_short: '',
          _snippet: x.snippet || '',
          _fetchProvider: 'wikipedia', _fetchId: x.provider_collection_id,
        })
      }
    }).catch(() => {}),
  ])

  descSources.value = [...igdbOut, ...rawgOut, ...steamOut, ...wikiOut]
  descFetched.value = true
  descLoading.value = false
}

async function applyDescription(src: DescSource) {
  applyingDesc.value = src.source + src.name
  try {
    let desc = src.description
    let short = src.description_short
    if (!desc && src._fetchId) {
      const { data } = await client.get('/plugins/metadata/collections/fetch', {
        params: { provider_id: src._fetchProvider, id: src._fetchId },
      })
      desc = data?.description || ''
      short = data?.description_short || ''
    }
    if (desc) editFields.description = desc
    if (short) editFields.description_short = short
  } catch { /* fetch failed */ } finally {
    applyingDesc.value = ''
  }
}

// ── Description manual fields ───────────────────────────────────────────────────
const editFields = reactive({
  description:       props.collection.description       || '',
  description_short: props.collection.description_short || '',
})

// ── Collection detail form ─────────────────────────────────────────────────────
const cName = ref<string>(props.collection.name || '')
// Year range: auto unless an override is explicitly set.
const cYearsAuto = ref<boolean>(props.collection.start_year_auto !== false && props.collection.end_year_auto !== false)
const cYearFrom  = ref<number | null>(props.collection.start_year ?? null)
const cYearTo    = ref<number | null>(props.collection.end_year ?? null)
// Rating: auto = average of member ratings; override = manual 0-5.
const cRatingAuto   = ref<boolean>(props.collection.rating_auto !== false)
const cRatingManual = ref<number | null>(props.collection.rating_auto === false ? (props.collection.rating ?? null) : null)
// Time to Beat: auto = average of member playtimes; override = manual hours.
const cHltbAuto      = ref<boolean>(props.collection.hltb_auto !== false)
const cHltbMainH     = ref<number | null>(props.collection.hltb_auto === false && props.collection.hltb_main_s ? props.collection.hltb_main_s / 3600 : null)
const cHltbCompleteH = ref<number | null>(props.collection.hltb_auto === false && props.collection.hltb_complete_s ? props.collection.hltb_complete_s / 3600 : null)

const avgRatingHint = computed(() => {
  const r = props.collection.rating
  return r != null ? `Average: ${Number(r).toFixed(1)}/5` : 'No member ratings yet'
})

// ── Save state ────────────────────────────────────────────────────────────────
const saving    = ref(false)
const saveOk    = ref(false)
const saveError = ref('')

// ── Cover actions ─────────────────────────────────────────────────────────────
function selectCover(cover: CoverOption) {
  selectedCover.value         = cover.url
  selectedCoverThumb.value    = cover.thumb || cover.url
  selectedCoverAnimated.value = cover.type === 'animated'
}

function onThumbError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img.src !== selectedCover.value) img.src = selectedCover.value
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(id: string) {
  activeTab.value = id
  if (id === 'cover'       && !coverSearchDone.value) searchAllCovers()
  if (id === 'background'  && !heroSearchDone.value)  searchAllHeroes()
  if (id === 'logo'        && !logoSearchDone.value)  searchAllLogos()
  if (id === 'description' && !descFetched.value)     loadDescriptions()
}

/** Unified cover search - queries GOG + IGDB + SteamGridDB in parallel. */
async function searchAllCovers() {
  coverSearching.value = true
  coverSearchDone.value = false
  allCoverResults.value = []

  const q = coverSearchQuery.value || props.collection.name
  const qEnc = encodeURIComponent(q)
  const baseUrl = `/collections/${props.collection.slug}/covers`

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
    client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=grids`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
    ).catch(() => [] as CoverOption[]),
  ])

  allCoverResults.value = results.flat()
  coverSearchDone.value = true
  coverSearching.value = false
}

/** Unified hero search - queries GOG bg + RAWG + SteamGridDB heroes in parallel. */
async function searchAllHeroes() {
  heroSearching.value = true
  heroSearchDone.value = false
  allHeroResults.value = []

  const q = heroSearchQuery.value || props.collection.name
  const qEnc = encodeURIComponent(q)
  const baseUrl = `/collections/${props.collection.slug}/covers`

  const results = await Promise.all([
    // GOG (returns background)
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
    client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=heroes`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
    ).catch(() => [] as CoverOption[]),
  ])

  allHeroResults.value = results.flat()
  heroSearchDone.value = true
  heroSearching.value = false
}

/** Unified logo search - GOG + SteamGridDB logos + LaunchBox Clear Logo + plugins. */
async function searchAllLogos() {
  logoSearching.value = true
  logoSearchDone.value = false
  allLogoResults.value = []

  const q = logoSearchQuery.value || props.collection.name
  const qEnc = encodeURIComponent(q)
  const baseUrl = `/collections/${props.collection.slug}/covers`

  const results = await Promise.all([
    // GOG (returns logo)
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
    client.get(`${baseUrl}?source=plugins&q=${qEnc}&asset_type=logos`).then(r =>
      (r.data as CoverOption[]).map(c => ({ ...c, _source: c._source || 'Plugin', _sourceIcon: c._sourceIcon || 'gog.ico' }))
    ).catch(() => [] as CoverOption[]),
  ])

  allLogoResults.value = results.flat()
  logoSearchDone.value = true
  logoSearching.value = false
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function save() {
  saving.value = true; saveOk.value = false; saveError.value = ''
  try {
    const payload: Record<string, unknown> = {}

    // Images - scraped external URLs are pulled to the server by the PATCH.
    if (selectedCover.value !== (props.collection.cover_path || '')) {
      payload.cover_path = selectedCover.value || null
    }
    if (selectedBackground.value !== (props.collection.hero_path || '')) {
      payload.hero_path = selectedBackground.value || null
    }
    if (selectedLogo.value !== (props.collection.logo_path || '')) {
      payload.logo_path = selectedLogo.value || null
    }

    // Name + description
    payload.name = cName.value.trim() || props.collection.name
    payload.description = editFields.description || null
    payload.description_short = editFields.description_short || null

    // Year range
    payload.start_year = cYearsAuto.value ? null : (cYearFrom.value != null ? Number(cYearFrom.value) : null)
    payload.end_year   = cYearsAuto.value ? null : (cYearTo.value != null ? Number(cYearTo.value) : null)

    // Rating
    payload.rating = cRatingAuto.value ? null : (cRatingManual.value != null ? Number(cRatingManual.value) : null)

    // Time to Beat
    payload.hltb_main_s     = cHltbAuto.value ? null : (cHltbMainH.value != null ? Math.round(Number(cHltbMainH.value) * 3600) : null)
    payload.hltb_complete_s = cHltbAuto.value ? null : (cHltbCompleteH.value != null ? Math.round(Number(cHltbCompleteH.value) * 3600) : null)

    await client.patch(`/collections/${props.collection.slug}`, payload)
    saveOk.value = true
    emit('updated')
    setTimeout(() => emit('close'), 800)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Save failed'
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  const ok = await gdConfirm(
    t('collections.delete_confirm', { name: props.collection.name }),
    { title: t('collections.delete'), danger: true, confirmText: t('common.delete'), cancelText: t('common.cancel') },
  )
  if (!ok) return
  saving.value = true; saveError.value = ''
  try {
    await client.delete(`/collections/${props.collection.slug}`)
    emit('deleted', props.collection.slug)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Delete failed'
    saving.value = false
  }
}

onMounted(async () => {
  await searchAllCovers()
})
</script>

<style scoped>
/* ── Overlay ──────────────────────────────────────────────────────────────── */
.mep-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  animation: mep-fade-in .18s ease;
}
@keyframes mep-fade-in { from { opacity: 0; } to { opacity: 1; } }

/* ── Panel ────────────────────────────────────────────────────────────────── */
.mep-panel {
  width: 92vw; max-width: 1180px; height: 88vh;
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  display: flex; flex-direction: column; overflow: hidden;
  animation: mep-slide-up .2s cubic-bezier(.23,1,.32,1);
}
@keyframes mep-slide-up { from { transform: translateY(24px); opacity: 0; } to { transform: none; opacity: 1; } }

/* ── Header ───────────────────────────────────────────────────────────────── */
.mep-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px; border-bottom: 1px solid var(--glass-border); flex-shrink: 0;
}
.mep-header-left {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.mep-game-name { color: var(--muted); font-weight: 500; }
.mep-close {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.mep-close:hover { background: rgba(255,255,255,.12); color: var(--text); }

/* ── Body ─────────────────────────────────────────────────────────────────── */
.mep-body { display: flex; flex: 1; overflow: hidden; }

/* ── Left sidebar ─────────────────────────────────────────────────────────── */
.mep-left {
  width: 200px; flex-shrink: 0;
  padding: 18px; border-right: 1px solid var(--glass-border);
  overflow-y: auto; background: rgba(255,255,255,.02);
}
.mep-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 8px;
}
.mep-cover-current, .mep-cover-selected-wrap {
  position: relative; width: 100%; aspect-ratio: 3/4;
  border-radius: 10px; overflow: hidden;
  background: var(--bg3); border: 1px solid var(--glass-border);
}
.mep-cover-current--wide { aspect-ratio: 16/9; }
.mep-cover-current--logo { aspect-ratio: 16/9; background: rgba(0,0,0,.35); }
.mep-cover-current--icon { width: 60px; height: 60px; aspect-ratio: 1/1; background: rgba(0,0,0,.25); }
.mep-cover-selected-wrap--wide { aspect-ratio: 16/9; }
.mep-cover-selected-wrap--logo { aspect-ratio: 16/9; background: rgba(0,0,0,.35); }
.mep-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mep-cover-empty {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
}
.mep-anim-badge {
  position: absolute; bottom: 6px; left: 6px;
  display: flex; align-items: center; gap: 3px;
  padding: 2px 7px; border-radius: var(--radius-xs, 4px);
  background: color-mix(in srgb, var(--pl-light) 85%, transparent); color: #fff;
  font-size: 9px; font-weight: 700; letter-spacing: .5px;
}
.mep-selected-info { margin-top: 2px; }
.mep-clear-btn {
  margin-top: 6px; font-size: 11px; color: var(--muted);
  background: none; border: none; cursor: pointer; padding: 0; font-family: inherit;
}
.mep-clear-btn:hover { color: var(--text); }
.mep-clear-btn:disabled { opacity: .5; cursor: not-allowed; }
.mep-cover-msg { margin-top: 6px; font-size: 12px; color: #4ade80; }

/* ── Right content ────────────────────────────────────────────────────────── */
.mep-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* Tabs */
.mep-tabs {
  display: flex; border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0; padding: 0 20px;
}
.mep-tab {
  padding: 14px 16px; font-size: 13px; font-weight: 600;
  color: var(--muted); border: none; background: none;
  cursor: pointer; border-bottom: 2px solid transparent;
  margin-bottom: -1px; font-family: inherit;
  transition: color .15s, border-color .15s;
}
.mep-tab:hover { color: var(--text); }
.mep-tab.active { color: var(--pl-light); border-bottom-color: var(--pl); }

/* Tab content */
.mep-tab-content { flex: 1; overflow-y: auto; padding: 0 20px 20px; }

/* ── Source sections ──────────────────────────────────────────────────────── */
.mep-source-section {
  padding: 18px 0 12px;
  border-bottom: 1px solid var(--glass-border);
}
.mep-source-section:last-child { border-bottom: none; }
.mep-source-header {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  margin-bottom: 14px;
}
.mep-source-header > img { width: 28px; height: 28px; border-radius: var(--radius-xs, 4px); }
.mep-source-name {
  font-size: var(--fs-sm, 12px); font-weight: 700;
  color: var(--text); text-transform: uppercase; letter-spacing: .8px;
}

/* ── Chip bar ────────────────────────────────────────────────────────────────*/
.mep-chip-bar { display: flex; gap: 6px; flex-wrap: wrap; }
.mep-chip-btn {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600;
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--muted); cursor: pointer; font-family: inherit; transition: all .15s;
}
.mep-chip-btn:hover { border-color: var(--pl); color: var(--text); }
.mep-chip-btn.active {
  background: var(--pl-dim); border-color: var(--pl);
  color: var(--pl-light); box-shadow: 0 0 8px var(--pglow2);
}

/* ── Cover grids ─────────────────────────────────────────────────────────── */
.mep-covers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--space-3, 12px);
}
.mep-covers-grid--wide {
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
}
.mep-cover-option { cursor: pointer; display: flex; flex-direction: column; gap: 5px; }
.mep-cover-option-img {
  position: relative; aspect-ratio: 3/4;
  border-radius: var(--radius-sm, 8px); overflow: hidden;
  border: 2px solid transparent; background: var(--bg3);
  transition: border-color .15s, box-shadow .15s, transform .15s;
}
.mep-cover-option:hover .mep-cover-option-img {
  border-color: rgba(255,255,255,.3);
  box-shadow: 0 4px 20px rgba(0,0,0,.5);
  transform: translateY(-2px);
}
.mep-cover-option.selected .mep-cover-option-img {
  border-color: var(--pl); box-shadow: 0 0 18px var(--pglow2);
}
.mep-cover-option-img img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mep-cover-option-img--hero { aspect-ratio: 32/10; }
.mep-cover-option-img--logo { aspect-ratio: 16/9; background: rgba(0,0,0,.3); }
.mep-cover-option-img--logo img { object-fit: contain; padding: var(--space-2, 8px); }
.mep-cover-option-img--icon { aspect-ratio: 1/1; }
.mep-cover-option-img--wide { aspect-ratio: 16/9; }
.mep-anim-badge-grid {
  position: absolute; top: 5px; left: 5px;
  padding: 2px 6px; border-radius: var(--radius-xs, 4px);
  background: color-mix(in srgb, var(--pl) 85%, transparent); color: #fff;
  font-size: 9px; font-weight: 700; letter-spacing: .6px;
  pointer-events: none;
}
.mep-selected-check {
  position: absolute; top: 6px; right: 6px;
  width: 22px; height: 22px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light);
  display: flex; align-items: center; justify-content: center;
}
.mep-source-badge {
  position: absolute; bottom: 4px; left: 4px;
  width: 20px; height: 20px; border-radius: var(--radius-xs, 4px);
  background: rgba(0,0,0,.65); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.mep-source-badge img { border-radius: 2px; width: 12px !important; height: 12px !important; }
.mep-source-badge--lg { width: 28px; height: 28px; border-radius: 5px; }
.mep-source-badge--lg img { width: 32px !important; height: 32px !important; }

.mep-cover-label {
  font-size: 11px; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mep-cover-author {
  font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.3);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── Search bar ───────────────────────────────────────────────────────────── */
.mep-search-row { display: flex; gap: var(--space-2, 8px); margin-bottom: 14px; }
.mep-search-input {
  flex: 1; background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  color: var(--text); font-size: 13px; font-family: inherit;
  padding: 8px 12px; outline: none; transition: border-color .15s;
}
.mep-search-input:focus { border-color: var(--pl); }
.mep-search-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; white-space: nowrap;
}
.mep-search-btn:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.mep-search-btn:disabled { opacity: .55; cursor: not-allowed; }

/* ── Loading / empty ─────────────────────────────────────────────────────── */
.mep-loading {
  display: flex; align-items: center; gap: 10px;
  color: var(--muted); font-size: 13px; padding: 20px 0;
}
.mep-empty-state {
  padding: 40px 0; text-align: center; color: var(--muted); font-size: var(--fs-md, 14px);
}
.mep-empty-state-sm {
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.3); padding: 8px 0 4px;
}
.mep-spinner {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.1); border-top-color: var(--pl);
  animation: mep-spin .7s linear infinite; flex-shrink: 0;
}
.mep-spinner--sm { width: 14px; height: 14px; }
@keyframes mep-spin { to { transform: rotate(360deg); } }

/* ── Description tab ─────────────────────────────────────────────────────── */
.mep-desc-list { display: flex; flex-direction: column; gap: 14px; padding-top: 18px; }
.mep-desc-source { border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.mep-desc-source-header {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 14px; background: rgba(255,255,255,.04);
  border-bottom: 1px solid var(--glass-border);
}
.mep-desc-source-name { font-size: 13px; font-weight: 700; color: var(--text); }
.mep-desc-apply-btn {
  padding: 5px 14px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: var(--fs-sm, 12px); font-weight: 600; font-family: inherit;
  cursor: pointer; white-space: nowrap; transition: all .15s;
  display: inline-flex; align-items: center; justify-content: center; min-width: 80px;
}
.mep-desc-apply-btn:hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.mep-desc-apply-btn:disabled { opacity: .6; cursor: wait; }
.mep-desc-preview {
  padding: 14px; font-size: 13px; color: rgba(255,255,255,.62); line-height: 1.7;
}

/* Wikipedia text badge (no icon) */
.mep-wiki-badge {
  display: inline-block; font-size: 8px; font-weight: 700; letter-spacing: .5px;
  color: var(--pl-light); background: color-mix(in srgb, var(--pl) 15%, transparent);
  padding: 2px 5px; border-radius: 3px; text-transform: uppercase;
}

/* ── Details tab form ────────────────────────────────────────────────────── */
/* ── Detail source cards ─────────────────────────────────────────────────── */
.mep-detail-sources { display: flex; flex-direction: column; gap: 10px; padding-top: 12px; }
.mep-detail-source {
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.mep-detail-grid {
  display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 14px;
}
.mep-detail-chip {
  display: inline-block; font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.7);
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08);
  border-radius: 6px; padding: 4px 10px; line-height: 1.4;
}
.mep-detail-chip b { color: var(--pl-light); font-weight: 600; margin-right: 2px; }

.mep-form { display: flex; flex-direction: column; gap: 14px; padding-top: 18px; }
.mep-form-section-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px;
  padding-bottom: 4px; border-bottom: 1px solid var(--glass-border);
}
.mep-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.mep-field { display: flex; flex-direction: column; gap: 5px; }
.mep-field-label {
  font-size: 11px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .8px;
}
.mep-field-row { display: flex; gap: var(--space-2, 8px); }
.mep-input {
  flex: 1; background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; transition: border-color .15s;
}
.mep-input:focus { border-color: var(--pl); }
.mep-textarea {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; resize: vertical; transition: border-color .15s; line-height: 1.6;
}
.mep-textarea:focus { border-color: var(--pl); }
.mep-apply-btn {
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.08); border: 1px solid var(--glass-border);
  color: var(--text); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; white-space: nowrap; transition: all .15s;
}
.mep-apply-btn:not(:disabled):hover { background: rgba(255,255,255,.14); }
.mep-apply-btn:disabled { opacity: .4; cursor: not-allowed; }

/* Description tab - provider icon */
.mep-desc-source-icon {
  display: flex; align-items: center;
  flex-shrink: 0;
}
.mep-desc-source-icon img { image-rendering: pixelated; border-radius: 3px; }

/* Details tab - OS checkboxes */
.mep-os-checks { display: flex; gap: 18px; flex-wrap: wrap; }
.mep-os-check-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--text); cursor: pointer;
}
.mep-os-check-label input[type="checkbox"] {
  width: 15px; height: 15px; cursor: pointer;
  accent-color: var(--pl);
}

/* Details tab - field hint */
.mep-field-hint {
  font-size: var(--fs-xs, 10px); font-weight: 400; color: var(--muted);
  text-transform: none; letter-spacing: 0;
}

/* File upload button (label wraps hidden input) */
.mep-upload-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--text); cursor: pointer; flex-shrink: 0;
  font-size: 12px; font-weight: 600;
  transition: all .15s; width: 100%;
}
.mep-upload-btn:hover { background: rgba(255,255,255,.12); color: var(--text); border-color: rgba(255,255,255,.25); }
.mep-file-input { display: none; }

/* ── Screenshots tab ─────────────────────────────────────────────────────── */
.mep-cover-option--removable { position: relative; }
.mep-ss-remove {
  position: absolute; top: 4px; right: 4px;
  width: 22px; height: 22px; border-radius: 50%;
  background: rgba(239,68,68,.85); border: 1px solid rgba(239,68,68,.5);
  color: #fff; font-size: 11px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .15s;
  z-index: 2;
}
.mep-cover-option--removable:hover .mep-ss-remove { opacity: 1; }

/* ── Screenshot list (reorderable) ──────────────────────────────────────── */
.mep-ss-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.mep-ss-item {
  display: flex; align-items: center; gap: 10px;
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); padding: 6px 8px; transition: background .15s;
}
.mep-ss-item:hover { background: rgba(255,255,255,.07); }
.mep-ss-item-thumb {
  width: 120px; height: 68px; object-fit: cover;
  border-radius: 5px; flex-shrink: 0;
}
.mep-ss-order-col {
  display: flex; flex-direction: column; align-items: center; gap: 2px; flex-shrink: 0;
}
.mep-ss-ord-btn {
  width: 22px; height: 20px; background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 4px);
  color: var(--muted); cursor: pointer; font-size: 9px;
  display: flex; align-items: center; justify-content: center; padding: 0;
  transition: background .12s;
}
.mep-ss-ord-btn:hover:not(:disabled) { background: rgba(255,255,255,.14); color: var(--text); }
.mep-ss-ord-btn:disabled { opacity: .3; cursor: default; }
.mep-ss-num { font-size: var(--fs-xs, 10px); color: var(--muted); font-weight: 600; min-width: 16px; text-align: center; }
.mep-ss-remove--list {
  margin-left: auto; flex-shrink: 0;
  width: 26px; height: 26px; display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: 6px; color: var(--muted); cursor: pointer; font-size: var(--fs-sm, 12px);
  transition: background .12s, color .12s;
}
.mep-ss-remove--list:hover { background: rgba(239,68,68,.15); color: #f87171; border-color: rgba(239,68,68,.3); }

/* ── Video results list ───────────────────────────────────────────────────── */
.mep-vid-results { display: flex; flex-direction: column; gap: var(--space-2, 8px); margin-top: 8px; }
.mep-vid-option {
  display: flex; align-items: center; gap: var(--space-3, 12px);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); padding: var(--space-2, 8px); cursor: pointer; transition: background .15s;
}
.mep-vid-option:hover { background: rgba(255,255,255,.08); }
.mep-vid-option.selected { border-color: var(--pl); background: color-mix(in srgb, var(--pl) 8%, transparent); }
.mep-vid-opt-thumb { width: 140px; height: 79px; object-fit: cover; border-radius: 5px; flex-shrink: 0; }
.mep-vid-opt-info { flex: 1; min-width: 0; }
.mep-vid-opt-label { font-size: 13px; font-weight: 600; color: var(--text); }
.mep-vid-opt-author { font-size: 11px; color: var(--muted); margin-top: 2px; }
.mep-vid-selected-check {
  width: 22px; height: 22px; border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}

/* ── Video tab ────────────────────────────────────────────────────────────── */
.mep-video-preview {
  display: flex; align-items: flex-start; gap: var(--space-4, 16px);
  padding: 14px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  margin-bottom: 14px;
}
.mep-video-thumb {
  width: 180px; aspect-ratio: 16/9; object-fit: cover;
  border-radius: 6px; flex-shrink: 0;
  border: 1px solid var(--glass-border);
}
.mep-video-info { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
.mep-video-yt-id { font-size: var(--fs-sm, 12px); color: var(--muted); font-family: monospace; word-break: break-all; }
.mep-video-link { font-size: var(--fs-sm, 12px); color: var(--pl-light); text-decoration: none; }
.mep-video-link:hover { text-decoration: underline; }

/* ── Icon preview in sidebar ─────────────────────────────────────────────── */
.mep-cover-selected-wrap--icon {
  width: 80px; height: 80px; aspect-ratio: 1/1;
  border-radius: 10px; background: rgba(0,0,0,.35);
  border: 1px solid var(--glass-border);
}

/* ── Footer ───────────────────────────────────────────────────────────────── */
.mep-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 22px; border-top: 1px solid var(--glass-border);
  flex-shrink: 0; background: rgba(255,255,255,.02);
}
.mep-save-status { font-size: 13px; }
.mep-footer-right { display: flex; align-items: center; gap: 10px; }
.mep-ok  { color: #4ade80; }
.mep-err { color: #f87171; }
.mep-footer-actions { display: flex; gap: 10px; }
.mep-btn-delete {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, #ef4444 16%, transparent); border: 1px solid color-mix(in srgb, #ef4444 40%, transparent);
  color: #fca5a5; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.mep-btn-delete:hover:not(:disabled) { background: color-mix(in srgb, #ef4444 28%, transparent); border-color: #ef4444; color: #fff; }
.mep-btn-delete:disabled { opacity: .5; cursor: not-allowed; }
.mep-btn-cancel {
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.mep-btn-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.mep-btn-save {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 9px 22px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 2px 12px var(--pglow2);
}
.mep-btn-save:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.mep-btn-save:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }

/* ── SRL Requirements tab ────────────────────────────────────────────────────── */
.srl-search-row {
  display: flex; gap: 6px; margin-bottom: 8px;
}
.srl-search-row .mep-input { flex: 1; }

.srl-error {
  font-size: 11px; color: #f87171;
  margin-bottom: 6px;
}

.srl-no-data {
  font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.35); font-style: italic;
}

.srl-matches {
  display: flex; flex-direction: column; gap: 3px; margin-bottom: 10px;
}

.srl-match-row {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  padding: 5px 8px; border-radius: 6px;
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.03);
  cursor: pointer; transition: background .12s;
}
.srl-match-row:hover { background: rgba(255,255,255,.07); }
.srl-match-row--active {
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  background: color-mix(in srgb, var(--pl) 8%, transparent);
}

.srl-match-score {
  font-size: var(--fs-xs, 10px); font-weight: 700;
  color: var(--pl-light, var(--pl));
  min-width: 32px; text-align: center;
  background: color-mix(in srgb, var(--pl) 15%, transparent);
  border-radius: var(--radius-xs, 4px); padding: 1px 4px;
}

.srl-match-title {
  flex: 1; font-size: var(--fs-sm, 12px); color: rgba(255,255,255,.75);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.srl-fetch-btn { flex-shrink: 0; padding: 3px 10px; font-size: 11px; }

.srl-req-table {
  display: flex; flex-direction: column; gap: var(--space-1, 4px); margin: 6px 0;
}

.srl-req-row {
  display: flex; gap: var(--space-2, 8px); align-items: baseline;
}

.srl-req-key {
  font-size: 11px; font-weight: 700; color: var(--muted);
  min-width: 72px; flex-shrink: 0; text-transform: uppercase; letter-spacing: .04em;
}

.srl-req-val {
  font-size: 11px; color: rgba(255,255,255,.7); line-height: 1.4;
}

.srl-preview {
  background: color-mix(in srgb, var(--pl) 6%, rgba(0,0,0,.3));
  border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent);
  border-radius: var(--radius-sm, 8px); padding: 10px 12px; margin-top: 8px;
}

.srl-preview-head {
  font-size: var(--fs-xs, 10px); font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--pl-light, var(--pl));
  margin-bottom: 4px;
}

.srl-apply-row {
  display: flex; gap: var(--space-2, 8px); margin-top: 10px;
}

.srl-clear-btn {
  margin-top: 8px; font-size: 11px;
  color: rgba(255,255,255,.3);
  background: none; border: none; cursor: pointer; padding: 0;
  text-decoration: underline; text-underline-offset: 2px;
  transition: color .15s;
}
.srl-clear-btn:hover { color: #f87171; }

.srl-pending-notice {
  font-size: 11px; color: #4ade80;
  padding: 6px 8px; background: rgba(74,222,128,.08);
  border: 1px solid rgba(74,222,128,.2); border-radius: 6px;
  margin-top: 8px;
}

/* Manual entry grid */
.srl-manual-grid {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 4px 8px;
  align-items: center;
  margin-bottom: 4px;
}
.mep-input--sm {
  padding: 4px 8px; font-size: 11px;
}

/* ── Mobile ────────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .mep-panel { width: 100vw; height: 100vh; border-radius: 0; max-width: none; }
  .mep-left { display: none; }
  .mep-tabs { flex-wrap: wrap; gap: 2px; }
  .mep-tab { font-size: .68rem; padding: 6px 8px; }
  .mep-header { padding: 10px 14px; }
  .mep-tab-content { padding: 10px; }
  .mep-covers-grid { grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 6px; }
  .mep-form-row { grid-template-columns: 1fr; }
}
</style>
