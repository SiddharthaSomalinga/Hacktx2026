import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import styles from './Panel.module.css'

export type Snap = 'peek' | 'half' | 'full'

const PanelContext = createContext<(snap: Snap) => void>(() => {})

/** Ask the docked panel for a height when this screen opens. */
export function usePanelSnap(snap: Snap): void {
  const setSnap = useContext(PanelContext)
  useEffect(() => setSnap(snap), [snap, setSnap])
}

const heights: Record<Snap, () => number> = {
  peek: () => 168,
  half: () => Math.round(window.innerHeight * 0.48),
  full: () => window.innerHeight - 64,
}

function nearest(px: number): Snap {
  const order: Snap[] = ['peek', 'half', 'full']
  return order.reduce((best, s) => (Math.abs(heights[s]() - px) < Math.abs(heights[best]() - px) ? s : best))
}

const wide = () => window.matchMedia('(min-width: 1024px)').matches

/**
 * The docked, non-modal panel: a draggable bottom sheet on phones, a side panel from 1024px.
 * It publishes its height as --panel-h so the canvas can keep its subject visible above it.
 */
export function Panel({ label, children }: { label: string; children: ReactNode }) {
  const [snap, setSnapState] = useState<Snap>('half')
  const [drag, setDrag] = useState<number | null>(null)
  const start = useRef<{ y: number; h: number } | null>(null)
  const [, force] = useState(0)

  useEffect(() => {
    const onResize = () => force((n) => n + 1)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const height = drag ?? heights[snap]()
  useEffect(() => {
    document.documentElement.style.setProperty('--panel-h', `${height}px`)
    document.documentElement.style.setProperty('--canvas-bottom', wide() ? '0px' : `${heights[snap]()}px`)
  }, [height, snap])

  const setSnap = useCallback((s: Snap) => setSnapState(s), [])

  const onPointerDown = (e: React.PointerEvent) => {
    if (wide()) return
    start.current = { y: e.clientY, h: heights[snap]() }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return
    const h = start.current.h + (start.current.y - e.clientY)
    setDrag(Math.max(96, Math.min(window.innerHeight - 64, h)))
  }
  const onPointerUp = (e: React.PointerEvent) => {
    if (!start.current) return
    const moved = Math.abs(start.current.y - e.clientY) > 6
    if (moved && drag !== null) setSnapState(nearest(drag))
    else setSnapState(snap === 'full' ? 'half' : snap === 'half' ? 'full' : 'half')
    start.current = null
    setDrag(null)
  }

  const next: Record<Snap, string> = { peek: 'Expand panel', half: 'Expand panel', full: 'Collapse panel' }
  return (
    <PanelContext.Provider value={setSnap}>
      <section aria-label={label} className={`${styles.panel} ${drag !== null ? styles.dragging : ''}`}>
        <button
          type="button"
          className={styles.handle}
          aria-label={next[snap]}
          aria-expanded={snap === 'full'}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
        <div className={styles.body}>{children}</div>
      </section>
    </PanelContext.Provider>
  )
}
