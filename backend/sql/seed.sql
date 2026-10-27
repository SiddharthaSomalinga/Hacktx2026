-- Synapse seed data. Idempotent (ON CONFLICT DO NOTHING).
--
-- PLACEHOLDER (Q2/H0): the physical demo table below uses the example ids from the original
-- interface contract: node 'table-1', seats 't1-s1', 't1-s2'. Replace them with the hardware
-- pair's node id and seat ids, in seat order, when H0 lands.

INSERT INTO buildings (id, name, is_simulated, busyness, lat, lng) VALUES
  ('pcl', 'PCL Library',    false, 45, 30.28270, -97.73810),
  ('wel', 'WEL Library',    true,  75, 30.28660, -97.73760),
  ('gdc', 'GDC Study Hall', true,  30, 30.28620, -97.73660)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tables (id, building_id, floor, label, x, y) VALUES
  ('pcl-2-t1', 'pcl', 2, 'Table 01', 25, 30),
  ('pcl-2-t2', 'pcl', 2, 'Table 02', 60, 30),
  ('pcl-2-t3', 'pcl', 2, 'Table 03', 25, 70),
  ('pcl-2-t4', 'pcl', 2, 'Table 04', 60, 70),
  ('pcl-3-t1', 'pcl', 3, 'Table 01', 30, 35),
  ('pcl-3-t2', 'pcl', 3, 'Table 02', 70, 35),
  ('pcl-3-t3', 'pcl', 3, 'Table 03', 50, 75),
  ('wel-1-t1', 'wel', 1, 'Table 01', 20, 30),
  ('wel-1-t2', 'wel', 1, 'Table 02', 55, 30),
  ('wel-1-t3', 'wel', 1, 'Table 03', 20, 70),
  ('wel-1-t4', 'wel', 1, 'Table 04', 55, 70),
  ('wel-2-t1', 'wel', 2, 'Table 01', 30, 40),
  ('wel-2-t2', 'wel', 2, 'Table 02', 70, 40),
  ('gdc-3-t1', 'gdc', 3, 'Table 01', 20, 35),
  ('gdc-3-t2', 'gdc', 3, 'Table 02', 50, 35),
  ('gdc-3-t3', 'gdc', 3, 'Table 03', 80, 35),
  ('gdc-3-t4', 'gdc', 3, 'Table 04', 50, 75)
ON CONFLICT (id) DO NOTHING;

-- The physical demo table (placeholder ids, see top of file).
INSERT INTO nodes (id) VALUES ('table-1') ON CONFLICT (id) DO NOTHING;
INSERT INTO seats (id, table_id, node_id, position, is_simulated) VALUES
  ('t1-s1', 'pcl-2-t1', 'table-1', 1, false),
  ('t1-s2', 'pcl-2-t1', 'table-1', 2, false)
ON CONFLICT (id) DO NOTHING;
INSERT INTO seat_state (seat_id, state, candidate_state)
SELECT id, 'open', 'open' FROM seats WHERE NOT is_simulated
ON CONFLICT (seat_id) DO NOTHING;

-- Every other table: six simulated seats each (FR-47).
INSERT INTO seats (id, table_id, node_id, position, is_simulated)
SELECT t.id || '-s' || p, t.id, NULL, p, true
FROM tables t CROSS JOIN generate_series(1, 6) AS p
WHERE t.id <> 'pcl-2-t1'
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, first_name, major, is_demo) VALUES
  ('u-alex',   'Alex',   'Biochemistry',     true),
  ('u-priya',  'Priya',  'Chemistry',        true),
  ('u-jordan', 'Jordan', 'Computer Science', true),
  ('u-mateo',  'Mateo',  'Neuroscience',     true),
  ('u-sam',    'Sam',    'Mathematics',      true),
  ('u-wei',    'Wei',    'Economics',        true),
  ('sim-taylor', 'Taylor', 'Chemistry',        false),
  ('sim-riley',  'Riley',  'Computer Science', false),
  ('sim-avery',  'Avery',  'Mathematics',      false),
  ('sim-morgan', 'Morgan', 'Biology',          false)
ON CONFLICT (id) DO UPDATE SET major = EXCLUDED.major;  -- D43: re-seeding adds majors

-- Seeded simulated hosts (FR-48): always findable, never sent requests (FR-31, D22).
INSERT INTO host_sessions (id, user_id, seat_id, topic_raw, course_code, subject, keywords, label,
                           open, muted, started_at, expires_at) VALUES
  ('00000000-0000-4000-8000-000000000001', 'sim-taylor', 'wel-1-t2-s3', 'orgo exam review',
   'CH 320M', 'chemistry', '{orgo,exam,review}', 'CH 320M · Organic Chemistry I',
   true, false, now(), '2100-01-01T00:00:00Z'),
  ('00000000-0000-4000-8000-000000000002', 'sim-riley', 'gdc-3-t1-s2', 'trees and graphs',
   'C S 314', 'computer science', '{trees,graphs}', 'C S 314 · Data Structures',
   true, false, now(), '2100-01-01T00:00:00Z'),
  ('00000000-0000-4000-8000-000000000003', 'sim-avery', 'wel-2-t1-s4', 'calc 1 derivatives',
   'M 408C', 'mathematics', '{calc,derivatives}', 'M 408C · Differential and Integral Calculus',
   true, false, now(), '2100-01-01T00:00:00Z'),
  ('00000000-0000-4000-8000-000000000004', 'sim-morgan', 'pcl-3-t2-s1', 'gen chem stoichiometry',
   'CH 301', 'chemistry', '{gen,chem,stoichiometry}', 'CH 301 · Principles of Chemistry I',
   true, false, now(), '2100-01-01T00:00:00Z')
ON CONFLICT (id) DO NOTHING;
