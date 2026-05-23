# Modbus Register Map — THE CONTRACT

This document defines the Modbus TCP register contract between the **simulator**
(or, later, the **real hardware I/O**) and the **OpenPLC control logic**.

> **This register map is the contract. It is mirrored in code by
> `simulator/modbus_map.py`. Neither the simulator nor the PLC control logic may
> be changed without updating this document and `modbus_map.py` together.**

Transport: **Modbus TCP.** The simulator hosts the server; OpenPLC is the
master/client. The server prefers the standard port **502** and automatically
falls back to **5020** when 502 is not bindable by an unprivileged process
(see `simulator/modbus_server.py`). **Point the OpenPLC Modbus master at
whichever port the simulator logged on startup** — 5020 in the common
(non-root) case.

A note on the addressing convention: addresses are written in the classic
4xxxx / 3xxxx "data model" notation. On the wire these are zero-based offsets
(e.g. `40001` = holding register offset `0`, `30001` = input register offset
`0`). Confirm the offset convention in the OpenPLC slave configuration when
wiring this up.

---

## Holding Registers — commands the simulator reads

These carry commands *to* the engine/load model. **Writers:** the operator
(HMI / dashboard) sets TARGET_RPM, CONTROL_MODE and SAFETY_ENABLE; the PLC
computes and writes only VALVE_POSITION_CMD (and the operator may write it
directly in manual mode). The simulator treats all four as read-only inputs.

| Address | Name               | Type   | Range       | Units / scaling                          |
|---------|--------------------|--------|-------------|------------------------------------------|
| 40001   | VALVE_POSITION_CMD | uint16 | 0 - 10000   | Commanded brake-valve restriction, scaled 0.0-100.0% (10000 = 100.00%). 0% = valve open / minimum back-pressure; 100% = maximum restriction / maximum back-pressure. |
| 40002   | TARGET_RPM         | uint16 | 0 - 6500    | Target engine RPM for PID/sweep modes    |
| 40003   | CONTROL_MODE       | uint16 | 0 - 2       | 0 = manual, 1 = PID hold, 2 = sweep      |
| 40004   | SAFETY_ENABLE      | uint16 | 0 - 1       | 0 = e-stop (force valve closed), 1 = run |

### Notes
- **40001 VALVE_POSITION_CMD** — the single actuator output, and the only
  holding register the PLC *computes*. Scaled x100 so the controller can command
  0.01% resolution without floats on the wire. The sim applies valve *lag*
  before this becomes the actual position (see 30005). **Physical meaning
  (2026-05-22): a restriction / back-pressure command into the spec'd
  proportional pressure/throttle (non-compensated) valve** (`docs/bom.md`).
  Higher command = more outlet restriction = higher pump-outlet pressure = more
  brake torque = lower RPM. The 0-100% range, x100 scaling, and control polarity
  (higher = more braking) are **unchanged** — only the actuator's physical
  identity is now fixed, so no PLC or sim code change is implied by this register.
  The driver translating this command to coil current (12 V PWM vs 0-10 V amp
  card) is still TBD.
- **40002 TARGET_RPM** — the speed setpoint, with **mode-scoped ownership**:
  - In **PID mode (1)** the OPERATOR owns it (set via the HMI / dashboard); the
    PLC reads it and holds it.
  - In **SWEEP mode (2)** the PLC sweep logic owns it: on entry and at each step
    it writes the current internal stepping target here, OVERWRITING any operator
    value. This is a documented hand-off, NOT a conflict — it exposes the live
    sweep target on :502 so the dashboard setpoint line tracks the staircase and
    the logger records it.
  Capped at 6500 to stay below the safety RPM limit.
- **40003 CONTROL_MODE** — operator-selected. Manual passes VALVE_POSITION_CMD
  straight through; PID hold drives the valve to hold TARGET_RPM; sweep ramps
  RPM across a band. There is no separate "engine enable" register —
  SAFETY_ENABLE is the master run/stop.
- **40004 SAFETY_ENABLE** — master run/stop. When 0, the PLC safety interlock
  forces the valve to 0 regardless of mode. The PLC interlock will also **drive
  this to 0 itself** on a latched fault. This is software e-stop; a hardware
  e-stop is a separate, non-negotiable circuit on the real rig.

---

## Sweep Registers (MODE_SWEEP) — operator params + PLC status

These registers drive the stepped acceleration sweep (CONTROL_MODE = 2). They
live in the PLC's `%QW` space and are exposed to the dashboard by OpenPLC's
built-in Modbus server on **:502**. Unlike 40001-40004 they are **NOT mirrored
to the simulator** — the sim does not model the sweep, so they stay on the
PLC ↔ dashboard (:502) side only and `simulator/modbus_map.py` is unchanged.

