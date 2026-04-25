/**
 * Avatar notification store - general-purpose notification system.
 *
 * Any component or plugin can push notifications that appear as a badge
 * on the user avatar chip. Dismissed notifications persist in sessionStorage
 * so they don't reappear until the browser/container restarts.
 *
 * Plugins access via: window.__GD__.notifications.add({ id, count, label })
 */

import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface AvatarNotification {
  id: string;
  count: number;
  label: string;
  details?: string[];
  action?: string;
  actionLabel?: string;
}

const SS_KEY = "gd3_notif_dismissed";

function loadDismissed(): Set<string> {
  try {
    const raw = sessionStorage.getItem(SS_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>) {
  sessionStorage.setItem(SS_KEY, JSON.stringify([...ids]));
}

export const useNotificationStore = defineStore("notifications", () => {
  const items = ref<AvatarNotification[]>([]);
  const dismissed = ref<Set<string>>(loadDismissed());

  const active = computed(() =>
    items.value.filter((n) => n.count > 0 && !dismissed.value.has(n.id))
  );

  const totalCount = computed(() =>
    active.value.reduce((sum, n) => sum + n.count, 0)
  );

  const hasBadge = computed(() => totalCount.value > 0);

  function add(notification: AvatarNotification) {
    const idx = items.value.findIndex((n) => n.id === notification.id);
    if (idx >= 0) {
      items.value[idx] = notification;
    } else {
      items.value.push(notification);
    }
    // If count changed, un-dismiss so it shows again
    if (notification.count > 0) {
      dismissed.value.delete(notification.id);
      saveDismissed(dismissed.value);
    }
  }

  function dismiss(id: string) {
    dismissed.value.add(id);
    saveDismissed(dismissed.value);
  }

  function dismissAll() {
    for (const n of items.value) {
      dismissed.value.add(n.id);
    }
    saveDismissed(dismissed.value);
  }

  function remove(id: string) {
    items.value = items.value.filter((n) => n.id !== id);
  }

  return { items, active, totalCount, hasBadge, add, dismiss, dismissAll, remove };
});
