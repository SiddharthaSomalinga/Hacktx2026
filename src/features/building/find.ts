import type { BuildingDetail, PublicState, Seat, Table } from '../../api/types'

export type SeatAt = { seat: Seat; table: Table; floor: number }

export function seatAt(detail: BuildingDetail | undefined, seatId: string | undefined): SeatAt | null {
  if (!detail || !seatId) return null
  for (const f of detail.floors)
    for (const t of f.tables) {
      const seat = t.seats.find((s) => s.id === seatId)
      if (seat) return { seat, table: t, floor: f.floor }
    }
  return null
}

export function countStates(seats: Seat[]): Record<PublicState, number> {
  const counts: Record<PublicState, number> = { open: 0, occupied: 0, likely_opening: 0, offline: 0 }
  for (const s of seats) counts[s.state] += 1
  return counts
}

export const floorSeats = (detail: BuildingDetail, floor: number) =>
  detail.floors.find((f) => f.floor === floor)?.tables.flatMap((t) => t.seats) ?? []
