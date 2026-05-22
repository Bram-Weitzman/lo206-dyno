# CLAUDE.md — Dev context for Claude Code

## Project purpose

Build a hybrid hydraulic/mechanical dynamometer for the Briggs & Stratton
LO206 kart engine, controlled by a Raspberry Pi running OpenPLC. We are
**sim-first**: a Python simulator stands in for the engine + load so the
entire control system can be validated before any hardware is bought.

## Current phase

**Current phase: hardware procurement.**

The full software stack is complete and verified end-to-end on dyno-dev:
- Simulator: DynoEngine class, clutch model, RPM noise model, 14/14 tests passing
- PLC control logic: PID hold, manual, sweep modes; safety interlocks
- Logger: Modbus TCP → SQLite at ~100 ms poll rate
- Dashboard: Next.js, live chart (RPM/torque/HP), run history, CSV export —
  verified 2026-05-21 with PLC holding 5000 RPM in PID mode
- Outstanding software issue: below 3,400 RPM the clutch disengages but
  pressure and CHT still compute from raw pump load (one-line fix, low
  priority — see Known open questions)
- Hardware: procurement in progress — proportional valve now confirmed
  (see docs/bom.md); all other hardware TBD

**Phase 4 (presentation/blog): not started, deadline May 29.**

**Hydraulic circuit decisions locked (May 2026):**
- Pump: 1.52 cu.in. gear pump, Princess Auto Item 8375446
- Drive: #219 chain, 20T drive sprocket / 70T driven sprocket, 3.5:1 reduction
  (same chain and ratio as the kart — reuses existing drivetrain components)
- Pump shaft speed: 6,200 RPM engine → 1,771 RPM pump (well within 3,000 RPM rating)
- Operating pressure revised to 500–700 PSI normal (3.5:1 ratio multiplies torque
  at pump shaft to ~35 ft-lbs, requiring ~595 PSI at 1.52 cu.in. displacement)
- Custom hub required: driven sprocket to 3/4 in. pump shaft — check if 70T #219
  sprocket is available in 3/4 in. bore before machining a custom part
- Operating pressure range: 500–700 PSI normal, 900 PSI software trip, 1,500 PSI mechanical relief
- Back-pressure baseline: ~200 PSI (return-line relief valve, Item 8688939)
- Note: OVERPRESSURE_TRIP_PSI in `simulator/modbus_map.py` is **900 PSI**
  (applied in commit 0dd0a7a) to match the chain-drive (3.5:1) pressure model.
- These values are reflected in `engine_sim.py` constants and `docs/bom.md`
- Observed RPM floor at max braking (100% valve): ~3,135 RPM in the updated
  simulator, down from ~4,236 RPM under the original 12.0 pump-load gain.

## Stack

- **Simulator**: Python 3.12 (pymodbus, numpy, pytest), venv at `/opt/dyno-venv`
- **PLC**: OpenPLC runtime, IEC 61131-3 Structured Text
- **Transport**: Modbus TCP (port 502)
- **Dashboard**: Next.js — complete (live RPM/torque/HP chart, run history, CSV export)
- **Persistence**: SQLite for local runs, PostgreSQL if/when we centralize

## Critical design principle

**The control logic is I/O-agnostic. The Modbus register map is the contract.**
The PLC reads sensor values and writes a valve command over Modbus. It does not
know or care whether the other end is the Python simulator or real hardware.
Never branch the control logic on "sim vs real". If the sim and the hardware
disagree, the register map (`plc/register_map.md`) is the source of truth and
must be changed *first*, deliberately, before either side.

## VM info

- Host alias: **dyno-dev** (Ubuntu 24.04 LTS dev stand-in for the Pi)
- IP: **10.20.99.55** (lab network 10.20.99.0/24)
- OpenPLC web UI: **http://10.20.99.55:8080** (service: `systemctl status openplc`)
- Python venv: **/opt/dyno-venv**
- Repo: **/home/ubuntu/projects/lo206-dyno**

## Key file locations

| Path                          | What it does                                      |
|-------------------------------|---------------------------------------------------|
| `simulator/engine_sim.py`     | LO206 engine + load physics model                 |
| `simulator/torque_curve.py`   | LO206 torque lookup table + interpolation         |
| `simulator/modbus_server.py`  | Modbus TCP server wrapping the sim                 |
| `plc/dyno_control.st`         | PID control loop + safety interlocks (ST)         |
| `plc/register_map.md`         | **The contract** — Modbus register definitions    |
| `docs/architecture.md`        | System design and rationale                       |
| `scripts/start_sim.sh`        | Launch the simulator                              |
| `scripts/provision_vm.sh`     | Reproduce the dev VM environment                  |

