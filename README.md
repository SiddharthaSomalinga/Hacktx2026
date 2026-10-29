# Synapse

[![CI](https://github.com/SiddharthaSomalinga/Hacktx2026/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SiddharthaSomalinga/Hacktx2026/actions/workflows/ci.yml)

A library seat map fed by desk sensors, with study-partner matching on top. Every seat reading carries `object_present` and `human_present`. A pure state machine in the backend turns them into one of four public states: `open`, `occupied`, `likely_opening` (belongings left with nobody there for 30 s, a "ghost seat"), or `offline`. Students studying the same course can then request an open spot at a host's table. Readings are stored change-only in TimescaleDB, and seat transitions run under `SELECT … FOR UPDATE`, so several API instances can share one database.

Built by 4 people at HackTX 2026, Sat 6 pm → Sun 11:30 am. The tag [`hacktx-2026`](https://github.com/SiddharthaSomalinga/Hacktx2026/tree/hacktx-2026) is what we demoed at 11:30 Sunday; `main` has changed since (docs, layout, CI).

**Live:** <https://64.177.55.143.sslip.io>. Pick a demo user, search a course such as "macro econ" and tap Join; a simulated host accepts in about 5 s and the match shows where to go.

https://github.com/user-attachments/assets/41e16989-e90b-4dd9-8c19-8be505fa0224

<p align="center"><sub>Recorded on a local stack. <code>make fake-node</code> stands in for the sensor, the ghost timer is shortened to 15 s, and the first half runs at 4× speed. A person sits (blue), a bag is left alone (blue, then yellow "likely opening"), the person leaves (green); then a seeker asks to join and a simulated host accepts.</sub></p>

| Campus map and demo login | Live floor plan | Study-partner match |
|:---:|:---:|:---:|
| <img src="docs/images/campus_map_login.png" width="260" alt="Campus map and demo login"/> | <img src="docs/images/floorplan_live_seats.png" width="260" alt="Live floor plan"/> | <img src="docs/images/host_study_match.png" width="260" alt="Host study match"/> |
| Open-seat share across PCL, Welch and GDC | Green = open, blue = occupied, yellow = likely opening, grey = offline | Course match and an icebreaker from Muse |

## Real vs. simulated

| Piece | Status |
|---|---|
| Seat sensing | **Real, one sensor.** The prototype has a single IR sensor per seat; those were the parts available at the hackathon. A single IR beam can't distinguish a person from a bag, so the bridge sends its value as both `object_present` and `human_present` |
| Ghost-seat detection (`likely_opening`) | **Modeled in the backend, not reachable from the prototype.** It needs "object yes, human no", which one IR sensor never reports. `make fake-node` can send it (`1 b`). Planned upgrade: a thermal sensor for the person plus IR for belongings, feeding the two fields the backend already reads |
| Demo hosts | **Simulated.** With `DEMO_HOSTS=true`, `make seed-demo` creates one host per catalog course, and they accept requests after `DEMO_ACCEPT_S` (5 s) |
| Desk installation diagram | **Concept**, below |
| Pulsing blue beacon at the host's seat | **Planned.** The backend returns `blue_blink` for a matched seat; the prototype firmware doesn't read the backend's LED colors yet |
| Map, matching, Muse calls, push | Real |

## Hardware

<p align="center"><img src="docs/images/hardware_prototype.jpg" width="520" alt="Arduino prototype with IR sensor and LEDs"/></p>

The prototype is an Arduino with a Grove shield, one IR sensor on D2, and two LEDs that the firmware drives itself: **green = open, blue = occupied**, matching the map. The firmware ([`firmware/HACKATHON`](firmware/HACKATHON/HACKATHON.ino)) needs 3 consistent reads (sampled every 50 ms) before it switches, and prints a text line, `occupied: true|false`, over USB serial at 115200 baud. [`bridge/arduino_bridge.py`](bridge/arduino_bridge.py) parses that line and posts JSON to `POST /api/readings` with an `X-Node-Key` header, whenever the reading changes, and every 2 s regardless.

```
Arduino (IR + LEDs) --serial text--> bridge (Python) --HTTP JSON--> FastAPI --> TimescaleDB
                                                                        |  \--> Muse (topic, ranking, icebreaker)
                                                                        v
                                                              React PWA (SSE: GET /api/live, web push)
```

**Concept** for a real desk: an object sensor on the desk surface and a presence sensor aimed at the chair, per seat, with one controller per table.

<p align="center"><img src="docs/images/campus_desk_setup.jpg" width="100%" alt="Concept: desk installation"/></p>

## Seat states

The API exposes only the four public states. Internally a seat is `open`, `occupied` (a person is there) or `away` (belongings only), and `away` stays public `occupied` until `GHOST_S` has passed:

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
- The away duration only feeds this decision; the API never exposes it.
- `now` and the timers are parameters. The domain layer has no clock, database or env access, and a test fails if it imports one.

Every threshold lives in [`backend/app/config.py`](backend/app/config.py) and can be overridden by env var. Transitions happen when a seat is read, when its node reports, or on a 2 s scheduler tick; the tick selects due rows `FOR UPDATE SKIP LOCKED`, so every instance can run the tick. The full state machines (seat, host, request, match) are in [ARCHITECTURE](docs/ARCHITECTURE.md).

## Matching

A host taps their seat (or scans its QR code) and types what they're studying, e.g. "orgo 1 midterm". A seeker types theirs and gets up to 5 hosts. Meta's Muse Spark (`muse-spark-1.3`) does three things:

| Call | Does |
|---|---|
| `normalize_topic` | Free text → catalog course (`CH 320M`) and concepts |
| `rank_hosts` | Scores hosts against the seeker's topic |
| `icebreaker` | One course-specific opener after a match |

Each call has a 4 s timeout (`AI_TIMEOUT_S`) and a deterministic fallback, and none runs inside a database lock, so a slow or failed AI call never blocks a request. Before a host accepts, the seeker sees only first name and major; the seat location is revealed after accept. Names are never sent to Muse.

## Running several instances

Each instance runs its own scheduler tick and push sender against the shared database, so Postgres does the coordinating. The push sender claims its work with:

```sql
SELECT id, user_id, kind, payload, attempts FROM notification_outbox
WHERE sent_at IS NULL ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED
```

- `sent_at IS NULL` is the queue: a row leaves it when its sender commits.
- `FOR UPDATE` keeps a claimed row away from every other sender until that commit.
- `SKIP LOCKED` sends the other senders to the next free rows rather than making them wait.
- The push goes out before the commit. A process that dies between the two leaves the row unsent, and another sender pushes it again: at-least-once.
- The row itself was inserted in the same transaction as the state change behind it, so a push that fails never undoes a transition.

Transitions re-read their row `FOR UPDATE` and re-check before acting, and partial unique indexes (one pending request per search, one active match per person) refuse a duplicate even if a lock were missing. [CONCURRENCY](docs/CONCURRENCY.md) covers each mechanism and the five Postgres tests that fail when its lock is removed.

## Live updates

An open app holds one Server-Sent Events stream, `GET /api/live`. Over it come the campus counts, the plan of whichever building is on screen, and, once you're logged in, the names of your screens that need refetching. A write on any instance reaches streams on every instance through Postgres `NOTIFY`, sent by the transaction itself:

```sql
SELECT pg_notify('synapse_live', p) FROM unnest(%s::text[]) AS p   -- just before COMMIT
```

- `NOTIFY` is transactional: a write that rolls back sends nothing, so no client refetches for a change that never happened.
- Each process `LISTEN`s on one extra connection and keeps one copy of each watched snapshot, rebuilt at once on a hint and every `LIVE_CHECK_S` (1 s) regardless. The periodic rebuild catches what changes with time alone (the ghost timer, a sensor going silent) and anything a lost notification missed. A hint only says when to look again.
- The work is one rebuild per watched building per process, whatever the number of phones. A changed snapshot is written to every stream. A stream that reads slowly gets the newest state, never a backlog.
- Snapshot events are byte for byte the bodies of the polling GETs. Per-user events name topics only (`["inbox","me"]`), never ids or names; the client refetches through the usual endpoints and their checks.
- The repository's writers record the hints, not the services. `save_seat_state` requires the seat's computed change, so code that writes seat state can't forget to hint. A seeded random walk of readings, clock jumps and user actions checks the rest. After every step, any user whose GET responses changed must have received a hint.
- If the stream can't vouch for its data for 6 s, the app polls every 3 s as before.

## Stack

| Part | Choice |
|---|---|
| Firmware | Arduino C++, Grove shield, IR sensor, two LEDs |
| Bridge | Python, pyserial, httpx |
| Backend | Python 3.12, FastAPI, Pydantic v2, psycopg 3, pywebpush, uv |
| Database | PostgreSQL 16 + TimescaleDB (hypertable, compression, retention) |
| AI | Meta Muse Spark, behind a timeout and a rule-based fallback |
| Frontend | React 19, TypeScript, Vite, MapLibre GL, installable PWA with web push |
| Observability | JSON logs with a request id per request, Prometheus `/metrics` behind a token |
| Hosting | Vultr |

## Try it

With Docker, from the repo root:

```bash
docker compose up --build     # same as: make demo
```

Then open <http://localhost:8000> (or set `PORT=8001` first if 8000 is taken). The first start pulls the 3.2 GB database image and builds the app image. A one-shot `init` job creates the schema, seeds three buildings with a day of history and one demo host per course, and generates the keys into a Docker volume. Demo hosts are on, so a search and Join ends in a match with nobody else around. To act as the sensor, run `docker compose run --rm fake-node` in a second terminal and type `1 p`, `1 b` or `1 e`. `docker compose down -v` deletes the data and the keys.

## Run it locally

For development, run each piece on its own. You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12), Docker, `make`, and Node 22 or 24 with the npm that ships with it (npm 10+). The database image is 3.2 GB.

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

In a second terminal:

```bash
cd frontend
npm ci
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

In a third, act as the hardware: `cd backend && make fake-node`, then type `1 p` for a person, `1 b` for a bag alone, `1 e` for empty, `q` to quit. Seat `t1-s1` changes on the map within a few seconds. Without `MUSE_API_KEY`, matching uses the fallback.

The Vite proxy sends `/api` to `http://localhost:8000`. If the API runs elsewhere, start the dev server with `API_PROXY_TARGET`, e.g. `API_PROXY_TARGET=http://localhost:8001 npm run dev`.

Real hardware: flash `firmware/HACKATHON`, plug in the Arduino, then from the repo root run `pip install -r bridge/requirements.txt` and `SYNAPSE_URL=http://localhost:8000 NODE_KEY=<key from .env> python bridge/arduino_bridge.py`.

## Tests

| Command | Result |
|---|---|
| `cd backend && make check` | ruff, mypy `--strict`, 256 passed, 44 skipped (Postgres tests skip without a DB) |
| `cd backend && make test-db` | 300 passed, including the Postgres repository contract, concurrency and `NOTIFY` tests |
| `cd frontend && npm test` | 50 passed (Vitest) |
| `cd frontend && npm run build` | type-checks the app and service worker, builds the PWA |
| `cd frontend && npm run e2e` | Playwright against the compose stack, 5 tests: a request, the host's accept, and the table appearing for the seeker only after it; a seat change on screen with no polling; no `/api/me` polling when logged out; the inbox filled by a hint; polling when the stream is blocked ([TESTING](docs/TESTING.md#automated-checks)) |

`InMemoryRepository` and `PostgresRepository` pass the same contract suite in `backend/tests/repo_contract/`.

## Load

`cd backend && make load-check` runs simulated phones against a running API, then removes its test data. `--mode poll` polls the map the way the app used to (every 3 s, with `If-None-Match`); `--mode sse` holds `/api/live` open. With `--setup`, a probe seat flips every 12 s. The delay is from the probe's readings response to the moment a phone shows the new state.

Apple M1 (8 GB), API as 4 uvicorn workers with JSON logs and metrics on, Postgres in Docker (4 CPUs, 2 GB), the generator on the same laptop. Ranges are over 3 runs of 60 s.

| 1000 phones, quiet building (only the probe changes) | Polling | Stream |
|---|---|---|
| Change on screen, p50 | 1.64–1.95 s | 67–73 ms |
| Change on screen, p95 | 3.24–3.47 s | 94–113 ms |
| Phone requests | 659–665/s | 17/s (the connects) |
| Server CPU, mean, all workers | 31–41% of a core | 12–14% |
| Database transactions | 29–31/s | 19/s |

| 2000 phones, 50 nodes rewriting a 200-seat floor every 2 s | Polling | Stream |
|---|---|---|
| `POST /api/readings`, p50 | 0.36–1.5 s, nodes starved (720–1071 of ~1460 posts) | 35–38 ms, all posts |
| Change on screen, p95 | 6.4–10.1 s | 1.19–1.46 s |
| Flips a phone never showed | 253–1996 | 0 |
| Received per phone | 2.1–3.2 KB/s | 9.4–9.9 KB/s |

- Polling at 2000 phones broke the way it did before: about 2000 connections each making a request every 3 s. The same 2000 phones as streams cost the server 35–43% of a core.
- Under churn the stream is slower than in a quiet building because each building's snapshot goes out at most once per `LIVE_CHECK_S`. A change waits up to 1 s for its turn.
- The stream costs about three times the bytes under churn: every update is the whole 200-seat floor plan, about once a second. Sending only the seats that changed would remove most of that.
- At 4000 streams under the same churn, streams went silent for more than 9 s and dropped (14,178 read timeouts), with the server at about one core writing snapshots. At 8000, connects failed against the laptop's file limits (`kern.maxfiles` 30720, two descriptors per phone with both ends local). So the ceiling here is the bytes, between 2000 and 4000 streams. A run with the generator on another machine is the next step.

## Limitations and next steps

- Presence comes from one IR sensor, so the prototype can't produce `likely_opening` (below). **Next:** the thermal + IR pair from the table above.
- The prototype firmware ignores the LED colors the backend returns, and the backend's LED colors (red for occupied) don't match the firmware and map (blue). The map is the reference. **Next:** agree the LED colors with the hardware side, then have the firmware show what the backend returns, which also brings the matched-seat beacon.
- Sign-in is a demo-user picker, and demo hosts are simulated. **Next:** university SSO behind the same auth service.
- Push is at-least-once, so a notification can arrive twice; the service worker tags it by URL, so the second replaces the first on screen.
- Live updates send whole snapshots, so a busy building costs about three times the bytes of polling, and one laptop topped out between 2000 and 4000 streams (Load). **Next:** per-seat deltas.
- The load numbers come from one laptop with the generator on it. They show the relative cost of the two modes, not the capacity of a server.
- Instances read time from their own clocks, so clock skew between servers shifts deadlines by the skew ([CONCURRENCY](docs/CONCURRENCY.md)).
- The two servers have no load balancer. Server 2 is a hot backup at its own address, so failing over means changing the URL.

## At the hackathon

Two things went wrong that shaped what's here.

- **The venue Wi-Fi blocked database ports and SSH.** Outbound 5432 and Tiger's port timed out even to an unrelated host while HTTPS worked. The app itself was unaffected: phones and the bridge talk only to the public HTTPS URL, and the servers reach Tiger from Vultr's network. What did break was operator work from the laptop, applying the schema and deploying over SSH, so that ran over a phone hotspot.
- **The parts came down to one IR sensor per seat.** The design called for two signals per seat, an object and a person (the original plan was a micro switch and a Bluetooth presence link). One IR sensor reads a bag and a person the same way, so the bridge sends its one value as both, and the ghost-seat state the project is built around can't come from the prototype. The backend kept the two-signal model, so the hardware fix is a second sensor, with no backend change.

## Design

| Doc | Covers |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Layers, the four state machines, push, scaling to several instances |
| [CONCURRENCY](docs/CONCURRENCY.md) | Row locks, `SKIP LOCKED`, the outbox, and the tests that fail without them |
| [REQUIREMENTS](docs/REQUIREMENTS.md) | FR/NFR ids, the API contract, config keys, the data model |
| [USER_FLOWS](docs/USER_FLOWS.md) | Every screen and what the user can do on it |
| [TESTING](docs/TESTING.md) | Features with manual test steps |
| [backend README](backend/README.md) | Running, testing and deploying the API |

[PLAN](docs/PLAN.md) (every design decision, numbered, and the open questions) and [PROGRESS](docs/PROGRESS.md) (what was run, per session) are the build log.

## Team

Built at HackTX 2026 by Sourish, Siddhartha (Sid), Manideep (Mani) and Dina.
