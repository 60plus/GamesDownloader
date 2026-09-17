/* The avatar badge that says a game has two memory cards to choose between.
 *
 * A scan that merges a renamed game's rows, where the same person had saved a
 * memory card on both, keeps one card in use and sets the other aside for them
 * (GET /savestates/conflicts). The server tells that person over the socket
 * (saves:conflict). That reaches somebody who is signed in at the time, so the
 * list is also asked for whenever an account signs in, and a person who was
 * away finds out on arrival rather than never.
 *
 * Every layout draws these badges - the built-in ones directly and the theme
 * plugins through __GD__.notifications - and the action takes the person to the
 * dashboard, where the saves panel holds the choice. So one badge here reaches
 * all of them.
 */
import { watch } from "vue";
import i18n from "@/i18n";
import dashboardActions from "@/lib/dashboardActions";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notifications";
import { useSocketStore } from "@/stores/socket";

export const SAVE_CONFLICT_BADGE = "save-conflicts";

/** Ask the server again and make the badge say what it says. Quiet on failure:
 * a badge that cannot be refreshed is left as it was, never cleared on a guess. */
export async function refreshSaveConflictBadge(): Promise<void> {
  let list;
  try {
    list = await dashboardActions.saveConflicts();
  } catch {
    return;
  }
  const notifications = useNotificationStore();
  if (!list.length) {
    notifications.remove(SAVE_CONFLICT_BADGE);
    return;
  }
  notifications.add({
    id: SAVE_CONFLICT_BADGE,
    count: list.length,
    label: i18n.t("profile.card_conflict_badge", "Two memory cards to choose between"),
    details: list.map((c) => c.rom_name || c.set_aside.file_name),
    action: "/dashboard",
    actionLabel: i18n.t("profile.card_conflict_open", "Choose"),
  });
}

/** Wire the badge up once, at start: on every sign-in, and on every message. */
export function watchSaveConflicts(): void {
  const auth = useAuthStore();
  watch(
    () => auth.user?.id,
    (id) => {
      if (id) void refreshSaveConflictBadge();
      else useNotificationStore().remove(SAVE_CONFLICT_BADGE);
    },
    { immediate: true },
  );
  useSocketStore().onSaveConflict(() => { void refreshSaveConflictBadge(); });
}
