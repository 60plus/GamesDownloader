<!--
  MyUploadsPanel - what this account has added to the library, what it costs
  against the upload quota, and the two things worth doing to it from here.

  For the uploader only. An admin has no quota worth watching and every game on
  the server is theirs, so this would be a second library listing rather than a
  summary. Their view of who is using what lives in Settings > Users, beside the
  figures they set.

  Laid out like the saves panel above it: one strip per shelf, folded away, the
  count and the weight on the right. That panel groups by platform because that
  is where a save lives; this one groups by library, because that is where a
  game lives, and somebody with games in Games, PC Ports and a custom shelf
  wants them apart rather than in one column sorted only by size.

  Covers rather than rows. A cover is how anybody recognises a game, and the
  reason to open this is to find the one to remove.
-->
<template>
  <div v-if="show" class="mup glass">
    <div class="mup-h">
      <i class="mdi mdi-cloud-upload-outline mup-h-ico"></i>
      <span>{{ t("uploads.my_uploads", "My uploads") }}</span>
      <span class="mup-count">{{ games.length }}</span>
    </div>

    <div v-if="loading" class="mup-loading"><span class="mup-spin"></span></div>

    <div v-else-if="loadError" class="mup-fail">
      {{ t("uploads.load_failed", "Could not load your uploads") }}
    </div>

    <template v-else>
      <!-- Only when a limit applies. With none set there is nothing to be a
           proportion of, and a full bar would say the opposite of the truth. -->
      <div v-if="limitBytes > 0" class="mup-quota">
        <div class="mup-quota-bar">
          <div
            class="mup-quota-fill"
            :class="{ warn: pct >= 90 }"
            :style="{ width: Math.min(pct, 100) + '%' }"
          ></div>
        </div>
        <div class="mup-quota-text">
          {{ fmtBytes(usedBytes) }} {{ t("profile.used_of", "of") }} {{ fmtBytes(limitBytes) }}
        </div>
      </div>
      <div v-else class="mup-quota-text mup-nolimit">
        {{ fmtBytes(usedBytes) }} {{ t("uploads.no_limit", "used, no limit set") }}
      </div>

      <div v-if="!games.length" class="mup-empty">
        {{ t("uploads.none", "You have not added any games yet.") }}
      </div>

      <div v-else class="mup-shelves">
        <div v-for="s in shelves" :key="s.slug" class="mup-shelf" :class="{ 'mup-shelf--open': open.has(s.slug) }">
          <div
            class="mup-shelf-row"
            role="button"
            tabindex="0"
            :aria-expanded="open.has(s.slug)"
            @click="toggle(s.slug)"
            @keydown.enter.prevent="toggle(s.slug)"
            @keydown.space.prevent="toggle(s.slug)"
          >
            <i class="mdi mup-chev" :class="open.has(s.slug) ? 'mdi-chevron-down' : 'mdi-chevron-right'"></i>
            <img v-if="s.icon" :src="s.icon" class="mup-shelf-icon" alt="" />
            <span class="mup-shelf-name">{{ s.name }}</span>
            <span class="mup-shelf-meta">{{ s.games.length }} · {{ fmtBytes(s.bytes) }}</span>
          </div>

          <div v-if="open.has(s.slug)" class="mup-grid">
            <div v-for="g in s.games" :key="g.id" class="mup-tile">
              <router-link
                class="mup-art"
                :to="g.kind === 'rom'
                  ? { name: 'emulation-detail', params: { platform: g.library.slug, id: g.id } }
                  : { name: 'games-detail', params: { id: g.id } }"
              >
                <img v-if="g.cover_path" :src="g.cover_path" class="mup-cover" :alt="g.title" />
                <span v-else class="mup-cover mup-cover--none">
                  <i class="mdi mdi-image-off-outline"></i>
                </span>
              </router-link>
              <!-- Both kinds get both buttons. A ROM has an owner and counts
                   against the same figure, so the account that fetched one
                   clears it up here the same way it clears up a game it
                   uploaded. Only the endpoints behind the buttons differ. -->
              <div class="mup-tools">
                <!-- An admin can shut an entry, including one of these. There is
                     nothing to open then, and opening the editor would fire
                     searches at the metadata providers for nothing. -->
                <button
                  class="mup-act"
                  :class="{ 'mup-act--locked': g.metadata_locked }"
                  :disabled="g.metadata_locked"
                  :title="g.metadata_locked
                    ? t('meta.locked_by_admin', 'Locked by an administrator')
                    : t('detail.edit_metadata', 'Edit metadata')"
                  @click="edit(g)"
                >
                  <i class="mdi" :class="g.metadata_locked ? 'mdi-lock' : 'mdi-pencil-outline'"></i>
                </button>
                <button
                  class="mup-act mup-act--danger"
                  :class="{ 'mup-act--locked': g.can_delete === false }"
                  :title="g.can_delete === false
                    ? t('uploads.shared_game', 'This game holds files from another account, so only an administrator can remove it.')
                    : t('common.delete', 'Delete')"
                  :disabled="busy === g.id || g.can_delete === false"
                  @click="remove(g)"
                >
                  <i class="mdi mdi-trash-can-outline"></i>
                </button>
              </div>
              <div class="mup-name" :title="g.title">{{ g.title }}</div>
              <!-- A game whose files have all gone still belongs here: that is
                   the wreckage this panel exists to clear away. -->
              <div class="mup-size" :class="{ 'mup-size--none': !g.file_count }">
                {{ g.file_count ? fmtBytes(g.size_bytes) : t("uploads.no_files", "no files") }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import client from "@/services/api/client";
import { useI18n } from "@/i18n";
import { useAuthStore } from "@/stores/auth";
import { useDialog } from "@/composables/useDialog";
import { openMetadataEditor } from "@/lib/pluginUi";

interface Shelf { slug: string; name: string; icon: string | null; color: string | null; order: number }
interface OwnedGame {
  // A ROM counts against the same figure and sits in the same list, but is a
  // different row in a different table: no files, no editor here, and its shelf
  // is the platform rather than a library.
  kind: "game" | "rom";
  id: number; title: string; slug: string;
  cover_path: string | null; source: string;
  size_bytes: number; file_count: number; metadata_locked: boolean;
  // A game can appear here because ONE file in it is this account's, while the
  // game itself belongs to somebody else - a catalogue entry fetched twice
  // reuses the first account's game on purpose. Removing it would take their
  // files too, so the delete rule reads the game's owner and the server says
  // here which kind of row this is.
  can_delete?: boolean;
  library: Shelf;
}
interface ShelfGroup extends Shelf { games: OwnedGame[]; bytes: number }

const { t } = useI18n();
const auth = useAuthStore();
const { gdConfirm } = useDialog();

const loading = ref(true);
const loadError = ref(false);
const usedBytes = ref(0);
const limitBytes = ref(0);
const games = ref<OwnedGame[]>([]);
const busy = ref<number | null>(null);
const open = ref<Set<string>>(new Set());

// The uploader alone. An admin's quota is not the thing they manage, and every
// game on the server is theirs, so this would be a second library listing.
const isUploader = computed(() => auth.user?.role === "uploader");
const show = computed(() => isUploader.value);

const pct = computed(() =>
  limitBytes.value > 0 ? (usedBytes.value / limitBytes.value) * 100 : 0);

const shelves = computed<ShelfGroup[]>(() => {
  const by = new Map<string, ShelfGroup>();
  for (const g of games.value) {
    const lib = g.library || { slug: "custom", name: "Custom", icon: null, color: null, order: 99 };
    let grp = by.get(lib.slug);
    if (!grp) {
      grp = { ...lib, games: [], bytes: 0 };
      by.set(lib.slug, grp);
    }
    grp.games.push(g);
    grp.bytes += g.size_bytes;
  }
  // Heaviest shelf first, which is the one worth opening when room runs out.
  return [...by.values()].sort((a, b) => b.bytes - a.bytes);
});

function toggle(slug: string) {
  const next = new Set(open.value);
  if (next.has(slug)) next.delete(slug); else next.add(slug);
  open.value = next;
}

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

async function load() {
  try {
    const { data } = await client.get("/library/my-uploads");
    usedBytes.value = data.used_bytes ?? 0;
    limitBytes.value = data.limit_bytes ?? 0;
    games.value = data.games ?? [];
    loadError.value = false;
    // The heaviest shelf starts open, the rest folded. Opening everything would
    // be the wall of covers this layout exists to avoid; opening nothing would
    // make somebody click before seeing anything at all.
    if (!open.value.size && shelves.value.length) {
      open.value = new Set([shelves.value[0].slug]);
    }
  } catch {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

// The editor wants the whole game, and this list carries the handful of fields
// the tiles need, so it is fetched on the way in rather than sent to every
// dashboard that will never open it.
// A ROM and a library game are edited and removed through different endpoints,
// so the row says which it is rather than the panel guessing from its shape.
function apiPrefix(g: OwnedGame): string {
  return g.kind === "rom" ? "/roms" : "/library/games";
}

async function edit(g: OwnedGame) {
  try {
    const { data } = await client.get(`${apiPrefix(g)}/${g.id}`);
    openMetadataEditor({ game: data, apiPrefix: apiPrefix(g), onSaved: () => { load(); } });
  } catch { /* it went while the dashboard was open */ }
}

// What removing this row would actually take, in the words of the row itself.
// A ROM is not one file: a floppy title is several discs that only mean
// anything together, a disc rip carries track files and a playlist, and the
// saves that go with all of them belong to whoever played them rather than to
// whoever is looking. None of that is visible from a tile, so it is asked for
// before the question is put. The ROM detail page has asked this way all along;
// this panel asked one sentence and deleted the lot.
async function removalDetail(g: OwnedGame): Promise<string> {
  if (g.kind !== "rom") return "";
  try {
    const { data } = await client.get(`/roms/${g.id}/removal`);
    const parts: string[] = [];
    const discs = (data.disks ?? []).length;
    if (discs > 1) {
      parts.push(t("uploads.delete_discs", "This title is {n} discs and all of them go.")
        .replace("{n}", String(discs)));
    }
    const extra = (data.files ?? []).length;
    if (extra) {
      parts.push(t("uploads.delete_extra_files", "{n} more files on disk go with them.")
        .replace("{n}", String(extra)));
    }
    if (data.saves) {
      parts.push(t("uploads.delete_saves", "{n} saved games go too, including other people's.")
        .replace("{n}", String(data.saves)));
    }
    return parts.length ? " " + parts.join(" ") : "";
  } catch {
    // The plain question, unchanged. It already says the files go.
    return "";
  }
}

async function remove(g: OwnedGame) {
  const ok = await gdConfirm(
    t("uploads.delete_body", "Delete {name} and its files from disk? This cannot be undone.")
      .replace("{name}", g.title) + await removalDetail(g),
    { danger: true, requireTick: true, title: t("common.delete", "Delete") },
  );
  if (!ok) return;
  busy.value = g.id;
  try {
    // delete_files either way: the confirmation says the files go, and leaving
    // them behind would put a ROM back in the library on the next scan, which
    // is not what somebody clearing space just agreed to.
    await client.delete(`${apiPrefix(g)}/${g.id}`, { params: { delete_files: true } });
    await load();
  } finally {
    busy.value = null;
  }
}

onMounted(() => {
  if (!isUploader.value) { loading.value = false; return; }
  load();
});
</script>

<style scoped>
.mup { padding: 14px 16px; border-radius: var(--radius, 12px); }
.mup-h {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-md, 14px); font-weight: 700; margin-bottom: 12px;
}
.mup-h-ico { opacity: .6; }
.mup-count {
  margin-left: auto; font-size: 12px; font-weight: 600;
  color: var(--muted); font-variant-numeric: tabular-nums;
}

.mup-quota { margin-bottom: 12px; }
.mup-quota-bar {
  height: 6px; border-radius: 3px; overflow: hidden;
  background: color-mix(in srgb, var(--pl, #7c3aed) 14%, transparent);
}
.mup-quota-fill {
  height: 100%; border-radius: 3px; transition: width .2s;
  background: linear-gradient(90deg, var(--pl, #7c3aed), var(--pl-light, #a78bfa));
}
.mup-quota-fill.warn { background: linear-gradient(90deg, #d97706, #f59e0b); }
.mup-quota-text {
  margin-top: 6px; font-size: 12px; color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.mup-nolimit { margin-bottom: 12px; }

.mup-loading, .mup-fail, .mup-empty {
  padding: 10px 0; font-size: 12px; color: var(--muted);
}
.mup-spin {
  display: inline-block; width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--pl, #7c3aed) 30%, transparent);
  border-top-color: var(--pl, #7c3aed); animation: mup-spin .7s linear infinite;
}
@keyframes mup-spin { to { transform: rotate(360deg); } }

/* A ceiling rather than a fixed height: with two shelves and four games this
   never shows, and with two hundred it stops the panel owning the page. */
.mup-shelves { max-height: 420px; overflow-y: auto; scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--pl, #7c3aed) 35%, transparent) transparent; }

.mup-shelf + .mup-shelf { margin-top: 6px; }
.mup-shelf-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; cursor: pointer;
  border: 1px solid var(--glass-border, rgba(255,255,255,.07));
  border-radius: var(--radius-sm, 8px);
  background: var(--glass-bg, rgba(255,255,255,.03));
  transition: border-color .15s;
}
.mup-shelf-row:hover { border-color: color-mix(in srgb, var(--pl, #7c3aed) 45%, transparent); }
.mup-shelf--open .mup-shelf-row {
  border-bottom-left-radius: 0; border-bottom-right-radius: 0;
}
.mup-chev { opacity: .5; font-size: 16px; }
/* Library icons are drawn to no common shape, so the height is capped and the
   tall ones letterbox instead of squashing. */
.mup-shelf-icon { width: 34px; height: auto; max-height: 24px; object-fit: contain; flex: none; }
.mup-shelf-name { font-size: 13px; font-weight: 600; }
.mup-shelf-meta {
  margin-left: auto; font-size: 11px; color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.mup-grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  padding: 12px;
  border: 1px solid var(--glass-border, rgba(255,255,255,.07));
  border-top: none;
  border-bottom-left-radius: var(--radius-sm, 8px);
  border-bottom-right-radius: var(--radius-sm, 8px);
}

.mup-tile { position: relative; min-width: 0; }
.mup-art { display: block; }
.mup-cover {
  width: 100%; aspect-ratio: 2 / 3; border-radius: 6px; object-fit: cover;
  display: block; background: color-mix(in srgb, var(--pl, #7c3aed) 12%, transparent);
  transition: transform .15s, box-shadow .15s;
}
.mup-art:hover .mup-cover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0,0,0,.5);
}
.mup-cover--none {
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 20px;
}

/* Always there rather than on hover: this panel is operated, not browsed, and
   a control that appears only under a pointer is one a touch screen never has. */
.mup-tools {
  position: absolute; top: 4px; right: 4px;
  display: flex; gap: 3px;
}
.mup-act {
  width: 22px; height: 22px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.62); border: none; color: rgba(255,255,255,.75);
  cursor: pointer; font-size: 13px; transition: all .15s;
}
.mup-act:hover { background: rgba(0,0,0,.85); color: #fff; }
.mup-act--danger:hover { background: rgba(220,38,38,.85); }
.mup-act--locked, .mup-act--locked:hover { color: #f59e0b; background: rgba(0,0,0,.62); }
.mup-act:disabled { opacity: .4; cursor: not-allowed; }

.mup-name {
  margin-top: 6px; font-size: 11px; line-height: 1.3;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mup-size {
  font-size: 10px; color: var(--muted); font-variant-numeric: tabular-nums;
}
.mup-size--none { color: #f59e0b; }

/* The Steam Deck plugin badges every image whose source matches a cover. On a
   shelf that is the point; here every tile would wear one and the panel would
   be about compatibility instead of about disk. Hidden view-side, the way the
   themes already hide it where it does not belong, because the plugin offers
   no way to opt out. */
.mup :deep(.gd-sdc-badge) { display: none !important; }
</style>
