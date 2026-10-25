const request = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (response.status === 304) return null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.message || data.error || 'Request failed')
  return data
}

export const api = {
  me: () => request('/me'),
  login: (user) => request('/login', { method: 'POST', body: JSON.stringify(user) }),
  logout: () => request('/logout', { method: 'POST' }),
  buildings: () => request('/buildings'),
  building: (id) => request(`/buildings/${id}`),
  recommend: (params) => request(`/recommend?${new URLSearchParams(params)}`),
  history: (id) => request(`/buildings/${id}/history`),
  linkSeat: (seatId) => request('/host/link', { method: 'POST', body: JSON.stringify({ seat_id: seatId }) }),
  toggleHost: (open) => request('/host/toggle', { method: 'POST', body: JSON.stringify({ open }) }),
  search: (topic) => request('/searches', { method: 'POST', body: JSON.stringify({ topic }) }),
}
