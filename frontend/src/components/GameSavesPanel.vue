<!--
  GameSavesPanel - the user's ROM savestates + battery saves + storage quota.
  Moved out of the profile page onto the Dashboard. Self-contained: fetches
  /savestates/my on mount and deletes through window.__GD__.dashboard's helpers,
  so it drops into any theme. Theme-agnostic styling via CSS variables.

  Each game rests as ONE folded line carrying a rail of nine numbered slot chips
  plus a battery marker - tinted = used, dashed = free - so free slots stay
  readable across every game at once without opening anything. Clicking a line
  unfolds that game's full memory-card grid (screenshots, empty tiles, battery)
  underneath; everything starts folded and only one game opens at a time, which
  is what keeps the panel small no matter how many games have saves.
-->
<template>
  <div class="gsp glass">
    <div class="gsp-h">
      <i class="mdi mdi-content-save-outline gsp-h-ico"></i>
      <span>{{ t("profile.game_saves", "Game saves") }}</span>
      <div class="gsp-sorts">
        <button
          v-for="s in SORTS"
          v-show="games.length > 1"
          :key="s"
          class="gsp-chip"
          :class="{ 'gsp-chip--on': sort === s }"
          @click="sort = s"
        >{{ s === "recent" ? t("profile.sort_recent", "Recent") : t("profile.sort_largest", "Largest") }}</button>
        <!-- Import lives up here, not on a tile: restoring a backup happens when
             the games have no saves yet, so they have no tiles to click. -->
        <button class="gsp-chip gsp-chip--act" :disabled="!!busy" @click="pickImport()">
          <span v-if="busy === 'import'" class="gsp-spin gsp-spin--sm"></span>
          <i v-else class="mdi mdi-tray-arrow-up"></i>
          {{ t("profile.import_saves", "Import") }}
        </button>
        <button v-if="games.length" class="gsp-chip gsp-chip--act" :disabled="!!busy" @click="exportAll()">
          <span v-if="busy === 'exportall'" class="gsp-spin gsp-spin--sm"></span>
          <i v-else class="mdi mdi-tray-arrow-down"></i>
          {{ t("profile.export_all", "Export all") }}
        </button>
      </div>
    </div>

    <!-- One picker drives every upload; `pending` says where the bytes go. -->
    <input ref="fileInput" type="file" multiple class="gsp-file" :accept="acceptFor" @change="onFiles" />

    <div v-if="notice" class="gsp-notice" :class="{ 'gsp-notice--bad': noticeBad }">
      <i class="mdi" :class="noticeBad ? 'mdi-alert-outline' : 'mdi-check-circle-outline'"></i>
      <span>{{ notice }}</span>
      <button class="gsp-notice-x" @click="notice = ''"><i class="mdi mdi-close"></i></button>
    </div>

    <div v-if="loading" class="gsp-loading"><span class="gsp-spin"></span></div>

    <div v-else-if="loadError" class="gsp-loadfail">
      {{ t('profile.saves_load_failed', 'Could not load your saves') }}
    </div>

    <template v-else-if="data">
      <!-- Quota -->
      <div class="gsp-quota">
        <div class="gsp-quota-bar">
          <div class="gsp-quota-fill" :class="{ warn: quotaPct >= 90 }" :style="{ width: Math.min(quotaPct, 100) + '%' }"></div>
        </div>
        <div class="gsp-quota-text">{{ fmtBytes(data.used_bytes) }} {{ t("profile.used_of", "of") }} {{ fmtBytes(data.limit_bytes) }}</div>
      </div>

      <div v-if="!games.length" class="gsp-empty">
        {{ t("profile.no_save_states", "No save states yet. They are created while playing in the browser emulator.") }}
      </div>

      <!-- One line per game; unfolds into the full card -->
      <div v-for="g in games" :key="g.romId" class="gsp-game" :class="{ 'gsp-game--open': open === g.romId }">
        <div
          class="gsp-row"
          role="button"
          tabindex="0"
          :aria-expanded="open === g.romId"
          @click="toggle(g.romId)"
          @keydown.enter.prevent="toggle(g.romId)"
          @keydown.space.prevent="toggle(g.romId)"
        >
          <i class="mdi gsp-chev" :class="open === g.romId ? 'mdi-chevron-down' : 'mdi-chevron-right'"></i>

          <div class="gsp-game-cover" :style="{ aspectRatio: g.aspect }">
            <img v-if="g.cover" :src="g.cover" class="gsp-game-cover-img" :alt="g.name" />
            <i v-else class="mdi mdi-gamepad-variant-outline gsp-game-cover-ph"></i>
          </div>

          <div class="gsp-game-info">
            <component
              :is="g.platformSlug ? 'router-link' : 'span'"
              :to="g.platformSlug ? `/emulation/${g.platformSlug}/${g.romId}` : undefined"
              class="gsp-game-name"
              @click.stop
            >{{ g.name }}</component>
            <div class="gsp-game-sub">
              <span v-if="g.platformName">{{ g.platformName }}</span>
              <span class="gsp-sep">·</span>
              <span>{{ fmtBytes(g.bytes) }}</span>
            </div>
          </div>

          <button
            class="gsp-btn gsp-btn--ghost"
            :disabled="!!busy"
            :title="t('profile.export_game', 'Export saves for this game')"
            @click.stop="exportGame(g)"
          >
            <span v-if="busy === 'g' + g.romId" class="gsp-spin gsp-spin--sm"></span>
            <i v-else class="mdi mdi-tray-arrow-down"></i>
          </button>

          <!-- The rail: nine numbered slots + battery. Dashed = free. -->
          <div class="gsp-rail">
            <span
              v-for="slot in maxSlot"
              :key="slot"
              class="gsp-pip"
              :class="{ 'gsp-pip--on': !!g.slots[slot] }"
              :title="g.slots[slot] ? `${t('profile.slot', 'Slot')} ${slot}` : `${t('profile.slot', 'Slot')} ${slot} - ${t('profile.slot_empty', 'Empty')}`"
            >{{ slot }}</span>
            <span
              class="gsp-pip gsp-pip--bat"
              :class="{ 'gsp-pip--on': !!g.battery.length }"
              :title="g.battery.length
                ? t('profile.battery_saves', 'Battery save')
                : `${t('profile.battery_saves', 'Battery save')} - ${t('profile.slot_empty', 'Empty')}`"
            ><i class="mdi mdi-sd"></i></span>
          </div>
        </div>

        <div v-if="open === g.romId" class="gsp-grid">
          <!-- Slots 1-N: filled ones carry the screenshot, empty ones stay visible -->
          <div v-for="slot in maxSlot" :key="'s' + slot" class="gsp-tile" :class="{ 'gsp-tile--empty': !g.slots[slot] }">
            <template v-if="g.slots[slot]">
              <div class="gsp-shot">
                <img
                  v-if="g.slots[slot]!.screenshot_url"
                  :src="g.slots[slot]!.screenshot_url!"
                  class="gsp-shot-img gsp-shot-img--zoom"
                  :alt="'Slot ' + slot"
                  :title="t('profile.zoom_shot', 'Click to enlarge')"
                  @click="zoom = { url: g.slots[slot]!.screenshot_url!, caption: `${g.name} - ${t('profile.slot', 'Slot')} ${slot}` }"
                />
                <i v-else class="mdi mdi-image-outline gsp-shot-ph"></i>
                <span class="gsp-badge">{{ t("profile.slot", "Slot") }} {{ slot }}</span>
                <div class="gsp-acts">
                  <button class="gsp-btn gsp-btn--play" @click="play(g, 'state:' + g.slots[slot]!.id)" :title="t('profile.play_from_save', 'Play from this save')">
                    <i class="mdi mdi-play"></i>
                  </button>
                  <button class="gsp-btn" :disabled="!!busy" @click="exportState(g.slots[slot]!.id)" :title="t('common.download', 'Download')">
                    <span v-if="busy === 'st' + g.slots[slot]!.id" class="gsp-spin gsp-spin--sm"></span>
                    <i v-else class="mdi mdi-download"></i>
                  </button>
                  <button class="gsp-btn gsp-btn--del" :disabled="busyId === 'st' + g.slots[slot]!.id" @click="del('state', g.slots[slot]!.id)" :title="t('profile.delete_save', 'Delete')">
                    <span v-if="busyId === 'st' + g.slots[slot]!.id" class="gsp-spin gsp-spin--sm"></span>
                    <i v-else class="mdi mdi-trash-can-outline"></i>
                  </button>
                </div>
              </div>
              <div class="gsp-tile-meta">
                <span>{{ fmtDate(savedAt(g.slots[slot]!)) }}</span>
                <span class="gsp-sep">·</span>
                <span>{{ fmtBytes(g.slots[slot]!.file_size_bytes) }}</span>
              </div>
            </template>
            <template v-else>
              <!-- The "+" now does what it always looked like it would: upload
                   a save file straight into this slot. -->
              <button
                class="gsp-shot gsp-shot--empty gsp-shot--drop"
                :disabled="!!busy"
                :title="t('profile.upload_to_slot', 'Upload a save into this slot')"
                @click="pickInto(g, slot)"
              >
                <span v-if="busy === 'u' + g.romId + '-' + slot" class="gsp-spin"></span>
                <i v-else class="mdi mdi-plus gsp-shot-ph"></i>
                <span class="gsp-badge gsp-badge--muted">{{ t("profile.slot", "Slot") }} {{ slot }}</span>
              </button>
              <div class="gsp-tile-meta gsp-tile-meta--muted">{{ t("profile.slot_empty", "Empty") }}</div>
            </template>
          </div>

          <!-- Legacy savestates: saved before slots, so they belong to no slot -->
          <div v-for="ls in g.legacy" :key="'l' + ls.id" class="gsp-tile">
            <div class="gsp-shot">
              <img
                v-if="ls.screenshot_url"
                :src="ls.screenshot_url"
                class="gsp-shot-img gsp-shot-img--zoom"
                :alt="ls.file_name"
                :title="t('profile.zoom_shot', 'Click to enlarge')"
                @click="zoom = { url: ls.screenshot_url!, caption: `${g.name} - ${t('profile.slot_legacy', 'Older')}` }"
              />
              <i v-else class="mdi mdi-image-outline gsp-shot-ph"></i>
              <span class="gsp-badge gsp-badge--legacy">{{ t("profile.slot_legacy", "Older") }}</span>
              <div class="gsp-acts">
                <button class="gsp-btn gsp-btn--play" @click="play(g, 'state:' + ls.id)" :title="t('profile.play_from_save', 'Play from this save')">
                  <i class="mdi mdi-play"></i>
                </button>
                <button class="gsp-btn" :disabled="!!busy" @click="exportState(ls.id)" :title="t('common.download', 'Download')">
                  <span v-if="busy === 'st' + ls.id" class="gsp-spin gsp-spin--sm"></span>
                  <i v-else class="mdi mdi-download"></i>
                </button>
                <button class="gsp-btn gsp-btn--del" :disabled="busyId === 'st' + ls.id" @click="del('state', ls.id)" :title="t('profile.delete_save', 'Delete')">
                  <span v-if="busyId === 'st' + ls.id" class="gsp-spin gsp-spin--sm"></span>
                  <i v-else class="mdi mdi-trash-can-outline"></i>
                </button>
              </div>
            </div>
            <div class="gsp-tile-meta">
              <span>{{ fmtDate(savedAt(ls)) }}</span>
              <span class="gsp-sep">·</span>
              <span>{{ fmtBytes(ls.file_size_bytes) }}</span>
            </div>
          </div>

          <!-- Battery save: one per game, holding the whole cartridge SRAM -->
          <div v-for="bs in g.battery" :key="'b' + bs.id" class="gsp-tile">
            <div class="gsp-shot gsp-shot--bat">
              <!-- The cartridge this SRAM came out of. Contained, never cropped:
                   support art runs from 0.91 (NES, squarish) to 2.87 (a slim
                   SNES front), so any fixed crop would slice most of them. -->
              <img v-if="g.support" :src="g.support" class="gsp-cart" :alt="g.name" />
              <i v-else class="mdi mdi-sd gsp-shot-ph gsp-shot-ph--bat"></i>
              <span class="gsp-badge gsp-badge--bat">{{ t("profile.battery_saves", "Battery save") }}</span>
              <div class="gsp-acts">
                <button class="gsp-btn gsp-btn--play" @click="play(g, 'battery')" :title="t('profile.play_from_save', 'Play from this save')">
                  <i class="mdi mdi-play"></i>
                </button>
                <button class="gsp-btn" :disabled="!!busy" @click="exportBattery(bs.id)" :title="t('common.download', 'Download')">
                  <span v-if="busy === 'sv' + bs.id" class="gsp-spin gsp-spin--sm"></span>
                  <i v-else class="mdi mdi-download"></i>
                </button>
                <button class="gsp-btn gsp-btn--del" :disabled="busyId === 'sv' + bs.id" @click="del('save', bs.id)" :title="t('profile.delete_battery', 'Delete')">
                  <span v-if="busyId === 'sv' + bs.id" class="gsp-spin gsp-spin--sm"></span>
                  <i v-else class="mdi mdi-trash-can-outline"></i>
                </button>
              </div>
            </div>
            <div class="gsp-tile-meta">
              <span>{{ fmtDate(savedAt(bs)) }}</span>
              <span class="gsp-sep">·</span>
              <span>{{ fmtBytes(bs.file_size_bytes) }}</span>
            </div>
          </div>

          <!-- No battery save yet: say so, rather than leaving a silent gap.
               The cartridge shows through greyed out - the game has one, it
               just has not written its SRAM yet. -->
          <div v-if="!g.battery.length" class="gsp-tile gsp-tile--empty">
            <button
              class="gsp-shot gsp-shot--empty gsp-shot--drop"
              :disabled="!!busy"
              :title="t('profile.upload_battery', 'Upload a battery save (.srm)')"
              @click="pickInto(g, null)"
            >
              <span v-if="busy === 'u' + g.romId + '-bat'" class="gsp-spin"></span>
              <img v-else-if="g.support" :src="g.support" class="gsp-cart gsp-cart--ghost" :alt="g.name" />
              <i v-else class="mdi mdi-sd gsp-shot-ph"></i>
              <span class="gsp-badge gsp-badge--muted">{{ t("profile.battery_saves", "Battery save") }}</span>
            </button>
            <div class="gsp-tile-meta gsp-tile-meta--muted">{{ t("profile.slot_empty", "Empty") }}</div>
          </div>
        </div>
      </div>
    </template>

    <!-- Screenshot at full size: a 148px tile is too small to tell where you
         actually stopped, which is the whole point of the picture. -->
    <Teleport to="body">
      <div v-if="zoom" class="gsp-zoom" @click="zoom = null">
        <img :src="zoom.url" class="gsp-zoom-img" :alt="zoom.caption" @click.stop />
        <div class="gsp-zoom-cap">{{ zoom.caption }}</div>
        <button class="gsp-zoom-x" :title="t('common.close', 'Close')" @click="zoom = null">
          <i class="mdi mdi-close"></i>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "@/i18n";
