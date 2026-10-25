// Copies the label glyphs the map style uses from protomaps/basemaps-assets, pinned by commit.
// Folders are renamed without spaces so glyph URLs need no percent-encoding.
import { mkdir, writeFile } from 'node:fs/promises'
import { OUT } from './campus.mjs'

const BASE = 'https://raw.githubusercontent.com/protomaps/basemaps-assets/COMMIT/fonts'
const STACKS = { 'noto-sans-regular': 'Noto Sans Regular', 'noto-sans-medium': 'Noto Sans Medium' }
const RANGES = ['0-255', '256-511', '512-767', '768-1023', '7680-7935', '8192-8447', '8448-8703']

const commit = process.argv[2]
if (!commit) throw new Error('usage: fetch-glyphs.mjs <basemaps-assets commit sha>')
for (const [folder, stack] of Object.entries(STACKS)) {
  const dir = new URL(`fonts/${folder}/`, OUT)
  await mkdir(dir, { recursive: true })
  for (const range of RANGES) {
    const url = `${BASE.replace('COMMIT', commit)}/${encodeURIComponent(stack)}/${range}.pbf`
    const response = await fetch(url)
    if (!response.ok) throw new Error(`${response.status} ${url}`)
    await writeFile(new URL(`${range}.pbf`, dir), new Uint8Array(await response.arrayBuffer()))
  }
}
console.log(`glyphs from basemaps-assets@${commit}`)
