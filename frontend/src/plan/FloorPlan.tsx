import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { BuildingDetail, PublicState } from '../api/types'
import type { SeatMark } from '../app/focus'
import { CHAIR, CHAIR_GAP, layoutFloor, TABLE_DEPTH, zoomTo, type Box, type PlacedSeat } from './layout'
import { seatName, tableName } from './seatName'
import styles from './FloorPlan.module.css'

type Props = {
  detail: BuildingDetail | undefined
  floor: number
  tableId?: string | undefined
  selectedSeatId?: string | undefined
  marks: SeatMark[]
  animate: boolean
  onTable: (tableId: string) => void
  onSeat: (seatId: string) => void
}

const GUTTER = 30 // room for the grid bubbles around the drawing
const COLUMNS = ['A', 'B', 'C', 'D', 'E', 'F']

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, size] as const
}

function Chair({ placed, mark, selected }: { placed: PlacedSeat; mark: string | undefined; selected: boolean }) {
  const { x, y, side, seat } = placed
  const h = CHAIR * 0.82
  const back = side === 'top' ? y - h / 2 - 5 : y + h / 2 + 1
  return (
    <g className={`${styles.chair} ${styles[seat.state]}`}>
      {mark && (
        <g className={styles.ring}>
          <rect x={x - CHAIR / 2 - 6} y={y - h / 2 - 6} width={CHAIR + 12} height={h + 12} rx={10} />
          <rect x={x - CHAIR / 2 - 10} y={y - h / 2 - 10} width={CHAIR + 20} height={h + 20} rx={13} />
        </g>
      )}
      {selected && <rect className={styles.selected} x={x - CHAIR / 2 - 5} y={y - h / 2 - 5} width={CHAIR + 10} height={h + 10} rx={9} />}
      <rect className={styles.back} x={x - CHAIR / 2 + 4} y={back} width={CHAIR - 8} height={4} rx={2} pathLength={1} />
      <rect className={styles.body} x={x - CHAIR / 2} y={y - h / 2} width={CHAIR} height={h} rx={6} pathLength={1} />
      {seat.state === 'likely_opening' && (
        <g className={styles.bag}>
          <rect x={x - 6} y={y - 3} width={12} height={10} rx={2.5} />
          <path d={`M${x - 3.5} ${y - 3}v-2.2a3.5 3.5 0 0 1 7 0V${y - 3}`} />
        </g>
      )}
    </g>
  )
}