| Address | %QW    | Name            | Type   | Range       | Owner    | Meaning |
|---------|--------|-----------------|--------|-------------|----------|---------|
| 40005   | %QW104 | SWEEP_START_RPM | uint16 | 2500 - 6100 | operator | First step's target RPM. Lower clamp 2500 (just above warm idle ~2400). With the clutch removed the brake-capacity floor is ~3360 RPM (re-probed 2026-05-22 after the Stock/Unrestricted 206 curve correction; was ~3135 under the old restricted curve); starting below it just saturates the PID on the low steps (RPM sits at the floor). Dashboard default 3400 (just above the floor). |
| 40006   | %QW105 | SWEEP_END_RPM   | uint16 | 2500 - 6100 | operator | Top of the sweep band; the sweep ends after the step at/above this completes. Capped at 6100 (limiter). |
| 40007   | %QW106 | SWEEP_STEP_RPM  | uint16 | 100 - 1000  | operator | RPM increment per step (typical 200-400). |
| 40008   | %QW107 | SWEEP_DWELL_MS  | uint16 | 500 - 30000 | operator | Time held at each step (ms) so the load cell gets a clean torque reading. Counted off the PLC scan, not wall-clock. Capped at 30000 (PLC reads it as a signed 16-bit INT). |
| 40009   | %QW108 | SWEEP_STATE     | uint16 | 0 - 2       | PLC      | 0 = idle, 1 = running, 2 = complete. PLC-written; the dashboard polls it to show progress and auto-close the run on completion. |

### Notes
- **CONTROL_MODE = 2 activates these.** The sweep is a SUPERVISOR over the
  mode-1 PID: it steps an internal setpoint from SWEEP_START_RPM toward
  SWEEP_END_RPM by SWEEP_STEP_RPM, dwelling SWEEP_DWELL_MS at each step, and
  reuses the existing PID to hold each step. It does not reimplement valve
  control.
- **Self-terminating.** When the final step's dwell completes, the PLC sets
  SWEEP_STATE = 2 and writes SAFETY_ENABLE = 0 itself — the engine disables and
  coasts down. This is the only place the control logic ends a run on its own
  (not on a fault).
- **SWEEP_STATE is a PLC output (`%QW108`), not an input register.** OpenPLC
  input registers (`%IW`) are sourced from the slave device (sim / field I/O)
  and cannot be written by the control program, so a PLC-computed status word
  must live in `%QW`. The dashboard reads it from :502 the same way it reads the
  command read-back.
- **Slave-device (sim mirror) config is unchanged.** Because the sweep registers
  are not mirrored to the sim, the OpenPLC slave-device Input-Register (size 7)
  and Holding-Write (size 4) blocks stay as they were; only the built-in :502
  server's exposed `%QW` range grows to include 104-108. (`simulator/modbus_map.py`
  therefore does not change for the sweep — these registers are not part of the
  sim's Modbus interface.)

---

## Input Registers — simulator writes, PLC reads

These carry sensed values *from* the engine/load model *to* the controller.
**Owner: simulator** (on real hardware, owner becomes the sensor I/O layer).
The PLC must treat these as read-only.

| Address | Name               | Type   | Range       | Units / scaling                                   |
|---------|--------------------|--------|-------------|---------------------------------------------------|
| 30001   | ENGINE_RPM         | uint16 | 0 - 7000    | Engine speed, RPM (1:1)                           |
| 30002   | TORQUE_FTLBS_x10   | uint16 | 0 - 150     | Torque, scaled x10 (105 = 10.5 ft-lbs)            |
| 30003   | HYDRAULIC_PSI      | uint16 | 0 - 3000    | Hydraulic brake pressure, PSI (1:1)               |
| 30004   | HEAD_TEMP_C        | uint16 | 0 - 300     | Cylinder head temperature, degrees C (1:1)        |
| 30005   | VALVE_POSITION_ACT | uint16 | 0 - 10000   | Actual valve position, scaled 0.0-100.0% (reflects lag) |
| 30006   | AFR_x10            | uint16 | 100 - 200   | Air/fuel ratio, scaled x10 (147 = 14.7) — reserved |
| 30007   | SIM_STATUS         | uint16 | 0 - 2       | 0 = stopped, 1 = running, 2 = fault               |
| 30008   | LIMITER_ACTIVE     | uint16 | 0 - 1       | 0 = limiter released, 1 = rev limiter cutting spark |

### Notes
- **30001 ENGINE_RPM** — the **process variable** the speed PID closes on.
  Range extends to 7000 (above the 6500 command cap and 6100 nominal max) so the
  controller can *see* an overspeed condition and act on it. Do not clamp this at
  the command limit.
- **30002 TORQUE_FTLBS_x10** — scaled x10 to carry one decimal place. The sim
  derives this from the torque curve at the current RPM and load. Logged by the
  PLC; not used in the control law.
