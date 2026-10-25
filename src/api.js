const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const request = async (path, options = {}) => {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (response.status === 304) return null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.message || data.error || 'Request failed')
  return data
}

const normalizeBuilding = (building) => ({
  ...building,
  short: building.short || building.name?.[0] || '?',
  distance: building.distance || 'Nearby',
  floors: building.floors || 1,
  color: building.color || (building.is_simulated ? 'yellow' : 'green'),
  location: building.location || 'UT Austin campus',
  status: building.status || (building.is_simulated ? 'simulated' : 'live'),
  total: building.total || 0,
  open: building.open || 0,
})

export const api = {
  me: () => request('/me'),
  login: (user) => request('/login', { method: 'POST', body: JSON.stringify(user) }),
  logout: () => request('/logout', { method: 'POST' }),
  buildings: async () => (await request('/buildings')).map(normalizeBuilding),
  building: (id) => request(`/buildings/${id}`),
  recommend: (params) => request(`/recommend?${new URLSearchParams(params)}`),
  history: (id) => request(`/buildings/${id}/history`),
  linkSeat: (seatId) => request('/host/link', { method: 'POST', body: JSON.stringify({ seat_id: seatId }) }),
  topic: (topicRaw) => request('/host/topic', { method: 'POST', body: JSON.stringify({ topic_raw: topicRaw }) }),
  toggleHost: (open) => request('/host/toggle', { method: 'POST', body: JSON.stringify({ open }) }),
  inbox: () => request('/host/inbox'),
  search: (topic) => request('/search', { method: 'POST', body: JSON.stringify({ topic_raw: topic }) }),
  searchStatus: (id) => request(`/search/${id}`),
  acceptRequest: (id) => request(`/requests/${id}/accept`, { method: 'POST' }),
  declineRequest: (id) => request(`/requests/${id}/decline`, { method: 'POST' }),
  match: (id) => request(`/matches/${id}`),
  arrived: (id) => request(`/matches/${id}/arrived`, { method: 'POST' }),
}
