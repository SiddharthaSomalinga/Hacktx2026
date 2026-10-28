# PROGRESS.md — Synapse

Session log. Concrete changes, commands and observed results only.

## Current status

- **Milestone:** hackathon over; the demo is tagged `hacktx-2026` (D58). The post-hackathon
  cleanup (D59, PR #1) and the engineering pass (D60, PRs #2 and #3) are merged into `main`
  (`eb8474c`), with CI green.
- **Live:** `https://64.177.55.143.sslip.io` (server 2 at `45.32.219.190`), D57. Still runs the
  D57 build; nothing from D59 or D60 is deployed.
- **Tests:** 236 pass with Postgres (`make test-db`); 204 pass and 32 skip without it; bridge 10;
  frontend 32 (Vitest); browser e2e 1 (Playwright, against the compose stack). Live e2e: 114/114
  (Session 6).
- **Open questions:** Q14, Q19, Q21, Q22 (PLAN).

---

## 2026-10-24 — Session 1: documentation and backend plan

### Found
- Branch heads:
  - `main` = `c032fbd` (source of truth only).
  - `v1` = `v1backend` = `109e539` (plus the requirements spec).
  - `v1frontend` = `1fc2322`: Vite + React with all data mocked in `src/main.jsx`, no `vite.config.js`, dependencies on `"latest"` with a lockfile.
- `ghost_seats_source_of_truth.md` was already deleted in the working tree. Its unique content (deadlines, tracks, hardware parts, demo script) moved into PLAN and ARCHITECTURE.
- Source of truth and spec disagreed on API paths, tables and image generation → D1 (ARCH §13).

### Changes
- `Ghost_Seats_Requirements_Spec.md` → `documentation/REQUIREMENTS.md` (`git mv`).
- First versions of ARCHITECTURE, PLAN and PROGRESS.

### Not verified
- No code existed; nothing ran.

## 2026-10-24 — Session 2: user flows, decisions, docs v1.1

### Inputs
- The team's two user-flow charts (seeker/visitor and host), transcribed into `USER_FLOWS.md` as Mermaid.

### Found
Comparing the flows with the spec exposed nine ambiguities (Q1, Q4–Q11) and
two flowchart errors ("seat empty", "mute for the rest of the session"). All
were answered by the team. Two new questions surfaced and are still open: Q12
(history window and retention) and Q13 (accept when the host's table is full).

### Decisions taken
D2–D32 in the PLAN decision log. The ones that changed behavior:
- **D17** Host setup order.
- **D18** No person = gone, belongings or not.
- **D19** One offered group per search.
- **D20** Undoable mute.
- **D21** Widening recommendations.
- **D22** Simulated hosts never receive requests.
- **D23** One role at a time.
- **D24** 3-hour confirmation with a 2-minute grace.
- **D25** The alternative seat shows in both match views.
- **D28** PWA with push.
- **D29** Ingest and scheduler triggers.
- **D30** Outbox.
- **D31** Change-only readings.
- **D32** Campus-scale design.

Withdrawn: D11 and D12, both justified by effort, which D16 rules out as a decision input.

### Changes
- `REQUIREMENTS.md` → v1.1: a change list at the top, FR edits, FR-50–FR-54, NFR-2/4/8, §6 tables, §7 endpoints and error codes, §8 keys and environment, HW-7/8 node key.
- `USER_FLOWS.md` → v1.1: flowchart corrections listed in the file, and every trace step mapped to requirement ids and decisions.
- `ARCHITECTURE.md` rewritten: §1–§13 updated; new §14 (push, scheduler, outbox) and §15 (scale design).
- `PLAN.md` rewritten around three roles (backend, frontend, hardware) with checklists, handoffs, integration checkpoints, a questions table and the decision log.

### Verification
A cross-reference script was run over the five docs.

| Check | Result |
|---|---|
| Every `D#` cited is defined in the PLAN decision log | Pass |
| Every `Q#`/`U#` cited is in the PLAN questions table | Pass |
| Every `FR-`/`NFR-`/`HW-` id cited, including range ends, exists in REQUIREMENTS | Pass |
| Every `ARCH §n` and `REQUIREMENTS §n` cited has a heading | Pass |
| Every endpoint cited exists in REQUIREMENTS §7 | Pass after adding `GET /api/health`. `/api/status` appears only in the source-of-truth delta table, by design |
| Every config key cited exists in REQUIREMENTS §8 | Pass. `NODE_ID` is bridge config (HW-7), by design |
| Stale terms (rank-once, cut list, code freeze, un-replaced ⚠, "seat empty" as a rule) | Pass. The one hit is the withdrawn D11, kept as history |
| Publication checks on staged content and full history (repo is public) | Pass: no hits |

### Not verified
- No code exists yet.
- These remain unknown until B0 and B2: Timescale Toolkit availability on Tiger Data (U2), Muse access (U1) and the deploy host (U3).

## 2026-10-24/25 — Session 3: backend B0–B5

### Environment (observed)
- **Docker Hub pulls kept failing** from Docker Desktop's VM (`Retrying` on one layer, auth EOF)
  while the same endpoints answered 200 from macOS. The `timescale/timescaledb-ha:pg16` image
  (3.24 GB, TimescaleDB 2.31.0, Toolkit 1.26.0) eventually arrived on a retry.
- **The Homebrew fallback is impossible on this Mac.** `postgresql@18` has no bottle for this
  configuration ("Tier 3") and the source build stops with "Your Command Line Tools (CLT) does
  not support macOS 14".
- **Alpine's `timescaledb` apk targets Postgres 18**, so it cannot load into
  `postgres:16-alpine`.

### What was built (commits `6f00e54`..`2b3040e` on `v1backend`)
- **B0:** uv project, config with fail-fast validation, every §7 route registered from day one,
  schema, seed (placeholder demo-table ids, Q2).
- **B1–B4:**
  - Pure domain: seat engine, simulation, recommendations, matching, lifecycle.
  - Services with a lifecycle coordinator.
  - In-memory and Postgres repositories under one conformance suite.
  - Change-only ingest, ETag map snapshots, history.
  - Host, search and match flows (D15–D25), safety.
- **B4.5:** outbox, VAPID web push, per-instance worker thread running the scheduler tick and
  push sender.
- **B5:**
  - Failure pass.
  - Path-id bounds.
  - Read/write split proven with a SELECT-only role.
  - 503 on outage.
  - `DB_POOL_SIZE` budget.
  - Load check; `pip-audit` clean.
- **Scripts:** `fake_node`, `seed_history`, `seat_qr`, `vapid_keys`, `load_check`, `db`.
- **Docs:**
  - REQUIREMENTS §6/§7/§8 additions found during the build.
  - ARCHITECTURE §2/§3/§10/§11.
  - PLAN ticks and decisions D33–D35.
  - `backend/README.md`.
- `b2a9309 test` is the author's own commit of the load-generator change, pushed to
  `origin/v1backend` during a pause. It contains only `scripts/load_check.py`.

### Bugs (cause → fix; each fix is its own commit)
1. **History intervals ran past the change that ended them** (in `a32a6a4`, fixed in
   `a3c2fe6`).
   - Cause: a `WHERE is_open` in the same CTE as `lead()`. SQL evaluates `WHERE` before window
     functions, so `lead()` never saw the closing row.
   - Confirmed with a two-row query before changing code.
2. **Empty history hours counted as fully open** (`a32a6a4` → `e5285da`).
   - Cause: Postgres `LEAST`/`GREATEST` ignore NULLs, so the LEFT JOIN's NULL interval became a
     whole hour.
   - Fix: `FILTER (WHERE iv.start_at IS NOT NULL)`.
3. **With `FRONTEND_DIST` set, unknown `/api/*` paths returned `index.html` with 200**
   (`85ab732` documents it as a strict xfail; `2372d5e` fixes it).
4. **Pools overran the database connection limit** (fixed in `d850259`).
   - Cause: a hard-coded pool of 10 per process × 4 workers against the image's
     `max_connections = 25` ("too many clients").
   - Fix: the `DB_POOL_SIZE` budget (default 5). Peak under load is exactly 20.

Caught before committing:
- **`seed_history` would have deleted real readings** in its window. It now only seeds seats
  that have no readings, and never deletes.
- **A flow test's timeline was one node tick off.** The engine was right.
- **Two tests that could not fail** (the full-building recommendation and the replica split)
  were rewritten until a mutation made them fail.

### Verification
- **`make test-db`:** 177 passed; `make check` green (ruff, mypy `--strict` on 59 files).
- **Mutations, each failing at least one test and then restored:**
  - a bag counts as presence (9 failures);
  - simulated hosts receive requests (1);
  - the cascade crosses groups (1, after adding the missing test);
  - the ghost timer uses `>` instead of `>=` (1);
  - `max_hosts` uses `>` (1);
  - no `FOR UPDATE` in the send step (8 concurrent advances: 7 `Conflict` errors);
  - writes routed through the replica pool (2).
- **Live quick start:**
  - `make sync db-up db-create db-init seed policies seed-history dev` against a fresh
    database.
  - `make fake-node`: LED green → red → yellow, and the map showed `likely_opening` after
    `GHOST_S` with two server instances.
  - `make qr` wrote 2 codes.
- **Load:** 500 polling clients plus 50 nodes posting every 2 s, 60 s × 3 runs, 4 server
  workers, generator split over 4 processes. Apple M1, 8 GB, macOS 14.6.1; Postgres in Docker
  (4 CPUs, 1.94 GB).

  | Endpoint | p50 | p95 | max |
  |---|---|---|---|
  | `GET /api/buildings/pcl` | 2.7–2.8 ms | 15–36 ms | 231–901 ms |
  | `GET /api/buildings` | 3.1–3.2 ms | 34–78 ms | 315–1064 ms |
  | `POST /api/readings` | 35–37 ms | 113–232 ms | 289–1012 ms |

  - About 355 requests/s (the full offered load).
  - One transport error in about 21,000 requests, in the first run.
  - The earlier runs (p95 above 1 s) measured the single-process generator: 70% CPU against
    7–17% per server worker and 19% for Postgres.
- **Database down:** `/api/health` → `{"ok": true, "db": false}` in 2 s; other endpoints → 503
  `database_unavailable` with `Retry-After: 5` in at most 5 s.
- **`pip-audit`** on the locked runtime dependencies: no known vulnerabilities.

### Not verified
- **Deployment (U3) and Tiger Data (U2):** its connection limit, and the jobs and policies on
  the managed service.
- **Web push to real browsers:** only the notifier double and VAPID signing were exercised.
- **Muse Spark (U1):** not built; every AI call uses the fallback.
- **Real hardware and the real seat ids (Q2/H0); frontend integration (IC1–IC3).**

## 2026-10-24 — Session 4: deploy decisions and deploy kit

### Decisions
- **D36:** Vultr, two instances in New Jersey behind a Vultr Load Balancer (resolves U3).
- **D37:** a `.tech` domain, with its DNS on Vultr (required for Auto SSL).
- Fly.io was the first recommendation. New Fly accounts no longer get a free allowance (they
  get a short trial, then about $2/month per small machine). App Runner was ruled out: it
  throttles CPU between requests, which would stall the worker thread.

### Changes
- `backend/Dockerfile`: a Node 22 stage builds the frontend; a Python 3.12 slim stage installs
  from `uv.lock` without dev dependencies. The image runs as a non-root user, has a health
  check and runs `uvicorn --workers $WEB_CONCURRENCY` (2) with proxy headers.
- `backend/Dockerfile.dockerignore`: the build context is the repo root, so the frontend can
  be included; this file keeps `.env*`, `.git`, tests and caches out.
- `backend/deploy/`:
  - `compose.yaml`: one API container per host, secrets from `/etc/ghostseats.env`.
  - `provision.sh`: one-time server setup.
  - `deploy.sh`: rolling deploy of one pushed commit.
- `make image`, `make deploy`. README deploy section; ARCH §2 and §11.

### Verification
- **Image:** built from a scratch context holding `origin/v1frontend` as `frontend/`; 395 MB.
  - Inside it: no `.env` anywhere, no `node_modules`, uid 999, Python 3.12.15.
  - Run against the local database: healthy with 2 worker processes. `/api/health` →
    `{"ok":true,"db":true}`, map 200, `/api/nope` → JSON 404, `/seat/t1-s1` → the app's
    `index.html`, `/sw.js` → 200 `text/javascript`.
- **`deploy.sh`,** run against a bare-repo "origin" and a server clone, with a stand-in `ssh`
  that executes locally:
  - Two hosts updated in turn, each healthy at the pinned commit.
  - An unpushed commit was refused before any host was touched.
  - An empty `SECRET_KEY` meant the container never turned healthy. The script printed the
    logs and stopped before the second host.
- **Found on the way:** the laptop's Compose 2.1.1 rejects a top-level `name:` ("Additional
  property name is not allowed"; it needs Compose 2.3+). The project name now comes from
  `COMPOSE_PROJECT_NAME`.
- Ubuntu 24.04 has `docker.io` 29.1, `docker-compose-v2` 2.40 and `docker-buildx` 0.30
  (`apt-get --dry-run` in `ubuntu:24.04`).
- `shellcheck` 0.10 clean on both scripts. `make check`: 150 passed, 27 skipped.

### Tiger Data (U2)
- **Venue Wi-Fi blocks outbound database ports.** Ports 30905 (Tiger's) and 5432 timed out
  even to an unrelated test host, while HTTPS worked. A phone hotspot fixed it. The servers
  are not affected.
- **Service:** Postgres **18.6** (local tests run on 16), TimescaleDB 2.31.0 and Toolkit
  1.26.0, TLS on. `max_connections` 105, 12 reserved, 8 used by the service itself.
- **`make db-init seed policies seed-history`:** 17 tables, `seat_readings` a compressed
  hypertable, and compression (12 h), retention (30 days) and `rollup_open_hourly` (1 h) jobs
  registered. 3 buildings, 98 seats, 10 users, 7,363 change rows.
- **On Postgres 18:** `open_hourly('pcl', …)` returns hourly averages. `CALL run_job` on the
  rollup wrote 72 rows (24 h × 3 buildings).
- **API against Tiger:**
  - `/api/health` → `{"ok":true,"db":true}`.
  - Buildings, building and history all 200; 0.6–1.0 s each from the laptop on a hotspot to
    `us-east-1`.
  - `POST /api/readings` → `{"leds":{"t1-s1":"green"}}`; a wrong node key → 401.

### Muse Spark (U1, D38)
- **Setup:** Meta's docs (`dev.meta.ai/docs`) gave the endpoint, Bearer auth, strict
  `json_schema` output, `reasoning_effort` values (Spark rejects `"none"`) and error codes.
- **Built:**
  - `adapters/ai_muse.py`.
  - `MUSE_BASE_URL` and `MUSE_MODEL` settings.
  - Wiring: `MuseAI` when a key is set, else `FallbackAI`.
  - `scripts/muse_check.py` (`make muse-check`).
- **Tests:** 24 adapter tests against an `httpx.MockTransport`, plus a real local server that
  answers after 2 s. A 0.3 s timeout cut the call off in under 1 s.
- **Mutations, each failing its test and then restored:**
  - the missing-host check dropped;
  - the off-catalog course code no longer kept;
  - the timeout ignored.
- **`make check`:** 174 passed, 27 skipped. **`make test-db`:** 201 passed.
- **Live, `muse-spark-1.3`:**

  | Call | Latency | Result |
  |---|---|---|
  | `normalize_topic("orgo 1 exam prep")` | 2.52 s | CH 320M |
  | `normalize_topic("314 trees hw")` | 1.30 s | C S 314 |
  | `rank_hosts` | 1.78 s | 98 for the orgo host, 5 for the trees host |
  | `icebreaker` | 1.71 s | "Want to work through Organic Chemistry I problems together for CH 320M?" |

- **Wrong key:** `HTTP 401 invalid_api_key` in the log, with no key or message text.

### Not verified
- `provision.sh` on a real Vultr instance (no systemd in the test container); the load
  balancer, Auto SSL and the `.tech` DNS.
- The full test suite on Postgres 18. It truncates every table, so it cannot run against the
  Tiger service.

## 2026-10-25 — Session 5: integration into `v1final`

### Found on GitHub
- **`v1`** (`a145f6b`): the partner merged an older `v1backend` (`1b0d6f6`) into
  `v1frontend` and wired the app to the API (`src/api.js`, a Vite `/api` proxy).
- **`v1hardsoft`** (`16f573f`, hardware pair; then `32680ba`, the UT color theme, by the partner):
  UI LED colors, a `DATABASE_URL=memory` mode in
  `backend/app/wiring.py`, and `backend/scripts/arduino_bridge.py` with a node key in the code.
- **`Arduino/Transmitter-Code`** (`384c530`): `HACKATHON.ino`, one IR sensor on D2, printing
  `occupied: true|false` every 50 ms and driving its own LEDs. Also a Web Bluetooth component
  saved as `.txt`, which posts `{table_id, occupied}` (not the readings contract).
- **The frontend matches the contract** for all 17 calls (paths and bodies checked against the
  OpenAPI schema). Its search never calls `/join`, so seekers do not send requests from the UI
  yet (F3).

### Trial merge, before any change
- `v1backend` + `v1hardsoft` + `Arduino/Transmitter-Code` merged with no conflicts.
- Tests passed, but `make check` failed: ruff (import order, a 105-character line) and mypy
  `--strict` (`PostgresRepository` assigned to an `InMemoryRepository` variable).
- **The merged image ran in Postgres mode.** Memory mode crashed in the container with
  `ModuleNotFoundError: No module named 'tests'`.

### Decisions
- **D39:** no in-memory mode; the bridge moves to `bridge/` with env config; the Arduino files
  move to `firmware/`.
- **D40:** `v1final` is the final branch, then `main`.
- **Q2 resolved.** **Q14 opened.**

### Changes
- `bridge/arduino_bridge.py`, `requirements.txt` and tests: env config (no key in code),
  sketch-line parsing, a post on change plus every 2 s, LED logging, and reconnect on serial
  errors.
- **`v1final`:**
  - created from `v1backend`, merging `v1hardsoft` and `Arduino/Transmitter-Code`;
  - then `bcb312d`: `wiring.py` back to the `v1backend` version, the old script removed, and
    the sketch moved to `firmware/HACKATHON/`.

### Verification on `v1final`
- **`make check`:** 174 passed, 27 skipped. **`make test-db`:** 201 passed. **Bridge:** 10
  passed. **`npm ci && npm run build`:** passes, 250 kB JS.
- **Bridge end to end:**
  - A pseudo-terminal played the sketch's exact lines into the real bridge (pyserial), which
    posted to a backend on the local database.
  - The seat went `occupied` on `true` and `open` on `false`; the LED went red, then green.
- **Image (`FRONTEND_DIR=.`) on one origin, replaying the frontend's API calls with two users:**
  - `link` 200 → `topic` 200 → findable → `search` 200 → `join` 200.
  - The inbox card carried no name (FR-43); then `accept` 200.
  - The seeker's match view: `other_first_name` Alex, `assigned_seat_id` `t1-s2`, and a live
    Muse icebreaker. `arrived` 200.
- **Found while replaying (Q14b):** with only `t1-s1` reporting, the host is hidden as
  `table_full`; it becomes findable only once `t1-s2` reports open. The backend behaves as
  FR-24 requires; the real table needs a second sensed seat.

### Pushed
- **During the merge, `v1hardsoft` was renamed `v1final` on GitHub** (head `32680ba`). That
  commit was already in the verified tree.
- The local `v1final` contains `origin/v1final`, so the push was a fast-forward.
- `32680ba` carries a `Co-authored-by: Copilot` trailer. It is a teammate's commit, already
  public; history was not rewritten.

### Not verified
- The frontend in a browser against this backend (only its API calls were replayed).
- The real Arduino on the bridge, and anything on Vultr.

## 2026-10-25 — Session 6: full e2e on `v1final`, a hang fix, website review

### End to end (`v1final` + this fix, fresh `ghostseats_e2e` database)
- **Setup:**
  - Live server with 2 workers and the worker thread, live Muse, short timers.
  - Fake nodes posting every 0.5 s.
  - An e2e-only second node with two real tables, so the cascade has more than one real host.
- **Result: 114/114 checks passed.**
  - Covers FR-1..54 except FR-10, FR-12 and FR-17, which are client behavior.
  - Also covered: D30 outbox, D32 ETag, D35 outage, and hostile input.
  - Phase B (session max 8 s, 1 request/hour) covered FR-27 confirm and FR-34 rate limit.
- **Harness fixes, not app bugs:**
  - FR-22 needed `HUMAN_FRESH_S` to pass after a prior person reading.
  - `REQUEST_TIMEOUT_S=5` was shorter than live Muse ranking plus accept.
  - FR-52: a user-initiated cancel notifies only the other side (`match.py`, by design). The
    requirement's "(both)" reads as all participants; the canceller gets no push.

### Bug: requests hung on an unresponsive database (`06cf73c` → `ab4e458`)
- **Found:** with the database container paused, `/api/health` did not answer in 15 s.
- **Cause:** `faulthandler` showed the thread in `repo_postgres.py:727 ping → conn.execute →
  psycopg wait`, on a pooled connection. Nothing bounded a round trip; the pool's 5 s applied
  only to getting a connection.
- **Fix (D41):**
  - `BoundedConnection.wait()` passes `DB_TIMEOUT_S` to every round trip and closes the
    connection on a timeout.
  - libpq `connect_timeout` bounds new connections.
- **Regression tests:** two tests through a freezable TCP proxy. Committed first as strict
  xfails; they failed with "still blocked after 8 s".
- **After the fix:** each answers in about 5.0 s (three runs). The original repro returns
  `False` in 5.0 s. `make test-db`: 203 passed.

### Website review (headless Chromium, 375 px and 1280 px)
- **No console errors, and no horizontal scroll at 375 px.**
- **Bugs found in the frontend:**
  - The ☰ button has no handler, and the nav and login are hidden under 800 px, so a phone
    cannot log in, host or open history.
  - The login map says `Maya: 'u-priya'` while the button shows Priya, so Priya logs in as
    Alex.
  - "Start looking" never calls `/join`.
  - "Save topic" posts to `/host/topic` for every user, which is 409 unless linked.
  - Host toggle on before link → 409 (D17: link creates the session).
  - Offline seats are drawn in the "likely vacant" color.
  - Seat tiles show raw ids.
  - "1 floors"; PCL has 2.

### Frontend fixes on `v1final` (at the author's request)
- **`e502f45`:** the ☰ button opens a menu panel (pages, log in or out); the profile chip opens
  it on desktop.
- **`32fd470`:** the login picker lists `/api/demo-users` and logs in by id. Before, Priya
  logged in as Alex.
- **`3059411`:** the core loop is wired to the API.
  - Seeker: search → join → poll → match (a cancel is offered while searching).
  - Host setup per D17: toggle, then link, then topic. The status and hidden reason come from
    `/me`; mute and confirm work.
  - Real inbox (Accept / Not now / Mute), replacing the mock "Maya".
  - Real match view on both sides, with the alt seat, "I'm here" and cancel.
  - Removed: "Block or report". The match response has no user id to block (FR-45 gap in
    the UI only).
- **`c77eead`:** `likely_opening` gets its style; offline seats are grey "No signal" with a
  count; labels read "T01·2"; building rows show the seat count; the hero space; the header
  fits at 375 px.
- **Verified in headless Chromium, two phones at 375 px:**
  - Alex links `t1-s1` → FINDABLE.
  - Priya searches → "Asking someone studying CH 320M · 115s left".
  - Alex's inbox card shows no name → Accept → Alex sees Priya, Priya's phone opens the match
    with Alex, `t1-s2` and the live icebreaker → "I'm here" → completed.
  - All 200, no page errors; passed again after the last commit.
- **Still open:** seat colors (green = occupied in the UI, green = open for LEDs and FR-8) are
  a team decision. The history chart's orange curve is decorative.

## 2026-10-25 — Session 7: 5-minute requests, name and major before accept (D42, D43)

### Changes
- **Backend:**
  - `REQUEST_TIMEOUT_S` 300.
  - `users.major` (an `ADD COLUMN IF NOT EXISTS` migration) and seeded majors.
  - Inbox items carry `seeker_first_name`/`seeker_major`.
  - `GET /api/search/:id` carries `asking {first_name, major}`.
  - The request push reads "Priya · Chemistry wants to study …".
  - The match view adds `other_major`.
  - Muse ranking and icebreakers receive majors through `Topic.major`; names never do.
- **Tests:**
  - The old "no names before accept" assertions are replaced by D43's.
  - Hard-coded 120 s waits now read `request_timeout_s`.
  - Two Muse tests: majors reach the payload; names and empty majors do not.
- **Frontend (`v1final`):** the picker shows majors; the seeker strip reads "Asking Alex ·
  Biochemistry · 4:55 left"; the host card reads "Priya · Chemistry wants to study CH 320M ·
  Organic Chemistry I"; both match views show the major.
- **`USER_FLOWS.md` v1.2:** the revisions, plus §3, the connection flow. It covers the sequence
  across both phones, the backend and Muse, what each side sees per stage, every Muse call
  with its bound and fallback, and the timers.

### Verification
- `make check`: 174 passed, 29 skipped. `make test-db`: 205 passed. Ruff and mypy `--strict`
  clean.
- **Two phones in headless Chromium at 375 px, live Muse:**
  - Alex findable.
  - Priya: "Asking Alex · Biochemistry · 4:55 left".
  - Alex's card: "Priya · Chemistry wants to study CH 320M · Organic Chemistry I", 4:51 left.
  - Accept: each match view shows the other's first name and major.
  - Icebreaker: "Want to team up on Organic Chemistry I mechanisms and share Chemistry and
    Biochemistry study tricks?"
  - "I'm here" → completed. All 200.

### Not done
- **The Tiger migration.** Tiger was unreachable from the venue network. On a hotspot, run
  `make db-init seed` from `backend/` before deploying this commit.
- **`make seed` on the e2e database** failed on the e2e-only fixture tables (simulated seats
  per table); only the users upsert was applied there. Tiger has no such tables.

## 2026-10-25 — Session 8: frontend redo decisions (D44–D53)

### Found (review of `v1final`'s frontend, checked against the code)
- Mock data shown as live: `seedBuildings` uses ids `union`/`sac` (the backend has `wel`), one
  seed seat grid is reused for every building, seat `A4` is hard-coded as recommended, history
  shows a fixed 54 beside a CSS curve, and "Live"/"Updated just now" are unconditional.
- Failed requests are swallowed (`.catch(() => {})` in 10 places); "Demo users are loading…"
  never clears after a failure.
- Seat colors: open = blue, occupied = green (FR-7 says green = open, red = occupied).
- The dark-mode toggle changes no colors; the manifest has no icons; nothing subscribes to
  push; the service worker caches nothing; there is no router.
- MapLibre 6.15.0 builds its worker URL at runtime, so the production build requests
  `/assets/maplibre-gl-worker.mjs`, which does not exist (the backend answers with
  `index.html`).
- `/api/recommend` is never called. Polls run at 1.5–3 s and do not pause in a hidden tab.
- API gaps: block/report need a user id no response carries; no seat lookup for
  `/seat/:id`; the match has only the building's name; `GET /search/:id` cannot tell a
  joined search from a preview.

### Decisions
- D44–D53 (PLAN): the redo on `v2-frontendredo`, the live floor plan, the map-first flow,
  dark palette, self-hosted map tiles, hosting from your chair, push in context, the FR-8
  denominator, the stack, and the API additions. Q15–Q18 resolved by them; Q19 and Q20 open.

### Changes
- PLAN: D44–D53, Q15–Q20, the Branches table, F3.6 and F4.5.2 wording.
- ARCHITECTURE §7 and §14: the pre-D43 text on names, icebreaker inputs and the request push.

### Backend for D53
- `GET /api/seats/:id` (`MapService.seat`); `SafetyService` resolves the other person from a
  `request_id` or `match_id` and returns `not_your_request` / `not_in_match` to outsiders;
  `MatchOut` gains `building_id`, `table_id`; `SearchStatusOut` gains `request_id`, `joined`,
  `label`, `offered_group`. REQUIREMENTS §7 and ARCH §13 updated.
- `make check`: ruff, mypy clean, 182 passed, 29 skipped. `make test-db`: 211 passed.

### Frontend v2 on `v2-frontendredo` (worktree `../Hacktx2026-v2`)
- **Stack:** React 19.3.1, TypeScript 5.9.3 strict, Vite 8.3.5, React Router 8.5.0, TanStack Query
  5.104.5, MapLibre 6.15.0, vite-plugin-pwa 2.0.0 (injectManifest), IBM Plex via @fontsource
  5.3.0, Vitest 5.0.5. Pinned exactly (`.npmrc`). TypeScript 7 was skipped: openapi-typescript
  7.13 requires TypeScript 5.
- **Map assets:** 30 tiles (z12–15, 2.9 MB) from Protomaps build 20261024, glyphs from
  basemaps-assets@028c18f, footprints for pcl/wel/gdc from the tiles' `buildings` layer.
  Overpass returned 502 and then timed out from the venue network, so outlines come from the
  tiles instead (`npm run map:footprints`).
- **Cards:** `make cards` (Muse Image, `POST /v1/images/generations`, `output_format: png`):
  9 images, reviewed for people and text, resized to 960 px (110–265 KB).
- **Verified (local DB, backend serving `dist/`, headless Chromium):**
  - Two browsers: host from `/seat/t1-s1` → login → link → topic → findable; seeker types a
    topic → login keeps it → "CH 320M · Organic Chemistry I" with counts on the map → join →
    host card "Priya · Chemistry" → accept → both match views (live Muse icebreaker) → "I'm
    here". A stand-in node posted readings for `t1-s1`/`t1-s2`.
  - Offline: after one visit, an offline reload renders the shell, tiles and last counts;
    the pill reads "Offline · data from N s ago"; no `/api` response came from the service worker.
  - axe on `/`, a floor, a table, history, login and a seat, light and dark: no violations.
  - `npm run typecheck`, `npm run build`, `npx vitest run` (32 tests) pass.
  - `make image FRONTEND_DIR=.` builds; the container serves deep links, `sw.js`, the
    manifest, tiles, cards and the MapLibre worker (200, JavaScript).
- **Bugs found and fixed:**
  - Seeded camera clamped north: MapLibre keeps the view inside `maxBounds`, and with half the
    screen under the panel the view needed area south of the extract → wider extract.
  - First visit reloaded the page: Workbox fires `controlling` on the first install too →
    reload only when `event.isUpdate` (`822c242` → `59f7778`).
  - `workbox-window` threw when service workers were unavailable → caught (`ccd117c`).
  - Map markers failed axe label-in-name → visible text plus a hidden description (`09c7dbc`).
- **Not verified:** real iOS and Android devices, installed PWA, a push reaching a locked
  phone, Lighthouse/CDP installability. No Playwright suite is committed; the flows above ran
  from a scratch script.

### Demo hosts (D56)
- `make seed-demo`: 24 hosts added, 0 on a second run. With `DEMO_HOSTS=true`: "physics
  mechanics", "psych 301", "stats" each found a joinable host; "macro econ" → join → matched
  with Skyler (Economics) within 9 s. New test: accepts only after the delay; the match
  survives 600 s with no sensor. `make check` passes.

### Deploy on Vultr (D57)
- Both servers: Ubuntu 24.04, swap, ufw 80/443, `provision.sh`, Caddy 2.6.2; `/etc/ghostseats.env`
  from the local `.env` plus `COOKIE_SECURE=true`, `DEMO_HOSTS=true`. Built and started
  `df12bef` on each: `{"ok":true,"db":true}` (Tiger reachable from Vultr).
- Tiger, from server 1: `schema.sql`, `seed.sql`, policies, `seed_demo_hosts` (24 added).
- `https://64.177.55.143.sslip.io` and `https://45.32.219.190.sslip.io`: valid certificates,
  200. Live check: "macro econ" → join → matched with Skyler in under 10 s, Muse icebreaker,
  card image 200.

## 2026-10-27 — Session 9: README audit, demo tag (D58)

An outside review of the public repo found README claims the code did not support and a
quickstart that failed from a fresh clone. Work is on `v3-repoaudit`; nothing pushed.

### Branch and tag
- `v3-repoaudit` starts at local `v2-frontendredo` (`8b4d296`), which already holds `main`, the
  unpushed Synapse rename (`63619cd`) and the README title fix.
- `hacktx-2026` (annotated) → `2197e21`, Sun 11:17, the last commit before the 11:30 demo.
  Local only.
- Removed `firmware/Transmitter Code from Arudino.txt`, a Next.js BLE component, not firmware.

### README claims checked against the code
| README said | Code says |
|---|---|
| Human IR sensor plus object IR sensor | One IR sensor on D2; the bridge copies it into both fields (Q14) |
| Blue = vacant, green = occupied | Firmware and map: green = open, blue = occupied (D54) |
| Arduino streams JSON | Firmware prints `occupied: true|false`; the bridge sends the JSON |
| `DEBOUNCE_S = 1s` | `debounce_s = 5` |
| Vacant / Away / LikelyOpening states | Public states `open`, `occupied`, `likely_opening`, `offline` (FR-6) |
| React 18, Node 18+ | React 19.3.1; Node `^22.12 || ^24` |
| "In-memory by default", `pip install -r pyproject.toml`, `backend/scripts/arduino_bridge.py` | None exist; the Makefile flow and `bridge/` do |

The README was rewritten with a real-vs-simulated table, the verified quickstart, measured test
counts and a limitations section. The team section lists names only.

### Fresh-clone run (scratchpad clone of `v3-repoaudit`, macOS)
- `make sync db-up db-create`, `make vapid-keys`, `.env` as in the README (fresh database
  `ghostseats_fresh` in the existing container, dropped afterwards), then
  `make db-init seed policies seed-history`: "seeded 7269 change rows for 98 seats".
- API on :8001 (:8000 was taken by the dev server): `/api/health` → `{"ok":true,"db":true}`.
  `make fake-node --base-url :8001`, `1 p`: `t1-s1` offline → occupied; LEDs `green` → `red`.
- `npm ci` failed with `EBADENGINE`: Homebrew's npm 7.13 was ahead of Node 24's npm on `PATH`
  and `.npmrc` sets `engine-strict`. A local leftover, not a repo issue: the 2021 Homebrew
  npm was moved aside, and plain `npm ci` then passed (0 vulnerabilities).
- Vite on :5199: page title "Synapse", `/api/health` through the proxy → ok.

### Measured
- `make check`: ruff, mypy `--strict`, 184 passed, 29 skipped.
- `make test-db`: 213 passed.
- `npm test`: 32 passed (7 files). `npm run build`: passes, 77 precache entries.

### Found
- The backend's LED colors (`occupied` → `red`, `seat_engine._LED`) disagree with the firmware
  and the map (blue, D54). Not changed; Q21.

## 2026-10-27 — Session 10: layout, CI, live link, demo GIF (D59)

### Layout
- `git mv` of the frontend into `frontend/`. Its paths are all relative to its own folder, so
  only docs changed. `backend/deploy/deploy.sh` and `make deploy` now default to `origin/main`;
  the image already defaulted to `FRONTEND_DIR=frontend`.
- From `frontend/`: `npm ci` (0 vulnerabilities), `npm run typecheck`, `npm test` (32 passed),
  `npm run build`. `make image`, then the container against the local DB: `/api/health` ok,
  `/` title "Synapse", `/seat/t1-s1` 200, `/sw.js` 200.
- `documentation/*.md` → `docs/`. Live links, the OpenAPI description and the dockerignore entry
  updated; history entries in PLAN and PROGRESS keep the old path. A script resolving every
  relative link in the 8 tracked `.md` files: 0 broken. `make check`: 184 passed, 29 skipped.
- `backend/README.md` deploy notes no longer describe a load balancer (D57).

### ARCHITECTURE
- §1 hardware: an "as built" paragraph (one IR sensor, laptop bridge, Q14) above the original
  parts table, which is kept for reference.

### CI (`.github/workflows/ci.yml`)
- Jobs: `backend` (lint, mypy, `make test-db` against a `timescale/timescaledb-ha:pg16` service),
  `bridge` (10 tests via uv), `frontend` (typecheck, test, build), `image` (`make image`).
  Actions pinned to commit SHAs. Bridge command checked locally: 10 passed.

### Live link
- Live API flow as a demo user: search "macro econ" → join → Skyler (Economics) accepted →
  matched at Welch floor 2 with a Muse icebreaker; the match was cancelled afterwards.
- The first attempt sent `"group": false` and got 422 (`group` is `"related"` or null): my
  request, not a bug.

### Demo GIF (`docs/images/demo.gif`, 6.2 MB, 31 s)
- Throwaway database `ghostseats_demo` (seeded, `make seed-demo`: 24 hosts), API on :8001 with
  `DEMO_HOSTS=true GHOST_S=15` serving `frontend/dist`. Playwright recorded the PCL floor 2
  table while `scripts.fake_node` sent `1 p`, `2 b`, `1 e`, then a seeker (Priya, "orgo exam")
  → join → Hayden (Chemistry) accepted. Frames checked: open → occupied → likely opening → open,
  and the match screen with the icebreaker. Database dropped afterwards.
- `brew install ffmpeg` refused (Command Line Tools too old for macOS 14); used the static
  ffmpeg from the `imageio-ffmpeg` package instead.

## 2026-10-27 — Session 11: engineering pass (D60), branch `v4-engineering`

### Concurrency
- Two new Postgres tests: four concurrent outbox drains over 20 rows, with a barrier in the
  notifier so every drain holds its claim at once, send each row exactly once; and an ingest
  waits on a transaction holding the seat row for `blink_until`, so neither write is lost.
- Re-ran the lock mutations on current code (each restored after):
  - `Lock.WAIT` without `FOR UPDATE`: 7 of 8 concurrent advances raise
    `Conflict('one pending request per search')`.
  - `claim_outbox` without `FOR UPDATE SKIP LOCKED`: the sorted send log starts
    `[0, 0, 0, 0, 1, 1, …]`.
  - With `FOR UPDATE` and no `SKIP LOCKED`: the drains queue, the barrier breaks, the queued
    drains hit `DB_TIMEOUT_S`.
  - `lock_seat_state` without `FOR UPDATE`: the ingest finishes within 0.5 s while the row is
    held.
  - `Lock.SKIP` with no lock, or with a waiting `FOR UPDATE`: the new tick test's tick is still
    blocked after 1 s.
  - `Lock.WAIT` and `Lock.SKIP` both removed: 5 of 6 concurrent ticks raise the `Conflict`.
- `docs/CONCURRENCY.md`: the three mechanisms with their code, what the database doesn't cover
  (instance clocks, connection budget, map snapshots), and the tests.

### Observability
- `app/interface/observability.py`: request id (plain `X-Request-ID` kept, else generated),
  echoed on every response including the generic 500; one access line with the route template.
  `LOG_FORMAT=json` loads `app/log_config.json`, which the image also passes to uvicorn as
  `--log-config`.
- 2 workers with the image's flags: 28 log lines, all JSON, one access line per request.
- `GET /metrics` behind `METRICS_TOKEN` (`Metrics` port, `PrometheusMetrics` adapter, `NullMetrics`
  default). With 2 workers and `PROMETHEUS_MULTIPROC_DIR`, after 20 requests four scrapes each
  reported 20; no token → 401, unset token → 404. A test runs two real processes into one
  directory and checks one render sums them (6).
- `prometheus-client` 0.26.0 added (released 2026-07-24).

### Compose demo
- `compose.yaml` at the root: `db`, a one-shot `init` (keys via `scripts/demo_env.py` into the
  `state` volume, then schema, seed, policies, history, demo hosts) and `api`; `fake-node` under
  the `tools` profile. The image gained `backend/deploy/entrypoint.sh`, which exports
  `SECRETS_FILE` when set and is a pass-through otherwise.
- From the working tree on port 8002: `/` and a deep link 200; three buildings; `fake-node` with
  `1 p` → LED red, `1 b` → still `occupied` (away, inside `GHOST_S`); Priya, "macro econ" →
  Join → matched with Dakota (Economics) at `wel-1-t4` in about 8 s. 54 API log lines, all JSON.
- `down`, then `up`: `init` kept the keys and added nothing (0 history rows, 0 demo hosts).

### Browser e2e (`frontend/e2e/match.e2e.ts`, Playwright 1.64.0)
- Alex hosts `t1-s1` with "orgo 1"; Priya searches and asks; her panel shows "Asking Alex ·
  Biochemistry" and not "Table 01"; Alex accepts; her match shows "PCL Library · Floor 2 ·
  Table 01". Passes in 8.2 s against `compose.yaml` + `compose.e2e.yaml`.
- With the search screen changed to print "at Table 01" before accept, the test fails on
  `not.toContainText`. CI's `image` job became `e2e`, which builds the image through compose.

### Load (`make load-check`, 4 workers with JSON logs and multiprocess metrics)
- 500 phones, 3 runs: p50 1.9–2.4 ms (building), 2.2–2.6 ms (buildings), 25.7–31.1 ms
  (readings); p95 6.8–28.5, 17.1–70.1, 75.3–202.7 ms; no errors in 63,997 requests.
- 1000 phones: 685 requests/s, map p50 under 3 ms. 2000 phones, three runs: p50 52–339 ms on the
  building, p95 1.6–4.0 s, readings starved, up to 3 timeouts. The server-side histogram for one
  of them: p95 ≤ 10 ms on both map routes. 680 phones polling every 1 s (same rate, 730
  connections): p50 4 ms.
- Ruled out: CPU (instantaneous: no worker above 24%, no generator process above 31%), swap
  (swap-ins 41/s during a run vs 45/s idle), listen queue (0 overflows). 8 workers with
  `DB_POOL_SIZE=2`: no better. 16 generator processes: worse (45 timeouts).

### Bugs (cause → fix)
1. **Port 8000 answered from the internet on both servers** (`curl http://<ip>:8000/api/health`
   → 200, bypassing Caddy and TLS). Cause: the deploy compose published `8000:8000`, and Docker
   publishes through its own iptables chain, which ufw doesn't filter. Fix `d52f426` binds
   127.0.0.1; live after the next deploy.
2. **`test_skip_locked_scheduler_ticks_do_not_collide` could not fail.** Found by removing
   `SKIP LOCKED` and watching it pass. Cause: its setup posted a reading after expiring the
   request, and ingest advances the search itself (`advance_session` → `advance_search`), so
   the ticks found nothing. Fix `e6181bf` (renamed `…concurrent_scheduler_ticks…`) expires the
   request in the database and asserts it is still pending before the ticks.

Caught before committing:
- JSON mode re-enabled uvicorn's access log: setting `propagate` on `uvicorn.access` undid
  `--no-access-log`, and `dictConfig` resets the children of any logger it configures. The
  JSON config now turns `uvicorn.access` off explicitly; a test pins it.
- With `--workers`, uvicorn's supervisor process logged in plain text, since it never calls
  `build()`. Hence `--log-config` in the image.
- `docker compose run fake-node` re-ran `init` through `depends_on`, and the first stdin lines
  were lost while it did. `fake-node` no longer depends on anything.
- The first e2e run posted only `t1-s1`, so `t1-s2` read as no signal and the host was hidden
  (no open seat at the table, FR-24). A real node reports all its seats; the test now does too.
- A formatting error reached a local commit because `make lint | tail` hid make's exit status;
  amended before any push.

### Not verified
- None of D60 is deployed. Before the next deploy, confirm each server's Caddyfile proxies to
  `localhost:8000` (or `127.0.0.1:8000`), since the port is no longer published on the public
  address.
- Push to real devices; `npm audit` reports 4 low findings, all in `workbox-build`'s
  `deepmerge`, already present before this session.

## Next steps
1. **Before redeploying,** check each server's Caddyfile upstream (bug 1). Then
   `HOSTS="root@64.177.55.143 root@45.32.219.190" make deploy` from `backend/`, and confirm
   `http://<ip>:8000` no longer answers.
2. **Branch cleanup:** `v1`, `v1frontend`, `v1backend`, `v1final`, `v2-frontendredo`,
   `Arduino/Transmitter-Code`, `v3-repoaudit`, `v4-engineering`, and the `Hacktx2026-v2`
   worktree; all are contained in `main`.
3. **Load:** run the generator from a second machine to find where 2000 connections stall.
4. **Q22:** a license, with the team.
5. **Q14 / D58:** thermal + IR hardware for real ghost-seat detection.