import dashboardActions, { type SavesData, type GameSaveItem } from "@/lib/dashboardActions";

const { t } = useI18n();
const router = useRouter();
const zoom = ref<{ url: string; caption: string } | null>(null);
const data = ref<SavesData | null>(null);
const loading = ref(true);
const busyId = ref<string | null>(null);

const SORTS = ["recent", "largest"] as const;
const sort = ref<(typeof SORTS)[number]>("recent");
// Everything starts folded so the panel stays as small as it can be, and only
// one game unfolds at a time - together that is what bounds its height. The
// rail already answers "which slots are free" without opening anything.
const open = ref<number | null>(null);

const maxSlot = computed(() => data.value?.max_slot || 9);

const quotaPct = computed(() =>
  data.value && data.value.limit_bytes > 0 ? (data.value.used_bytes / data.value.limit_bytes) * 100 : 0,
);

interface GameSaves {
  romId: number;
  name: string;
  cover: string | null;
  aspect: string;   // the cover's real ratio, so the frame never crops the art
  support: string | null;   // cartridge/disc art - the battery tile's picture
  platformName: string | null;
  platformSlug: string | null;
  slots: Record<number, GameSaveItem | undefined>;
  legacy: GameSaveItem[];
  battery: GameSaveItem[];
  bytes: number;
  latest: number;   // most recently touched save in this game
}

