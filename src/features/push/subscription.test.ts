import { describe, expect, it } from 'vitest'
import { subscribeBody } from './subscription'

describe('subscribeBody', () => {
  it('drops expirationTime, which the API rejects with a 422 (D50)', () => {
    const body = subscribeBody({ endpoint: 'https://push.example/x', expirationTime: null, keys: { p256dh: 'p', auth: 'a' } })
    expect(body).toEqual({ endpoint: 'https://push.example/x', keys: { p256dh: 'p', auth: 'a' } })
  })
  it('refuses a subscription without keys', () => {
    expect(() => subscribeBody({ endpoint: 'https://push.example/x' })).toThrow()
  })
})
