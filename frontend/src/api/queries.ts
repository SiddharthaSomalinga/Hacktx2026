import { QueryClient, useQuery, type QueryKey, type UseQueryOptions } from '@tanstack/react-query'
import { endpoints } from './endpoints'
import { pollingFor, type LiveState } from './live'
import { useLiveState } from './liveStore'
import { pollDelay } from './poll'
import type { BuildingDetail, Recommendation, BuildingFull, SeatLookup } from './types'

// Consecutive failures per query, for backoff. TanStack resets its own count on every fetch.
const failures = new Map<string, number>()

function tracked<T>(key: QueryKey, fn: () => Promise<T>): () => Promise<T> {
  const hash = JSON.stringify(key)
  return async () => {
    try {
      const result = await fn()
      failures.set(hash, 0)
      return result
    } catch (error) {
      failures.set(hash, (failures.get(hash) ?? 0) + 1)
      throw error
    }
  }
}

function every(query: { queryKey: QueryKey; state: { error: unknown } }): number {
  return pollDelay(failures.get(JSON.stringify(query.queryKey)) ?? 0, query.state.error)
}

/**
 * Map data comes from the live stream, per-user data refetches when the stream says so (D61).
 * A query polls only while the stream can't vouch for it: `map` queries name the building they
 * need (undefined: the buildings list, which every stream carries), `user` queries need hints.
 */
type Scope<T> = { live: LiveState } & ({ kind: 'map'; building?: (data: T | undefined) => string | null } | { kind: 'user' })

/** Poll every POLL_WEB_S while enabled and needed; TanStack pauses it while the tab is hidden. */
function polled<T>(key: QueryKey, fn: () => Promise<T>, enabled: boolean, scope: Scope<T>): UseQueryOptions<T, Error, T, QueryKey> {
  return {
    queryKey: key,
    queryFn: tracked(key, fn),
    enabled,
    refetchInterval: (query) => {
      if (!enabled) return false
      const now = Date.now()
      const need =
        scope.kind === 'map'
          ? pollingFor(scope.live, now, scope.building?.(query.state.data)).map
          : pollingFor(scope.live, now).user
      return need ? every(query) : false
    },
    refetchIntervalInBackground: false,
    retry: false,
  }
}

export const keys = {
  buildings: ['buildings'] as const,
  building: (id: string) => ['building', id] as const,
  history: (id: string) => ['history', id] as const,
  seat: (id: string) => ['seat', id] as const,
  me: ['me'] as const,
  demoUsers: ['demo-users'] as const,
  search: (id: string) => ['search', id] as const,
  inbox: ['inbox'] as const,
  match: (id: string) => ['match', id] as const,
}

export const PUBLIC_QUERY_ROOTS = new Set(['buildings', 'building'])

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 0, gcTime: 24 * 60 * 60 * 1000, refetchOnWindowFocus: true, retry: false },
      mutations: { retry: 0 },
    },
  })
}

export function useBuildings(enabled = true) {
  const live = useLiveState()
  return useQuery(polled(keys.buildings, endpoints.buildings, enabled, { live, kind: 'map' }))
}

export function useBuilding(id: string | undefined) {
  const live = useLiveState()
  const scope = { live, kind: 'map', building: () => id ?? null } as const
  return useQuery(polled(keys.building(id ?? ''), () => endpoints.building(id ?? ''), id !== undefined, scope))
}

/** A signature of the seats in scope: recommend refetches exactly when one of them changes. */
export function stateSignature(detail: BuildingDetail | undefined, floor?: number): string {
  if (!detail) return ''
  return detail.floors
    .filter((f) => floor === undefined || f.floor === floor)
    .flatMap((f) => f.tables.flatMap((t) => t.seats.map((s) => `${s.id}:${s.state}`)))
    .join(',')
}

export function useRecommendation(
  buildingId: string | undefined,
  detail: BuildingDetail | undefined,
  floor?: number,
  tableId?: string,
) {
  const signature = stateSignature(detail, undefined)
  return useQuery<Recommendation | BuildingFull>({
    queryKey: ['recommend', buildingId, floor ?? null, tableId ?? null, signature],
    queryFn: () => endpoints.recommend(buildingId ?? '', floor, tableId),
    enabled: buildingId !== undefined && detail !== undefined,
    placeholderData: (previous) => previous,
    retry: false,
  })
}

export const useHistory = (id: string | undefined) =>
  useQuery({
    queryKey: keys.history(id ?? ''),
    queryFn: () => endpoints.history(id ?? ''),
    enabled: id !== undefined,
    // The newest point is the current hour so far; refresh it every few minutes.
    refetchInterval: 5 * 60 * 1000,
    retry: false,
  })

/** A seat follows its building's floor plan when the stream carries it; otherwise it polls. */
export function useSeat(id: string | undefined) {
  const live = useLiveState()
  const scope = { live, kind: 'map', building: (seat: SeatLookup | undefined) => seat?.building_id ?? null } as const
  return useQuery(polled(keys.seat(id ?? ''), () => endpoints.seat(id ?? ''), id !== undefined, scope))
}

/** Logged out, `me` changes only by logging in, which refetches it; so it never polls. */
export function useMe() {
  const live = useLiveState()
  const options = polled(keys.me, endpoints.me, true, { live, kind: 'user' })
  const interval = options.refetchInterval
  return useQuery({
    ...options,
    refetchInterval: (query) =>
      query.state.data?.user === null || typeof interval !== 'function' ? false : interval(query),
  })
}

export const useDemoUsers = (enabled: boolean) =>
  useQuery({ queryKey: keys.demoUsers, queryFn: endpoints.demoUsers, enabled, retry: 1 })

export function useSearchStatus(id: string | undefined, enabled = true) {
  const live = useLiveState()
  return useQuery(polled(keys.search(id ?? ''), () => endpoints.searchStatus(id ?? ''), id !== undefined && enabled, { live, kind: 'user' }))
}

export function useInbox(enabled: boolean) {
  const live = useLiveState()
  return useQuery(polled(keys.inbox, endpoints.inbox, enabled, { live, kind: 'user' }))
}

export function useMatch(id: string | undefined, enabled = true) {
  const live = useLiveState()
  return useQuery(polled(keys.match(id ?? ''), () => endpoints.match(id ?? ''), id !== undefined && enabled, { live, kind: 'user' }))
}
