import type { PublicState } from '../api/types'

const WORDS: Record<PublicState, string> = {
  open: 'open',
  occupied: 'occupied',
  likely_opening: 'likely opening',
  offline: 'no signal',
}

/** The accessible name of a chair: where it is and its state, e.g. "Table 01 seat 2, likely opening". */
export function seatName(tableLabel: string, position: number, state: PublicState, mark?: string): string {
  return `${tableLabel} seat ${position}, ${WORDS[state]}${mark ? `, ${mark.toLowerCase()}` : ''}`
}

export function tableName(tableLabel: string, states: PublicState[]): string {
  const open = states.filter((s) => s === 'open').length
  return `${tableLabel}, ${open} of ${states.length} seats open`
}