// /savestates/my returns two flat lists across every game; the memory-card view
// needs them keyed by game, then by slot.
const games = computed<GameSaves[]>(() => {
  if (!data.value) return [];
  const byRom = new Map<number, GameSaves>();

  const bucket = (it: GameSaveItem): GameSaves => {
    let g = byRom.get(it.rom_id);
    if (!g) {
      g = {
        romId: it.rom_id,
        name: it.rom_name || stripExt(it.file_name),
        cover: it.rom_cover || null,
        aspect: it.rom_cover_aspect || "3/4",
        support: it.rom_support || null,
        platformName: it.platform_name || null,
        platformSlug: it.platform_slug || null,
        slots: {}, legacy: [], battery: [], bytes: 0, latest: 0,
      };
      byRom.set(it.rom_id, g);
    }
    g.bytes += it.file_size_bytes;
    g.latest = Math.max(g.latest, savedAtMs(it));
    return g;
  };

  for (const s of data.value.states) {
    const g = bucket(s);
    if (s.slot && s.slot >= 1 && s.slot <= maxSlot.value) g.slots[s.slot] = s;
    else g.legacy.push(s);
  }
  for (const s of data.value.saves) bucket(s).battery.push(s);

  const list = [...byRom.values()];
  return sort.value === "largest"
    ? list.sort((a, b) => b.bytes - a.bytes)
    : list.sort((a, b) => b.latest - a.latest);
});

