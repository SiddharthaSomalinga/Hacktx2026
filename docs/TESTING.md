# Synapse v2 — features and how to test them

Covers the app on `main` (the v2 frontend, D44, in `frontend/`). Every check below
was run on a Mac with headless Chromium unless it says **(device)**: those need a real phone.

## Set up: Mac and phone at the same time

One device hosts, the other seeks. Both talk to one backend on the Mac.

1. **Network.** Put the Mac and the phone on the same network. Venue Wi-Fi often blocks
   device-to-device traffic, so use the phone's hotspot and join it from the Mac.
2. **Database** (from `backend/`): `make db-up db-create`, then
   `DATABASE_URL=postgresql://postgres:ghostseats@localhost:5433/ghostseats make db-init seed policies`.
3. **Build the app** (from `frontend/`): `npm ci && npm run build`.
4. **Serve it to the network** (from `backend/`):
   ```bash
   DATABASE_URL=postgresql://postgres:ghostseats@localhost:5433/ghostseats \
   FRONTEND_DIST="$PWD/../frontend/dist" \
   uv run uvicorn app.main:build --factory --host 0.0.0.0 --port 8000
   ```
   Allow incoming connections if macOS asks.
5. **Demo hosts (one device is enough).** Run `make seed-demo` once, and start the server with
   `DEMO_HOSTS=true` in front of the command in step 4. Every catalog course then has a
   simulated host who accepts a Join after about 5 seconds (D56).
6. **Sit someone down.** Hosting needs the seat sensor to see a person. Without the hardware,
   run the stand-in node in another terminal (from `backend/`):
   `uv run python -m scripts.fake_node --seats t1-s1,t1-s2`, then type `1 p` (person on seat 1)
   and leave seat 2 empty, so the table has an open seat for the partner.
7. **Open the app.**
   - Mac: `http://localhost:8000`
   - Phone: `http://<the Mac's IP>:8000`. Find the IP with `ipconfig getifaddr en0`.
8. **Pick roles.** Mac as Alex (host), phone as Priya (seeker), or the other way round.
   Each device keeps its own login.

**What plain http on the phone can't do.** Browsers only allow install, offline and push
notifications over HTTPS (or on `localhost`). Over the Mac's IP, the phone runs every flow but
not those three. To test them on the phone, serve the app over HTTPS: deploy it (D36) or run a
tunnel from the Mac (`cloudflared tunnel --url http://localhost:8000`) and open the `https://`
link it prints on both devices.

## Features and checks

### Campus map
| Feature | How to test | Expect |
|---|---|---|
| Real street map, self-hosted | Open `/` | UT streets in the app's colors; no requests leave the app's origin |
| Live building outlines (FR-8, D51) | Look at PCL, WEL, GDC | Outline and swatch green ≥ 30% open, yellow 10–29%, red < 10%, grey when every seat is offline |
| Counts and Simulated label (FR-13) | Read the markers and the list | Open count per building; WEL and GDC say SIM / SIMULATED |
| Draw-in on first open | Open in a new private window | Outlines trace in while data loads, then fill |
| Building list | Scroll the panel | Most open seats first, with a bar of open / likely / taken / no signal |

### Floor plans
| Feature | How to test | Expect |
|---|---|---|
| Plan per building and floor (FR-9) | Tap PCL | Opens the floor with the most open seats; URL `/b/pcl/2` |
| Seat state by shape and color (D54) | Look at the chairs | Open green outline · occupied blue fill · likely opening yellow dashed with a bag · no signal grey hatched |
| Floor switch | Tap floor 3 | Plan and counts change; Back doesn't step through floors |
| Table zoom | Tap a table | Zooms in; URL `/b/pcl/2/<table>`; chairs listed in the panel |
| Best seat (FR-11, FR-12) | Any floor | One chair with a burnt-orange ring and "Best seat"; the card says table, floor or building level |
| Building full → nearest building | Fill a building (simulated data changes every minute) | "PCL is full right now" with a button to the nearest building |
| Real seats from the sensor | Run the stand-in node; type `1 b` | Seat t1-s1 turns occupied, then likely opening after `GHOST_S` with nobody sensed |
| 24-hour history (FR-49) | "Open seats over the last 24 hours" | Real bars per hour in Central Time; "No open seats recorded" when there is no data; table view toggle |

