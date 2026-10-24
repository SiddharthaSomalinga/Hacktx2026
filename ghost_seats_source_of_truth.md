# HackTX 26 Project Doc: Ghost Seats (Single Source of Truth)
**Last Updated:** Saturday, Oct 24, 2026 · **Tracks:** Best Hardware (Brick House), Meta (Bringing People Closer Together with AI), MLH Best Use of Tiger Data (+ Automatic: Best Novice, Best Overall)

---

## 1. Context & Rules for AI Assistants
If you are an AI assistant reading this: you are helping a 4-person team at a 24-hour hackathon (HackTX 26 at UT Austin). **This document is the final, locked single source of truth.**

### Rules for Helping Us
* **Optimize for shipping a working demo by Sunday 11:30 AM.** Speed and reliability beat elegance.
* **Hardware is locked to 4 core components (plus LEDs):** Arduino UNO R4, Micro Switch (acting as the central seat pressure/weight sensor), HC-05 Bluetooth Transmitters, and a Raspberry Pi. Do not suggest ultrasonic, mmWave, thermal, sound, or UV sensors.
* **No voice activation.** Check-in is triggered centrally by the physical pressure sensor (Micro Switch) and completed via a fast web input powered by Meta's **Muse Spark** and **Muse Image**.
* **Obey the Section 4 Interface Contract.** All communication between the hardware node, backend, and frontend must strictly follow the JSON payloads defined below.
* **Be direct and honest.** Flag risks plainly.

### Key Event Deadlines (Central Time)
* **Soft Submission (Devpost):** Saturday 11:30 PM (`hacktx26.devpost.com`)
* **WEL Building Lockout:** 11:00 PM – 6:30 AM (Overnight work/deployment must be in GDC)
* **Hard Submission & Hacking Ends:** Sunday 11:30 AM
* **Live Judging:** Sunday 2:00 PM – 5:00 PM in WEL
* **Pitching Competition:** Sunday 5:30 PM – 6:00 PM in GDC 2.216

---

## 2. Product Summary & The Core Social Hook

**One-Sentence Pitch:** Catch library "ghost seats" (saved by an unattended backpack for hours) using passive seat pressure & proximity hardware, and use Meta Muse to effortlessly match with students studying the exact same topic at an open seat right next to them.

### The Dual Problem We Solve
1. **The Space Problem (Ghost Seats):** Libraries look full during midterms, but 20–30% of seats are just holding a backpack while the owner is gone for an hour. Self-reported QR check-ins fail because people forget to check out—and seat hoarders never scan them.
2. **The Social Problem (Isolated Studying):** Hundreds of students sit in the same library struggling through the exact same problem sets alone because there is no low-friction way to know who is studying what, whether the seat next to them is actually free, and how to approach them without awkwardness.

### Why Meta Muse Is Integral (Not Tacked-On)
Muse is the bridge that turns a raw **physical seat state** into a **real-world human connection**:
1. **Physical Pressure Trigger $\rightarrow$ Instant Social Check-In:** When a student sits down, the **Micro Switch (pressure sensor)** closes. This physical state change unlocks the "Studying Here" prompt on the web app—ensuring only people physically occupying a seat can broadcast their study session.
2. **Zero-Effort Topic & Space Matching (`Muse Spark`):** Students type messy shorthand (*"dying on ch 320m stereochem mechanisms"* or *"314 trees hw"*). **`Muse Spark`** normalizes messy student input into structured UT course codes/topics, cross-references live **Tiger Data** seat availability to find matches **at tables that actually have an open or ghosted seat nearby**, and generates a hyper-specific 1-sentence study icebreaker (*"You're both working on CH 320M stereochemistry—compare your R/S configurations on Problem 4 first"*).
3. **Eliminating "First-Approach" Awkwardness (`Muse Image` + Blue LED):** Walking up to a stranger in a quiet library is intimidating. When two students accept a match, the hardware table blinks **Blue** (`blue_blink`) AND **`Muse Image`** generates a custom **Visual Study Pass** (a shared graphic badge for their specific topic and table) on both of their screens. The approaching student simply holds up the visual pass on their phone and walks to the blue-blinking table—zero awkward wandering.

---

## 3. Confirmed Hardware Architecture

We use a lean, bulletproof hardware stack owned by the **Hardware Pair**. Every seat answers two questions: **Is weight/pressure on the seat (`object_present`)?** and **Is the human actively there (`human_present`)?**

