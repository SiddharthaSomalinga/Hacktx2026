# Ghost Seats — Architecture

How the system is built. **What** it must do lives in `REQUIREMENTS.md` (v1.1)
and `USER_FLOWS.md`. This file cites requirement ids (`FR-24`) and decision
numbers (`D18`, see the decision log in `PLAN.md`) instead of restating them.

## 1. System at a glance

```
 seat: micro switch (object) + HC-05 link (human) + LED
        │ digital pins
 ┌──────▼───────┐  USB serial 115200   ┌──────────────┐  HTTPS + X-Node-Key  ┌──────────────────────────┐
 │ Arduino R4   │ ── R,10,00 ────────► │ Raspberry Pi │ ─ POST /api/readings►│ Backend (FastAPI) × N    │
 │ firmware/    │ ◄─ L,Y,G ─────────── │ bridge/      │ ◄─ {leds:{…}} ───────│ backend/                 │
 └──────────────┘  (REQUIREMENTS §10.3)└──────────────┘    every 2 s         │ engine · matching · AI   │
   local mode after 10 s silence (HW-5)                                      │ scheduler tick · outbox  │
                                                                             └──┬──────────▲─────────┬──┘
                                                         SQL (primary + read)   │          │ JSON    │ web push
                                                                 ┌──────────────▼───┐ ┌────┴───────┐ │ (VAPID)
                                                                 │ Tiger Data:      │ │ Web client │◄┘
                                                                 │ Postgres +       │ │ + PWA      │
                                                                 │ Timescale        │ │ (phones)   │
                                                                 └──────────────────┘ └────────────┘
```

The backend is the single source of truth for seat state. The only exception
is the node's local fallback (HW-5).

### Hardware parts (locked)

| Part | Signal | Notes |
|---|---|---|
| Micro switch under a hinged seat pad | `object_present` | A person or a backpack presses it |
| HC-05 Bluetooth module | `human_present` | The link drops when the student walks away; a backpack alone reads false |
| Arduino UNO R4 | — | Samples every 500 ms (HW-1), drives the LEDs, speaks the serial protocol |
| Raspberry Pi | — | Runs `bridge/`; serial ⇄ HTTPS (HW-7..10) |

## 2. Repository layout (target)

```
/
├── documentation/             # REQUIREMENTS · USER_FLOWS · ARCHITECTURE · PLAN · PROGRESS
├── backend/                   # FastAPI service (backend role, v1backend)
│   ├── app/
│   │   ├── main.py            # create_app(settings, services); static mount of frontend/dist
│   │   ├── config.py          # every key in REQUIREMENTS §8; validated at startup (fail fast)
│   │   ├── wiring.py          # builds the real adapters from config
│   │   ├── worker.py          # scheduler tick + outbox sender (a thread per instance)
│   │   ├── domain/            # pure logic, no I/O (§3)
│   │   ├── services/          # use cases, lifecycle coordinator, ports.py, facts.py
│   │   ├── adapters/          # repo_postgres, history_sql, ai_fallback, push_webpush, db, clock
│   │   └── interface/         # schemas.py (the contract), deps.py, errors.py, routes/
│   ├── sql/                   # schema.sql, seed.sql
│   ├── scripts/               # db, fake_node, seed_history, seat_qr, vapid_keys, load_check
│   ├── tests/                 # domain/, api/, repo_contract/, fakes.py (in-memory repository)
│   ├── deploy/                # compose.yaml, provision.sh, deploy.sh (rolling, D36)
│   ├── Dockerfile             # API + worker + frontend/dist; built from the repo root
│   └── pyproject.toml · uv.lock · Makefile · .env.example · .gitignore
├── bridge/                    # arduino_bridge.py: serial ⇄ POST /api/readings, env config (D39)
├── firmware/                  # HACKATHON/HACKATHON.ino: one IR sensor (Q14) (D39)
└── frontend/                  # Vite + React + PWA; still at the repo root on v1final (D6, D40)
```

## 3. Backend layers

