# Running several instances

Every API container runs `WEB_CONCURRENCY` uvicorn processes (2 by default). Each process
serves requests and runs a worker thread that ticks the scheduler and drains the push outbox
every `SCHEDULER_TICK_S` (2 s). The live deployment has two containers on two servers, all
sharing one Postgres (D57). Nothing of record lives in process memory (NFR-8), so every
rule below is enforced by the database, and adding an instance needs no coordination.

Three things change shared state: a request handler, a sensor ingest, and the tick. Any of
them can advance the same search, match or host session at the same moment.

## 1. Lock the row, then decide

Each advance re-reads its row `FOR UPDATE` inside a transaction and only then asks the pure
domain function what to do. This is the send step of `LifecycleService.advance_search`:

```python
with self._ctx.repo.tx() as tx:
    search = tx.search(search_id, Lock.WAIT)  # SELECT … FOR UPDATE
    if search is None or not needs_send(search, tx.pending_request_for_search(search_id)):
        return  # another trigger already acted
```

- `Lock.WAIT` appends `FOR UPDATE`. A second transaction that wants the same search blocks
  until the first commits.
- When the waiter wakes up, Postgres hands it the committed row. Read Committed re-reads a row
  it waited for. So `needs_send` sees the request the first transaction inserted and returns
  False.
- Muse ranks the hosts *before* this transaction, between two short ones. The ranking can
  take up to `AI_TIMEOUT_S` (4 s), and no lock is held while it runs (NFR-3). The re-check
  after re-locking is what makes that safe: the world may have moved while Muse was busy.
- The database also refuses the duplicate on its own. `requests_one_pending` is a partial
  unique index on `requests (search_id) WHERE status = 'pending'`, and it surfaces as
  `Conflict("one pending request per search")`. The other one-at-a-time rules (live session
  per user and per seat, active search, active match) are partial unique indexes too.

Accept and arrival lock the seat's `seat_state` row to set `blink_until`, the same row
ingest rewrites on every reading. Without the lock, whichever transaction commits second
erases the other's write: a lost reading or a lost blink.

## 2. Ticks skip what someone else holds

The tick selects due ids without a lock, then advances each one in its own transaction:

```python
for search_id in searches:
    self._lifecycle.advance_search(search_id, Lock.SKIP)
```

- `Lock.SKIP` appends `FOR UPDATE SKIP LOCKED`. If a request handler or another instance's
  tick holds the row, the query returns nothing and the tick moves on. The row is still due,
  so a tick 2 s later picks it up.
- One transaction per row keeps locks short, and rows already advanced stay committed if a
  later one fails.
- SKIP LOCKED is about waiting, not duplicates. With every worker ticking every 2 s, a
  plain `FOR UPDATE` would queue each tick behind any slow transaction on the same row. The
  duplicate guard is section 1's lock and index, which is why the concurrent-ticks test
  below still passes with either lock removed on its own.

## 3. Push goes through a transactional outbox

A transition and its notification row commit in the same transaction, so a committed
transition always has its notification and a failed push never undoes a transition (D30).
The drain claims rows like this, then sends and marks them in the same transaction:

```sql
SELECT id, user_id, kind, payload, attempts FROM notification_outbox
WHERE sent_at IS NULL ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED
```

- `WHERE sent_at IS NULL` selects only rows nobody has finished.
- `ORDER BY id` sends roughly in the order the transitions committed.
- `FOR UPDATE` holds each claimed row until this drain commits, so no other drain can send it.
- `SKIP LOCKED` lets the other drains take the next rows instead of waiting on these.
- **At-least-once.** The send happens before the commit. If a process dies after the push
  service accepted a message and before the commit, the lock is released with `sent_at`
  still NULL, and the next drain sends that message again. Committing the row and the push
  service's acceptance together isn't possible. The service worker tags each notification
  with its URL, so a duplicate replaces the one on screen instead of stacking.
- A failed send leaves the row unsent with `attempts + 1`, and it is retried on later ticks
  up to `PUSH_MAX_ATTEMPTS` (5). A 404 or 410 from the push service deletes the subscription.

## 4. Live hints are sent by the commit

Each process holds its own live streams (D61), so a change committed on one instance must
reach streams on all of them. Postgres `NOTIFY` does that, and its transactional rules are
why it is safe:

```sql
SELECT pg_notify(%s, p) FROM unnest(%s::text[]) AS p   -- channel synapse_live, run just before COMMIT
```

- A notification is delivered only when its transaction commits. A rolled-back write hints
  nothing, so no stream refetches for a change that never happened.
- Notifications reach every listener in commit order, and identical ones within one
  transaction are folded into one.
- Each process listens on one unpooled connection. A hint only says "look again"; the hub
  re-reads the snapshot, so a lost hint costs latency, never correctness. The periodic
  rebuild every `LIVE_CHECK_S` bounds that latency.
- A listener that stops reading would fill Postgres's notification queue (8 GB by default),
  and then committing transactions that NOTIFY would fail. Each listener reads continuously
  and proves its connection with a self-notification every `LIVE_FEED_PROBE_S`.
- The scheduler's sweep (ARCHITECTURE §14) runs on every instance, so a time-driven hint can
  arrive once per instance. Clients don't restart a refetch already in flight, which folds
  the duplicates.

## 5. What the database doesn't cover

- **Clocks.** Services read `now` from their own instance's clock, not from Postgres.
  Deadlines compare timestamps that different instances wrote, so clock skew between servers
  moves a deadline by the skew. NTP keeps that to milliseconds, against thresholds measured
  in seconds.
- **Connections.** Processes × instances × (pools × `DB_POOL_SIZE` + 1 live listener) has
  to fit within the database's `max_connections` (ARCHITECTURE §11).
- **Map snapshots.** Each process caches a building's map for `MAP_CACHE_S` (1 s), so two
  instances can show a seat change up to 1 s apart. The cache is derived, never written back.

## Tests

All are in `backend/tests/api/test_postgres_e2e.py` and run against real Postgres with
`cd backend && make test-db`. They use threads, and each thread has its own pooled
connection, so Postgres sees separate sessions exactly as it would from separate instances.
Each lock was removed in turn, the test run, and the code restored:

| Test | What runs at once | Lock removed | Result |
|---|---|---|---|
| `test_concurrent_advances_send_exactly_one_request` | 8 threads advance one search | `FOR UPDATE` (`Lock.WAIT`) | 7 of 8 raise `Conflict('one pending request per search')` |
| `test_concurrent_scheduler_ticks_do_not_collide` | 6 ticks on one due search | `Lock.WAIT` and `Lock.SKIP` together | 5 of 6 ticks raise the same `Conflict`. Either lock alone: still passes |
| `test_a_tick_skips_a_search_another_transaction_holds` | a tick while a transaction holds the search | `SKIP LOCKED`, or all of `FOR UPDATE SKIP LOCKED` | the tick is still blocked after 1 s |
| `test_concurrent_drains_send_each_notification_once` | 4 drains over 20 rows; a barrier in the notifier holds every drain's first send until all have claimed | `FOR UPDATE SKIP LOCKED` | the sorted send log starts `[0, 0, 0, 0, 1, 1, …]`: every drain claimed the same rows |
| same | same | `SKIP LOCKED` only | the drains queue behind the first one's rows, the barrier times out, and the queued drains hit `DB_TIMEOUT_S` (`Unavailable`) |
| `test_seat_lock_keeps_a_reading_and_a_concurrent_blink` | an ingest while a transaction holds the seat row to set `blink_until` | `FOR UPDATE` in `lock_seat_state` | the ingest finished within 0.5 s while the row was held |

The live hints have their own Postgres tests, also run by `make test-db`:

| Test | Shows | Broken on purpose | Result |
|---|---|---|---|
| `tests/repo_contract/test_live_hints.py` (both repositories) | each write hints the right users and buildings; a rollback hints nothing | the flush before COMMIT removed | every Postgres hint test fails |
| `tests/test_live_feed_pg.py::test_a_killed_listener_reconnects_and_says_resync` | `pg_terminate_backend` on the listener → `Lost`, then `Resync`, then hints again | — | — |
| `tests/test_live_feed_pg.py::test_a_write_on_one_instance_reaches_a_stream_on_another` | two instances on one database; the periodic rebuild set to 30 s, so only NOTIFY can deliver within 1 s | — | — |

The concurrent-ticks test used to pass for the wrong reason. Its setup posted a sensor
reading after expiring the request, and that ingest advanced the search itself, so the six
ticks found nothing to do. It now expires the request in the database and checks that it is
still pending before the ticks start.
