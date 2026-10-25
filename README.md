# Synapse

Library seats that tell you the truth, and a study partner at the end of the walk.

Each seat has two sensors: one for an object, one for a person. A bag with nobody behind it
for 30 seconds is a **ghost**: the seat shows *likely opening* instead of *occupied*. The app
puts every seat on a live floor plan, picks the best one for you, and can match you with
someone studying the same course, then point you to the open chair at their table. Built at
HackTX 26.

```
firmware/  Arduino: two sensors per seat, an LED per seat (green open, red taken, yellow ghost)
bridge/    Serial → POST /api/readings, every 2 s
backend/   FastAPI · Postgres/Timescale · Muse Spark for topics and icebreakers · web push
src/       React PWA: campus map, floor plans, matching
```

## How a seat becomes a ghost

`backend/app/domain/seat_engine.py`, run on every reading:

```python
def public_state(s: SeatState, now: datetime, t: Timers) -> PublicState:
    if is_offline(s, now, t):
        return PublicState.OFFLINE
    if s.state is InternalState.OPEN:
        return PublicState.OPEN
    if s.state is InternalState.OCCUPIED:
        return PublicState.OCCUPIED
    assert s.away_since is not None
    return PublicState.LIKELY_OPENING if now - s.away_since >= t.ghost else PublicState.OCCUPIED
```

- A reading becomes a state only after holding for `DEBOUNCE_S` (5 s), so someone shifting in
  their chair doesn't flicker the seat.
- Object present, person absent is *away*. Away stays *occupied* for `GHOST_S` (30 s), then
  turns *likely opening*.
- No reading for `OFFLINE_S` (30 s) is *offline*: a dead sensor never claims a seat is free.
- The away time decides the state and is never sent to anyone. Nobody can see how long you've
  been gone.

## Run it

```bash
cd backend && make sync db-up db-create && make db-init seed policies && make dev   # API :8000
cd .. && npm ci && npm run dev                                                      # app :5173
```

`cd backend && make image FRONTEND_DIR=.` builds one container that serves the API and the app.
To try it on a phone next to a laptop, see `documentation/TESTING.md`.

## What's in the app

- **Map first.** Opens on the UT campus with each library colored by its share of open seats.
  The streets are a self-hosted vector-tile extract, so the map works offline and on venue Wi-Fi.
- **Floor plans drawn from data.** Tables sit at their stored positions; chairs go around them.
  Open is a green outline, occupied blue, a ghost a dashed yellow chair with a bag, no signal
  hatched grey. Shape carries the state too, so it reads without color.
- **"What are you studying today?"** Type "orgo exam" and Muse maps it to CH 320M. You see how
  many people are studying it per floor, never who, until someone says yes.
- **Host from your chair.** Tap the chair you're in, or scan its QR code. The sensor has to
  see you sitting there before the link works.
- **Matching.** One request at a time, five minutes each. On accept, both phones show the table
  and the free seat beside the host, and the host's LED blinks blue.
- **Honest status.** "Live", "Updated 12 s ago" or "Offline · data from 2 min ago", from the
  last poll that worked. Simulated buildings say so.
- **An installable app.** Offline shell, push notifications, light and dark themes.

## Tests

| Where | Command | Result |
|---|---|---|
| Backend | `make check` | ruff, mypy `--strict`, 183 passed (29 need Postgres) |
| Backend + Postgres | `make test-db` | 212 passed |
| App | `npx vitest run` | 32 passed |

## Limits

- **One sensor pair per seat.** Someone leaning out of the person sensor's range reads as away.
  The 5 s debounce absorbs fidgeting, not a long stretch.
- **Polling, not push, for the map.** Phones ask every 3 s. Worst case, a seat change takes
  about 11 s to show: 5 s debounce, 2 s sensor interval, 1 s cache, 3 s poll.
- **Two of three buildings are simulated.** Only PCL Table 01 is wired to real sensors.
- **Push on iPhone** needs the app added to the Home Screen first.

Map data © OpenStreetMap contributors (ODbL) via Protomaps. Type: IBM Plex (OFL). Card art:
Muse Image, prompts in `public/cards/cards.json`.
