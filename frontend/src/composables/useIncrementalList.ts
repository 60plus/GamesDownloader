import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

/**
 * Render a long list incrementally instead of all at once.
 *
 * The full array stays in memory; only the first `count` items are exposed via
 * `visible`, and an IntersectionObserver on a sentinel element near the bottom
 * grows `count` by `step` as the user scrolls down. The list looks and scrolls
 * exactly like a plain `v-for` over the whole array - it just mounts its rows
 * in batches, so a 500-item library is a few dozen DOM rows at a time instead
 * of thousands at once.
 *
 * Usage in a view:
 *   const incr = useIncrementalList(displayedGames)
 *   // template: v-for="g in incr.visible" ... then <div ref="incr.sentinel" />
 *   // alpha jump: incr.ensure(idx); await nextTick(); <scroll to element>
 */
export function useIncrementalList<T>(
  source: Ref<T[]> | ComputedRef<T[]>,
  opts: { initial?: number; step?: number; rootMargin?: string } = {},
) {
  const initial = opts.initial ?? 60
  const step = opts.step ?? 40
  const rootMargin = opts.rootMargin ?? '600px'

  const count = ref(initial)
  const visible = computed(() => source.value.slice(0, count.value))
  const hasMore = computed(() => count.value < source.value.length)

  // A new result set (search / filter / different library changes the length)
  // starts again from the top; growing `count` on scroll never changes length,
  // so ordinary scrolling does not reset.
  watch(
    () => source.value.length,
    () => { count.value = initial },
  )

  function loadMore() {
    if (count.value < source.value.length) {
      count.value = Math.min(count.value + step, source.value.length)
    }
  }

  /** Ensure at least `index` items are mounted (used before a jump-to-letter). */
  function ensure(index: number) {
    if (count.value <= index) {
      count.value = Math.min(index + step, source.value.length)
    }
  }

  const sentinel = ref<HTMLElement | null>(null)
  let io: IntersectionObserver | null = null

  onMounted(() => {
    io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore()
      },
      { rootMargin },
    )
    if (sentinel.value) io.observe(sentinel.value)
  })

  watch(sentinel, (el, old) => {
    if (!io) return
    if (old) io.unobserve(old)
    if (el) io.observe(el)
  })

  onBeforeUnmount(() => {
    io?.disconnect()
    io = null
  })

  return { visible, hasMore, count, sentinel, loadMore, ensure }
}
