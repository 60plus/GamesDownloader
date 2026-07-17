<!--
  HomePlayRail - a home-page row of ROMs you have played, or have a save for.

  Deliberately a twin of GamesHome's "Recently added - Emulation" row (same
  120px cover keeping its own aspect, same platform wordmark, same scroller and
  chevrons), because it sits directly beneath it and anything else would read as
  a graft.

  In "resume" mode the tiles carry their saves: hovering shows a rail of the
  used slots, and hovering a slot swaps the cover for that save's screenshot -
  so you can see where you stopped without the tile hiding the game. Clicking
  the cover resumes the newest save, which is the common case and stays one
  click; clicking a slot resumes that one.
-->
<template>
  <section class="home-recent-section">
    <div class="home-section-head">
      <button class="home-section-title home-section-link" @click="router.push('/emulation')">
        {{ title }}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <div class="home-row-nav">
        <button class="home-nav-btn" @click="scroll('left')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg></button>
        <button class="home-nav-btn" @click="scroll('right')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg></button>
      </div>
    </div>

    <div ref="row" class="home-recent-scroll">
      <div
        v-for="it in items"
        :key="it.rom_id"
        class="emu-recent-item"
        @click="open(it)"
      >
        <div class="emu-recent-img-wrap" :style="{ aspectRatio: it.aspect || '3/4' }">
          <img
            v-if="shotFor(it) || it.cover"
            :src="shotFor(it) || it.cover!"
            :alt="it.name"
            class="home-recent-img"
            loading="lazy"
          />
          <div v-else class="home-recent-fallback emu-recent-fallback">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="opacity:.3">
              <rect x="2" y="6" width="20" height="14" rx="2"/>
              <circle cx="8" cy="13" r="1.5"/><circle cx="16" cy="13" r="1.5"/>
              <path d="M6 10h4M8 8v4M14 11h4"/>
            </svg>
          </div>

          <div class="home-recent-overlay">
            <span class="home-recent-overlay-title">{{ it.name }}</span>
          </div>

          <!-- Resume mode: the ROM's used slots. Same grammar as Game saves -
               the number IS the label. -->
          <div v-if="mode === 'resume' && (it.saves || []).length" class="hpr-slots">
            <button
              v-for="s in it.saves"
              :key="s.save"
              class="hpr-chip"
              :title="slotTitle(s)"
              @click.stop="open(it, s.save)"
              @mouseenter="preview = s.screenshot ? { rom: it.rom_id, url: s.screenshot } : null"
              @mouseleave="preview = null"
            >
              <i v-if="s.kind === 'battery'" class="mdi mdi-sd"></i>
              <template v-else>{{ s.slot ?? "•" }}</template>
            </button>
          </div>
        </div>

        <div class="emu-recent-platform">
          <img
            v-if="it.platform_fs_slug"
            :src="`/platforms/names/${it.platform_fs_slug}.svg`"
            :alt="it.platform || ''"
            class="emu-recent-platform-logo"
            @error="onLogoErr"
          />
          <span class="emu-recent-platform-text" :style="it.platform_fs_slug ? 'display:none' : ''">
            {{ it.platform || '' }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import type { RecentRom, RomSaveRef } from '@/lib/dashboardActions'

const props = withDefaults(defineProps<{
  title: string
  items: RecentRom[]
  /** resume = clicking plays from a save; open = clicking just opens the ROM. */
  mode?: 'resume' | 'open'
}>(), { mode: 'open' })

const router = useRouter()
const { t } = useI18n()
const row = ref<HTMLElement | null>(null)
// Which save's screenshot is standing in for a cover right now.
const preview = ref<{ rom: number; url: string } | null>(null)

function shotFor(it: RecentRom): string | null {
  return preview.value && preview.value.rom === it.rom_id ? preview.value.url : null
}

function slotTitle(s: RomSaveRef): string {
  return s.kind === 'battery'
    ? t('profile.battery_saves', 'Battery save')
    : `${t('profile.slot', 'Slot')} ${s.slot ?? ''}`
}

function open(it: RecentRom, save?: string): void {
  if (!it.platform_slug) return
  const query: Record<string, string> = {}
  if (props.mode === 'resume') {
    query.resume = '1'
    if (save) query.save = save
  }
  router.push({ path: `/emulation/${it.platform_slug}/${it.rom_id}`, query })
}

function scroll(dir: 'left' | 'right'): void {
  const el = row.value
  if (!el) return
  el.scrollBy({ left: dir === 'left' ? -el.clientWidth * 0.8 : el.clientWidth * 0.8, behavior: 'smooth' })
}

// Wordmark missing for this platform: fall back to its name.
function onLogoErr(e: Event): void {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
  ;(img.nextElementSibling as HTMLElement | null)?.removeAttribute('style')
}
</script>

<style scoped>
/* Mirrors GamesHome's own rows - this sits right under them. */
.home-recent-section { display: flex; flex-direction: column; }
.home-section-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 18px; }
.home-section-title { font-size: 19px; font-weight: 700; color: var(--text); }
.home-section-link { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; background: none; border: none; font-family: inherit; }
.home-row-nav { display: flex; gap: 6px; }
.home-nav-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 7px;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1);
  color: var(--text); cursor: pointer; transition: background var(--transition);
}
.home-nav-btn:hover { background: rgba(255,255,255,.14); }
.home-recent-scroll {
  display: flex; gap: var(--space-3, 12px); overflow-x: auto; padding-bottom: 8px;
  scroll-behavior: smooth; scrollbar-width: none;
}
.home-recent-scroll::-webkit-scrollbar { display: none; }

