# Ghost Seats — Plan

Who builds what, in what order, and why. Requirement ids refer to
`REQUIREMENTS.md` (v1.1), flow steps to `USER_FLOWS.md`, and "ARCH §n" to
`ARCHITECTURE.md`. Part 2 is the decision log.

**Ground rules**
- Time, effort and complexity are not decision inputs (D16). Choose what is correct and complete.
- Nothing is assumed. Anything neither REQUIREMENTS nor USER_FLOWS settles goes into the questions table and is asked.
- Commit before every bug fix and before every major feature (D27). A bug is a pair of commits: the state containing it, then `Fix …`. Subjects are imperative with no type prefix.

# Part 1 — Roles, checklists, integration

## Roles and ownership

| Role | Who | Owns | Branch |
|---|---|---|---|
| Backend | Manideep | `backend/`, `documentation/` | `v1backend` |
| Frontend | Software partner | The web app and PWA (`frontend/` after D6) | `v1frontend` |
| Hardware | Hardware pair | `firmware/`, `bridge/`, the physical demo table | `Arduino/Transmitter-Code`; UI and bridge work went to `v1hardsoft`, now `v1final` |

No two roles edit the same folder. The contract between them is REQUIREMENTS
§7 (API) and §10.3 (serial). A change to either is agreed by the roles it
touches, then recorded here as a decision.

## Branches

| Branch | Holds |
|---|---|
| `main` | Final, demo-ready. Receives `v1` after the IC3 rehearsal |
| `v1` | Integration: every role's branch merges here at each checkpoint |
| `v1backend` | Backend and documentation |
| `v1frontend` | Frontend |
| hardware branch (Q2) | Firmware and bridge |

## Event schedule (context only, not a decision input)

| When (Central Time) | What |
|---|---|
| Sat 11:00 PM | WEL lockout; overnight work moves to GDC |
| Sat 11:30 PM | Devpost soft submission (`hacktx26.devpost.com`) |
| Sun 11:30 AM | Hard submission, hacking ends |
| Sun 2:00–5:00 PM | Live judging in WEL |
| Sun 5:30 PM | Pitch, GDC 2.216 |

Tracks: Best Hardware · Meta (Bringing People Closer Together with AI) · MLH Best Use of Tiger Data · .TECH domain (D37).

## Current milestone

All roles integrated on `v1final` (D40). The two-phone flow works end to end in the browser with live Muse, and 205 backend tests pass (PROGRESS, Sessions 5–7). Open: the Tiger migration for D43, Q14 (demo-table sensors), and the Vultr deploy (D36, D37).

## Backend checklist — Manideep (`v1backend`)

Each numbered step is a major feature: commit before it, add tests with it,
commit when green.

### B0 — Skeleton and contract
1. ✅ `backend/pyproject.toml` (Python 3.12, uv): fastapi, uvicorn[standard], pydantic-settings, psycopg[binary,pool], httpx, itsdangerous, pywebpush; dev: pytest, ruff, mypy. Commit `uv.lock`.
2. ✅ `backend/.gitignore` (`.venv`, `__pycache__`, `.env`) before the first backend commit; `.env.example` lists every environment key (REQUIREMENTS §8) with no values.
3. ✅ Makefile targets: `dev test lint fmt typecheck check db-init seed seed-history fake-node load-check`.
4. ✅ `config.py` validates every §8 key at startup; missing required environment → the process refuses to start.
5. ✅ `GET /api/health → {ok, db}`; an import-guard test that `domain/` imports no I/O, config or clock.
6. ✅ **Contract first:** every request/response model in `interface/schemas.py`, every route registered and returning 501. From here `/docs` is the live contract for the frontend.
7. ✅ Local Timescale (Tiger Data service still to create, U3); `sql/schema.sql` (REQUIREMENTS §6, `CHECK` on every status, the hypertable, the partial unique indexes in ARCH §6); `sql/seed.sql` (buildings, tables, seats and node id agreed in H0, demo users).
8. ✅ U2 probe: `CREATE EXTENSION timescaledb_toolkit`, a `state_agg` query and a test continuous aggregate. Record the result in PROGRESS and pick the ARCH §10 path.

