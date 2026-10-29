---
title: "Synapse: Requirements Specification"
subtitle: "v1.1"
---

# Changes from v1.0

Decision numbers refer to `PLAN.md`, decision log.

- **FR-11** Recommendations widen from table to floor to building to nearest building, and report the level found (D21).
- **FR-20, FR-21, FR-24** Turning on host mode opens host setup. The session is created at link and is findable only once a topic is set (D17).
- **FR-25, FR-26, FR-41** "Absent" means no person present, whether or not belongings remain on the seat (D18).
- **FR-27** Hidden while the confirmation prompt is up; `CONFIRM_GRACE_S` to answer; new confirm endpoint (D24).
- **FR-28** Muting from a request declines that request; unmuting is allowed (D20).
- **FR-29, FR-31–FR-33** Each search has one offered group. The cascade stays inside it, skips simulated hosts and recomputes candidates at every hop. Join is hidden when the group has no real hosts (D15, D19, D22).
- **FR-37** The assigned seat is the open seat at the host's table nearest the host.
- **FR-39** The alternative seat appears in both match views (D25).
- **FR-48** Simulated hosts never receive requests (D22).
- **FR-49** History comes from change-only readings as time in state, over `HISTORY_WINDOW_H` (D31).
- **New:** FR-50 one role at a time (D23) · FR-51–FR-53 push notifications (D28, D30) · FR-54 optional related-subject retry (D19).
- **NFR-2** Timeouts are evaluated on read/write, on sensor ingest and by one scheduler tick (D29). **NFR-4** Installable PWA (D28). **New NFR-8** horizontal scale (D32).
- **Found during the build (v1.1, same release):** `label`, `searches.joined_at`, `host_sessions.confirm_notified_at` (§6); `table_not_found`, `seat_taken`, `database_unavailable` (§7); `PUSH_MAX_ATTEMPTS`, `FRONTEND_DIST`, `COOKIE_SECURE`, `WORKER_ENABLED`, `DB_POOL_SIZE` (§8); Q12 values 24 h / 30 days.
- **D42, D43** Requests wait 5 minutes; first name and major are visible before accept on both sides and in the request push; Muse ranks and writes icebreakers with majors.
- **§8 (D38, D41)** `MUSE_BASE_URL`, `MUSE_MODEL`, `DB_TIMEOUT_S`.
- **FR-31 (D56)** Demo mode lets simulated hosts take and accept requests; off by default.
- **§7 (D53)** `GET /api/seats/:id`; block and report by request or match id; ids on the match and search status.
- **HW-7 (D62)** The bridge's backend URL setting is `SYNAPSE_URL`; `GHOSTSEATS_URL` still works.
- **§6** Adds `buildings.lat/lng`, `keywords`, `offered_group`, change-only `seat_readings` with offline markers, `push_subscriptions` and `notification_outbox`. **§7** New and changed endpoints, node key, error codes. **§8** New keys and an environment table.

# 1. Overview

Synapse is a web app, installable on phones as a PWA, backed by seat
sensors. It shows which library seats are open, occupied, or held by
belongings with no one present ("ghosted"). It also lets students studying the
same course find each other and sit together.

**In scope:** seat sensing and state, the live seat map, seat recommendations,
topic-based study matching, host mode, safety controls, simulated buildings,
occupancy history and push notifications.

**Out of scope:** see section 11.

# 2. Roles

| Role | Description | Login |
|---|---|---|
| Visitor | Browses the map and seat recommendations | No |
| Seeker | Enters a topic and requests to join a host | Yes |
| Host | Is seated, linked to a seat, and open to study partners | Yes |

# 3. System components

| Component | Responsibility |
|---|---|
| Seat node firmware | Reads per-seat sensors, drives per-seat LEDs, exchanges serial messages with the bridge |
| Bridge | Relays sensor readings from the node to the backend and LED commands back |
| Backend API | Seat-state engine, recommendations, matching, AI calls, safety controls, scheduler tick, notification outbox |
| Database | Persistent state; seat readings stored as change-only time-series data |
| Web client | Phone-first UI for visitors, seekers and hosts; installable PWA with a push service worker |
| AI adapter | Topic normalization, host ranking, icebreakers; every call has a non-AI fallback |
| Push sender | Delivers web push notifications (VAPID) from the notification outbox |

