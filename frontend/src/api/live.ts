import { LIVE_FOR_MS, MAX_BACKOFF_MS } from '../config'
import type { BuildingDetail, SeatLookup } from './types'

/**
 * The live stream's state, as plain data (D61). `lastGood` is when a message last vouched for
 * the data (a snapshot, or a ping with `db: true`). Queries poll exactly when that is older
 * than LIVE_FOR_MS, the moment the freshness pill would stop saying "Live" (D46): a blip
 * shorter than that costs no requests, and a stream that fails is replaced by polling as soon
 * as the data would look old.
 */
export type LiveState = {
  status: 'connecting' | 'open' | 'down' | 'hidden'
  lastGood: number
  lastEventAt: number // any message, for the watchdog that replaces a silent connection
  db: boolean // the server rebuilt its snapshots fine (a ping's `db`)
  hints: boolean // per-user hints are arriving (a ping's `hints`)
  building: string | null // the floor plan this stream carries, besides the buildings list
}

export type LiveInput =
  | { type: 'connecting'; building: string | null }
  | { type: 'opened' }
  | { type: 'snapshot' }
  | { type: 'invalidate' }
  | { type: 'ping'; db: boolean; hints: boolean }
  | { type: 'failed' }
  | { type: 'hidden' }

export const initialLive: LiveState = {
  status: 'connecting',
  lastGood: 0,
  lastEventAt: 0,
  db: true,
  hints: true,
  building: null,
}

export function liveReducer(state: LiveState, input: LiveInput, now: number): LiveState {
  switch (input.type) {
    case 'connecting':
      // The first connect gets the same grace as a blip: the snapshots arrive within it.
      return { ...state, status: 'connecting', building: input.building, lastGood: state.lastGood || now }
    case 'opened':
      return { ...state, status: 'open', lastEventAt: now }
    case 'snapshot':
      return { ...state, lastGood: now, lastEventAt: now, db: true }
    case 'invalidate':
      return { ...state, lastEventAt: now }
    case 'ping':
      return { ...state, lastEventAt: now, db: input.db, hints: input.hints, lastGood: input.db ? now : state.lastGood }
    case 'failed':
      return { ...state, status: 'down' }
    case 'hidden':
      return { ...state, status: 'hidden' }
  }
}

/**
 * Which queries must poll at `now`. `building` is the building a map query needs: the stream
 * carries only the one in focus. Per-user queries also poll while hints are not arriving,
 * since then nothing would tell them to refetch.
 */
export function pollingFor(state: LiveState, now: number, building?: string | null): { map: boolean; user: boolean } {
  if (state.status === 'hidden') return { map: false, user: false }
  const stale = now - state.lastGood >= LIVE_FOR_MS
  const covered = building === undefined || building === state.building
  return { map: stale || !covered, user: stale || (state.status === 'open' && !state.hints) }
}

/** An open stream that has said nothing for this long is replaced (a half-open connection). */
export function isSilent(state: LiveState, now: number): boolean {
  return state.status === 'open' && now - state.lastEventAt >= LIVE_FOR_MS
}

/** When the stream should try again: like failed polls, doubling to 30 s, with jitter. */
export function reconnectDelay(attempt: number, random = Math.random): number {
  return Math.round(Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS) * (0.5 + random()))
}

export function liveUrl(building: string | null, lastEventId: string | null): string {
  const query = new URLSearchParams()
  if (building) query.set('building', building)
  if (lastEventId) query.set('last_event_id', lastEventId)
  const text = query.toString()
  return text ? `/api/live?${text}` : '/api/live'
}

/** The ETag each half of an event id stands for (`<buildings>.<building>`, `-` for none). */
export function etagsOf(eventId: string): { buildings: string | null; building: string | null } {
  const [a, b] = eventId.split('.')
  const tag = (v: string | undefined) => (v && v !== '-' ? `"${v}"` : null)
  return { buildings: tag(a), building: tag(b) }
}

export const USER_TOPICS = ['me', 'search', 'inbox', 'match'] as const
export type UserTopic = (typeof USER_TOPICS)[number]

/** An invalidate event's topics, keeping only names this client knows. */
export function topicsOf(data: string): UserTopic[] {
  try {
    const parsed: unknown = JSON.parse(data)
    return Array.isArray(parsed) ? USER_TOPICS.filter((t) => parsed.includes(t)) : []
  } catch {
    return []
  }
}

/** A seat's lookup with its state taken from a newer floor plan, or unchanged if absent. */
export function seatFromDetail(seat: SeatLookup, detail: BuildingDetail): SeatLookup {
  if (detail.id !== seat.building_id) return seat
  for (const floor of detail.floors) {
    for (const table of floor.tables) {
      const found = table.seats.find((s) => s.id === seat.id)
      if (found) return found.state === seat.state ? seat : { ...seat, state: found.state }
    }
  }
  return seat
}
