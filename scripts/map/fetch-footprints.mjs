// Writes src/map/footprints.json: the outline of each tracked building, keyed by backend building
// id. Outlines come from the `buildings` layer of the campus tiles (OSM data via Protomaps, ODbL),
// so they line up with the map exactly. Each building is the polygon that contains its seeded
// lat/lng (backend/sql/seed.sql); a wrong coordinate fails here instead of drawing elsewhere.
import { readFile, writeFile } from 'node:fs/promises'
import { VectorTile } from '@mapbox/vector-tile'
import { PbfReader } from 'pbf'
import { MAX_ZOOM, OUT } from './campus.mjs'

const BUILDINGS = {
  pcl: { lat: 30.2827, lng: -97.7381 },
  wel: { lat: 30.2866, lng: -97.7376 },
  gdc: { lat: 30.2862, lng: -97.7366 },
}

const tileOf = (lng, lat, z) => {
  const rad = (lat * Math.PI) / 180
  return {
    x: Math.floor(((lng + 180) / 360) * 2 ** z),
    y: Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** z),
  }
}

function contains(ring, [px, py]) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

const round = (ring) => ring.map(([x, y]) => [Number(x.toFixed(7)), Number(y.toFixed(7))])

const features = []
for (const [id, { lat, lng }] of Object.entries(BUILDINGS)) {
  const { x, y } = tileOf(lng, lat, MAX_ZOOM)
  const bytes = await readFile(new URL(`tiles/${MAX_ZOOM}/${x}/${y}.mvt`, OUT))
  const layer = new VectorTile(new PbfReader(bytes)).layers.buildings
  if (!layer) throw new Error(`tile ${MAX_ZOOM}/${x}/${y} has no buildings layer`)
  let found = null
  for (let i = 0; i < layer.length && !found; i++) {
    const geo = layer.feature(i).toGeoJSON(x, y, MAX_ZOOM)
    const polygons = geo.geometry.type === 'Polygon' ? [geo.geometry.coordinates] : geo.geometry.type === 'MultiPolygon' ? geo.geometry.coordinates : []
    const hit = polygons.find((rings) => contains(rings[0], [lng, lat]))
    if (hit) found = { rings: hit, height: geo.properties.height ?? null }
  }
  if (!found) throw new Error(`no building outline contains ${id} at ${lat},${lng}`)
  features.push({
    type: 'Feature',
    id,
    properties: { id, height: found.height },
    geometry: { type: 'Polygon', coordinates: found.rings.map(round) },
  })
  console.log(id, `${found.rings[0].length} points`, found.height ? `${found.height} m` : '')
}
const collection = { type: 'FeatureCollection', features }
await writeFile(new URL('../../src/map/footprints.json', import.meta.url), JSON.stringify(collection) + '\n')
