// Pure geometry for the floor plan. Only what the API gives is drawn: tables at their x/y
// (percent of the floor canvas) and chairs by position around them (D45). No walls, no scale.
import type { Seat, Table } from '../api/types'

export const CHAIR = 30
export const PITCH = 38
export const TABLE_DEPTH = 40
export const CHAIR_GAP = 6

export type Box = { left: number; top: number; width: number; height: number }

export type PlacedSeat = { seat: Seat; x: number; y: number; side: 'top' | 'bottom' }
export type PlacedTable = { table: Table; cx: number; cy: number; width: number; height: number; seats: PlacedSeat[] }
export type PlanLayout = { tables: PlacedTable[]; scale: number }

/** Chairs split across the two long sides, numbered clockwise: top left→right, bottom right→left. */
export function placeSeats(seats: Seat[]): { width: number; height: number; seats: PlacedSeat[] } {
  const sorted = [...seats].sort((a, b) => a.position - b.position)
  const topCount = Math.ceil(sorted.length / 2)
  const bottomCount = sorted.length - topCount
  const cols = Math.max(topCount, 1)
  const width = cols * PITCH + 10
  const offset = TABLE_DEPTH / 2 + CHAIR_GAP + CHAIR / 2
  const placed = sorted.map((seat, i): PlacedSeat => {
    if (i < topCount) return { seat, x: (i - (topCount - 1) / 2) * PITCH, y: -offset, side: 'top' }
    const j = i - topCount
    return { seat, x: ((bottomCount - 1) / 2 - j) * PITCH, y: offset, side: 'bottom' }
  })
  return { width, height: TABLE_DEPTH + 2 * (CHAIR_GAP + CHAIR), seats: placed }
}

const MARGIN = 18

/**
 * Places every table at its x/y inside `area` and finds one uniform scale at which no two tables
 * overlap and none crosses the edge. Glyphs are never stretched, whatever the area's aspect ratio.
 */
export function layoutFloor(tables: Table[], area: Box, maxScale = 1.5): PlanLayout {
  const placed = tables.map((table) => {
    const glyph = placeSeats(table.seats)
    return {
      table,
      cx: area.left + (table.x / 100) * area.width,
      cy: area.top + (table.y / 100) * area.height,
      width: glyph.width,
      height: glyph.height,
      seats: glyph.seats,
    }
  })
  let scale = maxScale
  for (const t of placed) {
    scale = Math.min(
      scale,
      (t.cx - area.left) / (t.width / 2),
      (area.left + area.width - t.cx) / (t.width / 2),
      (t.cy - area.top) / (t.height / 2),
      (area.top + area.height - t.cy) / (t.height / 2),
    )
  }
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i]!
      const b = placed[j]!
      const fitX = (Math.abs(a.cx - b.cx) - MARGIN) / ((a.width + b.width) / 2)
      const fitY = (Math.abs(a.cy - b.cy) - MARGIN) / ((a.height + b.height) / 2)
      scale = Math.min(scale, Math.max(fitX, fitY))
    }
  }
  return { tables: placed, scale: Math.max(0.4, scale) }
}

/** The camera transform that brings one table to fill most of the area. */
export function zoomTo(table: PlacedTable, scale: number, area: Box): { x: number; y: number; k: number } {
  const w = table.width * scale
  const h = table.height * scale
  const k = Math.min(3.2, (area.width * 0.72) / w, (area.height * 0.7) / h)
  const x = area.left + area.width / 2 - table.cx * k
  const y = area.top + area.height / 2 - table.cy * k
  return { x, y, k }
}
