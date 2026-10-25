import { LIVE_FOR_MS } from '../config'

export type Freshness =
  | { kind: 'loading' }
  | { kind: 'live' }
  | { kind: 'aging'; ageMs: number }
  | { kind: 'stale'; ageMs: number }
  | { kind: 'offline'; ageMs: number | null }

/**
 * How current the map data is, from the client's last successful poll (D46). This is the age of
 * the snapshot, never how long any seat has been in its state (FR-6).
 */
export function freshness(input: {
  updatedAt: number
  failed: boolean
  unavailable: boolean
  online: boolean
  now: number
}): Freshness {
  const { updatedAt, failed, unavailable, online, now } = input
  const ageMs = updatedAt > 0 ? Math.max(0, now - updatedAt) : null
  if (!online || unavailable) return { kind: 'offline', ageMs }
  if (ageMs === null) return { kind: 'loading' }
  if (failed) return { kind: 'stale', ageMs }
  if (ageMs < LIVE_FOR_MS) return { kind: 'live' }
  return { kind: 'aging', ageMs }
}

export function ageText(ms: number): string {
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s} s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  return `${Math.round(m / 60)} h ago`
}

/** A short label that always fits, and the detail shown when there is room. */
export function freshnessText(f: Freshness): { label: string; detail: string } {
  switch (f.kind) {
    case 'loading':
      return { label: 'Connecting…', detail: '' }
    case 'live':
      return { label: 'Live', detail: '' }
    case 'aging':
      return { label: `Updated ${ageText(f.ageMs)}`, detail: '' }
    case 'stale':
      return { label: 'Unable to refresh', detail: ` · updated ${ageText(f.ageMs)}` }
    case 'offline':
      return { label: 'Offline', detail: f.ageMs === null ? '' : ` · data from ${ageText(f.ageMs)}` }
  }
}
