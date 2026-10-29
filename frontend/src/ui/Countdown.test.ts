import { describe, expect, it } from 'vitest'
import { remainingAt } from './Countdown'

describe('remainingAt', () => {
  it('counts down from the fetch, not from the first time the number was seen', () => {
    const firstFetch = 1_000_000
    expect(remainingAt(300, firstFetch, firstFetch + 290_000)).toBe(10)
    // The next request reports 300 again; only its fetch time tells the two apart.
    const nextFetch = firstFetch + 295_000
    expect(remainingAt(300, nextFetch, nextFetch + 1_000)).toBe(299)
  })

  it('never goes below zero', () => {
    expect(remainingAt(5, 0, 60_000)).toBe(0)
  })
})
