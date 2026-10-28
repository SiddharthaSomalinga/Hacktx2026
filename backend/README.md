# Synapse backend

FastAPI service that turns per-seat sensor readings into public seat states and runs the study
matching flow on top of them.

- **Readings.** Each reading is two booleans, `object_present` and `human_present`, stored
  change-only in a TimescaleDB hypertable.
- **Seat state.** A pure state machine derives `open`, `occupied`, `likely_opening` and
  `offline`.
- **Timers.** Every timeout (ghost seat, request expiry, host absence) is a stored timestamp,
  evaluated when an entity is read, when its seat reports, or by a scheduler tick. Transitions
  are applied under `SELECT … FOR UPDATE`, and the tick claims rows with
  `FOR UPDATE SKIP LOCKED`, which lets every instance run it at once.
- **Guarantees.** At most one pending request per search, and one active match per host and per
  seeker. Push delivery is at-least-once.

What it must do is specified in `../docs/REQUIREMENTS.md`; how it is built is in
`../docs/ARCHITECTURE.md`.

## Stack

| Piece | Choice |
|---|---|
| Language | Python 3.12 (uv, `uv.lock` committed) |
| API | FastAPI, Pydantic v2 models as the contract (`/docs`) |
| Database | PostgreSQL 16 + TimescaleDB 2.31 (local: `timescale/timescaledb-ha:pg16`) |
| Driver | psycopg 3 with `psycopg_pool`, raw parameterized SQL |
| Push | Web push with VAPID (`pywebpush`) through a transactional outbox |
| Tests | pytest, ruff, mypy `--strict` |

## Layout

| Path | What lives there |
|---|---|
| `app/domain/` | Pure logic: seat engine, simulation, recommendations, matching, lifecycle decisions. No I/O; a test enforces it. |
| `app/services/` | Use cases; `lifecycle.py` applies transitions under row locks; `ports.py` defines the repository, AI, notifier and clock interfaces. |
| `app/adapters/` | Postgres repository (all SQL), fallback AI, web push, clock |
| `app/interface/` | Routes, request/response schemas, error mapping |
| `app/worker.py` | Scheduler tick and push sender, one thread per process |
| `sql/` | `schema.sql` (tables, hypertable, history function, rollup job), `seed.sql` |
| `scripts/` | `fake_node`, `seed_history`, `seat_qr`, `vapid_keys`, `load_check`, `db` |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 itself)
- Docker, for the local database. The image is 3.2 GB.
- `make`

## Quick start

```bash
cd backend
make sync                 # dependencies from uv.lock
make db-up                # Postgres + TimescaleDB on localhost:5433
make db-create            # databases: ghostseats (dev) and ghostseats_test
```

Create `backend/.env` (git ignores it):

```bash
DATABASE_URL=postgresql://postgres:ghostseats@localhost:5433/ghostseats
SECRET_KEY=<python3 -c 'import secrets; print(secrets.token_urlsafe(48))'>
NODE_KEY=<python3 -c 'import secrets; print(secrets.token_urlsafe(24))'>
VAPID_SUBJECT=mailto:you@example.com
# plus the two lines printed by: make vapid-keys
```

Then:

```bash
make db-init seed policies seed-history
make dev                  # http://localhost:8000, contract at http://localhost:8000/docs
```

In a second terminal, play the hardware:

```bash
make fake-node            # type "1 p" (person), "1 b" (bag only), "1 e" (empty), "q"
```

A seat changes only after a new state has held for `DEBOUNCE_S` (5 s), and a bag-only seat
turns yellow after `GHOST_S` (30 s; the demo uses 15). For printed seat codes:
`make qr ORIGIN=https://<deployed-host>` writes `out/seat-qr.html`.

## How the request cascade stays single

A seeker's join sends one request at a time, to the top-ranked findable host. The next host is
asked when that request is declined, expires or is skipped. Several things can advance the same
search at once: the seeker polling, the host polling, the seat reporting, and the scheduler
tick on every instance. This is the step that sends:

```python
# Rank outside any lock: the AI call may take up to AI_TIMEOUT_S.
with self._ctx.repo.read() as tx:
    candidates = [...]
scores = self._ctx.ai.rank_hosts(topic_of(search), candidates)
ranked_ids = [s.id for s in rank((c.session for c in candidates), scores)]

with self._ctx.repo.tx() as tx:
    search = tx.search(search_id, Lock.WAIT)
    if search is None or not needs_send(search, tx.pending_request_for_search(search_id)):
        return  # another trigger already acted
```