function toggle(romId: number): void {
  open.value = open.value === romId ? null : romId;
}

// ── Export / import ─────────────────────────────────────────────────────────
// Downloads go through the API client, never a plain <a href>: the API
// authenticates on the Authorization header, which a link does not send.

const busy = ref<string | null>(null);
const notice = ref("");
const noticeBad = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
// Where the next picked file goes. null = the header's Import (an archive knows
// its own way home); otherwise a specific game+slot, or battery when slot=null.
const pending = ref<{ romId: number; slot: number | null } | null>(null);

const acceptFor = computed(() =>
  pending.value ? ".state,.srm,.zip" : ".zip,.state,.srm",
);

function say(msg: string, bad = false): void {
  notice.value = msg;
  noticeBad.value = bad;
}

async function run(tag: string, fn: () => Promise<void>): Promise<void> {
  if (busy.value) return;
  busy.value = tag;
  try {
    await fn();
  } catch (e: any) {
    say(e?.response?.data?.detail || e?.message || t("profile.export_failed", "Failed"), true);
  } finally {
    busy.value = null;
  }
}

function exportState(id: number): void { run("st" + id, () => dashboardActions.exportSaveState(id)); }
function exportBattery(id: number): void { run("sv" + id, () => dashboardActions.exportBatterySave(id)); }
function exportGame(g: GameSaves): void { run("g" + g.romId, () => dashboardActions.exportSaves(g.romId)); }
function exportAll(): void { run("exportall", () => dashboardActions.exportSaves()); }