## Before writing any code

1. **Read `plc/register_map.md` first.** If your change touches any value that
   crosses the Modbus boundary, the register map must be updated *before* the
   code on either side.
2. Confirm which side *owns* the register you are touching (PLC-writes vs
   sim-writes). Owners are documented in the register map.
3. Keep the control logic free of sim-specific assumptions.
4. Run `pytest` in `simulator/` before committing simulator changes.

## Known open questions

- **Proportional valve**: RESOLVED — Sun Hydraulics RPGC-LBN confirmed; full
  spec, sources, and cost in `docs/bom.md`. Remaining sub-decision: the driver
  circuit (Option A custom MCP4725 DAC + DRV8871 vs Option B Sun PRZE-LBN amp
  card), both specced in `docs/bom.md` — pick one before ordering.
- **Engine inertia / valve lag constants**: placeholders in `engine_sim.py`;
  need real values once we can bench-measure the engine and valve.
- **Torque curve fidelity**: we currently use published B&S Black Slide data.
  Other slide configs are not yet digitized (see `docs/bom.md`).
- **Safety thresholds**: RPM > 6500 remains a first-guess — confirm against
  engine builder recommendations once on real hardware. PSI software trip:
  `OVERPRESSURE_TRIP_PSI` in `simulator/modbus_map.py` is **900 PSI** (applied
  in commit 0dd0a7a) to match the chain-drive (3.5:1) pressure model. System
  relief valve (Princess Auto Item 8688947) is set at 1,500 PSI; the software
  trip fires first. Back-pressure baseline is ~200 PSI (return-line relief, Item
  8688939). Review the RPM trip threshold after first live runs.
- **AFR channel (30006)**: reserved but unpopulated — wideband O2 is a Phase 2
  hardware addition.
- **Dashboard data path**: RESOLVED — the logger polls Modbus TCP and writes
  SQLite (`data/dyno.db`); the dashboard reads that SQLite DB. Verified
  end-to-end 2026-05-21.
- **Clutch model pressure/CHT scope** (known issue, low priority): below
  CLUTCH_ENGAGEMENT_RPM (3,400) the clutch is disengaged from engine
  acceleration, but hydraulic pressure and CHT still compute from the raw
  (un-clutched) pump load. One-line fix; deferred. Surfaced 2026-05-21.

## Real-world calibration data

Measured from actual LO206 race session (RPM + GPS logs, May 2026).
Use these as ground truth when setting sim constants and validating
the control system.

### Engine idle
- Warm idle RPM: **2,400–2,500 RPM**
- Cold/high idle during warmup: up to 3,000–3,200 RPM before settling
- Warm idle is safely below clutch engagement (~3,400 RPM) — engine can
  be started and warmed without loading the pump
- Dyno startup procedure: do not blip throttle above ~3,400 RPM until
  operator is ready to load the pump

### Clutch engagement profile (Hilliard Inferno Flame, stock config)
- Spring config: 2 black + 2 white springs, 0 heavy weights per shoe
- First engagement RPM: **~3,400 RPM** (confirmed — matches Hilliard spring
  chart spec, validated against race data cursor reading of 3,537 RPM at
  the visible transition point)
- Engagement behavior: **no RPM dip**. Engine RPM acceleration rate visibly
  reduces as clutch absorbs inertia torque, but RPM does not drop.
- Estimated full lockup RPM: **~4,200 RPM** under pump load (TBD — on-track
  data not conclusive; pump load is much heavier than kart rolling resistance)
- Sim model: torque_transfer = linear ramp from 0 at CLUTCH_ENGAGEMENT_RPM
  to 1.0 at CLUTCH_LOCKUP_RPM. No RPM dip modeled.
- Blog note: on-track clutch engagement is nearly transparent because kart
  rolling resistance is trivial. On the dyno, engagement against a pressurized
  pump circuit will be more pronounced — lockup RPM will shift higher under load.

### RPM signal characteristics
- Real RPM signal shows consistent ~±100 RPM noise band at steady state
- Visible across all zoom levels of race data
- Source: likely Hall-effect pickup with single trigger tooth — normal for kart
- Sim should add representative noise to RPM output so PID is tuned against
  realistic input, not a perfectly clean signal