- `Lock.WAIT` becomes `SELECT … FROM searches WHERE id = %s FOR UPDATE`. Concurrent advancers
  queue on that row.
- `needs_send` is re-checked *after* the lock is held, so the second advancer finds the pending
  request the first one created and returns.
- Ranking happens before the lock, so a slow AI call never holds a row lock.
- The partial index `requests_one_pending ON requests (search_id) WHERE status = 'pending'` is
  the backstop. I removed the `FOR UPDATE` and ran 8 concurrent advances against Postgres: 7 of
  8 failed with `Conflict('one pending request per search')`. With the lock, all 8 succeed and
  exactly one request exists (`tests/api/test_postgres_e2e.py`).

The scheduler calls the same functions with `FOR UPDATE SKIP LOCKED`, so a tick never waits on
a search that a request or another instance is advancing; it leaves it for the next tick.
[CONCURRENCY](../docs/CONCURRENCY.md) lists every concurrency test and the lock each one catches.

## Logs and metrics

- **Logs.** With `LOG_FORMAT=json`, which the image sets, every line is one JSON object,
  uvicorn's included. Each request gets an id, taken from a plain `X-Request-ID` header or
  generated, that comes back in the response header and is on every line the request writes.
  The access line carries the route template (`/api/requests/{request_id}`), status and
  `duration_ms`.
- **Metrics.** `GET /metrics` with `Authorization: Bearer $METRICS_TOKEN` returns Prometheus
  text: request latency by route template and status, scheduler tick duration, push outcomes
  (`sent`, `retry`, `gave_up`), AI fallbacks by call, and the unsent outbox rows, counted at
  scrape time. Paths no route matches share the label `unmatched`.
- **Several processes.** A scrape reaches one uvicorn process. With `PROMETHEUS_MULTIPROC_DIR`
  set (the image does), every process writes its samples there and each scrape sums them. With
  2 workers I sent 20 requests and scraped four times: every scrape reported 20.

## Tests

```bash
make check                # ruff, mypy --strict, unit + in-memory tests
make test-db              # + Postgres tests against ghostseats_test (truncated each test)
```

201 tests pass with Postgres (174 pass and 27 are skipped without it). They cover:

- **Seat engine.** Each threshold at its exact boundary.
- **User flows.** Both flows end to end over HTTP, with a simulated node posting every 2 s.
- **Repository conformance.** The same suite runs against the in-memory reference and against
  Postgres. It caught two history SQL bugs the in-memory tests could not:
  - a `WHERE` evaluated before `lead()`;
  - `LEAST`/`GREATEST` skipping NULLs.
- **Read/write split.** The replica URL connects as a SELECT-only role, so any write on the read
  path fails.
- **Mutation checks.** Breaking key rules makes tests fail: a backpack counting as presence,
  the cascade crossing groups, simulated hosts receiving requests, the `>=` on the ghost timer.

## Load check

`make load-check` creates 50 load-test nodes (4 seats each), runs 500 phones polling
`/api/buildings` and `/api/buildings/pcl` every 3 s with `If-None-Match`, has every node post
every 2 s, and then removes the load-test data.

| Endpoint, 3 runs × 60 s | p50 | p95 | max |
|---|---|---|---|
| `GET /api/buildings/pcl` (mostly 304) | 1.9–2.4 ms | 6.8–28.5 ms | 129–1015 ms |
| `GET /api/buildings` | 2.2–2.6 ms | 17.1–70.1 ms | 168–1478 ms |
| `POST /api/readings` | 25.7–31.1 ms | 75.3–202.7 ms | 257–1549 ms |

- **Setup.** Apple M1, 8 GB, macOS 14.6. Four uvicorn workers with `LOG_FORMAT=json` and
  `PROMETHEUS_MULTIPROC_DIR`, as in the image. Postgres in Docker Desktop's VM (4 CPUs, 2 GB).
  The generator ran on the same laptop as 4 processes.
- **Throughput.** About 355 requests/s, the full offered load, with no errors in 63,997
  requests.
- **The ramp.** `ARGS="--clients 1000 --procs 6"`: 685 requests/s, map p50 under 3 ms, no errors.
  `ARGS="--clients 2000 --procs 8"`, three runs: p50 52–339 ms on the building, p95 1.6–4.0 s,
  readings starved (921–1221 posts instead of about 1450), up to 3 timeouts.