Dependencies point inward: `interface → services → domain`. Adapters implement
ports declared in `services/ports.py`. Domain code takes `now` and a `Timers`
value as parameters. It never reads a clock, env var, database or network,
and an import-guard test enforces that.

| Module | Responsibility | Requirements |
|---|---|---|
| `domain/types.py` | Enums, frozen records, `Timers` | §6 status values |
| `domain/seat_engine.py` | `candidate_of`, `apply_reading`, `public_state`, `led_for`, `human_present_now`, `absent_for` (§4) | FR-1..7, 22 |
| `domain/simulation.py` | `simulated_state(seat_id, now, busyness, t)` (§9) | FR-47 |
| `domain/geometry.py` | Seat distance, nearest open seat, haversine | FR-11, 37, 39 |
| `domain/recommend.py` | Widening recommendation with `level` (§5) | FR-11 (D21) |
| `domain/matching.py` | `host_status`, `group_of`, `offered_group`, `aggregate`, `keyword_overlap`, `rank` | FR-24, 29, 30 |
| `domain/lifecycle.py` | `advance_host_session`, `advance_search`, `advance_match`; they return step objects (§6) | FR-25..27, 31..35, 41, 42 |
| `domain/catalog.py` | UT course codes → title and subject; keyword aliases | FR-18, 19 |
| `domain/topic_rules.py` | Fallback normalizer, fallback icebreaker, `card_key_for` | §9 |
| `domain/notifications.py` | Which transition emits which outbox `kind` and payload (first name and major only before accept, D43) | FR-52, 53 |
| `services/ports.py` | `Repository`, `TopicAI`, `Notifier`, `Clock` protocols | — |
| `services/lifecycle.py` | Applies `advance_*` decisions under row locks; the one place where host, search and match transitions trigger each other | NFR-2, D29 |
| `services/facts.py` | Per-transaction snapshot answering "what state is this seat" and "is this host findable", identically for every service | FR-24 |
| `services/ai_guard.py` | Wraps any `TopicAI`: an exception or out-of-bounds output becomes the deterministic fallback | NFR-3 |
| `services/topics.py` | `topic_cache` in front of `normalize_topic` | §9 |
| `services/*.py` | `readings`, `map`, `history`, `auth`, `host`, `search`, `requests`, `match`, `safety`, `push`, `scheduler` | — |
| `adapters/repo_postgres.py` | All SQL, parameterized only | — |
| `adapters/ai_fallback.py`, `ai_muse.py` | `TopicAI` implementations (§8) | NFR-3 |
| `adapters/push_webpush.py` | `Notifier` over `pywebpush` | FR-51..53 |
| `interface/routes/*.py` | Parse, call one service, return. No business `if`s | §7 |

**Ports and fakes (D3).** `Repository` has two implementations,
`PostgresRepository` and `InMemoryRepository` (`tests/fakes.py`). Both pass
one shared conformance suite in `tests/repo_contract/`. The in-memory
implementation snapshots its state when a transaction starts and restores it
on rollback. Domain and service tests run against the fake; row-lock
behaviour and SQL are tested against Postgres.

## 4. Seat state engine (FR-1..7)

Internal states: `open`, `occupied`, `away`. `away` never leaves the backend (FR-6).

```
reading ──► candidate:   human            → occupied
                         object ∧ ¬human  → away
                         ¬object ∧ ¬human → open

candidate ≠ candidate_state     → candidate_state := candidate, candidate_since := now
now − candidate_since ≥ DEBOUNCE_S and candidate_state ≠ state
                                → state := candidate_state, state_since := now
                                  (entering away: away_since := candidate_since)
every reading                   → last_seen := now; human → last_human := now; object → last_object := now
```

Read-time projection. Offline is never stored; it is computed:

| Condition (first match wins) | Public state | LED |
|---|---|---|
| `now − last_seen ≥ OFFLINE_S` | `offline` | `off` |
| `blink_until > now` | (state below) | `blue_blink` |
| `state = open` | `open` | `green` |
| `state = occupied` | `occupied` | `red` |
| `state = away`, `now − away_since < GHOST_S` | `occupied` | `red` |
| `state = away`, `now − away_since ≥ GHOST_S` | `likely_opening` | `yellow` |

**Presence (D18).**
- `human_present_now = now − last_human ≤ HUMAN_FRESH_S`.
- `absent_for = now − last_human`.
- Belongings (`object_present`) never count as presence. This one rule drives FR-22, 24, 25, 26 and 41.

### Ingest sequence (D29, D31)

```
POST /api/readings  {node_id, readings[]}   header X-Node-Key
  └─ services.readings.ingest(node_id, readings, now)            one transaction
       ├─ nodes.last_seen := now
       ├─ per seat: SELECT seat_state … FOR UPDATE
       │    ├─ gap: now − last_seen > OFFLINE_S → INSERT marker (online=false) at last_seen + OFFLINE_S
       │    ├─ (object, human) ≠ last stored pair → INSERT seat_readings row (change-only)
       │    ├─ apply_reading → UPDATE seat_state
       │    └─ leds[seat_id] := led_for(state, now)
       └─ advance host session and match linked to these seats (presence rules, §6)
  ◄─ {leds: {seat_id: color}}        unknown seat_id: skipped and logged
```

## 5. Map and recommendations (FR-8..13)

**Snapshot (D32).**
- `map` builds one snapshot per building: real seats projected with `public_state(now)`, simulated seats through `simulated_state` (§9).
- The snapshot is cached in memory for `MAP_CACHE_S` and carries a strong `ETag`. `If-None-Match` → `304`.
- The building list and building detail are both served from snapshots, read from the replica connection when `DATABASE_READ_URL` is set.
- The cache is derived data, so any instance can rebuild it (NFR-8).

**Recommendation (D21).**
- `recommend(seats, selection)` tries `table` → `floor` → `building`.
- At each level it takes the open seat nearest the selection; only if none is open does it take the nearest `likely_opening` seat (labeled). Ties go to the lowest position.
- If the building has neither → `{full: true, nearest_building_id}`, chosen by haversine over `buildings.lat/lng` among buildings with open seats.
- The response always carries `level`, so the client can say "nothing open at this table, here's the closest seat".

`GET /api/buildings/:id` shape: REQUIREMENTS §7.

## 6. Social flows — state machines

Pure `advance_*` functions in `domain/lifecycle.py` decide transitions from
stored timestamps. Services apply them under row locks
(`SELECT … FOR UPDATE`) in one transaction (NFR-2, D29).

| Trigger | Advances |
|---|---|
| Any read or write of the entity | that entity |
| Sensor ingest (§4) | host sessions and matches linked to the seat → presence rules |
| Scheduler tick every `SCHEDULER_TICK_S` (§14) | rows past a time-only deadline: request expiry, match expiry, confirm grace |

### Host session (FR-20..28, D17, D18, D20, D23, D24)

```
UI: turn on "Open to study partners" (client only) → link → topic
POST /host/link  requires human_present_now (FR-22) and no active search or seeker-side match (FR-50)
                 → session(open, muted=false, started_at=now, expires_at=now+SESSION_MAX_S)

status, computed and never stored (first match wins; exposed as /api/me host.status + hidden_reason):
  ended                   ended_at set
  hidden needs_topic      topic not set
  hidden confirm_pending  now ≥ expires_at
  hidden in_match         an active match
  hidden away             ¬human_present_now          → pending request skipped (FR-25)
  hidden muted            muted
  hidden table_full       the host's table has no open seat
  findable                otherwise

ends (ended_at, end_reason):
  toggled_off   POST /host/toggle {open:false}
  no_person     absent_for ≥ HOST_END_S                    ingest, read
  unconfirmed   now ≥ expires_at + CONFIRM_GRACE_S         tick, read
confirm:  POST /host/confirm while confirm_pending → expires_at := now + SESSION_MAX_S
mute:     POST /host/mute {muted}; decline {mute:true} = silent decline + muted (D20)
outbox:   confirm_needed when confirm_pending starts (tick); session_ended on no_person / unconfirmed
```