# 4. Functional requirements

## 4.1 Seat state

- **FR-1** The backend shall accept per-seat readings with two booleans: `object_present` and `human_present`.
- **FR-2** The backend shall derive a candidate state per reading: human present is *occupied*; object present with no human is *away*; neither is *open*.
- **FR-3** A candidate state shall be committed only after it holds for `DEBOUNCE_S`.
- **FR-4** An *away* seat shall be reported as *occupied* until it has been away for `GHOST_S`, then as *ghosted*.
- **FR-5** A seat with no reading for `OFFLINE_S` shall be reported as *offline*.
- **FR-6** Public interfaces shall expose only `open`, `occupied`, `likely_opening` (ghosted) and `offline`. They shall never expose how long a seat has been away.
- **FR-7** The backend shall return an LED command per seat on every reading: open = green, occupied = red, ghosted = yellow, offline = off. A seat in an active blink window shall return blue blink instead.

## 4.2 Seat map and recommendations

- **FR-8** The client shall show all buildings with counts of open, likely-opening, occupied and offline seats, colored by open share (green ≥ 30%, yellow 10–29%, red < 10%, grey offline).
- **FR-9** The client shall show a building's floors, tables and seats with each seat's public state.
- **FR-10** The client shall refresh map data every `POLL_WEB_S` without a page reload.
- **FR-11** The backend shall recommend one seat for the client's current selection. It searches the selected table first, then that table's floor, then the whole building. At each level an open seat is preferred, and a likely-opening seat (labeled as such) is chosen only if no seat is open. Ties go to the seat nearest the selection, then the lowest seat position. If the building has no open or likely-opening seat, the response names the nearest building that has open seats. The response states the level at which the seat was found.
- **FR-12** The recommended seat shall be highlighted with a style distinct from all seat-state colors.
- **FR-13** Simulated buildings shall be visibly labeled as simulated.

## 4.3 Accounts

- **FR-14** Browsing the map and recommendations shall not require login.
- **FR-15** Searching, hosting, matching, blocking, reporting and push opt-in shall require login.
- **FR-16** Login shall be a demo-user picker that sets a session cookie. No passwords.

## 4.4 Topic input

- **FR-17** On opening the map, a logged-in or anonymous user shall be prompted "What are you studying today?" with an option to skip.
- **FR-18** Submitting a topic shall require login, then normalize free text to `{course_code, subject, keywords}` through the AI adapter. A topic typed before login shall be kept and submitted after login.
- **FR-19** The client shall display the normalized label (e.g. "CH 320M · Organic Chemistry I").

## 4.5 Host mode

- **FR-20** A user shall be able to turn on "Open to study partners" for one session. It is off by default. Turning it on opens host setup (link, then topic). It does not by itself make the user findable.
- **FR-21** A host shall link to a seat by selecting it on the building view or by opening that seat's URL (`/seat/{seat_id}`), for example from a QR code on the seat. Linking creates the host session.
- **FR-22** Linking shall succeed only if the seat read `human_present = true` within the last `HUMAN_FRESH_S`.
- **FR-23** A host shall enter a topic and an optional short "about me" text.
- **FR-24** A host shall be findable only while all of the following hold:
  - the session is open, not muted and not ended;
  - no confirmation is pending (FR-27);
  - the host has entered a topic;
  - the linked seat reads a person present;
  - the host has no active match and no active search (FR-50);
  - the host's table has at least one `open` seat.
- **FR-25** While the linked seat reads no person present, whether or not belongings remain on it, the host shall be hidden from search. Any pending request to the host shall be marked skipped. The host becomes findable again when a person is present.
- **FR-26** A host session shall end when the linked seat has had no person present for `HOST_END_S`, whether or not belongings remain, or when the host turns it off.
- **FR-27** When a session reaches `SESSION_MAX_S`, the host shall be hidden from search and asked to confirm they are still open to partners. Confirming within `CONFIRM_GRACE_S` renews the session for another `SESSION_MAX_S`. No confirmation within `CONFIRM_GRACE_S` ends the session.
- **FR-28** A host shall be able to mute new requests from the host panel or from an incoming request. Muting from a request declines that request silently (FR-36). A host shall be able to unmute.

