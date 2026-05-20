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
- **Safety thresholds**: current limits (RPM > 6500, PSI > 1200) are
  first-guess values and must be reviewed against the real hydraulic circuit.
- **AFR channel (30006)**: reserved but unpopulated — wideband O2 is a Phase 2
  hardware addition.
- **Dashboard data path**: does the dashboard read Modbus directly, or through
  a logging service writing to SQLite/Postgres? Undecided.

## Git author note

Git on the VM is configured as `Bram Weitzman <bram.weitzman@gmail.com>`.
**Confirm/replace** these if a different identity should own the commits.

## Current session state

Last worked on: 2026-05-20. PID tuning pass 2 against the sim. Dropped `Kp`
from 0.30 → 0.20 in `dyno_control.st` (`Ki = 0.05`, `Kd = 0.01` unchanged),
recompiled under OpenPLC v3 and re-ran the 0 → 5000 RPM step from a freshly
restarted sim. Hunting collapsed (valve swing 5.3 pp → 1.3 pp), settling
sped up (~13.9 s → ~10.1 s), steady-state error tightened (8.4 → 3.0 RPM),
with rise effectively unchanged (~1.5 s) and a small overshoot increase
(~4 % → ~6 %). All pass-2 acceptance criteria from the brief met; `Kp = 0.20`
is the new committed default. Full before/after table and notes in
`plc/README.md` under "PID Tuning Log".

Gotcha worth carrying forward for next time: OpenPLC's `/compile-program`
silently 302-redirects to `/login` when the session cookie has expired and
no recompile actually happens, so always re-login before a compile call and
verify the rebuild by checking `core/openplc`'s mtime — not just the HTTP
status. The sim also has no mechanical-loss model, so between captures the
sim must be killed and restarted to start a step from RPM = 0.

Immediate next step: choose between (a) instrumenting the sim for a swept
RPM sweep (`CONTROL_MODE = 2`, the not-yet-implemented sweep mode) to
capture torque-vs-RPM curves end-to-end, or (b) beginning Phase 1 dashboard
scaffolding (Next.js skeleton + a Modbus → SQLite logging service). The
control loop is now usable; the bottleneck has shifted from controller
tuning to observability/UX.

Blocking questions: None outstanding from this session. Architectural and
hardware questions still live in the "Known open questions" section above.