### Search and request cascade (FR-29..36, D15, D19, D22)

```
POST /search {topic_raw, group?}
   already_hosting if a live host session exists (FR-50)
   topic normalized (§8); findable hosts (incl. simulated) not blocked either way are grouped:
      same_course: equal non-null course_code      related: equal subject, different course
   offered_group := group ?? (same_course if it has any host, else related)
   has_real_hosts := offered group contains a non-simulated host
   → search(active, offered_group, tried = [])           nothing is sent yet

POST /search/:id/join   no_real_hosts if ¬has_real_hosts; rate_limited per FR-34; then advance

advance_search(now):
   pending request:
      now ≥ expires_at                               → expired
      host no longer findable (away, muted, ended…)  → skipped (FR-25)
      else                                           → wait
   no pending request and the search has been joined (tried ≠ []):
      candidates := findable real hosts in offered_group, ∉ tried, not blocked either way   (recomputed, D15)
      ranked by rank_hosts (AI, keyword-overlap fallback, FR-30)
      |tried| ≥ MAX_HOSTS_PER_SEARCH or none left    → exhausted        outbox search_exhausted
      else → request(pending, expires_at = now + REQUEST_TIMEOUT_S) to the top; tried += it
                                                                        outbox request_received
   decline / "Not now"   → declined (silent, FR-36) → advance
POST /search/:id/cancel  → cancelled; pending request cancelled (FR-35)
```

The cascade never leaves `offered_group` and never sends to a simulated host.

**AI ranking runs outside the lock.** The service reads candidates, ranks them
(≤ `AI_TIMEOUT_S`), then locks the search, re-checks that it still needs a
send, and sends to the highest-ranked candidate that is still findable. A slow
AI call never holds a row lock.

**Database guarantees** (partial unique indexes):
- One active search per seeker.
- One pending request per search.
- One live host session per user.
- One active match per host session and per seeker.

Two concurrent advances can therefore produce at most one request.

### Match (FR-37..42, D18, D25)

```
accept (host): icebreaker via AI BEFORE the transaction (≤ AI_TIMEOUT_S, fallback)
   tx: request pending → accepted; search → matched
       match(active, expires_at = now + MATCH_TIMEOUT_S,
             assigned_seat = open seat at the host's table nearest the host's seat (FR-37),
             card_key = card_key_for(subject))
       host seat blink_until := now + BLINK_S                           outbox request_accepted (seeker)
active:
   arrived (seeker)                       → completed; blink_until := now + BLINK_S (FR-40)
   cancel (either side)                   → cancelled                    outbox match_cancelled (other side)
   host absent_for ≥ HOST_LEAVE_CANCEL_S  → cancelled (ingest, read)     outbox match_cancelled (both)
   now ≥ expires_at                       → expired (tick, read)         outbox match_expired (both)
GET /matches/:id (both sides): assigned seat no longer open → alt_seat_id = nearest open seat, same floor (FR-39, D25)
```

Open: what accept does when the host's table has no open seat at that instant
(Q13 in PLAN).

## 7. Auth, safety and privacy (FR-14..16, 43..46, 50, 53; NFR-7)

- **Users:** demo-user picker. `POST /api/login {user_id}` sets a signed session cookie (Starlette `SessionMiddleware`, `SECRET_KEY`, HttpOnly, SameSite=Lax). `deps.current_user` → 401 `not_logged_in`. SSO would replace only the `auth` service and `deps` (NFR-7).
- **Nodes:** the `X-Node-Key` header is compared in constant time with `NODE_KEY` → 401 `invalid_node_key`.
- **One role at a time (FR-50):** `already_hosting` and `already_searching` (409), enforced in the services and backed by the unique indexes in §6.
- **Input:** Pydantic bounds every field (`topic_raw` ≤ 200 chars, `about_me` ≤ 280, `reason` ≤ 500). SQL is parameterized only.
- **Prompt injection:** `about_me` reaches only `rank_hosts`, whose output is validated as integers 0–100. The icebreaker prompt receives topics only, and its output is capped at 140 chars. User text never reaches a prompt whose output is displayed verbatim.
- **Blocks:** filtered in both directions in the candidate query; a report also inserts a block (FR-45).
- **Names** are joined only for an accepted match (FR-43). Push payloads follow the same rule (FR-53, §14).
- **Logging:** method, path, status, duration; errors with context. Never logged: `NODE_KEY`, cookies, `MUSE_API_KEY`, VAPID keys, push endpoints.