function pickImport(): void {
  pending.value = null;
  fileInput.value?.click();
}
function pickInto(g: GameSaves, slot: number | null): void {
  pending.value = { romId: g.romId, slot };
  fileInput.value?.click();
}

async function onFiles(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";   // so picking the same file twice still fires
  if (!files.length) return;

  const target = pending.value;
  const tag = target
    ? "u" + target.romId + "-" + (target.slot ?? "bat")
    : "import";

  await run(tag, async () => {
    const res = await dashboardActions.importSaves(
      files,
      target ? { romId: target.romId, slot: target.slot ?? undefined } : undefined,
    );
    const failed = res.results.filter((r) => r.status !== "imported" && r.status !== "replaced");
    if (res.imported) data.value = await dashboardActions.saves();

    if (!failed.length) {
      say(t("profile.import_done", "Restored {n} save(s)").replace("{n}", String(res.imported)));
      return;
    }
    // Name the first failure rather than a bare count - "no_rom" in particular
    // means the archive is fine but this server lacks the game.
    const f = failed[0];
    const why = f.status === "no_rom"
      ? t("profile.import_no_rom", "no matching game on this server")
      : f.status === "need_target"
        ? t("profile.import_need_target", "a bare save file needs a game - use the + on a slot")
        : f.detail || t("profile.import_failed", "failed");
    say(`${f.name}: ${why}` + (failed.length > 1 ? ` (+${failed.length - 1})` : ""), true);
  });
}

