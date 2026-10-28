import { describe, expect, it } from 'vitest'
import type { Seat, Table } from '../api/types'
import { layoutFloor, placeSeats } from './layout'

const seats = (n: number): Seat[] => Array.from({ length: n }, (_, i) => ({ id: `s${i + 1}`, position: i + 1, state: 'open' }))
const table = (id: string, x: number, y: number, n = 6): Table => ({ id, label: id, x, y, seats: seats(n) })

// The seeded floors (backend/sql/seed.sql).
const FLOORS: Record<string, Table[]> = {
  'pcl-2': [table('t1', 25, 30, 2), table('t2', 60, 30), table('t3', 25, 70), table('t4', 60, 70)],
  'pcl-3': [table('t1', 30, 35), table('t2', 70, 35), table('t3', 50, 75)],
  'wel-1': [table('t1', 20, 30), table('t2', 55, 30), table('t3', 20, 70), table('t4', 55, 70)],
  'wel-2': [table('t1', 30, 40), table('t2', 70, 40)],
  'gdc-3': [table('t1', 20, 35), table('t2', 50, 35), table('t3', 80, 35), table('t4', 50, 75)],
}

describe('placeSeats', () => {
  it('numbers chairs clockwise: top left to right, then bottom right to left', () => {
    const placed = placeSeats(seats(6)).seats
    expect(placed.map((p) => p.side)).toEqual(['top', 'top', 'top', 'bottom', 'bottom', 'bottom'])
    expect(placed[0]!.x).toBeLessThan(placed[2]!.x)
    expect(placed[3]!.x).toBeGreaterThan(placed[5]!.x)
  })
  it('seats two people opposite each other', () => {
    const [a, b] = placeSeats(seats(2)).seats
    expect(a!.side).toBe('top')
    expect(b!.side).toBe('bottom')
    expect(a!.x).toBe(b!.x)
  })
  it('orders by position, not by array order', () => {
    const shuffled = [seats(3)[2]!, seats(3)[0]!, seats(3)[1]!]
    expect(placeSeats(shuffled).seats.map((p) => p.seat.position)).toEqual([1, 2, 3])
  })
})

describe('layoutFloor', () => {
  const areas = { phone: { left: 30, top: 30, width: 306, height: 520 }, desktop: { left: 30, top: 30, width: 1100, height: 700 } }
  for (const [name, tables] of Object.entries(FLOORS)) {
    for (const [device, area] of Object.entries(areas)) {
      it(`keeps ${name} tables apart and inside the frame on a ${device}`, () => {
        const { tables: placed, scale } = layoutFloor(tables, area)
        const boxes = placed.map((t) => ({
          l: t.cx - (t.width * scale) / 2,
          r: t.cx + (t.width * scale) / 2,
          t: t.cy - (t.height * scale) / 2,
          b: t.cy + (t.height * scale) / 2,
        }))
        for (const box of boxes) {
          expect(box.l).toBeGreaterThanOrEqual(area.left - 0.01)
          expect(box.r).toBeLessThanOrEqual(area.left + area.width + 0.01)
        }
        for (let i = 0; i < boxes.length; i++)
          for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i]!
            const b = boxes[j]!
            const overlap = a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b
            expect(overlap).toBe(false)
          }
      })
    }
  }
})
