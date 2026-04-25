/**
 * Shared reactive badge state for Game Request notifications.
 * Module-level refs so all components share the same counters.
 *   - Admin sees pending_count (always-on indicator)
 *   - User sees count of their requests whose status changed since last viewed
 */
import { ref, computed } from 'vue'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'

const pendingCount = ref(0)
const myChanged    = ref(0)

export function useRequestNotify() {
  const auth = useAuthStore()

  async function refresh() {
    try {
      const { data } = await client.get('/requests/notify')
      pendingCount.value = data.pending_count ?? 0

      const userId = auth.user?.id
      if (userId) {
        const seen: Record<string, string> = JSON.parse(
          localStorage.getItem(`gd3_req_ack_${userId}`) ?? '{}'
        )
        let changed = 0
        for (const r of data.my_requests as { id: number; status: string }[]) {
          if (r.status !== 'pending' && seen[String(r.id)] !== r.status) changed++
        }
        myChanged.value = changed
      }
    } catch { /* network errors are silent */ }
  }

  /** Call after loading the request list so the user badge clears. */
  function markSeen(myRequests: { id: number; status: string }[]) {
    const userId = auth.user?.id
    if (!userId) return
    const seen: Record<string, string> = {}
    for (const r of myRequests) seen[String(r.id)] = r.status
    localStorage.setItem(`gd3_req_ack_${userId}`, JSON.stringify(seen))
    myChanged.value = 0
  }

  const isAdmin    = computed(() => ['admin', 'editor'].includes(auth.user?.role as string))
  /** Badge count shown on the Request button */
  const totalBadge = computed(() =>
    (isAdmin.value ? pendingCount.value : 0) + myChanged.value
  )

  return { pendingCount, myChanged, totalBadge, refresh, markSeen }
}
