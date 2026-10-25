import type { StyleSpecification } from 'maplibre-gl'
import tiles from '../../public/map/tiles.json'

const v = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/**
 * The campus basemap, drawn in the app's own palette from the design tokens (D48). It is kept
 * monochrome on purpose: only the tracked buildings carry color, and that color means FR-8.
 */
export function campusStyle(): StyleSpecification {
  const origin = window.location.origin
  const paper = v('--paper')
  const surface2 = v('--surface-2')
  const line = v('--line')
  const line2 = v('--line-2')
  const ink3 = v('--ink-3')
  const ink2 = v('--ink-2')
  const grid = v('--grid')
  return {
    version: 8,
    glyphs: `${origin}/map/fonts/{fontstack}/{range}.pbf`,
    sources: {
      campus: {
        type: 'vector',
        tiles: [`${origin}/map/tiles/{z}/{x}/{y}.mvt`],
        bounds: tiles.bounds as [number, number, number, number],
        minzoom: tiles.minzoom,
        maxzoom: tiles.maxzoom,
        attribution: tiles.attribution,
      },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': paper } },
      { id: 'earth', type: 'fill', source: 'campus', 'source-layer': 'earth', paint: { 'fill-color': paper } },
      {
        id: 'landuse',
        type: 'fill',
        source: 'campus',
        'source-layer': 'landuse',
        filter: ['in', ['get', 'kind'], ['literal', ['park', 'grass', 'garden', 'pitch', 'university', 'college', 'recreation_ground']]],
        paint: { 'fill-color': grid },
      },
      { id: 'water', type: 'fill', source: 'campus', 'source-layer': 'water', paint: { 'fill-color': line } },
      {
        id: 'paths',
        type: 'line',
        source: 'campus',
        'source-layer': 'roads',
        filter: ['==', ['get', 'kind'], 'path'],
        paint: { 'line-color': line2, 'line-width': ['interpolate', ['linear'], ['zoom'], 15, 0.5, 18, 1.5], 'line-dasharray': [2, 2] },
      },
      {
        id: 'roads-casing',
        type: 'line',
        source: 'campus',
        'source-layer': 'roads',
        filter: ['in', ['get', 'kind'], ['literal', ['highway', 'major_road', 'minor_road']]],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': line2,
          'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 14, 2, 18, ['match', ['get', 'kind'], 'minor_road', 12, 22]],
        },
      },
      {
        id: 'roads',
        type: 'line',
        source: 'campus',
        'source-layer': 'roads',
        filter: ['in', ['get', 'kind'], ['literal', ['highway', 'major_road', 'minor_road']]],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': paper,
          'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 14, 1, 18, ['match', ['get', 'kind'], 'minor_road', 10, 19]],
        },
      },
      {
        id: 'buildings',
        type: 'fill',
        source: 'campus',
        'source-layer': 'buildings',
        paint: { 'fill-color': surface2, 'fill-outline-color': line2 },
      },
      {
        id: 'road-labels',
        type: 'symbol',
        source: 'campus',
        'source-layer': 'roads',
        minzoom: 15,
        filter: ['all', ['has', 'name'], ['in', ['get', 'kind'], ['literal', ['major_road', 'minor_road']]]],
        layout: {
          'symbol-placement': 'line',
          'text-field': ['get', 'name'],
          'text-font': ['noto-sans-regular'],
          'text-size': 11,
          'text-letter-spacing': 0.04,
        },
        paint: { 'text-color': ink2, 'text-halo-color': paper, 'text-halo-width': 1.5 },
      },
      {
        id: 'poi-labels',
        type: 'symbol',
        source: 'campus',
        'source-layer': 'pois',
        minzoom: 16.5,
        filter: ['has', 'name'],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['noto-sans-regular'], 'text-size': 10, 'text-max-width': 8 },
        paint: { 'text-color': ink3, 'text-halo-color': paper, 'text-halo-width': 1.2 },
      },
    ],
  }
}

export const TILE_BOUNDS = tiles.bounds as [number, number, number, number]
