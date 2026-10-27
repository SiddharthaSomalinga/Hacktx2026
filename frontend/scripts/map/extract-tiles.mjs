// Copies the campus tiles out of the hosted Protomaps archive into public/map/tiles/{z}/{x}/{y}.mvt.
// Tiles are written decompressed: the backend serves files with FileResponse, which cannot set
// Content-Encoding, and MapLibre must never be handed gzip bytes it did not ask for.
import { mkdir, writeFile } from 'node:fs/promises'
import { PMTiles } from 'pmtiles'
import { BBOX, BUILD, MAX_ZOOM, MIN_ZOOM, OUT } from './campus.mjs'

const lonToX = (lon, z) => Math.floor(((lon + 180) / 360) * 2 ** z)
const latToY = (lat, z) => {
  const rad = (lat * Math.PI) / 180
  return Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** z)
}

const archive = new PMTiles(`https://build.protomaps.com/${BUILD}.pmtiles`)
const header = await archive.getHeader()
let written = 0
let bytes = 0
for (let z = MIN_ZOOM; z <= MAX_ZOOM; z++) {
  for (let x = lonToX(BBOX.west, z); x <= lonToX(BBOX.east, z); x++) {
    for (let y = latToY(BBOX.north, z); y <= latToY(BBOX.south, z); y++) {
      const tile = await archive.getZxy(z, x, y)
      const dir = new URL(`tiles/${z}/${x}/`, OUT)
      await mkdir(dir, { recursive: true })
      // An empty file stands in for an absent tile, so the server never answers with index.html.
      const data = tile ? new Uint8Array(tile.data) : new Uint8Array()
      await writeFile(new URL(`${y}.mvt`, dir), data)
      written += 1
      bytes += data.byteLength
    }
  }
}
const tilejson = {
  tilejson: '3.0.0',
  bounds: [BBOX.west, BBOX.south, BBOX.east, BBOX.north],
  minzoom: MIN_ZOOM,
  maxzoom: MAX_ZOOM,
  attribution: '© OpenStreetMap contributors · Protomaps',
  build: BUILD,
  schema: header.specVersion,
}
await writeFile(new URL('tiles.json', OUT), JSON.stringify(tilejson, null, 2) + '\n')
console.log(`${written} tiles, ${(bytes / 1024).toFixed(0)} KiB, build ${BUILD}`)