## 8. AI adapter (REQUIREMENTS §9, NFR-3)

```python
class TopicAI(Protocol):                     # services/ports.py
    def normalize_topic(self, text: str) -> Topic: ...
    def rank_hosts(self, seeker: Topic, hosts: list[HostTopic]) -> dict[str, int]: ...
    def icebreaker(self, a: Topic, b: Topic) -> str: ...
```

- **`FallbackAI`** is deterministic:
  - `catalog.py` course codes and keyword aliases, plus a course-code regex. UT departments can contain spaces, e.g. `C S 314`.
  - Ranking by Jaccard keyword overlap.
  - The REQUIREMENTS §9 template icebreaker.
- **`MuseAI`** (`adapters/ai_muse.py`, D38) wraps Muse Spark over Meta's OpenAI-compatible Model API: a strict `json_schema` per call (catalog codes and subjects as enums, host ids aliased `h1…hN`), `reasoning_effort: "minimal"`, an `AI_TIMEOUT_S` timeout, no retries, replies re-validated with Pydantic. Any timeout, HTTP error or invalid output raises `MuseError`, and `GuardedAI` answers with `FallbackAI`. Callers never see an AI failure. `make muse-check` makes one live call per function.
- `normalize_topic` results are cached in `topic_cache`, keyed by lowercased, whitespace-collapsed text.
- **Card images** are pre-generated with Muse Image (one per subject plus a generic one; no people, no text) and shipped as static files in `frontend/public/cards/`. `card_url = /cards/<card_key>.png`.

## 9. Simulation (FR-47, 48, D22)

- Simulated seats have no `seat_state` rows.
- `simulated_state` hashes `f"{seat_id}:{slot}"` (sha256 → uniform [0, 1)), with `slot = floor(epoch_s / SIM_SLOT_S)`, and maps the result to a state through thresholds set by the building's `busyness`. The result is deterministic per slot, so every client and every instance agrees.
- Seeded simulated host sessions count in search aggregates and are always findable. They never receive requests, because the cascade filters `is_simulated`.

## 10. History — Tiger Data (FR-49, D31, D33)

- **Storage.** `seat_readings` is a Timescale hypertable on `time`, change-only, with offline markers (REQUIREMENTS §6). A seat's state at time *t* is its latest row at or before *t*.
- **One query, two callers.** The SQL function `open_hourly(building, since, until, offline)` in `sql/schema.sql` computes hourly average open seats. The API (`GET /api/buildings/:id/history`, last `HISTORY_WINDOW_H`) and the rollup job both call it, so they cannot disagree. Its steps:
  1. Take each seat's row in force at `since`, plus every change inside the window.
  2. Compute `lead()` over **all** rows, so an open interval ends at the change that ended it.
  3. Keep the open intervals; clip them to the window and to `last_seen + OFFLINE_S`, because a silent seat's state is unknown after that.
  4. Sum open seconds per hour. `LEAST`/`GREATEST` skip NULLs in Postgres, so hours with no interval are filtered out explicitly rather than counted as fully open.
- **Rollup and retention (Q12).**
  - A Timescale job (`add_job`, hourly) calls `rollup_open_hourly`, which stores completed hours in `building_open_hourly` and is idempotent.
  - `add_compression_policy` compresses raw chunks older than a day.
  - `add_retention_policy` drops raw rows after `READINGS_RETENTION_DAYS` (30); the hourly table is kept.
  - `make policies` applies all three, idempotently.
