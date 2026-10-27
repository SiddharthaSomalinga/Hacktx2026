import { describe, expect, it } from 'vitest'
import { freshness, freshnessText } from './freshness'

const base = { updatedAt: 1000, failed: false, unavailable: false, online: true }

describe('freshness (D46)', () => {
  it('is live only while the data is under two poll intervals old', () => {
    expect(freshness({ ...base, now: 6999 }).kind).toBe('live')
    expect(freshness({ ...base, now: 7000 }).kind).toBe('aging')
  })
  it('says it could not refresh instead of pretending to be live', () => {
    expect(freshness({ ...base, failed: true, now: 2000 }).kind).toBe('stale')
  })
  it('is offline when the network or database is down, and keeps the data age', () => {
    const f = freshness({ ...base, unavailable: true, failed: true, now: 61000 })
    expect(f).toEqual({ kind: 'offline', ageMs: 60000 })
    expect(freshnessText(f)).toEqual({ label: 'Offline', detail: ' · data from 1 min ago' })
  })
  it('is loading, not live, before any data arrives', () => {
    expect(freshness({ ...base, updatedAt: 0, now: 5 }).kind).toBe('loading')
  })
})