## 4.6 Search and requests

- **FR-29** A search shall return findable hosts in two groups, same course and related (same subject), aggregated by building and floor with counts. No names. Simulated hosts are included in the counts. The search shall record its offered group: same course if that group has any hosts, otherwise related. The client shall hide Join when the offered group has no real (non-simulated) host.
- **FR-30** Within each group, hosts shall be ranked by the AI relatability score, falling back to keyword overlap.
- **FR-31** "Join" shall send a request to the top-ranked real host in the offered group only. Simulated hosts never receive requests. *(Demo mode, D56: with `DEMO_HOSTS` on, simulated hosts receive requests and accept them after `DEMO_ACCEPT_S`.)*
- **FR-32** A request shall expire after `REQUEST_TIMEOUT_S`. On decline, expiry or skip, the next host shall receive it. The next host is the top-ranked real host in the offered group, recomputed at that moment, excluding hosts already tried.
- **FR-33** After `MAX_HOSTS_PER_SEARCH` hosts, or when no untried real host remains in the offered group, the search shall end as exhausted. The seeker shall see "No one's free right now" with seat recommendations. The cascade never moves to the other group.
- **FR-34** A seeker shall have at most one active search and at most `MAX_REQUESTS_PER_HOUR` requests per hour.
- **FR-35** A seeker shall be able to cancel a search, withdrawing any pending request.
- **FR-36** A host's request card shall show the seeker's first name and major, the course and the host's table, with the actions Accept, Not now and Mute. Declines shall be silent to the seeker (D43).

## 4.7 Match lifecycle

- **FR-37** On accept, the backend shall:
  - create a match;
  - generate an icebreaker;
  - select a card image by subject;
  - assign the open seat at the host's table nearest the host's seat;
  - start a `BLINK_S` blue blink on the host's seat.
- **FR-38** The match view shall show the other person's first name, building, floor, table, assigned seat, icebreaker and card image.
- **FR-39** If the assigned seat becomes occupied before arrival, both the seeker's and the host's match views shall show the nearest open seat on the same floor.
- **FR-40** The seeker shall be able to mark "I'm here", which restarts the blue blink and completes the match.
- **FR-41** A match shall be cancelled if the host's seat has had no person present for `HOST_LEAVE_CANCEL_S`, whether or not belongings remain, or if either side cancels.
- **FR-42** A match shall expire if the seeker has not marked "I'm here" within `MATCH_TIMEOUT_S`. The host becomes findable again.

## 4.8 Safety and privacy

- **FR-43** Before a request is accepted, only a first name and major are shown: the seeker's on the host's request card, and the asked host's on the seeker's waiting screen. Location stays hidden until accept (FR-44) (D43).
- **FR-44** Location shall be shared only as building, floor, table and seat after acceptance. No live location.
- **FR-45** Users shall be able to block and report from every request and match view. A report shall also block. Blocks apply in both directions.
- **FR-46** No images or audio shall be stored.

## 4.9 Simulation

- **FR-47** The system shall support simulated buildings whose seat states are computed on read from a hash of the seat id and the current time slot (`SIM_SLOT_S`), with a per-building busyness level.
- **FR-48** The system shall support seeded simulated host sessions on simulated seats. They are always findable and counted in search results, but never receive requests (FR-31).

## 4.10 Occupancy history

- **FR-49** The system shall provide hourly average open-seat counts per building over the last `HISTORY_WINDOW_H` hours for a history chart. The counts are computed as time spent open from stored and seeded change-only readings, and offline time is excluded.

## 4.11 Roles

- **FR-50** A user shall hold at most one role at a time. A user with an active host session cannot start a search (`already_hosting`). A user with an active search, or an active match as seeker, cannot link a seat (`already_searching`).

