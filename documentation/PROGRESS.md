# PROGRESS.md — Ghost Seats

Session log. Concrete changes, commands and observed results only.

## Current status

- **Milestone:** backend B0–B5 built and verified locally on Postgres 16 + TimescaleDB 2.31.
  Remaining backend steps wait on other roles or unknowns (PLAN: H0 hand-off, the D36 deploy,
  U1 Muse, IC1–IC3).
- **Tests:** 177 pass with Postgres (`make test-db`); 150 pass and 27 skip without it.
- **Open questions:** Q2, U1, U2 (Tiger Data connection limit) (PLAN). U3 resolved: D36, D37.

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

## Next steps
1. **Frontend integration (IC1).** The partner merges `origin/v1backend` into their branch and
   points the Vite proxy at `make dev`.
2. **H0:** the hardware pair's node and seat ids replace the placeholders in `sql/seed.sql`.
3. **Deploy (D36, D37):** Vultr instances and load balancer, `.tech` DNS on Vultr. Set `DB_POOL_SIZE` against the database limit, `COOKIE_SECURE=true`,
   `FRONTEND_DIST`. Run `make policies` on Tiger Data, then `make qr ORIGIN=…`.
4. **U1:** add the `MuseAI` adapter behind `TopicAI` once access exists.