- **30003 HYDRAULIC_PSI** — brake circuit pressure. Feeds the safety interlock
  (over-pressure trip). **Range widened to 0-3000 PSI (2026-05-22)** for the
  spec'd brake hardware's three-tier pressure scheme: **working ~1128 PSI /
  mechanical relief ~2000 PSI / pump rating 3000 PSI** (`docs/bom.md`). Code:
  `PSI_REG_MAX` in `simulator/modbus_map.py` is bumped 1500 → 3000 to match this
  range (the contract doc and code stay in sync per this file's header). This is
  **behavior-neutral today**: the unchanged overpressure trips (sim
  `OVERPRESSURE_TRIP_PSI` = 900, PLC `PSI_TRIP_PSI` = 750) cap/fault the pressure
  well below 1500, so nothing is published above 1500 yet. See Safety trip limits.
- **30004 HEAD_TEMP_C** — thermal model output; slow-moving (degC, 1:1 — **not**
  scaled). Feeds the over-temperature trip.
- **30005 VALVE_POSITION_ACT** — the *actual* valve position after lag, distinct
  from the commanded 40001. Telemetry today; available as feedback for an
  optional inner valve-position loop (not implemented — the speed loop closes on
  30001, not on this).
- **30006 AFR_x10** — **reserved.** No wideband O2 sensor in Phase 1; the sim
  may emit a nominal 147 (14.7:1) placeholder. Do not build control logic that
  depends on this yet.
- **30007 SIM_STATUS** — health/heartbeat. `2 = fault` causes the PLC to latch a
  fault, close the valve, and clear SAFETY_ENABLE.
- **30008 LIMITER_ACTIVE** — read-only limiter telemetry. `1` while the sim's
  rev limiter is cutting spark (RPM in the 6100+ limiter band, released below
  6000 with hysteresis — see `simulator/engine_sim.py`). The PLC must treat
  this as read-only and **must not** branch its control law on it; it exists
  so the host/logger can flag and exclude limiter-active samples from the
  power curve. Not a fault — distinct from SIM_STATUS.

---

## Safety trip limits (PLC- and sim-enforced)

These are physical-plant limits, not registers. They live in
`simulator/modbus_map.py` as the single source of truth and are enforced **on
both sides**: the sim trips and sets `SIM_STATUS = 2`, and the PLC interlock
independently trips on the same thresholds (defense-in-depth — the PLC does not
trust the status word alone).

| Limit                  | Value     | Source constant         | Checked against |
|------------------------|-----------|-------------------------|-----------------|
| Overspeed              | 6500 RPM  | (PLC `RPM_TRIP_RPM`)    | 30001 ENGINE_RPM |
| Over-pressure (sim)    | 900 PSI   | `OVERPRESSURE_TRIP_PSI` (`simulator/modbus_map.py`) | 30003 HYDRAULIC_PSI |
| Over-pressure (PLC)    | 750 PSI   | `PSI_TRIP_PSI` (`dyno_control.st`) | 30003 HYDRAULIC_PSI |
| Over-temperature       | 250 °C    | `OVERTEMP_TRIP_C`       | 30004 HEAD_TEMP_C |

> The PLC trip thresholds are flagged `(* TODO: calibrate against real hardware *)`
> in `dyno_control.st`. Tune them on the sim, then verify against the real rig.

> **Three-tier pressure scheme (spec'd brake hardware, 2026-05-22):** the brake
> circuit's design pressures are **working ~1128 PSI / mechanical relief ~2000 PSI
> / pump rating 3000 PSI** (`docs/bom.md`). The two overpressure trips above
> (sim 900, PLC 750) currently sit **below the ~1128 PSI working point** — they
> were calibrated to the old 3.5:1 chain-drive / 1.52 cu.in. pressure model and
> are **deliberately NOT changed this session.** With the new physically-grounded
> brake model (`engine_sim.py`), full braking develops ~1128+ PSI and therefore
> trips the sim immediately — expected, and to be resolved next session by
> retuning the PID for the new plant and raising the trips against the ~2000 PSI
> relief. Until then the sim cannot hold the upper band.

---

## How the implemented control logic uses these

`plc/dyno_control.st` binds:

| Role             | Register                 |
|------------------|--------------------------|
| Process variable | 30001 ENGINE_RPM         |
| Setpoint         | 40002 TARGET_RPM         |
| Control output   | 40001 VALVE_POSITION_CMD |
| Mode select      | 40003 CONTROL_MODE       |
| Master enable    | 40004 SAFETY_ENABLE      |
| Fault input      | 30007 SIM_STATUS         |
| Trip inputs      | 30003 PSI, 30004 CHT, 30001 RPM |

---

## Ownership summary

| Direction          | Registers      | Writer                     | Reader |
|--------------------|----------------|----------------------------|--------|
| Valve command      | 40001          | PLC (operator in manual)        | Sim/HW |
| Target RPM         | 40002          | Operator in PID; PLC in SWEEP    | PLC    |
| Mode / enable      | 40003 - 40004  | Operator (HMI / dashboard)      | PLC    |
| Sweep params       | 40005 - 40008  | Operator (dashboard)            | PLC (not sim) |
| Sweep status       | 40009          | PLC                             | Dashboard |
| Telemetry (in)     | 30001 - 30008  | Sim/HW                          | PLC    |

Any change to address, scaling, range, or ownership above is a **contract
change**: update this file and `simulator/modbus_map.py` first, then update both
sides to match.
