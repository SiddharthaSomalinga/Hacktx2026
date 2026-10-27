# Synapse

A library seat map fed by desk sensors, with study-partner matching on top. Every seat reading carries `object_present` and `human_present`. A pure state machine in the backend turns them into one of four public states: `open`, `occupied`, `likely_opening` (belongings left with nobody there for 30 s, a "ghost seat"), or `offline`. Students studying the same course can then request an open spot at a host's table. Readings are stored change-only in TimescaleDB, and seat transitions run under `SELECT … FOR UPDATE`, so several API instances can share one database.

Built by 4 people at HackTX 2026, Sat 6 pm → Sun 11:30 am. The tag [`hacktx-2026`](https://github.com/SiddharthaSomalinga/Hacktx2026/tree/hacktx-2026) is what we demoed at 11:30 Sunday; this branch has changed since (docs and cleanup).

| Campus map and demo login | Live floor plan | Study-partner match |
|:---:|:---:|:---:|
| <img src="docs/images/campus_map_login.png" width="260" alt="Campus map and demo login"/> | <img src="docs/images/floorplan_live_seats.png" width="260" alt="Live floor plan"/> | <img src="docs/images/host_study_match.png" width="260" alt="Host study match"/> |
| Open-seat share across PCL, Welch and GDC | Green = open, blue = occupied, yellow = likely opening, grey = offline | Course match and an icebreaker from Muse |

## Real vs. simulated

| Piece | Status |
|---|---|
| Seat sensing | **Real, one sensor.** The prototype has a single IR sensor per seat; those were the parts available at the hackathon. One IR sensor can't tell a person from a bag, so the bridge sends its value as both `object_present` and `human_present` |
| Ghost-seat detection (`likely_opening`) | **Modeled in the backend, not reachable from the prototype.** It needs "object yes, human no", which one IR sensor never reports. `make fake-node` can send it (`1 b`). Planned upgrade: a thermal sensor for the person plus IR for belongings, feeding the two fields the backend already reads |
| Demo hosts | **Simulated** (D56). With `DEMO_HOSTS=true`, `make seed-demo` creates one host per catalog course, and they accept requests after `DEMO_ACCEPT_S` (5 s) |
| Desk installation diagram | **Concept**, below |
| Pulsing blue beacon at the host's seat | **Planned.** The backend returns `blue_blink` for a matched seat; the prototype firmware doesn't read the backend's LED colors yet |
| Map, matching, Muse calls, push | Real |

## Hardware

<p align="center"><img src="docs/images/hardware_prototype.jpg" width="520" alt="Arduino prototype with IR sensor and LEDs"/></p>

The prototype is an Arduino with a Grove shield, one IR sensor on D2, and two LEDs that the firmware drives itself: **green = open, blue = occupied**, matching the map. The firmware ([`firmware/HACKATHON`](firmware/HACKATHON/HACKATHON.ino)) needs 3 consistent reads (sampled every 50 ms) before it switches, and prints a text line, `occupied: true|false`, over USB serial at 115200 baud. [`bridge/arduino_bridge.py`](bridge/arduino_bridge.py) parses that line and posts JSON to `POST /api/readings` with an `X-Node-Key` header, on every change and at least every heartbeat.

```
Arduino (IR + LEDs) --serial text--> bridge (Python) --HTTP JSON--> FastAPI --> TimescaleDB
                                                                        |  \--> Muse (topic, ranking, icebreaker)
                                                                        v
                                                              React PWA (polls every 3 s, web push)
```

**Concept** for a real desk: an object sensor on the desk surface and a presence sensor aimed at the chair, per seat, with one controller per table.

<p align="center"><img src="docs/images/campus_desk_setup.jpg" width="100%" alt="Concept: desk installation"/></p>

## Seat states

The API exposes only the four public states (FR-6). Internally a seat is `open`, `occupied` (a person is there) or `away` (belongings only), and `away` stays public `occupied` until `GHOST_S` has passed:

```python
def public_state(s: SeatState, now: datetime, t: Timers) -> PublicState:
    if is_offline(s, now, t):
        return PublicState.OFFLINE
    if s.state is InternalState.OPEN:
        return PublicState.OPEN
    if s.state is InternalState.OCCUPIED:
        return PublicState.OCCUPIED
    return PublicState.LIKELY_OPENING if now - s.away_since >= t.ghost else PublicState.OCCUPIED
```

- A new reading becomes the seat's state only once it has been stable for `DEBOUNCE_S` (5 s).
- `away_since` is the moment belongings-only started, so the 30 s ghost timer includes the debounce.
- A seat with no reading for `OFFLINE_S` (30 s) is `offline`, whatever it was before.
- The away duration is used here and never returned by the API.
- `now` and the timers are parameters. The domain layer has no clock, database or env access, and a test fails if it imports one.

Every threshold lives in [`backend/app/config.py`](backend/app/config.py) and can be overridden by env var. Transitions happen when a seat is read, when its node reports, or on a 2 s scheduler tick; the tick selects due rows `FOR UPDATE SKIP LOCKED`, so every instance can run the tick. The full state machines (seat, host, request, match) are in [ARCHITECTURE](documentation/ARCHITECTURE.md).

## Matching

A host taps their seat (or scans its QR code) and types what they're studying, e.g. "orgo 1 midterm". A seeker types theirs and gets up to 5 hosts. Meta's Muse Spark (`muse-spark-1.3`) does three things:

| Call | Does |
|---|---|
| `normalize_topic` | Free text → catalog course (`CH 320M`) and concepts |
| `rank_hosts` | Scores hosts against the seeker's topic |
| `icebreaker` | One course-specific opener after a match |

Each call has a 4 s timeout (`AI_TIMEOUT_S`) and a deterministic fallback, and none runs inside a database lock, so a slow or failed AI call never blocks a request. Before a host accepts, the seeker sees only first name and major; the seat location is revealed after accept. Names are never sent to Muse.

## Stack

| Part | Choice |
|---|---|
| Firmware | Arduino C++, Grove shield, IR sensor, two LEDs |
| Bridge | Python, pyserial, httpx |
| Backend | Python 3.12, FastAPI, Pydantic v2, psycopg 3, pywebpush, uv |
| Database | PostgreSQL 16 + TimescaleDB (hypertable, compression, retention) |
| AI | Meta Muse Spark, behind a timeout and a rule-based fallback |
| Frontend | React 19, TypeScript, Vite, MapLibre GL, installable PWA with web push |
| Hosting | Vultr |

## Run it locally

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12), Docker, `make`, and Node 22 or 24 with the npm that ships with it (npm 10+). The database image is 3.2 GB.