- DONE: `RPM_NOISE_BAND = 100` applied in `engine_sim.py` (commit 4b126e1) —
  ±100 RPM injected on `get_rpm()` output only; internal physics state stays clean.

### Calibrated sim constants (applied)
The following constants are confirmed from real-world data and have been
applied to the simulator. IDLE_RPM, RPM_NOISE_BAND, and OVERPRESSURE_TRIP_PSI
were applied in the prior code session; the clutch constants are now wired into
the physics loop via clutch_torque_fraction() (this session).
Note: `OVERPRESSURE_TRIP_PSI` lives in `simulator/modbus_map.py`, not `engine_sim.py`.
The real simulator API uses `set_engine_enable()` and valve positions as 0–100 (int),
not `set_safety_enable()` or 0.0–1.0 floats — use the correct API when applying these.

```python
# engine_sim.py
IDLE_RPM = 2400               # APPLIED -- warm idle, measured from race data
CLUTCH_ENGAGEMENT_RPM = 3400  # APPLIED -- confirmed vs. spring chart and race data
CLUTCH_LOCKUP_RPM = 4200      # APPLIED -- estimated under pump load; validate on real hardware
RPM_NOISE_BAND = 100          # APPLIED -- +/-RPM noise on output only, steady state from race data

# simulator/modbus_map.py
OVERPRESSURE_TRIP_PSI = 900   # APPLIED -- 3.5:1 chain drive, ~595 PSI normal operating
```

## Git author note

Git on the VM is configured as `Bram Weitzman <bram.weitzman@gmail.com>`.
**Confirm/replace** these if a different identity should own the commits.

## Current session state

### Session 2026-05-22 — Issue #3: dashboard operator command path (partially closed)

The dashboard now has its first WRITE path. Issue #3 (no software start/throttle
path; engine could only be enabled by a manual `pymodbus` poke to OpenPLC :502)
is **partially closed**:

