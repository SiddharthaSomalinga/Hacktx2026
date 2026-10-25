// Web Mercator with MapLibre's 512px tiles. Used to place the camera before MapLibre loads, so
// the SVG footprints drawn first sit exactly where the map later draws its streets.
import footprints from './footprints.json'

export type LngLat = [number, number]
export type Camera = { center: LngLat; zoom: number }
export type Padding = { top: number; right: number; bottom: number; left: number }

const TILE = 512

export function project([lng, lat]: LngLat, zoom: number): [number, number] {
  const scale = TILE * 2 ** zoom
  const x = ((lng + 180) / 360) * scale
  const rad = (lat * Math.PI) / 180
  const y = ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * scale
  return [x, y]
}

export function bounds(rings: LngLat[][]): [LngLat, LngLat] {
  const pts = rings.flat()
  const lngs = pts.map((p) => p[0])
  const lats = pts.map((p) => p[1])
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ]
}

/** The camera that fits `box` inside the viewport minus padding, like MapLibre's fitBounds. */
export function fit(box: [LngLat, LngLat], width: number, height: number, pad: Padding, maxZoom = 18): Camera {
  const [sw, ne] = box
  const [x0, y1] = project(sw, 0)
  const [x1, y0] = project(ne, 0)
  const availW = Math.max(1, width - pad.left - pad.right)
  const availH = Math.max(1, height - pad.top - pad.bottom)
  const zoom = Math.min(maxZoom, Math.log2(Math.min(availW / (x1 - x0), availH / (y1 - y0))))
  // Center the box in the padded area: shift the center by half the padding imbalance.
  const scale = 2 ** zoom
  const cx = ((x0 + x1) / 2) * scale + (pad.right - pad.left) / 2
  const cy = ((y0 + y1) / 2) * scale + (pad.bottom - pad.top) / 2
  return { center: unproject([cx, cy], zoom), zoom }
}

export function unproject([x, y]: [number, number], zoom: number): LngLat {
  const scale = TILE * 2 ** zoom
  const lng = (x / scale) * 360 - 180
  const n = Math.PI - (2 * Math.PI * y) / scale
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))
  return [lng, lat]
}

type Feature = { id: string; properties: { id: string }; geometry: { coordinates: LngLat[][] } }
export const FOOTPRINTS = (footprints as unknown as { features: Feature[] }).features
export const CAMPUS_BOUNDS = bounds(FOOTPRINTS.map((f) => f.geometry.coordinates[0] ?? []))