## 4.12 Notifications

- **FR-51** A logged-in user shall be able to opt in to push notifications. On iOS this requires the app to be installed to the Home Screen.
- **FR-52** Push notifications shall be sent when:
  - a request arrives (host);
  - a request is accepted (seeker);
  - a match is cancelled or expires (both);
  - a search is exhausted (seeker);
  - a confirmation is needed (FR-27) or a session ends (host).

  No notification is sent for an alternative seat (FR-39).
- **FR-53** Notification payloads shall contain nothing beyond first name and major before a request is accepted (FR-43), and no location beyond building, floor, table and seat (FR-44).
- **FR-54** *(Optional.)* When a same-course search ends exhausted and related-subject hosts exist, the client may offer "Try people studying related material?". It starts a new search whose offered group is related.

# 5. Non-functional requirements

- **NFR-1** A real seat change shall be visible on the map within 5 seconds.
- **NFR-2** All timeouts shall be evaluated from stored timestamps. Transitions are applied:
  - on every read or write of the entity;
  - on sensor ingest, for host sessions and matches linked to that seat;
  - by one scheduler tick every `SCHEDULER_TICK_S`, for deadlines that depend only on time.

  The tick shall be safe to run on several backend instances at once.
- **NFR-3** Every AI call shall time out after `AI_TIMEOUT_S` and fall back; an AI failure shall never block a flow.
- **NFR-4** The client shall be usable at 375 px width on iOS Safari and Android Chrome, and installable as a PWA.
- **NFR-5** All times shall be stored in UTC and displayed in Central Time.
- **NFR-6** All timers and thresholds shall live in a single config.
- **NFR-7** Authentication is demo-grade (session cookie) and must be replaceable by university SSO.
- **NFR-8** The backend shall hold no state of record in process memory, so any number of instances can serve traffic. Derived caches may live in memory for at most `MAP_CACHE_S`.

# 6. Data model

| Table | Columns |
|---|---|
| buildings | id, name, is_simulated, busyness, lat, lng |
| tables | id, building_id, floor, label, x, y |
| seats | id, table_id, node_id, position, is_simulated |
| nodes | id, last_seen |
| seat_readings | time, seat_id, online, object_present, human_present (time-series, change-only) |
| seat_state | seat_id, state, candidate_state, candidate_since, state_since, away_since, last_object, last_human, last_seen, blink_until |
| users | id, first_name, major (nullable, D43), is_demo |
| host_sessions | id, user_id, seat_id, topic_raw, course_code, subject, keywords, label, about_me, open, muted, started_at, expires_at, ended_at, end_reason, confirm_notified_at |
| searches | id, seeker_id, topic_raw, course_code, subject, keywords, label, offered_group, status, tried_session_ids, created_at, joined_at |
| requests | id, search_id, seeker_id, host_session_id, status, created_at, expires_at |
| matches | id, request_id, seeker_id, host_session_id, icebreaker, card_key, assigned_seat_id, status, created_at, expires_at, arrived_at |
| blocks | user_id, blocked_user_id |
| reports | id, reporter_id, reported_id, reason, created_at |
| topic_cache | text_key, course_code, subject, keywords, label |
| push_subscriptions | id, user_id, endpoint, p256dh, auth, created_at |
| notification_outbox | id, user_id, kind, payload, created_at, sent_at, attempts |

**Status values:**
- searches: active, matched, exhausted, cancelled.
- requests: pending, accepted, declined, expired, skipped, cancelled.
- matches: active, completed, cancelled, expired.
- host_sessions.end_reason: toggled_off, no_person, unconfirmed.
- searches.offered_group: same_course, related.
- notification_outbox.kind: request_received, request_accepted, match_cancelled, match_expired, search_exhausted, confirm_needed, session_ended.

**seat_readings storage:**
- A row is written only when a seat's (`object_present`, `human_present`) pair differs from its previous stored row.
- When readings resume after a gap longer than `OFFLINE_S`, one marker row (`online = false`, null sensor values) is written first, at `last_seen + OFFLINE_S`.
- Raw rows older than `READINGS_RETENTION_DAYS` are dropped; hourly rollups are kept.

