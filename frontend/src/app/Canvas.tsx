import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useBuilding, useBuildings } from '../api/queries'
import { CampusMap } from '../map/CampusMap'
import { FloorPlan } from '../plan/FloorPlan'
import { session } from '../lib/storage'
import { useFocusState } from './focus'
import { paths } from './paths'
import styles from './Canvas.module.css'

/** Draw-in plays once per building per visit, and never over data that was already on screen. */
function useFirstDraw(key: string, hasCachedData: boolean): boolean {
  const [first] = useState(() => {
    const seen = session.getItem(`gs-drawn:${key}`) !== null
    if (!seen) session.setItem(`gs-drawn:${key}`, '1')
    return !seen && !hasCachedData
  })
  return first
}

function Plan({ buildingId, floor, tableId, selectedSeatId, marks }: {
  buildingId: string
  floor: number | null
  tableId?: string | undefined
  selectedSeatId?: string | undefined
  marks: { seatId: string; label: string }[]
}) {
  const navigate = useNavigate()
  const detail = useBuilding(buildingId)
  const animate = useFirstDraw(buildingId, detail.data !== undefined)
  const shownFloor = floor ?? detail.data?.floors[0]?.floor ?? null
  return (
    <div className={styles.plan} key={buildingId}>
      <FloorPlan
        detail={detail.data}
        floor={shownFloor ?? 0}
        tableId={tableId}
        selectedSeatId={selectedSeatId}
        marks={marks}
        animate={animate}
        onTable={(id) => shownFloor !== null && navigate(paths.table(buildingId, shownFloor, id))}
        onSeat={(id) => navigate(paths.seat(id))}
      />
    </div>
  )
}

export function Canvas() {
  const { focus } = useFocusState()
  const navigate = useNavigate()
  const buildings = useBuildings(focus.kind === 'campus')
  const animate = useFirstDraw('campus', buildings.data !== undefined)
  const onPlan = focus.kind === 'plan'
  return (
    <div className={styles.canvas}>
      <div className={`${styles.campus} ${onPlan ? styles.behind : ''}`} aria-hidden={onPlan}>
        <CampusMap
          buildings={buildings.data}
          badges={focus.kind === 'campus' ? focus.badges : undefined}
          animate={animate}
          onBuilding={(id) => navigate(paths.building(id))}
        />
      </div>
      {focus.kind === 'plan' && (
        <Plan
          buildingId={focus.buildingId}
          floor={focus.floor}
          tableId={focus.tableId}
          selectedSeatId={focus.selectedSeatId}
          marks={focus.marks ?? []}
        />
      )}
    </div>
  )
}