### B1 — Seat slice (Hardware track)
1. ✅ `domain/types.py`, `domain/seat_engine.py`. Tests at exact boundaries: `DEBOUNCE_S`, `GHOST_S`, `OFFLINE_S`, `HUMAN_FRESH_S`; blink overrides color; `away → occupied` resets `away_since`; offline wins.
2. ✅ `Repository` port, `InMemoryRepository`, `PostgresRepository` seat methods, and the `tests/repo_contract/` conformance suite.
3. ✅ `POST /api/readings` (ARCH §4):
   - `X-Node-Key` check; unknown seats skipped and logged.
   - Change-only insert plus offline markers; row lock per seat.
   - Tests: 10 identical readings → 1 row; a gap → marker plus row.
4. ✅ `scripts/fake_node.py`: interactive per-seat toggles, the same payload as the bridge.
5. ✅ `GET /api/buildings`, `GET /api/buildings/:id` from the snapshot cache with `ETag`/304 (ARCH §5). Tests: a second request within `MAP_CACHE_S` doesn't hit the repository; `If-None-Match` → 304.
6. ⬜ Hand the hardware pair the URL, `NODE_KEY`, seat ids and LED mapping. *(Waits on H0 seat ids and a deployed URL.)*
7. ⬜ **IC1.**

### B2 — Map extras (Tiger Data track)
1. ✅ `domain/simulation.py` (deterministic per slot; busier → fewer open), wired into the snapshots (FR-13, 47).
2. ✅ `domain/geometry.py`, `domain/recommend.py` widening (D21), `GET /api/recommend`. Tests for each level, likely-only levels, full → nearest building.
3. ✅ History (ARCH §10, needs Q12):
   - `state_agg` path, continuous aggregate, compression and retention policies.
   - `scripts/seed_history.py`; `GET /api/buildings/:id/history`.
   - Test: a hand-built change log → exact `open_avg` per hour.
4. 🚧 Deploy (D36, D37): one origin serving `frontend/dist`, two instances, and the Pi pointed at it.
   - ✅ `backend/Dockerfile`, `deploy/` (compose, provision, rolling deploy), tested locally.
   - ✅ Tiger Data service loaded: schema, seed, policies, 24 h of history (PROGRESS, Session 4).
   - ⬜ Vultr instances and load balancer, `.tech` DNS, first deploy from `v1`.
5. ✅ `scripts/seat_qr.py`: a printable sheet of `<origin>/seat/<seat_id>` QR codes for the hardware pair.

### B3 — Accounts, topics, host, search (Meta track)
1. ✅ Auth: demo users, login, logout, `/api/me` with `host.status` / `hidden_reason`.
2. ✅ `domain/catalog.py`, `domain/topic_rules.py`, `FallbackAI`, `topic_cache`. Tests: `"ch 320m stereochem mechanisms"` and `"orgo 1 exam prep"` → CH 320M; `"314 trees hw"` → C S 314.
3. ✅ Host machine (ARCH §6; D17, D18, D20, D23, D24):
   - Endpoints: link, topic, toggle, mute/unmute, confirm.
   - Tests: each `hidden_reason` triggered alone; each end reason; FR-50 errors.
4. ✅ Search machine (ARCH §6; D15, D19, D22):
   - Endpoints: create with `offered_group` and `has_real_hosts`; join (`no_real_hosts`, FR-34); status; cancel.
   - Tests: expire, skip on absence, decline, simulated hosts never chosen, blocked hosts never chosen, exhaust at `MAX_HOSTS_PER_SEARCH`, never crosses groups.
   - A Postgres test with two concurrent advances → exactly one pending request.
5. ✅ Inbox; `decline {mute}` (D20).
6. ⬜ **IC2.**

### B4 — Match payoff (Meta + Hardware tracks)
1. ✅ Accept → match: AI icebreaker outside the transaction, seat assignment (FR-37, Q13), `card_key`, blink.
2. ✅ `GET /api/matches/:id` for both roles with `alt_seat_id` (D25); arrived; cancel; `advance_match` (2-min absence, 20-min expiry).
3. ✅ Block and report.
4. ✅ Seeded simulated host sessions (FR-48), verified never to receive requests.
5. ✅ *(Optional, FR-54)* search pinned to `related`.
6. ⬜ **IC3.**
7. ✅ `MuseAI` (D38), live-checked with `make muse-check`; Muse-off: a bad key → 401, and the guard answers with the fallback.