// Launch the game resuming from THIS save. The ROM detail still asks how you
// want the window (fullscreen/window/tab) - only the save is picked for you.
function play(g: GameSaves, save: string): void {
  if (!g.platformSlug) return;
  router.push({
    path: `/emulation/${g.platformSlug}/${g.romId}`,
    query: { resume: "1", save },
  });
}

function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape" && zoom.value) zoom.value = null;
}
onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + u[i];
}
function stripExt(f: string): string { return f.replace(/\.(state|srm)$/, ""); }

// A slot keeps its created_at when re-saved, so the date the user cares about -
// when this save was actually written - is updated_at.
function savedAt(s: GameSaveItem): string | null { return s.updated_at || s.created_at; }
function savedAtMs(s: GameSaveItem): number {
  const d = new Date(savedAt(s) || 0).getTime();
  return isNaN(d) ? 0 : d;
}
function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function recalcUsed(): void {
  if (!data.value) return;
  data.value.used_bytes =
    data.value.states.reduce((a, s) => a + s.file_size_bytes, 0) +
    data.value.saves.reduce((a, s) => a + s.file_size_bytes, 0);
}

async function del(kind: "state" | "save", id: number): Promise<void> {
  const tag = (kind === "state" ? "st" : "sv") + id;
  if (busyId.value) return;
  busyId.value = tag;
  try {
    if (kind === "state") {
      await dashboardActions.deleteSaveState(id);
      if (data.value) data.value.states = data.value.states.filter((s) => s.id !== id);
    } else {
      await dashboardActions.deleteBatterySave(id);
      if (data.value) data.value.saves = data.value.saves.filter((s) => s.id !== id);
    }
    recalcUsed();
  } catch (e: any) {
    say(e?.response?.data?.detail || t('profile.delete_failed', 'Could not delete that save'), true);
  } finally {
    busyId.value = null;
  }
}

