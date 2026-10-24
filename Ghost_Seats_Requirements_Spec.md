---
title: "Ghost Seats: Requirements Specification"
subtitle: "v1.0"
---

# 1. Overview

Ghost Seats is a web app backed by seat sensors. It shows which library seats are open, occupied, or held by belongings with no one present ("ghosted"), and lets students studying the same course find each other and sit together.

**In scope:** seat sensing and state, live seat map, seat recommendations, topic-based study matching, host mode, safety controls, simulated buildings.

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
| Backend API | Seat-state engine, recommendations, matching, AI calls, safety controls |
| Database | Persistent state; seat readings stored as time-series data |
| Web client | Phone-first UI for visitors, seekers and hosts |
| AI adapter | Topic normalization, host ranking, icebreakers; every call has a non-AI fallback |

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
- **FR-11** The backend shall recommend one seat per building: an open seat if any exist; otherwise a likely-opening seat, labeled as such; if the building is full, the nearest building with open seats.
- **FR-12** The recommended seat shall be highlighted with a style distinct from all seat-state colors.
- **FR-13** Simulated buildings shall be visibly labeled as simulated.

## 4.3 Accounts

- **FR-14** Browsing the map and recommendations shall not require login.
- **FR-15** Searching, hosting, matching, blocking and reporting shall require login.
- **FR-16** Login shall be a demo-user picker that sets a session cookie. No passwords.

## 4.4 Topic input

- **FR-17** On opening the map, a logged-in or anonymous user shall be prompted "What are you studying today?" with an option to skip.
- **FR-18** Submitting a topic shall require login, then normalize free text to `{course_code, subject, keywords}` through the AI adapter.
- **FR-19** The client shall display the normalized label (e.g. "CH 320M · Organic Chemistry I").

## 4.5 Host mode

- **FR-20** A user shall be able to turn on "Open to study partners" for one session. It is off by default.
- **FR-21** A host shall link to a seat by selecting it on the building view or by opening that seat's URL (`/seat/{seat_id}`).
- **FR-22** Linking shall succeed only if the seat read `human_present = true` within the last 10 seconds.
- **FR-23** A host shall enter a topic and an optional short "about me" text.
- **FR-24** A host shall be findable only while: the session is open and not muted; the session has not ended; the linked seat reads human-present; the host has no active match; and the host's table has at least one `open` seat.
- **FR-25** While the linked seat reads human-absent, the host shall be hidden from search and any pending request to the host shall be marked skipped.
- **FR-26** A host session shall end when the linked seat has no human for `HOST_END_S`, or when the host turns it off.
- **FR-27** After `SESSION_MAX_S`, the host shall be asked to confirm they are still open to partners; no confirmation ends the session.
- **FR-28** A host shall be able to mute new requests.

## 4.6 Search and requests

- **FR-29** A search shall return findable hosts grouped as same course first, then same subject, aggregated by building and floor with counts. No names.
- **FR-30** Within each group, hosts shall be ranked by the AI relatability score, falling back to keyword overlap.
- **FR-31** "Join" shall send a request to the top-ranked host only.
- **FR-32** A request shall expire after `REQUEST_TIMEOUT_S`. On decline, expiry or skip, the next host shall receive it.
- **FR-33** After `MAX_HOSTS_PER_SEARCH` hosts or no remaining hosts, the search shall end as exhausted and the seeker shall see "No one's free right now" with seat recommendations.
- **FR-34** A seeker shall have at most one active search and at most `MAX_REQUESTS_PER_HOUR` requests per hour.
- **FR-35** A seeker shall be able to cancel a search, withdrawing any pending request.
- **FR-36** A host's request card shall show only the course and the host's table. Declines shall be silent to the seeker.

## 4.7 Match lifecycle