- **Write route `dashboard/app/api/command/route.ts`** — POST `{action}` where
  action is `start` | `stop` | `estop`. Writes operator commands to **OpenPLC
  :502** (the PLC's `%QW` image), never to the sim on :5020. `start` writes
  CONTROL_MODE=PID then SAFETY_ENABLE=1 (TARGET_RPM left as-is — sweep params are
  Session C); `stop`/`estop` write SAFETY_ENABLE=0. The route is the ONLY place
  the dashboard opens Modbus (per-request connection, closed in `finally`), has
  NO sim-vs-real branching, and returns the post-write read-back of TARGET_RPM /
  CONTROL_MODE / SAFETY_ENABLE. Uses the `modbus-serial` npm package (added this
  session). E-stop deliberately does NOT write the valve: the PLC interlock
  already forces VALVE_POSITION_CMD=0 on SAFETY_ENABLE=0 (verified end-to-end —
  `%QW100` read back 0 after stop/e-stop).
- **Run lifecycle moved from logger to dashboard.** The dashboard is now the
  SOLE creator/closer of `test_runs` rows: POST `/api/runs` opens a run, PATCH
  `/api/run/[id]` stamps `ended_at`. The logger (`logger/logger.py`) no longer
  INSERTs a run or UPDATEs `ended_at` — it polls for the newest open run, attaches
  samples to it, logs "Waiting for an open run" while none exists, and returns to
  waiting when the run closes (no restart needed). This removes the split-brain
  `run_id` failure mode from the earlier ops sessions: exactly ONE writer of run
  rows. The logger `--notes` flag is now a no-op (kept for start_all.sh / CLI
  compat); run notes are owned by the dashboard.
- **UI controls** (`dashboard/components/OperatorControls.tsx`, "use client"):
  Start (opens a run + enables engine), End Run (closes the run; does NOT stop
  the engine), Stop (SAFETY_ENABLE=0), and a large red always-visible Emergency
  Stop (immediate, no confirm). Start is disabled while a run is open; End Run is
  disabled while none is. Each command shows the `/api/command` read-back. Ending
  a run and stopping the engine are independently triggerable.
- **register_map.md ownership table corrected** — TARGET_RPM / CONTROL_MODE /
  SAFETY_ENABLE are now documented as OPERATOR inputs (the PLC consumes them);
  only VALVE_POSITION_CMD is PLC-written (operator-written in manual mode). This
  matches `dyno_control.st`'s header, which was already authoritative.

**Verified end-to-end from a REMOTE browser** (http://10.20.99.55:3000 from the
operator PC, not curl-from-VM — the cross-origin reload-storm class of bug is
invisible to localhost). After `./stop_all.sh && ./start_all.sh` the logger came
up "Waiting for an open run"; Start created run #9, the logger attached and
telemetry populated (PID holding ~5000 RPM, status dot green); End Run stamped
`ended_at` and the logger returned to waiting; Stop and E-stop both read back
SAFETY_ENABLE=0 and the sim went to STATUS=0. Network tab showed a steady
`/api/live` + `/api/runs` poll with NO `GET /` reload storm — the
`allowedDevOrigins` fix from the prior session is holding. Engine left STOPPED.

**What remains (NOT closed by this session):**
- **Sweep mode** is still a stub in `dyno_control.st` and there is no UI/route
  for sweep parameters (start/stop band, ramp rate, TARGET_RPM entry). That is
  **Session C**. `start` currently always uses CONTROL_MODE=PID with whatever
  TARGET_RPM is already in the register.
- Minor UI nuance (pre-existing, not introduced here): `/api/live` returns the
  last sample of the newest run even when that run is closed, so when no run is
  open the telemetry cards show the last-known (frozen) values rather than going
  blank. The operator-controls panel correctly shows "No run open". Worth a
  follow-up if it confuses operators.

**REAL-HARDWARE WARNING:** the dashboard Emergency Stop is a **convenience
control, NOT a safety device.** It issues the same software SAFETY_ENABLE=0
write as Stop and depends on the dashboard, network, OpenPLC, and the field bus
all being healthy. The real rig MUST have a **physically wired E-stop that breaks
the enable/power circuit** independently of any software — the on-screen button
sits beside it, it does not replace it.

Last worked on: 2026-05-21 — end-to-end integration validated. Simulator, PLC
control logic, SQLite logger, and Next.js dashboard are all complete, committed,
and verified together. Next.js bumped 14.2 -> 16.2 / React 18 -> 19 to clear 4
security advisories; required async-API migrations (`serverExternalPackages`,
async dynamic-route `params`) applied. `start_all.sh` / `stop_all.sh` added so
the whole stack comes up with one command.

Integration test (`/tmp/integration_test.py`, throwaway) ran the brief's
sweep 3000 -> 4000 -> 5000 -> 6100 -> 4000 RPM via OpenPLC's slave port 502
(operator writes go to `%QW100`-`%QW103`, not directly to the sim's holding
registers, because the PLC mirrors its own variables down to the sim every scan
and would overwrite direct writes). Results:

| Setpoint | Avg RPM (last 5s) | Steady err | Limiter? | OVERSPEED? |
|---------:|------------------:|-----------:|:--------:|:----------:|
| 3000     | 4236.0            | +1236.0    | no       | no         |
| 4000     | 4238.4            | +238.4     | no       | no         |
| 5000     | 5019.6            | +19.6      | no       | no         |
| 6100     | 6038.6            | -61.4      | **yes**  | no         |
| 4000     | 4244.8            | +244.8     | no       | no         |

- OK: OVERSPEED_TRIP (6500) never fired; max observed RPM 6106.
- OK: Limiter fired only at the 6100 setpoint step (34 of 1337 samples that run).
- NOTE: **Physical floor at ~4236 RPM.** With the brake at 100% the dyno cannot
  pull the engine below ~4236 RPM at full throttle — engine torque exceeds max
  brake torque at lower RPMs. The 3000/4000 setpoints in the brief are below
  this floor and saturate. The 5000 RPM step tracks within 20 RPM, which is
  the realistic working band.

**Known bug surfaced during integration:** the logger's default `--db`
is `data/dyno.db` *relative to CWD*, and the dashboard reads
`<cwd>/../data/dyno.db`. If the logger is launched from `logger/` they end up
on different files. `start_all.sh` runs the logger from the repo root so both
land on `data/dyno.db`. If you ever start the logger by hand, cd to the repo
root first (or pass `--db /home/ubuntu/projects/lo206-dyno/data/dyno.db`).

Immediate next step: write up the project (blog/docs) and prep the demo
presentation. Future calibration: tune J_ENGINE / cut-duration so per-cut RPM
drop at the limiter approaches the ~800 RPM real-world target.
Blocking questions: None.

### Bring-up notes — 2026-05-21 live-debug session

**Symptom:** full stack running (sim :5020, OpenPLC, logger, dashboard :3000) but
the dashboard showed "No live run" / "Waiting for data" and all telemetry was zero.

**Root cause (failure mode A + C): the engine was never enabled, and it cannot be
enabled by poking the sim.** `SAFETY_ENABLE` (40004 / `iSafetyEnable AT %QW103`)
is an *operator* command, but `dyno_control.st` has no code path that ever sets it
to 1 — it only reads it, or forces it to 0 on a latched fault. The OpenPLC
slave-device master writes all four holding registers (`%QW100..103`) to the sim
every 50 ms scan, so a manual write of SAFETY_ENABLE=1 directly to the sim
(port 5020) is overwritten back to 0 within one scan (verified: wrote
[_,5000,1,1], read back [_,4000,1,0] after 1 s). The dashboard is read-only and
has no Modbus write path, so nothing commands a start. This is the Issue #3 gap.

**Two suspected modes ruled out by evidence:**
- *Not a slave-mapping bug.* OpenPLC `ir_size = 7` is CORRECT, not a typo for 8.
  The PLC binds only `%IW100..106` (7 telemetry words) and deliberately omits
  `LIMITER_ACTIVE@30008` (the control law must not branch on it); the logger reads
  the 8th register straight from the sim. **Do not "fix" ir_size to 8.**
- *Not a DB-path mismatch.* Logger and dashboard share the same file (inode
  verified); `/api/live` was already serving valid JSON.

**Fix / how to enable the engine today:** write the operator commands to
**OpenPLC's own Modbus server on port 502** (exposes the PLC's `%QW` image), NOT
to the sim on 5020: addr 101 = TARGET_RPM, addr 102 = CONTROL_MODE (1 = PID),
addr 103 = SAFETY_ENABLE (1 = run). The PLC reads `%QW103=1`, runs the PID, and
mirrors the holding registers down to the sim — where SAFETY_ENABLE now *stays* 1.
Verified end-to-end: sim left STOPPED, RPM settled at 5004 (target 5000),
SIM_STATUS=1, `/api/live` live, dashboard populated.

