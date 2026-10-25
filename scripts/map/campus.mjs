// The campus extract's fixed parameters (D48). Changing any of them means re-running the map scripts.
export const BUILD = '20261024' // Protomaps daily build, basemap schema 4.15.2
export const BBOX = { west: -97.752, south: 30.27, east: -97.722, north: 30.299 }
export const MIN_ZOOM = 12
export const MAX_ZOOM = 15
export const OUT = new URL('../../public/map/', import.meta.url)
