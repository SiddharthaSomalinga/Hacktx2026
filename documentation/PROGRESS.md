# PROGRESS.md — Ghost Seats

Session log. Concrete changes, commands and observed results only.

## Current status

- **Milestone:** documentation v1.1 complete; B0, F0 and H0 are next (PLAN.md).
- **Code:** none yet.
- **Open questions:** Q2, Q12, Q13, U1, U2, U3 (PLAN.md).

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