const loadError = ref(false);
onMounted(async () => {
  try {
    data.value = await dashboardActions.saves();
  } catch (e: any) {
    // Swallowing this left `data` null with loading false, so the panel drew its
    // header, the sort chips and Import over nothing at all - identical to
    // having no saves. Someone whose saves failed to load must not be told they
    // have none.
    loadError.value = true;
    say(e?.response?.data?.detail || t('profile.saves_load_failed', 'Could not load your saves'), true);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.gsp { border-radius: 12px; padding: 14px 16px; margin-top: 14px; }
.gsp-loadfail { padding: 18px 4px; font-size: 13px; opacity: 0.75; text-align: center; color: var(--text, #eee); }
.gsp-h { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; margin-bottom: 12px; }
.gsp-h-ico { font-size: 26px; opacity: 0.9; color: var(--accent, #38d3db); }
.gsp-sorts { margin-left: auto; display: flex; gap: 5px; }
.gsp-chip { border: 0; border-radius: 20px; padding: 3px 10px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.3px; cursor: pointer; color: var(--text, #eee); background: color-mix(in srgb, var(--accent, #38d3db) 10%, transparent); opacity: 0.75; transition: opacity 0.15s ease, background 0.15s ease; }
.gsp-chip:hover { opacity: 1; }
.gsp-chip--on { background: color-mix(in srgb, var(--accent, #38d3db) 26%, transparent); opacity: 1; }
.gsp-chip--act { display: inline-flex; align-items: center; gap: 4px; }
.gsp-chip--act i { font-size: 13px; }
.gsp-chip:disabled { opacity: 0.4; cursor: default; }
/* The picker is driven from code; the visible controls are the chips and tiles. */
.gsp-file { display: none; }

.gsp-notice { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 8px 10px; border-radius: 8px; margin-bottom: 12px; background: color-mix(in srgb, var(--accent, #38d3db) 12%, transparent); }
.gsp-notice--bad { background: color-mix(in srgb, #f87171 14%, transparent); color: #fca5a5; }
.gsp-notice i { font-size: 15px; flex: 0 0 auto; }
.gsp-notice-x { margin-left: auto; border: 0; background: transparent; color: inherit; cursor: pointer; opacity: 0.6; font-size: 14px; display: inline-flex; }
.gsp-notice-x:hover { opacity: 1; }
.gsp-loading { display: flex; justify-content: center; padding: 20px 0; }
.gsp-spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.25); border-top-color: var(--accent, #38d3db); animation: gspSpin 0.7s linear infinite; display: inline-block; }
.gsp-spin--sm { width: 12px; height: 12px; }
@keyframes gspSpin { to { transform: rotate(360deg); } }

/* Quota */
.gsp-quota { margin-bottom: 14px; }
.gsp-quota-bar { height: 8px; border-radius: 6px; background: rgba(255,255,255,0.08); overflow: hidden; }
.gsp-quota-fill { height: 100%; border-radius: 6px; background: var(--accent, #38d3db); transition: width 0.5s ease; }
.gsp-quota-fill.warn { background: #fbbf24; }
.gsp-quota-text { font-size: 11.5px; opacity: 0.6; margin-top: 6px; }
.gsp-empty { font-size: 12px; opacity: 0.5; padding: 4px 0 8px; }
.gsp-sep { opacity: 0.5; }

/* Game line */
.gsp-game { border-top: 1px solid rgba(255,255,255,0.07); }
.gsp-game:first-of-type { border-top: 0; }
.gsp-row { display: flex; align-items: center; gap: 10px; padding: 8px 6px; border-radius: 8px; cursor: pointer; transition: background 0.15s ease; }
.gsp-row:hover { background: rgba(255,255,255,0.04); }
.gsp-row:focus-visible { outline: 2px solid var(--accent, #38d3db); outline-offset: -2px; }
.gsp-game--open .gsp-row { background: rgba(255,255,255,0.04); }
.gsp-chev { font-size: 18px; opacity: 0.5; flex: 0 0 auto; }
/* Height is fixed, width follows the cover's own aspect-ratio (inline, from the
   API) - a hardcoded portrait box crops the 4/3 art SNES and friends ship. */
.gsp-game-cover { height: 38px; flex: 0 0 auto; border-radius: 5px; overflow: hidden; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; }
.gsp-game-cover-img { width: 100%; height: 100%; object-fit: contain; }
.gsp-game-cover-ph { font-size: 16px; opacity: 0.35; }
.gsp-game-info { flex: 1; min-width: 0; }
.gsp-game-name { font-size: 13.5px; font-weight: 600; color: var(--text, #eee); text-decoration: none; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
a.gsp-game-name:hover { color: var(--accent, #38d3db); }
.gsp-game-sub { font-size: 11px; opacity: 0.6; display: flex; align-items: center; gap: 5px; }

/* Slot rail: dashed = free, tinted = used. The number IS the label. */
.gsp-rail { display: flex; align-items: center; gap: 3px; flex: 0 0 auto; }
.gsp-pip { width: 18px; height: 18px; border-radius: 5px; display: inline-flex; align-items: center; justify-content: center; font-size: 9.5px; font-weight: 700; border: 1px dashed rgba(255,255,255,0.22); color: rgba(255,255,255,0.3); background: transparent; }
.gsp-pip--on { border: 1px solid transparent; background: color-mix(in srgb, var(--accent, #38d3db) 32%, transparent); color: var(--text, #eee); }
.gsp-pip--bat { margin-left: 5px; border-radius: 50%; font-size: 11px; }
.gsp-pip--bat.gsp-pip--on { background: color-mix(in srgb, var(--accent, #38d3db) 32%, transparent); }

/* Unfolded card */
.gsp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(148px, 1fr)); gap: 10px; padding: 4px 6px 14px; }
.gsp-tile { min-width: 0; }
.gsp-shot { position: relative; aspect-ratio: 4 / 3; border-radius: 8px; overflow: hidden; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; }
.gsp-shot-img { width: 100%; height: 100%; object-fit: cover; }
.gsp-shot-ph { font-size: 26px; opacity: 0.25; }
.gsp-shot--empty { border: 1px dashed rgba(255,255,255,0.14); background: transparent; }
/* An empty tile is a button (upload into this slot) - reset it to look like the
   frame it replaced, and invite the click on hover. */
.gsp-shot--drop { width: 100%; padding: 0; color: inherit; font: inherit; cursor: pointer; transition: border-color 0.15s ease, background 0.15s ease; }
.gsp-shot--drop:hover:not(:disabled) { border-color: var(--accent, #38d3db); background: color-mix(in srgb, var(--accent, #38d3db) 8%, transparent); }
.gsp-shot--drop:hover:not(:disabled) .gsp-shot-ph { opacity: 0.6; }
.gsp-shot--drop:disabled { cursor: default; }
.gsp-btn--ghost { flex: 0 0 auto; background: transparent; opacity: 0.55; }
.gsp-btn--ghost:hover { opacity: 1; background: rgba(255,255,255,0.08); }
.gsp-shot--bat { background: color-mix(in srgb, var(--accent, #38d3db) 8%, transparent); }
.gsp-shot-ph--bat { opacity: 0.5; color: var(--accent, #38d3db); }
/* The cartridge, whole, inside the 4/3 tile. width/height stay auto so the
   art keeps its own proportions - it runs from 0.91 (NES, squarish) to 2.87
   (a slim SNES front), and any fixed crop would slice most of them. The
   drop-shadow follows the alpha where the scrape cut the cartridge out
   (NES, Genesis) and the rounded rect where it did not, so it reads as an
   object either way. */
.gsp-cart { max-width: 86%; max-height: 78%; border-radius: 3px; filter: drop-shadow(0 5px 10px rgba(0,0,0,0.55)); }
/* Empty battery slot: the cartridge greyed out - present, but holding nothing
   yet. Must follow .gsp-cart: same specificity, so order decides, and the flat
   filter here deliberately drops the shadow (a ghost casts none). */
.gsp-cart--ghost { opacity: 0.26; filter: grayscale(1); }
.gsp-badge { position: absolute; top: 6px; left: 6px; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 20px; background: rgba(10,12,18,0.72); color: #fff; backdrop-filter: blur(3px); }
.gsp-badge--muted { background: rgba(255,255,255,0.08); opacity: 0.6; }
.gsp-badge--legacy { background: color-mix(in srgb, #fbbf24 26%, rgba(10,12,18,0.72)); }
.gsp-badge--bat { background: color-mix(in srgb, var(--accent, #38d3db) 26%, rgba(10,12,18,0.72)); }

/* Actions ride on the tile and appear on hover; always visible on touch */
.gsp-acts { position: absolute; right: 5px; bottom: 5px; display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s ease; }
.gsp-tile:hover .gsp-acts, .gsp-tile:focus-within .gsp-acts { opacity: 1; }
@media (hover: none) { .gsp-acts { opacity: 1; } }
.gsp-btn { width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 6px; background: rgba(10,12,18,0.78); color: var(--text, #eee); cursor: pointer; font-size: 14px; text-decoration: none; transition: filter 0.15s ease; }
.gsp-btn:hover { filter: brightness(1.35); }
.gsp-btn--play { background: color-mix(in srgb, var(--accent, #38d3db) 32%, rgba(10,12,18,0.78)); color: var(--text, #eee); }
.gsp-btn--del { color: #f87171; }
.gsp-btn:disabled { opacity: 0.5; cursor: default; }
.gsp-shot-img--zoom { cursor: zoom-in; }

/* Full-size screenshot. Teleported to body so no dashboard panel's overflow or
   stacking context can clip it. */
.gsp-zoom { position: fixed; inset: 0; z-index: 300; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 5vh 5vw; background: rgba(8,10,15,0.88); backdrop-filter: blur(4px); cursor: zoom-out; }
.gsp-zoom-img { max-width: 100%; max-height: 82vh; border-radius: 10px; box-shadow: 0 18px 60px rgba(0,0,0,0.6); image-rendering: pixelated; cursor: default; }
.gsp-zoom-cap { font-size: 12.5px; opacity: 0.75; color: #fff; }
.gsp-zoom-x { position: absolute; top: 16px; right: 18px; width: 34px; height: 34px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 50%; background: rgba(255,255,255,0.12); color: #fff; font-size: 18px; cursor: pointer; }
.gsp-zoom-x:hover { background: rgba(255,255,255,0.2); }

.gsp-tile-meta { font-size: 10.5px; opacity: 0.6; margin-top: 5px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.gsp-tile-meta--muted { opacity: 0.35; }

/* Narrow: the rail drops under the title rather than squeezing the name away */
@media (max-width: 560px) {
  .gsp-row { flex-wrap: wrap; }
  .gsp-game-info { flex: 1 1 60%; }
  .gsp-rail { flex: 1 0 100%; padding-left: 28px; }
}
</style>