```bash
cd backend
make sync db-up db-create     # deps, Postgres + TimescaleDB on :5433, databases ghostseats and ghostseats_test
make vapid-keys               # prints two VAPID_ lines for .env
```

Then write `backend/.env`, which is gitignored:

```bash
DATABASE_URL=postgresql://postgres:ghostseats@localhost:5433/ghostseats
SECRET_KEY=<python3 -c 'import secrets; print(secrets.token_urlsafe(48))'>
NODE_KEY=<python3 -c 'import secrets; print(secrets.token_urlsafe(24))'>
VAPID_SUBJECT=mailto:you@example.com
# VAPID_PUBLIC_KEY=… and VAPID_PRIVATE_KEY=… from make vapid-keys
```

```bash
make db-init seed policies seed-history
make dev                      # API on :8000, live contract at /docs
```

In a second terminal, from the repo root:

```bash
npm ci
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

In a third, act as the hardware: `cd backend && make fake-node`, then type `1 p` for a person, `1 b` for a bag alone, `1 e` for empty, `q` to quit. Seat `t1-s1` changes on the map within a few seconds. Without `MUSE_API_KEY`, matching uses the fallback.

The Vite proxy expects the API on port 8000; if something else holds that port, stop it first.

Real hardware: flash `firmware/HACKATHON`, plug in the Arduino, then from the repo root run `pip install -r bridge/requirements.txt` and `GHOSTSEATS_URL=http://localhost:8000 NODE_KEY=<key from .env> python bridge/arduino_bridge.py`.

## Tests

| Command | Result |
|---|---|
| `cd backend && make check` | ruff, mypy `--strict`, 184 passed, 29 skipped (Postgres tests skip without a DB) |
| `cd backend && make test-db` | 213 passed, including the Postgres repository contract tests |
| `npm test` | 32 passed (Vitest) |
| `npm run build` | type-checks the app and service worker, builds the PWA |

`InMemoryRepository` and `PostgresRepository` pass the same contract suite in `backend/tests/repo_contract/`. `make load-check` runs 500 polling clients and 50 fake nodes against a running API.

## Limitations

- Presence comes from one IR sensor, so the prototype can't produce `likely_opening`. The thermal + IR upgrade is the first thing to build.
- The prototype firmware ignores the LED colors the backend returns, and the backend's LED colors (red for occupied) don't match the firmware and map (blue). The map is the reference (D54).
- Push delivery is at-least-once through a transactional outbox, so a notification can arrive twice.
- The frontend polls every 3 s; there is no WebSocket.
- Demo hosts are simulated, and there is no real account system: sign-in is a demo-user picker.

## Docs

[ARCHITECTURE](documentation/ARCHITECTURE.md) (layers, state machines, push, scaling) · [REQUIREMENTS](documentation/REQUIREMENTS.md) (FR/NFR ids, API contract) · [USER_FLOWS](documentation/USER_FLOWS.md) · [backend README](backend/README.md)

## Team

Built at HackTX 2026 by Sourish, Siddhartha (Sid), Manideep (Mani) and Dina.
