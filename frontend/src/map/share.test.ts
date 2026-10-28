import { describe, expect, it } from 'vitest'
import { shareOf } from './share'

const b = (open: number, total: number, offline = 0) => ({ open, total, offline })

describe('FR-8 open share (D51)', () => {
  it('splits at exactly 10% and 30%', () => {
    expect(shareOf(b(999, 10000))).toBe('low')
    expect(shareOf(b(10, 100))).toBe('mid')
    expect(shareOf(b(2999, 10000))).toBe('mid')
    expect(shareOf(b(30, 100))).toBe('high')
  })
  it('judges a building by the seats that report, not by offline ones', () => {
    // 3 open of 10, but 5 are offline: 3 / 5 = 60%, not 30%.
    expect(shareOf(b(3, 10, 5))).toBe('high')
  })
  it('is grey only when every seat is offline', () => {
    expect(shareOf(b(0, 6, 6))).toBe('none')
    expect(shareOf(b(0, 6, 5))).toBe('low')
  })
})
