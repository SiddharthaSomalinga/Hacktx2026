import { api } from './client'
import type {
  BuildingDetail,
  BuildingFull,
  BuildingSummary,
  DemoUser,
  HistoryPoint,
  InboxItem,
  Match,
  Me,
  Recommendation,
  SearchResult,
  SearchStatus,
  SeatLookup,
  TopicOut,
} from './types'

const enc = encodeURIComponent

/** Who to block or report: the request or match on screen names them (D53). */
export type Other = { request_id: string } | { match_id: string }

export const endpoints = {
  buildings: () => api<BuildingSummary[]>('GET', '/buildings', undefined, { revalidate: true }),
  building: (id: string) => api<BuildingDetail>('GET', `/buildings/${enc(id)}`, undefined, { revalidate: true }),
  history: (id: string) => api<HistoryPoint[]>('GET', `/buildings/${enc(id)}/history`),
  seat: (id: string) => api<SeatLookup>('GET', `/seats/${enc(id)}`),
  recommend: (buildingId: string, floor?: number, tableId?: string) => {
    const query = new URLSearchParams({ building_id: buildingId })
    if (floor !== undefined) query.set('floor', String(floor))
    if (tableId !== undefined) query.set('table_id', tableId)
    return api<Recommendation | BuildingFull>('GET', `/recommend?${query}`)
  },

  me: () => api<Me>('GET', '/me'),
  demoUsers: () => api<DemoUser[]>('GET', '/demo-users'),
  login: (userId: string) => api<DemoUser>('POST', '/login', { user_id: userId }),
  logout: () => api<{ ok: boolean }>('POST', '/logout'),

  search: (topicRaw: string, related = false) =>
    api<SearchResult>('POST', '/search', related ? { topic_raw: topicRaw, group: 'related' } : { topic_raw: topicRaw }),
  searchStatus: (id: string) => api<SearchStatus>('GET', `/search/${enc(id)}`),
  join: (id: string) => api<SearchStatus>('POST', `/search/${enc(id)}/join`),
  cancelSearch: (id: string) => api<{ status: string }>('POST', `/search/${enc(id)}/cancel`),

  link: (seatId: string) => api<{ session_id: string }>('POST', '/host/link', { seat_id: seatId }),
  hostTopic: (topicRaw: string, aboutMe?: string) =>
    api<TopicOut>('POST', '/host/topic', aboutMe ? { topic_raw: topicRaw, about_me: aboutMe } : { topic_raw: topicRaw }),
  hostToggle: (open: boolean) => api<{ open: boolean }>('POST', '/host/toggle', { open }),
  hostMute: (muted: boolean) => api<{ muted: boolean }>('POST', '/host/mute', { muted }),
  hostConfirm: () => api<{ expires_at: string }>('POST', '/host/confirm'),
  inbox: () => api<InboxItem[]>('GET', '/host/inbox'),
  accept: (requestId: string) => api<{ match_id: string }>('POST', `/requests/${enc(requestId)}/accept`),
  decline: (requestId: string, mute = false) =>
    api<{ status: string }>('POST', `/requests/${enc(requestId)}/decline`, mute ? { mute: true } : undefined),

  match: (id: string) => api<Match>('GET', `/matches/${enc(id)}`),
  arrived: (id: string) => api<{ status: string }>('POST', `/matches/${enc(id)}/arrived`),
  cancelMatch: (id: string) => api<{ status: string }>('POST', `/matches/${enc(id)}/cancel`),

  block: (other: Other) => api<{ ok: boolean }>('POST', '/block', other),
  report: (other: Other, reason: string) => api<{ ok: boolean }>('POST', '/report', { ...other, reason }),

  vapidKey: () => api<{ key: string }>('GET', '/push/vapid-public-key'),
  subscribe: (body: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    api<{ ok: boolean }>('POST', '/push/subscribe', body),
  unsubscribe: (endpoint: string) => api<{ ok: boolean }>('DELETE', '/push/subscribe', { endpoint }),
}