export function FloorPlan({ detail, floor, tableId, selectedSeatId, marks, animate, onTable, onSeat }: Props) {
  const [ref, size] = useSize<HTMLDivElement>()
  const floorData = detail?.floors.find((f) => f.floor === floor)
  const tables = floorData?.tables ?? []

  const area: Box = useMemo(
    () => ({ left: GUTTER, top: GUTTER, width: Math.max(0, size.width - 2 * GUTTER), height: Math.max(0, size.height - 2 * GUTTER) }),
    [size.width, size.height],
  )
  const layout = useMemo(() => layoutFloor(tables, area), [tables, area])
  const s = layout.scale
  const focused = layout.tables.find((t) => t.table.id === tableId)
  const camera = focused ? zoomTo(focused, s, area) : { x: 0, y: 0, k: 1 }
  const markBySeat = new Map(marks.map((m) => [m.seatId, m.label]))
  const seatsTappable = focused !== undefined || CHAIR * s >= 40

  // Draw order follows distance from the middle, so the plan unfolds outward.
  const mid = { x: area.left + area.width / 2, y: area.top + area.height / 2 }
  const reach = Math.hypot(area.width, area.height) / 2 || 1
  const delay = (x: number, y: number) => `${Math.round((Math.hypot(x - mid.x, y - mid.y) / reach) * 420)}ms`

  return (
    <div ref={ref} className={`${styles.root} ${animate ? styles.animate : ''}`}>
      {size.width > 0 && (
        <>
          <svg className={styles.grid} width={size.width} height={size.height} aria-hidden>
            <rect className={styles.frame} x={GUTTER} y={GUTTER} width={area.width} height={area.height} pathLength={1} />
            {COLUMNS.slice(0, 5).map((c, i) => {
              const x = area.left + ((i + 0.5) / 5) * area.width
              return (
                <g key={c}>
                  <line className={styles.gridLine} x1={x} x2={x} y1={GUTTER} y2={GUTTER + area.height} />
                  <circle className={styles.bubble} cx={x} cy={GUTTER / 2} r={9} />
                  <text className={styles.bubbleText} x={x} y={GUTTER / 2}>
                    {c}
                  </text>
                </g>
              )
            })}
            {[1, 2, 3, 4].map((n, i) => {
              const y = area.top + ((i + 0.5) / 4) * area.height
              return (
                <g key={n}>
                  <line className={styles.gridLine} x1={GUTTER} x2={GUTTER + area.width} y1={y} y2={y} />
                  <circle className={styles.bubble} cx={GUTTER / 2} cy={y} r={9} />
                  <text className={styles.bubbleText} x={GUTTER / 2} y={y}>
                    {n}
                  </text>
                </g>
              )
            })}
          </svg>

          <div
            className={styles.stage}
            style={{ transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.k})` }}
          >
            <svg width={size.width} height={size.height} aria-hidden className={styles.drawing}>
              <defs>
                <pattern id="gs-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="5" height="5" fill="var(--offline-fill)" />
                  <line x1="0" y1="0" x2="0" y2="5" stroke="var(--offline)" strokeWidth="1.4" />
                </pattern>
              </defs>
              {layout.tables.map((t) => (
                <g
                  key={t.table.id}
                  transform={`translate(${t.cx} ${t.cy}) scale(${s})`}
                  className={focused && focused !== t ? styles.dim : undefined}
                  style={{ ['--delay' as string]: delay(t.cx, t.cy) }}
                >
                  <rect
                    className={styles.table}
                    x={-t.width / 2}
                    y={-TABLE_DEPTH / 2}
                    width={t.width}
                    height={TABLE_DEPTH}
                    rx={4}
                    pathLength={1}
                  />
                  <text className={styles.tableLabel} x={0} y={0}>
                    {t.table.label.replace('Table ', 'T')}
                  </text>
                  {t.seats.map((p) => (
                    <Chair key={p.seat.id} placed={p} mark={markBySeat.get(p.seat.id)} selected={p.seat.id === selectedSeatId} />
                  ))}
                </g>
              ))}
            </svg>

            {layout.tables.map((t) => {
              const states = t.table.seats.map((x) => x.state as PublicState)
              const isFocused = focused === t
              return (
                <div key={t.table.id}>
                  {!isFocused && (
                    <button
                      type="button"
                      className={styles.tableHit}
                      aria-label={tableName(t.table.label, states)}
                      style={{
                        left: t.cx - (t.width * s) / 2,
                        top: t.cy - Math.max(TABLE_DEPTH * s, 44) / 2,
                        width: t.width * s,
                        height: Math.max(TABLE_DEPTH * s, 44),
                      }}
                      onClick={() => onTable(t.table.id)}
                    />
                  )}
                  {(isFocused || (seatsTappable && !focused)) &&
                    t.seats.map((p) => {
                      const hit = Math.max(CHAIR * s, 44 / camera.k)
                      const mark = markBySeat.get(p.seat.id)
                      return (
                        <button
                          key={p.seat.id}
                          type="button"
                          className={styles.seatHit}
                          aria-label={seatName(t.table.label, p.seat.position, p.seat.state as PublicState, mark)}
                          aria-pressed={p.seat.id === selectedSeatId}
                          style={{ left: t.cx + p.x * s - hit / 2, top: t.cy + p.y * s - hit / 2, width: hit, height: hit }}
                          onClick={() => onSeat(p.seat.id)}
                        />
                      )
                    })}
                  {t.seats
                    .filter((p) => markBySeat.has(p.seat.id))
                    .map((p) => (
                      <span
                        key={`tag-${p.seat.id}`}
                        className={styles.tag}
                        aria-hidden
                        style={{
                          left: t.cx + p.x * s,
                          top: t.cy + (p.y + (p.side === 'top' ? -1 : 1) * (CHAIR / 2 + CHAIR_GAP + 14)) * s,
                          transform: `translate(-50%, -50%) scale(${1 / camera.k})`,
                        }}
                      >
                        {markBySeat.get(p.seat.id)}
                      </span>
                    ))}
                </div>
              )
            })}
          </div>
          {detail && tables.length === 0 && <p className={styles.empty}>No tables on this floor.</p>}
        </>
      )}
    </div>
  )
}