- **FR-37** On accept, the backend shall create a match, generate an icebreaker, select a card image by subject, assign an open seat at the host's table, and start a `BLINK_S` blue blink on the host's seat.
- **FR-38** The match view shall show the other person's first name, building, floor, table, assigned seat, icebreaker and card image.
- **FR-39** If the assigned seat becomes occupied before arrival, the match view shall show the nearest open seat on the same floor.
- **FR-40** The seeker shall be able to mark "I'm here", which restarts the blue blink and completes the match.
- **FR-41** A match shall be cancelled if the host's seat has no human for `HOST_LEAVE_CANCEL_S`, or if either side cancels.
- **FR-42** A match shall expire if the seeker has not marked "I'm here" within `MATCH_TIMEOUT_S`.

## 4.8 Safety and privacy

- **FR-43** Names shall be shown only after a request is accepted.
- **FR-44** Location shall be shared only as building, floor, table and seat after acceptance. No live location.
- **FR-45** Users shall be able to block and report from every request and match view. A report shall also block. Blocks apply in both directions.
- **FR-46** No images or audio shall be stored.

## 4.9 Simulation

- **FR-47** The system shall support simulated buildings whose seat states are computed on read from a hash of the seat id and the current time slot, with a per-building busyness level.
- **FR-48** The system shall support seeded simulated host sessions on simulated seats that are always findable.

## 4.10 Occupancy history (optional)

- **FR-49** The system shall provide hourly average open-seat counts per building for a history chart, from stored and seeded readings.

# 5. Non-functional requirements

- **NFR-1** A real seat change shall be visible on the map within 5 seconds.
- **NFR-2** The backend shall run no background jobs. All timeouts shall be evaluated from stored timestamps on read or write.
- **NFR-3** Every AI call shall time out after `AI_TIMEOUT_S` and fall back; an AI failure shall never block a flow.
- **NFR-4** The client shall be usable at 375 px width on iOS Safari and Android Chrome.
- **NFR-5** All times shall be stored in UTC and displayed in Central Time.
- **NFR-6** All timers and thresholds shall live in a single config.
- **NFR-7** Authentication is demo-grade (session cookie) and must be replaceable by university SSO.

# 6. Data model

| Table | Columns |
|---|---|
| buildings | id, name, is_simulated, busyness |
| tables | id, building_id, floor, label, x, y |
| seats | id, table_id, node_id, position, is_simulated |
| nodes | id, last_seen |
| seat_readings | time, seat_id, object_present, human_present (time-series) |
| seat_state | seat_id, state, candidate_state, candidate_since, state_since, away_since, last_object, last_human, last_seen, blink_until |
| users | id, first_name, is_demo |
| host_sessions | id, user_id, seat_id, topic_raw, course_code, subject, about_me, open, muted, started_at, expires_at, ended_at, end_reason |
| searches | id, seeker_id, topic_raw, course_code, subject, status, tried_session_ids, created_at |
| requests | id, search_id, seeker_id, host_session_id, status, created_at, expires_at |
| matches | id, request_id, seeker_id, host_session_id, icebreaker, card_key, assigned_seat_id, status, created_at, expires_at, arrived_at |
| blocks | user_id, blocked_user_id |
| reports | id, reporter_id, reported_id, reason, created_at |
| topic_cache | text_key, course_code, subject, keywords |

**Status values:** searches: active, matched, exhausted, cancelled. requests: pending, accepted, declined, expired, skipped, cancelled. matches: active, completed, cancelled, expired.

# 7. API

JSON over HTTPS. Errors: `{"error": "<code>", "message": "<sentence>"}` with a 4xx status.

