import { QueryClient, useQuery, type QueryKey, type UseQueryOptions } from '@tanstack/react-query'
import { endpoints } from './endpoints'
import { pollDelay } from './poll'
import type { BuildingDetail, Recommendation, BuildingFull } from './types'

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

/** Poll every POLL_WEB_S while enabled; TanStack pauses it while the tab is hidden. */
function polled<T>(key: QueryKey, fn: () => Promise<T>, enabled = true): UseQueryOptions<T, Error, T, QueryKey> {
  return {
    queryKey: key,
    queryFn: tracked(key, fn),
    enabled,
    refetchInterval: (query) => (enabled ? every(query) : false),
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

export const useBuildings = (enabled = true) => useQuery(polled(keys.buildings, endpoints.buildings, enabled))

export const useBuilding = (id: string | undefined) =>
  useQuery(polled(keys.building(id ?? ''), () => endpoints.building(id ?? ''), id !== undefined))

/** A signature of the seats in scope: recommend refetches exactly when one of them changes. */
function stateSignature(detail: BuildingDetail | undefined, floor?: number): string {
  if (!detail) return ''
  return detail.floors
    .filter((f) => floor === undefined || f.floor === floor)
    .flatMap((f) => f.tables.flatMap((t) => t.seats.map((s) => s.state[0])))
    .join('')
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

export const useSeat = (id: string | undefined) =>
  useQuery(polled(keys.seat(id ?? ''), () => endpoints.seat(id ?? ''), id !== undefined))

export const useMe = () => useQuery(polled(keys.me, endpoints.me))

export const useDemoUsers = (enabled: boolean) =>
  useQuery({ queryKey: keys.demoUsers, queryFn: endpoints.demoUsers, enabled, retry: 1 })

export const useSearchStatus = (id: string | undefined, enabled = true) =>
  useQuery(polled(keys.search(id ?? ''), () => endpoints.searchStatus(id ?? ''), id !== undefined && enabled))

export const useInbox = (enabled: boolean) => useQuery(polled(keys.inbox, endpoints.inbox, enabled))

export const useMatch = (id: string | undefined, enabled = true) =>
  useQuery(polled(keys.match(id ?? ''), () => endpoints.match(id ?? ''), id !== undefined && enabled))