- **What broke was connections, not requests.** The server-side histogram from `/metrics`,
  diffed across a 2000-client run, put p95 at ≤ 10 ms for both map routes and ≤ 100 ms for
  readings. `ARGS="--clients 680 --poll 1 --procs 8"` offers the same rate over 730 connections
  and got 1291 requests/s at a p50 of 4 ms. Instantaneous CPU never passed 24% for any server
  worker or 31% for any generator process, swap-ins stayed at the idle rate, and the kernel
  counted no listen-queue overflows. 8 server workers (with `DB_POOL_SIZE=2`) and 16 generator
  processes were no better. The generator and the server share the laptop, so the next step
  is a generator on a second machine.
- **Building list rarely 304s.** Its counts change every second under random node traffic, so
  its ETag rarely repeats. The building detail is mostly 304.

## Deploy

Two Vultr instances (D57). Each builds and runs one image, the API with its worker thread and
the built frontend, behind Caddy, which terminates HTTPS with a Let's Encrypt certificate for
`<ip>.sslip.io`. The container's port is published on 127.0.0.1 only, so traffic reaches it
through Caddy.

```bash
# once per server, as root on a fresh Ubuntu 24.04 instance
bash provision.sh https://github.com/SiddharthaSomalinga/Hacktx2026.git
# then fill /etc/ghostseats.env (mode 600) from .env.example, with COOKIE_SECURE=true

# from backend/ on your laptop, for any commit already pushed
make deploy HOSTS="root@<ip-1> root@<ip-2>" REF=origin/main
```

- **Rolling.** `deploy.sh` updates one host at a time and waits for its container health check
  before the next. A commit that is not on GitHub is refused before any host is touched.
- **A failed host stops the rollout.** I tested it with an empty `SECRET_KEY`. The config check
  kills uvicorn's workers, the container never turns healthy, and the script prints the last
  50 log lines and exits. The other host keeps serving the old commit. The broken host stays
  broken until the next deploy.
- **A short gap per host.** There is no load balancer (D57): each server is reached at its own
  address, so the one being restarted is unreachable for a few seconds.
- **`make image`** builds the same image locally, with the frontend from `frontend/`.

## Security

- **Validation.** Every input is bounded by a Pydantic model or path parameter, including ids
  in URLs (≤ 64 chars). Malformed uuids are "not found", never a database error.
- **SQL** is parameterized only.
- **Authorization.** Searches, requests and matches are checked per object against the
  logged-in user.
- **Session cookie.** Signed, `HttpOnly`, `SameSite=Lax`, and `Secure` when
  `COOKIE_SECURE=true`.
- **Node key.** Compared in constant time; nodes can only write their own seats.
- **Metrics.** `/metrics` is a 404 unless `METRICS_TOKEN` is set, and then needs that bearer
  token, compared in constant time.
- **Failures.**
  - Unexpected errors return a generic 500 with details only in the log.
  - A database outage returns 503 `database_unavailable` within the 5 s pool wait.
- **Static files.** The frontend mount refuses path traversal, and unknown `/api/*` paths stay
  JSON 404s.
- **Dependency audit.** `pip-audit` on the locked runtime dependencies found no known
  vulnerabilities (2026-10-24).

## Limitations

- **Demo login.** Anyone can log in as any demo user (NFR-7). Swapping in SSO touches only the
  auth service and the `current_user` dependency.
- **Muse is on the request path.** With `MUSE_API_KEY` set, topic cleanup, ranking and the
  icebreaker call Muse Spark (D38). Live calls took 1.3–2.5 s against the 4 s `AI_TIMEOUT_S`;
  the first is slowest because it opens the TLS connection. A slower or failed call is answered
  by the rule-based fallback, so a seeker can wait up to 4 s for a worse answer. Topics are
  cached, so each distinct topic text is sent once.
- **Push is at-least-once.** The sender pushes inside the transaction that marks the row sent;
  if a process dies between the push and the commit, the notification is sent again.
- **Timer lag.** A timer fires up to `SCHEDULER_TICK_S` (2 s) late when nobody polls, and the
  map can be up to `MAP_CACHE_S` (1 s) stale per instance.
- **Connection budget.** Processes × instances × `DB_POOL_SIZE` (5) has to fit inside the
  database's connection limit. The local image allows 25; Tiger Data's limit is not checked
  yet.
- **Placeholder seat ids.** The demo table uses node `table-1` and seats `t1-s1`, `t1-s2` until
  the hardware ids replace them in `sql/seed.sql`.
- **Not deployed yet**, so web push has only been exercised against a test double, and the
  rollout was tested on this laptop with a stand-in for `ssh`, not on Vultr.
