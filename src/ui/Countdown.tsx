import { useEffect, useRef, useState } from 'react'

/**
 * Counts down from the server's `seconds_left`, re-syncing whenever a poll brings a new value.
 * Interpolated with performance.now(), so a throttled timer can't make it drift.
 */
export function useCountdown(secondsLeft: number | undefined): number {
  const anchor = useRef({ at: performance.now(), left: secondsLeft ?? 0 })
  const [left, setLeft] = useState(secondsLeft ?? 0)
  useEffect(() => {
    anchor.current = { at: performance.now(), left: secondsLeft ?? 0 }
    setLeft(secondsLeft ?? 0)
  }, [secondsLeft])
  useEffect(() => {
    const id = window.setInterval(() => {
      const elapsed = (performance.now() - anchor.current.at) / 1000
      setLeft(Math.max(0, Math.round(anchor.current.left - elapsed)))
    }, 1000)
    return () => window.clearInterval(id)
  }, [])
  return left
}

export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