**Topic fields:** `host_sessions` topic fields are null until the host enters a topic (FR-24). `label` is the normalized display label (FR-19).

**Timestamps that drive transitions:** `searches.joined_at` marks when Join started the cascade (a search before Join is only a preview). `host_sessions.confirm_notified_at` records that the FR-27 prompt was sent for the current `expires_at`, so it is sent once.

# 7. API

JSON over HTTPS. Errors: `{"error": "<code>", "message": "<sentence>"}` with a 4xx status.

| Method and path | Auth | Request | Response |
|---|---|---|---|
| GET /api/health | None | | `{ok, db}`; `db` is false when the database is unreachable |
| POST /api/readings | Header `X-Node-Key` | `{node_id, readings: [{seat_id, object_present, human_present}]}` | `{leds: {<seat_id>: green or red or yellow or blue_blink or off}}`; unknown seat ids are skipped |
| GET /api/buildings | None | | `[{id, name, is_simulated, open, likely_opening, occupied, offline, total}]`; supports `ETag` / `If-None-Match` |
| GET /api/buildings/:id | None | | See shape below; supports `ETag` / `If-None-Match` |
| GET /api/recommend?building_id=&floor=&table_id= | None | `floor`, `table_id` optional | `{seat_id, table_id, floor, kind, level}` with kind `open` or `likely_opening` and level `table`, `floor` or `building`; or `{full: true, nearest_building_id}` |
| GET /api/buildings/:id/history | None | | `[{hour, open_avg}]` |
| GET /api/seats/:id | None | | `{id, building_id, floor, table_id, table_label, position, state}` (D53) |
| GET /api/demo-users | None | | `[{id, first_name, major}]` |
| POST /api/login | None | `{user_id}` | `{id, first_name, major}`; sets the session cookie |
| POST /api/logout | Login | | `{ok}`; clears the cookie |
| GET /api/me | None | | `{user: {id, first_name, major} or null, host: {session_id, seat_id, label, muted, status, hidden_reason} or null, search_id or null, match_id or null}`. `status` is `findable` or `hidden`; `hidden_reason` is `needs_topic`, `away`, `muted`, `table_full`, `in_match` or `confirm_pending` |
| POST /api/search | Login | `{topic_raw, group?}`; `group: "related"` only for FR-54 | `{search_id, label, course_code, subject, offered_group, has_real_hosts, same_course: [{building_id, floor, count}], related: [...]}` |
| POST /api/search/:id/join | Login | | Same as `GET /api/search/:id` |
| GET /api/search/:id | Login | | `{status, seconds_left, match_id, asking, request_id, joined, label, offered_group}`; `asking` is `{first_name, major}` of the host holding the pending request (`request_id`), or null (D43). `joined` is false while the search is a preview (D53) |
| POST /api/search/:id/cancel | Login | | `{status}` |
| POST /api/host/link | Login | `{seat_id}` | `{session_id}` |
| POST /api/host/topic | Login | `{topic_raw, about_me}` | `{label, course_code, subject}` |
| POST /api/host/toggle | Login | `{open}` | `{open}`; `open: false` ends the session |
| POST /api/host/mute | Login | `{muted}` | `{muted}` |
| POST /api/host/confirm | Login | | `{expires_at}` |
| GET /api/host/inbox | Login | | `[{request_id, seeker_first_name, seeker_major, course_label, table_label, seconds_left}]` (D43) |
| POST /api/requests/:id/accept | Login | | `{match_id}` |
| POST /api/requests/:id/decline | Login | `{mute?}` | `{status}`; `mute: true` also mutes (FR-28) |
| GET /api/matches/:id | Login | | `{status, role, other_first_name, other_major, building, building_id, floor, table_id, table_label, assigned_seat_id, alt_seat_id, icebreaker, card_url}` |
| POST /api/matches/:id/arrived | Login | | `{status}` |
| POST /api/matches/:id/cancel | Login | | `{status}` |
| POST /api/block | Login | Exactly one of `{user_id}`, `{request_id}`, `{match_id}`; a request or match names its other side (D53) | `{ok}` |
| POST /api/report | Login | The same, plus `reason` | `{ok}` |
| GET /api/push/vapid-public-key | None | | `{key}` |
| POST /api/push/subscribe | Login | `{endpoint, keys: {p256dh, auth}}` | `{ok}` |
| DELETE /api/push/subscribe | Login | `{endpoint}` | `{ok}` |

