import { Navigation, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router'
import { useBuildings, useRecommendation } from '../../api/queries'
import type { BuildingDetail } from '../../api/types'
import { paths } from '../../app/paths'
import { Button } from '../../ui/Button'
import { ErrorNote } from '../../ui/Notes'
import { StateGlyph } from '../../ui/StateGlyph'
import s from '../../ui/screen.module.css'
import { seatAt } from './find'
import styles from './Recommendation.module.css'

type Props = { buildingId: string; detail: BuildingDetail; floor: number; tableId?: string | undefined }

/** FR-11/12: one seat for the current selection, widening table → floor → building. */
export function Recommendation({ buildingId, detail, floor, tableId }: Props) {
  const navigate = useNavigate()
  const rec = useRecommendation(buildingId, detail, floor, tableId)
  const buildings = useBuildings()

  if (rec.isError) return <ErrorNote error={rec.error} onRetry={() => void rec.refetch()} />
  if (!rec.data) return null

  if ('full' in rec.data) {
    const nearestId = rec.data.nearest_building_id
    const nearest = buildings.data?.find((b) => b.id === nearestId)
    return (
      <div className={styles.card}>
        <p className={styles.headline}>{detail.name} is full right now.</p>
        {nearestId ? (
          <Button variant="primary" block onClick={() => navigate(paths.building(nearestId))}>
            <Navigation size={18} aria-hidden />
            Go to {nearest?.name ?? 'the nearest building'} · {nearest?.open ?? ''} open
          </Button>
        ) : (
          <p className={`${s.small} ${s.muted}`}>No building has an open seat at the moment.</p>
        )}
      </div>
    )
  }

  const r = rec.data
  const at = seatAt(detail, r.seat_id)
  const where = at ? `${at.table.label} · seat ${at.seat.position}` : 'A seat'
  const likely = r.kind === 'likely_opening'
  const scope =
    r.level === 'table' ? 'at this table' : r.level === 'floor' ? 'on this floor' : r.floor === floor ? 'on this floor' : `on floor ${r.floor}`
  const here = r.floor === floor && (tableId === undefined || r.table_id === tableId)

  return (
    <div className={styles.card}>
      <p className={s.eyebrow}>
        <Sparkles size={14} aria-hidden /> Best seat {scope}
      </p>
      <div className={styles.seatLine}>
        <StateGlyph state="foryou" size={20} />
        <span className={styles.headline}>{where}</span>
        {r.floor !== floor && <span className={s.tag}>FLOOR {r.floor}</span>}
      </div>
      <p className={`${s.small} ${s.muted}`}>
        {likely
          ? 'Nothing is open, so this is the seat most likely to free up: belongings left, nobody there.'
          : r.level === 'table'
            ? 'Open at the table you picked.'
            : r.level === 'floor'
              ? tableId
                ? 'That table is full, so this is the nearest open seat on the floor.'
                : 'Open, and nearest to where you are looking.'
              : 'This floor is full, so this is the closest open seat in the building.'}
      </p>
      {!here || tableId !== r.table_id ? (
        <Button variant="secondary" block onClick={() => navigate(paths.table(buildingId, r.floor, r.table_id))}>
          Show me
        </Button>
      ) : null}
    </div>
  )
}