**Full-stack launch order (one command: `./start_all.sh`):**
1. OpenPLC runtime (systemd `openplc` + start PLC via web API / :8080)
2. Simulator `simulator/modbus_server.py` — prefers 502, falls back to **5020**
   when unprivileged (the usual case)
3. Logger `logger/logger.py` from the **repo root** so `--db data/dyno.db`
   resolves to the same file the dashboard reads
4. Dashboard `npm run dev` in `dashboard/` (:3000)
Then enable via the port-502 writes above.

**OpenPLC slave-device config (runtime config — NOT version controlled; re-enter
in the web UI after a fresh OpenPLC install):** Protocol TCP, IP 127.0.0.1, Port
**5020**, Slave ID **1**, Input Registers start 0 size **7** (`%IW100..106`),
Holding Registers-Write start 0 size **4** (`%QW100..103`), Holding-Read size 0.

**Open architectural gap (Issue #3):** there is no software start/throttle command
path. The engine can be enabled today only by a manual write to OpenPLC port 502
(or a hardwired operator panel on the real rig). The dashboard is a read-only
observer. Building the dashboard's command-write path (TARGET_RPM / CONTROL_MODE /
SAFETY_ENABLE -> OpenPLC port 502) is Issue #3 and is the real fix that makes the
rig operable without a manual pymodbus poke.

**OpenPLC Monitoring page empty:** the located `%IW/%QW` vars were not published to
the web Monitoring table this session, so `%QW103` could not be forced from the UI
— which is why the port-502 write is the working enable path. Data flow itself was
fine; only the web Monitoring view was empty.

### Bring-up notes — 2026-05-21 ops/split-brain session

**Symptom (Round 2):** dashboard intermittently showed "No live run" / zeros
even though `./start_all.sh` had succeeded and the sim was clearly running on
:5020.

**Root cause: duplicate sim + duplicate logger — split-brain on `run_id`.** Two
`modbus_server.py` and two `logger/logger.py` processes were alive. The losing
sim couldn't bind 5020 but the winning logger and losing logger each opened a
fresh row in `test_runs` and wrote samples under different run IDs. The
dashboard's `/api/live` reads "the latest run" — whichever logger opened the
newer row owned the dashboard, regardless of which sim was actually being
driven by the PLC. NOT a code bug. **Slave `ir_size=7` is still correct by
design — do not "fix" it.**