**`GET /api/buildings/:id` shape.** `x` and `y` are percentages of the floor canvas (0–100):

```json
{
  "id": "pcl", "name": "PCL Library", "is_simulated": false,
  "floors": [
    { "floor": 2,
      "tables": [
        { "id": "pcl-2-t1", "label": "Table 01", "x": 30, "y": 22,
          "seats": [ { "id": "t1-s1", "position": 1, "state": "open" } ] } ] } ]
}
```

**Error codes:**

| Status | Codes |
|---|---|
| 401 | `not_logged_in`, `invalid_node_key` |
| 403 | `not_your_search`, `not_your_request`, `not_in_match` |
| 404 | `unknown_user`, `building_not_found`, `table_not_found`, `seat_not_found`, `search_not_found`, `request_not_found`, `match_not_found` |
| 409 | `seat_not_occupied`, `seat_taken`, `not_linked`, `already_hosting`, `already_searching`, `no_real_hosts`, `request_not_pending`, `search_not_active`, `match_not_active`, `confirm_not_due` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 503 | `database_unavailable` (with `Retry-After`); the client keeps polling and shows an offline state |

# 8. Configuration

| Key | Default | Meaning |
|---|---|---|
| GHOST_S | 30 | Away time before ghosted (production: 1800) |
| DEBOUNCE_S | 5 | Time a new state must hold |
| OFFLINE_S | 30 | No readings before offline |
| HUMAN_FRESH_S | 10 | A person counts as present if seen this recently (FR-22, FR-24) |
| REQUEST_TIMEOUT_S | 300 | Host response window (D42) |
| MAX_HOSTS_PER_SEARCH | 5 | Request cascade limit |
| HOST_END_S | 600 | No person before host session ends |
| HOST_LEAVE_CANCEL_S | 120 | No person before match cancels |
| MATCH_TIMEOUT_S | 1200 | Seeker arrival window |
| BLINK_S | 60 | Blue blink duration |
| SESSION_MAX_S | 10800 | Host session confirmation interval |
| CONFIRM_GRACE_S | 120 | Time to answer the confirmation prompt |
| POLL_WEB_S | 3 | Client polling interval |
| AI_TIMEOUT_S | 4 | AI call timeout |
| MAX_REQUESTS_PER_HOUR | 10 | Per seeker |
| SIM_SLOT_S | 60 | Simulated-state time slot |
| SCHEDULER_TICK_S | 2 | Scheduler tick interval |
| MAP_CACHE_S | 1 | Map snapshot lifetime |
| HISTORY_WINDOW_H | 24 | History chart window (Q12) |
| READINGS_RETENTION_DAYS | 30 | Raw reading retention (Q12) |
| PUSH_MAX_ATTEMPTS | 5 | Delivery attempts per notification before giving up |

**Environment** (secrets and deployment, never committed):

| Key | Required | Meaning |
|---|---|---|
| DATABASE_URL | Yes | Primary database |
| DATABASE_READ_URL | No | Read replica for map, history and recommendations |
| SECRET_KEY | Yes | Session cookie signing |
| NODE_KEY | Yes | Shared key the bridge sends as `X-Node-Key` |
| MUSE_API_KEY | No | AI provider key; without it, fallbacks are used |
| MUSE_BASE_URL | No | AI provider base URL (default `https://api.meta.ai/v1`, D38) |
| MUSE_MODEL | No | AI model id (default `muse-spark-1.3`, D38) |
| VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT | Yes | Web push |
| FRONTEND_DIST | No | Built frontend folder to serve from the same origin (D5) |
| COOKIE_SECURE | No | `true` in production (HTTPS-only session cookie) |
| WORKER_ENABLED | No | Run the scheduler tick and push sender in this instance (default `true`) |
| DB_POOL_SIZE | No | Connections per pool per process (default 5). Processes × instances × pools × this must stay under the database's `max_connections` |
| DB_TIMEOUT_S | No | Bound on each database wait: a pooled connection, connecting, each round trip (default 5, D41) |
| LOG_FORMAT | No | `text` (default) or `json`: one JSON object per line with the request id (D60). The image sets `json` |
| METRICS_TOKEN | No | Bearer token for `GET /metrics` (at least 16 characters). Unset, `/metrics` is a 404 (D60) |
| PROMETHEUS_MULTIPROC_DIR | No | Directory the uvicorn processes share metric samples through, so one scrape covers all of them. The image sets it |

