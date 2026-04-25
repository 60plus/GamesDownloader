/**
 * Composable for user-facing notifications.
 * Provides success/error/info toast methods.
 */

import { ref } from "vue";

export interface Notification {
  id: number;
  type: "success" | "error" | "info" | "warning";
  message: string;
  timeout?: number;
}

const notifications = ref<Notification[]>([]);
let nextId = 0;

function add(type: Notification["type"], message: string, timeout = 4000) {
  const id = nextId++;
  notifications.value.push({ id, type, message, timeout });
  if (timeout > 0) {
    setTimeout(() => remove(id), timeout);
  }
}

function remove(id: number) {
  notifications.value = notifications.value.filter((n) => n.id !== id);
}

export function useNotifications() {
  return {
    notifications,
    success: (msg: string) => add("success", msg),
    error: (msg: string) => add("error", msg, 6000),
    info: (msg: string) => add("info", msg),
    warning: (msg: string) => add("warning", msg),
    remove,
  };
}
