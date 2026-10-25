# Ghost Seats

Ghost Seats helps UT Austin students find genuinely open seats and discover nearby study partners.

## Frontend

The current frontend is a Vite + React demo on the `v1frontend` branch.

```bash
npm install
npm run dev
```

The UI currently includes:

- Live-looking seat states for open, occupied, likely opening, and offline seats
- A UT Austin campus overview with searchable, clickable building footprint shapes
- A real 3D vector-tile campus view powered by MapLibre GL
- Dark mode
- A focused building zoom with floor count and a generated classroom-layout preview
- A building focus card that jumps into the building's live seat view
- Topic normalization, host mode, and study-match demo interactions

The seat and building data are local demo fixtures until the backend API and authorized campus geometry are connected. The current footprints and classroom layouts are deliberately simulated.

### 3D map provider

The frontend uses MapLibre GL. By default it renders real OpenStreetMap geography as a raster base with local 3D demo extrusions for the tracked campus buildings, so the map remains visible even when a vector-tile provider has no data for a tile. To use true provider-supplied building geometry from OpenFreeMap, Esri, MapTiler, or another licensed source, set a compatible style URL before starting Vite:

```bash
VITE_MAP_STYLE_URL="https://your-provider.example/style.json" npm run dev
```

Provider credentials belong in environment variables and should never be committed. The current map has real geographic context and 3D camera behavior, but the default campus building footprints and room names are still demo fixtures until they are connected to authorized campus data.

## Campus Map Plan

It is possible to show a larger section of the UT Austin campus, draw building footprints, select a building, and zoom into a building-level classroom view. The intended flow is:

1. Render an overview of the campus with building polygons and labels.
2. Search for or click a building polygon.
3. Zoom to the selected building and show its metadata, such as name, address, and number of floors.
4. Open a generated classroom layout for a selected floor.
5. Highlight the selected classroom or seat and connect it to live occupancy data.

### Map data and licensing

Do not scrape or copy Google Maps tiles, building shapes, or other Google map data into the repository. Google Maps data is licensed and subject to Google's terms. For production map geometry, use one of these sources instead:

- OpenStreetMap building footprints through a permitted tile or data provider
- A UT Austin campus GIS dataset with permission to use it
- Another licensed campus mapping provider

The source, license, attribution, and update date should be recorded alongside any imported geometry. API keys must stay in environment variables and must never be committed.

A practical implementation would use GeoJSON for building footprints and a map renderer such as MapLibre GL JS. The campus data adapter should normalize each source into a small internal shape:

```ts
{
  id: "pcl",
  name: "Perry-Castaneda Library",
  floors: 4,
  footprint: { type: "Polygon", coordinates: [] },
  source: "openstreetmap",
  sourceUpdatedAt: "2026-10-24"
}
```

## Generated Classroom Layouts

The classroom interiors shown in the demo are intentionally generated placeholders. Their walls, rooms, doors, and classroom shapes are **not real UT Austin floor plans** and must not be presented as accurate navigation information.

Until verified floor plans are available, generated interiors should:

- Be labeled as simulated or generated in the UI
- Use deterministic fixture data so demos are repeatable
- Contain no claims about real room locations or accessibility routes
- Remain separate from real seat sensor data

In the future, replace the generated floor fixtures with verified floor-plan data from UT Austin or another authorized source. Keep the same normalized interface so the UI can switch data sources without changing the search, zoom, and seat-selection workflow.

## Planned Backend Integration

The frontend will eventually call the API described in [Ghost_Seats_Requirements_Spec.md](Ghost_Seats_Requirements_Spec.md), including:

- `GET /api/buildings` and `GET /api/buildings/:id`
- `GET /api/recommend`
- `POST /api/readings`
- Search, host, request, match, block, and report endpoints

Until those endpoints are available, the frontend uses local state and mock occupancy values.

## Privacy and Safety

The product should not expose public ghost duration, live user location, or unverified classroom navigation. Names and precise seat details should only be shared after a study request is accepted, as defined in the requirements specification.