# 9. AI integration

| Function | Input | Output | Fallback |
|---|---|---|---|
| normalizeTopic | Free text | `{course_code or null, subject, keywords}` | Course-code regex plus keyword-to-subject map |
| rankHosts | Seeker topic, up to 10 host topics and about-me texts | Score 0–100 per host | Keyword overlap |
| icebreaker | Both topics, shared course | One sentence, max 140 characters | Template: "You're both studying {label}. Start by comparing where you're stuck." |

- Model provider: Meta Muse Spark. Any provider must be swappable behind the adapter.
- Prompts request JSON only and contain no personal data beyond topic, about-me text and major. Names never reach the model (D43).
- normalizeTopic results are cached in `topic_cache`.
- Card images: a fixed set of pre-generated Muse Image pictures, one per subject plus a generic one, with no people or text. The client overlays names, course and icebreaker as text.

# 10. Hardware requirements

## 10.1 Per-seat inputs and outputs

| Item | Requirement |
|---|---|
| Object sensor | Digital signal: true when belongings or a person press the seat (micro switch or equivalent) |
| Human sensor | Signal that is true only when a person is present; a loaded backpack must read false |
| Seat LED | Shows green, red, yellow, blue (blinking) and off |
| Seats per node | One node supports N seats in a fixed order |

## 10.2 Firmware

- **HW-1** The node shall sample all seat sensors every 500 ms.
- **HW-2** A human-sensor change shall require 3 consecutive matching samples.
- **HW-3** The node shall send one readings message every 2 seconds.
- **HW-4** The node shall apply LED commands on receipt; blue blink toggles every 300 ms.
- **HW-5** If no LED command arrives for 10 seconds, the node shall switch to local mode: red if any sensor is true, green otherwise.
- **HW-6** If the human sensor needs a baseline, it shall be calibrated only while the seat's object sensor reads false.

## 10.3 Serial protocol (115200 baud, newline-terminated)

| Direction | Format | Example |
|---|---|---|
| Node to bridge | `R,<o1><h1>,<o2><h2>,...` (1 = true), seats in fixed order | `R,10,00` |
| Bridge to node | `L,<c1>,<c2>,...` with G, R, Y, B (blue blink), O (off) | `L,Y,G` |
| Node debug (optional) | `D,<raw1>,<raw2>,...` | ignored by the bridge |

## 10.4 Bridge

- **HW-7** The bridge shall map seat positions to seat ids from config (`SERIAL_PORT`, `SYNAPSE_URL`, `NODE_ID`, `NODE_KEY`, `SEAT_IDS`; D62).
- **HW-8** The bridge shall convert each `R` message to `POST /api/readings`, sending the `X-Node-Key` header, and write the response as an `L` message (green → G, red → R, yellow → Y, blue_blink → B, off → O).
- **HW-9** If the backend does not respond, the bridge shall send nothing, so the node's local mode takes over.
- **HW-10** The bridge shall log every request and response with a timestamp.

# 11. Out of scope

Seat-release nudges · card tap-to-claim · public ghost timers · login to browse · chat, profile pages, friend lists · seat reservations · gamification · native mobile app (the installable PWA is in scope, NFR-4) · staff dashboard · natural-language seat search · live location sharing · NFC tags · Muse agent connector · voice input · live image generation at match time.
