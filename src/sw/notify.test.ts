import { describe, expect, it } from 'vitest'
import { clickTarget, parsePayload } from './notify'

describe('notification click targets', () => {
  it('opens the screens the backend links to', () => {
    expect(clickTarget('/host')).toBe('/host')
    expect(clickTarget('/match/8f0c-1a')).toBe('/match/8f0c-1a')
    expect(clickTarget('/search/abc')).toBe('/search/abc')
  })
  it('refuses anything that could leave the app', () => {
    for (const url of ['//evil.example', 'https://evil.example/host', 'javascript:alert(1)', '/match/../../x', 5, null])
      expect(clickTarget(url)).toBe('/')
  })
})

describe('push payloads', () => {
  it('shows a generic notification for a malformed payload instead of throwing', () => {
    expect(parsePayload('not json').title).toBe('Ghost Seats')
    expect(parsePayload(null).url).toBe('/')
  })
  it('keeps the backend fields', () => {
    const shown = parsePayload(JSON.stringify({ title: 'New study request', body: 'Priya · Chemistry wants…', url: '/host' }))
    expect(shown).toEqual({ title: 'New study request', body: 'Priya · Chemistry wants…', url: '/host' })
  })
})