### B4.5 — Push, scheduler, outbox (ARCH §14; D28–D30)
1. ✅ Tables `push_subscriptions`, `notification_outbox`; `Notifier` port, `push_webpush` adapter, `FakeNotifier`.
2. ✅ `GET /api/push/vapid-public-key`, `POST` / `DELETE /api/push/subscribe`.
3. ✅ `domain/notifications.py`: one outbox row per FR-52 event, payloads per FR-53.
4. ✅ Ingest-triggered advance of seat-linked sessions and matches.
5. ✅ `app/worker.py`: scheduler tick and outbox sender with `SKIP LOCKED`.
6. ✅ Tests:
   - A request expires with no client polling → the next host gets a request and an outbox row.
   - Two concurrent ticks → one transition.
   - A failing push leaves the transition committed.
   - A 410 response deletes the subscription.

### B5 — Failure pass and hardening
1. ✅ On every endpoint: empty · one · many · absurdly large · hostile input · database down · Muse slow or down · push service down · same request twice · failure mid-transaction.
2. ✅ Boundary logging without secrets (ARCH §7).
3. ✅ Read/write split via `DATABASE_READ_URL`. Test: locked and write paths never use the read pool.
4. ✅ `scripts/load_check.py`: 500 polling clients plus 50 fake nodes; p50/p95 latency and DB load recorded in PROGRESS with the machine named.
5. 🚧 Security pass and pre-commit checklist ✅; two instances verified locally (4 workers) ✅; merge into `v1final` and deploy ⬜ (D36, D40, IC1).

### B6 — Ship
1. ⬜ Demo environment: `GHOST_S=15`.
2. ⬜ Three full rehearsals on the venue network with all roles.
3. ⬜ Merge `v1 → main`; root README (what it is, run/test commands, key decisions); Devpost.

## Frontend checklist — software partner (`v1frontend`)

