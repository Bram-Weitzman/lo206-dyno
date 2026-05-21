# LO206 Dyno — Dashboard

A Next.js dashboard for the LO206 dynamometer: a **live** view (status bar +
rolling 60-second chart) and a **run history** view (table of past runs, a
static per-run chart, and per-run CSV export).

## What it does

- **Live section** — auto-refreshes every 500 ms:
  - **Status bar**: current RPM, torque (ft-lbs), HP, valve %, control mode, and
    sim status.
  - **Live chart**: rolling 60-second window with three lines — RPM (left axis),
    torque and HP (right axis). The window clears and restarts when a new run
    begins.
- **Run history section**:
  - Table of past runs (started, ended, notes, sample count).
  - Clicking a row loads that run's full samples into a static chart above the
    table.
  - **Export CSV** button per run — downloads all samples for that run.

## How it connects to the data

The dashboard reads from `data/dyno.db` (SQLite). It does **not** talk to Modbus
and has no direct connection to the simulator or hardware:

```
  simulator/PLC  --Modbus-->  logger  --writes-->  dyno.db  <--reads--  dashboard
```

The **logger** process (`logger/logger.py`) polls the Modbus registers and writes
samples continuously. The dashboard is a pure, read-only **observer** of that
same file. There is no shared in-memory state, message bus, or IPC between the
two — SQLite is the entire handoff layer. This keeps the logger and dashboard
fully decoupled: either can be restarted independently.

All engineering-unit conversions (`torque_ftlbs = torque_x10 / 10`,
`valve_pct = valve_cmd / 100`, `cht_c` is 1:1 °C) live in the API layer
(`lib/types.ts`), per `simulator/modbus_map.py`. The DB stores raw register
values.

## Live polling architecture — why polling, not WebSocket

The frontend polls `GET /api/live` every 500 ms via `fetch()`. There is no
WebSocket and no streaming infrastructure, by design:

- **Simplicity** — no socket server, no reconnection/backpressure handling, no
  extra process to supervise.
- **Sufficient** — the logger writes at ~100 ms; a 500 ms UI refresh is plenty
  for a human watching a status board, and the chart still shows fine detail
  because each `/api/live` poll reads the newest committed sample.
- **No extra infrastructure** — it is just HTTP against the same Next.js server
  that serves the page.

## Install

```bash
cd dashboard
npm install
```

`better-sqlite3` is a native module; `npm install` fetches a prebuilt binary for
the platform (no compiler needed on Node 22).

## Run

```bash
# from the dashboard/ directory
npm run dev
# then open http://localhost:3000
```

The DB path is configurable via the `DYNO_DB_PATH` environment variable. The
default is `../data/dyno.db` (relative to the dashboard directory), which is
correct when you run `npm run dev` from `dashboard/`. To point elsewhere:

```bash
DYNO_DB_PATH=/abs/path/to/dyno.db npm run dev
```

Production build:

```bash
npm run build && npm start
```

## API routes

| Route                | Returns                                                       |
|----------------------|---------------------------------------------------------------|
| `GET /api/live?run_id=N` | Most recent sample for run N (or the latest run if omitted). |
| `GET /api/runs`      | All runs, newest first, each with a `sample_count`.           |
| `GET /api/run/[id]`  | All samples for a run, ordered by time — history + CSV.       |

Sample shape (engineering units):

```json
{
  "run_id": 1, "ts": "2026-05-21T...Z",
  "rpm": 5000, "torque_ftlbs": 6.6, "hp": 6.28,
  "pressure": 110, "cht_c": 85, "valve_pct": 67.3,
  "control_mode": 1, "sim_status": 1, "limiter_active": 0,
  "rpm_setpoint": 5000
}
```

## CSV export

Each run row has a **CSV** button. The CSV is built **client-side** from the
`/api/run/[id]` response and downloaded via a Blob (no server-side file
generation). Column order:

```
ts, rpm, torque_ftlbs, hp, pressure, cht_c, valve_pct, control_mode, sim_status, limiter_active
```

Files download as `dyno_run_<id>.csv`.

## What changes for real hardware

**Nothing in the dashboard.** The dashboard reads the DB; the logger writes the
DB. Only the logger's `--host`/`--port` change to point at the real rig instead
of the simulator. The register contract, schema, and conversions are identical.

## Verified

Verified on the `dyno-dev` VM (Ubuntu 24.04, Node v22.22.2, npm 10.9.7) on
2026-05-21 against the simulator with the OpenPLC runtime closing the control
loop (PID holding 5000 RPM), the logger writing `data/dyno.db`, and the
dashboard reading it.

**`npm run build` — clean:**

```
 ✓ Compiled successfully
   Linting and checking validity of types ...
Route (app)                              Size     First Load JS
┌ ○ /                                    103 kB          191 kB
├ ƒ /api/live                            0 B                0 B
├ ƒ /api/run/[id]                        0 B                0 B
└ ƒ /api/runs                            0 B                0 B
```

**`GET /api/runs`** — newest first, `sample_count` via JOIN:

```json
[
  {"id":2,"started_at":"2026-05-21T01:46:22.689+00:00","ended_at":null,"notes":"dashboard verification","sample_count":2826},
  {"id":1,"started_at":"2026-05-21T01:24:41.212+00:00","ended_at":"2026-05-21T01:24:56.020+00:00","notes":"integration test","sample_count":148}
]
```

**`GET /api/live`** — valid JSON, live values (RPM 5000, mode PID, running):

```json
{"run_id":2,"ts":"2026-05-21T01:51:05.403+00:00","rpm":5000,"torque_ftlbs":6.6,
 "hp":6.283320639756283,"pressure":386,"cht_c":91,"valve_pct":67.29,
 "control_mode":1,"sim_status":1,"limiter_active":0,"rpm_setpoint":5000}
```

Conversions confirmed against `simulator/modbus_map.py`: `torque_ftlbs` = 66/10,
`cht_c` = 91 (1:1 °C, not divided), `valve_pct` = 6729/100.

**`GET /api/run/2`** — array of 2836 samples ordered by `ts` ASC (first sample
timestamp earlier than last).

**Page** — `GET /` returns HTTP 200 and renders the title plus the "Live" and
"Run history" sections. The status bar shows live values, and the live chart
renders and updates on the 500 ms poll. Invalid run id (`/api/run/abc`) returns
HTTP 400.

**CSV export** — built client-side from the `/api/run/[id]` response and
downloaded via a Blob, with the column order documented above.

## Known limitation — read-only (Issue #3)

The dashboard is a pure **observer**: it reads `data/dyno.db` and has **no Modbus
write path**. It cannot start the engine or change TARGET_RPM / CONTROL_MODE /
SAFETY_ENABLE. Until a command-write path is added (**Issue #3**), the engine is
enabled out-of-band by writing the operator commands to OpenPLC's Modbus server on
port 502 (`%QW101`=TARGET_RPM, `%QW102`=CONTROL_MODE, `%QW103`=SAFETY_ENABLE) —
see `plc/README.md`. If the dashboard shows "No live run", the engine is simply
not enabled (`sim_status = 0`); that label is keyed off `sim_status !== 1` in
`app/page.tsx`, not a data-pipeline failure.
