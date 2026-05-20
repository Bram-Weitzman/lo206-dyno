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

Last worked on: 2026-05-20. Initial scaffolding of this section. Most recent
engineering work was the first end-to-end verification of the closed-loop
step response (commit `28a4702`): `dyno_control.st` running under OpenPLC v3
held 5000 RPM against `simulator/modbus_server.py` with committed gains
(`Kp=0.3, Ki=0.05, Kd=0.01`, `T#50ms`). Rise time ~1.4 s, overshoot ~4 %,
settled within ±1 % by ~14 s, with visible steady-state hunting. Wiring
fixes (`AT %IW100..106` / `AT %QW100..103` clauses and a
`CONFIGURATION / RESOURCE / TASK` block) landed in the same commit; details
in `plc/README.md` under "Verified Step Response (sim)".

Immediate next step: PID tuning pass against the sim. Drop `Kp` to ~0.15–0.2
and rerun the 0 → 5000 RPM step against a freshly restarted sim; goal is to
collapse the steady-state hunting (currently ~62–70 % valve cycling) without
losing the ~1 s rise time. Re-tune `Ki` only if steady-state error widens
past ~25 RPM. Document before/after numbers in the README per the standing
rule that gain changes require evidence.

Blocking questions: None outstanding from this session. Architectural and
hardware questions still live in the "Known open questions" section above.