### F0 — Foundations
1. ⬜ Move the app into `frontend/` (D6, the frontend owner's call).
2. ⬜ `vite.config.js`: React plugin, `server.proxy['/api'] = 'http://localhost:8000'`.
3. ⬜ `src/api.js`:
   - Every `fetch` sends cookies.
   - `{error, message}` → thrown error; handles 304 with `If-None-Match`.
   - Maps `likely` → `likely_opening` once.
4. ⬜ Pin dependency versions (the current `package.json` uses `"latest"`).

### F1 — Live map (with B1)
1. ⬜ Building list from `GET /api/buildings`, polled every `POLL_WEB_S`, colored per FR-8.
2. ⬜ Building → floor → table view from `GET /api/buildings/:id` (shape in REQUIREMENTS §7).

### F2 — Recommendations and history (with B2)
1. ⬜ Recommended-seat pulsing outline, distinct from every state color (FR-12), with a message per `level`; full building → nearest building.
2. ⬜ Simulated labels (FR-13); history chart from `/history`.
3. ⬜ Route `/seat/:seat_id` (opened by the QR codes; starts linking).

### F3 — Accounts, topic, host, search (with B3)
1. ⬜ Demo login picker; state restored from `/api/me` on load; logout.
2. ⬜ "What are you studying today?" with skip; quick login keeps the typed topic (FR-18); normalized label (FR-19).
3. ⬜ Search results:
   - Same-course and related groups with counts, no names.
   - Join shown only when `has_real_hosts`.
   - Empty states "No one's studying this right now" and "No one's free right now".
   - Countdown while a request is pending.
4. ⬜ Host setup in flow order: toggle → link (tap a seat or `/seat/:id`) → topic.
5. ⬜ Host panel: findable/hidden with `hidden_reason`, mute/unmute, the 3-hour confirm prompt.
6. ⬜ Inbox cards: course, table, countdown; Accept / Not now / Mute.

### F4 — Match (with B4)
1. ⬜ Match view for both roles: first name, building/floor/table, assigned seat, `alt_seat_id` when set, icebreaker, card image.
2. ⬜ "I'm here", cancel, block and report on every request and match view (FR-45).
3. ⬜ Card images pre-generated with Muse Image (one per subject plus generic; no people, no text) in `public/cards/` (U1).
4. ⬜ *(Optional, FR-54)* "Try people studying related material?".

### F4.5 — PWA and push (with B4.5)
1. ⬜ `manifest.webmanifest`, icons, theme color.
2. ⬜ Service worker: `push` handler, `notificationclick` → inbox or match; **never caches `/api`**.
3. ⬜ Opt-in after login: VAPID key → `PushManager.subscribe` → `POST /api/push/subscribe`; unsubscribe on logout.
4. ⬜ iOS hint: "Add to Home Screen to get requests" (FR-51).

### F5 — Device pass
1. ⬜ 375 px on iOS Safari and Android Chrome, in the browser and as an installed PWA (NFR-4).
2. ⬜ All times shown in Central Time (NFR-5).

## Hardware checklist — hardware pair

### H0 — Agreements (before B0.7)
1. ⬜ Node id, seat ids and seat order for the demo table, given to the backend for `seed.sql`.
2. ⬜ Name the hardware branch (Q2); code lives in `firmware/` and `bridge/`.

### H1 — Firmware (REQUIREMENTS §10.2)
1. ⬜ Sample every seat sensor every 500 ms (HW-1); a human-sensor change needs 3 matching samples (HW-2).
2. ⬜ Send `R,<o><h>,…` every 2 s (HW-3).
3. ⬜ Apply `L,…` on receipt; blue blink toggles every 300 ms (HW-4).
4. ⬜ Local mode after 10 s without a command: red if any sensor is true, green otherwise (HW-5).
5. ⬜ Calibrate the human sensor only while the object sensor reads false (HW-6).

### H2 — Bridge (REQUIREMENTS §10.4)
1. ⬜ Config `SERIAL_PORT`, `BACKEND_URL`, `NODE_ID`, `NODE_KEY`, `SEAT_IDS` (HW-7).
2. ⬜ `R` → `POST /api/readings` with the `X-Node-Key` header; response → `L` using green→G, red→R, yellow→Y, blue_blink→B, off→O (HW-8).
3. ⬜ On timeout or error, send nothing (HW-9). Log every request and response with a timestamp (HW-10).

### H3 — Bench test
1. ⬜ Bridge against a local backend (B1) and against `fake_node`'s payload format.
2. ⬜ Verify a loaded backpack alone reads `human_present = false` (§10.1).

### H4 — Demo table
1. ⬜ Hinged pad over the micro switch, hidden wiring, LEDs visible from a walking distance.

### H5 — Deployment
1. ⬜ QR codes from B2.5 on each seat.
2. ⬜ Pi on the hotspot reaching the deployed URL.
3. ⬜ Join IC1, IC3 and the B6 rehearsals.

## Handoffs

| From → To | What | Due |
|---|---|---|
| Hardware → Backend | Node id, seat ids, seat order | H0, before B0.7 |
| Backend → Frontend, Hardware | Live contract at `/docs` | B0.6 |
| Backend → Hardware | URL, `NODE_KEY`, LED mapping | B1.6 |
| Hardware → Backend | Live readings from the real table | IC1 |
| Frontend → Backend | Buildable `frontend/` for the single-origin deploy | B2.4 |
| Backend → Hardware | QR sheet | B2.5 |
| Frontend → all | Card images | F4.3 (needs U1) |

## Integration checkpoints

| Checkpoint | After | Proves |
|---|---|---|
| IC1 | B1 + F1 + H2 | The real seat drives the live map and the LED |
| IC2 | B3 + F3 | Topic → search → join reaches a host's inbox |
| IC3 | B4 + F4 (+ B4.5/F4.5 when done) | Every edge of both user flows on two phones and the real seat |

At each checkpoint: every role pushes its branch, the branches merge into `v1final`
(D40), `v1final` is deployed, and the result is logged in PROGRESS.

## Acceptance criteria

1. Every edge of both USER_FLOWS diagrams works on two phones and the real seat, three times in a row on the venue network.
2. The same with Muse unreachable (NFR-3).
3. Three buildings (one real, two simulated and labeled) render at 375 px and in the installed PWA, refreshing every `POLL_WEB_S`.
4. A host with a locked phone receives a request push. An expired request moves to the next host with no client open.
5. The history chart comes from the change-only hypertable through `state_agg` or its fallback (ARCH §10).
6. Unplugging the Pi shows `offline` on the map; stopping the backend puts the node in local mode.
7. Two backend instances serve traffic, and the load check is recorded.

## Out of scope

REQUIREMENTS §11, plus WebSockets (FR-10 specifies polling).

## Questions and unknowns

| Id | Question | Owner | Blocks | Status |
|---|---|---|---|---|
| Q1 | Can a join request reach a simulated host? | Team | B4.4 | Resolved: D22 |
| Q2 | Hardware branch name; demo-table node and seat ids | Hardware pair | B0.7, H0 | Resolved: branches `Arduino/Transmitter-Code` and `v1hardsoft` (renamed `v1final` on GitHub); the bridge uses the placeholder ids `table-1` / `t1-s1` |
| Q4 | What does turning on host mode do before linking? | Team | B3.3 | Resolved: D17 |
| Q5 | "Seat empty" vs "no person" for ending sessions and matches | Team | B3.3, B4.2 | Resolved: D18 |
| Q6 | Mute from a request card | Team | B3.5 | Resolved: D20 |
| Q7 | Recommendation scope | Team | B2.2 | Resolved: D21 |
| Q8 | Related-subject matches and the cascade | Team | B3.4 | Resolved: D19 |
| Q9 | What the host sees when the seeker's seat changes | Team | B4.2 | Resolved: D25 |
| Q10 | Host and seeker at the same time | Team | B3.3, B3.4 | Resolved: D23 |
| Q11 | FR-27 confirmation endpoint and grace | Team | B3.3 | Resolved: D24 |
| Q12 | History chart window and raw retention | Team | B2.3 | Resolved: 24 h, 30 days (hourly rollup kept) |
| Q13 | On accept, the host's table has no open seat at that instant | Team | B4.1 | Resolved: nearest open seat on the floor; none → no assigned seat |
| Q14 | The demo table has one IR proximity sensor (seat `t1-s1`). (a) The bridge sends `human_present = object_present`, so a bag reads as a person and the seat never turns `likely_opening` (D18, HW-1..6). (b) `t1-s2` never reports, so the table has no open seat and the host is hidden as `table_full` (FR-24): no seeker can join the real table. Second sensor, presence sensor, or a changed demo? | Team, hardware pair | IC1, IC2, B6 | **Open** |
| U1 | Muse Spark and Muse Image access (key, endpoint, auth, JSON mode) | Backend, from Meta sponsors | B4.7, F4.3 | Resolved: key obtained; API per D38. `muse-image-1.0` is on the same API (F4.3) |
| U2 | Tiger Data: connection limit (sets `DB_POOL_SIZE`) | Backend | Deploy | Resolved: `max_connections` 105 (12 reserved); 2 hosts × 2 workers × 5 = 20, so `DB_POOL_SIZE` stays 5 |
| U3 | Deploy host (always-on, HTTPS, env vars, ≥ 2 instances) | Backend | B2.4 | Resolved: D36, D37 |

## Risks

| Risk | Mitigation |
|---|---|
| Muse access never arrives (U1) | `FallbackAI` covers every call; acceptance criterion 2 proves it |
| The toolkit isn't available on Tiger Data (U2) | `LEAD()`-window fallback over change-only rows (ARCH §10) |
| Venue Wi-Fi isolates the Pi or phones | Everything uses the public URL; phone hotspot as backup |
| Backend needs readings before the hardware exists | `scripts/fake_node.py` sends the exact bridge payload |
| Concurrent advances double-send | Row locks, partial unique indexes, `SKIP LOCKED`; tested in B3.4 and B4.5 |
| iOS push needs a Home Screen install | Hint in F4.5; polling still works in an open tab |
| HC-05 link flaps | HW-2 three-sample rule plus `DEBOUNCE_S` |
| A role changes the contract unilaterally | Contract changes are recorded as decisions before code |

---

# Part 2 — Decision log

Format: options → decision → why. Withdrawn entries stay, marked.

**D1 — Spec v1.0 beats the source of truth.** The two disagreed on API paths,
tables and image generation (ARCH §13). The spec was the later and more
precise document. The source of truth's deadlines, tracks, hardware parts and
demo script were carried into PLAN and ARCH.

**D2 — FastAPI + Pydantic v2 + psycopg 3 on Python 3.12.** Options: FastAPI, Node/Express.
- **Pydantic** models validate every request and response, and the same models generate the OpenAPI `/docs` page. The contract cannot drift from the code.
- **Node's main advantage**, sharing TypeScript types with the frontend, doesn't apply: the frontend is JSX.
- **Python** is the backend owner's strongest language.

**D3 (revised) — Raw SQL behind a repository port with two implementations.**
- **Raw SQL:** Timescale features (`create_hypertable`, `time_bucket`, `state_agg`, policies) are SQL-native.
- **`Repository` protocol:** implemented by `PostgresRepository` and `InMemoryRepository`, both held to one conformance suite. Services are then testable without a database while staying honest about SQL behavior.
- The original version (concrete repository, no fake) was justified by effort and was revised under D16.

**D4 — Timeouts are evaluated from stored timestamps under row locks.** Pure
`advance_*` functions decide; services apply them under `SELECT … FOR
UPDATE`. Extended by D29.

**D5 — One origin.** FastAPI serves the API and the built frontend; in dev,
Vite proxies `/api`. A cookie session across two origins would need CORS with
credentials and `SameSite=None; Secure` cookies, which widens the CSRF
surface. One origin keeps `SameSite=Lax` and gives the service worker the
app's whole scope.

**D6 — Folder ownership; the frontend moves to `frontend/`** (the frontend
owner's call). Each role owns its folders, so branches never conflict. A root
that names every component is easier to navigate.

**D7 — AI behind a port with a deterministic fallback.** `FallbackAI` makes
every flow work and testable with no network. `MuseAI` sits behind the same
`TopicAI` port, so a Muse outage changes output quality, not behavior (NFR-3).

**D8 — Shared node key.** `POST /api/readings` requires `X-Node-Key`. Node
ids are guessable, and the backend has a public URL.

**D9 — `GET /api/me` and `POST /api/logout`.** After a reload the client needs
the user, host status, and any active search or match from the server, rather
than from browser storage that drifts out of sync.

**D10 — `buildings.lat/lng`.** FR-11 needs a location to find the nearest building.

**D11 — Withdrawn → D24.** Reusing `toggle {open:true}` as the FR-27
confirmation was justified by "no new route" (an effort argument).

**D12 — Withdrawn → D15.** Ranking once per search was justified by AI call
count (an effort argument), and it missed hosts who became findable mid-search.

**D13 — Documentation layout.**
- `documentation/` holds REQUIREMENTS (what), USER_FLOWS (user-facing behavior), ARCHITECTURE (how), PLAN (who, when, why) and PROGRESS (what happened).
- Documents cite ids instead of restating each other.

**D14 — USER_FLOWS is authoritative for UX.** Where a flowchart was wrong, the
flowchart was corrected (USER_FLOWS "Revised in v1.1") rather than the spec
bent around it.

**D15 — Candidates are recomputed at every hop.** The next host is the
top-ranked findable real host in the offered group, excluding those tried. A
host who becomes findable mid-search can receive the next hop. This matches
the spec's data model, which stores only `tried_session_ids`.

**D16 — Resources are not a decision input.** Time, effort and complexity
never decide a design, a scope cut or a recommendation. D3, D11 and D12 were
revisited under this rule.

**D17 — Host mode starts at link.** Options: toggle creates the session; or
toggle is a UI entry point and link creates it. Decision: the latter. The spec
already returns `session_id` from link. The host is findable only once a topic
is set. `toggle {open:false}` ends the session.

**D18 — No person = gone, belongings or not.** Options: absence means no
person; or only a fully empty seat counts. Decision: no person.
- **It's the product's purpose.** A backpack holding a social session or match would rebuild the ghost-seat problem inside the social feature.
- **Seekers' expectations.** A seeker should never walk over to find only a backpack.
- **Resulting rules:** hidden at once (FR-25), match cancelled at 2 min (FR-41), session ended at 10 min (FR-26). The seat still goes yellow publicly.
- The original flowchart wording was the bug.

**D19 — One offered group per search.** Options: stay in one group; one
cascade crossing groups; seeker picks. Decision: stay in one group.
- **The search records `offered_group`:** same course if that group has any hosts, otherwise related.
- **The seeker agreed to a specific offer.** Silently sending a request to a related-subject host would also mislabel the host's card.
- **Join is hidden** when the group has no real host.
- **Optional FR-54** lets the seeker explicitly start a related search.

**D20 — Mute from a request card = silent decline + mute, undoable.** The
flowchart's "for the rest of the session" was too strict: a host should be
able to undo a tap. Sent as `POST /requests/:id/decline {mute: true}` in one
transaction.

**D21 — Recommendations widen.** Options: building-wide (v1.0); scoped to the
selection and widening. Decision: widening, table → floor → building → nearest
building, open before likely at every level. The response carries `level` so
the UI can say "nothing open at this table, here's the closest seat".

**D22 — Simulated hosts never receive requests.** Options: skip; auto-decline;
auto-accept. Decision: skip.
- **Skip:** a request should always reach a person.
- **Auto-accept** would fake a match.
- **Auto-decline** would waste a seeker's hop.
- Simulated hosts still count in aggregates. In the demo, a teammate is the real host.

**D23 — One role at a time.** A user with a live host session can't search
(`already_hosting`). A user with an active search or a seeker-side match can't
link (`already_searching`). Nobody is ever both requester and requestee.

**D24 — FR-27 confirmation.** At `SESSION_MAX_S` the host is hidden and
prompted. `POST /api/host/confirm` within `CONFIRM_GRACE_S` (120 s) renews the
session; no answer ends it (`unconfirmed`).

**D25 — The alternative seat shows in both match views.** No separate alert
or push; the host's view updates on its next poll.

**D26 — Split by layer.** Backend, frontend and hardware each own folders and
a branch. The API and serial contracts are the seams.

**D27 — Commit protocol.** Commit before every bug fix and before every major
feature. A bug becomes a reviewable pair of commits. Subjects are imperative
with no prefix.

**D28 — Website plus an installable PWA with web push.** Options:
- Website only.
- PWA.
- Capacitor app.
- React Native app.

Decision: PWA.
- It's the same codebase, installable on phones.
- It solves the real problem: a host's request arriving while the phone is in a pocket.
- A native app stays out of scope (§11).

**D29 — Three triggers for transitions (NFR-2 amended).**
- **On read/write** of the entity.
- **On sensor ingest**, for seat-linked sessions and matches, so presence rules fire every 2 s.
- **A scheduler tick** every `SCHEDULER_TICK_S` for deadlines that depend only on time.

Push makes this necessary: with every phone locked, nothing polls. `FOR UPDATE SKIP LOCKED` keeps the tick safe on any number of instances.

**D30 — Transactional outbox for push.** Notification rows commit with the
transition. A sender drains them with `SKIP LOCKED`. A failed push never rolls
back a state change, and 404/410 deletes the subscription. Payloads follow
FR-53.

**D31 — Change-only `seat_readings` with offline markers.** Options: every
reading; change-only. Decision: change-only.
- **Storage:** sensor pairs change rarely, so storage drops by orders of magnitude.
- **History becomes exact:** time in state via Timescale Toolkit `state_agg`, not sample averages biased by gaps.
- **Hard to change later:** stored rows would carry mixed meaning, so this was decided before any data exists.

**D32 — Campus-scale design built now.**
- A per-building map snapshot (`MAP_CACHE_S`) with `ETag`/304.
- Compression and retention policies; an hourly continuous aggregate.
- A read/write connection split.
- No state of record in process memory (NFR-8).
- Verified by a load check (B5.4).

**D33 — History is a window-function SQL function plus an hourly rollup job; Toolkit is not used
(2026-10-24).**
- The U2 probe showed `state_agg` works locally, including in a continuous aggregate, but it only measures between its own rows.
- Change-only storage leaves hours with no rows, so per-hour aggregates would score long stable periods as zero (the probe returned 30 of 75 open minutes).
- `open_hourly()` rebuilds intervals with `lead()` and is exact. A Timescale job stores completed hours in `building_open_hourly`, so the hourly series outlives the 30-day raw retention (Q12).
- The API and the job call the same function. Tiger Data only needs TimescaleDB.

**D34 — Connection budget.** `DB_POOL_SIZE` (default 5) per pool per process. The local Timescale
image allows 25 connections; a hard-coded pool of 10 overran it with 4 workers ("too many
clients"). Processes × instances × pools × `DB_POOL_SIZE` < `max_connections`, checked against
the real limit before deploying (U2).

**D35 — Database outages are a 503.** The repository turns connection-level failures into the
port's `Unavailable`. The API answers 503 `database_unavailable` with `Retry-After: 5`, after at
most a 5 s pool wait, instead of a 500 after 10 s. The frontend shows an offline state and keeps
polling.

**D36 — Deploy on Vultr: two instances behind a Vultr Load Balancer (resolves U3).** Options:
Fly.io, AWS (App Runner, ECS Fargate, EC2), Vultr; the team chose Vultr.
- **Two Cloud Compute instances in New Jersey.** It is the Vultr region closest to Tiger Data's
  `us-east-1`, and every request makes several database round trips, so database latency
  matters more than distance to Austin.
- **Each instance** runs the same Docker image (API, `frontend/dist`, worker thread) with
  `restart: unless-stopped`. Nothing of record is local (NFR-8), so either instance can die.
- **The load balancer** terminates HTTPS with Auto SSL and health-checks `GET /api/health`. That
  endpoint answers 200 even when the database is down (D35), so a database outage does not
  empty the pool; each instance still answers 503 on its own.
- **Deploys roll one instance at a time** from a pinned commit of `v1`, waiting for the health
  check before the next, so the URL never goes down.

**D37 — Public URL on a `.tech` domain, DNS on Vultr.** Vultr's Auto SSL only works for domains
whose DNS Vultr hosts, so the domain's nameservers point at Vultr. The printed QR codes and the
Pi bridge use this URL, so it is fixed before `make qr` runs.

**D38 — Muse Spark through Meta's Model API (resolves U1).** From Meta's documentation
(`dev.meta.ai/docs`):
- **Protocol:** `POST {MUSE_BASE_URL}/chat/completions`, OpenAI-compatible, `Authorization:
  Bearer`. Defaults `https://api.meta.ai/v1` and `muse-spark-1.3`, both settings (§8), so a
  model or provider change needs no code.
- **Structured output:** every call sends a strict `json_schema`. Course codes and subjects
  are enums from the catalog, so the model cannot invent a course. A course the catalog lacks
  comes back as `NONE`, and the regex fallback supplies the code.
- **Latency:** `reasoning_effort: "minimal"`, the lowest Spark accepts. No retries inside the
  `AI_TIMEOUT_S` budget: any error, 429 or timeout goes straight to the fallback (NFR-3).
- **Privacy:** prompts carry topic and about-me text only, and host ids are replaced by
  `h1…hN` (REQUIREMENTS §9). User text is passed as JSON data, never as instructions.

**D39 — Hardware code lives in `firmware/` and `bridge/`; the backend has no in-memory mode.**
`v1hardsoft` added two things under `backend/`.
- **A `DATABASE_URL=memory` mode in `wiring.py` is dropped.** It imported `tests/`, which the
  image does not contain (`ModuleNotFoundError` in the container), and it kept seat state in
  process memory, which two instances cannot share (NFR-8). Tiger Data or the local Docker
  database replaces it.
- **The serial bridge moves to `bridge/arduino_bridge.py`.** It reads `GHOSTSEATS_URL`,
  `NODE_KEY`, `NODE_ID`, `SEAT_ID` and `SERIAL_PORT` from the environment, so no key sits in
  the public repo, and it has its own `requirements.txt` (`pyserial` is not a backend
  dependency). It keeps the sketch's protocol: it parses `occupied: true|false`, posts on
  every change and at least every 2 s (HW-8), and logs the LED color returned.
- **The Arduino files move into `firmware/`.** The sketch goes to
  `firmware/HACKATHON/HACKATHON.ino`, since the Arduino IDE needs the folder name to match. The
  Web Bluetooth component is kept as reference only: it posts `{table_id, occupied}`, which is
  not the `/api/readings` contract.

**D40 — `v1final` is the final integration branch, then `main`.** `v1final` = `v1backend` +
`v1hardsoft` (which contains `v1` and `v1frontend`) + `Arduino/Transmitter-Code`, plus the
D39 clean-up. It deploys with `FRONTEND_DIR=.` while the frontend sits at the repo root (D6
is the partner's call). Once it runs on the servers, `main` fast-forwards to it.

**D41 — Every database wait is bounded (`DB_TIMEOUT_S`, default 5).**
- **The gap.** D35 promised a 503 within 5 s, but that held only when connections were
  refused. With a paused database, the connection stays open and the server never replies, so
  `/api/health` and every query hung indefinitely. The live e2e run found it.
- **The bound.** `BoundedConnection.wait()` passes a timeout to every server round trip
  (queries, `BEGIN`, `COMMIT`). libpq's `connect_timeout` covers new connections, and the same
  value is the pool wait.
- **On a timeout,** the connection is closed so the pool discards it. The error is an
  `OperationalError`, so it maps to `Unavailable` and a 503.
- **Why per round trip and not per checkout.** The outbox drain holds a transaction across
  push HTTP calls; a checkout deadline would roll back sent marks and resend notifications.

**D42 — Requests wait 5 minutes (`REQUEST_TIMEOUT_S` 120 → 300).** The author's call: a host
studying with headphones on needs more than two minutes to notice and answer. A declined or
expired request still moves to the next host (FR-32); a seeker now waits at most 5 minutes
per host, up to `MAX_HOSTS_PER_SEARCH` hosts.

**D43 — First name and major before accept; majors feed Muse.** The author's call; FR-36, 43,
53 and REQUIREMENTS §6, §7, §9 amended.
- **Who sees what before accept.** The host's request card shows the seeker as "Priya ·
  Chemistry"; the seeker's waiting screen shows the asked host as "Asking Alex ·
  Biochemistry". The request push says the same.
- **What stays hidden.** Location (building, floor, table, seat) stays hidden until accept
  (FR-44). Declines stay silent.
- **Data.** `users.major` is seeded on the demo users; there is no profile editing.
- **Muse.** Ranking and icebreakers receive each side's major alongside the topic. Names still
  never reach the model. The fallback ignores majors.
