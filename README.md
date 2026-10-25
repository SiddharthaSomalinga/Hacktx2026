# Ghost Seats

Seat sensors in UT Austin libraries tell a seat held by a backpack with nobody in it ("ghosted",
shown as *likely opening*) from one that is taken or free. The web app shows every seat live on
a floor plan, recommends one, and matches students studying the same course to an open seat at
the host's table. HackTX 26.

```
firmware/   Arduino sketch: seat sensors and the LED (open green, taken red, ghost yellow)
bridge/     Serial → POST /api/readings
backend/    FastAPI + Postgres/Timescale: seat state, matching, Muse Spark, web push
src/        The web app and PWA (this README)
```

## Run it

```bash
cd backend && make sync db-up db-create && make db-init seed policies   # API + local database
make dev                                   # API on :8000, live contract at /docs
cd .. && npm ci && npm run dev             # app on :5173, /api proxied to :8000
```

Production is one origin: `cd backend && make image FRONTEND_DIR=.` builds the app into the API
image, which serves `dist/` and answers every app path with `index.html`.

| Command | What it does |
|---|---|
| `npm run build` | Typecheck (app and service worker), then build `dist/` with the precache manifest |
| `npx vitest run` | Unit tests for the pure logic: FR-8 colors, floor layout, polling, freshness, push |
| `npm run api:types` | Regenerate `src/api/schema.gen.ts` from a running backend's OpenAPI |
| `npm run map:tiles` / `map:glyphs <sha>` / `map:footprints` | Rebuild the self-hosted campus map in `public/map/` |

## How the app works

- **Map first.** The app opens on the campus. Typing what you're studying goes straight into
  matching; skipping goes to building → floor → table and a recommended seat.
- **Honest data.** Status reads Live, "Updated N s ago", "Unable to refresh" or Offline, from the
  last successful poll. Simulated buildings are labeled. Nothing is mocked in the app.
- **State by shape and color.** Open is an outlined chair, taken is filled, likely opening is a
  dashed outline with a bag, no signal is hatched. Red and green alone are not enough for
  color-blind readers, so every state also has its own shape.
- **Polling, not sockets.** Every 3 s with ETags, paused in a hidden tab, backing off to 30 s
  and honoring `Retry-After` when the backend is down.
- **Offline.** The service worker precaches the shell, fonts, map tiles and card images. API
  responses are never cached; the last map is shown with its age.
- **Push.** Offered where it helps (waiting for an answer, hosting). On iPhone it needs the app
  added to the Home Screen first.

## Data and credits

- Map: © OpenStreetMap contributors (ODbL), tiles from a [Protomaps](https://protomaps.com) daily
  build (20261024), glyphs from protomaps/basemaps-assets. Building outlines come from the same tiles.
- Type: IBM Plex Sans and Mono (SIL OFL).
- Match card images: generated once with Meta's Muse Image (`backend/scripts/card_images.py`);
  prompts and hashes in `public/cards/cards.json`.

Secrets (`NODE_KEY`, VAPID keys, `MUSE_API_KEY`, `SECRET_KEY`) live in `backend/.env`, which is
never committed.
