import { describe, expect, it } from 'vitest'
import { LIVE_FOR_MS } from '../config'
import {
  etagsOf,
  initialLive,
  isSilent,
  liveReducer,
  liveUrl,
  pollingFor,
  reconnectDelay,
  seatFromDetail,
  topicsOf,
  type LiveInput,
  type LiveState,
} from './live'
import type { BuildingDetail, SeatLookup } from './types'

function run(inputs: [number, LiveInput][]): LiveState {
  return inputs.reduce((s, [at, input]) => liveReducer(s, input, at), initialLive)
}

const healthy = run([
  [1_000, { type: 'connecting', building: 'pcl' }],
  [1_100, { type: 'opened' }],
  [1_150, { type: 'snapshot' }],
])

describe('pollingFor', () => {
  it('does not poll while the stream is healthy, for the buildings list and its building', () => {
    expect(pollingFor(healthy, 2_000)).toEqual({ map: false, user: false })
    expect(pollingFor(healthy, 2_000, 'pcl')).toEqual({ map: false, user: false })
  })

  it('polls a building the stream does not carry', () => {
    expect(pollingFor(healthy, 2_000, 'gdc').map).toBe(true)
  })

  it('gives the first connect LIVE_FOR_MS before polling', () => {
    const booting = liveReducer(initialLive, { type: 'connecting', building: null }, 1_000)
    expect(pollingFor(booting, 1_000 + LIVE_FOR_MS - 1).map).toBe(false)
    expect(pollingFor(booting, 1_000 + LIVE_FOR_MS).map).toBe(true)
  })

  it('rides out a short drop, then polls once the data would look old', () => {
    const dropped = liveReducer(healthy, { type: 'failed' }, 3_000)
    expect(pollingFor(dropped, 1_150 + LIVE_FOR_MS - 1)).toEqual({ map: false, user: false })
    expect(pollingFor(dropped, 1_150 + LIVE_FOR_MS)).toEqual({ map: true, user: true })
  })

  it('keeps pings fresh only while the server vouches for the data', () => {
    const pinged = liveReducer(healthy, { type: 'ping', db: true, hints: true }, 5_000)
    expect(pollingFor(pinged, 5_000 + LIVE_FOR_MS - 1).map).toBe(false)
    const failing = liveReducer(pinged, { type: 'ping', db: false, hints: true }, 8_000)
    expect(pollingFor(failing, 5_000 + LIVE_FOR_MS).map).toBe(true) // aged from the last good ping
  })

  it('polls per-user state while hints are not arriving, but not the map', () => {
    const deaf = liveReducer(healthy, { type: 'ping', db: true, hints: false }, 2_000)
    expect(pollingFor(deaf, 2_500)).toEqual({ map: false, user: true })
  })

  it('never polls while the app is hidden', () => {
    const hidden = liveReducer(healthy, { type: 'hidden' }, 2_000)
    expect(pollingFor(hidden, 60_000)).toEqual({ map: false, user: false })
  })
})

describe('isSilent', () => {
  it('flags an open stream that has gone quiet, counting unhealthy pings as messages', () => {
    const failing = liveReducer(healthy, { type: 'ping', db: false, hints: true }, 5_000)
    expect(isSilent(failing, 5_000 + LIVE_FOR_MS - 1)).toBe(false)
    expect(isSilent(failing, 5_000 + LIVE_FOR_MS)).toBe(true)
  })
})

describe('reconnectDelay', () => {
  it('doubles from 1 s to 30 s, with ±50% jitter', () => {
    const mid = () => 0.5
    expect([0, 1, 2, 5, 9].map((n) => reconnectDelay(n, mid))).toEqual([1000, 2000, 4000, 30000, 30000])
    expect(reconnectDelay(0, () => 0)).toBe(500)
    expect(reconnectDelay(0, () => 0.999)).toBe(1499)
  })
})

describe('urls, ids and topics', () => {
  it('builds the stream url', () => {
    expect(liveUrl(null, null)).toBe('/api/live')
    expect(liveUrl('pcl', 'ab.cd')).toBe('/api/live?building=pcl&last_event_id=ab.cd')
  })

  it('reads the ETags back out of an event id', () => {
    expect(etagsOf('ab12.cd34')).toEqual({ buildings: '"ab12"', building: '"cd34"' })
    expect(etagsOf('ab12.-')).toEqual({ buildings: '"ab12"', building: null })
  })

  it('keeps only known topic names, and survives garbage', () => {
    expect(topicsOf('["me","inbox","nope"]')).toEqual(['me', 'inbox'])
    expect(topicsOf('{"me":1}')).toEqual([])
    expect(topicsOf('not json')).toEqual([])
  })
})

describe('seatFromDetail', () => {
  const seat: SeatLookup = { id: 't1-s1', building_id: 'pcl', floor: 2, table_id: 'pcl-2-t1', table_label: 'Table 01', position: 1, state: 'open' }
  const detail = (state: SeatLookup['state']): BuildingDetail => ({
    id: 'pcl',
    name: 'PCL',
    is_simulated: false,
    floors: [{ floor: 2, tables: [{ id: 'pcl-2-t1', label: 'Table 01', x: 1, y: 1, seats: [{ id: 't1-s1', position: 1, state }] }] }],
  })

  it('takes the newer state from the floor plan', () => {
    expect(seatFromDetail(seat, detail('occupied')).state).toBe('occupied')
  })

  it('returns the same object when nothing changed, or the plan is another building', () => {
    expect(seatFromDetail(seat, detail('open'))).toBe(seat)
    expect(seatFromDetail(seat, { ...detail('occupied'), id: 'gdc' })).toBe(seat)
  })
})
