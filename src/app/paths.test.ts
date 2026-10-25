import { describe, expect, it } from 'vitest'
import { parentOf } from './parent'
import { parseFloor, safeNext } from './paths'

describe('safeNext', () => {
  it('only follows paths inside the app after login', () => {
    expect(safeNext('/find')).toBe('/find')
    expect(safeNext('//evil.example')).toBe('/')
    expect(safeNext('https://evil.example')).toBe('/')
    expect(safeNext(null)).toBe('/')
  })
})

describe('parseFloor', () => {
  it('accepts floor numbers and rejects anything else', () => {
    expect(parseFloor('2')).toBe(2)
    expect(parseFloor('2a')).toBeNull()
    expect(parseFloor('history')).toBeNull()
  })
})

describe('parentOf', () => {
  it('goes up one level from a deep link instead of leaving the app', () => {
    expect(parentOf('/b/pcl/2/pcl-2-t1')).toBe('/b/pcl/2')
    expect(parentOf('/seat/t1-s1/host')).toBe('/seat/t1-s1')
    expect(parentOf('/seat/t1-s1')).toBe('/')
    expect(parentOf('/match/abc')).toBe('/')
  })
})
