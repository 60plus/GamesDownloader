/**
 * The cover that leans towards the pointer, with a highlight sliding across it.
 *
 * Six detail views carried their own copy, and the copies had come apart. Four
 * of them computed the whole effect without ever asking the theme store, so the
 * Card tilt and Card shine switches did nothing there. The two that did ask
 * required tilt to be on before the shine could show, which is not what the
 * two separate switches promise.
 *
 * One implementation now, and the two switches are independent: either can be
 * on without the other.
 */
import { ref } from 'vue'

import { useThemeStore } from '@/stores/theme'

const REST = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'

export function useCoverTilt() {
  const themeStore = useThemeStore()
  const coverTilt  = ref(REST)
  const sheenStyle = ref('opacity:0')

  function onCoverMove(e: MouseEvent) {
    if (!themeStore.cardTilt && !themeStore.cardShine) return
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const cx = rect.width / 2
    const cy = rect.height / 2

    if (themeStore.cardTilt) {
      const dx = e.clientX - rect.left - cx
      const dy = e.clientY - rect.top  - cy
      const rotY =  (dx / cx) * 10
      const rotX = -(dy / cy) *  7
      coverTilt.value = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.03,1.03,1.03)`
    }

    if (themeStore.cardShine) {
      const mx = ((e.clientX - rect.left) / rect.width  * 100).toFixed(1)
      const my = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1)
      sheenStyle.value = `opacity:1; background: radial-gradient(ellipse at ${mx}% ${my}%, rgba(255,255,255,0.22) 0%, transparent 65%);`
    }
  }

  function onCoverLeave() {
    coverTilt.value  = REST
    sheenStyle.value = 'opacity:0'
  }

  return { coverTilt, sheenStyle, onCoverMove, onCoverLeave }
}
