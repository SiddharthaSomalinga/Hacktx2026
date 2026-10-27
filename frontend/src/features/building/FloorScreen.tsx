import { BarChart3, ChevronRight } from 'lucide-react'
import { useEffect } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { useBuilding, useRecommendation } from '../../api/queries'
import type { PublicState } from '../../api/types'
import { useCanvas, type SeatMark } from '../../app/focus'
import { parseFloor, paths } from '../../app/paths'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, Loading } from '../../ui/Notes'
import { StateGlyph, STATE_WORDS } from '../../ui/StateGlyph'
import s from '../../ui/screen.module.css'
import { countStates, floorSeats } from './find'
import { Recommendation } from './Recommendation'
import styles from './FloorScreen.module.css'

const ORDER: PublicState[] = ['open', 'likely_opening', 'occupied', 'offline']

/** /b/:id picks the floor with the most open seats and replaces itself, so Back skips it. */
export function BuildingRedirect() {
  const { buildingId = '' } = useParams()
  const detail = useBuilding(buildingId)
  useCanvas({ kind: 'plan', buildingId, floor: null })
  if (detail.isError) return <ErrorNote error={detail.error} onRetry={() => void detail.refetch()} />
  if (!detail.data) return <Loading label="Opening the floor plan…" />
  const best = [...detail.data.floors].sort(
    (a, b) => countStates(b.tables.flatMap((t) => t.seats)).open - countStates(a.tables.flatMap((t) => t.seats)).open,
  )[0]
  if (!best) return <ErrorNote error={null} />
  return <Navigate to={paths.floor(buildingId, best.floor)} replace />
}

export function FloorScreen() {
  const { buildingId = '', floor: rawFloor, tableId } = useParams()
  const navigate = useNavigate()
  const floor = parseFloor(rawFloor)
  const detail = useBuilding(buildingId)
  const rec = useRecommendation(buildingId, detail.data, floor ?? undefined, tableId)
  usePanelSnap(tableId ? 'half' : 'half')

  const marks: SeatMark[] = []
  if (rec.data && !('full' in rec.data)) marks.push({ seatId: rec.data.seat_id, label: 'Best seat' })
  useCanvas({ kind: 'plan', buildingId, floor, tableId, marks })

  const floorExists = detail.data?.floors.some((f) => f.floor === floor)
  const table = detail.data?.floors.find((f) => f.floor === floor)?.tables.find((t) => t.id === tableId)
  useEffect(() => {
    // An unknown table in the URL drops back to the floor instead of showing nothing.
    if (detail.data && floorExists && tableId && !table && floor !== null) navigate(paths.floor(buildingId, floor), { replace: true })
  }, [detail.data, floorExists, tableId, table, floor, buildingId, navigate])

  if (detail.isError && !detail.data) return <ErrorNote error={detail.error} onRetry={() => void detail.refetch()} />
  if (!detail.data) return <Loading label="Opening the floor plan…" />
  if (floor === null || !floorExists) return <p className={s.muted}>This building has no floor {rawFloor}.</p>

  const d = detail.data
  const counts = countStates(table ? table.seats : floorSeats(d, floor))

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>{table ? `${d.name.toUpperCase()} · FLOOR ${floor}` : `FLOOR ${floor} · ${counts.open} OPEN`}</p>
        <h1 className={s.title}>
          {table ? table.label : d.name} {d.is_simulated && <span className={s.tag}>SIMULATED</span>}
        </h1>
        {d.is_simulated && <p className={`${s.small} ${s.muted}`}>Demo data: these seats are generated, not sensed.</p>}
      </header>

      {d.floors.length > 1 && (
        <nav aria-label="Floors" className={styles.floors}>
          {d.floors.map((f) => {
            const open = countStates(f.tables.flatMap((t) => t.seats)).open
            return (
              <Link
                key={f.floor}
                to={paths.floor(buildingId, f.floor)}
                replace
                className={styles.floor}
                aria-current={f.floor === floor ? 'page' : undefined}
              >
                <span className="mono">{f.floor}</span>
                <span className={s.small}>{open} open</span>
              </Link>
            )
          })}
        </nav>
      )}

      <Recommendation buildingId={buildingId} detail={d} floor={floor} tableId={tableId} />

      <section aria-label={table ? 'Seats at this table' : 'Seats on this floor'}>
        <ul className={styles.legend}>
          {ORDER.map((state) => (
            <li key={state}>
              <StateGlyph state={state} size={18} />
              <span>{STATE_WORDS[state]}</span>
              <span className={`mono ${styles.n}`}>{counts[state]}</span>
            </li>
          ))}
        </ul>
        <p className={`${s.small} ${s.muted} ${styles.hint}`}>
          {table ? 'Tap your chair to host from it.' : 'Tap a table to zoom in. Likely opening means belongings left with nobody there.'}
        </p>
      </section>

      {table && (
        <ul className={s.list} aria-label={`${table.label} seats`}>
          {table.seats.map((seat) => (
            <li key={seat.id}>
              <Link to={paths.seat(seat.id)} className={styles.seat}>
                <StateGlyph state={seat.state} size={20} />
                <span>Seat {seat.position}</span>
                <span className={s.muted}>{STATE_WORDS[seat.state]}</span>
                <ChevronRight size={18} aria-hidden className={styles.chevron} />
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Link to={paths.history(buildingId)} className={styles.history}>
        <BarChart3 size={18} aria-hidden />
        Open seats over the last 24 hours
        <ChevronRight size={18} aria-hidden className={styles.chevron} />
      </Link>
    </div>
  )
}