.emu-recent-item { flex: 0 0 auto; cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.emu-recent-img-wrap {
  width: 120px;
  /* aspect-ratio is inline per ROM: SNES boxes are 4/3, a fixed frame crops them */
  border-radius: var(--radius-sm, 8px);
  overflow: hidden;
  position: relative;
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: 0 4px 14px rgba(0,0,0,.45);
  transition: box-shadow .2s, transform .2s;
}
.emu-recent-item:hover .emu-recent-img-wrap { box-shadow: 0 8px 28px rgba(0,0,0,.6); transform: translateY(-2px); }
.home-recent-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.home-recent-fallback { width: 100%; height: 100%; background: rgba(255,255,255,.04); }
.emu-recent-fallback { display: flex; align-items: center; justify-content: center; }
.home-recent-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,.85) 0%, transparent 50%);
  display: flex; align-items: flex-end; padding: var(--space-2, 8px);
  opacity: 0; transition: opacity .2s;
}
.emu-recent-item:hover .home-recent-overlay { opacity: 1; }
.home-recent-overlay-title {
  font-size: var(--fs-xs, 10px); font-weight: 600; color: #fff; line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}

/* Slot rail: sits over the art's foot, above the title gradient. */
.hpr-slots {
  position: absolute; left: 0; right: 0; bottom: 0;
  display: flex; gap: 3px; padding: 5px; justify-content: center; flex-wrap: wrap;
  background: linear-gradient(to top, rgba(6,8,12,.92), transparent);
  opacity: 0; transition: opacity .15s;
}
.emu-recent-item:hover .hpr-slots { opacity: 1; }
/* No hover on touch - the slots are the point, so keep them visible there. */
@media (hover: none) { .hpr-slots { opacity: 1; } }
.hpr-chip {
  width: 18px; height: 18px; flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  border: 0; border-radius: 5px; cursor: pointer;
  font-size: 9.5px; font-weight: 700; line-height: 1;
  background: color-mix(in srgb, var(--accent, #38d3db) 34%, rgba(6,8,12,.85));
  color: #fff; transition: transform .12s, background .12s;
}
.hpr-chip:hover { transform: translateY(-1px); background: var(--accent, #38d3db); }
.hpr-chip i { font-size: 11px; }

.emu-recent-platform { display: flex; align-items: center; justify-content: center; height: 18px; }
.emu-recent-platform-logo { max-width: 92px; max-height: 16px; object-fit: contain; opacity: .75; }
.emu-recent-platform-text { font-size: 10px; color: var(--muted); }
</style>
