-- Ghost Seats schema (REQUIREMENTS §6). Idempotent: safe to re-run on an empty or existing database.
-- All times are timestamptz in UTC (NFR-5).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Timescale Toolkit powers exact time-in-state history (D31). Optional: when it is missing
-- the backend computes the same result with a window query (ARCHITECTURE §10).
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'timescaledb_toolkit unavailable: %', SQLERRM;
END $$;

-- Places ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS buildings (
  id            text PRIMARY KEY,
  name          text NOT NULL,
  is_simulated  boolean NOT NULL DEFAULT false,
  busyness      smallint NOT NULL DEFAULT 50 CHECK (busyness BETWEEN 0 AND 100),
  lat           double precision CHECK (lat BETWEEN -90 AND 90),
  lng           double precision CHECK (lng BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS tables (
  id           text PRIMARY KEY,
  building_id  text NOT NULL REFERENCES buildings(id),
  floor        smallint NOT NULL,
  label        text NOT NULL,
  x            real NOT NULL CHECK (x BETWEEN 0 AND 100),
  y            real NOT NULL CHECK (y BETWEEN 0 AND 100)
);
CREATE INDEX IF NOT EXISTS tables_building ON tables (building_id, floor);

CREATE TABLE IF NOT EXISTS nodes (
  id         text PRIMARY KEY,
  last_seen  timestamptz
);

CREATE TABLE IF NOT EXISTS seats (
  id            text PRIMARY KEY,
  table_id      text NOT NULL REFERENCES tables(id),
  node_id       text REFERENCES nodes(id),
  position      smallint NOT NULL CHECK (position > 0),
  is_simulated  boolean NOT NULL DEFAULT false,
  UNIQUE (table_id, position),
  CHECK (is_simulated OR node_id IS NOT NULL)
);

-- Sensing --------------------------------------------------------------------

-- Change-only: a row only when a seat's (object, human) pair changes, plus an
-- online=false marker at the start of each offline gap (D31).
CREATE TABLE IF NOT EXISTS seat_readings (
  time            timestamptz NOT NULL,
  seat_id         text NOT NULL REFERENCES seats(id),
  online          boolean NOT NULL DEFAULT true,
  object_present  boolean,
  human_present   boolean,
  CHECK (online = (object_present IS NOT NULL AND human_present IS NOT NULL))
);
SELECT create_hypertable('seat_readings', 'time', if_not_exists => true);
CREATE INDEX IF NOT EXISTS seat_readings_seat_time ON seat_readings (seat_id, time DESC);

CREATE TABLE IF NOT EXISTS seat_state (
  seat_id          text PRIMARY KEY REFERENCES seats(id),
  state            text NOT NULL CHECK (state IN ('open', 'occupied', 'away')),
  candidate_state  text NOT NULL CHECK (candidate_state IN ('open', 'occupied', 'away')),
  candidate_since  timestamptz,
  state_since      timestamptz,
  away_since       timestamptz,
  last_object      timestamptz,
  last_human       timestamptz,
  last_seen        timestamptz,
  blink_until      timestamptz,
  CHECK (state <> 'away' OR away_since IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS seat_state_last_human ON seat_state (last_human);

-- People ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
  id          text PRIMARY KEY,
  first_name  text NOT NULL,
  is_demo     boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS topic_cache (
  text_key     text PRIMARY KEY,
  course_code  text,
  subject      text NOT NULL,
  keywords     text[] NOT NULL DEFAULT '{}',
  label        text NOT NULL
);

CREATE TABLE IF NOT EXISTS host_sessions (
  id                   uuid PRIMARY KEY,
  user_id              text NOT NULL REFERENCES users(id),
  seat_id              text NOT NULL REFERENCES seats(id),
  topic_raw            text,
  course_code          text,
  subject              text,
  keywords             text[] NOT NULL DEFAULT '{}',
  label                text,
  about_me             text CHECK (length(about_me) <= 280),
  open                 boolean NOT NULL DEFAULT true,
  muted                boolean NOT NULL DEFAULT false,
  started_at           timestamptz NOT NULL,
  expires_at           timestamptz NOT NULL,
  ended_at             timestamptz,
  end_reason           text CHECK (end_reason IN ('toggled_off', 'no_person', 'unconfirmed')),
  confirm_notified_at  timestamptz,
  CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);
-- One live session per user and per seat.
CREATE UNIQUE INDEX IF NOT EXISTS host_sessions_live_user ON host_sessions (user_id) WHERE ended_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS host_sessions_live_seat ON host_sessions (seat_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS host_sessions_live_expiry ON host_sessions (expires_at) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS searches (
  id                 uuid PRIMARY KEY,
  seeker_id          text NOT NULL REFERENCES users(id),
  topic_raw          text NOT NULL,
  course_code        text,
  subject            text NOT NULL,
  keywords           text[] NOT NULL DEFAULT '{}',
  label              text NOT NULL,
  offered_group      text NOT NULL CHECK (offered_group IN ('same_course', 'related')),
  status             text NOT NULL CHECK (status IN ('active', 'matched', 'exhausted', 'cancelled')),
  tried_session_ids  uuid[] NOT NULL DEFAULT '{}',
  created_at         timestamptz NOT NULL,
  joined_at          timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS searches_one_active ON searches (seeker_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS requests (
  id               uuid PRIMARY KEY,
  search_id        uuid NOT NULL REFERENCES searches(id),
  seeker_id        text NOT NULL REFERENCES users(id),
  host_session_id  uuid NOT NULL REFERENCES host_sessions(id),
  status           text NOT NULL CHECK (status IN ('pending', 'accepted', 'declined', 'expired', 'skipped', 'cancelled')),
  created_at       timestamptz NOT NULL,
  expires_at       timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS requests_one_pending ON requests (search_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS requests_pending_session ON requests (host_session_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS requests_pending_expiry ON requests (expires_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS requests_seeker_time ON requests (seeker_id, created_at);

CREATE TABLE IF NOT EXISTS matches (
  id                uuid PRIMARY KEY,
  request_id        uuid NOT NULL UNIQUE REFERENCES requests(id),
  seeker_id         text NOT NULL REFERENCES users(id),
  host_session_id   uuid NOT NULL REFERENCES host_sessions(id),
  icebreaker        text NOT NULL CHECK (length(icebreaker) <= 140),
  card_key          text NOT NULL,
  assigned_seat_id  text REFERENCES seats(id),
  status            text NOT NULL CHECK (status IN ('active', 'completed', 'cancelled', 'expired')),
  created_at        timestamptz NOT NULL,
  expires_at        timestamptz NOT NULL,
  arrived_at        timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS matches_one_active_host ON matches (host_session_id) WHERE status = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS matches_one_active_seeker ON matches (seeker_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS matches_active_expiry ON matches (expires_at) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS blocks (
  user_id          text NOT NULL REFERENCES users(id),
  blocked_user_id  text NOT NULL REFERENCES users(id),
  PRIMARY KEY (user_id, blocked_user_id),
  CHECK (user_id <> blocked_user_id)
);
CREATE INDEX IF NOT EXISTS blocks_reverse ON blocks (blocked_user_id);

CREATE TABLE IF NOT EXISTS reports (
  id           bigserial PRIMARY KEY,
  reporter_id  text NOT NULL REFERENCES users(id),
  reported_id  text NOT NULL REFERENCES users(id),
  reason       text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
  created_at   timestamptz NOT NULL
);

-- Push -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS push_subscriptions (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users(id),
  endpoint    text NOT NULL UNIQUE,
  p256dh      text NOT NULL,
  auth        text NOT NULL,
  created_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS push_subscriptions_user ON push_subscriptions (user_id);

CREATE TABLE IF NOT EXISTS notification_outbox (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users(id),
  kind        text NOT NULL CHECK (kind IN ('request_received', 'request_accepted', 'match_cancelled',
                                            'match_expired', 'search_exhausted', 'confirm_needed',
                                            'session_ended')),
  payload     jsonb NOT NULL,
  created_at  timestamptz NOT NULL,
  sent_at     timestamptz,
  attempts    integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS notification_outbox_unsent ON notification_outbox (id) WHERE sent_at IS NULL;

-- History (FR-49, D31, D33) ------------------------------------------------------

-- Hourly average open seats for one building over [p_since, p_until), from change-only
-- readings. The API and the rollup job both call this, so they cannot disagree.
CREATE OR REPLACE FUNCTION open_hourly(
  p_building text, p_since timestamptz, p_until timestamptz, p_offline interval
) RETURNS TABLE (hour timestamptz, open_avg double precision)
LANGUAGE sql STABLE AS $fn$

WITH seats_b AS (
  SELECT s.id, ss.last_seen
  FROM seats s
  JOIN tables t ON t.id = s.table_id
  LEFT JOIN seat_state ss ON ss.seat_id = s.id
  WHERE t.building_id = p_building
),
rows_in AS (
  -- the row in force at the start of the window, per seat ...
  SELECT x.seat_id, x.time, x.online, x.object_present, x.human_present
  FROM seats_b sb
  CROSS JOIN LATERAL (
    SELECT r.seat_id, r.time, r.online, r.object_present, r.human_present
    FROM seat_readings r
    WHERE r.seat_id = sb.id AND r.time <= p_since
    ORDER BY r.time DESC
    LIMIT 1
  ) x
  UNION ALL
  -- ... and every change inside the window
  SELECT r.seat_id, r.time, r.online, r.object_present, r.human_present
  FROM seat_readings r
  WHERE r.seat_id IN (SELECT id FROM seats_b)
    AND r.time > p_since AND r.time < p_until
),
all_intervals AS (
  -- lead() must see every row: a WHERE here would run before the window function and let an
  -- open interval run past the change that ended it.
  SELECT
    i.online AND NOT i.object_present AND NOT i.human_present AS is_open,
    greatest(i.time, p_since) AS start_at,
    least(
      coalesce(lead(i.time) OVER (PARTITION BY i.seat_id ORDER BY i.time), p_until),
      coalesce(sb.last_seen + p_offline, p_until),
      p_until
    ) AS stop_at
  FROM rows_in i
  JOIN seats_b sb ON sb.id = i.seat_id
),
intervals AS (
  SELECT start_at, stop_at FROM all_intervals WHERE is_open
),
hours AS (
  SELECT h AS hour_at, least(h + interval '1 hour', p_until) AS hour_end
  FROM generate_series(p_since, p_until - interval '1 microsecond',
                       interval '1 hour') AS h
)
-- FILTER: Postgres LEAST/GREATEST skip NULLs, so an hour with no interval (NULLs from the
-- LEFT JOIN) would otherwise count as fully open.
SELECT
  hours.hour_at AS hour,
  (coalesce(sum(extract(epoch FROM least(iv.stop_at, hours.hour_end)
                                   - greatest(iv.start_at, hours.hour_at)))
              FILTER (WHERE iv.start_at IS NOT NULL), 0)
     / extract(epoch FROM hours.hour_end - hours.hour_at))::double precision AS open_avg
FROM hours
LEFT JOIN intervals iv
  ON iv.stop_at > hours.hour_at AND iv.start_at < hours.hour_end AND iv.stop_at > iv.start_at
GROUP BY hours.hour_at, hours.hour_end
ORDER BY hours.hour_at
$fn$;

-- Completed hours, kept after raw readings age out (Q12: raw 30 days, hourly kept).
CREATE TABLE IF NOT EXISTS building_open_hourly (
  building_id  text NOT NULL REFERENCES buildings(id),
  hour         timestamptz NOT NULL,
  open_avg     double precision NOT NULL,
  PRIMARY KEY (building_id, hour)
);

-- Timescale job: roll up every completed hour not yet stored. Idempotent.
CREATE OR REPLACE PROCEDURE rollup_open_hourly(job_id int, config jsonb)
LANGUAGE plpgsql AS $proc$
DECLARE
  b record;
  offline interval := make_interval(secs => coalesce((config->>'offline_s')::int, 30));
  horizon timestamptz := date_trunc('hour', now());
  since timestamptz;
BEGIN
  FOR b IN SELECT id FROM buildings LOOP
    SELECT coalesce(max(hour) + interval '1 hour', horizon - interval '24 hours')
      INTO since FROM building_open_hourly WHERE building_id = b.id;
    IF since < horizon THEN
      INSERT INTO building_open_hourly (building_id, hour, open_avg)
      SELECT b.id, h.hour, h.open_avg FROM open_hourly(b.id, since, horizon, offline) h
      ON CONFLICT DO NOTHING;
    END IF;
  END LOOP;
END
$proc$;
