import type { Map as MapLibreMap } from 'maplibre-gl'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { BuildingSummary } from '../api/types'
import { CAMPUS_BOUNDS, FOOTPRINTS, fit, project, type Camera, type LngLat, type Padding } from './camera'
import { SHARE_VAR, SHARE_WORDS, shareOf, shortName } from './share'
import styles from './CampusMap.module.css'

type Props = {
  buildings: BuildingSummary[] | undefined
  badges?: Record<string, string> | undefined
  animate: boolean
  onBuilding: (id: string) => void
}

// Room for the top bar and markers, and for the panel: half the screen on phones (its default
// snap), a 400px column on wide screens.
function padding(width: number, height: number): Padding {
  if (width >= 1024) return { top: 140, right: 96, bottom: 72, left: 500 }
  return { top: 190, right: 48, bottom: Math.round(height * 0.48) + 24, left: 48 }
}

const MARKER_H = 44
const MARKER_W = 120

/** Lifts markers that would overlap, so close buildings stay readable. Returns a lift per id. */
function liftMarkers(points: { id: string; x: number; y: number }[]): Map<string, number> {
  const placed: { x: number; y: number }[] = []
  const lifts = new Map<string, number>()
  for (const p of [...points].sort((a, b) => b.y - a.y)) {
    let lift = 0
    while (placed.some((q) => Math.abs(q.x - p.x) < MARKER_W && Math.abs(q.y - (p.y - lift)) < MARKER_H + 6)) lift += MARKER_H + 8
    placed.push({ x: p.x, y: p.y - lift })
    lifts.set(p.id, lift)
  }
  return lifts
}

function centroid(ring: LngLat[]): LngLat {
  const n = ring.length - 1 || 1 // the ring repeats its first point
  const pts = ring.slice(0, n)
  return [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length]
}

/** The campus: a real street map (MapLibre, self-hosted tiles) under live building footprints. */
export function CampusMap({ buildings, badges, animate, onBuilding }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<HTMLDivElement>(null)
  const map = useRef<MapLibreMap | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [camera, setCamera] = useState<Camera | null>(null)
  const [, setFrame] = useState(0) // re-project the overlay as the map moves
  const [mapState, setMapState] = useState<'loading' | 'ready' | 'unavailable'>('loading')

  useLayoutEffect(() => {
    const el = rootRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      const { width, height } = entry.contentRect
      setSize({ width, height })
      setCamera((current) => current ?? fit(CAMPUS_BOUNDS, width, height, padding(width, height), 17.2))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Load MapLibre after first paint; the footprints are already drawn in SVG meanwhile.
  useEffect(() => {
    if (!camera || !mapRef.current || map.current) return
    let cancelled = false
    const container = mapRef.current
    void (async () => {
      try {
        const [maplibregl, { default: workerUrl }, { campusStyle, TILE_BOUNDS }] = await Promise.all([
          import('maplibre-gl'),
          import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'),
          import('./style'),
          import('maplibre-gl/dist/maplibre-gl.css'),
        ])
        if (cancelled) return
        maplibregl.setWorkerUrl(workerUrl)
        const instance = new maplibregl.Map({
          container,
          style: campusStyle(),
          center: camera.center,
          zoom: camera.zoom,
          minZoom: 14.5,
          maxZoom: 18.5,
          maxBounds: [
            [TILE_BOUNDS[0], TILE_BOUNDS[1]],
            [TILE_BOUNDS[2], TILE_BOUNDS[3]],
          ],
          renderWorldCopies: false,
          dragRotate: false,
          pitchWithRotate: false,
          attributionControl: { compact: true },
        })
        instance.touchZoomRotate.disableRotation()
        instance.keyboard.disableRotation()
        instance.on('move', () => setFrame((n) => n + 1))
        instance.once('load', () => setMapState('ready'))
        instance.on('error', (e) => console.warn('campus map:', e.error.message))
        map.current = instance

        // Follow theme changes: a manual override or the system setting.
        const restyle = () => instance.setStyle(campusStyle())
        const scheme = window.matchMedia('(prefers-color-scheme: dark)')
        scheme.addEventListener('change', restyle)
        const observer = new MutationObserver(restyle)
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
        instance.once('remove', () => {
          scheme.removeEventListener('change', restyle)
          observer.disconnect()
        })
      } catch (error) {
        console.warn('campus map unavailable:', error)
        if (!cancelled) setMapState('unavailable')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [camera])

  useEffect(() => () => map.current?.remove(), [])

  const toScreen = (p: LngLat): [number, number] => {
    if (map.current && mapState === 'ready') {
      const pt = map.current.project(p)
      return [pt.x, pt.y]
    }
    if (!camera) return [0, 0]
    const [x, y] = project(p, camera.zoom)
    const [cx, cy] = project(camera.center, camera.zoom)
    return [x - cx + size.width / 2, y - cy + size.height / 2]
  }

  const byId = new Map((buildings ?? []).map((b) => [b.id, b]))
  const lifts = liftMarkers(
    FOOTPRINTS.map((f) => {
      const [x, y] = toScreen(centroid(f.geometry.coordinates[0] ?? []))
      return { id: f.id, x, y }
    }),
  )

  return (
    <div ref={rootRef} className={`${styles.root} ${animate ? styles.animate : ''}`}>
      <div ref={mapRef} className={`${styles.map} ${mapState === 'ready' ? styles.mapReady : ''}`} aria-hidden />
      {camera && size.width > 0 && (
        <>
          <svg className={styles.overlay} width={size.width} height={size.height} aria-hidden>
            {FOOTPRINTS.map((f) => {
              const ring = f.geometry.coordinates[0] ?? []
              const d = ring.map((p, i) => `${i ? 'L' : 'M'}${toScreen(p).join(' ')}`).join('') + 'Z'
              const b = byId.get(f.id)
              const color = b ? SHARE_VAR[shareOf(b)] : 'var(--ink-3)'
              return (
                <path
                  key={f.id}
                  d={d}
                  pathLength={1}
                  className={`${styles.footprint} ${b ? styles.known : ''}`}
                  style={{ ['--share' as string]: color }}
                />
              )
            })}
          </svg>
          {FOOTPRINTS.map((f) => {
            const b = byId.get(f.id)
            const [x, y] = toScreen(centroid(f.geometry.coordinates[0] ?? []))
            const lift = lifts.get(f.id) ?? 0
            const share = b ? shareOf(b) : 'none'
            const badge = badges?.[f.id]
            const label = b
              ? `${b.name}${b.is_simulated ? ', simulated' : ''}: ${b.open} open, ${SHARE_WORDS[share]}${badge ? `, ${badge}` : ''}`
              : shortName(f.id)
            return (
              <button
                key={f.id}
                type="button"
                className={styles.marker}
                style={{ left: x, top: y, ['--share' as string]: SHARE_VAR[share], ['--lift' as string]: `${lift}px` }}
                aria-label={label}
                onClick={() => onBuilding(f.id)}
              >
                <span className={styles.swatch} aria-hidden />
                <span className={styles.code}>{shortName(f.id)}</span>
                {b && <span className={styles.count}>{b.open}</span>}
                {b?.is_simulated && <span className={styles.sim}>SIM</span>}
                {badge && <span className={styles.badge}>{badge}</span>}
              </button>
            )
          })}
        </>
      )}
      {mapState === 'unavailable' && <p className={styles.note}>Street map unavailable on this device</p>}
    </div>
  )
}
