import { useState } from 'react'
import { useParams } from 'react-router'
import { useBuilding, useHistory } from '../../api/queries'
import type { HistoryPoint } from '../../api/types'
import { useCanvas } from '../../app/focus'
import { centralHour } from '../../lib/clock'
import { Button } from '../../ui/Button'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, InfoNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import styles from './HistoryScreen.module.css'

function niceMax(n: number): number {
  if (n <= 5) return 5
  const step = 10 ** Math.floor(Math.log10(n))
  return Math.ceil(n / step) * step
}

/** FR-49: hourly average of open seats, last 24 hours, in Central Time (NFR-5). Real points only. */
function Chart({ points }: { points: HistoryPoint[] }) {
  const [active, setActive] = useState<number | null>(null)
  const max = niceMax(Math.max(...points.map((p) => p.open_avg)))
  const W = 340
  const H = 160
  const barW = W / points.length
  const peak = points.reduce((best, p, i) => (p.open_avg > (points[best]?.open_avg ?? -1) ? i : best), 0)
  const shown = active ?? points.length - 1
  const focus = points[shown]
  return (
    <figure className={styles.figure}>
      <div className={styles.readout} aria-live="polite">
        <span className="mono">{focus ? Math.round(focus.open_avg) : '–'}</span>
        <span className={`${s.small} ${s.muted}`}>
          open on average at {focus ? centralHour(focus.hour) : ''}
          {shown === points.length - 1 ? ' (this hour so far)' : ''}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H + 22}`} className={styles.svg} role="img" aria-label="Open seats per hour, last 24 hours">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line className={styles.gridline} x1={0} x2={W} y1={H - f * H} y2={H - f * H} />
            <text className={styles.axis} x={W} y={H - f * H - 3} textAnchor="end">
              {Math.round(f * max)}
            </text>
          </g>
        ))}
        {points.map((p, i) => {
          const h = (p.open_avg / max) * H
          return (
            <g key={p.hour}>
              <rect
                className={`${styles.bar} ${i === shown ? styles.barActive : ''} ${i === points.length - 1 ? styles.partial : ''}`}
                x={i * barW + 1}
                y={H - h}
                width={Math.max(1, barW - 2)}
                height={Math.max(h, 0.5)}
                rx={2}
              />
              <rect
                className={styles.hit}
                x={i * barW}
                y={0}
                width={barW}
                height={H}
                onPointerEnter={() => setActive(i)}
                onClick={() => setActive(i)}
              />
            </g>
          )
        })}
        {[0, 6, 12, 18, points.length - 1].map((i) =>
          points[i] ? (
            <text key={i} className={styles.axis} x={i * barW + barW / 2} y={H + 16} textAnchor="middle">
              {i === points.length - 1 ? 'now' : centralHour(points[i].hour)}
            </text>
          ) : null,
        )}
        {points[peak] && peak !== shown && (
          <text className={styles.peak} x={peak * barW + barW / 2} y={H - (points[peak].open_avg / max) * H - 5} textAnchor="middle">
            peak
          </text>
        )}
      </svg>
      <figcaption className={`${s.small} ${s.muted}`}>Times in Central Time. Tap a bar for that hour.</figcaption>
    </figure>
  )
}

export function HistoryScreen() {
  const { buildingId = '' } = useParams()
  usePanelSnap('full')
  useCanvas({ kind: 'plan', buildingId, floor: null })
  const detail = useBuilding(buildingId)
  const history = useHistory(buildingId)
  const [table, setTable] = useState(false)

  const points = history.data ?? []
  const empty = points.length > 0 && points.every((p) => p.open_avg === 0)

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>{detail.data?.name.toUpperCase() ?? buildingId.toUpperCase()} · LAST 24 HOURS</p>
        <h1 className={s.title}>Open seats by hour</h1>
      </header>
      {history.isError ? (
        <ErrorNote error={history.error} onRetry={() => void history.refetch()} />
      ) : !history.data ? (
        <Loading label="Loading the last 24 hours…" />
      ) : empty ? (
        <InfoNote>No open seats were recorded here in the last 24 hours. Either the sensors were not reporting or every seat was taken.</InfoNote>
      ) : table ? (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Hour (CT)</th>
              <th scope="col">Open on average</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.hour}>
                <td>{centralHour(p.hour)}</td>
                <td className="mono">{p.open_avg.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Chart points={points} />
      )}
      {history.data && !empty && (
        <Button variant="quiet" onClick={() => setTable((t) => !t)}>
          {table ? 'Show as chart' : 'Show as table'}
        </Button>
      )}
    </div>
  )
}
