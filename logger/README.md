# LO206 Dyno — Data Logger

A standalone Python process that polls the Modbus registers exposed by the
simulator (or, later, the real hardware I/O) and writes timestamped samples to
SQLite.

## Why it's a separate process

The simulator models the engine, the PLC (OpenPLC) closes the control loop, and
this logger is a passive **observer** of the Modbus register contract. It reads
telemetry only — it never writes the holding/command registers, which the PLC
owns. Keeping it out of the simulator means logging can be started, stopped, and
pointed at a different host (sim today, real rig tomorrow) without touching the
control or physics code. It is the natural place to land the SQLite/Postgres
"data path" question left open in the root `CLAUDE.md`.

## Running it against the simulator

```bash
# from the repo root, with the sim already running (scripts/start_sim.sh)
python logger/logger.py --interval 100 --notes "bench test"
```

The sim listens on port **502** when privileged and falls back to **5020** when
run unprivileged (the common case) — the logger defaults to `5020`. Point
`--port` at whatever the simulator logged on startup.

| Flag         | Default        | Meaning                                  |
|--------------|----------------|------------------------------------------|
| `--host`     | `localhost`    | Modbus TCP host                          |
| `--port`     | `5020`         | Modbus TCP port                          |
| `--interval` | `100`          | Poll interval, milliseconds              |
| `--db`       | `data/dyno.db` | SQLite output file                       |
| `--notes`    | (none)         | Optional note stored on the test run     |

A one-line status is printed once per second (not per poll):

```
[01:24:41] RPM: 5000 | Torque: 6.6 ft-lbs | HP: 6.28 | Valve: 67.3% | Mode: PID | Status: running
```

Stop with Ctrl-C: the logger stamps `test_runs.ended_at`, reports the sample
count, and exits cleanly. Lost Modbus connections and single failed polls are
logged and retried — the loop does not crash.

## Running it against real hardware

Only `--host` and `--port` change:

```bash
python logger/logger.py --host 10.20.99.x --port 502 --notes "dyno pull 1"
```

Everything else — the register addresses, scaling, schema — is identical. The
addresses, scale factors, and mode constants are imported from
`simulator/modbus_map.py`, the single source of truth mirrored in
`plc/register_map.md`, so the logger can never drift from the contract.

## Database

- Default location: `data/dyno.db`.
- **Gitignored.** `.gitignore` ignores `data/*.db` (and `*.db` globally) so test
  and run databases are never committed; only `data/.gitkeep` is tracked, so the
  default path works on a fresh clone with no manual `mkdir`.

### Schema

Two tables (see [`db_schema.sql`](db_schema.sql)):

- **`test_runs`** — one row per logging session: `started_at`, `ended_at` (NULL
  until a clean stop), and an optional operator `notes` string.
- **`samples`** — one row per poll, linked by `run_id`. Holds the raw register
  values plus a computed `hp` column.

### Raw vs. converted storage

Samples store **raw register values, not converted engineering units**:

- `torque_x10` is the raw 30002 value (ft-lbs ×10) — divide by 10 at display.
- `cht` is the raw 30004 value, which is **1:1 °C, not scaled** (per the
  contract — `HEAD_TEMP_C`, *not* `cht_x10`). Do not divide it.
- `valve_cmd` is the raw 40001 value (% ×100, 0–10000).
- `sim_status` is read from **30007** (30006 is the reserved `AFR_x10` register).

Storing the raw integers preserves the exact value that crossed the wire at full
resolution and keeps the conversion logic in one place (the dashboard). The one
derived column we precompute is `hp = (torque_x10 / 10.0 * rpm) / 5252.0`,
because it spans two registers and is handy for plotting power curves.

### Example query — last 60 seconds of a run

```sql
SELECT ts, rpm, torque_x10 / 10.0 AS torque_ftlbs, hp
FROM samples
WHERE run_id = (SELECT MAX(id) FROM test_runs)
  AND ts >= datetime('now', '-60 seconds')
ORDER BY ts;
```

## Verified

End-to-end test on `dyno-dev` (2026-05-21), simulator + OpenPLC running, logger
polling at 100 ms for 15 s (`--notes "integration test"`):

- **148 samples** written in 15 s (~9.9/s, consistent with 100 ms polling).
- First sample row `(rpm, torque_x10, pressure, cht, valve_cmd, control_mode,
  sim_status, limiter_active, hp)`:
  `(5000, 66, 386, 91, 6730, 1, 1, 0, 6.283)`.
  - RPM non-zero (5000), `torque_x10` 66 matches sim output (6.6 ft-lbs).
  - `hp` = (66/10 × 5000) / 5252 = **6.28** ✓.
  - `sim_status = 1` (running) — confirms 30007 is read, not the AFR register.
  - `cht = 91` stored 1:1 °C (not divided) — confirms the contract scaling.
  - `control_mode = 1` (PID): the OpenPLC PID loop was actively driving the
    valve (`valve_cmd` 6730 = 67.3%), so this is a true closed-loop capture.
- `test_runs` row: `started_at 2026-05-21T01:24:41.212+00:00`,
  `ended_at 2026-05-21T01:24:56.020+00:00` after a clean SIGINT — both populated.
- Timestamps are ISO-8601 UTC, millisecond precision, ~100 ms apart
  (`...41.222` → `...41.322`).
