import { describe, expect, it } from 'vitest'
import { ApiError } from './client'
import { pollDelay } from './poll'

const noJitter = () => 0.5 // factor 0.8 + 0.5 * 0.4 = 1

describe('pollDelay', () => {
  it('polls every POLL_WEB_S while healthy', () => {
    expect(pollDelay(0, null, noJitter)).toBe(3000)
  })
  it('doubles per failure and caps at 30 s', () => {
    expect(pollDelay(1, null, noJitter)).toBe(6000)
    expect(pollDelay(2, null, noJitter)).toBe(12000)
    expect(pollDelay(9, null, noJitter)).toBe(30000)
  })
  it("never retries sooner than the server's Retry-After", () => {
    const error = new ApiError(503, 'database_unavailable', 'down', 20000)
    expect(pollDelay(1, error, noJitter)).toBe(20000)
  })
})