### Finding a study partner (seeker)
| Feature | How to test | Expect |
|---|---|---|
| "What are you studying today?" (FR-17) | Open `/` | Prompt in the panel; Skip collapses it to a pill until the next visit |
| Topic kept through login (FR-18) | Logged out, type "orgo exam", submit | Login list, then straight to results with no retyping |
| Normalized topic (FR-19) | Same | "CH 320M · Organic Chemistry I" |
| Results without names (FR-29) | Same | Counts by building and floor, also shown as badges on the map |
| Join only with a real host | Search a topic nobody real hosts | No Join; a note that everyone there is simulated |
| Waiting screen (FR-43, D42) | Join | "Asking Alex · Biochemistry" with a 5:00 countdown |
| Nobody available (FR-33) | Host declines with Not now | "No one's free right now" and "Find a seat" |
| Related material (FR-54) | After an exhausted same-course search with related hosts | "Try people studying related material" |
| Cancel | "Cancel search" | Back to the map; the host's card disappears |

### Hosting from your chair
| Feature | How to test | Expect |
|---|---|---|
| Seat sheet from a chair or QR (FR-21, D49) | Tap Table 01, then seat 1, or open `/seat/t1-s1` | "Table 01 · Seat 1", its state, "Open to study partners" switch |
| Must be sitting there (FR-22) | Switch on with seat 1 empty (`1 e`) | "Sit down first…" with Try again |
| Topic and about me (FR-23) | Switch on with `1 p`, enter a topic | Host panel says "Findable by people on your course" |
| Hidden reasons (FR-24–27) | Type `1 e` (away), or mute | Hidden, with the reason in plain words |
| Request card (FR-36, D43) | Seeker joins | "Priya · Chemistry wants to study CH 320M…" with countdown, Accept / Not now / Mute |
| Mute from a card (FR-28) | Tap Mute | Request declined silently; "Unmute requests" appears |
| Stop hosting | "Stop hosting" | Session ends; back to the map |
| Live bar | While hosting, open the map | A bar at the top of the panel returns to the host panel |

### The match
| Feature | How to test | Expect |
|---|---|---|
| Match on both devices (FR-38) | Host accepts | Both open `/match/<id>`: name and major, building, floor, table, seat, card image, icebreaker |
| Seat on the plan | Same | The plan zooms to the table; the seat is ringed "Your seat" or "Priya's seat" |
| New seat if taken (FR-39) | Seat 2 gets a person (`2 p`) before arrival | Note on both devices; the ring moves to the nearest open seat |
| I'm here (FR-40) | Seeker taps "I'm here" | "You found each other"; the seat LED blinks blue again |
| Cancel and expiry (FR-41, 42) | Cancel on either side | Both show "This match was cancelled" |
| Block and report (FR-45, D53) | On a request card, the waiting screen or the match | Confirm dialog; a report asks for a reason and also blocks |

### Accounts, honesty and app behavior
| Feature | How to test | Expect |
|---|---|---|
| Demo login and restore (FR-16, D9) | Log in, reload on any screen | Same screen after reload; a match or search reopens from `/` |
| Freshness pill (D46) | Watch the top bar; stop the database (`docker stop ghostseats-db`) | Live → "Unable to refresh" / "Offline · data from N s ago"; back to Live after `docker start` |
| Back button and deep links | Open `/b/pcl/2/pcl-2-t1` in a new tab, press the in-app back arrow | Goes up to `/b/pcl/2`, not out of the app |
| Dark mode (D47) | Account or settings menu → Dark; or the system setting | A separate dark palette; the map restyles too |
| Accessibility | Tab through; turn on VoiceOver; set Reduce Motion | Visible focus everywhere; chairs read "Table 01 seat 2, open"; no animation with Reduce Motion |
| Offline (Mac) | Load once, then turn Wi-Fi off and reload | Map, tiles and last counts appear, labeled with their age |
| Install **(device, HTTPS)** | Chrome: install icon; iPhone Safari: Share → Add to Home Screen | Opens full screen with the ghost-chair icon |
| Push **(device, HTTPS)** | Seeker: "Get a notification when they answer" → Turn on; lock the phone; host accepts | A notification that opens the match |
| Update prompt | Rebuild and reload while the app is open | "A new version is ready" with Reload |

## Automated checks

| Command | Covers |
|---|---|
| `npm test` (`frontend/`) | FR-8 colors, floor layout on every seeded floor, polling and backoff, freshness, notification URLs, push body |
| `npm run build` (`frontend/`) | Typecheck of the app and the service worker, then the production build |
| `make check` / `make test-db` (`backend/`) | API, services and repository, including the D53 additions |