- **Why not Toolkit `state_agg` (D33).**
  - The U2 probe ran locally on TimescaleDB 2.31 with Toolkit 1.26: both install, and `state_agg` works inside a continuous aggregate.
  - But a `state_agg` only measures between its own rows. With change-only storage, a seat that stays open for hours has no rows in those hours, so per-hour aggregates score them as zero. In the probe, `duration_in` returned 30 min of "open" where the window held 75.
  - Fixing that needs gap-filling across buckets. The window function is exact and needs no extension, so Tiger Data only has to provide TimescaleDB itself.
- **Seeding.** `scripts/seed_history.py` writes change-only rows for seats with no readings in the window. It never deletes, so it is safe on a live database.
- **Verification.** The repository conformance suite runs the same scenarios against the in-memory reference and against Postgres (including carry-in from before the window, silent-seat capping and the partial current hour). That suite caught two SQL bugs the in-memory tests could not (PROGRESS, Session 3).

## 11. Deployment topology (D5, D32)

```
 phones / PWA ──HTTPS──► load balancer ──► FastAPI × N (API + frontend/dist + worker thread each)
 Pi bridge ──HTTPS + X-Node-Key──┘                 │ primary: writes, locks      │ read URL: map, history, recommend
                                                   ▼                             ▼
                                             Tiger Data primary ───────► read replica (optional)
 dev:  Vite :5173 ──proxy /api──► uvicorn :8000
```

- **One origin.** The session cookie stays SameSite=Lax with no CORS, and the service worker scope covers the app.
- **N instances** are safe because no state of record lives in memory (NFR-8). The scheduler uses `SKIP LOCKED` (§14), and caches are derived (§5).
- **Connection budget (D34).** Every process opens a primary pool of `DB_POOL_SIZE` (default 5), plus a replica pool when `DATABASE_READ_URL` is set. Processes × instances × pools × `DB_POOL_SIZE` must stay below the database's `max_connections`. The local Timescale image allows 25, and 4 workers × 5 peaked at exactly 20 under load.
- **Outages (D35).** Connection failures become `Unavailable` in the repository and a 503 `database_unavailable` with `Retry-After: 5` at the API, after at most the 5 s pool wait. `/api/health` reports `db: false`.
- **Host (D36, D37).** Two Vultr Cloud Compute instances in New Jersey behind a Vultr Load Balancer (Auto SSL, health check `GET /api/health`), on a `.tech` domain whose DNS is on Vultr. Deploys roll one instance at a time. Fallback: a laptop behind a `cloudflared` tunnel.
- **Network.** The Pi and the phones use the public URL. A phone hotspot is the backup network.

## 12. Frontend integration map (frontend role)

| Today (`src/main.jsx` mock) | Replace with | Notes |
|---|---|---|
| `buildings` constant | `GET /api/buildings`, polled | The mock's `likely` key → API `likely_opening`, mapped once in `src/api.js`. `short`, `accent`, `note` stay frontend-only, keyed by building id |
| `initialSeats` + 9 s fake toggle | `GET /api/buildings/:id` every `POLL_WEB_S` with `If-None-Match` | Shape in REQUIREMENTS §7 |
| Hardcoded recommendation card | `GET /api/recommend?building_id&floor&table_id` | Pulsing outline (FR-12); message per `level` |
| "Demo login picker coming next" | `GET /api/demo-users`, `POST /api/login`, `GET /api/me`, `POST /api/logout` | `/me` restores state after reload |
| `handleTopicSubmit` fake normalizer | `POST /api/search` | Quick login keeps the typed topic (FR-18). Shows `label`, groups, Join only if `has_real_hosts`, and the two empty states |
| `requestMatch` toast | `POST /api/search/:id/join`, poll `GET /api/search/:id` | "No one's free right now" on `exhausted`; optional related retry (FR-54) |
| Host toggle | Host setup: toggle (client) → link → `POST /api/host/topic` | Host panel: `hidden_reason`, mute/unmute, confirm prompt (`POST /api/host/confirm`) |
| — | Inbox cards: Accept / Not now / Mute | `GET /api/host/inbox`, `/accept`, `/decline {mute}` |
| — | Match view (both roles), "I'm here", cancel, block, report | `GET /api/matches/:id` incl. `alt_seat_id`; `/arrived`, `/cancel`, `/api/block`, `/api/report` |
| — | Route `/seat/:seat_id` | Opened by the seat QR codes; starts linking |
| — | History chart | `GET /api/buildings/:id/history` |
| — | PWA: manifest, icons, service worker, push opt-in | `GET /api/push/vapid-public-key`, `POST/DELETE /api/push/subscribe`. The service worker never caches `/api`. iOS "Add to Home Screen" hint (FR-51) |

