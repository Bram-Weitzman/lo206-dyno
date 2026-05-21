# CLAUDE.md — Dev context for Claude Code

## Project purpose

Build a hybrid hydraulic/mechanical dynamometer for the Briggs & Stratton
LO206 kart engine, controlled by a Raspberry Pi running OpenPLC. We are
**sim-first**: a Python simulator stands in for the engine + load so the
entire control system can be validated before any hardware is bought.

## Current phase

**Phase 0 — scaffolding and simulator bring-up.** No hardware exists yet.
The immediate goals are: lock the Modbus register map, implement the torque
curve interpolation, and get the Modbus server talking to OpenPLC.

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
- Note: OVERPRESSURE_TRIP_PSI in `simulator/modbus_map.py` is currently 1,200 PSI
  (set in previous session). Pending update to 900 PSI in next code session to
  match revised chain-drive pressure model.
- These values are reflected in `engine_sim.py` constants and `docs/bom.md`
- Observed RPM floor at max braking (100% valve): ~3,135 RPM in the updated
  simulator, down from ~4,236 RPM under the original 12.0 pump-load gain.

## Stack

- **Simulator**: Python 3.12 (pymodbus, numpy, pytest), venv at `/opt/dyno-venv`
- **PLC**: OpenPLC runtime, IEC 61131-3 Structured Text
- **Transport**: Modbus TCP (port 502)
- **Dashboard**: Next.js (not scaffolded yet)
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

- **Valve driver**: 0-10V amp card vs PWM + MOSFET — undecided. See
  `docs/sim_to_real.md`.
- **Engine inertia / valve lag constants**: placeholders in `engine_sim.py`;
  need real values once we can bench-measure the engine and valve.
- **Torque curve fidelity**: we currently use published B&S Black Slide data.
  Other slide configs are not yet digitized (see `docs/bom.md`).
- **Safety thresholds**: RPM > 6500 remains a first-guess — confirm against
  engine builder recommendations once on real hardware. PSI software trip:
  `OVERPRESSURE_TRIP_PSI` in `simulator/modbus_map.py` is currently 1,200 PSI
  (set in previous session) and is **pending revision to 900 PSI** in the next
  code session to match the chain-drive (3.5:1) pressure model. System relief
  valve (Princess Auto Item 8688947) is set at 1,500 PSI; the software trip
  fires first. Back-pressure baseline is ~200 PSI (return-line relief, Item
  8688939). Review both thresholds after first live runs.
- **AFR channel (30006)**: reserved but unpopulated — wideband O2 is a Phase 2
  hardware addition.
- **Dashboard data path**: does the dashboard read Modbus directly, or through
  a logging service writing to SQLite/Postgres? Undecided.

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
- TODO: add `RPM_NOISE_BAND = 100` to `engine_sim.py` in a future session

### Calibrated sim constants (pending — apply in next code session)
The following constants are confirmed from real-world data but NOT YET applied
to the simulator. Apply them in the next dedicated code session.
Note: `OVERPRESSURE_TRIP_PSI` lives in `simulator/modbus_map.py`, not `engine_sim.py`.
The real simulator API uses `set_engine_enable()` and valve positions as 0–100 (int),
not `set_safety_enable()` or 0.0–1.0 floats — use the correct API when applying these.

```python
# engine_sim.py
IDLE_RPM = 2400               # Warm idle, measured from race data
CLUTCH_ENGAGEMENT_RPM = 3400  # Confirmed vs. spring chart and race data
CLUTCH_LOCKUP_RPM = 4200      # Estimated under pump load — validate on real hardware
RPM_NOISE_BAND = 100          # ±RPM noise observed at steady state in race data

# simulator/modbus_map.py
OVERPRESSURE_TRIP_PSI = 900   # Revised: 3.5:1 chain drive, ~595 PSI normal operating
                              # Currently 1,200 PSI — pending update
```

## Git author note

Git on the VM is configured as `Bram Weitzman <bram.weitzman@gmail.com>`.
**Confirm/replace** these if a different identity should own the commits.

## Current session state

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
