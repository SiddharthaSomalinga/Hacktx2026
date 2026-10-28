import { useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect, useRef, useSyncExternalStore } from 'react'
import { primeEtag } from '../api/client'
import { etagsOf, isSilent, liveUrl, reconnectDelay, seatFromDetail, topicsOf, USER_TOPICS } from '../api/live'
import { liveStore } from '../api/liveStore'
import { keys, useMe } from '../api/queries'
import type { BuildingDetail, BuildingSummary, SeatLookup } from '../api/types'
import { useFocusState } from './focus'

const subscribeVisibility = (onChange: () => void) => {
  document.addEventListener('visibilitychange', onChange)
  return () => document.removeEventListener('visibilitychange', onChange)
}
const useVisible = () => useSyncExternalStore(subscribeVisibility, () => document.visibilityState === 'visible')

function parse<T>(data: string): T | undefined {
  try {
    return JSON.parse(data) as T
  } catch {
    return undefined
  }
}

/** Refetch what this user sees; an in-flight fetch is kept, so repeated hints cost one request. */
function refetch(client: QueryClient, roots: readonly string[]) {
  for (const root of roots) void client.invalidateQueries({ queryKey: [root] }, { cancelRefetch: false })
}

/** A ping vouches for data the client already has: mark it current without changing it. */
function touch(client: QueryClient, key: QueryKey) {
  client.setQueryData(key, (data: unknown) => data, { updatedAt: Date.now() })
}

/**
 * The live stream (D61): one EventSource for the open app, carrying the buildings list, the
 * floor plan in focus and the logged-in user's refetch hints. It reopens when the focused
 * building or the user changes, closes while the app is hidden, and reconnects with backoff;
 * the queries poll on their own whenever it can't vouch for their data.
 */
export function useLive(): void {
  const { focus } = useFocusState()
  const building = focus.kind === 'plan' ? focus.buildingId : null
  const userId = useMe().data?.user?.id ?? null
  const visible = useVisible()
  const client = useQueryClient()
  const lastEventId = useRef<string | null>(null)

  useEffect(() => {
    if (!visible) {
      liveStore.dispatch({ type: 'hidden' })
      return
    }
    if (typeof EventSource === 'undefined') {
      liveStore.dispatch({ type: 'failed' }) // polling takes over after LIVE_FOR_MS
      return
    }
    let source: EventSource | null = null
    let retry = 0
    let attempt = 0

    const reconnect = () => {
      source?.close()
      liveStore.dispatch({ type: 'failed' })
      window.clearTimeout(retry)
      retry = window.setTimeout(connect, reconnectDelay(attempt++))
    }

    const snapshot = <T,>(event: MessageEvent<string>, key: QueryKey, path: string, etag: string | null): T | undefined => {
      const data = parse<T>(event.data)
      if (data === undefined) return undefined
      lastEventId.current = event.lastEventId
      client.setQueryData(key, data)
      if (etag) primeEtag(path, etag, data)
      liveStore.dispatch({ type: 'snapshot' })
      return data
    }

    function connect() {
      liveStore.dispatch({ type: 'connecting', building })
      const es = new EventSource(liveUrl(building, lastEventId.current))
      source = es
      es.onopen = () => {
        attempt = 0
        liveStore.dispatch({ type: 'opened' })
        refetch(client, USER_TOPICS) // anything may have changed while disconnected
      }
      es.addEventListener('buildings', (event) => {
        snapshot<BuildingSummary[]>(event, keys.buildings, '/buildings', etagsOf(event.lastEventId).buildings)
      })
      es.addEventListener('building', (event) => {
        if (building === null) return
        const path = `/buildings/${encodeURIComponent(building)}`
        const detail = snapshot<BuildingDetail>(event, keys.building(building), path, etagsOf(event.lastEventId).building)
        if (!detail) return
        for (const [key, seat] of client.getQueriesData<SeatLookup>({ queryKey: ['seat'] })) {
          if (seat && seatFromDetail(seat, detail) !== seat) client.setQueryData(key, seatFromDetail(seat, detail))
        }
      })
      es.addEventListener('invalidate', (event) => {
        liveStore.dispatch({ type: 'invalidate' })
        refetch(client, topicsOf(event.data))
      })
      es.addEventListener('ping', (event) => {
        const health = parse<{ db?: unknown; hints?: unknown }>(event.data)
        const db = health?.db === true
        liveStore.dispatch({ type: 'ping', db, hints: health?.hints === true })
        if (!db) return
        lastEventId.current = event.lastEventId
        touch(client, keys.buildings)
        if (building !== null) touch(client, keys.building(building))
      })
      es.onerror = reconnect // we reconnect ourselves: EventSource gives up after a non-200
    }

    connect()
    const watchdog = window.setInterval(() => {
      if (isSilent(liveStore.get(), Date.now())) reconnect()
    }, 1000)
    return () => {
      window.clearInterval(watchdog)
      window.clearTimeout(retry)
      source?.close()
    }
  }, [building, userId, visible, client])
}