All `fetch` calls go through one `src/api.js`. It sends cookies, turns
`{error, message}` bodies into thrown errors, and handles `304`.

## 13. Contract deltas

**v1.0 → v1.1:** the "Changes from v1.0" list at the top of REQUIREMENTS.

**Source of truth → spec (D1):**

| `ghost_seats_source_of_truth.md` | REQUIREMENTS (authoritative) |
|---|---|
| `GET /api/buildings/{id}/seats` | `GET /api/buildings/:id` |
| `POST` / `DELETE /api/status` | `/api/host/link`, `/topic`, `/toggle` |
| `GET /api/matches?subject=` | `POST /api/search` |
| `POST` / `GET /api/requests` | `/api/search/:id/join`, `/api/host/inbox` |
| Muse Image generates a study pass live | Pre-generated card per subject (live generation is out of scope) |
| 3 seat states | Plus `offline` |
| `study_status`, `match_requests` tables | `host_sessions`, `searches`, `requests`, `matches` |
| `open_seats`, `likely_opening_seats` | `open`, `likely_opening` |
| Demo script: 15 s ghost timer | `GHOST_S` defaults to 30; the demo environment sets 15 |

## 14. Push, scheduler and outbox (FR-51..53, NFR-2, D28–D30)

```
transition (any trigger) ──same tx──► INSERT notification_outbox(user_id, kind, payload)
worker thread (each instance, `app/worker.py`):
   every SCHEDULER_TICK_S:
      SELECT … WHERE <deadline passed> FOR UPDATE SKIP LOCKED   → advance_* (requests, matches, sessions)
   outbox sender:
      SELECT … FROM notification_outbox WHERE sent_at IS NULL FOR UPDATE SKIP LOCKED LIMIT k
      → Notifier.send(subscriptions of user_id) → sent_at := now  (attempts += 1 on failure)
      404 / 410 from the push service → DELETE that push_subscription
```

- **Transactional outbox.** The notification row commits with the transition, so a push failure never rolls back a state change and a committed transition is never missing its notification.
- **`SKIP LOCKED`** means N instances never pick the same row. Duplicates are impossible within one outbox row.
- **Payloads** (`domain/notifications.py`):
  - `request_received`: course label and table label only.
  - `request_accepted`: the host's first name, allowed after accept (FR-43).
  - Never live location; never anything the matching UI wouldn't show.
- **Client.** The service worker shows the notification. `notificationclick` opens `/host` for host events and `/match/:id` or `/search/:id` for seeker events.

## 15. Scale design (D31, D32, NFR-8)

| Pressure | Design |
|---|---|
| Map polling from many phones | Per-building snapshot for `MAP_CACHE_S`, `ETag`/`304`, replica reads |
| Sensor write volume | Change-only `seat_readings`; compression and retention policies; hourly continuous aggregate |
| Many app instances | No state of record in memory; `SKIP LOCKED` worker; signed cookies |
| Lock contention | Row locks per seat, search or match only; AI calls never inside a lock |
| Verification | `scripts/load_check.py`: 500 polling clients plus 50 fake nodes; results and hardware in PROGRESS (Session 3) |