| Method and path | Auth | Request | Response |
|---|---|---|---|
| POST /api/readings | Node id | `{node_id, readings: [{seat_id, object_present, human_present}]}` | `{leds: {<seat_id>: green or red or yellow or blue_blink or off}}` |
| GET /api/buildings | None | | `[{id, name, is_simulated, open, likely_opening, occupied, offline, total}]` |
| GET /api/buildings/:id | None | | Floors, tables (label, x, y), seats (id, public state) |
| GET /api/recommend?building_id= | None | | `{seat_id, table_id, floor, kind}` or `{full: true, nearest_building_id}` |
| GET /api/buildings/:id/history | None | | `[{hour, open_avg}]` |
| GET /api/demo-users | None | | `[{id, first_name}]` |
| POST /api/login | None | `{user_id}` | Sets session cookie |
| POST /api/search | Login | `{topic_raw}` | `{search_id, label, course_code, subject, same_course: [{building_id, floor, count}], related: [...]}` |
| POST /api/search/:id/join | Login | | `{status, seconds_left}` |
| GET /api/search/:id | Login | | `{status, seconds_left, match_id}` |
| POST /api/search/:id/cancel | Login | | `{status}` |
| POST /api/host/link | Login | `{seat_id}` | `{session_id}` or error `seat_not_occupied` |
| POST /api/host/topic | Login | `{topic_raw, about_me}` | `{label, course_code, subject}` |
| POST /api/host/toggle | Login | `{open}` | `{open}` |
| POST /api/host/mute | Login | `{muted}` | `{muted}` |
| GET /api/host/inbox | Login | | `[{request_id, course_label, table_label, seconds_left}]` |
| POST /api/requests/:id/accept | Login | | `{match_id}` |
| POST /api/requests/:id/decline | Login | | `{status}` |
| GET /api/matches/:id | Login | | `{status, other_first_name, building, floor, table_label, assigned_seat_id, alt_seat_id, icebreaker, card_url}` |
| POST /api/matches/:id/arrived | Login | | `{status}` |
| POST /api/matches/:id/cancel | Login | | `{status}` |
| POST /api/block | Login | `{user_id}` | `{ok}` |
| POST /api/report | Login | `{user_id, reason}` | `{ok}` |

# 8. Configuration

| Key | Default | Meaning |
|---|---|---|
| GHOST_S | 30 | Away time before ghosted (production: 1800) |
| DEBOUNCE_S | 5 | Time a new state must hold |
| OFFLINE_S | 30 | No readings before offline |
| REQUEST_TIMEOUT_S | 120 | Host response window |
| MAX_HOSTS_PER_SEARCH | 5 | Request cascade limit |
| HOST_END_S | 600 | Seat empty before host session ends |
| HOST_LEAVE_CANCEL_S | 120 | Host absent before match cancels |
| MATCH_TIMEOUT_S | 1200 | Seeker arrival window |
| BLINK_S | 60 | Blue blink duration |
| SESSION_MAX_S | 10800 | Host session confirmation interval |
| POLL_WEB_S | 3 | Client polling interval |
| AI_TIMEOUT_S | 4 | AI call timeout |
| MAX_REQUESTS_PER_HOUR | 10 | Per seeker |

# 9. AI integration

| Function | Input | Output | Fallback |
|---|---|---|---|
| normalizeTopic | Free text | `{course_code or null, subject, keywords}` | Course-code regex plus keyword-to-subject map |
| rankHosts | Seeker topic, up to 10 host topics and about-me texts | Score 0–100 per host | Keyword overlap |
| icebreaker | Both topics, shared course | One sentence, max 140 characters | Template: "You're both studying {label}. Start by comparing where you're stuck." |

- Model provider: Meta Muse Spark; any provider must be swappable behind the adapter.
- Prompts request JSON only and contain no personal data beyond topic and about-me text.
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

- **HW-7** The bridge shall map seat positions to seat ids from config (`SERIAL_PORT`, `BACKEND_URL`, `NODE_ID`, `SEAT_IDS`).
- **HW-8** The bridge shall convert each `R` message to `POST /api/readings` and write the response as an `L` message.
- **HW-9** If the backend does not respond, the bridge shall send nothing, so the node's local mode takes over.
- **HW-10** The bridge shall log every request and response with a timestamp.

# 11. Out of scope

Seat-release nudges · card tap-to-claim · public ghost timers · login to browse · chat, profile pages, friend lists · seat reservations · gamification · native mobile app · staff dashboard · natural-language seat search · live location sharing · NFC tags · Muse agent connector · voice input · live image generation at match time.
