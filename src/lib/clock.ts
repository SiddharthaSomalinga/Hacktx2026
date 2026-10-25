import { onlineManager } from '@tanstack/react-query'
import { useEffect, useState, useSyncExternalStore } from 'react'

/** The current time, ticking once a second while the page is visible. */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    let id = 0
    const start = () => {
      window.clearInterval(id)
      if (document.visibilityState === 'visible') id = window.setInterval(() => setNow(Date.now()), 1000)
    }
    start()
    document.addEventListener('visibilitychange', start)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', start)
    }
  }, [])
  return now
}

export const useOnline = () => useSyncExternalStore(onlineManager.subscribe.bind(onlineManager), () => onlineManager.isOnline())

const hourFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', timeZone: 'America/Chicago' })

/** An hour in Central Time (NFR-5), e.g. "3 PM". */
export const centralHour = (iso: string) => hourFormat.format(new Date(iso))
