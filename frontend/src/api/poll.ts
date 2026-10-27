import { MAX_BACKOFF_MS, POLL_WEB_S } from '../config'
import { ApiError } from './client'

/**
 * How long to wait before the next poll (FR-10). Healthy: every POLL_WEB_S. Failing: double the
 * wait per consecutive failure up to MAX_BACKOFF_MS, never sooner than the server's Retry-After.
 * Jitter keeps a room full of phones from retrying in lockstep after an outage.
 */
export function pollDelay(failures: number, error: unknown, random = Math.random): number {
  const base = POLL_WEB_S * 1000
  if (failures === 0) return base
  const backoff = Math.min(base * 2 ** failures, MAX_BACKOFF_MS)
  const floor = error instanceof ApiError ? (error.retryAfterMs ?? 0) : 0
  return Math.round(Math.max(floor, backoff) * (0.8 + random() * 0.4))
}