**Operational fix:** `start_all.sh` and `stop_all.sh` are now idempotent
(commit 1ddc623):
- `start_all.sh` gates each service on `pgrep -f` of its cmdline pattern. If
  something already matches, it records that PID into the pidfile and skips
  the spawn instead of blindly launching a second instance.
- `stop_all.sh` kills ALL pids matching each pattern (not just the one in the
  pidfile), so orphans started outside `start_all.sh` (e.g. by
  `scripts/start_sim.sh` or a manual `python3 logger/logger.py`) are also
  cleaned up.

**Clean cold-start sequence (now safe to re-run any time):**
1. `./stop_all.sh`   — kills any sim/logger/dashboard duplicates by pattern,
   leaves OpenPLC runtime alone
2. `./start_all.sh`  — idempotent; brings up exactly one of each service.
   Verify with `ps -eo pid,cmd | grep -E 'modbus_server|logger|next' | grep -v grep`
3. Confirm sim is on **:5020** (`ss -tln | grep 5020`) and OpenPLC slave is
   pointed there
4. Enable via OpenPLC port **:502** — write `%QW101=TARGET_RPM`,
   `%QW102=1` (CONTROL_MODE = PID), `%QW103=1` (SAFETY_ENABLE). Do NOT
   write SAFETY_ENABLE directly to the sim on :5020; the PLC overwrites it
   within one scan (see prior session note).

**Engine left RUNNING at 5000 RPM** at end of session so the operator sees
live data on the dashboard. To stop cleanly: write `%QW103=0` via :502.

**Still open: Issue #3.** No software start/throttle path — enabling the
engine still requires a manual `pymodbus` write to OpenPLC :502. The
dashboard remains read-only. Closing #3 (adding a dashboard command-write
path) is the real fix for ergonomic operation.

### Bring-up notes — 2026-05-21 remote-browser HMR reload storm

**Symptom (Round 3):** the operator's browser at `http://10.20.99.55:3000`
showed "No live run" and empty cards even though all server-side checks
passed: one of each process, logger writing the same `data/dyno.db` the
dashboard reads (inode-verified), run #8 open, `SAFETY_ENABLE=1` at the
PLC, and `/api/live` returning valid live JSON when curled from the VM
itself.

**Root cause: Next 16 cross-origin dev guard.** Browsing the dev server
from any host other than `localhost` (the operator PC -> `10.20.99.55`)
counts as cross-origin in Next 16. With no `allowedDevOrigins` in
`next.config.js`, the HMR WebSocket (`/_next/webpack-hmr`) was blocked at
startup -- visible in the dev-server log as a one-time warning. The HMR
reconnect path then fell back to force-reloading `/` several times per
second; the access log showed hundreds of `GET /` against only ~3
`GET /api/live` calls. Each reload re-mounted `<Page>`, scheduled
`setInterval(tick, 500)` -- and then the next reload tore the component
down before the first 500 ms tick fired. The poll never got a chance to
run on the client even though `page.tsx` correctly declared `"use client"`
and the useEffect was structured properly.

**This bug is undetectable by curl-from-VM testing.** `curl http://localhost:3000/api/live`
from inside the VM is same-origin -- Next never trips the guard, the API
returns fine, and the server side looks healthy. The failure mode lives
entirely in the remote browser. **Future verification of dashboard
behavior MUST include opening the URL in a real browser on the operator
PC -- a healthy `/api/live` curl from the VM is not sufficient.**

**Fix (commit 0b625b7):** added `allowedDevOrigins: ["10.20.99.55"]` to
`dashboard/next.config.js` and restarted the dashboard only (sim, logger,
OpenPLC, and run #8 left untouched). Post-restart the dev-server access
log shows a steady stream of `GET /api/live` and zero new `GET /` rows
over a 15-second window -- the reload storm is gone. No recharts /
hydration / React-19 errors in the log, so the secondary recharts-vs-
React-19 suspect does not need a bump right now.

**Recharts caveat for future migrations:** `recharts ^2.13.3` is what the
Next 14 -> 16 / React 18 -> 19 migration left in `package.json`. It
worked here without a render-time throw, but recharts 2.13.x had
documented React-19 incompatibilities; if `<LiveChart>` ever starts
throwing during render after a dependency bump, suspect recharts first
and try bumping to 2.15+.