### Locked Component List
| Component | Role in System | How It Works |
| :--- | :--- | :--- |
| **Micro Switch (Central Pressure Sensor)** | Detects `object_present` (Weight on Seat / Tabletop) | Mounted underneath a hinged seat pad / tabletop mat. When a student sits down OR drops a heavy backpack on the seat, the physical weight depresses the micro switch (`object_present = true`). When lifted, it springs back (`object_present = false`). |
| **HC-05 Bluetooth Transmitter** | Detects `human_present` (Active Student Presence) | Acts as a short-range proximity/connection beacon paired to the student's device (or a secondary clip-on HC-05 tag). When the student is at the table, the HC-05 link/state pin is active (`human_present = true`). When they walk away and leave their backpack on the micro switch, the link drops (`human_present = false`). |
| **Arduino UNO R4** | Real-Time Sensor Controller & LED Driver | Reads the Micro Switch digital pin and HC-05 state/serial link every 500 ms. Drives the seat status LEDs (**Green** = Open, **Red** = Occupied, **Yellow** = Ghosted/Opening Soon, **Blinking Blue** = Social Match Handshake). |
| **Raspberry Pi** | Edge Gateway & API Forwarder | Connects to the Arduino R4 via USB Serial (or Bluetooth via a receiver HC-05). Aggregates sensor readings every 2 seconds, sends `POST /api/readings` to the cloud backend over Wi-Fi/hotspot, and passes the backend's LED color commands back to the Arduino. |

### The 3 Hardware States + 1 Social State
1. **OPEN (`Green LED`):** Micro Switch is OPEN (`object_present: false`) + HC-05 is DISCONNECTED (`human_present: false`).
2. **OCCUPIED (`Red LED`):** Micro Switch is PRESSED (`object_present: true`) + HC-05 is CONNECTED (`human_present: true`). *Triggers the web check-in prompt.*
3. **GHOSTED / LIKELY OPENING SOON (`Yellow LED`):** Micro Switch is PRESSED (`object_present: true` — backpack left behind) + HC-05 is DISCONNECTED (`human_present: false` — human walked away) for longer than the ghost threshold (30 seconds in demo mode; 30 minutes in production).
4. **SOCIAL MATCH (`Blinking Blue LED`):** Triggered by the backend for 60 seconds when two students accept a study match via **Muse**, guiding the new study partner directly to the table.

---

## 4. Software Architecture & Interface Contract

The backend is the single source of truth. The **Software Pair** builds against this exact contract so hardware and software never block each other.

### Node-to-Backend Contract (`POST /api/readings`)
Sent by the Raspberry Pi every 2 seconds.
**Request:**
```json
{
  "node_id": "table-1",
  "readings": [
    {"seat_id": "t1-s1", "object_present": true, "human_present": false},
    {"seat_id": "t1-s2", "object_present": false, "human_present": false}
  ]
}
```
**Response:**
```json
{
  "leds": {
    "t1-s1": "yellow",
    "t1-s2": "green"
  }
}
```
*Allowed LED values:* "green", "red", "yellow", "blue_blink", "off".
*Offline Fallback:* If the Raspberry Pi/Arduino gets no backend response for 10 seconds, it defaults locally to "red" when the Micro Switch is pressed (`object_present: true`) and "green" when unpressed (`object_present: false`).

### Website-to-Backend Contract
| Method & Path | Auth | Purpose & Muse AI Role |
| :--- | :--- | :--- |
| `GET /api/buildings` | None | Lists buildings with `open_seats`, `likely_opening_seats`, `total_seats`, and `is_simulated`. |
| `GET /api/buildings/{id}/seats` | None | Returns seats by floor/table with public state (`open`, `occupied`, `likely_opening`). Never exposes raw ghost duration to prevent theft. |
| `GET /api/buildings/{id}/history` | None | Queries **Tiger Data** time-series hypertable for hourly seat availability charts. |
| `POST /api/status` | Login Stub | Activated when the pressure sensor (`object_present`) is active. Sends `{subject_raw, building_id, floor, seat_id, open_to_company}`. Calls **`Muse Spark`** to normalize the course/topic and verify an adjacent seat at that table is `open` or `likely_opening`. |
| `DELETE /api/status` | Login Stub | "I'm leaving" button (or auto-triggered when the seat pressure sensor goes `false` for >5 mins). |
| `GET /api/matches?subject=...` | Login Stub | Uses **`Muse Spark`** semantic ranking to return opted-in students studying the same/complementary topic **who have an open or ghosted seat at their table**. |
| `POST /api/requests` | Login Stub | Sends a study meetup request to a matched student. |
| `GET /api/requests` | Login Stub | Polls incoming/outgoing study requests every 3 seconds. |
| `POST /api/requests/{id}/accept` | Login Stub | Confirms the match! Calls **`Muse Spark`** to generate a custom 1-sentence study `icebreaker`, calls **`Muse Image`** to generate a shared `study_pass_image_url`, and sets the host student's `seat_id` LED to `"blue_blink"` for 60 seconds. |

