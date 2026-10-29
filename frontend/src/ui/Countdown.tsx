import { useEffect, useState } from 'react'

/** Seconds left at `nowMs`, counting down from `secondsLeft` as fetched at `anchorAt`. */
export function remainingAt(secondsLeft: number, anchorAt: number, nowMs: number): number {
  return Math.max(0, Math.round(secondsLeft - (nowMs - anchorAt) / 1000))
}

/**
 * Counts down from the server's `seconds_left`. `anchorAt` is when that value was fetched (the
 * query's `dataUpdatedAt`): it moves on every fetch, so a new request that again reports 300
 * restarts the count even though the number is the same (D61).
 */
export function useCountdown(secondsLeft: number | undefined, anchorAt: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [secondsLeft, anchorAt])
  return remainingAt(secondsLeft ?? 0, anchorAt, now)
}

export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
