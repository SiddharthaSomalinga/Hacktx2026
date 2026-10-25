// Every screen has a URL (D46). Build paths here, never by hand in components.
const enc = encodeURIComponent

export const paths = {
  home: () => '/',
  building: (id: string) => `/b/${enc(id)}`,
  floor: (id: string, floor: number) => `/b/${enc(id)}/${floor}`,
  table: (id: string, floor: number, tableId: string) => `/b/${enc(id)}/${floor}/${enc(tableId)}`,
  history: (id: string) => `/b/${enc(id)}/history`,
  seat: (id: string) => `/seat/${enc(id)}`,
  hostSetup: (seatId: string) => `/seat/${enc(seatId)}/host`,
  host: () => '/host',
  login: (next: string) => `/login?next=${enc(next)}`,
  find: () => '/find',
  search: (id: string) => `/search/${enc(id)}`,
  match: (id: string) => `/match/${enc(id)}`,
}

/** Only same-app paths are followed after login, so `next` can't send anyone off-site. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export function parseFloor(raw: string | undefined): number | null {
  if (raw === undefined || !/^-?\d{1,3}$/.test(raw)) return null
  return Number(raw)
}