### Database Schema (Postgres on Tiger Data)
* **`buildings`**: `building_id`, `name`, `is_simulated`
* **`seats`**: `seat_id`, `node_id`, `building_id`, `floor`, `table_label`
* **`seat_readings`** *(Tiger Data Hypertable)*: `time`, `seat_id`, `object_present`, `human_present`
* **`seat_state`**: `seat_id`, `state` (`open`, `occupied`, `ghosted`), `state_since`, `away_since`, `match_blink_until`
* **`users`**: `user_id`, `first_name`, `email`, `verified` (Stubbed via dropdown selector for demo)
* **`study_status`**: `user_id`, `seat_id`, `subject_raw`, `subject_normalized` (JSONB from `Muse Spark`), `building_id`, `floor`, `table_hint`, `open_to_company`, `expires_at`
* **`match_requests`**: `request_id`, `from_user`, `to_user`, `status` (`sent`, `accepted`, `declined`, `expired`), `icebreaker` (Text from `Muse Spark`), `study_pass_url` (URL from `Muse Image`), `created_at`

---

## 5. Build Priorities & Schedule (4:30 PM Onward)

Build strictly in tier order. Do not start a lower tier until the tier above it works end-to-end.

| Tier | Feature | "Done" Means | Target Time |
| :--- | :--- | :--- | :--- |
| **Tier 1 (Must)** | **Pressure + Proximity Node** | Arduino R4 reads Micro Switch (`object_present`) + HC-05 (`human_present`) and sends JSON via Raspberry Pi. | **Sat 5:30 PM** |
| **Tier 1 (Must)** | **Backend State Engine + LEDs** | Backend computes `open`, `occupied`, `ghosted` (30s demo timer) and drives Green/Red/Yellow LEDs on the Arduino. | **Sat 7:00 PM** |
| **Tier 1 (Must)** | **Live Public Seat Map** | Website displays buildings, tables, and live seat states updating every 3 seconds without login. | **Sat 7:00 PM** |
| **Tier 2 (Should)** | **Tiger Data Time-Series History** | `seat_readings` hypertable stores live + simulated history and renders 1 clean availability chart on the building page. | **Sat 10:00 PM** |
| **Tier 2 (Should)** | **Clean Demo Table Enclosure** | Hinged pressure pad over the Micro Switch so placing a real backpack or sitting/pressing triggers it cleanly with hidden wires. | **Sat 11:00 PM** |
| **Tier 2 (Should)** | **Devpost Soft Submission** | Draft project page submitted on `hacktx26.devpost.com` with 3 tracks locked in. | **Sat 11:30 PM** |
| **Tier 3 (Must for Meta)** | **Muse Spark Smart Matching** | Pressure check-in unlocks status input; `Muse Spark` normalizes topics, filters for tables with open/ghosted seats, and ranks matches. | **Sun 1:00 AM** |
| **Tier 3 (Must for Meta)** | **Muse Image Pass + Blue LED** | Accepting a match generates the `Muse Spark` icebreaker + `Muse Image` visual study pass and blinks the Blue LED on the table. | **Sun 2:00 AM** |

---

## 6. The 2-Minute Live Judging Demo Script

Tailor the emphasis to the judge standing in front of you (Hardware vs. Meta), but run this exact flow:

1. **The Hook (0:00–0:15):** *"During midterms at PCL, you don't just waste 30 minutes looking for a seat because of 'ghost backpacks'—you also end up studying the exact same exam material completely alone. Ghost Seats fixes both."*
2. **The Central Pressure Sensor & Ghost Detection (0:15–0:45):**
   * Have the judge place a heavy backpack on the demo seat (**Micro Switch** depresses $\rightarrow$ `object_present: true`).
   * Show the **HC-05** transmitter link is active (`human_present: true` $\rightarrow$ **Red LED: Occupied**).
   * Turn off/walk away with the **HC-05** student tag while leaving the backpack on the **Micro Switch**. After the sped-up 15-second demo timer, the LED turns **Yellow ("Likely Opening Soon")** and the live website map updates immediately.
3. **The Meta Muse Social Handshake (0:45–1:30):**
   * A teammate presses down the seat (**Occupied**) and types `"ch 320m stereochem mechanisms"` into the check-in box.
   * On a second screen, the judge types `"orgo 1 exam prep"`.
   * Show **`Muse Spark`** instantly bridge the two different phrasings into a high-confidence `CH 320M / Organic Chemistry I` match **specifically because our hardware knows there is an open seat right next to them at Table 1**.
   * The judge clicks **Request to Study**, and the teammate clicks **Accept**.
   * **The Payoff:** Instantly, the physical seat LED starts **blinking Blue**, **`Muse Spark`** displays a custom icebreaker (*"Start by comparing your R/S stereocenter rankings on the practice exam"*), and **`Muse Image`** renders a shared visual **Study Pass** on both screens so they can spot each other and sit down together with zero awkwardness.
4. **Architecture & Close (1:30–2:00):** Highlight the passive, camera-free privacy design, the **Tiger Data** time-series occupancy chart, and our live student survey results.
